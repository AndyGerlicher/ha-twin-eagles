#!/usr/bin/env python3
"""Logging pass-through proxy that stands in for te.bonelessgrills.com.

Point the grill's DNS for te.bonelessgrills.com at this machine. Each HTTPS request from the grill is
logged in plain text, forwarded unchanged to the real cloud server, and the real reply is logged and
returned, so the grill keeps working normally. If the grill verifies certificates it will refuse the
self-signed certificate; that shows up as a TLS error in the log and nothing is forwarded.

Usage:
    python3 tools/cloud_proxy.py --upstream <real server IP>

Look up the real IP before redirecting DNS, e.g. `dig @1.1.1.1 te.bonelessgrills.com +short`.

Logs go to results/cloud_proxy_<timestamp>/ (gitignored: they contain the grill's identifiers).
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import threading
from datetime import datetime

HOST = "te.bonelessgrills.com"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

lock = threading.Lock()


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def make_cert(outdir: str) -> tuple[str, str]:
    cert, key = os.path.join(outdir, "cert.pem"), os.path.join(outdir, "key.pem")
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365", "-subj", f"/CN={HOST}",
         "-addext", f"subjectAltName=DNS:{HOST}", "-keyout", key, "-out", cert],
        check=True, capture_output=True,
    )
    return cert, key


def read_until(sock, marker: bytes, buf: bytes) -> tuple[bytes, bytes]:
    while marker not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("closed before " + repr(marker))
        buf += chunk
    head, _, rest = buf.partition(marker)
    return head, rest


def read_exact(sock, n: int, buf: bytes) -> tuple[bytes, bytes]:
    while len(buf) < n:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError("closed mid-body")
        buf += chunk
    return buf[:n], buf[n:]


def read_chunked(sock, buf: bytes) -> tuple[bytes, bytes]:
    body = b""
    while True:
        line, buf = read_until(sock, b"\r\n", buf)
        size = int(line.split(b";")[0], 16)
        if size == 0:
            _, buf = read_until(sock, b"\r\n", buf)
            return body, buf
        data, buf = read_exact(sock, size + 2, buf)
        body += data[:-2]


def read_message(sock, buf: bytes = b"", on_expect=None) -> tuple[bytes, dict, bytes]:
    """Read one HTTP message. Returns (start line + headers, header dict, decoded body)."""
    head, buf = read_until(sock, b"\r\n\r\n", buf)
    lines = head.split(b"\r\n")
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(b":")
        headers[name.strip().lower().decode()] = value.strip().decode(errors="replace")
    if on_expect and headers.get("expect", "").lower() == "100-continue":
        on_expect()
    if headers.get("transfer-encoding", "").lower() == "chunked":
        body, buf = read_chunked(sock, buf)
    elif "content-length" in headers:
        body, buf = read_exact(sock, int(headers["content-length"]), buf)
    elif lines[0].startswith(b"HTTP/"):
        while chunk := sock.recv(65536):
            buf += chunk
        body = buf
    else:
        body = b""
    return head, headers, body


def rebuild(head: bytes, body: bytes, drop: set[str]) -> bytes:
    lines = [ln for ln in head.split(b"\r\n") if ln.split(b":")[0].strip().lower().decode() not in drop]
    lines = [lines[0], *lines[1:], b"Content-Length: " + str(len(body)).encode(), b"Connection: close"]
    return b"\r\n".join(lines) + b"\r\n\r\n" + body


def upstream_exchange(ip: str, request: bytes, tls: bool) -> tuple[bytes, dict, bytes]:
    with socket.create_connection((ip, 443 if tls else 80), timeout=20) as raw:
        if not tls:
            raw.sendall(request)
            return read_message(raw)
        with ssl.create_default_context().wrap_socket(raw, server_hostname=HOST) as s:
            s.sendall(request)
            return read_message(s)


def handle(conn: socket.socket, addr, args, outdir: str, counter: list[int], tls: bool = True) -> None:
    try:
        head, headers, body = read_message(conn, on_expect=lambda: conn.sendall(b"HTTP/1.1 100 Continue\r\n\r\n"))
        request = rebuild(head, body, {"content-length", "transfer-encoding", "expect", "connection"})
        rhead, rheaders, rbody = upstream_exchange(args.upstream, request, tls)
        conn.sendall(rebuild(rhead, rbody, {"content-length", "transfer-encoding", "connection"}))
        with lock:
            counter[0] += 1
            n = counter[0]
            record = {
                "n": n,
                "time": datetime.now().isoformat(),
                "client": addr[0],
                "tls": tls,
                "request": head.decode(errors="replace"),
                "request_body": body.decode(errors="replace"),
                "response": rhead.decode(errors="replace"),
                "response_body": rbody.decode(errors="replace"),
            }
            with open(os.path.join(outdir, "exchanges.jsonl"), "a") as f:
                f.write(json.dumps(record) + "\n")
        log(f"#{n} {'https' if tls else 'http'} {head.split(b' ')[0].decode()} {head.split(b' ')[1].decode()} "
            f"({len(body)} bytes) -> {rhead.split(b' ')[1].decode()} ({len(rbody)} bytes)")
    except Exception as e:  # noqa: BLE001 - keep serving
        log(f"{addr[0]}: error {e!r}")
    finally:
        conn.close()


def serve_http(args, outdir: str, counter: list[int]) -> None:
    srv = socket.create_server(("0.0.0.0", args.http_port), reuse_port=True)
    log(f"listening on :{args.http_port} (plain HTTP)")
    while True:
        raw, addr = srv.accept()
        raw.settimeout(20)
        threading.Thread(target=handle, args=(raw, addr, args, outdir, counter, False), daemon=True).start()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--upstream", required=True, help="Real cloud server IP (local DNS is redirected)")
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--http-port", type=int, default=80, help="Plain HTTP pass-through (the grill's clock request)")
    args = ap.parse_args()

    outdir = os.path.join(ROOT, "results", f"cloud_proxy_{datetime.now():%Y%m%d_%H%M%S}")
    os.makedirs(outdir, exist_ok=True)
    cert, key = make_cert(outdir)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1
    ctx.load_cert_chain(cert, key)

    srv = socket.create_server(("0.0.0.0", args.port), reuse_port=True)
    log(f"listening on :{args.port}, forwarding to {args.upstream}, logging to {outdir}")
    counter = [0]
    threading.Thread(target=serve_http, args=(args, outdir, counter), daemon=True).start()
    while True:
        raw, addr = srv.accept()
        raw.settimeout(20)
        try:
            conn = ctx.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError) as e:
            log(f"{addr[0]}: TLS handshake failed: {e!r}")
            raw.close()
            continue
        threading.Thread(target=handle, args=(conn, addr, args, outdir, counter), daemon=True).start()


if __name__ == "__main__":
    main()

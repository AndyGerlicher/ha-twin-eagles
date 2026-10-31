#!/usr/bin/env python3
"""Probe a Twin Eagles grill while connected to its own Wi-Fi (GRILL WIFI / BGX-TE_ network).

Works offline and only uses the standard library (runs on macOS's built-in python3).
Everything it sends is read-only: TCP connects, passive banner reads, HTTP GET on web ports, and the
app's "get_all" status request. It never sends commands that change the grill.

Usage:
    python3 tools/grill_ap_probe.py [--key <PRODUCT_KEY>]

The product key is on the grill under SETTINGS > DEVICE INFO > Product Key. Without --key it is read from
TE_PRODUCT_KEY in the repo's .env.
Results are written to results/grill_ap_<timestamp>/ (results.json + summary.txt).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import json
import os
import platform
import re
import resource
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime

# Addresses the app uses in local mode: pellet grills (device_operations.php) and ovens (/app/status).
KNOWN_HOSTS = ["192.168.0.1", "192.168.4.1"]
# The only operation sent to device_operations.php. It is what the app polls for status.
READ_OPERATION = "get_all"
WEB_PORTS = {80, 443, 8000, 8008, 8080, 8081, 8443, 8888, 5000, 3000}
STATUS_SAMPLES = 5
SAMPLE_INTERVAL = 3

PHP_TZ_WARNING = re.compile(r"<br />\s*<b>Warning</b>:.*?<br />\s*", re.S)


def env_key() -> str | None:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(path):
        return None
    for line in open(path):
        name, _, value = line.strip().partition("=")
        if name.strip() == "TE_PRODUCT_KEY" and value.strip():
            return value.strip().strip("'\"")
    return None


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def run(cmd: list[str], timeout: float = 10) -> dict:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"cmd": " ".join(cmd), "rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        return {"cmd": " ".join(cmd), "rc": None, "stdout": out, "stderr": "timeout"}
    except Exception as e:  # noqa: BLE001 - record everything, never abort
        return {"cmd": " ".join(cmd), "error": repr(e)}


def network_info() -> dict:
    info = {"platform": platform.platform(), "python": sys.version}
    route = run(["route", "-n", "get", "default"])
    info["route_default"] = route
    gw = re.search(r"gateway:\s*(\S+)", route.get("stdout", ""))
    iface = re.search(r"interface:\s*(\S+)", route.get("stdout", ""))
    info["gateway"] = gw.group(1) if gw else None
    info["interface"] = iface.group(1) if iface else "en0"
    info["ifconfig"] = run(["ifconfig", info["interface"]])
    info["arp"] = run(["arp", "-an"])
    info["ssid_networksetup"] = run(["networksetup", "-getairportnetwork", info["interface"]])
    info["ipconfig_summary"] = run(["ipconfig", "getsummary", info["interface"]])
    info["mdns_services"] = run(["dns-sd", "-B", "_services._dns-sd._udp", "local."], timeout=6)
    return info


def tcp_open(host: str, port: int, timeout: float = 0.6) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def scan_workers() -> int:
    """Stay under the open file limit (macOS terminals default to 256)."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    try:
        target = 4096 if hard == resource.RLIM_INFINITY else min(4096, hard)
        resource.setrlimit(resource.RLIMIT_NOFILE, (max(soft, target), hard))
        soft = max(soft, target)
    except (ValueError, OSError):
        pass
    return max(16, min(400, soft - 64))


def scan(host: str) -> list[int]:
    with concurrent.futures.ThreadPoolExecutor(scan_workers()) as ex:
        results = ex.map(lambda p: p if tcp_open(host, p) else None, range(1, 65536))
        return [p for p in results if p]


def passive_banner(host: str, port: int, wait: float = 3) -> dict:
    """Connect and read whatever the service volunteers, without sending anything."""
    s = socket.socket()
    s.settimeout(wait)
    try:
        s.connect((host, port))
        data = b""
        try:
            while len(data) < 4096:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
        except socket.timeout:
            pass
        return {"bytes": len(data), "text": data.decode(errors="replace"), "hex": data[:512].hex()}
    except OSError as e:
        return {"error": repr(e)}
    finally:
        s.close()


def http_request(host: str, port: int, method: str, path: str, body: bytes | None = None,
                 headers: dict | None = None, timeout: float = 6) -> dict:
    try:
        conn = http.client.HTTPConnection(host, port, timeout=timeout)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        data = resp.read(65536)
        conn.close()
        return {
            "status": resp.status,
            "reason": resp.reason,
            "headers": dict(resp.getheaders()),
            "body": data.decode(errors="replace"),
        }
    except Exception as e:  # noqa: BLE001
        return {"error": repr(e)}


def multipart(fields: dict) -> tuple[bytes, str]:
    boundary = "----probe" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n')
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode(), f"multipart/form-data; boundary={boundary}"


def get_all(host: str, key: str) -> dict:
    """Exactly what the app sends to poll status in local mode."""
    body, ctype = multipart({"operation": READ_OPERATION, "clave": key, "sleep_get_all": "500"})
    return http_request(host, 80, "POST", "/device_operations.php", body, {"Content-Type": ctype})


def parse_get_all(text: str) -> dict:
    """The response is space separated 'name value name value ...' tokens."""
    tokens = PHP_TZ_WARNING.sub("", text).split()
    return {tokens[i]: tokens[i + 1] for i in range(0, len(tokens) - 1, 2)}


def step(r: dict, name: str, fn, message: str) -> None:
    log(message)
    try:
        r[name] = fn()
    except Exception as e:  # noqa: BLE001
        r[name + "_error"] = repr(e)
        log(f"  failed: {e!r}")


def probe_host(host: str, key: str | None, results: dict) -> None:
    r = results.setdefault("hosts", {}).setdefault(host, {})
    log(f"{host}: checking reachability")
    ping = run(["ping", "-c", "2", "-t", "4", host])
    r["ping"] = ping
    r["responds_to_ping"] = ping.get("rc") == 0
    # Most important first: the app's status request. Each step is isolated so one failure can't stop the rest.
    if tcp_open(host, 80, 3):
        step(r, "device_operations_get", lambda: http_request(host, 80, "GET", "/device_operations.php"),
             f"{host}: GET /device_operations.php (no parameters)")
        step(r, "get_all_no_key", lambda: get_all(host, ""),
             f"{host}: get_all with an empty key (to learn how auth failures look)")
        if key:
            r["get_all"] = []
            for i in range(STATUS_SAMPLES):
                log(f"{host}: get_all sample {i + 1}/{STATUS_SAMPLES}")
                resp = get_all(host, key)
                resp["time"] = datetime.now().isoformat()
                if "body" in resp:
                    resp["parsed"] = parse_get_all(resp["body"])
                r["get_all"].append(resp)
                if i < STATUS_SAMPLES - 1:
                    time.sleep(SAMPLE_INTERVAL)
        step(r, "app_status", lambda: http_request(host, 80, "GET", f"/app/status?prodKey={key or ''}"),
             f"{host}: oven-style GET /app/status")
    else:
        r["port_80"] = "closed"
        log(f"{host}: port 80 closed")

    step(r, "open_ports", lambda: scan(host), f"{host}: scanning all TCP ports (about a minute)")
    log(f"{host}: open ports {r.get('open_ports')}")
    r["banners"] = {}
    r["http_root"] = {}
    for port in r.get("open_ports") or []:
        r["banners"][port] = passive_banner(host, port)
        if port in WEB_PORTS:
            r["http_root"][port] = http_request(host, port, "GET", "/")


def summarize(results: dict) -> str:
    lines = [f"Grill AP probe {results['started']}", ""]
    net = results.get("network", {})
    lines.append(f"Interface {net.get('interface')}, gateway {net.get('gateway')}")
    ssid = re.search(r"\bSSID\s*:\s*(.+)", net.get("ipconfig_summary", {}).get("stdout", ""))
    lines.append(f"SSID: {ssid.group(1).strip() if ssid else net.get('ssid_networksetup', {}).get('stdout', '').strip()}")
    for host, r in results.get("hosts", {}).items():
        lines += ["", f"== {host}", f"responds to ping: {r.get('responds_to_ping')}", f"open ports: {r.get('open_ports')}"]
        for port, b in (r.get("banners") or {}).items():
            if b.get("text"):
                lines.append(f"  banner {port}: {b['text'][:120]!r}")
        for port, h in (r.get("http_root") or {}).items():
            lines.append(f"  GET / on {port}: {h.get('status', h.get('error'))}")
        if "get_all_no_key" in r:
            lines.append(f"  get_all (no key): {str(r['get_all_no_key'].get('body', r['get_all_no_key']))[:200]!r}")
        for sample in r.get("get_all") or []:
            parsed = sample.get("parsed") or {}
            lines.append(
                f"  get_all: status={sample.get('status', sample.get('error'))} fields={len(parsed)} "
                f"setpoint={parsed.get('consigna(1)')} pit={parsed.get('temp(1)')} state={parsed.get('estadoBBQ')}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", help="Product key from SETTINGS > DEVICE INFO on the grill")
    ap.add_argument("--hosts", nargs="*", help="Override hosts to probe (default: gateway + known addresses)")
    ap.add_argument("--out", default="results", help="Output directory (default: results)")
    args = ap.parse_args()

    key = args.key or env_key()
    if not key and sys.stdin.isatty():
        key = input("Product key (Enter to skip): ").strip() or None

    started = datetime.now()
    outdir = os.path.join(args.out, f"grill_ap_{started:%Y%m%d_%H%M%S}")
    os.makedirs(outdir, exist_ok=True)
    results: dict = {"started": started.isoformat(), "key_provided": bool(key)}

    def save() -> None:
        with open(os.path.join(outdir, "results.json"), "w") as f:
            json.dump(results, f, indent=2, default=str)

    try:
        log("collecting network info")
        results["network"] = network_info()
        save()
        hosts = args.hosts or list(dict.fromkeys([results["network"].get("gateway"), *KNOWN_HOSTS]))
        for host in [h for h in hosts if h]:
            try:
                probe_host(host, key, results)
            except Exception as e:  # noqa: BLE001
                results.setdefault("hosts", {}).setdefault(host, {})["error"] = repr(e)
            save()
    except KeyboardInterrupt:
        results["interrupted"] = True
    finally:
        results["finished"] = datetime.now().isoformat()
        save()
        summary = summarize(results)
        with open(os.path.join(outdir, "summary.txt"), "w") as f:
            f.write(summary)
        print("\n" + summary)
        log(f"saved to {os.path.abspath(outdir)}")


if __name__ == "__main__":
    main()

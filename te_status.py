#!/usr/bin/env python3
"""Read-only status client for the Twin Eagles cloud API (te.bonelessgrills.com).

Reverse engineered from the Android app (v2.2.1). Only performs login + GETs.

Usage:
    Put TE_USER / TE_PASS in .env (or the environment), then: python3 te_status.py [-v]
"""
import json
import os
import sys
import urllib.request

BASE = "https://te.bonelessgrills.com/app/"


def call(method, path, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


def load_env(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    if not os.path.exists(path):
        return
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main():
    load_env()
    user, pw = os.environ.get("TE_USER"), os.environ.get("TE_PASS")
    if not user or not pw:
        sys.exit("Set TE_USER and TE_PASS")

    token = call("POST", "account/login", body={"username": user, "password": pw})["id_token"]
    devices = call("GET", "account/devices", token)

    for dev in devices:
        print(f"== {dev.get('name')} ({dev.get('technology')}/{dev.get('identifier')})")
        status = call("GET", f"{dev['technology'].lower()}/{dev['identifier']}", token)
        if "-v" in sys.argv:
            print(json.dumps(status, indent=2))
        for chamber in status.get("chambers") or []:
            pit = chamber["probes"][0]
            print(f"  chamber {chamber.get('numChamber')}: on={chamber.get('onOff')} mode={chamber.get('mode')}")
            print(f"  set temp:     {pit.get('targetTemperature')} °F")
            print(f"  current temp: {pit.get('currentTemperature')} °F")
            for probe in chamber["probes"][1:]:
                print(f"  probe {probe.get('numProbe')}: {probe.get('currentTemperature')} °F "
                      f"(target {probe.get('targetTemperature')})")


if __name__ == "__main__":
    main()

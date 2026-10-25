"""Client for the Twin Eagles cloud API (te.bonelessgrills.com).

Reverse engineered from the Android app v2.2.1. Temperatures are always °F.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import aiohttp

from .base import GrillAuthError, GrillClient, GrillConnectionError
from .models import GrillDevice, GrillStatus, Probe

BASE_URL = "https://te.bonelessgrills.com/app/"
TIMEOUT = aiohttp.ClientTimeout(total=15)

# Unplugged probes report 0 °C.
UNPLUGGED_PROBE_TEMP = 32


class CloudClient(GrillClient):
    """Cloud API client. Logs in lazily and again when the token expires."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    async def async_login(self) -> None:
        try:
            data = await self._request(
                "POST", "account/login", {"username": self._username, "password": self._password}, auth=False
            )
        except GrillAuthError:
            self._token = None
            raise
        token = data.get("id_token") if isinstance(data, dict) else None
        if not token:
            raise GrillAuthError("Login response had no token")
        self._token = token

    async def async_list_devices(self) -> list[GrillDevice]:
        devices = await self._authed("GET", "account/devices")
        return [
            GrillDevice(
                id=d["identifier"],
                name=d.get("name") or d["identifier"],
                technology=d["technology"],
                model=d.get("model"),
            )
            for d in devices
        ]

    async def async_get_status(self, device: GrillDevice) -> GrillStatus:
        # The status path is case sensitive: the device list says PELLETS, the API wants pellets.
        data = await self._authed("GET", f"{device.technology.lower()}/{device.id}")
        return parse_status(data)

    async def _authed(self, method: str, path: str) -> Any:
        if self._token is None:
            await self.async_login()
        try:
            return await self._request(method, path)
        except GrillAuthError:
            await self.async_login()
            return await self._request(method, path)

    async def _request(self, method: str, path: str, body: Any = None, auth: bool = True) -> Any:
        headers = {"Content-Type": "application/json"}
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            async with self._session.request(
                method, BASE_URL + path, json=body, headers=headers, timeout=TIMEOUT
            ) as resp:
                if resp.status in (400, 401, 403) and (not auth or path == "account/login"):
                    raise GrillAuthError(f"Login rejected ({resp.status})")
                if resp.status in (401, 403):
                    raise GrillAuthError(f"Token rejected ({resp.status})")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise GrillConnectionError(str(err)) from err


def parse_status(data: dict[str, Any]) -> GrillStatus:
    chamber = (data.get("chambers") or [{}])[0]
    probes = chamber.get("probes") or []
    pit = probes[0] if probes else {}
    alarms = [a.get("type") for a in chamber.get("currentAlarms") or [] if a.get("type")]
    last_ms = data.get("lastDeviceUpdate") or 0

    return GrillStatus(
        online=last_ms > 0 and "DEVICE_NOT_FOUND" not in alarms,
        on=bool(chamber.get("onOff")),
        mode=(chamber.get("mode") or "").lower() or None,
        pit_temperature=pit.get("currentTemperature"),
        set_temperature=pit.get("targetTemperature"),
        probes=[
            Probe(
                number=p["numProbe"],
                temperature=None
                if p.get("currentTemperature") == UNPLUGGED_PROBE_TEMP
                else p.get("currentTemperature"),
                target=p.get("targetTemperature"),
            )
            for p in probes[1:]
        ],
        fan=bool(chamber.get("fan")),
        ignitor=bool(chamber.get("ignitor")),
        auger=bool(chamber.get("motor")),
        light=bool(chamber.get("light")),
        alarms=alarms,
        last_update=datetime.fromtimestamp(last_ms / 1000, tz=timezone.utc) if last_ms else None,
    )

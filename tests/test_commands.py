"""Safety rules for commands, enforced in the client base class."""
from __future__ import annotations

import dataclasses

import pytest

from custom_components.twin_eagles.api import GrillClient, GrillCommandError, GrillStatus

from .conftest import ONLINE, load_status


class FakeClient(GrillClient):
    """Records what would be sent to the grill."""

    def __init__(self, status: GrillStatus) -> None:
        self.status = status
        self.sent: list[tuple] = []

    async def async_list_devices(self):
        return [ONLINE]

    async def async_get_status(self, device):
        return self.status

    async def _async_set_probe_target(self, device, probe, temperature):
        self.sent.append(("target", probe, temperature))

    async def _async_set_mode(self, device, mode):
        self.sent.append(("mode", mode))

    async def _async_set_sear_level(self, device, level):
        self.sent.append(("sear", level))


def running(**changes) -> FakeClient:
    return FakeClient(dataclasses.replace(load_status("status_online"), **changes))


async def test_set_temperature() -> None:
    client = running()
    await client.async_set_temperature(ONLINE, 225)
    assert client.sent == [("target", 0, 225)]


@pytest.mark.parametrize("temperature", [139, 726])
async def test_set_temperature_out_of_range(temperature) -> None:
    client = running()
    with pytest.raises(GrillCommandError):
        await client.async_set_temperature(ONLINE, temperature)
    assert client.sent == []


async def test_set_temperature_not_in_sear_mode() -> None:
    client = running(mode="sear")
    with pytest.raises(GrillCommandError, match="smoke"):
        await client.async_set_temperature(ONLINE, 300)
    assert client.sent == []


@pytest.mark.parametrize(
    ("changes", "message"),
    [({"on": False}, "off"), ({"online": False}, "offline")],
)
async def test_commands_refused_when_not_running(changes, message) -> None:
    client = running(**changes)
    for command in (
        client.async_set_temperature(ONLINE, 225),
        client.async_set_probe_target(ONLINE, 1, 165),
        client.async_set_mode(ONLINE, "smoke"),
        client.async_set_sear_level(ONLINE, "max"),
    ):
        with pytest.raises(GrillCommandError, match=message):
            await command
    assert client.sent == []


async def test_set_probe_target() -> None:
    client = running()
    await client.async_set_probe_target(ONLINE, 2, 165)
    assert client.sent == [("target", 2, 165)]


@pytest.mark.parametrize(("probe", "temperature"), [(0, 165), (4, 165), (1, 99), (1, 226)])
async def test_set_probe_target_invalid(probe, temperature) -> None:
    client = running()
    with pytest.raises(GrillCommandError):
        await client.async_set_probe_target(ONLINE, probe, temperature)
    assert client.sent == []


async def test_set_mode() -> None:
    client = running()
    await client.async_set_mode(ONLINE, "sear")
    assert client.sent == [("mode", "sear")]


async def test_charcoal_mode_not_settable() -> None:
    client = running()
    with pytest.raises(GrillCommandError):
        await client.async_set_mode(ONLINE, "charcoal")
    assert client.sent == []


async def test_set_sear_level() -> None:
    client = running(mode="sear")
    await client.async_set_sear_level(ONLINE, "med")
    assert client.sent == [("sear", "med")]


async def test_sear_level_requires_sear_mode() -> None:
    client = running()
    with pytest.raises(GrillCommandError, match="sear mode"):
        await client.async_set_sear_level(ONLINE, "max")
    assert client.sent == []

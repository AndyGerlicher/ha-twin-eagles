"""Client interface. Implement this to add a new data source (e.g. local polling)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import (
    MAX_PROBE_TARGET,
    MAX_TEMPERATURE,
    MIN_PROBE_TARGET,
    MIN_TEMPERATURE,
    MODE_SEAR,
    PROBE_COUNT,
    SEAR_LEVELS,
    SETTABLE_MODES,
    TEMPERATURE_MODES,
    GrillDevice,
    GrillStatus,
)


class GrillError(Exception):
    """Base error."""


class GrillAuthError(GrillError):
    """Credentials rejected."""


class GrillConnectionError(GrillError):
    """Could not reach the grill or service."""


class GrillCommandError(GrillError):
    """A command was refused because it is invalid or unsafe in the current state."""


class GrillClient(ABC):
    """Access to one or more grills.

    The public set methods check the current status first and refuse to act on a grill that is off or offline,
    so nothing here can bring an idle grill to life. There is deliberately no start command.
    """

    @abstractmethod
    async def async_list_devices(self) -> list[GrillDevice]:
        """Return the grills this client can reach."""

    @abstractmethod
    async def async_get_status(self, device: GrillDevice) -> GrillStatus:
        """Return the current status of a grill."""

    async def async_set_temperature(self, device: GrillDevice, temperature: int) -> None:
        """Set the pit temperature (°F). Only allowed in smoke modes."""
        _check_range("Temperature", temperature, MIN_TEMPERATURE, MAX_TEMPERATURE)
        status = await self._async_require_running(device)
        if status.mode not in TEMPERATURE_MODES:
            raise GrillCommandError(f"Temperature can only be set in {', '.join(TEMPERATURE_MODES)} mode")
        await self._async_set_probe_target(device, 0, temperature)

    async def async_set_probe_target(self, device: GrillDevice, probe: int, temperature: int) -> None:
        """Set a meat probe target (°F)."""
        if not 1 <= probe <= PROBE_COUNT:
            raise GrillCommandError(f"Probe must be 1-{PROBE_COUNT}; use async_set_temperature for the pit")
        _check_range("Probe target", temperature, MIN_PROBE_TARGET, MAX_PROBE_TARGET)
        await self._async_require_running(device)
        await self._async_set_probe_target(device, probe, temperature)

    async def async_set_mode(self, device: GrillDevice, mode: str) -> None:
        if mode not in SETTABLE_MODES:
            raise GrillCommandError(f"Mode must be one of {', '.join(SETTABLE_MODES)}")
        await self._async_require_running(device)
        await self._async_set_mode(device, mode)

    async def async_set_sear_level(self, device: GrillDevice, level: str) -> None:
        if level not in SEAR_LEVELS:
            raise GrillCommandError(f"Sear level must be one of {', '.join(SEAR_LEVELS)}")
        status = await self._async_require_running(device)
        if status.mode != MODE_SEAR:
            raise GrillCommandError("Sear level can only be set in sear mode")
        await self._async_set_sear_level(device, level)

    async def _async_require_running(self, device: GrillDevice) -> GrillStatus:
        status = await self.async_get_status(device)
        if not status.online:
            raise GrillCommandError("Grill is offline")
        if not status.on:
            raise GrillCommandError("Grill is off; start it from the grill or the app first")
        return status

    @abstractmethod
    async def _async_set_probe_target(self, device: GrillDevice, probe: int, temperature: int) -> None:
        """Send a target temperature. Probe 0 is the pit. Inputs are already validated."""

    @abstractmethod
    async def _async_set_mode(self, device: GrillDevice, mode: str) -> None:
        """Send a mode change. Inputs are already validated."""

    @abstractmethod
    async def _async_set_sear_level(self, device: GrillDevice, level: str) -> None:
        """Send a sear level change. Inputs are already validated."""


def _check_range(name: str, value: int, low: int, high: int) -> None:
    if not low <= value <= high:
        raise GrillCommandError(f"{name} must be between {low} and {high} °F")

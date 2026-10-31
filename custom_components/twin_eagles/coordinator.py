"""Polling coordinator. Works with any GrillClient implementation."""
from __future__ import annotations

import logging
from datetime import timedelta
from collections.abc import Awaitable, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GrillAuthError, GrillClient, GrillCommandError, GrillDevice, GrillError, GrillStatus
from .const import (
    CONF_ACTIVE_INTERVAL,
    CONF_IDLE_INTERVAL,
    DEFAULT_ACTIVE_INTERVAL,
    DEFAULT_IDLE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

type TwinEaglesConfigEntry = ConfigEntry[TwinEaglesCoordinator]


class TwinEaglesCoordinator(DataUpdateCoordinator[GrillStatus]):
    """Fetches status for a single grill."""

    def __init__(
        self, hass: HomeAssistant, entry: TwinEaglesConfigEntry, client: GrillClient, device: GrillDevice
    ) -> None:
        self.idle_interval = timedelta(seconds=entry.options.get(CONF_IDLE_INTERVAL, DEFAULT_IDLE_INTERVAL))
        self.active_interval = timedelta(seconds=entry.options.get(CONF_ACTIVE_INTERVAL, DEFAULT_ACTIVE_INTERVAL))
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {device.id}", update_interval=self.idle_interval
        )
        self.client = client
        self.device = device

    async def _async_update_data(self) -> GrillStatus:
        try:
            status = await self.client.async_get_status(self.device)
        except GrillAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GrillError as err:
            raise UpdateFailed(str(err)) from err
        self.update_interval = self.active_interval if status.online and status.on else self.idle_interval
        return status

    async def async_command(self, command: Callable[[GrillClient, GrillDevice], Awaitable[None]]) -> None:
        """Run a command against the grill, then refresh so entities reflect the result."""
        try:
            await command(self.client, self.device)
        except GrillCommandError as err:
            raise HomeAssistantError(str(err)) from err
        except GrillAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(str(err)) from err
        except GrillError as err:
            raise HomeAssistantError(f"Could not reach the grill: {err}") from err
        finally:
            await self.async_request_refresh()

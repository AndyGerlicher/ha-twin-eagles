"""Polling coordinator. Works with any GrillClient implementation."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GrillAuthError, GrillClient, GrillDevice, GrillError, GrillStatus
from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)

type TwinEaglesConfigEntry = ConfigEntry[TwinEaglesCoordinator]


class TwinEaglesCoordinator(DataUpdateCoordinator[GrillStatus]):
    """Fetches status for a single grill."""

    def __init__(
        self, hass: HomeAssistant, entry: TwinEaglesConfigEntry, client: GrillClient, device: GrillDevice
    ) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} {device.id}", update_interval=SCAN_INTERVAL
        )
        self.client = client
        self.device = device

    async def _async_update_data(self) -> GrillStatus:
        try:
            return await self.client.async_get_status(self.device)
        except GrillAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GrillError as err:
            raise UpdateFailed(str(err)) from err

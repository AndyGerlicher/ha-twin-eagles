"""Twin Eagles pellet grill integration."""
from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CloudClient, GrillClient, GrillDevice
from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_MODEL, CONF_SOURCE, CONF_TECHNOLOGY, SOURCE_CLOUD
from .coordinator import TwinEaglesConfigEntry, TwinEaglesCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


def create_client(hass: HomeAssistant, data: dict) -> GrillClient:
    """Build the client for a config entry. Add new sources (e.g. local) here."""
    source = data.get(CONF_SOURCE, SOURCE_CLOUD)
    if source == SOURCE_CLOUD:
        return CloudClient(async_get_clientsession(hass), data[CONF_USERNAME], data[CONF_PASSWORD])
    raise ValueError(f"Unknown source {source}")


async def async_setup_entry(hass: HomeAssistant, entry: TwinEaglesConfigEntry) -> bool:
    device = GrillDevice(
        id=entry.data[CONF_DEVICE_ID],
        name=entry.data[CONF_DEVICE_NAME],
        technology=entry.data[CONF_TECHNOLOGY],
        model=entry.data.get(CONF_MODEL),
    )
    coordinator = TwinEaglesCoordinator(hass, entry, create_client(hass, entry.data), device)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: TwinEaglesConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

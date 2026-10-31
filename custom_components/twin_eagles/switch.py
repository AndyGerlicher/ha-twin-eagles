"""Light switch."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TwinEaglesConfigEntry, TwinEaglesCoordinator
from .entity import TwinEaglesEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TwinEaglesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([TwinEaglesLight(entry.runtime_data)])


class TwinEaglesLight(TwinEaglesEntity, SwitchEntity):
    _attr_translation_key = "light"

    def __init__(self, coordinator: TwinEaglesCoordinator) -> None:
        super().__init__(coordinator, "light")

    @property
    def available(self) -> bool:
        # Unlike the cooking controls, the light works while the grill is off.
        return super().available and self.coordinator.data.online

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.light

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(lambda client, device: client.async_set_light(device, True))

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_command(lambda client, device: client.async_set_light(device, False))

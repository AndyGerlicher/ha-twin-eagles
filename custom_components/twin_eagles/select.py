"""Mode and sear level controls."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api.models import MODE_SEAR, SEAR_LEVELS, SETTABLE_MODES
from .coordinator import TwinEaglesConfigEntry, TwinEaglesCoordinator
from .entity import TwinEaglesEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TwinEaglesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([TwinEaglesModeSelect(coordinator), TwinEaglesSearLevelSelect(coordinator)])


class _RunningSelect(TwinEaglesEntity, SelectEntity):
    @property
    def available(self) -> bool:
        # Controls only work on a running grill; the client enforces this too.
        data = self.coordinator.data
        return super().available and data.online and data.on


class TwinEaglesModeSelect(_RunningSelect):
    _attr_translation_key = "mode"
    _attr_options = SETTABLE_MODES

    def __init__(self, coordinator: TwinEaglesCoordinator) -> None:
        super().__init__(coordinator, "mode_select")

    @property
    def current_option(self) -> str | None:
        mode = self.coordinator.data.mode
        return mode if mode in SETTABLE_MODES else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_command(lambda client, device: client.async_set_mode(device, option))


class TwinEaglesSearLevelSelect(_RunningSelect):
    _attr_translation_key = "sear_level"
    _attr_options = SEAR_LEVELS

    def __init__(self, coordinator: TwinEaglesCoordinator) -> None:
        super().__init__(coordinator, "sear_level")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.mode == MODE_SEAR

    @property
    def current_option(self) -> str | None:
        return self.coordinator.data.sear_level

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_command(lambda client, device: client.async_set_sear_level(device, option))

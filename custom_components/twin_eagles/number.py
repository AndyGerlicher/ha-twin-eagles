"""Temperature controls."""
from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api.models import (
    MAX_PROBE_TARGET,
    MAX_TEMPERATURE,
    MIN_PROBE_TARGET,
    MIN_TEMPERATURE,
    PROBE_COUNT,
    TEMPERATURE_MODES,
)
from .coordinator import TwinEaglesConfigEntry, TwinEaglesCoordinator
from .entity import TwinEaglesEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: TwinEaglesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [TwinEaglesTemperatureNumber(coordinator)]
        + [TwinEaglesProbeTargetNumber(coordinator, n) for n in range(1, PROBE_COUNT + 1)]
    )


class _TemperatureNumber(TwinEaglesEntity, NumberEntity):
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    @property
    def available(self) -> bool:
        # Controls only work on a running grill; the client enforces this too.
        data = self.coordinator.data
        return super().available and data.online and data.on


class TwinEaglesTemperatureNumber(_TemperatureNumber):
    """Pit set temperature."""

    _attr_translation_key = "temperature"
    _attr_native_min_value = MIN_TEMPERATURE
    _attr_native_max_value = MAX_TEMPERATURE

    def __init__(self, coordinator: TwinEaglesCoordinator) -> None:
        super().__init__(coordinator, "temperature")

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.mode in TEMPERATURE_MODES

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.set_temperature

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(lambda client, device: client.async_set_temperature(device, round(value)))


class TwinEaglesProbeTargetNumber(_TemperatureNumber):
    """Meat probe target."""

    _attr_translation_key = "probe_target"
    _attr_native_min_value = MIN_PROBE_TARGET
    _attr_native_max_value = MAX_PROBE_TARGET

    def __init__(self, coordinator: TwinEaglesCoordinator, probe: int) -> None:
        super().__init__(coordinator, f"probe_{probe}_target")
        self._probe = probe
        self._attr_translation_placeholders = {"probe": str(probe)}

    @property
    def native_value(self) -> float | None:
        probe = next((p for p in self.coordinator.data.probes if p.number == self._probe), None)
        return probe.target if probe else None

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_command(
            lambda client, device: client.async_set_probe_target(device, self._probe, round(value))
        )

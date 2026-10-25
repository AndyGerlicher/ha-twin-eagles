"""Temperature and status sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import GrillStatus
from .coordinator import TwinEaglesConfigEntry, TwinEaglesCoordinator
from .entity import TwinEaglesEntity

PROBE_COUNT = 3


@dataclass(frozen=True, kw_only=True)
class TwinEaglesSensorDescription(SensorEntityDescription):
    value_fn: Callable[[GrillStatus], Any]


def _temperature(key: str, value_fn: Callable[[GrillStatus], Any], **kwargs: Any) -> TwinEaglesSensorDescription:
    return TwinEaglesSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=value_fn,
        **kwargs,
    )


def _probe(status: GrillStatus, number: int):
    return next((p for p in status.probes if p.number == number), None)


SENSORS: list[TwinEaglesSensorDescription] = [
    _temperature("pit_temperature", lambda s: s.pit_temperature),
    _temperature("set_temperature", lambda s: s.set_temperature),
    TwinEaglesSensorDescription(
        key="mode",
        translation_key="mode",
        value_fn=lambda s: s.mode,
    ),
    TwinEaglesSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.last_update,
    ),
]

for _n in range(1, PROBE_COUNT + 1):
    SENSORS += [
        _temperature(
            f"probe_{_n}_temperature",
            lambda s, n=_n: (p := _probe(s, n)) and p.temperature,
            translation_placeholders={"probe": str(_n)},
        ),
        _temperature(
            f"probe_{_n}_target",
            lambda s, n=_n: (p := _probe(s, n)) and p.target,
            translation_placeholders={"probe": str(_n)},
            entity_registry_enabled_default=False,
        ),
    ]


async def async_setup_entry(
    hass: HomeAssistant, entry: TwinEaglesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(TwinEaglesSensor(coordinator, description) for description in SENSORS)


class TwinEaglesSensor(TwinEaglesEntity, SensorEntity):
    entity_description: TwinEaglesSensorDescription

    def __init__(self, coordinator: TwinEaglesCoordinator, description: TwinEaglesSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if self.entity_description.key == "last_update":
            return super().available
        return super().available and self.coordinator.data.online

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

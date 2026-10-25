"""On/off state sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import GrillStatus
from .coordinator import TwinEaglesConfigEntry, TwinEaglesCoordinator
from .entity import TwinEaglesEntity


@dataclass(frozen=True, kw_only=True)
class TwinEaglesBinarySensorDescription(BinarySensorEntityDescription):
    value_fn: Callable[[GrillStatus], bool]


BINARY_SENSORS: list[TwinEaglesBinarySensorDescription] = [
    TwinEaglesBinarySensorDescription(
        key="power", translation_key="power", device_class=BinarySensorDeviceClass.RUNNING, value_fn=lambda s: s.on
    ),
    TwinEaglesBinarySensorDescription(key="fan", translation_key="fan", value_fn=lambda s: s.fan),
    TwinEaglesBinarySensorDescription(
        key="ignitor", translation_key="ignitor", device_class=BinarySensorDeviceClass.HEAT, value_fn=lambda s: s.ignitor
    ),
    TwinEaglesBinarySensorDescription(
        key="auger", translation_key="auger", device_class=BinarySensorDeviceClass.RUNNING, value_fn=lambda s: s.auger
    ),
    TwinEaglesBinarySensorDescription(
        key="light", translation_key="light", device_class=BinarySensorDeviceClass.LIGHT, value_fn=lambda s: s.light
    ),
    TwinEaglesBinarySensorDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda s: bool(s.alarms),
    ),
    TwinEaglesBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda s: s.online,
    ),
]

# These report even when the grill is offline.
ALWAYS_AVAILABLE = {"online", "alarm"}


async def async_setup_entry(
    hass: HomeAssistant, entry: TwinEaglesConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(TwinEaglesBinarySensor(coordinator, description) for description in BINARY_SENSORS)


class TwinEaglesBinarySensor(TwinEaglesEntity, BinarySensorEntity):
    entity_description: TwinEaglesBinarySensorDescription

    def __init__(self, coordinator: TwinEaglesCoordinator, description: TwinEaglesBinarySensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def available(self) -> bool:
        if self.entity_description.key in ALWAYS_AVAILABLE:
            return super().available
        return super().available and self.coordinator.data.online

    @property
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.key == "alarm":
            return {"alarms": self.coordinator.data.alarms}
        return None

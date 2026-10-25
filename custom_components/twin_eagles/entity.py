"""Base entity."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import TwinEaglesCoordinator


class TwinEaglesEntity(CoordinatorEntity[TwinEaglesCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: TwinEaglesCoordinator, key: str) -> None:
        super().__init__(coordinator)
        device = coordinator.device
        self._attr_unique_id = f"{device.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device.id)},
            name=device.name,
            manufacturer=MANUFACTURER,
            model=device.model or f"{device.technology.title()} grill",
            serial_number=device.id,
        )

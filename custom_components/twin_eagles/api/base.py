"""Client interface. Implement this to add a new data source (e.g. local polling)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from .models import GrillDevice, GrillStatus


class GrillError(Exception):
    """Base error."""


class GrillAuthError(GrillError):
    """Credentials rejected."""


class GrillConnectionError(GrillError):
    """Could not reach the grill or service."""


class GrillClient(ABC):
    """Read-only access to one or more grills."""

    @abstractmethod
    async def async_list_devices(self) -> list[GrillDevice]:
        """Return the grills this client can reach."""

    @abstractmethod
    async def async_get_status(self, device: GrillDevice) -> GrillStatus:
        """Return the current status of a grill."""

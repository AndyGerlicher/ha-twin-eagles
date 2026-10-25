"""Source-agnostic data models. Every client (cloud, local) returns these."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class GrillDevice:
    """A grill registered to the account."""

    id: str
    name: str
    technology: str
    model: str | None = None


@dataclass
class Probe:
    """A meat probe. Temperatures are in °F; None means unplugged/unknown."""

    number: int
    temperature: float | None
    target: float | None


@dataclass
class GrillStatus:
    """Snapshot of a grill. Temperatures are in °F."""

    online: bool
    on: bool
    mode: str | None
    pit_temperature: float | None
    set_temperature: float | None
    probes: list[Probe] = field(default_factory=list)
    fan: bool = False
    ignitor: bool = False
    auger: bool = False
    light: bool = False
    alarms: list[str] = field(default_factory=list)
    last_update: datetime | None = None

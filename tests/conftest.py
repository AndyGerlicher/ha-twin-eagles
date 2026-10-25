"""Shared fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.twin_eagles.api import GrillDevice
from custom_components.twin_eagles.api.cloud import parse_status

FIXTURES = Path(__file__).parent / "fixtures"

ONLINE = GrillDevice(id="BGX_TE_online", name="My Twin Eagles Grill", technology="PELLETS", model="TE01V4")
OFFLINE = GrillDevice(id="BGX_TE_offline", name="My Twin Eagles Grill", technology="PELLETS", model="TE01V4")


def load_status(name: str):
    return parse_status(json.loads((FIXTURES / f"{name}.json").read_text()))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def mock_client():
    """Patch CloudClient everywhere it is constructed."""
    statuses = {ONLINE.id: load_status("status_online"), OFFLINE.id: load_status("status_offline")}
    client = AsyncMock()
    client.async_login.return_value = None
    client.async_list_devices.return_value = [OFFLINE, ONLINE]
    client.async_get_status.side_effect = lambda device: statuses[device.id]
    client.statuses = statuses
    with (
        patch("custom_components.twin_eagles.CloudClient", return_value=client),
        patch("custom_components.twin_eagles.config_flow.CloudClient", return_value=client),
    ):
        yield client

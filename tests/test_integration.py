"""End-to-end tests of config flow, setup and entities."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.twin_eagles.api import GrillAuthError
from custom_components.twin_eagles.const import DOMAIN

from .conftest import OFFLINE, ONLINE

CREDS = {"username": "me@example.com", "password": "pw"}


def make_entry(device=ONLINE) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=device.id,
        title=device.name,
        data={
            **CREDS,
            "source": "cloud",
            "device_id": device.id,
            "device_name": device.name,
            "technology": device.technology,
            "model": device.model,
        },
    )


async def test_config_flow_defaults_to_online_grill(hass: HomeAssistant, mock_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["step_id"] == "device"
    schema = result["data_schema"].schema
    key = next(iter(schema))
    assert key.default() == ONLINE.id
    assert list(schema[key].container)[0] == ONLINE.id

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device_id": ONLINE.id})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["device_id"] == ONLINE.id
    assert result["data"]["model"] == "TE01V4"


async def test_config_flow_invalid_auth(hass: HomeAssistant, mock_client) -> None:
    mock_client.async_login.side_effect = GrillAuthError
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDS)
    assert result["errors"] == {"base": "invalid_auth"}


async def test_entities(hass: HomeAssistant, mock_client) -> None:
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    prefix = "my_twin_eagles_grill"
    pit = hass.states.get(f"sensor.{prefix}_pit_temperature")
    assert float(pit.state) == 247
    assert pit.attributes["unit_of_measurement"] == "°F"
    assert float(hass.states.get(f"sensor.{prefix}_set_temperature").state) == 247
    assert hass.states.get(f"sensor.{prefix}_mode").state == "smoke_plus"
    # Unplugged probes report 32 °F and should show as unknown.
    assert hass.states.get(f"sensor.{prefix}_probe_1_temperature").state == STATE_UNKNOWN
    assert hass.states.get(f"binary_sensor.{prefix}_power").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{prefix}_light").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{prefix}_online").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{prefix}_alarm").state == STATE_OFF


async def test_offline_grill_is_unavailable(hass: HomeAssistant, mock_client) -> None:
    entry = make_entry(OFFLINE)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    prefix = "my_twin_eagles_grill"
    assert hass.states.get(f"sensor.{prefix}_pit_temperature").state == STATE_UNAVAILABLE
    assert hass.states.get(f"binary_sensor.{prefix}_online").state == STATE_OFF
    alarm = hass.states.get(f"binary_sensor.{prefix}_alarm")
    assert alarm.state == STATE_ON
    assert alarm.attributes["alarms"] == ["DEVICE_NOT_FOUND"]


async def test_auth_failure_starts_reauth(hass: HomeAssistant, mock_client) -> None:
    mock_client.async_get_status.side_effect = GrillAuthError
    entry = make_entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]

    mock_client.async_get_status.side_effect = lambda device: mock_client.statuses[device.id]
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {**CREDS, "password": "new"})
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new"

"""End-to-end tests of config flow, setup and entities."""
from __future__ import annotations

import dataclasses
from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.twin_eagles.api import GrillAuthError, GrillCommandError
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
    assert hass.states.get(f"switch.{prefix}_light").state == STATE_OFF
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


async def _setup(hass: HomeAssistant, mock_client, **changes) -> None:
    status = dataclasses.replace(mock_client.statuses[ONLINE.id], **changes)
    mock_client.statuses[ONLINE.id] = status
    hass.config.units = US_CUSTOMARY_SYSTEM
    entry = make_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_controls(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass, mock_client)
    prefix = "my_twin_eagles_grill"

    temp = hass.states.get(f"number.{prefix}_set_temperature")
    assert float(temp.state) == 247
    assert temp.attributes["min"] == 140 and temp.attributes["max"] == 725
    assert hass.states.get(f"select.{prefix}_cooking_mode").state == "smoke_plus"
    # No probe target set (240) shows as unknown.
    assert hass.states.get(f"number.{prefix}_probe_1_target").state == STATE_UNKNOWN
    # Sear level only applies in sear mode.
    assert hass.states.get(f"select.{prefix}_sear_level").state == STATE_UNAVAILABLE

    await hass.services.async_call(
        "number", "set_value", {"entity_id": f"number.{prefix}_set_temperature", "value": 225}, blocking=True
    )
    mock_client.async_set_temperature.assert_awaited_once_with(ONLINE, 225)

    await hass.services.async_call(
        "number", "set_value", {"entity_id": f"number.{prefix}_probe_2_target", "value": 165}, blocking=True
    )
    mock_client.async_set_probe_target.assert_awaited_once_with(ONLINE, 2, 165)

    await hass.services.async_call(
        "select", "select_option", {"entity_id": f"select.{prefix}_cooking_mode", "option": "sear"}, blocking=True
    )
    mock_client.async_set_mode.assert_awaited_once_with(ONLINE, "sear")


async def test_sear_controls(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass, mock_client, mode="sear", sear_level="max")
    prefix = "my_twin_eagles_grill"

    assert hass.states.get(f"number.{prefix}_set_temperature").state == STATE_UNAVAILABLE
    assert hass.states.get(f"select.{prefix}_sear_level").state == "max"
    await hass.services.async_call(
        "select", "select_option", {"entity_id": f"select.{prefix}_sear_level", "option": "min"}, blocking=True
    )
    mock_client.async_set_sear_level.assert_awaited_once_with(ONLINE, "min")


async def test_controls_unavailable_when_off(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass, mock_client, on=False)
    prefix = "my_twin_eagles_grill"
    for entity_id in (
        f"number.{prefix}_set_temperature",
        f"number.{prefix}_probe_1_target",
        f"select.{prefix}_cooking_mode",
        f"select.{prefix}_sear_level",
    ):
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE, entity_id


async def test_command_error_surfaces(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass, mock_client)
    mock_client.async_set_temperature.side_effect = GrillCommandError("Grill is off")
    with pytest.raises(HomeAssistantError, match="Grill is off"):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": "number.my_twin_eagles_grill_set_temperature", "value": 225},
            blocking=True,
        )


async def test_poll_interval_follows_power(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass, mock_client)
    coordinator = hass.config_entries.async_entries(DOMAIN)[0].runtime_data
    assert coordinator.update_interval == timedelta(seconds=20)

    mock_client.statuses[ONLINE.id] = dataclasses.replace(mock_client.statuses[ONLINE.id], on=False)
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(minutes=2)

    mock_client.statuses[ONLINE.id] = dataclasses.replace(mock_client.statuses[ONLINE.id], on=True, online=False)
    await coordinator.async_refresh()
    assert coordinator.update_interval == timedelta(minutes=2)


async def test_options_change_intervals(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass, mock_client)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"active_interval": 10, "idle_interval": 600}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # The entry reloads with the new values; the grill is on, so the fast rate applies.
    assert entry.runtime_data.active_interval == timedelta(seconds=10)
    assert entry.runtime_data.idle_interval == timedelta(minutes=10)
    assert entry.runtime_data.update_interval == timedelta(seconds=10)


async def test_light_works_while_off(hass: HomeAssistant, mock_client) -> None:
    await _setup(hass, mock_client, on=False)
    entity_id = "switch.my_twin_eagles_grill_light"
    assert hass.states.get(entity_id).state == STATE_OFF

    await hass.services.async_call("switch", "turn_on", {"entity_id": entity_id}, blocking=True)
    mock_client.async_set_light.assert_awaited_once_with(ONLINE, True)
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    mock_client.async_set_light.assert_awaited_with(ONLINE, False)


async def test_light_unavailable_when_offline(hass: HomeAssistant, mock_client) -> None:
    entry = make_entry(OFFLINE)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("switch.my_twin_eagles_grill_light").state == STATE_UNAVAILABLE

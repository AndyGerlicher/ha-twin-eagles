"""Config flow: log in to the cloud, then pick a grill."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CloudClient, GrillAuthError, GrillDevice, GrillError
from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, CONF_MODEL, CONF_SOURCE, CONF_TECHNOLOGY, DOMAIN, SOURCE_CLOUD

CREDENTIALS_SCHEMA = vol.Schema({vol.Required(CONF_USERNAME): str, vol.Required(CONF_PASSWORD): str})


class TwinEaglesConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, str] = {}
        self._devices: dict[str, tuple[GrillDevice, bool]] = {}

    async def _async_validate(self, username: str, password: str) -> tuple[CloudClient, str | None]:
        client = CloudClient(async_get_clientsession(self.hass), username, password)
        try:
            await client.async_login()
        except GrillAuthError:
            return client, "invalid_auth"
        except GrillError:
            return client, "cannot_connect"
        return client, None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client, error = await self._async_validate(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            if error is None:
                try:
                    for device in await client.async_list_devices():
                        status = await client.async_get_status(device)
                        self._devices[device.id] = (device, status.online)
                except GrillError:
                    error = "cannot_connect"
            if error:
                errors["base"] = error
            elif not self._devices:
                return self.async_abort(reason="no_devices")
            else:
                self._credentials = user_input
                return await self.async_step_device()

        return self.async_show_form(step_id="user", data_schema=CREDENTIALS_SCHEMA, errors=errors)

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            device, _ = self._devices[user_input[CONF_DEVICE_ID]]
            await self.async_set_unique_id(device.id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=device.name,
                data={
                    **self._credentials,
                    CONF_SOURCE: SOURCE_CLOUD,
                    CONF_DEVICE_ID: device.id,
                    CONF_DEVICE_NAME: device.name,
                    CONF_TECHNOLOGY: device.technology,
                    CONF_MODEL: device.model,
                },
            )

        # Online grills first; accounts often keep stale registrations after a controller swap.
        ordered = sorted(self._devices.values(), key=lambda d: not d[1])
        options = {
            device.id: f"{device.name} ({device.id}) - {'online' if online else 'offline'}"
            for device, online in ordered
        }
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({vol.Required(CONF_DEVICE_ID, default=next(iter(options))): vol.In(options)}),
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            _, error = await self._async_validate(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CREDENTIALS_SCHEMA, {CONF_USERNAME: entry.data[CONF_USERNAME]}
            ),
            errors=errors,
        )

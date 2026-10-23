"""ModuleTwo battery: setup, reconfiguration and polling options."""

import uuid
from collections.abc import Mapping
from typing import Any

import probatio as vol
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from modbus_connection import ModbusError
from mygrid_modbus import UNIT_ID, MyGridDevice, UnsupportedMapError

from .const import (
    CONF_DEVICE,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEVICE_MODULETWO,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .helpers import device_type, interval_schema, normalize_host
from .moduletwo_helpers import create_modbus_params

MODULETWO_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): normalize_host,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)


class ModuleTwoFlow(ConfigFlow):
    """Steps that configure one battery or cluster leader endpoint."""

    def _duplicate(self, data: Mapping[str, Any], exclude: str | None = None) -> bool:
        return any(
            entry.entry_id != exclude
            and device_type(entry) == DEVICE_MODULETWO
            and normalize_host(entry.data[CONF_HOST]) == data[CONF_HOST]
            and entry.data[CONF_PORT] == data[CONF_PORT]
            for entry in self._async_current_entries()
        )

    async def _validate(self, data: Mapping[str, Any]) -> str | None:
        try:
            async with async_get_temporary_unit(
                self.hass, create_modbus_params(data), UNIT_ID
            ) as unit:
                await MyGridDevice(unit).async_read()
        except UnsupportedMapError:
            return "unsupported_map"
        except ModbusError, OSError, TimeoutError:
            return "cannot_connect"
        except HomeAssistantError:
            return "link_settings_in_use"
        return None

    async def async_step_moduletwo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate the map and keep a persistent identity independent of IP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data = MODULETWO_SCHEMA(user_input)
            if self._duplicate(data):
                return self.async_abort(reason="already_configured")
            if error := await self._validate(data):
                errors["base"] = error
            else:
                # Another setup flow may have finished while the probe awaited.
                if self._duplicate(data):
                    return self.async_abort(reason="already_configured")
                await self.async_set_unique_id(uuid.uuid4().hex)
                return self.async_create_entry(
                    title="MyGrid ModuleTwo",
                    data={**data, CONF_DEVICE: DEVICE_MODULETWO},
                )
        return self.async_show_form(
            step_id="moduletwo", data_schema=MODULETWO_SCHEMA, errors=errors
        )

    async def async_step_reconfigure_moduletwo(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Move an existing identity without opening a second connection to it."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = MODULETWO_SCHEMA(user_input)
            if self._duplicate(data, entry.entry_id):
                return self.async_abort(reason="already_configured")
            if all(entry.data.get(key) == value for key, value in data.items()):
                # The active connection already validates these settings.
                return self.async_abort(reason="reconfigure_successful")
            # Even different names can resolve to the same IP. Unload the old
            # entry before probing, respecting the battery's one-client limit.
            if not await self.hass.config_entries.async_unload(entry.entry_id):
                errors["base"] = "cannot_unload"
            else:
                try:
                    error = await self._validate(data)
                except BaseException:
                    # Cancellation must not leave a previously active battery
                    # unloaded. Setup is scheduled so cancellation can propagate.
                    self.hass.config_entries.async_schedule_reload(entry.entry_id)
                    raise
                if error:
                    errors["base"] = error
                    await self.hass.config_entries.async_setup(entry.entry_id)
                else:
                    return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reconfigure_moduletwo",
            data_schema=self.add_suggested_values_to_schema(
                MODULETWO_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


class ModuleTwoOptionsFlow(OptionsFlow):
    """Set the battery polling interval without storing connection data twice."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage polling frequency."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=interval_schema(
                self.config_entry.options.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                ),
                MIN_POLL_INTERVAL,
                MAX_POLL_INTERVAL,
            ),
        )

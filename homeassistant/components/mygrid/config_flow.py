"""UI setup, discovery, reconfiguration and polling options for MyGrid devices."""

import ipaddress
import uuid
from collections.abc import Mapping
from typing import Any, cast

import probatio as vol
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from modbus_connection import ModbusError
from mygrid_modbus import UNIT_ID, MyGridDevice, UnsupportedMapError
from mygrid_voltbridge import (
    VoltBridgeClient,
    VoltBridgeError,
    VoltBridgeInfo,
    VoltBridgeNoDataError,
)

from . import device_type
from .const import (
    CONF_DEVICE,
    CONF_MAC,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEVICE_MODULETWO,
    DEVICE_VOLTBRIDGE,
    DOMAIN,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    VOLTBRIDGE_DEFAULT_POLL_INTERVAL,
    VOLTBRIDGE_MAX_POLL_INTERVAL,
    VOLTBRIDGE_MIN_POLL_INTERVAL,
)
from .moduletwo_helpers import create_modbus_params


@callback
def normalize_host(value: str) -> str:
    """Normalize hostname spelling and equivalent IPv4/IPv6 literals."""
    host = value.strip().rstrip(".").lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        if (
            not host
            or any(char.isspace() for char in host)
            or any(char in host for char in "/:@[]")
        ):
            raise vol.Invalid("Enter a hostname or IP address") from None
        return host


MODULETWO_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): normalize_host,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)
VOLTBRIDGE_SCHEMA = vol.Schema({vol.Required(CONF_HOST): normalize_host})


class MyGridConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure one ModuleTwo battery or VoltBridge P1 meter per entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._mac: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Return the polling options handler of the entry's device family."""
        if device_type(config_entry) == DEVICE_VOLTBRIDGE:
            return VoltBridgeOptionsFlow()
        return ModuleTwoOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which kind of MyGrid device to add."""
        return self.async_show_menu(
            step_id="user", menu_options=[DEVICE_MODULETWO, DEVICE_VOLTBRIDGE]
        )

    # ModuleTwo ---------------------------------------------------------------

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the entry's device family."""
        if device_type(self._get_reconfigure_entry()) == DEVICE_VOLTBRIDGE:
            return await self.async_step_reconfigure_voltbridge(user_input)
        return await self.async_step_reconfigure_moduletwo(user_input)

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

    # VoltBridge --------------------------------------------------------------

    async def _voltbridge_serial(self, host: str) -> tuple[str | None, str | None]:
        """Return ``(serial, error)`` after one real read."""
        client = VoltBridgeClient(host, async_get_clientsession(self.hass))
        try:
            data = await client.async_get_p1_data()
        except VoltBridgeNoDataError:
            return None, "voltbridge_no_data"
        except VoltBridgeError:
            return None, "voltbridge_cannot_connect"
        if not data.meter_serial:
            return None, "voltbridge_no_data"
        return data.meter_serial, None

    async def async_step_voltbridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Identify the meter by its P1 serial, which survives IP changes."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = VOLTBRIDGE_SCHEMA(user_input)[CONF_HOST]
            serial, error = await self._voltbridge_serial(host)
            if serial is None:
                errors["base"] = error or "voltbridge_cannot_connect"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})
                return self.async_create_entry(
                    title="MyGrid VoltBridge",
                    data={CONF_DEVICE: DEVICE_VOLTBRIDGE, CONF_HOST: host},
                )
        return self.async_show_form(
            step_id="voltbridge",
            data_schema=self.add_suggested_values_to_schema(
                VOLTBRIDGE_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Offer a VoltBridge found through its ``_mygrid._tcp`` advertisement."""
        try:
            info = VoltBridgeInfo.from_properties(
                cast(
                    Mapping[str | bytes, str | bytes | None], discovery_info.properties
                )
            )
        except VoltBridgeError:
            return self.async_abort(reason="not_voltbridge")
        self.context["title_placeholders"] = {
            "name": discovery_info.hostname.removesuffix(".local.")
        }
        return await self._async_voltbridge_discovered(
            str(discovery_info.ip_address), info.mac_address
        )

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Follow a known VoltBridge to a new address."""
        mac = ":".join(
            discovery_info.macaddress[i : i + 2] for i in range(0, 12, 2)
        ).lower()
        return await self._async_voltbridge_discovered(discovery_info.ip, mac)

    async def _async_voltbridge_discovered(
        self, host: str, mac: str
    ) -> ConfigFlowResult:
        serial, error = await self._voltbridge_serial(host)
        if serial is None:
            return self.async_abort(reason=error or "voltbridge_cannot_connect")
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_MAC: mac})
        self._host, self._mac = host, mac
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm setting up a discovered VoltBridge."""
        assert self._host is not None
        if user_input is not None:
            data = {CONF_DEVICE: DEVICE_VOLTBRIDGE, CONF_HOST: self._host}
            if self._mac:
                data[CONF_MAC] = self._mac
            return self.async_create_entry(title="MyGrid VoltBridge", data=data)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="discovery_confirm", description_placeholders={"host": self._host}
        )

    async def async_step_reconfigure_voltbridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address of an existing VoltBridge entry."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = VOLTBRIDGE_SCHEMA(user_input)[CONF_HOST]
            serial, error = await self._voltbridge_serial(host)
            if serial is None:
                errors["base"] = error or "voltbridge_cannot_connect"
            elif serial != entry.unique_id:
                return self.async_abort(reason="wrong_device")
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_HOST: host}
                )
        return self.async_show_form(
            step_id="reconfigure_voltbridge",
            data_schema=self.add_suggested_values_to_schema(
                VOLTBRIDGE_SCHEMA, user_input or entry.data
            ),
            errors=errors,
        )


def _interval_schema(current: int, minimum: int, maximum: int) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_POLL_INTERVAL, default=current): vol.All(
                vol.Coerce(int), vol.Range(min=minimum, max=maximum)
            )
        }
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
            data_schema=_interval_schema(
                self.config_entry.options.get(
                    CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                ),
                MIN_POLL_INTERVAL,
                MAX_POLL_INTERVAL,
            ),
        )


class VoltBridgeOptionsFlow(OptionsFlow):
    """Set how often the HTTP snapshot is refreshed alongside UDP push."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start at the VoltBridge-specific step so it has its own text."""
        return await self.async_step_voltbridge_init(user_input)

    async def async_step_voltbridge_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage polling frequency."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="voltbridge_init",
            data_schema=_interval_schema(
                self.config_entry.options.get(
                    CONF_POLL_INTERVAL, VOLTBRIDGE_DEFAULT_POLL_INTERVAL
                ),
                VOLTBRIDGE_MIN_POLL_INTERVAL,
                VOLTBRIDGE_MAX_POLL_INTERVAL,
            ),
        )

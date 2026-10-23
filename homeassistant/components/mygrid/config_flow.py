"""UI setup for MyGrid: choose a device, then use that device's flow."""

from typing import Any

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import DEVICE_MODULETWO, DEVICE_VOLTBRIDGE, DOMAIN
from .helpers import device_type
from .moduletwo_config_flow import ModuleTwoFlow, ModuleTwoOptionsFlow
from .voltbridge_config_flow import VoltBridgeFlow, VoltBridgeOptionsFlow


class MyGridConfigFlow(ModuleTwoFlow, VoltBridgeFlow, domain=DOMAIN):
    """Configure one ModuleTwo battery or VoltBridge P1 meter per entry."""

    VERSION = 1

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

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the entry's device family."""
        if device_type(self._get_reconfigure_entry()) == DEVICE_VOLTBRIDGE:
            return await self.async_step_reconfigure_voltbridge(user_input)
        return await self.async_step_reconfigure_moduletwo(user_input)

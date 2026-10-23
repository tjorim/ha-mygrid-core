"""UI setup for the MyGrid ModuleTwo battery."""

from typing import Any

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import DOMAIN
from .moduletwo_config_flow import ModuleTwoFlow, ModuleTwoOptionsFlow


class MyGridConfigFlow(ModuleTwoFlow, domain=DOMAIN):
    """Configure one battery or cluster leader endpoint."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Return the polling options handler."""
        return ModuleTwoOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Go straight to the battery form; this package supports one device."""
        return await self.async_step_moduletwo(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Reconfigure the battery endpoint."""
        return await self.async_step_reconfigure_moduletwo(user_input)

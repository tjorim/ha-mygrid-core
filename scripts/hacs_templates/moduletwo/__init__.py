"""MyGrid ModuleTwo battery over local Modbus TCP."""

from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .moduletwo_setup import (
    async_setup_moduletwo_entry as async_setup_entry,
)
from .moduletwo_setup import (
    async_unload_moduletwo_entry as async_unload_entry,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

__all__ = ["CONFIG_SCHEMA", "async_setup_entry", "async_unload_entry"]

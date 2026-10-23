"""MyGrid: ModuleTwo batteries over Modbus TCP and VoltBridge P1 meters."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .const import DEVICE_VOLTBRIDGE, DOMAIN
from .helpers import device_type
from .moduletwo_setup import async_setup_moduletwo_entry, async_unload_moduletwo_entry
from .voltbridge_setup import (
    async_setup_voltbridge_entry,
    async_unload_voltbridge_entry,
)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Set up one device of the entry's family."""
    if device_type(entry) == DEVICE_VOLTBRIDGE:
        return await async_setup_voltbridge_entry(hass, entry)
    return await async_setup_moduletwo_entry(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Unload one device of the entry's family."""
    if device_type(entry) == DEVICE_VOLTBRIDGE:
        return await async_unload_voltbridge_entry(hass, entry)
    return await async_unload_moduletwo_entry(hass, entry)

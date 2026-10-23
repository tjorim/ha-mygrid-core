"""Diagnostics for every MyGrid device family."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import device_type
from .const import DEVICE_VOLTBRIDGE
from .moduletwo_diagnostics import async_get_config_entry_diagnostics as moduletwo
from .voltbridge_diagnostics import async_get_config_entry_diagnostics as voltbridge


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry[Any]
) -> dict[str, Any]:
    """Delegate to the entry's device family."""
    if device_type(entry) == DEVICE_VOLTBRIDGE:
        return await voltbridge(hass, entry)
    return await moduletwo(hass, entry)

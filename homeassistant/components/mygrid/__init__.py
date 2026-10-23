"""MyGrid: ModuleTwo batteries over Modbus TCP and VoltBridge P1 meters."""

from __future__ import annotations

from typing import Any

from homeassistant.components.modbus import async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from mygrid_modbus import UNIT_ID, MyGridDevice

from .const import CONF_DEVICE, DEVICE_MODULETWO, DEVICE_VOLTBRIDGE, DOMAIN
from .moduletwo_coordinator import ModuleTwoConfigEntry, ModuleTwoCoordinator
from .moduletwo_helpers import create_modbus_params
from .voltbridge_coordinator import VoltBridgeConfigEntry, VoltBridgeCoordinator

MODULETWO_PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
]
VOLTBRIDGE_PLATFORMS = [Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def device_type(entry: ConfigEntry[Any]) -> str:
    """Return the device family of an entry; entries without one are ModuleTwo."""
    return str(entry.data.get(CONF_DEVICE, DEVICE_MODULETWO))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Set up one device after validating a real snapshot."""
    if device_type(entry) == DEVICE_VOLTBRIDGE:
        return await _async_setup_voltbridge(hass, entry)
    return await _async_setup_moduletwo(hass, entry)


async def _async_setup_moduletwo(
    hass: HomeAssistant, entry: ModuleTwoConfigEntry
) -> bool:
    try:
        unit = async_get_unit(hass, entry, create_modbus_params(entry.data), UNIT_ID)
    except HomeAssistantError as err:
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="link_settings_in_use"
        ) from err
    device = MyGridDevice(unit)
    coordinator = entry.runtime_data = ModuleTwoCoordinator(hass, entry, device)
    await coordinator.async_config_entry_first_refresh()
    # The Modbus manager releases its hold on unload, including setup failure.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, MODULETWO_PLATFORMS)
    return True


async def _async_setup_voltbridge(
    hass: HomeAssistant, entry: VoltBridgeConfigEntry
) -> bool:
    coordinator = entry.runtime_data = VoltBridgeCoordinator(hass, entry)
    await coordinator.async_start()
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, VOLTBRIDGE_PLATFORMS)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> None:
    """Apply polling options through a clean reload."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry[Any]) -> bool:
    """Unload entities; transports are released by their owners on unload."""
    platforms = (
        VOLTBRIDGE_PLATFORMS
        if device_type(entry) == DEVICE_VOLTBRIDGE
        else MODULETWO_PLATFORMS
    )
    return await hass.config_entries.async_unload_platforms(entry, platforms)

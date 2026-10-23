"""Replayable raw-register diagnostics with graceful offline handling."""

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from modbus_connection import ModbusError

from .coordinator import MyGridConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MyGridConfigEntry
) -> dict[str, Any]:
    """Allowlist device fields and raw words; omit addresses and entry identities."""
    if entry.state is not ConfigEntryState.LOADED:
        return {
            "options": dict(entry.options),
            "last_update_success": False,
            "registers": None,
            "registers_error": "NotLoaded",
        }
    coordinator = entry.runtime_data
    payload: dict[str, Any] = {
        "options": dict(entry.options),
        "last_update_success": coordinator.last_update_success,
        "updated": sorted(coordinator.data.updated),
        "failed": {
            name: type(error).__name__
            for name, error in coordinator.data.failed.items()
        },
        "data": asdict(coordinator.device.snapshot),
        "active_faults": coordinator.device.snapshot.active_faults,
    }
    try:
        payload["registers"] = await coordinator.device.async_read_raw()
    except (ModbusError, OSError, TimeoutError) as err:
        # Exception text can include a host or link details; export the type only.
        payload["registers"] = None
        payload["registers_error"] = type(err).__name__
    return payload

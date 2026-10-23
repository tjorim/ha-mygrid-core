"""Run real Home Assistant platforms, lifecycle, services and diagnostics."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.components.modbus.connection import async_get_connection_info
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from modbus_connection.model import UpdateReport
from mygrid_modbus import (
    FAULTS,
    InvalidSetpointError,
    MyGridError,
    UnsupportedMapError,
)

from homeassistant.components.mygrid.const import DOMAIN
from homeassistant.components.mygrid.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.common import async_fire_time_changed


def publish(coordinator, snapshot):
    coordinator.device.snapshot = snapshot
    coordinator.async_set_updated_data(UpdateReport(updated={"battery"}))


def entity_id(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(
        platform, DOMAIN, f"{entry.entry_id}_{key}"
    )


def state(hass, entry, key, platform="sensor"):
    return hass.states.get(entity_id(hass, entry, platform, key))


async def setup(hass, entry):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def enable(hass, entry, platform, key):
    er.async_get(hass).async_get_or_create(
        platform,
        DOMAIN,
        f"{entry.entry_id}_{key}",
        config_entry=entry,
        disabled_by=None,
    )


async def test_entities(hass, entry, mock_client, device_registry):
    await setup(hass, entry)
    for key, expected in {
        "state_of_charge": "82",
        "power": "-800",
        "charging_power": "0",
        "discharging_power": "800",
        "max_charge": "1200",
        "max_discharge": "1000",
        "status": "normal",
        "stored_energy": "3000",
        "lifetime_charged": "131079",
        "lifetime_discharged": "196617",
        "total_capacity": "5000",
    }.items():
        assert state(hass, entry, key).state == expected
    assert state(hass, entry, "problem", "binary_sensor").state == "off"
    number = state(hass, entry, "power_setpoint", "number")
    assert number.state == "-800"
    assert number.attributes["min"] == -1000
    assert number.attributes["max"] == 1200
    assert number.attributes["step"] == 100
    assert (
        state(hass, entry, "lifetime_charged").attributes["state_class"]
        == "total_increasing"
    )
    assert (
        state(hass, entry, "stored_energy").attributes["state_class"] == "measurement"
    )
    assert len(device_registry.devices) == 1
    assert not state(hass, entry, "fault_flags")
    assert not state(hass, entry, "restart", "button")
    mock_client.async_update.assert_awaited_once()
    mock_client.async_set_power.assert_not_called()
    mock_client.async_restart.assert_not_called()


async def test_stale_and_recovery(hass, entry, mock_client):
    await setup(hass, entry)
    coordinator = entry.runtime_data
    original = coordinator.device.snapshot
    publish(
        coordinator,
        replace(original, status=2, state_of_charge=None, power=None, fault_flags=None),
    )
    await hass.async_block_till_done()
    for key in ["state_of_charge", "power", "charging_power", "discharging_power"]:
        assert state(hass, entry, key).state == STATE_UNKNOWN
    assert state(hass, entry, "problem", "binary_sensor").state == STATE_UNKNOWN
    assert state(hass, entry, "status").state == "telemetry_stale"
    assert state(hass, entry, "stored_energy").state == "3000"
    publish(coordinator, original)
    await hass.async_block_till_done()
    assert state(hass, entry, "state_of_charge").state == "82"


@pytest.mark.parametrize("bit", list(FAULTS))
async def test_optional_faults(hass, entry, mock_client, bit):
    entry.add_to_hass(hass)
    enable(hass, entry, "sensor", "fault_flags")
    enable(hass, entry, "sensor", "map_version")
    for name in FAULTS.values():
        enable(hass, entry, "binary_sensor", f"fault_{name}")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    publish(coordinator, replace(coordinator.device.snapshot, fault_flags=1 << bit))
    await hass.async_block_till_done()
    assert state(hass, entry, "fault_flags").state == str(1 << bit)
    assert state(hass, entry, "fault_flags").attributes["active_faults"] == [
        FAULTS[bit]
    ]
    assert state(hass, entry, "map_version").state == "2"
    assert state(hass, entry, "problem", "binary_sensor").state == "on"
    for other, name in FAULTS.items():
        assert state(hass, entry, f"fault_{name}", "binary_sensor").state == (
            "on" if other == bit else "off"
        )
    publish(
        coordinator, replace(coordinator.device.snapshot, status=2, fault_flags=None)
    )
    await hass.async_block_till_done()
    assert (
        state(hass, entry, f"fault_{FAULTS[bit]}", "binary_sensor").state
        == STATE_UNKNOWN
    )
    assert state(hass, entry, "fault_flags").attributes["active_faults"] is None


@pytest.mark.parametrize(("status", "flags"), [(1, 0), (0, 1 << 10)])
async def test_aggregate_fault(hass, entry, mock_client, status, flags):
    await setup(hass, entry)
    coordinator = entry.runtime_data
    publish(
        coordinator,
        replace(coordinator.device.snapshot, status=status, fault_flags=flags),
    )
    await hass.async_block_till_done()
    assert state(hass, entry, "problem", "binary_sensor").state == "on"


async def test_command(hass, entry, mock_client):
    await setup(hass, entry)
    mock_client.async_set_power.return_value = replace(
        entry.runtime_data.device.snapshot, setpoint=500, power=500
    )
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id(hass, entry, "number", "power_setpoint"), "value": 600},
        blocking=True,
    )
    await hass.async_block_till_done()
    mock_client.async_set_power.assert_awaited_once_with(600)
    assert state(hass, entry, "power_setpoint", "number").state == "500"
    assert state(hass, entry, "charging_power").state == "500"
    assert state(hass, entry, "discharging_power").state == "0"


async def test_command_validation(hass, entry, mock_client):
    await setup(hass, entry)
    mock_client.async_set_power.side_effect = InvalidSetpointError()
    with pytest.raises(ServiceValidationError):
        await entry.runtime_data.async_set_power(600)
    assert entry.runtime_data.last_update_success


async def test_command_failed(hass, entry, mock_client):
    await setup(hass, entry)
    mock_client.async_set_power.side_effect = MyGridError()
    with pytest.raises(HomeAssistantError) as raised:
        await entry.runtime_data.async_set_power(600)
    assert raised.value.translation_key == "command_failed"
    await hass.async_block_till_done()
    assert not entry.runtime_data.last_update_success
    assert state(hass, entry, "state_of_charge").state == STATE_UNAVAILABLE
    await entry.runtime_data.async_refresh()
    mock_client.async_set_power.assert_awaited_once()


@pytest.mark.parametrize("error", [None, MyGridError()])
async def test_restart(hass, entry, mock_client, error):
    entry.add_to_hass(hass)
    enable(hass, entry, "button", "restart")
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    mock_client.async_restart.side_effect = error
    if error:
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "button",
                "press",
                {"entity_id": entity_id(hass, entry, "button", "restart")},
                blocking=True,
            )
    else:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": entity_id(hass, entry, "button", "restart")},
            blocking=True,
        )
        assert len(async_get_connection_info(hass)) == 1
    await hass.async_block_till_done()
    assert not entry.runtime_data.last_update_success
    assert state(hass, entry, "power").state == STATE_UNAVAILABLE
    await entry.runtime_data.async_refresh()
    mock_client.async_restart.assert_awaited_once()
    assert entry.runtime_data.last_update_success


async def test_dynamic_bounds(hass, entry, mock_client):
    await setup(hass, entry)
    coordinator = entry.runtime_data
    publish(
        coordinator,
        replace(coordinator.device.snapshot, max_charge=6553500, max_discharge=6553500),
    )
    await hass.async_block_till_done()
    attributes = state(hass, entry, "power_setpoint", "number").attributes
    assert attributes["min"] == -3276800
    assert attributes["max"] == 3276700


async def test_failure_recovery_logging(hass, entry, mock_client, caplog):
    await setup(hass, entry)
    coordinator = entry.runtime_data
    mock_client.async_update.side_effect = MyGridError()
    caplog.clear()
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, entry, "state_of_charge").state == STATE_UNAVAILABLE
    assert sum("Error fetching mygrid" in r.message for r in caplog.records) == 1
    mock_client.async_update.side_effect = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, entry, "state_of_charge").state == "82"
    assert "recovered" in caplog.text
    mock_client.async_set_power.assert_not_called()


async def test_polling_and_unload(hass, entry, mock_client, freezer):
    await setup(hass, entry)
    freezer.tick(timedelta(seconds=6))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert mock_client.async_update.await_count == 2
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert async_get_connection_info(hass) == []
    freezer.tick(timedelta(seconds=10))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert mock_client.async_update.await_count == 2
    mock_client.async_set_power.assert_not_called()
    mock_client.async_restart.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (MyGridError(), ConfigEntryState.SETUP_RETRY),
        (UnsupportedMapError(), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_failure(hass, entry, mock_client, error, expected):
    entry.add_to_hass(hass)
    if isinstance(error, UnsupportedMapError):
        mock_client.async_update.return_value = UpdateReport(failed={"battery": error})
    else:
        mock_client.async_update.side_effect = error
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == expected
    assert async_get_connection_info(hass) == []


async def test_diagnostics(hass, entry, mock_client):
    await setup(hass, entry)
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["data"]["state_of_charge"] == 82
    assert diagnostics["last_update_success"]
    assert diagnostics["active_faults"] == []
    text = str(diagnostics)
    for secret in [entry.entry_id, entry.unique_id, "battery.local", entry.title]:
        assert secret not in text
    mock_client.async_update.assert_awaited_once()


async def test_failed_unload_keeps_connection(hass, entry, mock_client):
    await setup(hass, entry)
    with patch.object(
        hass.config_entries, "async_unload_platforms", return_value=False
    ):
        assert not await hass.config_entries.async_unload(entry.entry_id)
    assert len(async_get_connection_info(hass)) == 1


async def test_setup_link_conflict(hass, entry, mock_client):
    entry.add_to_hass(hass)
    with patch(
        "homeassistant.components.mygrid.moduletwo_setup.async_get_unit",
        side_effect=HomeAssistantError("different link settings"),
    ):
        assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.SETUP_ERROR
    mock_client.async_read.assert_not_called()
    assert async_get_connection_info(hass) == []

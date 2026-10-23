"""Counter continuity, restore behavior, and raw diagnostics failure handling."""

from unittest.mock import patch

import pytest
from homeassistant.components.sensor import SensorExtraStoredData
from modbus_connection import ModbusTimeoutError
from modbus_connection.model import UpdateReport

from homeassistant.components.mygrid.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.components.mygrid.moduletwo_sensor import ModuleTwoTotalSensor

from .test_moduletwo_integration import setup, state


async def test_counters_hold_during_outage_and_accept_real_reset(
    hass, entry, mock_client
):
    from dataclasses import replace

    from homeassistant.helpers.update_coordinator import UpdateFailed

    await setup(hass, entry)
    entry.runtime_data.async_set_update_error(UpdateFailed("offline"))
    await hass.async_block_till_done()
    assert state(hass, entry, "power").state == "unavailable"
    assert state(hass, entry, "lifetime_charged").state == "131079"
    mock_client.snapshot = replace(mock_client.snapshot, lifetime_charged=0)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, entry, "lifetime_charged").state == "0"


@pytest.mark.parametrize("value", [7000, 0, "invalid"])
async def test_restored_counter_when_link_drops_during_entity_setup(
    hass, entry, mock_client, value
):
    async def restore(sensor):
        # A valid first refresh completed, then connectivity is lost while
        # entities restore. Their totals must use the saved native value.
        sensor.coordinator.last_update_success = False
        return SensorExtraStoredData(value, "Wh")

    with patch.object(
        ModuleTwoTotalSensor,
        "async_get_last_sensor_data",
        autospec=True,
        side_effect=restore,
    ):
        await setup(hass, entry)
    expected = str(value) if isinstance(value, int) else "unavailable"
    assert state(hass, entry, "lifetime_charged").state == expected
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, entry, "lifetime_charged").state == "131079"


async def test_empty_or_failed_report_is_not_fresh(hass, entry, mock_client):
    from mygrid_modbus import MyGridError

    await setup(hass, entry)
    mock_client.async_update.return_value = UpdateReport(
        failed={"battery": MyGridError()}
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert state(hass, entry, "power").state == "unavailable"
    assert state(hass, entry, "lifetime_charged").state == "131079"


async def test_raw_diagnostics_and_offline_redaction(hass, entry, mock_client):
    await setup(hass, entry)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["registers"]["holding"][5] == 64736
    assert result["updated"] == ["battery"]
    mock_client.async_read_raw.side_effect = ModbusTimeoutError("battery.local secret")
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["registers"] is None
    assert result["registers_error"] == "ModbusTimeoutError"
    assert "battery.local" not in str(result)
    assert "secret" not in str(result)


async def test_diagnostics_before_successful_setup(hass, entry):
    entry.add_to_hass(hass)
    result = await async_get_config_entry_diagnostics(hass, entry)
    assert result["registers"] is None
    assert result["registers_error"] == "NotLoaded"
    assert result["last_update_success"] is False

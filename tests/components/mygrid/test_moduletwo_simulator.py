"""Real TCP tests exercise Home Assistant's shared Modbus connection manager."""

import pytest
from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.components.modbus.connection import async_get_connection_info
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from modbus_connection import ModbusTcpParams

from tests.components.mygrid.conftest import start_moduletwo
from tests.components.mygrid.moduletwo_simulator import BatterySimulator

pytestmark = [pytest.mark.simulator, pytest.mark.usefixtures("socket_enabled")]


async def test_home_assistant_end_to_end(hass, registers):
    async with BatterySimulator(registers) as battery:
        result = await start_moduletwo(
            hass, {"host": "127.0.0.1", "port": battery.port}
        )
        assert result["type"] == FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
        entry = result["result"]
        assert entry.runtime_data.device.snapshot.state_of_charge == 82
        assert battery.writes == []
        await entry.runtime_data.async_set_power(-500)
        assert entry.runtime_data.device.snapshot.setpoint == -500
        assert battery.writes == [(2, 65531)]
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert async_get_connection_info(hass) == []
        assert battery.maximum_connections == 1
        assert battery.rejects == 0
        assert battery.writes == [(2, 65531)]


async def test_probe_runtime_restart_and_unload_share_peer_connection(hass, registers):
    async with BatterySimulator(registers) as battery:
        params = ModbusTcpParams(host="127.0.0.1", port=battery.port)
        async with async_get_temporary_unit(hass, params, 1) as peer:
            peer.require_timeout(3)
            assert (await peer.read_holding_registers(0, 18))[1] == 82
            result = await start_moduletwo(
                hass, {"host": "127.0.0.1", "port": battery.port}
            )
            assert result["type"] == FlowResultType.CREATE_ENTRY
            await hass.async_block_till_done()
            entry = result["result"]
            await entry.runtime_data.async_set_power(-500)
            await entry.runtime_data.async_restart()
            assert (await peer.read_holding_registers(0, 18))[2] == 65531
            assert battery.total_connections == 1
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            # The remaining consumer can still read on the original socket.
            assert (await peer.read_holding_registers(0, 18))[1] == 82
            assert battery.total_connections == 1
            assert len(async_get_connection_info(hass)) == 1
            assert battery.writes == [(2, 65531), (9, 1)]
        assert async_get_connection_info(hass) == []
        assert battery.rejects == 0


async def test_probe_and_setup_failure_leave_peer_connected(hass, registers, entry):
    registers[0] = 3
    async with BatterySimulator(registers) as battery:
        params = ModbusTcpParams(host="127.0.0.1", port=battery.port)
        async with async_get_temporary_unit(hass, params, 1) as peer:
            peer.require_timeout(3)
            await peer.read_holding_registers(0, 18)
            result = await start_moduletwo(
                hass, {"host": "127.0.0.1", "port": battery.port}
            )
            assert result["errors"] == {"base": "unsupported_map"}
            entry.add_to_hass(hass)
            hass.config_entries.async_update_entry(
                entry, data={"host": "127.0.0.1", "port": battery.port}
            )
            assert not await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()
            assert entry.state == ConfigEntryState.SETUP_ERROR
            assert (await peer.read_holding_registers(0, 18))[1] == 82
            assert battery.total_connections == 1
            assert async_get_connection_info(hass)[0].units == {}
        assert async_get_connection_info(hass) == []
        assert battery.writes == []

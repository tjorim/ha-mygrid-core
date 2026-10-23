"""ModuleTwo fixtures mock the independent device API, not the protocol."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from modbus_connection.model import UpdateReport
from mygrid_modbus import BatteryData, MyGridDevice

from homeassistant.components.mygrid.const import DOMAIN
from tests.common import MockConfigEntry


@pytest.fixture
def registers() -> list[int]:
    return [2, 82, 65528, 12, 10, 64736, 0, 0, 0, 0, 3000, 0, 7, 2, 9, 3, 5000, 0]


@pytest.fixture
def mock_client(registers: list[int]) -> Generator[AsyncMock]:
    device = AsyncMock(spec=MyGridDevice)
    device.snapshot = BatteryData(
        2, 82, -800, 1200, 1000, -800, 0, 0, 3000, 131079, 196617, 5000
    )
    device.async_read.return_value = device.snapshot
    device.async_update.return_value = UpdateReport(updated={"battery"})
    device.async_set_power.return_value = device.snapshot
    device.async_read_raw.return_value = {"holding": dict(enumerate(registers))}

    async def confirm(value):
        device.snapshot = device.async_set_power.return_value
        return device.snapshot

    device.async_set_power.side_effect = confirm
    with (
        patch(
            "homeassistant.components.mygrid.moduletwo_setup.MyGridDevice",
            return_value=device,
        ),
        patch(
            "homeassistant.components.mygrid.moduletwo_config_flow.MyGridDevice",
            return_value=device,
        ),
    ):
        yield device


@pytest.fixture
def entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="MyGrid ModuleTwo",
        unique_id="persistent-identity",
        data={"host": "battery.local", "port": 502},
    )

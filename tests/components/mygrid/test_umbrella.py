"""One integration, two device families: menu, coexistence and legacy entries."""

from collections.abc import Callable

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from mygrid_voltbridge import P1Broadcast

from homeassistant.components.mygrid.const import DOMAIN
from homeassistant.components.mygrid.helpers import device_type
from tests.common import MockConfigEntry

from .flows import start_moduletwo, start_voltbridge
from .voltbridge_support import SERIAL


async def test_user_step_offers_both_devices(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["moduletwo", "voltbridge"]


async def test_entries_without_a_device_type_are_moduletwo(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    assert "device" not in entry.data
    assert device_type(entry) == "moduletwo"


async def test_both_devices_run_side_by_side(
    hass: HomeAssistant,
    mock_client,
    entry: MockConfigEntry,
    vb_client,
    vb_entry: MockConfigEntry,
    vb_listener: Callable[[], Callable[[P1Broadcast], None]],
) -> None:
    entry.add_to_hass(hass)
    vb_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert vb_entry.state is ConfigEntryState.LOADED

    registry = er.async_get(hass)
    platforms = {
        item.platform: set()
        for item in registry.entities.values()
        if item.config_entry_id in (entry.entry_id, vb_entry.entry_id)
    }
    assert set(platforms) == {DOMAIN}
    by_entry = {
        entry.entry_id: {
            item.domain
            for item in registry.entities.values()
            if item.config_entry_id == entry.entry_id
        },
        vb_entry.entry_id: {
            item.domain
            for item in registry.entities.values()
            if item.config_entry_id == vb_entry.entry_id
        },
    }
    assert by_entry[entry.entry_id] == {"sensor", "binary_sensor", "number", "button"}
    assert by_entry[vb_entry.entry_id] == {"sensor", "button"}

    assert await hass.config_entries.async_unload(vb_entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_a_voltbridge_entry_never_blocks_moduletwo_setup(
    hass: HomeAssistant, mock_client, vb_entry: MockConfigEntry, vb_client
) -> None:
    """Duplicate detection must ignore entries of the other family (no port key)."""
    vb_entry.add_to_hass(hass)
    result = await start_moduletwo(hass, {"host": "battery", "port": 502})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["device"] == "moduletwo"


async def test_flows_create_distinct_entries(
    hass: HomeAssistant, mock_client, vb_client, vb_setup_entry: None
) -> None:
    battery = await start_moduletwo(hass, {"host": "battery", "port": 502})
    meter = await start_voltbridge(hass, {"host": "meter"})
    assert battery["result"].unique_id != meter["result"].unique_id
    assert meter["result"].unique_id == SERIAL
    assert meter["data"] == {"device": "voltbridge", "host": "meter"}

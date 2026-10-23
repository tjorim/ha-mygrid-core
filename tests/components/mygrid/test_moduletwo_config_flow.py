"""Exercise UI configuration with Home Assistant's actual flow manager."""

from unittest.mock import patch

import pytest
from homeassistant.components.modbus.connection import async_get_connection_info
from homeassistant.config_entries import SOURCE_RECONFIGURE
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from mygrid_modbus import MyGridError, UnsupportedMapError

from homeassistant.components.mygrid.const import DOMAIN
from homeassistant.components.mygrid.helpers import normalize_host
from tests.common import MockConfigEntry
from tests.components.mygrid.flows import start_moduletwo


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        (" BATTERY.Local. ", "battery.local"),
        ("[2001:0DB8::1]", "2001:db8::1"),
        ("192.168.1.20", "192.168.1.20"),
    ],
)
def test_normalize(host, expected):
    assert normalize_host(host) == expected


@pytest.mark.parametrize(
    "host", ["", "https://battery", "battery local", "battery:502", "[broken"]
)
def test_invalid_host(host):
    import probatio

    with pytest.raises(probatio.Invalid):
        normalize_host(host)


async def test_user(hass, mock_client):
    with patch("homeassistant.components.mygrid.async_setup_entry", return_value=True):
        result = await start_moduletwo(hass)
        assert result["type"] == FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": " BATTERY.Local. ", "port": 502}
        )
        await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "host": "battery.local",
        "port": 502,
        "device": "moduletwo",
    }
    assert result["result"].unique_id
    assert async_get_connection_info(hass) == []
    mock_client.async_set_power.assert_not_called()


@pytest.mark.parametrize(
    ("error", "key"),
    [(MyGridError(), "cannot_connect"), (UnsupportedMapError(), "unsupported_map")],
)
async def test_setup_errors(hass, mock_client, error, key):
    mock_client.async_read.side_effect = error
    result = await start_moduletwo(hass, {"host": "battery", "port": 502})
    assert result["errors"] == {"base": key}
    assert async_get_connection_info(hass) == []


async def test_duplicate(hass, entry, mock_client):
    entry.add_to_hass(hass)
    result = await start_moduletwo(hass, {"host": "BATTERY.LOCAL.", "port": 502})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.async_read.assert_not_called()


async def test_duplicate_during_probe(hass, mock_client):
    async def probe():
        MockConfigEntry(
            domain=DOMAIN, data={"host": "battery", "port": 502}, unique_id="another"
        ).add_to_hass(hass)

    mock_client.async_read.side_effect = probe
    result = await start_moduletwo(hass, {"host": "battery", "port": 502})
    assert result["reason"] == "already_configured"


async def test_options(hass, entry, mock_client):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    with patch.object(
        hass.config_entries, "async_reload", return_value=True
    ) as manager:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"poll_interval": 12}
        )
        await hass.async_block_till_done()
        manager.assert_awaited_once_with(entry.entry_id)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options == {"poll_interval": 12}


async def start_reconfigure(hass, entry):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": entry.entry_id}
    )


async def test_reconfigure(hass, entry, mock_client):
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry_before = list(hass.states.async_entity_ids())
    unique_id = entry.unique_id
    result = await start_reconfigure(hass, entry)
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "new.local", "port": 502}
    )
    await hass.async_block_till_done()
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "new.local"
    assert entry.unique_id == unique_id
    assert list(hass.states.async_entity_ids()) == registry_before
    info = async_get_connection_info(hass)
    assert len(info) == 1
    assert info[0].endpoint == ("tcp", "new.local", 502)


async def test_reconfigure_unchanged(hass, entry, mock_client):
    entry.add_to_hass(hass)
    result = await start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], dict(entry.data)
    )
    assert result["reason"] == "reconfigure_successful"
    mock_client.async_read.assert_not_called()


async def test_reconfigure_duplicate(hass, entry, mock_client):
    entry.add_to_hass(hass)
    MockConfigEntry(
        domain=DOMAIN, data={"host": "other", "port": 502}, unique_id="other"
    ).add_to_hass(hass)
    result = await start_reconfigure(hass, entry)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"host": "other", "port": 502}
    )
    assert result["reason"] == "already_configured"


async def test_reconfigure_cannot_unload(hass, entry, mock_client):
    entry.add_to_hass(hass)
    result = await start_reconfigure(hass, entry)
    with patch.object(hass.config_entries, "async_unload", return_value=False):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "other", "port": 502}
        )
    assert result["errors"] == {"base": "cannot_unload"}
    mock_client.async_read.assert_not_called()


async def test_reconfigure_failed_restores(hass, entry, mock_client):
    entry.add_to_hass(hass)
    result = await start_reconfigure(hass, entry)
    mock_client.async_read.side_effect = MyGridError()
    with (
        patch.object(hass.config_entries, "async_unload", return_value=True),
        patch.object(hass.config_entries, "async_setup", return_value=True) as setup,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "other", "port": 502}
        )
        setup.assert_awaited_once_with(entry.entry_id)
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data["host"] == "battery.local"


async def test_reconfigure_cancellation_restores(hass, entry, mock_client):
    import asyncio

    entry.add_to_hass(hass)
    result = await start_reconfigure(hass, entry)
    mock_client.async_read.side_effect = asyncio.CancelledError()
    with (
        patch.object(hass.config_entries, "async_unload", return_value=True),
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        with pytest.raises(asyncio.CancelledError):
            await hass.config_entries.flow.async_configure(
                result["flow_id"], {"host": "other", "port": 502}
            )
        reload.assert_called_once_with(entry.entry_id)
    assert async_get_connection_info(hass) == []
    assert entry.data["host"] == "battery.local"


async def test_probe_link_conflict(hass, mock_client):
    with patch(
        "homeassistant.components.mygrid.moduletwo_config_flow.async_get_temporary_unit",
        side_effect=HomeAssistantError("different link settings"),
    ):
        result = await start_moduletwo(hass, {"host": "battery", "port": 502})
    assert result["errors"] == {"base": "link_settings_in_use"}
    mock_client.async_read.assert_not_called()

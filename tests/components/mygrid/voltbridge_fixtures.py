"""VoltBridge fixtures mock the independent client library, not HTTP or UDP."""

from collections.abc import Callable, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mygrid_voltbridge import P1Broadcast

from homeassistant.components.mygrid.const import DOMAIN
from tests.common import MockConfigEntry

from .voltbridge_support import SERIAL, make_data, make_telegram


@pytest.fixture
def vb_client() -> Generator[AsyncMock]:
    with (
        patch(
            "homeassistant.components.mygrid.voltbridge_coordinator.VoltBridgeClient"
        ) as coordinator_cls,
        patch(
            "homeassistant.components.mygrid.voltbridge_config_flow.VoltBridgeClient",
            coordinator_cls,
        ),
    ):
        instance = AsyncMock()
        instance.async_get_p1_data.return_value = make_data()
        instance.async_get_telegram.return_value = make_telegram()
        coordinator_cls.return_value = instance
        yield instance


@pytest.fixture
def vb_listener() -> Generator[Callable[[], Callable[[P1Broadcast], None]]]:
    """Patch ``async_listen``; the returned getter yields the registered callback."""
    transport = MagicMock()
    with patch(
        "homeassistant.components.mygrid.voltbridge_coordinator.async_listen",
        new_callable=AsyncMock,
        return_value=transport,
    ) as listen:
        listen.transport = transport
        yield lambda: listen.call_args.args[0]


@pytest.fixture
def vb_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="MyGrid VoltBridge",
        unique_id=SERIAL,
        data={"device": "voltbridge", "host": "192.168.0.45"},
    )


@pytest.fixture
def vb_setup_entry() -> Generator[None]:
    """Skip real setup when a flow creates an entry."""
    with patch("homeassistant.components.mygrid.async_setup_entry", return_value=True):
        yield

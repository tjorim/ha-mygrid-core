"""Sensors for every MyGrid device family."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DEVICE_VOLTBRIDGE
from .helpers import device_type
from .moduletwo_sensor import async_setup_entry as async_setup_moduletwo
from .voltbridge_sensor import async_setup_entry as async_setup_voltbridge

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[Any],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Delegate to the entry's device family."""
    setup = (
        async_setup_voltbridge
        if device_type(entry) == DEVICE_VOLTBRIDGE
        else async_setup_moduletwo
    )
    await setup(hass, entry, async_add_entities)

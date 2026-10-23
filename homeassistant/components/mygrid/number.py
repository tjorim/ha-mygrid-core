"""Power setpoint control (ModuleTwo)."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .moduletwo_coordinator import ModuleTwoConfigEntry
from .moduletwo_number import async_setup_entry as async_setup_moduletwo

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModuleTwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Only ModuleTwo entries forward this platform."""
    await async_setup_moduletwo(hass, entry, async_add_entities)

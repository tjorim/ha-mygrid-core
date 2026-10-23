"""Opt-in battery restart command."""

from homeassistant.components.button import ButtonEntity
from homeassistant.components.button.const import ButtonDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .moduletwo_coordinator import ModuleTwoConfigEntry
from .moduletwo_entity import ModuleTwoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModuleTwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register a restart button, disabled until the user enables it."""
    async_add_entities(
        [ModuleTwoRestart(entry.runtime_data, entry.entry_id, "restart")]
    )


class ModuleTwoRestart(ModuleTwoEntity, ButtonEntity):
    """Write one restart request; a lost acknowledgment is never retried."""

    _attr_translation_key = "restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    async def async_press(self) -> None:
        """Restart the battery explicitly."""
        await self.coordinator.async_restart()

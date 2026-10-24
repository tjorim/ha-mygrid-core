"""Aggregate battery problems and optional per-fault diagnostics."""

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
)
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from mygrid_modbus import FAULTS

from .moduletwo_coordinator import ModuleTwoConfigEntry, ModuleTwoCoordinator
from .moduletwo_entity import ModuleTwoEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModuleTwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create aggregate and opt-in fault entities."""
    async_add_entities(
        [ModuleTwoProblem(entry.runtime_data, entry.entry_id)]
        + [ModuleTwoProblem(entry.runtime_data, entry.entry_id, bit) for bit in FAULTS]
    )


class ModuleTwoProblem(ModuleTwoEntity, BinarySensorEntity):
    """A problem remains unknown while fault telemetry is stale."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: ModuleTwoCoordinator, identity: str, bit: int | None = None
    ) -> None:
        """Initialize the ModuleTwoProblem."""
        key = "problem" if bit is None else f"fault_{FAULTS[bit]}"
        super().__init__(coordinator, identity, key)
        self._bit = bit
        self._attr_translation_key = key
        self._attr_entity_registry_enabled_default = bit is None

    @property
    def is_on(self) -> bool | None:
        """Report either the aggregate fault or a particular documented bit."""
        data = self.coordinator.device.snapshot
        if data.fault_flags is None:
            return None
        if self._bit is None:
            return data.status == 1 or data.fault_flags != 0
        return bool(data.fault_flags & (1 << self._bit))

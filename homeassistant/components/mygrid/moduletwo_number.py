"""Explicit charge/discharge power control."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .moduletwo_coordinator import ModuleTwoConfigEntry
from .moduletwo_entity import ModuleTwoEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModuleTwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a confirmed-state power control; do not restore prior commands."""
    async_add_entities(
        [ModuleTwoPowerSetpoint(entry.runtime_data, entry.entry_id, "power_setpoint")]
    )


class ModuleTwoPowerSetpoint(ModuleTwoEntity, NumberEntity):
    """A 100 W setpoint bounded by live limits and signed register range."""

    _attr_translation_key = "power_setpoint"
    _attr_device_class = NumberDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_native_step = 100
    _attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        """Return the device's accepted value."""
        return self.coordinator.device.snapshot.setpoint

    @property
    def native_min_value(self) -> float:
        """Cap unsigned device limits to the signed register range."""
        return -min(self.coordinator.device.snapshot.max_discharge, 3276800)

    @property
    def native_max_value(self) -> float:
        """Return the current charge limit in watts."""
        return min(self.coordinator.device.snapshot.max_charge, 3276700)

    async def async_set_native_value(self, value: float) -> None:
        """Send a single explicit command and publish readback."""
        await self.coordinator.async_set_power(value)

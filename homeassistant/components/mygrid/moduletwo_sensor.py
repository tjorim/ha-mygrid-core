"""Battery telemetry and Energy dashboard sensors."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from mygrid_modbus import BatteryData

from .moduletwo_coordinator import ModuleTwoConfigEntry, ModuleTwoCoordinator
from .moduletwo_entity import ModuleTwoEntity

STATUS = ("normal", "fault", "telemetry_stale")


@dataclass(frozen=True, kw_only=True)
class ModuleTwoSensorDescription(SensorEntityDescription):
    """Describe how to read a value from the shared snapshot."""

    value_fn: Callable[[BatteryData], int | str | None]


SENSORS = (
    ModuleTwoSensorDescription(
        key="state_of_charge",
        translation_key="state_of_charge",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.state_of_charge,
    ),
    ModuleTwoSensorDescription(
        key="power",
        translation_key="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.power,
    ),
    ModuleTwoSensorDescription(
        key="charging_power",
        translation_key="charging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: None if d.power is None else max(d.power, 0),
    ),
    ModuleTwoSensorDescription(
        key="discharging_power",
        translation_key="discharging_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: None if d.power is None else max(-d.power, 0),
    ),
    ModuleTwoSensorDescription(
        key="max_charge",
        translation_key="max_charge",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.max_charge,
    ),
    ModuleTwoSensorDescription(
        key="max_discharge",
        translation_key="max_discharge",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.max_discharge,
    ),
    ModuleTwoSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=list(STATUS),
        value_fn=lambda d: STATUS[d.status],
    ),
    ModuleTwoSensorDescription(
        key="stored_energy",
        translation_key="stored_energy",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.stored_energy,
    ),
    ModuleTwoSensorDescription(
        key="lifetime_charged",
        translation_key="lifetime_charged",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.lifetime_charged,
    ),
    ModuleTwoSensorDescription(
        key="lifetime_discharged",
        translation_key="lifetime_discharged",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.lifetime_discharged,
    ),
    ModuleTwoSensorDescription(
        key="total_capacity",
        translation_key="total_capacity",
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.total_capacity,
    ),
    ModuleTwoSensorDescription(
        key="map_version",
        translation_key="map_version",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.map_version,
    ),
    ModuleTwoSensorDescription(
        key="fault_flags",
        translation_key="fault_flags",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: d.fault_flags,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ModuleTwoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create all sensors without further network calls."""
    async_add_entities(
        (
            ModuleTwoTotalSensor
            if description.state_class == SensorStateClass.TOTAL_INCREASING
            else ModuleTwoSensor
        )(entry.runtime_data, entry.entry_id, description)
        for description in SENSORS
    )


class ModuleTwoSensor(ModuleTwoEntity, SensorEntity):
    """A sensor backed by a coherent register snapshot."""

    entity_description: ModuleTwoSensorDescription

    def __init__(
        self,
        coordinator: ModuleTwoCoordinator,
        identity: str,
        description: ModuleTwoSensorDescription,
    ) -> None:
        """Initialize the ModuleTwoSensor."""
        super().__init__(coordinator, identity, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | float | str | None:
        """Return unknown for stale measurements, not an invented zero."""
        return self.entity_description.value_fn(self.coordinator.device.snapshot)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Explain diagnostic bits while preserving the full fault word."""
        if self.entity_description.key == "fault_flags":
            return {"active_faults": self.coordinator.device.snapshot.active_faults}
        return None


class ModuleTwoTotalSensor(ModuleTwoSensor, RestoreSensor):
    """Retain cumulative energy during outages and restore it across restarts."""

    _attr_native_value: int | float | None = None

    @property
    def available(self) -> bool:
        """A known cumulative value remains usable while measurements are offline."""
        return self._attr_native_value is not None

    @property
    def native_value(self) -> int | float | None:
        """Return the last confirmed counter, never a synthetic zero."""
        return self._attr_native_value

    async def async_added_to_hass(self) -> None:
        """Restore the last confirmed counter before the first update."""
        await super().async_added_to_hass()
        stored = await self.async_get_last_sensor_data()
        if stored is not None and isinstance(stored.native_value, (int, float)):
            self._attr_native_value = stored.native_value
        self._update_total()

    def _update_total(self) -> None:
        if (
            not self.coordinator.last_update_success
            or "battery" not in self.coordinator.data.updated
        ):
            return
        value = self.entity_description.value_fn(self.coordinator.device.snapshot)
        if isinstance(value, (int, float)):
            # The protocol documents U32 lifetime counters, including real
            # rollover/reset. Preserve such decreases for TOTAL_INCREASING.
            self._attr_native_value = value

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_total()
        super()._handle_coordinator_update()

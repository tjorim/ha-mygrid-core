"""Common device identity and coordinator subscription."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MyGridCoordinator


class MyGridEntity(CoordinatorEntity[MyGridCoordinator]):
    """A named entity whose identity survives address reconfiguration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MyGridCoordinator, identity: str, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{identity}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity)},
            name="MyGrid ModuleTwo",
            manufacturer="MyGrid",
            model="ModuleTwo",
        )

    @property
    def available(self) -> bool:
        """Expose measurements only when their component refreshed successfully."""
        return super().available and "battery" in self.coordinator.data.updated

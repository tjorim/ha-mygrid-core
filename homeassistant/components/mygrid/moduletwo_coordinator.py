"""Single polling coordinator and serialized command publication."""

import logging
from asyncio import Lock
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryError,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from modbus_connection import ModbusError
from modbus_connection.model import UpdateReport
from mygrid_modbus import InvalidSetpointError, MyGridDevice, UnsupportedMapError

from .const import CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL, DOMAIN

LOGGER = logging.getLogger(__name__)
type ModuleTwoConfigEntry = ConfigEntry[ModuleTwoCoordinator]


class ModuleTwoCoordinator(DataUpdateCoordinator[UpdateReport]):
    """Publish coherent snapshots and never replay a power command."""

    def __init__(
        self, hass: HomeAssistant, entry: ModuleTwoConfigEntry, device: MyGridDevice
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
            ),
            always_update=True,
        )
        self.device = device
        self._operation_lock = Lock()

    async def _async_update_data(self) -> UpdateReport:
        async with self._operation_lock:
            try:
                report = await self.device.async_update()
            except (ModbusError, OSError, TimeoutError) as err:
                raise UpdateFailed(
                    translation_domain=DOMAIN, translation_key="communication_error"
                ) from err
            if not report.updated:
                error = next(iter(report.failed.values()), None)
                if isinstance(error, UnsupportedMapError):
                    raise ConfigEntryError(
                        translation_domain=DOMAIN, translation_key="unsupported_map"
                    ) from error
                raise UpdateFailed(
                    translation_domain=DOMAIN, translation_key="communication_error"
                ) from error
            return report

    async def async_set_power(self, watts: float) -> None:
        """Write once and publish the readback under the same operation lock."""
        async with self._operation_lock:
            try:
                await self.device.async_set_power(watts)
            except InvalidSetpointError as err:
                raise ServiceValidationError(
                    translation_domain=DOMAIN, translation_key="invalid_setpoint"
                ) from err
            except (ModbusError, OSError, TimeoutError) as err:
                self.async_set_update_error(UpdateFailed("Command confirmation failed"))
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_failed"
                ) from err
            self.async_set_updated_data(UpdateReport(updated={"battery"}))

    async def async_restart(self) -> None:
        """Request restart and immediately invalidate cached telemetry."""
        async with self._operation_lock:
            try:
                await self.device.async_restart()
            except (ModbusError, OSError, TimeoutError) as err:
                self.async_set_update_error(UpdateFailed("Restart confirmation failed"))
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="command_failed"
                ) from err
            self.async_set_update_error(UpdateFailed("Battery restart requested"))

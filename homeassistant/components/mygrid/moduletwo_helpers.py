"""Build the connection parameters consumed by Home Assistant's Modbus manager."""

from collections.abc import Mapping
from typing import Any

from homeassistant.const import CONF_HOST, CONF_PORT
from modbus_connection import ModbusTcpParams


def create_modbus_params(data: Mapping[str, Any]) -> ModbusTcpParams:
    """Use one canonical endpoint for config-flow and runtime consumers."""
    return ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])

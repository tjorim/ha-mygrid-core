---
title: MyGrid
description: Monitor and control MyGrid ModuleTwo home batteries locally.
ha_category:
  - Energy
ha_iot_class: Local Polling
ha_release: '2026.11'
ha_config_flow: true
ha_codeowners:
  - '@tjorim'
ha_domain: mygrid
ha_integration_type: device
ha_platforms:
  - binary_sensor
  - button
  - diagnostics
  - number
  - sensor
---

The **MyGrid** integration monitors and controls ModuleTwo batteries using local Modbus TCP. It supports register map version 2. No cloud account is used by the integration.

## Prerequisites

Enable **Home Assistant** as the battery's control source in the MyGrid app. Home Assistant must already be available as a configured control-source choice for that battery. Put both devices on the same LAN. For a cluster, connect to the unit in **Auto** mode, which is the leader; do not use a Follow unit.

The battery serves one TCP client. Home Assistant shares its connection internally, but a separate Modbus test program must be disconnected. Choose one power controller because other app controls and integrations share the same setpoint.

{% include integrations/config_flow.md %}

Enter the battery's hostname or IP address and port (default **502**). Unit ID is fixed to **1**. Reconfigure changes the address without changing entity identities. The protocol has no hardware identity; create a new entry when replacing hardware to avoid combining histories.

## Provided entities

The integration provides state of charge, measured power, separate charge/discharge power, live charge/discharge limits, status, stored energy, capacity, lifetime charged/discharged counters, and an aggregate Problem indicator. Raw fault flags, all documented individual faults, map version and Restart are diagnostic entities disabled by default.

The power setpoint is in **W**, with **100 W** steps. Positive charges, negative discharges and zero requests idle. It checks fresh limits and displays the battery's accepted value. Use `number.set_value` in automations. No command is sent on startup, reconnect or removal, and uncertain writes are never retried automatically. The manual defines no disconnection watchdog; stopping Home Assistant does not promise that power returns to zero.

## Energy dashboard

Use **Lifetime charged energy** for energy into battery storage and **Lifetime discharged energy** for energy out. These cumulative counters keep their last confirmed values through communication outages and restore saved native values when entities restart. Stored energy and capacity are snapshots, not cumulative flows. Cluster-wide aggregation of all energy registers is not established by the manual; verify your installation before using whole-house totals.

## Polling and diagnostics

One read retrieves registers 0–17 every **5 seconds**. Configure polling between **2 and 300 seconds**. Explicit power commands also read fresh limits and confirmed state. When telemetry is stale, SOC, measured/derived power and fault information become unknown. Connection failures make live measurements unavailable; polling recovers without reloading the entry or replaying commands.

Downloaded diagnostics contain a fresh raw register dump, a validated snapshot, and poll status. They omit addresses and entry identifiers. Offline diagnostics report the failure type and retain the last snapshot. The dump can reproduce register decoding in the library's tests.

## Troubleshooting

If setup fails, check the LAN, host, port, app control source, leader selection and competing TCP clients. Unsupported map versions require the corresponding firmware documentation. Rejected commands must be multiples of 100 W within current limits. Unexpected power changes usually indicate multiple writers. The protocol uses no TLS or authentication; keep port 502 on the trusted LAN.

Remove the entry through Devices & services to stop polling and release its connection hold. The physical link closes only after its last consumer releases it. Removal does not write a zero setpoint.

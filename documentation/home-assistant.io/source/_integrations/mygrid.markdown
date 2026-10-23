---
title: MyGrid
description: Monitor and control MyGrid ModuleTwo home batteries and VoltBridge P1 meters locally.
ha_category:
  - Energy
ha_iot_class: Local Polling
ha_release: '2026.11'
ha_config_flow: true
ha_codeowners:
  - '@tjorim'
ha_domain: mygrid
ha_dhcp: true
ha_zeroconf: true
ha_integration_type: device
ha_platforms:
  - binary_sensor
  - button
  - diagnostics
  - number
  - sensor
---

The **MyGrid** integration works with two MyGrid devices on your local network. No cloud account is used.

| Device | What it provides | Connection |
| --- | --- | --- |
| [ModuleTwo](#moduletwo-battery) | Battery telemetry and explicit charge/discharge control | Modbus TCP |
| [VoltBridge](#voltbridge-p1-meter) | Grid power, energy, voltage, current, gas and water readings from the digital meter | HTTP and UDP broadcast |

Add each device separately: **Add integration → MyGrid**, then choose the device. A VoltBridge is also discovered automatically.

## ModuleTwo battery

The ModuleTwo is monitored and controlled using local Modbus TCP. The integration supports register map version 2.

### Prerequisites

Enable **Home Assistant** as the battery's control source in the MyGrid app. Home Assistant must already be available as a configured control-source choice for that battery. Put both devices on the same LAN. For a cluster, connect to the unit in **Auto** mode, which is the leader; do not use a Follow unit.

The battery serves one TCP client. Home Assistant shares its connection internally, but a separate Modbus test program must be disconnected. Choose one power controller because other app controls and integrations share the same setpoint.

### Configuration

{% include integrations/config_flow.md %}

Choose **ModuleTwo battery (Modbus TCP)**, then enter the battery's hostname or IP address and port (default **502**). Unit ID is fixed to **1**. Reconfigure changes the address without changing entity identities. The protocol has no hardware identity; create a new entry when replacing hardware to avoid combining histories.

### Provided entities

The integration provides state of charge, measured power, separate charge/discharge power, live charge/discharge limits, status, stored energy, capacity, lifetime charged/discharged counters, and an aggregate Problem indicator. Raw fault flags, all documented individual faults, map version and Restart are diagnostic entities disabled by default.

The power setpoint is in **W**, with **100 W** steps. Positive charges, negative discharges and zero requests idle. It checks fresh limits and displays the battery's accepted value. Use `number.set_value` in automations. No command is sent on startup, reconnect or removal, and uncertain writes are never retried automatically. The manual defines no disconnection watchdog; stopping Home Assistant does not promise that power returns to zero.

### Energy dashboard

Use **Lifetime charged energy** for energy into battery storage and **Lifetime discharged energy** for energy out. These cumulative counters keep their last confirmed values through communication outages and restore saved native values when entities restart. Stored energy and capacity are snapshots, not cumulative flows. Cluster-wide aggregation of all energy registers is not established by the manual; verify your installation before using whole-house totals.

### Polling and diagnostics

One read retrieves registers 0–17 every **5 seconds**. Configure polling between **2 and 300 seconds**. Explicit power commands also read fresh limits and confirmed state. When telemetry is stale, SOC, measured/derived power and fault information become unknown. Connection failures make live measurements unavailable; polling recovers without reloading the entry or replaying commands.

Downloaded diagnostics contain a fresh raw register dump, a validated snapshot, and poll status. They omit addresses and entry identifiers. Offline diagnostics report the failure type and retain the last snapshot. The dump can reproduce register decoding in the library's tests.

### Troubleshooting

If setup fails, check the LAN, host, port, app control source, leader selection and competing TCP clients. Unsupported map versions require the corresponding firmware documentation. Rejected commands must be multiples of 100 W within current limits. Unexpected power changes usually indicate multiple writers. The protocol uses no TLS or authentication; keep port 502 on the trusted LAN.

Remove the entry through Devices & services to stop polling and release its connection hold. The physical link closes only after its last consumer releases it. Removal does not write a zero setpoint.

## VoltBridge P1 meter

The VoltBridge reads the digital electricity (and gas and water) meter through its P1 port. The integration uses the device's local, unauthenticated HTTP API and its UDP broadcast; it does not need an MQTT broker. The API is unofficial and was verified on one single-phase meter with firmware build 15.6.

### Prerequisites

Connect the P1 cable and let the VoltBridge receive at least one telegram before adding it: entities are created from the first snapshot. The VoltBridge is discovered through mDNS (`_mygrid._tcp`) and followed to a new address through DHCP, or you can enter its host name or IP address. Each meter is identified by its P1 serial, so an address change does not create a new device.

### Provided entities

Net, import and export power; energy imported and exported (day and night, suitable for the Energy dashboard); voltage and current per phase; the current quarter-hour average demand, the monthly peak demand and its time (the monthly peak history is an attribute); the tariff; gas and water volumes if those meters are connected to the meter's M-Bus; and a diagnostic breaker state. Per-phase power and the limiter/fuse thresholds are disabled by default, and the thresholds are only created when the meter has real limits.

Export values and phases L2 and L3 are decoded from the device's documented layout but have not been verified against hardware with solar production or a three-phase meter.

### Data updates

Live power, voltage and current arrive by UDP broadcast about once a second. The HTTP snapshot and the raw telegram, which carry gas, water, breaker state and the peak history, are polled every **30 seconds**; configure between **5 and 600 seconds**. If broadcasts do not reach Home Assistant (VLANs, containers without host networking), everything still works at the polling interval.

### Troubleshooting

If the device cannot be added, open `http://<address>/` in a browser from the Home Assistant host. A repair issue appears while the VoltBridge is reachable but receives no P1 data; check the P1 cable and that the meter's P1 port is enabled. Reload the entry after connecting a gas or water meter or adding a phase. The device has no authentication; keep it on the trusted LAN.

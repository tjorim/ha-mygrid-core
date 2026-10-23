# MyGrid core contribution overlay

This repository contains the MyGrid integration and tests arranged for a Home Assistant core contribution. **One integration (`mygrid`) covers both MyGrid devices**, the way HomeWizard covers its device family: a ModuleTwo battery (Modbus TCP) and a VoltBridge P1 meter (HTTP and UDP push). Each config entry is one device; the user chooses the device in the first config-flow step, and a VoltBridge is also found by mDNS and followed by DHCP. It follows the [Modernizing Modbus recommendations](https://contributors.home-assistant.io/blog/2026/07/05/modernizing-modbus/) and the [Modbus integration guide](https://developers.home-assistant.io/docs/modbus/introduction).

It is an **overlay**, not a full Home Assistant fork or an accepted upstream integration. Local validation targets Home Assistant 2026.10.2. The complete upstream checks must also run in the target core checkout before submission.

## Four deliverables

| Folder / repository | Purpose |
| --- | --- |
| `mygrid-modbus` | Independent PyPI device library for the ModuleTwo using `Device`, `Component`, typed fields and the supplied mock backend |
| `mygrid-voltbridge` | Independent PyPI client library for the VoltBridge: HTTP API, raw DSMR telegram, UDP broadcast decoder |
| `ha-mygrid-core` | This canonical integration, its core-layout tests and draft user documentation |
| `ha-mygrid` | Generated HACS version with vendored copies of both libraries; community testing does not require PyPI publication |

The canonical runtime files are under `homeassistant/components/mygrid`. Tests belong under `tests/components/mygrid` and import `tests.common`, as core tests do. `conftest.py` at the repository root is a local overlay bootstrap; **do not copy it into core**. It uses the installed test harness and extends the component lookup path, without modifying installed Home Assistant files.

## Local checks

Place this repository beside `mygrid-modbus` and `mygrid-voltbridge`, then:

```sh
uv sync --frozen
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run python scripts/validate_metadata.py
```

The library is installed as a package, not imported through a source-path shortcut. Its own tests run independently. Only the development uv source overrides reference the sibling checkouts; the production manifest requires `mygrid-modbus==0.1.0` and `mygrid-voltbridge==0.3.0` from PyPI.

## Preparing the core change

1. Publish the reviewed device-library versions to PyPI and verify a clean installation.
2. Run `uv run python scripts/apply_to_core.py /path/to/core --dry-run`, review the paths, then run without `--dry-run` to copy the new domain and its tests into a clean target core checkout. Existing domain directories are never overwritten.
3. In that checkout, run its required tooling, including `python -m script.hassfest --integration-path homeassistant/components/mygrid`, Ruff, strict typing and `pytest tests/components/mygrid`. Adapt to the target branch's current APIs if they differ from the tested minimum.
4. Submit the draft `documentation/home-assistant.io/source/_integrations/mygrid.markdown` to the documentation repository, updating the proposed release version to the actual merge target.
5. Resolve the tracked maintainer/brand requirements, record physical-battery acceptance results, and request the normal upstream review. No official quality tier is asserted in the manifest.

The source repositories are published under [tjorim on GitHub](https://github.com/tjorim). No upstream PR or PyPI release has been created. Manufacturer-approved branding and physical-device validation remain pending. The protocol provides no hardware identity, so entry identities survive address reconfiguration but replacement hardware must be configured as a new entry.

## Layout

Flat modules, because the HACS generator adapts a single directory level: `moduletwo_*.py` and `voltbridge_*.py` hold each device family's coordinator, entity base and platforms; `sensor.py`, `binary_sensor.py`, `number.py`, `button.py` and `diagnostics.py` are thin dispatchers (Home Assistant loads platforms by those names); `__init__.py` and `config_flow.py` route by the entry's `device` field. Entries created before the field existed are ModuleTwo entries. Home Assistant allows one `iot_class` per manifest; `local_polling` is declared because the battery is polled and the VoltBridge's snapshot is polled alongside its UDP push.

## Architecture

Home Assistant's `modbus` integration owns the shared link. The config flow borrows a temporary unit; entry setup holds a managed unit. The library states its timing requirements and produces `UpdateReport`s. The coordinator runs its first refresh before forwarding platforms. Failed component reports make live readings unavailable; cumulative counters preserve confirmed values and use `RestoreSensor` across restarts. Diagnostics retrieve replayable raw words and serialize error types without exposing connection details.

The VoltBridge coordinator has no update interval: UDP telegrams (about 1 Hz) are merged into a polled HTTP snapshot and telegram, so a busy push stream cannot starve the poll. The VoltBridge entities are read-only. No setup, reconnect, polling, unload or restore operation writes power. Commands remain explicit, fresh-limit checked and confirmed by readback. The library and both supported backends never replay uncertain writes. All tests involving actual sockets use a local simulator. See the HACS repository's hardware checklist for device acceptance.

## Keeping HACS synchronized

Edit device code in `mygrid-modbus` or `mygrid-voltbridge`, integration code/tests here, then run from `ha-mygrid`:

```sh
uv run python scripts/sync_sources.py
uv run python scripts/sync_sources.py --check
uv run python scripts/validate_metadata.py
```

The generator adapts namespaces and the custom manifest, copies both libraries byte for byte, and records source commits and SHA-256 hashes. Do not maintain a hand-edited protocol fork in the custom integration.

The standalone `ha-mygrid-voltbridge` custom integration (domain `mygrid_voltbridge`) was the prototype of the VoltBridge half; it is superseded by this umbrella.

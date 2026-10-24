"""Generate the single-device HACS packages from this umbrella integration.

HACS allows one integration (one domain) per repository, so each MyGrid device
gets its own repository with its own domain. Both are generated from the code
and tests here plus the device's standalone library, which is vendored byte for
byte. Run from this repository::

    uv run python scripts/sync_hacs.py            # write both packages
    uv run python scripts/sync_hacs.py --check    # fail if either has drifted
"""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "homeassistant/components/mygrid"
TESTS = ROOT / "tests/components/mygrid"
TEMPLATES = ROOT / "scripts/hacs_templates"
# Format from an empty directory so that neither this repository's ruff config nor
# its top-level `homeassistant` package changes how imports are grouped.
NEUTRAL = Path(tempfile.mkdtemp(prefix="sync-hacs-"))

# Config-flow and translation keys that belong to one device only. Everything
# else (including shared aborts) is kept in both packages.
VOLTBRIDGE_ONLY = {
    "config.step": {"voltbridge", "discovery_confirm", "reconfigure_voltbridge"},
    "config.error": {"voltbridge_cannot_connect", "voltbridge_no_data"},
    "config.abort": {
        "not_voltbridge",
        "wrong_device",
        "voltbridge_cannot_connect",
        "voltbridge_no_data",
    },
    "options.step": {"voltbridge_init"},
}
MODULETWO_ONLY = {
    "config.step": {"moduletwo", "reconfigure_moduletwo"},
    "config.error": {
        "cannot_connect",
        "unsupported_map",
        "cannot_unload",
        "link_settings_in_use",
    },
    "options.step": {"init"},
}


@dataclass(frozen=True)
class Profile:
    """Everything that differs between the two packages."""

    device: str
    domain: str
    name: str
    repo: str
    library: str
    package: str
    library_dir: str
    manifest: dict[str, object] = field(default_factory=dict)


PROFILES = {
    "moduletwo": Profile(
        device="moduletwo",
        domain="mygrid_modbus",
        name="MyGrid ModuleTwo",
        repo="ha-mygrid-modbus",
        library="mygrid-modbus",
        package="mygrid_modbus",
        library_dir="python-mygrid-modbus",
        manifest={
            "categories": ["energy.solar_batteries"],
            "dependencies": ["modbus"],
            "iot_class": "local_polling",
            "loggers": ["modbus_connection", "tmodbus"],
        },
    ),
    "voltbridge": Profile(
        device="voltbridge",
        domain="mygrid_voltbridge",
        name="MyGrid VoltBridge",
        repo="ha-mygrid-voltbridge",
        library="mygrid-voltbridge",
        package="mygrid_voltbridge",
        library_dir="python-mygrid-voltbridge",
        manifest={
            "categories": ["energy.meters_monitoring"],
            "iot_class": "local_push",
            "loggers": ["mygrid_voltbridge"],
            "dhcp": [{"registered_devices": True}],
            "zeroconf": [
                {
                    "type": "_mygrid._tcp.local.",
                    "properties": {"model": "voltbridge*"},
                }
            ],
        },
    ),
}
OTHER = {"moduletwo": "voltbridge", "voltbridge": "moduletwo"}


def revision(path: Path) -> str:
    """Record provenance without requiring a remote repository."""
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def format_python(content: str, path: Path) -> str:
    """Normalize import groups after namespace adaptation, using project tools."""
    result = subprocess.run(
        [
            "ruff",
            "check",
            "--isolated",
            "--select",
            "I",
            "--fix",
            # Classify imports the same way no matter which files already exist.
            "--config",
            "lint.isort.known-first-party = ['custom_components', 'tests']",
            "--stdin-filename",
            str(path),
            "-",
        ],
        input=content,
        text=True,
        capture_output=True,
        check=True,
        cwd=NEUTRAL,
    )
    return subprocess.run(
        ["ruff", "format", "--isolated", "--stdin-filename", str(path), "-"],
        input=result.stdout,
        text=True,
        capture_output=True,
        check=True,
        cwd=NEUTRAL,
    ).stdout


def pinned_version(profile: Profile) -> str:
    """Read the library version this integration pins in its core manifest."""
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    for requirement in manifest["requirements"]:
        match = re.fullmatch(r"([a-z-]+)==([0-9][^\s]*)", requirement)
        if match and match.group(1) == profile.library:
            return match.group(2)
    message = f"Core manifest does not pin {profile.library}"
    raise SystemExit(message)


def voltbridge_entity_keys() -> set[str]:
    """Return the translation keys of the VoltBridge entities.

    Descriptions either spell the key out (``translation_key="gas"``) or pass it
    as the first argument of a helper (``_power("net_power", ...)``).
    """
    patterns = (
        r'translation_key="([a-z0-9_]+)"',
        r'\b_(?:power|energy)\(\s*"([a-z0-9_]+)"',
        r'\bkey="([a-z0-9_]+)"',
    )
    keys: set[str] = set()
    for path in COMPONENT.glob("voltbridge_*.py"):
        for pattern in patterns:
            keys.update(re.findall(pattern, path.read_text()))
    return keys


def filter_strings(strings: dict, profile: Profile) -> dict:
    """Keep only the translations of one device; the device menu goes too."""
    other_only = VOLTBRIDGE_ONLY if profile.device == "moduletwo" else MODULETWO_ONLY
    result = json.loads(json.dumps(strings))
    result["title"] = profile.name
    result["config"]["step"].pop("user", None)
    for section, drop in other_only.items():
        top, sub = section.split(".")
        for key in drop:
            result[top][sub].pop(key, None)
    exceptions = result["exceptions"]
    for key in list(exceptions):
        if key.startswith("voltbridge_") != (profile.device == "voltbridge"):
            del exceptions[key]
    if profile.device == "moduletwo":
        result.pop("issues", None)
    voltbridge = voltbridge_entity_keys()
    for platform in list(result["entity"]):
        items = result["entity"][platform]
        for key in list(items):
            if (key in voltbridge) != (profile.device == "voltbridge"):
                del items[key]
        if not items:
            del result["entity"][platform]
    if not result["config"]["step"].get("reconfigure_" + profile.device):
        message = "Missing reconfigure strings"
        raise SystemExit(message)
    return result


def filter_icons(icons: dict, profile: Profile) -> dict:
    """Keep only the icons of one device's entities."""
    voltbridge = voltbridge_entity_keys()
    result = json.loads(json.dumps(icons))
    for platform in list(result["entity"]):
        items = result["entity"][platform]
        for key in list(items):
            if (key in voltbridge) != (profile.device == "voltbridge"):
                del items[key]
        if not items:
            del result["entity"][platform]
    return result


def adapt_python(content: str, profile: Profile, *, vendored_prefix: str) -> str:
    """Point the device's library import at the vendored copy and fix the domain."""
    content = content.replace(
        f"from {profile.package} import",
        f"from {vendored_prefix}.{profile.package} import",
    )
    return content.replace('DOMAIN = "mygrid"', f'DOMAIN = "{profile.domain}"')


def component_files(profile: Profile, target: Path, library: Path) -> dict[Path, bytes]:
    """Return the generated integration: shared code, one device's modules, glue, vendor."""
    files: dict[Path, bytes] = {}
    base = Path("custom_components") / profile.domain
    other = OTHER[profile.device]
    glue = {"__init__.py", "config_flow.py", "sensor.py", "diagnostics.py"}
    moduletwo_platforms = {"binary_sensor.py", "number.py", "button.py"}
    existing = target / base / "manifest.json"
    # The integration version is owned by the HACS repository, not generated.
    version = (
        json.loads(existing.read_text())["version"] if existing.exists() else "0.1.0"
    )
    for path in sorted(COMPONENT.iterdir()):
        name = path.name
        if (
            name.startswith(f"{other}_")
            or name in glue
            or name in {"manifest.json", "strings.json", "icons.json"}
            or (profile.device == "voltbridge" and name in moduletwo_platforms)
            or path.suffix not in (".py", ".json", ".yaml")
        ):
            continue
        content = path.read_text()
        if path.suffix == ".py":
            content = adapt_python(content, profile, vendored_prefix=".vendor")
            files[base / name] = format_python(content, base / name).encode()
        else:
            files[base / name] = content.encode()
    for name in sorted(glue):
        content = (TEMPLATES / profile.device / name).read_text()
        content = adapt_python(content, profile, vendored_prefix=".vendor")
        files[base / name] = format_python(content, base / name).encode()
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    for key in (
        "categories",
        "dhcp",
        "zeroconf",
        "dependencies",
        "iot_class",
        "loggers",
    ):
        manifest.pop(key, None)
    manifest.update(profile.manifest)
    manifest.update(
        domain=profile.domain,
        name=profile.name,
        version=version,
        documentation=f"https://github.com/tjorim/{profile.repo}/blob/main/README.md",
        issue_tracker=f"https://github.com/tjorim/{profile.repo}/issues",
        requirements=[],
    )
    keys = ["domain", "name", *sorted(set(manifest) - {"domain", "name"})]
    files[base / "manifest.json"] = (
        json.dumps({key: manifest[key] for key in keys}, indent=2) + "\n"
    ).encode()
    strings = filter_strings(
        json.loads((COMPONENT / "strings.json").read_text()), profile
    )
    encoded = (json.dumps(strings, indent=2, ensure_ascii=False) + "\n").encode()
    files[base / "strings.json"] = encoded
    files[base / "translations/en.json"] = encoded
    icons = filter_icons(json.loads((COMPONENT / "icons.json").read_text()), profile)
    if icons["entity"]:
        files[base / "icons.json"] = (json.dumps(icons, indent=2) + "\n").encode()
    vendor = base / "vendor"
    files[vendor / "__init__.py"] = (
        b'"""Generated dependency; update with scripts/sync_hacs.py in ha-mygrid-core."""\n'
    )
    hashes = {}
    for path in sorted((library / "src" / profile.package).iterdir()):
        if path.suffix == ".py" or path.name == "py.typed":
            data = path.read_bytes()
            files[vendor / profile.package / path.name] = data
            hashes[path.name] = hashlib.sha256(data).hexdigest()
    files[vendor / f"LICENSE.{profile.library}"] = (library / "LICENSE").read_bytes()
    files[vendor / "origin.json"] = (
        json.dumps(
            {
                "library": profile.library,
                "version": pinned_version(profile),
                "library_commit": revision(library),
                "core_commit": revision(ROOT),
                "sha256": hashes,
                "adapter_sha256": {
                    str(path.relative_to(base)): hashlib.sha256(data).hexdigest()
                    for path, data in files.items()
                    if path.parts[:2] == ("custom_components", profile.domain)
                    and "vendor" not in path.parts
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    return files


def flows_helper(profile: Profile) -> str:
    """Return the source of the single-device flow helper used by the tests."""
    return f'''"""Start the config flow the way a user does; this package has no device menu."""

from homeassistant.config_entries import SOURCE_USER

from custom_components.{profile.domain}.const import DOMAIN


async def start_{profile.device}(hass, data=None):
    """Open the config flow and optionally submit its form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={{"source": SOURCE_USER}}
    )
    if data is not None:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    return result
'''


def conftest(profile: Profile) -> str:
    """Return the source of the single-device test conftest."""
    names = {
        "moduletwo": "entry, mock_client, registers",
        "voltbridge": "vb_client, vb_entry, vb_listener, vb_setup_entry",
    }[profile.device]
    return f'''"""Re-export this device's fixtures and enable the custom integration."""

import pytest

from .{profile.device}_fixtures import {names}  # noqa: F401


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Enable the generated custom integration in the test runtime."""
'''


def adapt_test(content: str, profile: Profile) -> str:
    """Move a core-layout test into the custom-component namespace."""
    content = adapt_python(
        content, profile, vendored_prefix=f"custom_components.{profile.domain}.vendor"
    )
    return (
        content.replace(
            "homeassistant.components.mygrid", f"custom_components.{profile.domain}"
        )
        .replace(
            "from tests.common import",
            "from pytest_homeassistant_custom_component.common import",
        )
        .replace("tests.components.mygrid.", "tests.")
        .replace('"mygrid"', f'"{profile.domain}"')
        .replace("Error fetching mygrid", f"Error fetching {profile.domain}")
    )


def test_files(profile: Profile) -> dict[Path, bytes]:
    """The device's tests, adapted to the custom-component namespace."""
    files: dict[Path, bytes] = {}
    other = OTHER[profile.device]
    own = (
        f"test_{profile.device}_",
        f"{profile.device}_",
        "voltbridge_support" if profile.device == "voltbridge" else "\0",
    )
    for path in sorted(TESTS.iterdir()):
        if path.is_dir():
            if path.name == "fixtures" and profile.device == "voltbridge":
                for fixture in sorted(path.iterdir()):
                    files[Path("tests/fixtures") / fixture.name] = fixture.read_bytes()
            elif path.name == "live" and profile.device == "voltbridge":
                for live in sorted(path.glob("*.py")):
                    files[Path("tests/live") / live.name] = format_python(
                        adapt_test(live.read_text(), profile),
                        Path("tests/live") / live.name,
                    ).encode()
            continue
        if path.suffix != ".py" or not path.name.startswith(own):
            continue
        if path.name.startswith(f"{other}_") or path.name.startswith(f"test_{other}_"):
            continue
        files[Path("tests") / path.name] = format_python(
            adapt_test(path.read_text(), profile), Path("tests") / path.name
        ).encode()
    files[Path("tests/__init__.py")] = (TESTS / "__init__.py").read_bytes()
    files[Path("tests/conftest.py")] = format_python(
        conftest(profile), Path("tests/conftest.py")
    ).encode()
    files[Path("tests/flows.py")] = format_python(
        flows_helper(profile), Path("tests/flows.py")
    ).encode()
    return files


def expected(profile: Profile, target: Path, library: Path) -> dict[Path, bytes]:
    """Every generated file of one package, relative to its repository root."""
    return {**component_files(profile, target, library), **test_files(profile)}


def stale_files(profile: Profile, target: Path, files: dict[Path, bytes]) -> list[Path]:
    """Generated-area files in the target that the generator no longer produces."""
    patterns = (
        f"custom_components/{profile.domain}/*.py",
        f"custom_components/{profile.domain}/*.json",
        f"custom_components/{profile.domain}/vendor/*/*",
        f"custom_components/{profile.domain}/vendor/LICENSE.*",
        "tests/*.py",
        "tests/live/*.py",
        "tests/fixtures/*",
    )
    return [
        path
        for pattern in patterns
        for path in target.glob(pattern)
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.relative_to(target) not in files
    ]


def main() -> None:
    """Write both packages, or verify that neither has drifted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    for profile in PROFILES.values():
        parser.add_argument(
            f"--{profile.repo}",
            type=Path,
            default=ROOT.parent / profile.repo,
            dest=profile.device,
        )
        parser.add_argument(
            f"--{profile.library_dir}",
            type=Path,
            default=ROOT.parent / profile.library_dir,
            dest=f"{profile.device}_library",
        )
    parser.add_argument("--only", choices=sorted(PROFILES))
    args = parser.parse_args()
    problems: list[str] = []
    for profile in PROFILES.values():
        if args.only and args.only != profile.device:
            continue
        target: Path = getattr(args, profile.device)
        library: Path = getattr(args, f"{profile.device}_library")
        files = expected(profile, target, library)
        stale = stale_files(profile, target, files)
        different = [
            f"{profile.repo}/{path}"
            for path, data in files.items()
            if not (target / path).exists() or (target / path).read_bytes() != data
        ] + [f"{profile.repo}/{path.relative_to(target)}" for path in stale]
        if args.check:
            problems.extend(different)
            continue
        for path in stale:
            path.unlink()
        for path, data in files.items():
            (target / path).parent.mkdir(parents=True, exist_ok=True)
            (target / path).write_bytes(data)
        print(f"{profile.repo}: wrote {len(files)} files")
    if args.check:
        if problems:
            raise SystemExit("Generated files differ: " + ", ".join(problems))
        print("Both HACS packages match their canonical sources.")


if __name__ == "__main__":
    main()

"""Validate core-layout boundaries and the independent library requirement."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "homeassistant/components/mygrid"


def main() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    assert list(manifest) == [
        "domain",
        "name",
        *sorted(set(manifest) - {"domain", "name"}),
    ]
    assert manifest["domain"] == "mygrid"
    assert manifest["dependencies"] == ["modbus"]
    assert manifest["requirements"] == ["mygrid-modbus==0.1.0"]
    assert "version" not in manifest and "issue_tracker" not in manifest
    assert (
        manifest["documentation"] == "https://www.home-assistant.io/integrations/mygrid"
    )
    assert not (COMPONENT / "vendor").exists()
    for path in COMPONENT.glob("*.py"):
        tree = ast.parse(path.read_text())
        assert "custom_components" not in path.read_text()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith(
                    (
                        "pymodbus",
                        "tmodbus",
                        "modbus_connection.tmodbus",
                        "modbus_connection.pymodbus",
                    )
                ), path
    print(
        "Core metadata, independent library requirement, and namespace boundaries validated."
    )


if __name__ == "__main__":
    main()

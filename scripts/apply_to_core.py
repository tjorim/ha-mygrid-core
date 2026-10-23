"""Copy the reviewed contribution overlay into a separate core checkout."""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    checkout = args.checkout.resolve()
    if (
        not (checkout / "homeassistant/components").is_dir()
        or not (checkout / "tests/common.py").is_file()
    ):
        raise SystemExit("Target must be a Home Assistant core source checkout.")
    paths = [Path("homeassistant/components/mygrid"), Path("tests/components/mygrid")]
    if any((checkout / path).exists() for path in paths):
        raise SystemExit(
            "Target already has MyGrid files; review and merge them manually."
        )
    for path in paths:
        print(f"{ROOT / path} -> {checkout / path}")
    if not args.dry_run:
        for path in paths:
            shutil.copytree(
                ROOT / path,
                checkout / path,
                ignore=shutil.ignore_patterns("__pycache__"),
            )


if __name__ == "__main__":
    main()

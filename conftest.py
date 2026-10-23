"""Run a contribution overlay against an installed Home Assistant test runtime.

Only the domain's component and tests are contributed; this bootstrap is local.
"""

import sys
from pathlib import Path

import pytest_homeassistant_custom_component.common as test_support

import homeassistant.components

homeassistant.components.__path__.insert(
    0, str(Path(__file__).parent / "homeassistant/components")
)
sys.modules.setdefault("tests.common", test_support)

"""Run a contribution overlay against an installed Home Assistant test runtime.

Only the domain's component and tests are contributed; this bootstrap is local.
"""

from pathlib import Path
import sys

import homeassistant.components
import pytest_homeassistant_custom_component.common as test_support

homeassistant.components.__path__.insert(0, str(Path(__file__).parent / "homeassistant/components"))
sys.modules.setdefault("tests.common", test_support)

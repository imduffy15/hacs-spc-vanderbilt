"""Pytest fixtures for the Vanderbilt SPC (EDP) test suite."""

from __future__ import annotations

import sys
from pathlib import Path

pytest_plugins = "pytest_homeassistant_custom_component"

# Make custom_components importable the way Home Assistant loads it.
sys.path.insert(0, str(Path(__file__).parent.parent))

"""The decision core runs without Home Assistant."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))

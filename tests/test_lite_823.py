"""0.82.3: the HC Lite thermostat uses the climate temperature names this Home Assistant knows (native_* from
2026.11, the old ones before), as the room thermostats do since 0.71.4 – no deprecation warning."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
BASE = ROOT / "custom_components" / "hc_thermostat"


def test_the_names_follow_home_assistant():
    from homeassistant.components.climate import ClimateEntity
    lite = importlib.import_module("hc_thermostat.lite")
    native = hasattr(ClimateEntity, "native_current_temperature")
    assert lite.NATIVE_TEMPS is native
    own = vars(lite.LiteClimate)
    if native:
        assert "native_current_temperature" in own and "native_target_temperature" in own
        assert "_attr_native_temperature_unit" in own and "current_temperature" not in own and "_attr_temperature_unit" not in own
    else:
        assert "current_temperature" in own and "target_temperature" in own and "_attr_temperature_unit" in own


def test_both_branches_are_written():
    src = (BASE / "lite.py").read_text("utf-8")
    for k in ("native_current_temperature = property(_room_temp)", "native_target_temperature = property(_target_temp)",
              "current_temperature = property(_room_temp)", "_attr_native_temperature_unit = UnitOfTemperature.CELSIUS"):
        assert k in src, k

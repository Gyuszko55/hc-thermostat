"""0.71.4: no deprecation warnings on Home Assistant 2026.11 – the climate temperatures as native_*, the room devices'
parent by `via_device_id` on every platform – while 2026.10 still works with the old names."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from homeassistant.components import climate as ha_climate  # noqa: E402


def _reload(native: bool):
    import hc_thermostat.climate as c
    had = "native_current_temperature" in vars(ha_climate.ClimateEntity)
    if native and not had:
        ha_climate.ClimateEntity.native_current_temperature = None
    try:
        return importlib.reload(c)
    finally:
        if native and not had:
            del ha_climate.ClimateEntity.native_current_temperature


def test_old_home_assistant_keeps_the_old_names():
    c = _reload(native=hasattr(ha_climate.ClimateEntity, "native_current_temperature"))
    for cls in (c.HcClimate, c.HcRoomClimate):
        if c.NATIVE_TEMPS:
            assert "native_current_temperature" in vars(cls)
        else:
            assert {"current_temperature", "target_temperature", "_attr_temperature_unit"} <= set(vars(cls))


def test_2026_11_gets_only_the_native_names():
    try:
        c = _reload(native=True)
        assert c.NATIVE_TEMPS
        for cls in (c.HcClimate, c.HcRoomClimate):
            names = set(vars(cls))
            assert {"native_current_temperature", "native_target_temperature", "_attr_native_temperature_unit"} <= names
            assert not names & {"current_temperature", "target_temperature", "_attr_temperature_unit"}
        ent = c.HcClimate.__new__(c.HcClimate)
        ent.coordinator = SimpleNamespace(data=SimpleNamespace(indoor=21.4, target=22.5))
        assert ent.native_current_temperature == 21.4 and ent.native_target_temperature == 22.5
    finally:
        _reload(native=False)


def test_room_devices_hang_under_the_host_by_id_everywhere():
    import hc_thermostat.climate as c
    assert c._via("abc", "e1") == {"via_device_id": "abc"}
    assert c._via(None, "e1") == {"via_device": ("hc_thermostat", "e1")}
    for f in ("measure_entities.py", "room_groups.py"):
        src = (BASE / f).read_text()
        assert "via_device=(DOMAIN" not in src and "**via_for(" in src

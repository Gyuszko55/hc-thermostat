"""0.37.0: the floor limit by covering and probe position; the tempering offset by covering."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.floor import FLOOR_LIMITS, floor_limit, temper_offset
from core.matrix import default_timing, floor_system, source_defaults
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


@pytest.mark.parametrize("probe,covering,limit", [
    ("surface", "tiles", 29), ("surface", "laminate", 27), ("surface", "wood", 27), ("surface", "vinyl", 27),
    ("surface", "carpet", 27), ("screed", "tiles", 29), ("screed", "laminate", 33), ("screed", "wood", 33),
    ("screed", "vinyl", 31), ("screed", "carpet", 33), ("above_pipe", "tiles", 36), ("above_pipe", "carpet", 36),
])
def test_table(probe, covering, limit):
    assert FLOOR_LIMITS[probe][covering] == limit
    assert floor_limit(0.0, covering, probe, electric=False) == (limit, "covering")


def test_override_electric_default_and_none():
    assert floor_limit(28.5, "tiles", "screed", False) == (28.5, "manual")
    assert floor_limit(0.0, "", "surface", True) == (27.0, "electric")
    assert floor_limit(0.0, "none", "screed", True) == (27.0, "electric")  # "none" from a form = not given
    assert floor_limit(0.0, "", "surface", False) == (29.0, "water")  # 0 never drops the limit of an old instance
    assert floor_limit(0.0, "laminate", "screed", True) == (27.0, "covering")  # electric: always the surface column
    assert floor_limit(0.0, "tiles", "bogus", False) == (29.0, "covering")


def test_config_properties():
    c = HcConfig(floor_covering="laminate", floor_probe="screed")
    assert c.floor_limit == 33.0 and c.floor_limit_from == "covering"
    c = HcConfig.from_mapping({**source_defaults("floor_single", "electric_heater"), "floor_max": 0.0})
    assert c.floor_limit == 27.0 and c.floor_limit_from == "electric"
    c = HcConfig.from_mapping({**source_defaults("floor_single", "onoff_boiler")})  # a stored-less old water floor
    assert c.floor_limit == 29.0 and c.floor_limit_from == "manual"  # source default kept: no change


def test_offset_by_covering():
    assert temper_offset(0.0, "tiles") == 2.0
    for cover in ("laminate", "wood", "vinyl", "carpet"):
        assert temper_offset(0.0, cover) == 3.0
    assert temper_offset(0.0, "") == 2.0 and temper_offset(0.0, "none") == 2.0
    assert temper_offset(1.5, "carpet") == 1.5
    assert HcConfig(floor_covering="wood").temper_offset == 3.0


def test_supervisor_uses_the_effective_limit():
    cfg = HcConfig.from_mapping({**source_defaults("floor_single", "onoff_boiler"), **default_timing("floor_single"),
                                 **DAY, "floor_max": 0.0, "floor_covering": "laminate", "floor_probe": "screed",
                                 "control": "tpi", "floor_system": True})
    sup = Supervisor(cfg)
    d = sup.step(Inputs(now=T0, indoor=Reading(18.0), outdoor=Reading(5.0), floor=Reading(32.5)))
    assert d.reason == Reason.REGULATING  # 32.5 is fine in the screed under laminate (limit 33)
    d = sup.step(Inputs(now=T0 + timedelta(minutes=1), indoor=Reading(18.0), outdoor=Reading(5.0), floor=Reading(33.0)))
    assert d.reason == Reason.FLOOR_LIMIT and d.details["floor_max"] == 33.0


def test_tempering_target_by_covering():
    cfg = HcConfig.from_mapping({**DAY, "floor_covering": "wood", "control": "tpi", "floor_system": True,
                                 "floor_temper": True})
    sup = Supervisor(cfg)
    d = sup.step(Inputs(now=T0, indoor=Reading(21.2), outdoor=Reading(5.0), floor=Reading(22.0)))
    assert d.reason == Reason.FLOOR_TEMPER and d.details["floor_target"] == 24.0  # 21 + 3 under wood


def test_forms_accept_zero_and_default_to_it():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    pytest.importorskip("homeassistant")
    from custom_components.hc_thermostat.config_flow import _floor_fields, vol  # HA's own voluptuous
    for source in ("onoff_boiler", "electric_heater"):
        fields = _floor_fields("floor_single", source, "tpi", {})
        defaults = {str(k): k.default() for k in fields if hasattr(k, "default") and callable(k.default)}
        assert defaults["floor_max"] == 0.0 and defaults["floor_covering"] == "none" and defaults["floor_probe"] == "surface"
        data = vol.Schema(fields)({"floor_entity": "sensor.floor", "floor_max": 0, "floor_hysteresis": 1.0,
                                   "floor_covering": "laminate", "floor_probe": "screed",
                                   "floor_temper": False, "floor_temper_offset": 0, "floor_temper_night": 0,
                                   "floor_temper_hysteresis": 0.3, "floor_temper_room_margin": 1.0,
                                   "floor_fallback": True})
        assert data["floor_max"] == 0
    # a stored value is kept as the default
    fields = _floor_fields("floor_single", "electric_heater", "tpi", {"floor_max": 26.0, "floor_entity": "sensor.f"})
    assert {str(k): k.default() for k in fields if callable(getattr(k, "default", None))}["floor_max"] == 26.0

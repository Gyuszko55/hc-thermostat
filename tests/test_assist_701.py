"""0.70.1 (the terrace AC heated the terrace to 21 °C through a kitchen door left open): the help for the house waits
for a lasting open door, and the unit's setpoint stays under a limit while helping."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
model = importlib.import_module("core.model")
sup_mod = importlib.import_module("core.supervisor")
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

T0 = datetime(2026, 11, 17, 10, 37, tzinfo=timezone.utc)


def _sup(**kw):
    return sup_mod.Supervisor(model.HcConfig(control="ac", target_home=18.0, target_night=18.0, season_enabled=True, **kw))


def _step(sup, m, assist, room=19.1):
    return sup.step(model.Inputs(now=T0 + timedelta(minutes=m), indoor=model.Reading(room, 0),
                                 outdoor=model.Reading(5.0, 0), outdoor_avg=5.0, unit_temp=18.0, unit_step=1.0,
                                 unit_min=16.0, unit_max=30.0, assist_target=assist))


def test_defaults():
    cfg = model.HcConfig()
    assert cfg.assist_delay_s == 600.0 and cfg.assist_max_setpoint == 22.0


def test_a_quick_walk_through_does_not_raise_the_unit():
    sup = _sup()
    d = _step(sup, 0, 22.5)
    assert d.details["aim"] == 18.0 and not d.details["assist"] and d.details["assist_wait_s"] == 0
    d = _step(sup, 5, 22.5)
    assert d.details["aim"] == 18.0 and d.details["assist_wait_s"] == 300
    d = _step(sup, 6, None)  # the door closed
    assert d.details["aim"] == 18.0 and "assist_wait_s" not in d.details
    d = _step(sup, 7, 22.5)  # opened again: the clock starts over
    assert d.details["assist_wait_s"] == 0


def test_a_lasting_open_door_helps_with_a_capped_setpoint():
    sup = _sup()
    for m in range(0, 120, 1):
        d = _step(sup, m, 22.5, room=19.0)
        if m >= 10:
            assert d.details["aim"] == 22.5 and d.details["assist"]
        assert d.external.target <= 22.0  # never 23 / 25 on the unit as on 11-17
    assert d.external.target == 22.0


def test_zero_keeps_the_earlier_behaviour():
    sup = _sup(assist_delay_s=0.0, assist_max_setpoint=0.0)
    d = None
    for m in range(0, 120):
        d = _step(sup, m, 22.5, room=19.0)
    assert d.details["assist"] and d.external.target > 22.0


def test_form_and_texts():
    from hc_thermostat import config_flow as cf
    assert {"assist_delay_s", "assist_max_setpoint"} <= set(cf.SETTINGS_SECTIONS["regulation"])
    for lang in ("hu", "en"):
        sec = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]["step"]["settings"]["sections"]["regulation"]
        for k in ("assist_delay_s", "assist_max_setpoint"):
            assert sec["data"][k] and len(sec["data_description"][k]) > 60

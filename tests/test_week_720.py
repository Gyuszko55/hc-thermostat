"""0.72.0: a weekly program for the instance and for each own-schedule TRV room – levels (comfort / home / night /
eco) painted on a 7 × 24 h grid on the info panel; presence, a preset and a manual target still win."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
week = importlib.import_module("core.week")
model = importlib.import_module("core.model")
sup_mod = importlib.import_module("core.supervisor")
rm = importlib.import_module("core.room_model")
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

MON = datetime(2026, 11, 16, tzinfo=timezone.utc)  # a Monday
PROG = {"0": [["00:00", "sleep"], ["06:00", "home"], ["08:00", "eco"], ["16:00", "comfort"], ["22:00", "sleep"]],
        "5": [["07:30", "home"], ["23:00", "sleep"]]}


def at(day, h, m=0):
    return MON + timedelta(days=day, hours=h, minutes=m)


def test_parse_levels_and_changes():
    p = week.parse(PROG)
    assert week.level_at(p, at(0, 5)) == "sleep" and week.level_at(p, at(0, 7)) == "home"
    assert week.level_at(p, at(0, 12)) == "eco" and week.level_at(p, at(0, 18)) == "comfort"
    assert week.level_at(p, at(2, 12)) == "sleep"  # a day without changes: the level of the day before carries on
    assert week.level_at(p, at(5, 8)) == "home"
    assert week.next_change(p, at(0, 7)) == at(0, 8)
    assert week.next_change(p, at(1, 3)) == at(5, 7, 30)  # Tuesday night … Saturday morning
    assert week.to_raw(p)["0"][0] == ["06:00", "home"]  # 00:00 sleep repeats the level carried in: dropped


def test_parse_rejects_and_normalises():
    assert week.parse(None) is None and week.parse({}) is None and week.parse({"0": [["x", "home"]]}) is None
    assert week.parse({"0": [["06:07", "hot"]]}) is None  # an unknown level
    p = week.parse({"0": [["06:07", "home"]]})  # rounded to the quarter hour; one level all week
    assert week.level_at(p, at(3, 1)) == "home" and week.next_change(p, at(3, 1)) is None


def _sup(**kw):
    cfg = model.HcConfig(target_home=21.0, target_night=18.5, target_comfort=22.5, target_eco=19.0,
                         optimal_start=False, **kw)
    return sup_mod.Supervisor(cfg)


def _inputs(now, presence=None):
    return model.Inputs(now=now, indoor=model.Reading(20.0, 0), outdoor=model.Reading(5.0, 0), outdoor_avg=5.0,
                        **({"presence": presence} if presence else {}))


def test_instance_target_follows_the_program():
    s = _sup(week_program=PROG)
    assert s._schedule_target(_inputs(at(0, 5))) == 18.5
    assert s._schedule_target(_inputs(at(0, 12))) == 19.0
    assert s._schedule_target(_inputs(at(0, 18))) == 22.5
    assert s.active_preset(at(0, 18)) == "comfort" and s._is_night(at(0, 23))
    assert s._next_boundary(at(0, 12)) == at(0, 16)
    # presence still wins
    assert s._schedule_target(_inputs(at(0, 18), model.Presence.AWAY)) == s.cfg.target_away


def test_without_a_program_the_night_window_as_before():
    s = _sup()
    assert s.week is None
    assert s._schedule_target(_inputs(at(0, 23))) == 18.5 and s._schedule_target(_inputs(at(0, 12))) == 21.0


def test_optimal_start_aims_at_the_level_after_the_night():
    s = _sup(week_program={"0": [["00:00", "sleep"], ["06:00", "comfort"]]})
    assert s._wake_target(week.level_end(s.week, at(0, 5))) == 22.5


def test_own_room_follows_its_program_and_presence_wins():
    spec = rm.parse_room({"name": "Konyha", "trvs": ["climate.k_trv"], "mode": "own", "target_home": 21,
                          "target_night": 18, "target_comfort": 22, "target_eco": 19.5, "week": PROG})
    assert spec.week and spec.as_dict()["week"]["0"][0] == ["06:00", "home"]
    rc = rm.RoomControl()
    t = rc.target(spec, at(0, 18), 21.0, "home", 7.0, 12.0)
    assert t.target == 22 and t.reason == "comfort"
    assert rc.target(spec, at(0, 12), 21.0, "home", 7.0, 12.0).reason == "eco"
    assert rc.target(spec, at(0, 23), 21.0, "home", 7.0, 12.0).reason == "night"
    assert rc.target(spec, at(0, 18), 21.0, "away", 7.0, 12.0).reason == "household_away"
    follow = rm.parse_room({"name": "Háló", "trvs": ["climate.h"], "week": PROG})  # follow: no program of its own
    assert follow.week is None


def test_week_options_for_the_instance_and_a_room():
    from hc_thermostat import info
    house = {"comfort": 22.0, "home": 21.0, "sleep": 19.0, "eco": 18.0, "away": 17.0}
    out = info.week_options({"x": 1}, {}, None, PROG, {"comfort": 23, "bogus": 1}, house)
    assert out["week_program"]["5"] == [["07:30", "home"], ["23:00", "sleep"]] and out["target_comfort"] == 23.0
    assert "week_program" not in info.week_options(out, out, None, None, None, house)  # removed: the night window
    rooms = [{"name": "Konyha", "trvs": ["climate.k_trv"], "offset": 0.5}, {"name": "Háló", "sensors": ["sensor.h"]}]
    out = info.week_options({}, {"rooms": rooms}, "konyha", PROG, None, house)
    k = out["rooms"][0]
    assert k["mode"] == "own" and k["target_home"] == 21.5 and k["target_comfort"] == 22.5 and k["week"]["0"]
    assert rooms[0].get("mode") is None  # the stored list is not changed in place
    assert info.week_options({}, {"rooms": rooms}, "konyha", None, None, house) == {}  # clearing a follow room: no-op
    try:
        info.week_options({}, {"rooms": rooms}, "halo", PROG, None, house)
        raise AssertionError("a room without heads must be refused")
    except ValueError:
        pass


def test_panel_editor_and_command():
    panel = (BASE / "www" / "hc-info-panel.js").read_text()
    for s in ("_wkModal", "_wkButton", "hc_thermostat/week_set", "const WK", "elementFromPoint", "if (this._wk) return;"):
        assert s in panel
    assert "ws_week_set" in (BASE / "wizard.py").read_text()

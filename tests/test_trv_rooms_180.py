"""0.18.0: TRV rooms of a single zone – heads get the house target, optional room demand, TRV advice texts."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
trv = importlib.import_module("core.trv")
rooms = importlib.import_module("core.rooms")
model = importlib.import_module("core.model")
from sim import House, Run  # noqa: E402

T0 = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)


def test_head_gets_the_house_target_and_hand_changes_stay_until_the_target_changes():
    t = trv.TrvTargets()
    p = t.plan("climate.konyha", 22.5, "heat", 20.0)
    assert p.target == 22.5
    t.written("climate.konyha", 22.5, 22.5)
    assert t.plan("climate.konyha", 22.5, "heat", 22.5).reason == "same"
    assert t.plan("climate.konyha", 22.5, "heat", 20.0).reason == "manual"  # turned down on the head
    assert t.plan("climate.konyha", 21.0, "heat", 20.0).target == 21.0  # house target changed: ours again


def test_off_unavailable_and_limits():
    t = trv.TrvTargets()
    assert t.plan("h", 22.0, "off", 20.0).reason == "off"
    assert t.plan("h", 22.0, "unavailable", None).reason == "unavailable"
    assert t.plan("h", 3.0, "heat", 10.0, lo=5.0, hi=30.0).target == 5.0
    assert t.plan("h", 22.1, "heat", 22.0).reason == "same"  # below the minimum change


def test_room_demand_needs_half_an_hour_far_below_with_an_open_head():
    d = trv.RoomDemand()
    assert d.update(T0, {"Háló": (20.0, 22.5, True)}) == []
    assert d.update(T0 + timedelta(minutes=31), {"Háló": (20.0, 22.5, True)}) == ["Háló"]
    assert d.update(T0 + timedelta(minutes=32), {"Háló": (20.0, 22.5, False)}) == []  # head closed
    assert d.update(T0 + timedelta(minutes=70), {"Háló": (21.8, 22.5, True)}) == []  # only 0.7 below


def _run(room_demand, indoor):
    cfg = model.HcConfig(target_home=22.5, target_night=22.5, learning_enabled=False, boost_enabled=False,
                         season_enabled=False)
    r = Run(cfg, House(indoor=indoor, outdoor=5.0, loss_tau_s=72 * 3600, full_power_delta=232))
    r.uptime_s = 1e9
    sup, now = r.sup, r.now
    d = sup.step(model.Inputs(now=now, indoor=model.Reading(indoor, 0), outdoor=model.Reading(5.0, 0),
                              room_demand=room_demand))
    return d


def test_room_demand_lifts_the_demand_only_while_the_main_room_is_not_above_its_target():
    calm = _run((), 22.45)
    asked = _run(("Háló",), 22.45)
    assert asked.demand > calm.demand and asked.details.get("room_demand") == ["Háló"]
    warm = _run(("Háló",), 22.6)  # main above target: the main thermometer decides
    assert not warm.details.get("room_demand")


def test_trv_advice_texts():
    a = rooms.Announcement("Konyha", "down", 0.7, 60)
    assert "nem zár" in rooms.room_text(a, "hu", trv=True)
    assert "lejjebb" in rooms.room_text(a, "hu", trv=False)
    assert "kevés" in rooms.room_text(rooms.Announcement("Háló", "up", -0.8, 60), "hu", trv=True)

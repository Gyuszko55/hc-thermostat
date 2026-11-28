"""0.89.0: the system's recommendation, goals instead of parameters, advice from the last days (core/tuning.py)."""

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "hc_thermostat"))
sys.path.insert(0, str(ROOT / "custom_components"))

from core.tuning import advice_text, advise, effective, expect, goal_changes, profile  # noqa: E402

BOILER = {"role": "standalone", "control": "tpi", "system": "radiator", "heat_source": "gas_boiler", "mode": "active"}


def test_profile_lists_only_what_differs():
    assert profile(BOILER) == []  # the defaults are the recommendation
    recs = {r.key: r for r in profile({**BOILER, "cycle_s": 600.0, "min_off_s": 600.0})}
    assert recs["cycle_s"].recommended == 900.0 and recs["cycle_s"].reason == "timing_longer"
    assert "min_off_s" not in recs  # longer than recommended is a choice (fewer switching)
    assert profile({**BOILER, "min_off_s": 600.0}, both=True)[0].reason == "timing_shorter"
    assert goal_changes("recommended", {**BOILER, "cycle_s": 1800.0}) == {"cycle_s": 900.0}
    floor = {r.key: r for r in profile({**BOILER, "system": "floor_single", "cycle_s": 900.0, "pre_change_s": 1800.0})}
    assert floor["cycle_s"].recommended == 3600.0 and floor["pre_change_s"].recommended == 7200.0


def test_safety_only_ever_stricter():
    recs = {r.key: r for r in profile({**BOILER, "frost_temp": 4.0})}
    assert recs["frost_temp"].recommended == 7.0 and recs["frost_temp"].safety
    assert "frost_temp" not in {r.key for r in profile({**BOILER, "frost_temp": 9.0})}  # stricter already: left
    mat = {**BOILER, "system": "floor_single", "heat_source": "electric_heater"}
    recs = {r.key: r for r in profile({**mat, "floor_max": 30.0, "sensor_lost_demand": 0.3, "guard_max_on_s": 0})}
    assert recs["floor_max"].recommended == 27.0
    assert recs["sensor_lost_demand"].recommended == 0.0 and recs["guard_max_on_s"].recommended == 7200.0
    assert "floor_max" not in {r.key for r in profile({**mat, "floor_max": 25.0})}


def test_goals_change_only_regulation():
    few = goal_changes("fewer_switching", BOILER)
    assert few == {"cycle_s": 1500.0, "min_on_s": 600.0, "min_off_s": 600.0}
    steady = goal_changes("steadier", BOILER)
    assert steady["cycle_s"] == 600.0 and all(not k.startswith("target") for k in steady)
    thrift = goal_changes("thriftier", BOILER)
    assert thrift == {"pre_change_s": 3600.0, "coast_window_s": 2700.0}
    assert goal_changes("recommended", {**BOILER, "cycle_s": 600.0}) == {"cycle_s": 900.0}
    assert goal_changes("fewer_switching", {**BOILER, "control": "external"}) == {}
    assert goal_changes("fewer_switching", {**BOILER, "system": "floor_single", "cycle_s": 6000.0})["cycle_s"] == 7200.0


def test_expectation_is_a_rough_scale():
    e = expect("fewer_switching", {"cycle_s": 1350.0}, BOILER, {"starts_day": 21.0, "dev_c": 0.2})
    assert e == {"starts": (21, 14), "dev": (0.2, 0.2)}
    assert expect("fewer_switching", {"cycle_s": 1350.0}, BOILER, None) == {}
    assert effective({**BOILER, "system": "floor_single"})["catchup_after_s"] == 7200.0


def test_advice_from_the_numbers():
    assert advise({"days": 1.0, "starts_day": 40, "short_runs_pct": 90}, BOILER) == []
    assert advice_text([], "hu", 1.0).startswith("Még kevés az adat")
    items = advise({"days": 7, "starts_day": 30.4, "short_runs_pct": 70, "cold_h_day": 2.5, "overheated_h_day": 0.4,
                    "quiet_gaps": 2, "longest_gap_h": 3.25}, BOILER)
    assert [i["id"] for i in items] == ["many_short", "often_cold", "sensor_quiet"]
    text = advice_text(items, "hu", 7)
    assert "naponta kb. 30 indítás, ezek 70 %-a 5 percnél" in text and "2 alkalommal" in text and "{" not in text
    assert advice_text(advise({"days": 7, "starts_day": 10}, BOILER), "en", 7) == "Nothing to do from the last days' numbers."
    hot = advise({"days": 3, "overheated_h_day": 3.25}, BOILER)
    assert hot[0]["id"] == "often_hot" and hot[0]["goal"] == "thriftier"
    assert "átlagosan 3,2 órát" in advice_text(hot, "hu", 3)
    shadow = {**BOILER, "mode": "shadow"}
    assert advise({"days": 3, "overheated_h_day": 9.0, "starts_day": 40, "short_runs_pct": 90}, shadow) == []
    assert advice_text([], "hu", 3, shadow=True).startswith("Árnyék módban")
    assert [i["id"] for i in advise({"days": 3, "quiet_gaps": 1, "longest_gap_h": 1.0}, shadow)] == ["sensor_quiet"]


def test_runs_and_gaps():
    import importlib
    th = importlib.import_module("hc_thermostat.tuning_ha")
    t0 = datetime(2026, 11, 28, 0, 0)
    m = lambda x: t0 + timedelta(minutes=x)  # noqa: E731
    series = [(m(-10), True), (m(5), False), (m(20), True), (m(26), False), (m(40), True)]
    assert th.runs(series, t0, m(60)) == [300.0, 360.0]  # the run still on at the end does not count
    sensor = [(m(0), 21.0), (m(10), None), (m(50), 21.2), (m(60), None), (m(70), 21.1)]
    assert th.gaps(sensor, t0, m(120)) == [2400.0]

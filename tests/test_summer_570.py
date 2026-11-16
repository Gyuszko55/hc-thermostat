"""0.57.0: automatic summer / winter mode of the heat pump coordination – from the house's own demand, not a date:
summer after `hp_summer_after_h` with no circuit / zone demand, back to winter when the demand lasted
`hp_winter_after_s` without a break and a room still asks; the frost limit and the cold-weather ON stay; an optional
weekly "exercise due" signal for the PLC."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
hpc = importlib.import_module("hc_thermostat.core.hp_coord")

T0 = datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)  # a Monday
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def H(hours: float) -> datetime:
    return T0 + timedelta(hours=hours)


def need(demand: bool, asking: bool | None = None):
    return hpc.CircuitNeed("floor", demand, 30.0, 2.0, asking)


def I(demand=False, asking=None, **kw):
    base = dict(outdoor=12.0, top=40.0, charge=None, trend_c_h=0.0, circuits=(need(demand, asking),))
    base.update(kw)
    return hpc.HpInputs(**base)


def HP(**kw):
    kw.setdefault("hp_auto_summer", True)
    kw.setdefault("hp_min_on_s", 0)
    kw.setdefault("hp_min_off_s", 0)
    return hpc.HeatPumpCoordinator(hpc.HpConfig(**kw))


def into_summer(h, hours=24.0):
    h.step(H(0), I())
    d = h.step(H(hours), I())
    assert d.summer and d.details["season_change"] == "summer"
    return d


def test_off_by_default_and_nothing_changes():
    cfg = hpc.HpConfig()
    assert cfg.hp_auto_summer is False and cfg.hp_summer_after_h == 24 and cfg.hp_winter_after_s == 1800
    h = hpc.HeatPumpCoordinator(cfg)
    h.step(H(0), I())
    d = h.step(H(100), I())
    assert not d.summer and d.reason == "off"


def test_summer_after_24_hours_without_room_demand():
    h = HP()
    assert not h.step(H(0), I()).summer
    assert not h.step(H(23.9), I()).summer
    d = h.step(H(24), I())
    assert d.summer and d.reason == "summer" and not d.enable and not d.heat_demand


def test_a_room_demand_restarts_the_24_hours():
    h = HP()
    h.step(H(0), I())
    h.step(H(20), I(demand=True))
    assert not h.step(H(30), I()).summer  # only 10 h since the last demand
    assert h.step(H(44), I()).summer


def test_tank_charging_does_not_keep_winter():
    """Only the rooms count: a low tank (heat demand of the tank) does not stop the summer from coming."""
    h = HP(hp_charge_on=10)
    h.step(H(0), I(charge=5.0))
    d = h.step(H(24), I(charge=5.0))
    assert d.summer and not d.heat_demand and d.reason == "summer"


def test_no_low_charge_start_and_no_standby_in_summer():
    h = HP(hp_charge_on=10, hp_standby=True)
    into_summer(h)
    d = h.step(H(25), I(charge=3.0))
    assert not d.heat_demand and not d.enable and d.reason == "summer"
    assert d.raw == 25.0  # the lowest target


def test_running_heating_stops_when_summer_starts():
    h = HP(hp_charge_on=10)
    h.step(H(0), I(charge=5.0))
    assert h.heating
    d = h.step(H(24), I(charge=6.0))
    assert d.summer and not d.heat_demand and not h.heating


def test_frost_limit_still_heats_in_summer():
    h = HP()
    into_summer(h)
    d = h.step(H(25), I(top=6.0))
    assert d.summer and d.heat_demand and d.reason == "frost"


def test_cold_weather_on_keeps_the_unit_on_without_heating():
    h = HP(hp_cold_on=True)
    into_summer(h)
    d = h.step(H(25), I(outdoor=2.0))
    assert d.summer and d.enable and d.reason == "cold_on" and not d.heat_demand and d.raw == 25.0


def test_one_tpi_pulse_does_not_end_the_summer():
    h = HP()
    into_summer(h)
    # a single ask: the circuit keeps its lasting demand for 30 min, but no room asks at the end
    h.step(H(25), I(demand=True, asking=True))
    d = h.step(H(25) + timedelta(minutes=31), I(demand=True, asking=False))
    assert d.summer
    d = h.step(H(25) + timedelta(minutes=32), I(demand=False, asking=False))
    assert d.summer and d.details["demand_held_s"] is None


def test_lasting_demand_brings_winter_back_after_30_minutes():
    h = HP()
    into_summer(h)
    t = H(30)
    assert h.step(t, I(demand=True, asking=True)).summer
    assert h.step(t + timedelta(minutes=15), I(demand=True, asking=False)).summer  # TPI pause, still lasting
    d = h.step(t + timedelta(minutes=29), I(demand=True, asking=True))
    assert d.summer and d.details["demand_held_s"] == 29 * 60
    d = h.step(t + timedelta(minutes=30), I(demand=True, asking=True, top=28.0))
    assert not d.summer and d.details["season_change"] == "winter"
    assert d.heat_demand and d.enable and d.reason == "heat_needed"  # need 32 > top 28: it heats again at once


def test_zero_means_back_to_winter_at_once():
    h = HP(hp_winter_after_s=0)
    into_summer(h)
    d = h.step(H(30), I(demand=True, asking=True, top=28.0))
    assert not d.summer and d.heat_demand


def test_buffer_zones_without_circuits_count_too():
    h = HP(hp_winter_after_s=0)
    h.step(H(0), I(circuits=()))
    assert h.step(H(24), I(circuits=())).summer
    assert not h.step(H(30), I(circuits=(), zones_asking=True)).summer


def test_summer_replaces_the_24h_stop_with_standby():
    h = HP(hp_standby=True, hp_idle_off=True)
    h.step(H(0), I())
    assert h.step(H(1), I()).reason == "standby"
    assert h.step(H(24), I()).reason == "summer"


def test_switching_the_option_off_ends_the_summer():
    h = HP()
    into_summer(h)
    h.cfg.hp_auto_summer = False
    d = h.step(H(25), I())
    assert not d.summer and d.details["season_change"] == "winter"


def test_exercise_signal_weekly_in_summer_only():
    h = HP(hp_exercise=True, hp_exercise_weekday=2, hp_exercise_hour=10, hp_exercise_min=10)  # Wednesday 10:00
    h.step(H(0), I())  # Monday 06:00
    wed = datetime(2026, 11, 18, 10, 0, tzinfo=timezone.utc)
    assert h.step(wed - timedelta(minutes=1), I()).summer
    assert not h.step(wed - timedelta(minutes=1), I()).exercise
    assert h.step(wed, I()).exercise
    assert h.step(wed + timedelta(minutes=9), I()).exercise
    assert not h.step(wed + timedelta(minutes=10), I()).exercise
    # in winter there is no exercise signal (the zones run their valves by heating)
    w = HP(hp_exercise=True, hp_exercise_weekday=2, hp_exercise_hour=10)
    w.step(wed - timedelta(hours=1), I(demand=True))
    assert not w.step(wed, I(demand=True)).exercise


def test_restart_keeps_the_summer_and_the_clocks():
    h = HP()
    into_summer(h)
    data = json.loads(json.dumps(h.state(H(24))))
    g = HP()
    g.restore(data, H(25))
    assert g.summer and g.summer_since == H(24)
    d = g.step(H(25), I())
    assert d.summer and d.details["season_change"] is None
    off = HP(hp_auto_summer=False)
    off.restore(data, H(25))
    assert not off.summer  # the option was switched off meanwhile


def test_old_state_without_the_new_keys():
    g = HP()
    g.restore({"enable": False, "heating": False}, H(0))
    assert not g.summer and g.last_room is None
    assert not g.step(H(0), I()).summer  # the 24 h count starts at the first run, not from never


def test_settings_entities_and_texts():
    assert "summer" in hpc.REASONS
    src = (BASE / "config_flow.py").read_text()
    for key in ("hp_auto_summer", "hp_exercise"):
        assert f'b("{key}")' in src
    for key in ("hp_summer_after_h", "hp_winter_after_s", "hp_exercise_weekday", "hp_exercise_hour", "hp_exercise_min"):
        assert f'n("{key}"' in src
    assert "CONF_HP_SUMMER_OUT" in src and "CONF_HP_EXERCISE_OUT" in src
    bs = (BASE / "binary_sensor.py").read_text()
    assert "HcHpSummer(c)" in bs and "HcHpExercise(c)" in bs
    for lang in ("en", "hu"):
        text = (BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8")
        data = json.loads(text)
        assert data["entity"]["binary_sensor"]["hp_summer"]["name"]
        assert data["entity"]["binary_sensor"]["hp_exercise"]["name"]
        assert data["entity"]["sensor"]["hp_decision"]["state"]["summer"]
        for key in ("hp_auto_summer", "hp_summer_after_h", "hp_winter_after_s", "hp_summer_entity", "hp_exercise_entity"):
            assert text.count(f'"{key}"') == 2, (lang, key)
    panel = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "hp_auto_summer" in panel and 'summer: "Nyári üzem: nem fűt"' in panel


def test_coordinator_passes_the_asking_now():
    src = (BASE / "hp_coord_coordinator.py").read_text()
    assert "_ASK_FRESH_S" in src and "cc.circuit.last_ask" in src
    assert "self.out_summer" in src and "self.out_exercise" in src


def test_version():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.57.0", "0.57.1", "0.58.0", "0.59.0", "0.60.0", "0.61.0")

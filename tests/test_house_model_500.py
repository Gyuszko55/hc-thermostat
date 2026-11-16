"""0.50.0: the house model – loss factor and free heat from a line through the days, the time constant τ from the
quiet stretches, and their uses: the optimal start before the night end and the forecast hold before a lowering.

Numbers from a real house: before the wall insulation 163 W/K with 0.7 kW free heat (the plain ratio said
125 W/K), after it about 100 W/K; τ about 90 h from 19 nights without a burn.
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from core.heat_need import PRIOR_DAYS, HeatNeedEstimator
from core.messages import explain
from core.model import HcConfig, Inputs, Presence, Reading
from core.supervisor import Supervisor
from core.thermal import TauEstimator, predict

LOCAL = timezone(timedelta(hours=1))


def _days(est, loss, gains, deltas, start=1):
    for i, dT in enumerate(deltas):
        kw = loss * dT - gains
        est.add_sample(f"2026-10-{start + i:02d}", kw * 24, dT * 24)


# --- 1. the line ----------------------------------------------------------------------------------------------------
def test_the_line_finds_the_loss_and_the_free_heat():
    est = HeatNeedEstimator()
    _days(est, 0.163, 0.7, [8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30])
    assert est.source == "fit"
    assert est.loss_kw_per_k == pytest.approx(0.163, rel=1e-6)
    assert est.gains_kw == pytest.approx(0.7, rel=1e-6)
    # the plain ratio folds the free heat in: too low, and the need in a cold spell half of the truth
    assert est.ratio_kw_per_k < 0.14
    assert est.need_kw(22.0, -10.0) == pytest.approx(0.163 * 32 - 0.7)
    assert est.balance_point(22.0) == pytest.approx(22.0 - 0.7 / 0.163)


def test_days_of_the_same_weather_keep_the_ratio():
    est = HeatNeedEstimator()
    _days(est, 0.1, 0.3, [15.0, 15.5, 16.0, 15.2, 15.8, 15.1, 15.9, 15.4, 15.6, 15.3, 15.7, 15.0])
    assert est.fit() is None and est.source == "ratio"
    assert est.gains_kw == 0.0


def test_a_hand_given_value_holds_until_days_are_learned_then_blends():
    est = HeatNeedEstimator(0.163, 0.7)
    assert est.source == "manual" and est.loss_kw_per_k == pytest.approx(0.163)
    assert est.need_kw(22.0, 2.0) == pytest.approx(0.163 * 20 - 0.7)
    _days(est, 0.1, 0.3, [8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 9, 11])  # 14 days: half and half
    assert len(est.samples) == PRIOR_DAYS
    assert est.source == "fit"
    assert est.loss_kw_per_k == pytest.approx((0.163 + 0.1) / 2, rel=1e-6)
    assert est.gains_kw == pytest.approx((0.7 + 0.3) / 2, rel=1e-6)


def test_a_poor_line_is_not_trusted():
    est = HeatNeedEstimator()
    deltas = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26]
    for i, dT in enumerate(deltas):  # heat unrelated to the weather
        est.add_sample(f"2026-10-{i + 1:02d}", (2.0 if i % 2 else 0.5) * 24, dT * 24)
    assert est.fit() is None


def test_relearning_drops_the_old_days_and_the_seed_before_it():
    est = HeatNeedEstimator()
    _days(est, 0.163, 0.7, [8, 10, 12, 14, 16, 18, 20, 22, 24, 26])
    est.reset("2026-11-14")
    assert not est.samples and est.source is None
    est.add_sample("2026-11-10", 30.0, 400.0)  # a day from the statistics, before the change
    assert not est.samples
    est.add_sample("2026-11-15", 30.0, 400.0)
    fresh = HeatNeedEstimator()
    fresh.restore(est.state())
    assert fresh.since == "2026-11-14" and len(fresh.samples) == 1


# --- 2. τ -----------------------------------------------------------------------------------------------------------
def _night(est, start, hours, tau, t0=22.5, eq=3.0, heat_before=True, step_min=5):
    if heat_before:
        est.update(start - timedelta(minutes=70), True, True, t0, eq)
    for k in range(int(hours * 60 / step_min) + 1):
        now = start + timedelta(minutes=k * step_min)
        est.update(now, False, True, predict(t0, eq, tau, k * step_min / 60), eq)
    est.update(start + timedelta(hours=hours, minutes=step_min), True, True, None, eq)  # the next burn closes it


def test_tau_is_learned_from_quiet_nights():
    est = TauEstimator()
    for d in range(3):
        _night(est, datetime(2026, 11, 1 + d, 22, 0, tzinfo=LOCAL), 6, 90.0)
    assert est.source == "learned"
    assert est.tau_h == pytest.approx(90.0, rel=0.03)


def test_short_or_disturbed_stretches_teach_nothing():
    est = TauEstimator()
    _night(est, datetime(2026, 11, 1, 22, 0, tzinfo=LOCAL), 2, 90.0)  # under 3 hours
    start = datetime(2026, 11, 2, 22, 0, tzinfo=LOCAL)
    for k in range(70):  # a window opens after an hour
        now = start + timedelta(minutes=5 * k)
        est.update(now, False, k < 12, 22.0 - 0.01 * k, 3.0)
    assert not est.samples and est.tau_h is None


def test_hand_given_tau_and_the_blend():
    est = TauEstimator(manual_tau_h=90.0)
    assert est.tau_h == 90.0 and est.source == "manual"
    for d in range(5):
        _night(est, datetime(2026, 11, 1 + d, 22, 0, tzinfo=LOCAL), 6, 130.0)
    assert est.tau_h == pytest.approx((90 + 130) / 2, rel=0.03)
    fresh = TauEstimator(manual_tau_h=90.0)
    fresh.restore(est.state())
    assert len(fresh.samples) == 5
    fresh.reset()
    assert fresh.tau_h == 90.0


def test_the_prediction():
    assert predict(22.5, 3.0, 90.0, 6.0) == pytest.approx(3.0 + 19.5 * math.exp(-6 / 90))
    assert predict(22.5, 3.0, 0.0, 6.0) == 22.5


# --- 3. the supervisor ----------------------------------------------------------------------------------------------
BASE = dict(control="pid", pid_kp=0.5, pid_ki_per_hour=0.2, target_home=22.5, target_night=21.0,
            night_start="22:00", night_end="06:00", cycle_s=1800, min_on_s=300, min_off_s=300,
            season_enabled=False, boost_enabled=False, learning_enabled=False,
            house_loss_w_k=100.0, house_gains_kw=0.3, house_tau_h=90.0)


def _step(sup, now, room, outdoor=0.0, **kw):
    return sup.step(Inputs(now=now, indoor=Reading(room), outdoor=Reading(outdoor), presence=Presence.HOME, **kw))


def test_the_need_uses_the_line():
    sup = Supervisor(HcConfig(**{**BASE, "night_start": "00:00", "night_end": "00:00"}))
    d = _step(sup, datetime(2026, 11, 14, 12, 0, tzinfo=LOCAL), 22.0, outdoor=2.0)
    assert d.loss_kw_per_k == pytest.approx(0.1)
    assert d.heat_need_kw == pytest.approx(0.1 * (22.5 - 2.0) - 0.3)
    assert sup.equilibrium(2.0) == pytest.approx(5.0)


def test_optimal_start_brings_the_day_target_forward():
    sup = Supervisor(HcConfig(**BASE, optimal_start=True))
    morning = datetime(2026, 11, 15, 4, 30, tzinfo=LOCAL)
    # the room at 21 °C: about 1.5 K to rise, 17 min/K + 20 min = about 46 min
    d = _step(sup, morning, 21.0)
    assert d.target == 21.0 and "optimal_start" not in d.details
    started = None
    for k in range(1, 60):
        now = morning + timedelta(minutes=k)
        d = _step(sup, now, 21.0)
        if d.target == 22.5:
            started = now
            break
    assert started is not None and timedelta(minutes=40) <= datetime(2026, 11, 15, 6, 0, tzinfo=LOCAL) - started \
        <= timedelta(minutes=50)
    assert d.details["optimal_start"]["needed_min"] in range(44, 50)
    assert "Optimális indítás" in explain(d, "hu") and "Optimal start" in explain(d, "en")
    # the room warms: the day target stays until the night end, then the schedule takes over
    d = _step(sup, started + timedelta(minutes=20), 22.3)
    assert d.target == 22.5
    d = _step(sup, datetime(2026, 11, 15, 6, 1, tzinfo=LOCAL), 22.5)
    assert d.target == 22.5 and "optimal_start" not in d.details and sup.early_start is None


def test_optimal_start_is_off_by_default_and_waits_for_a_warm_room():
    sup = Supervisor(HcConfig(**BASE))
    assert _step(sup, datetime(2026, 11, 15, 5, 50, tzinfo=LOCAL), 21.0).target == 21.0
    sup = Supervisor(HcConfig(**BASE, optimal_start=True))
    assert _step(sup, datetime(2026, 11, 15, 5, 50, tzinfo=LOCAL), 22.45).target == 21.0  # warm enough already
    sup = Supervisor(HcConfig(**BASE, optimal_start=True))
    d = sup.step(Inputs(now=datetime(2026, 11, 15, 5, 50, tzinfo=LOCAL), indoor=Reading(21.0),
                        outdoor=Reading(0.0), presence=Presence.AWAY))
    assert d.target == BASE.get("target_away", HcConfig().target_away)


def test_optimal_start_survives_a_restart():
    sup = Supervisor(HcConfig(**BASE, optimal_start=True))
    _step(sup, datetime(2026, 11, 15, 5, 30, tzinfo=LOCAL), 21.0)
    assert sup.early_start is not None
    again = Supervisor(HcConfig(**BASE, optimal_start=True))
    again.restore(sup.state())
    assert _step(again, datetime(2026, 11, 15, 5, 40, tzinfo=LOCAL), 22.4).target == 22.5


def test_the_hold_before_the_night_looks_ahead_with_tau():
    evening = datetime(2026, 11, 14, 20, 30, tzinfo=LOCAL)  # 90 min before the night
    sup = Supervisor(HcConfig(**BASE))
    sup.regulator.integral = 0.25
    d = _step(sup, evening, 22.4)
    # left alone: 3.0 + 19.4 × e^(-1.5/90) ≈ 22.08 – above 21 and within 0.5 of 22.5
    assert d.limited_by == "pre_change" and not d.output
    assert d.details["pre_change"]["predicted"] == pytest.approx(22.08, abs=0.02)
    assert "kb. 22,08 °C-ra hűl" in explain(d, "hu") or "22.08" in explain(d, "en")
    # a cooler room would sag too far under the current target: a normal start
    sup = Supervisor(HcConfig(**BASE))
    sup.regulator.integral = 0.25
    d = _step(sup, evening, 22.0)
    assert d.limited_by != "pre_change"


def test_without_tau_the_hold_keeps_its_fixed_window():
    cfg = {**BASE, "house_tau_h": 0.0}
    sup = Supervisor(HcConfig(**cfg))
    sup.regulator.integral = 0.25
    assert _step(sup, datetime(2026, 11, 14, 20, 30, tzinfo=LOCAL), 22.4).limited_by != "pre_change"
    sup = Supervisor(HcConfig(**cfg))
    sup.regulator.integral = 0.25
    assert _step(sup, datetime(2026, 11, 14, 21, 45, tzinfo=LOCAL), 22.4).limited_by == "pre_change"


def test_tau_learns_inside_the_supervisor():
    sup = Supervisor(HcConfig(**{**BASE, "house_tau_h": 0.0, "night_start": "00:00", "night_end": "00:00",
                                 "target_home": 15.0}))
    eq = sup.equilibrium(0.0)
    start = datetime(2026, 11, 14, 22, 0, tzinfo=LOCAL)
    for night in range(3):
        t0 = start + timedelta(days=night)
        for k in range(0, 7 * 12):
            now = t0 + timedelta(minutes=5 * k)
            _step(sup, now, predict(22.5, eq, 90.0, k / 12), actual_heating=False)
        _step(sup, t0 + timedelta(hours=7, minutes=5), 21.0, actual_heating=True)
    assert sup.tau.source == "learned"
    assert sup.tau.tau_h == pytest.approx(90.0, rel=0.05)


def test_version():
    import json
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
    assert json.loads((root / "manifest.json").read_text())["version"] in ("0.50.0", "0.51.0", "0.51.1", "0.51.2", "0.52.0", "0.52.1", "0.53.0", "0.54.0", "0.55.0", "0.56.0", "0.56.1", "0.57.0", "0.57.1", "0.58.0", "0.59.0", "0.60.0", "0.61.0")


# --- 4. mould risk at the coldest surface, humidity sensors from the thermometers ------------------------------------
def test_the_coldest_surface():
    from core.measures import surface
    s = surface(22.0, 55.0, 0.0, 0.7)
    assert s["surface_temp"] == 15.4
    assert 80 < s["surface_rh"] < 86  # 55 % in the room is about 83 % in the corner
    assert 50 < s["rh_limit"] < 55
    assert surface(22.0, 40.0, 0.0, 0.8)["surface_rh"] < 60  # an insulated corner, drier air
    assert surface(22.0, 55.0, 25.0, 0.7) is None  # warmer outside: no cold surface
    assert surface(22.0, None, 0.0, 0.7) is None


def test_the_risk_by_the_surface_hours():
    from core.measures import Humidity
    h = Humidity()
    t = datetime(2026, 11, 14, 0, 0, tzinfo=LOCAL)
    for k in range(5):
        h.update(t + timedelta(hours=k), 55.0, 82.0)
    assert h.risk(55.0, 82.0) == "moderate"
    h.update(t + timedelta(hours=5), 55.0, 81.0)
    assert h.risk(55.0, 75.0) == "high"  # six hours of 80 % in the corner
    dry = Humidity()
    dry.update(t, 45.0, 65.0)
    assert dry.risk(45.0, 65.0) == "low"
    assert Humidity().risk(50.0, 91.0) == "high"
    again = Humidity()
    again.restore(h.state())
    assert again.surface == h.surface
    old = Humidity()
    old.restore({"2026-11-14T01": 72.0})  # stored before 0.50.0: the hours table itself
    assert old.hours == {"2026-11-14T01": 72.0} and old.risk(72.0) == "moderate"


def test_rooms_get_the_humidity_of_their_thermometers(monkeypatch):
    import importlib
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
    rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
    parse_rooms = importlib.import_module("hc_thermostat.core.room_model").parse_rooms
    rooms = [{"key": "nappali", "name": "Nappali", "sensors": []},
             {"key": "haloszoba", "name": "Hálószoba", "sensors": ["sensor.halo_t"]},
             {"key": "konyha", "name": "Konyha", "sensors": ["sensor.konyha_t"], "humidity": ["sensor.mine"]}]
    devices = {"sensor.house_t": ["sensor.house_rh"], "sensor.halo_t": ["sensor.halo_rh"],
               "sensor.konyha_t": ["sensor.konyha_rh"]}
    monkeypatch.setattr(rooms_ha, "humidity_of", lambda hass, ids: [h for i in ids for h in devices.get(i, [])])
    monkeypatch.setattr(rooms_ha, "room_specs_for", lambda hass, conf: (parse_rooms(rooms), "nappali"))
    out = rooms_ha.auto_humidity(None, {"indoor_entity": "sensor.house_t"})
    got = {r["key"]: r.get("humidity") for r in out["rooms"]}
    assert got == {"nappali": ["sensor.house_rh"], "haloszoba": ["sensor.halo_rh"], "konyha": ["sensor.mine"]}
    monkeypatch.setattr(rooms_ha, "room_specs_for", lambda hass, conf: ([], None))
    assert rooms_ha.auto_humidity(None, {"indoor_entity": "sensor.house_t"}) == {"humidity_entity": "sensor.house_rh"}
    assert rooms_ha.auto_humidity(None, {"indoor_entity": "sensor.house_t", "humidity_entity": "sensor.x"}) is None


def test_a_line_with_negative_free_heat_is_not_trusted():
    est = HeatNeedEstimator(0.1, 0.3)
    _days(est, 0.05, -0.4, [8, 10, 12, 14, 16, 18, 20, 22, 24, 26])  # hot water in the meter, mild days
    assert est.fit() is None and est.source == "manual" and est.loss_kw_per_k == pytest.approx(0.1)


def test_one_mould_sensor_per_room_across_instances():
    import importlib
    import sys
    from pathlib import Path
    from types import SimpleNamespace
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
    rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
    first = SimpleNamespace(entry_id="a", title="Boiler HC", data={}, options={"rooms": [{"key": "nappali", "humidity": ["sensor.rh"]}]})
    second = SimpleNamespace(entry_id="b", title="HC Thermostat", data={}, options={"rooms": [{"key": "nappali", "humidity": ["sensor.rh"]}]})
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: [first, second]))
    assert rooms_ha.humidity_owner(hass, "a", ["sensor.rh"]) is None
    assert rooms_ha.humidity_owner(hass, "b", ["sensor.rh"]) == "Boiler HC"

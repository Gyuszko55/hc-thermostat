"""0.69.0 (a tester's first night on a buffer house): the fast catch-up of a room long behind, the holding offset
learned by the hour, the mixing circuit's flow from the rooms' lasting shortfall, the measured answer of a room, a
timing suggestion with a valve delay; the heat pump's full target at a new charge and its compressor power threshold."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from core.circuit import CircuitConfig, MixingCircuit, ZoneReading  # noqa: E402
from core.hp_coord import CircuitNeed, HeatPumpCoordinator, HpConfig, HpInputs  # noqa: E402
from core.learning import Learner  # noqa: E402
from core.matrix import source_defaults, timing_advice  # noqa: E402
from core.messages import explain  # noqa: E402
from core.model import HcConfig, Inputs, Reading, Reason  # noqa: E402
from core.response import ResponseMeter  # noqa: E402
from core.setpoint_hold import HoldConfig, SetpointHold  # noqa: E402
from core.supervisor import Supervisor  # noqa: E402

T0 = datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, boost_enabled=False, learning_enabled=False,
           target_home=21.0, control="tpi")


def at(m):
    return T0 + timedelta(minutes=m)


def _step(sup, m, indoor, outdoor=5.0):
    return sup.step(Inputs(now=at(m), indoor=Reading(indoor), outdoor=Reading(outdoor)))


# --- 1. the fast catch-up -------------------------------------------------------------------------------------------
def test_a_room_long_behind_gets_the_whole_cycle():
    sup = Supervisor(HcConfig(**DAY))
    for m in range(30):
        d = _step(sup, m, 20.4)
        assert d.reason == Reason.REGULATING and d.demand < 1.0 and "catchup" not in d.details
    d = _step(sup, 30, 20.4)
    assert d.demand == 1.0 and d.output and d.details["catchup"]["since_min"] == 30
    assert "Gyors felzárkózás" in explain(d, "hu") and "Fast catch-up" in explain(d, "en")
    d = _step(sup, 31, 20.75)  # 0.25 behind: still on
    assert d.demand == 1.0
    d = _step(sup, 32, 20.85)  # within 0.2: the TPI again
    assert d.demand < 1.0 and "catchup" not in d.details


def test_a_shortfall_that_does_not_last_or_a_new_target_starts_again():
    sup = Supervisor(HcConfig(**DAY))
    for m in range(20):
        _step(sup, m, 20.4)
    _step(sup, 20, 20.6)  # 0.4: below the threshold – the count starts again
    for m in range(21, 50):
        assert "catchup" not in _step(sup, m, 20.4).details
    assert "catchup" in _step(sup, 51, 20.4).details
    assert sup._catchup_step(at(52), 22.0, 20.4, False) is None  # a new target: counts again


def test_switched_off_yielding_and_kept_over_a_restart():
    sup = Supervisor(HcConfig(**{**DAY, "catchup_gap": 0.0}))
    for m in range(40):
        d = _step(sup, m, 20.4)
    assert d.demand < 1.0
    sup = Supervisor(HcConfig(**DAY))
    for m in range(31):
        _step(sup, m, 20.4)
    assert sup._catchup
    fresh = Supervisor(HcConfig(**DAY))
    fresh.restore(json.loads(json.dumps(sup.state(), default=str)))
    assert fresh._catchup and fresh._catchup_since == sup._catchup_since
    assert sup._catchup_step(at(40), 21.0, 20.4, True) is None and not sup._catchup  # another source in charge


def test_a_floor_waits_two_hours():
    assert source_defaults("floor_single", "heat_pump")["catchup_after_s"] == 7200.0
    assert "catchup_after_s" not in source_defaults("radiator_single", "onoff_boiler")
    assert HcConfig().catchup_gap == 0.5 and HcConfig().catchup_release == 0.2


def test_a_partial_cycle_cooling_back_is_no_fault():
    """After a catch-up the room settles back while the relay runs part of the cycle: not a dead burner."""
    sup = Supervisor(HcConfig(**DAY))
    sup._last_partial = True
    sup._fail_strikes = 1
    t = 20.8
    for m in range(0, 120):
        sup._update_fault(Inputs(now=at(m), indoor=Reading(t), actual_heating=True), t, 21.0, 60.0)
        t -= 0.005
    assert not sup.fault
    sup._last_partial = False  # the whole cycle and still cooling: a fault
    for m in range(120, 200):
        sup._update_fault(Inputs(now=at(m), indoor=Reading(t), actual_heating=True), t, 21.0, 60.0)
        t -= 0.005
    assert sup.fault


# --- 2. the holding offset by the hour --------------------------------------------------------------------------------
def test_the_offset_moves_every_hour_not_while_saturated():
    learner = Learner(HcConfig(learning_enabled=True))
    t = T0
    for _ in range(120):
        learner.regulating(t, 30.0, 23.2, 22.9)
        t += timedelta(seconds=30)
    assert learner.tpi_offset == 0.02  # 0.3 behind for an hour: one step (at most 0.02)
    for _ in range(240):
        learner.regulating(t, 30.0, 23.2, 22.4, saturated=True)
        t += timedelta(seconds=30)
    assert learner.tpi_offset == 0.02  # the whole cycle already: no wind-up
    restored = Learner(HcConfig(learning_enabled=True))
    restored.restore(json.loads(json.dumps(learner.state())))
    assert restored.tpi_offset == 0.02 and restored._h_s == learner._h_s


# --- 3. the circuit's flow from the lasting shortfall ----------------------------------------------------------------
def _circ(**kw):
    return MixingCircuit(CircuitConfig.from_conf({"circuit_kind": "radiator", "circuit_room_trim": True,
                                                  "circuit_confirm_s": 0, "circuit_min_interval_s": 0,
                                                  "circuit_deadband": 0.5, **kw}))


def _hour(c, start, zones, outdoor=0.0, minutes=61):
    d = None
    for m in range(minutes):
        d = c.step(start + timedelta(minutes=m), zones, outdoor)
    return d


def test_rooms_short_while_heating_raise_the_water_step_by_step():
    c = _circ()
    zones = [ZoneReading("a", True, 23.2, 22.8), ZoneReading("b", True, 23.2, 22.9), ZoneReading("c", False, 23.2, 23.2)]
    d0 = c.step(T0, zones, 0.0)
    d = _hour(c, T0, zones)
    assert c.trim == 0.5 and c.trim_why == "rooms_short" and d.details["trim"] == 0.5
    _hour(c, T0 + timedelta(minutes=61), zones)
    assert c.trim == 1.0
    assert c.raw(0.0, 23.2, 0.4) == round(d0.raw + 1.0, 2) or c.raw(0.0, 23.2, 0.4) > d0.raw


def test_rooms_holding_easily_lower_the_water_within_the_limit():
    c = _circ(circuit_trim_max=1.0)
    zones = [ZoneReading("a", False, 21.0, 21.1), ZoneReading("b", False, 21.0, 21.0)]
    for h in range(4):
        _hour(c, T0 + timedelta(minutes=61 * h), zones)
    assert c.trim == -1.0 and c.trim_why == "rooms_easy"


def test_a_cold_tank_or_one_hungry_room_of_three_does_not_raise():
    zones = [ZoneReading("a", True, 23.2, 22.5), ZoneReading("b", False, 23.2, 23.2), ZoneReading("c", False, 23.2, 23.3)]
    c = _circ()
    _hour(c, T0, zones)
    assert c.trim == 0.0
    c = _circ()
    c.limited = True
    c.cap = lambda now, given, top, linked: (given, None, "limited")  # keep it limited
    _hour(c, T0, [ZoneReading("a", True, 23.2, 22.5)])
    assert c.trim == 0.0


def test_trim_off_by_default_and_kept_over_a_restart():
    assert CircuitConfig().circuit_room_trim is False
    c = MixingCircuit(CircuitConfig.from_conf({"circuit_kind": "floor"}))
    _hour(c, T0, [ZoneReading("a", True, 23.2, 22.5)])
    assert c.trim == 0.0 and "trim" not in c.step(T0 + timedelta(hours=2), [], 0.0).details
    c = _circ()
    _hour(c, T0, [ZoneReading("a", True, 23.2, 22.5)])
    c2 = _circ()
    c2.restore(json.loads(json.dumps(c.state(T0 + timedelta(minutes=61)))), T0 + timedelta(minutes=61))
    assert c2.trim == c.trim == 0.5 and c2.trim_why == "rooms_short"


# --- 4. the measured answer ------------------------------------------------------------------------------------------
def test_response_meter_from_ordinary_runs():
    r = ResponseMeter()
    temps = [22.0] * 6 + [22.0 + 0.02 * i for i in range(1, 31)]  # 6 min of nothing, then +1.2 °C/h for 30 min
    m = 0
    for temp in temps:
        r.step(at(m), True, temp, 23.0, True)
        m += 1
    after = [22.6 + 0.02 * i for i in range(1, 6)] + [22.7 - 0.01 * i for i in range(1, 50)]
    for temp in after:
        r.step(at(m), False, temp, 23.0, True)
        m += 1
    r.step(at(m), True, 22.2, 23.0, True)  # the next run closes the cooling
    v = r.info()["values"]
    assert 9 <= v["delay_min"] <= 12
    assert 1.0 <= v["rise_c_h"] <= 1.4
    assert 0.07 <= v["afterheat_c"] <= 0.11 and v["afterheat_min"] == 4
    assert 0.4 <= v["cool_c_h"] <= 0.7
    r2 = ResponseMeter()
    r2.restore(json.loads(json.dumps(r.state())))
    assert r2.values == r.values


def test_response_meter_skips_short_and_disturbed_runs():
    r = ResponseMeter()
    for m in range(5):
        r.step(at(m), True, 22.0 + 0.05 * m, 23.0, True)
    r.step(at(6), False, 22.3, 23.0, True)  # 6 minutes: too short
    assert r.info()["values"] == {}
    for m in range(10, 28):
        r.step(at(m), True, 22.0 + 0.02 * m, 23.0 if m < 20 else 23.5, True)  # the target changed: 8 min left
    r.step(at(28), False, 22.6, 23.5, True)
    assert "delay_min" not in r.info()["values"]


# --- 5. the timing suggestion ---------------------------------------------------------------------------------------
def test_timing_advice():
    assert timing_advice(None, 900, 0, 300) is None
    a = timing_advice(None, 900, 300, 300)  # the tester's first night: 15-min cycles, 5-min valves
    assert a == {"cycle_s": 1800.0, "min_on_s": 600.0, "lost_pct": 33, "floor": False}
    assert timing_advice("floor_single", 900, 300, 300)["cycle_s"] == 3600.0
    assert timing_advice(None, 3600, 300, 1200) is None  # the tester's new values


# --- 6. the heat pump: the full target at a new charge, the compressor's power threshold ----------------------------
def _hp(**kw):
    return HeatPumpCoordinator(HpConfig(**{"hp_charge_mode": "demand", "hp_min_off_s": 0, "hp_min_on_s": 0,
                                           "hp_reserve": 0.0, **kw}))


COLD = (("top", 36.0, 250.0, True), ("upper", 34.0, 250.0, True), ("lower", 32.0, 250.0, True), ("bottom", 28.0, 250.0, True))
WARM = (("top", 50.0, 250.0, True), ("upper", 50.0, 250.0, True), ("lower", 50.0, 250.0, True), ("bottom", 48.0, 250.0, True))


def _inp(layers, running=None, need=44.5):
    return HpInputs(outdoor=-3.0, top=layers[0][1], charge=30.0, trend_c_h=0.0,
                    circuits=(CircuitNeed("rad", True, need, 2.0, True),), layers=layers, hp_running=running)


def test_a_new_charge_gives_the_full_target_at_once():
    hp = _hp()
    d = hp.step(T0, _inp(WARM))
    assert not d.heat_demand and d.target == HpConfig().hp_flow_min
    d = hp.step(T0 + timedelta(minutes=1), _inp(COLD))
    assert d.heat_demand and d.target == d.raw >= 44.5 and d.details["jump"] == "charge_start"
    old = _hp(hp_charge_jump=False)
    old.step(T0, _inp(WARM))
    d = old.step(T0 + timedelta(minutes=1), _inp(COLD))
    assert d.target < d.raw and "jump" not in d.details  # the hold's confirmation and ramp, as before


def test_a_compressor_stopped_below_the_target_gets_it():
    hp = _hp()
    hp.step(T0, _inp(COLD, need=40.0))
    d = hp.step(T0 + timedelta(minutes=1), _inp(COLD, running=False, need=44.5))
    assert d.target == d.raw >= 44.5 and d.details["jump"] == "compressor_stopped"
    hp2 = _hp()
    hp2.step(T0, _inp(COLD, need=40.0))
    d = hp2.step(T0 + timedelta(minutes=1), _inp(COLD, running=True, need=44.5))
    assert d.target < d.raw  # running: the ordinary hold


def test_hold_jump():
    h = SetpointHold(HoldConfig(2.0, 600.0, 2700.0, 3.0, 6.0))
    h.step(T0, 30.0, 20.0, 50.0)
    r = h.jump(T0 + timedelta(seconds=10), 44.5, 20.0, 50.0, "charge_start")
    assert r.value == 44.5 and r.reason == "charge_start" and r.changed


def test_compressor_power_threshold():
    from hc_thermostat.hp_coord_coordinator import on_state
    st = SimpleNamespace(state="150", attributes={"unit_of_measurement": "W"}, last_reported=None, last_updated=None)
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: st))
    assert on_state(hass, "sensor.p") is True  # 100 W by default
    assert on_state(hass, "sensor.p", None, 200.0) is False  # the tester's 200 W
    st.state, st.attributes = "0.25", {"unit_of_measurement": "kW"}
    assert on_state(hass, "sensor.p", None, 200.0) is True
    assert HpConfig().hp_running_w == 100.0 and HpConfig().hp_charge_jump is True


# --- 7. form, texts, panel -------------------------------------------------------------------------------------------
def test_form_texts_and_panel():
    from hc_thermostat import config_flow as cf
    reg = cf.SETTINGS_SECTIONS["regulation"]
    for k in ("catchup_gap", "catchup_after_s", "catchup_release", "tpi_coef_int", "tpi_coef_ext"):
        assert k in reg
    keys = {str(k) for k in cf._circuit_settings({}, "radiator")}
    assert {"circuit_room_trim", "circuit_trim_step", "circuit_trim_s", "circuit_trim_max"} <= keys
    assert "hp_charge_jump" in cf.HPC_SECTIONS["hold"] and "hp_running_w" in cf.HPC_SECTIONS["running"]
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        sec = tr["options"]["step"]["settings"]["sections"]["regulation"]
        for k in ("catchup_gap", "catchup_after_s", "catchup_release", "tpi_coef_int", "tpi_coef_ext"):
            assert sec["data"][k] and sec["data_description"][k]
        for top in ("config", "options"):
            assert tr[top]["step"]["circuit_settings"]["data"]["circuit_room_trim"]
            assert tr[top]["step"]["hp_coord_settings"]["sections"]["hold"]["data"]["hp_charge_jump"]
    js = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "catchupText" in js and "responseText" in js and "timingText" in js and "Tartós igazítás" in js
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1")

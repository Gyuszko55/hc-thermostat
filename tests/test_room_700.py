"""0.70.0 (a tester's list after the 0.69.0 night): the heat pump's own target next to HC's on the diagram, watching a
mixing circuit's chain demand → pump → flow (watching only), and the heat pump's standby told apart from the
compressor running."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from core.circuit import CircuitConfig  # noqa: E402
from core.circuit_watch import CircuitWatch  # noqa: E402
from core.hp_coord import HpConfig  # noqa: E402

T0 = datetime(2026, 11, 17, 20, 0, tzinfo=timezone.utc)


def at(m):
    return T0 + timedelta(minutes=m)


# --- 2. the circuit watch ---------------------------------------------------------------------------------------------
def _w():
    return CircuitWatch(600.0, 900.0, 1.0)


def test_watch_normal_chain_with_the_plc_start_delay():
    w = _w()
    assert w.step(at(0), False, False, 25.0, 34.0, True, True) == "idle"
    assert w.step(at(1), True, False, 25.0, 34.0, True, True) == "wait_pump"
    assert w.step(at(6), True, False, 25.0, 34.0, True, True) == "wait_pump"  # the PLC's 5-minute delay: normal
    assert w.step(at(7), True, True, 25.0, 34.0, True, True) == "wait_flow"
    assert w.step(at(12), True, True, 25.6, 34.0, True, True) == "wait_flow"
    assert w.step(at(14), True, True, 26.2, 34.0, True, True) == "ok"
    assert w.step(at(30), True, True, 26.0, 34.0, True, True) == "ok"  # kept for the rest of the run
    assert w.step(at(31), False, False, 26.0, 34.0, True, True) == "idle"


def test_watch_pump_does_not_start():
    w = _w()
    w.step(at(0), True, False, 25.0, 34.0, True, True)
    assert w.step(at(9), True, False, 25.0, 34.0, True, True) == "wait_pump"
    assert w.step(at(10), True, False, 25.0, 34.0, True, True) == "no_pump"
    info = w.info(at(11))
    assert info["problem"] and info["problem_since"] == at(10)
    assert w.step(at(12), True, True, 25.0, 34.0, True, True) == "wait_flow"  # it started: the problem clears
    assert w.info(at(12))["problem"] is False


def test_watch_flow_does_not_move_and_a_warm_flow_is_fine():
    w = _w()
    w.step(at(0), True, True, 25.0, 34.0, True, True)
    assert w.step(at(14), True, True, 25.5, 34.0, True, True) == "wait_flow"
    assert w.step(at(15), True, True, 25.5, 34.0, True, True) == "no_flow"
    w2 = _w()  # already near the target when the pump started: no move needed
    assert w2.step(at(0), True, True, 33.0, 34.0, True, True) == "ok"


def test_watch_unknown_pump_never_raises_a_problem():
    w = _w()
    for m in range(0, 40):
        st = w.step(at(m), True, None, 25.0, 34.0, True, True)
    assert st == "wait_pump" and w.info(at(40))["pump_unknown"] is True


def test_watch_without_entities_or_switched_off():
    assert _w().step(at(0), True, True, 25.0, 34.0, False, False) == "not_watched"
    off = CircuitWatch(enabled=False)
    assert off.step(at(0), True, True, 25.0, 34.0, True, True) == "not_watched"
    w = _w()  # only a pump: the flow is not watched
    assert w.step(at(0), True, True, None, 34.0, True, False) == "pump_only"
    w = _w()  # only a flow thermometer: watched from the demand's start
    w.step(at(0), True, None, 25.0, 34.0, False, True)
    assert w.step(at(15), True, None, 25.2, 34.0, False, True) == "no_flow"


def test_watch_pump_stopping_restarts_the_flow_clock():
    w = _w()
    w.step(at(0), True, True, 25.0, 34.0, True, True)
    w.step(at(10), True, False, 25.0, 34.0, True, True)  # the PLC paused it
    assert w.step(at(12), True, True, 25.0, 34.0, True, True) == "wait_flow"
    assert w.step(at(26), True, True, 25.0, 34.0, True, True) == "wait_flow"
    assert w.step(at(27), True, True, 25.0, 34.0, True, True) == "no_flow"


def test_watch_config_defaults_and_pump_reading():
    cfg = CircuitConfig()
    assert (cfg.circuit_watch, cfg.circuit_watch_pump_s, cfg.circuit_watch_flow_s, cfg.circuit_watch_flow_c) == (True, 600.0, 900.0, 1.0)
    from hc_thermostat.circuit_coordinator import pump_state
    states = {"switch.p": SimpleNamespace(state="on"), "binary_sensor.p": SimpleNamespace(state="off"),
              "sensor.p": SimpleNamespace(state="35"), "sensor.z": SimpleNamespace(state="0"),
              "sensor.u": SimpleNamespace(state="unavailable")}
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    assert pump_state(hass, "switch.p") is True and pump_state(hass, "binary_sensor.p") is False
    assert pump_state(hass, "sensor.p") is True and pump_state(hass, "sensor.z") is False
    assert pump_state(hass, "sensor.u") is None and pump_state(hass, None) is None


# --- 3. standby vs the compressor ---------------------------------------------------------------------------------------
def _hass(**states):
    return SimpleNamespace(states=SimpleNamespace(get=states.get))


def _p(value, unit="W", when=T0):
    return SimpleNamespace(state=str(value), attributes={"unit_of_measurement": unit}, last_reported=when, last_updated=when)


def test_run_state_standby_heating_stopped_unknown():
    from hc_thermostat.hp_coord_coordinator import RUN_BOOL, run_state
    h = _hass(**{"sensor.a": _p(138), "sensor.b": _p(1450), "sensor.c": _p(3), "sensor.d": _p(1450, when=T0 - timedelta(minutes=30)),
                 "sensor.e": _p(138, when=T0 - timedelta(hours=2)), "sensor.f": _p(0.9, "kW")})
    assert run_state(h, "sensor.a", T0, 200.0, 10.0) == ("standby", 138.0)  # the tester's 138 W at a 200 W threshold
    assert run_state(h, "sensor.b", T0, 200.0, 10.0) == ("heating", 1450.0)
    assert run_state(h, "sensor.c", T0, 200.0, 10.0) == ("stopped", 3.0)
    assert run_state(h, "sensor.d", T0, 200.0, 10.0)[0] == "unknown"  # a stale "runs"
    assert run_state(h, "sensor.e", T0, 200.0, 10.0)[0] == "standby"  # a quiet low reading stays (as since 0.59.0)
    assert run_state(h, "sensor.f", T0, 200.0, 10.0) == ("heating", 900.0)
    assert run_state(h, "sensor.x", T0, 200.0, 10.0) == ("unknown", None)
    assert RUN_BOOL["standby"] is False and RUN_BOOL["heating"] is True and RUN_BOOL["unknown"] is None
    clim = _hass(**{"climate.hp": SimpleNamespace(state="heat", attributes={"hvac_action": "idle"})})
    assert run_state(clim, "climate.hp", T0)[0] == "standby"
    assert HpConfig().hp_standby_w == 10.0


def test_on_state_unchanged_by_standby():
    from hc_thermostat.hp_coord_coordinator import on_state
    h = _hass(**{"sensor.a": _p(138), "sensor.old": _p(41, when=T0 - timedelta(minutes=30))})
    assert on_state(h, "sensor.a", T0) is True  # 100 W default
    assert on_state(h, "sensor.a", T0, 200.0) is False
    assert on_state(h, "sensor.old", T0) is False  # an old low reading stays "does not run"


def test_diagram_and_coordination_use_the_same_state():
    from hc_thermostat.core.hp_coord import HeatPumpCoordinator, HpInputs
    hp = HeatPumpCoordinator(HpConfig())
    d = hp.step(T0, HpInputs(outdoor=5.0, top=40.0, hp_running=False, hp_state="standby", hp_power_w=138.0))
    assert d.details["hp_running"] is False and d.details["hp_state"] == "standby" and d.details["hp_power_w"] == 138.0
    js = (BASE / "www" / "hc-overview.js").read_text()
    assert "const hpOn = hp && hpState(hp.decision?.details || {}) === \"heating\"" in js


# --- 1. the heat pump's target --------------------------------------------------------------------------------------
def _coord(rep, sent):
    from hc_thermostat.hp_coord_coordinator import HpCoordCoordinator
    fake = SimpleNamespace(conf={"hp_target_entity": "number.hp"}, _mismatch_since=None,
                           out_target=SimpleNamespace(reported=lambda: rep, sent=sent))
    return HpCoordCoordinator, fake


def test_target_check_matches_and_mismatch_after_ten_minutes():
    cls, fake = _coord(45.0, 45.0)
    d = SimpleNamespace(raw=44.8, target=45.0, details={})
    cls._target_check(fake, T0, d, True)
    tc = d.details["target_check"]
    assert tc == {"raw": 44.8, "given": 45.0, "sent": 45.0, "reported": 45.0, "diff": 0.0, "writing": True,
                  "mismatch": False, "mismatch_min": None, "restore": None}
    fake.out_target = SimpleNamespace(reported=lambda: 39.0, sent=45.0)  # the Tuya kept its own 39 °C
    cls._target_check(fake, at(1), d, True)
    assert d.details["target_check"]["diff"] == -6.0 and d.details["target_check"]["mismatch"] is False
    cls._target_check(fake, at(11), d, True)
    assert d.details["target_check"]["mismatch"] is True and d.details["target_check"]["mismatch_min"] == 10


def test_target_check_in_shadow_never_mismatches_and_no_output_no_check():
    cls, fake = _coord(39.0, None)
    d = SimpleNamespace(raw=44.8, target=45.0, details={})
    for m in (0, 30):
        cls._target_check(fake, at(m), d, False)
    tc = d.details["target_check"]
    assert tc["writing"] is False and tc["mismatch"] is False and tc["sent"] is None and tc["diff"] == -6.0
    fake.conf = {}
    d2 = SimpleNamespace(raw=44.8, target=45.0, details={})
    cls._target_check(fake, T0, d2, True)
    assert "target_check" not in d2.details


def test_rounding_within_tolerance():
    cls, fake = _coord(45.0, 44.7)
    d = SimpleNamespace(raw=44.7, target=44.7, details={})
    cls._target_check(fake, T0, d, True)
    cls._target_check(fake, at(20), d, True)
    assert d.details["target_check"]["mismatch"] is False


# --- form, texts, panel -----------------------------------------------------------------------------------------------
def test_form_texts_repairs_and_panel():
    from hc_thermostat import config_flow as cf
    keys = {str(k) for k in cf._circuit_settings({}, "floor")}
    assert {"circuit_watch", "circuit_watch_pump_s", "circuit_watch_flow_s", "circuit_watch_flow_c"} <= keys
    assert "hp_standby_w" in cf.HPC_SECTIONS["running"]
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        issue = tr["issues"]["circuit_problem"]
        assert "{name}" in issue["title"] and {"{problem}", "{since}"} <= {p for p in ("{problem}", "{since}") if p in issue["description"]}
        for top in ("config", "options"):
            st = tr[top]["step"]["circuit_settings"]
            for k in ("circuit_watch", "circuit_watch_pump_s", "circuit_watch_flow_s", "circuit_watch_flow_c"):
                assert st["data"][k] and st["data_description"][k]
            assert tr[top]["step"]["hp_coord_settings"]["data"]["hp_standby_w"]
    ov = (BASE / "www" / "hc-overview.js").read_text()
    for s in ("hpTargetSvg", "watchSt", "hpStS", "tgtMis"):
        assert s in ov
    panel = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "Kör felügyelete" in panel and "Egyezés a kérttel" in panel

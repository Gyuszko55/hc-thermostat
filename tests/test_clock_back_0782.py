"""0.78.2 (security review M5): a wall clock that jumps back never holds a relay ON, and a report from the future is
no fresh reading."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

clock = importlib.import_module("hc_thermostat.core.clock")
pwm_mod = importlib.import_module("hc_thermostat.core.pwm")
curve = importlib.import_module("hc_thermostat.core.curve")
model = importlib.import_module("hc_thermostat.core.model")
inputs = importlib.import_module("hc_thermostat.core.inputs")
central = importlib.import_module("hc_thermostat.core.central")
hp = importlib.import_module("hc_thermostat.core.hp_coord")

T0 = datetime(2026, 11, 20, 23, 0, tzinfo=timezone.utc)
BACK = T0 - timedelta(hours=2)  # NTP corrected a clock that ran 2 hours ahead


def test_rebase():
    assert clock.rebase(T0, None, True, 300) is None
    assert clock.rebase(T0, BACK, True, 300) == BACK  # in the past: unchanged
    assert clock.rebase(BACK, T0, True, 300) == BACK - timedelta(seconds=300)  # ON: its minimum run is over
    assert clock.rebase(BACK, T0, False, 300) == BACK  # OFF: the minimum pause starts again now


def test_pwm_on_stops_after_a_clock_jump_back():
    cfg = model.HcConfig(cycle_s=1800, min_on_s=300, min_off_s=300)
    p = pwm_mod.Pwm(cfg)
    p.step(T0, 0.5)
    assert p.output is True
    out, why = p.step(BACK, 0.0)  # demand gone, clock 2 h back
    assert out is False and why is None
    # with a demand the jump does not make a full ON either: a new cycle from now
    p2 = pwm_mod.Pwm(cfg)
    p2.step(T0, 0.3)
    p2.step(T0 + timedelta(seconds=700), 0.3)  # 30 % of 30 min = 9 min: off again
    assert p2.output is False
    out, why = p2.step(BACK, 0.0)
    assert out is False and p2.cycle_start == BACK


def test_run_gate_central_and_heat_pump():
    g = curve.RunGate()
    g.step(T0, True, 600, 600)
    assert g.step(BACK, False, 600, 600) == (False, None)
    hpc = hp.HeatPumpCoordinator(hp.HpConfig())
    hpc.enable, hpc.last_change = True, T0
    assert hpc._switch(BACK, False, False) is None and hpc.enable is False
    hpc.enable, hpc.last_change = False, T0
    assert hpc._switch(BACK, True, False) == "min_off"  # an OFF keeps its pause from now
    assert hpc._switch(BACK + timedelta(seconds=hpc.cfg.hp_min_off_s), True, False) is None
    b = central.CentralBoiler(central.CentralConfig(central_valve_open_s=0))
    b.output, b.last_change = True, T0
    d = b.step(BACK, [], uptime_s=3600)
    assert d.output is False and d.reason != "min_on"


def test_a_report_from_the_future_is_stale():
    sample = SimpleNamespace(state="21.0", attributes={"unit_of_measurement": "°C"}, last_reported=T0, seen=None)
    view = SimpleNamespace(get=lambda e: sample)
    r = inputs.reading(view, "sensor.t", BACK)
    assert r.value == 21.0 and r.age_s == clock.UNKNOWN_AGE_S and r.fresh(900) is None
    r = inputs.reading(view, "sensor.t", T0 - timedelta(seconds=30))  # within the tolerance: fresh
    assert r.age_s == 0.0

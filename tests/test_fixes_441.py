"""0.44.1: integral fixes after the Smart Thermostat 2026.11.0 review (its #305, #324, #326).

- PID: a saturated output freezes the integral instead of cutting it back to 0 (a large target step wiped a learned
  positive integral, an overshoot a negative one that cancels a too generous feed-forward).
- Air conditioner: a pause in regulation (window, switched off, ...) is not integrated in one step on resume.
- Weather curve: no integration towards a flow limit it already sits at, nor further down while there is no demand.
"""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
ac_mod = importlib.import_module("core.ac")
model = importlib.import_module("core.model")
sup_mod = importlib.import_module("core.supervisor")
from core.curve import CurveRegulator  # noqa: E402
from core.regulators import PidRegulator  # noqa: E402

T0 = datetime(2026, 11, 12, 4, 0, tzinfo=timezone.utc)
CIRKO = dict(pid_kp=0.5, pid_ki_per_hour=0.2, pid_kd=0.0, pid_ke=0.01)


def test_pid_keeps_a_positive_integral_through_a_large_target_step():
    reg = PidRegulator(model.HcConfig(**CIRKO))
    reg.integral = 0.08
    reg.update(18.0, 18.0, 5.0, T0, 0.3)
    for k in range(1, 61):  # 30 minutes far below the new target: P alone saturates the output
        out = reg.update(22.5, 18.0 + k * 0.01, 5.0, T0 + timedelta(seconds=30 * k), 0.3)
        assert out == 1.0
    assert abs(reg.integral - 0.08) < 1e-9  # frozen, not wiped (before 0.44.1: 0.0)


def test_pid_keeps_a_negative_integral_through_an_overshoot():
    reg = PidRegulator(model.HcConfig(**CIRKO))
    reg.integral = -0.05  # cancels a feed-forward that asks too much
    reg.update(22.5, 22.5, 5.0, T0, 0.3)
    out = reg.update(20.0, 22.6, 5.0, T0 + timedelta(seconds=30), 0.3)  # the night step: far above the target
    assert out == 0.0
    assert abs(reg.integral - (-0.05)) < 1e-9  # before 0.44.1: 0.0


def test_pid_integral_unwinds_at_once_when_the_error_turns():
    reg = PidRegulator(model.HcConfig(**CIRKO))
    reg.integral = 0.6
    reg.update(21.0, 21.0, 5.0, T0, 0.6)  # base 0.6 + I 0.6: saturated high
    reg.update(21.0, 21.4, 5.0, T0 + timedelta(seconds=30), 0.6)  # too warm: the integral may go down
    assert reg.integral < 0.6


def test_pid_integral_stays_within_the_output_range():
    reg = PidRegulator(model.HcConfig(pid_kp=0.0, pid_ki=0.01, pid_kd=0.0, pid_ke=0.0))
    reg.integral = 0.99
    reg.update(21.0, 21.0, None, T0, -0.5)  # a negative feed-forward keeps the total in range
    reg.update(21.0, 11.0, None, T0 + timedelta(seconds=30), -0.5)
    assert reg.integral <= 1.0


def test_ac_does_not_integrate_a_pause_on_resume():
    c = ac_mod.AcController(0.5)
    c.step(T0, "heat", 21.0, 21.0, 21.0)
    c.hold(T0 + timedelta(minutes=60))  # the window was open for an hour
    c.step(T0 + timedelta(minutes=60, seconds=30), "heat", 21.0, 19.0, 19.0)
    assert abs(c.integral) < 0.02  # one 30 s step: 0.5 × 2 × 30 / 3600 ≈ 0.008 (before 0.44.1: ≈ 1.02)


def test_ac_long_gap_without_hold_is_not_integrated():
    c = ac_mod.AcController(0.5)
    c.step(T0, "heat", 21.0, 21.0, 21.0)
    c.step(T0 + timedelta(minutes=61), "heat", 21.0, 19.0, 19.0)  # e.g. Home Assistant was busy
    assert c.integral == 0.0


def test_supervisor_holds_the_ac_while_the_window_is_open():
    cfg = model.HcConfig(control="ac", target_home=21.0, target_night=21.0, season_enabled=False, window_delay_s=0.0)
    sup = sup_mod.Supervisor(cfg)

    def inp(now, room, window):
        return model.Inputs(now=now, indoor=model.Reading(room, 0), outdoor=model.Reading(5.0, 0), outdoor_avg=5.0,
                            unit_temp=room, unit_step=1.0, unit_min=16.0, unit_max=30.0, window_open=window)

    sup.step(inp(T0, 21.0, False))
    t = T0
    for _ in range(120):  # one hour with the window open
        t += timedelta(seconds=30)
        d = sup.step(inp(t, 19.0, True))
    assert d.reason != model.Reason.AC_HEAT
    before = sup.ac.integral
    sup.step(inp(t + timedelta(seconds=30), 19.0, False))
    assert abs(sup.ac.integral - before) < 0.02


def _curve_cfg(**kw):
    return model.HcConfig(control="curve", curve_slope=1.0, curve_shift=0.0, room_kp=2.0, room_ki_per_hour=1.0,
                          room_integral_limit=10.0, flow_min=25.0, flow_max=45.0, **kw)


def test_curve_integral_does_not_wind_up_at_the_flow_maximum():
    cfg = _curve_cfg()
    reg = CurveRegulator(cfg)
    t = T0
    for _ in range(6 * 120):  # six hours far below the target, the flow pinned at flow_max
        t += timedelta(seconds=30)
        assert reg.update(22.0, 15.0, -10.0, t) == cfg.flow_max
    assert reg.integral == 0.0  # before 0.44.1: +10 (the limit)


def test_curve_integral_does_not_wind_down_without_demand():
    cfg = _curve_cfg()
    reg = CurveRegulator(cfg)
    t = T0
    for _ in range(6 * 120):  # six hours well above the target: no demand at all
        t += timedelta(seconds=30)
        assert reg.update(21.0, 23.0, 10.0, t) is None
    assert reg.integral == 0.0  # before 0.44.1: −10


def test_curve_integral_still_corrects_inside_the_range():
    reg = CurveRegulator(_curve_cfg())
    t = T0
    for _ in range(120):
        t += timedelta(seconds=30)
        reg.update(21.0, 20.8, 5.0, t)  # flow ≈ 37 °C: inside the range
    assert 0.15 < reg.integral < 0.25  # 1 °C/°C/h × 0.2 °C × 1 h


def test_version():
    assert json.loads((ROOT / "manifest.json").read_text())["version"] in ("0.44.1", "0.44.2", "0.44.3", "0.44.4", "0.44.5", "0.45.0", "0.46.0", "0.47.0", "0.48.0", "0.48.1", "0.48.2", "0.48.3", "0.49.0")

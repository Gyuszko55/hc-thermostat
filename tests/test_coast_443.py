"""0.44.3: coasting after a burn (11-12 morning, Cirkó HC).

7:47–7:59 a 12-min burn at 22.0 °C (target 22.5); the room kept rising to 22.4 by 8:17, when the next 30-min cycle
started a 7-min burn at 22 % demand – the room peaked at 22.8. With coasting the second burn waits while the room
is just under the target and still rising, and the integral does not grow meanwhile.
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.messages import explain
from core.model import HcConfig, Inputs, Presence, Reading
from core.supervisor import Supervisor

LOCAL = timezone(timedelta(hours=1))
T0 = datetime(2026, 11, 12, 7, 59, tzinfo=LOCAL)  # the first burn ended
CFG = HcConfig(control="pid", pid_kp=0.5, pid_ki_per_hour=0.2, target_home=22.5, night_start="00:00",
               night_end="00:00", cycle_s=1800, min_on_s=300, min_off_s=300, season_enabled=False,
               boost_enabled=False, learning_enabled=False, coast_window_s=2700.0)  # 0.47.0: opt-in


def _sup(integral=0.0):
    sup = Supervisor(CFG)
    sup.regulator.integral = integral
    sup.pwm.output, sup.pwm.last_change, sup.pwm.cycle_start = False, T0, T0 - timedelta(minutes=12)
    return sup


def _run(sup, readings, start=T0):
    """readings: (minutes after T0, room °C) – the sensor keeps its last value in between, one step per 30 s."""
    out, d = [], None
    for k in range(int(readings[-1][0] * 2) + 1):
        m = k / 2
        room = [v for t, v in readings if t <= m][-1]
        d = sup.step(Inputs(now=start + timedelta(minutes=m), indoor=Reading(room), outdoor=Reading(5.8),
                            presence=Presence.HOME))
        out.append((m, d))
    return out


MORNING = [(0, 22.0), (3, 22.1), (7, 22.2), (12, 22.3), (16, 22.4), (27, 22.5), (32, 22.6)]


def test_the_11_12_second_burn_waits_while_the_room_rises():
    sup = _sup()
    steps = _run(sup, MORNING)
    at_new_cycle = [d for m, d in steps if 18 <= m <= 26]  # 8:17–8:25: the next cycle began, room 22.4 and rising
    assert at_new_cycle and not any(d.output for d in at_new_cycle)
    assert any(d.limited_by == "coast" for d in at_new_cycle)
    assert not any(d.output for m, d in steps if m >= 15)  # nor at the target while still rising (22.5, 22.6)
    assert "Utánfűtés" in explain(next(d for d in at_new_cycle if d.limited_by == "coast"), "hu")


def test_the_integral_does_not_grow_while_coasting():
    sup = _sup()
    seen = []
    for m, d in _run(sup, MORNING):
        if d.limited_by == "coast":
            seen.append(sup.regulator.integral)
    assert len(seen) > 5 and max(seen) - min(seen) < 1e-9


def test_without_coasting_it_burned_again():
    sup = Supervisor(HcConfig(**{**CFG.__dict__, "coast_window_s": 0.0}))
    sup.pwm.output, sup.pwm.last_change, sup.pwm.cycle_start = False, T0, T0 - timedelta(minutes=12)
    steps = _run(sup, MORNING)
    assert any(d.output for m, d in steps if 18 <= m <= 26)


def test_a_flat_room_under_the_target_still_gets_heat():
    sup = _sup()
    steps = _run(sup, [(0, 22.3), (40, 22.3)])
    assert any(d.output for m, d in steps)


def test_a_large_demand_is_not_held_back():
    sup = _sup(integral=0.3)  # ~50 %: a real need
    steps = _run(sup, MORNING)
    assert any(d.output for m, d in steps if m <= 26)


def test_far_under_the_target_is_not_held_back():
    sup = _sup(integral=0.0)
    steps = _run(sup, [(0, 21.6), (5, 21.7), (10, 21.8), (15, 21.9), (30, 21.9)])
    assert not any(d.limited_by == "coast" for m, d in steps)  # 0.6 °C under: outside the band


def test_coasting_ends_after_the_window():
    sup = _sup()
    steps = _run(sup, [(0, 22.0), (10, 22.2), (20, 22.3), (30, 22.4), (40, 22.4), (60, 22.4)])
    assert not any(d.limited_by == "coast" for m, d in steps if m > 45)  # 45 min after the burn: a normal start


def test_version():
    root = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
    assert json.loads((root / "manifest.json").read_text())["version"] in ("0.44.3", "0.44.4", "0.44.5", "0.45.0", "0.46.0", "0.47.0", "0.48.0", "0.48.1", "0.48.2", "0.48.3")

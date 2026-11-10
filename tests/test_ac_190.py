"""0.19.0: air conditioner by the room thermometer (virtual i-Feel)."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))
ac_mod = importlib.import_module("core.ac")
model = importlib.import_module("core.model")
sup_mod = importlib.import_module("core.supervisor")
messages = importlib.import_module("core.messages")

T0 = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


class Terrace:
    """Room heated (or cooled) by an inverter unit that modulates on (setpoint − own reading)."""

    def __init__(self, room=18.0, outdoor=5.0, bias=-2.5, p_max_delta=30.0, tau_s=4 * 3600.0):
        self.room, self.outdoor, self.bias, self.p_max_delta, self.tau = room, outdoor, bias, p_max_delta, tau_s

    @property
    def unit(self) -> float:
        return round(self.room + self.bias)  # the unit reports whole degrees

    def advance(self, mode, setpoint, dt=30.0):
        power = 0.0
        if mode == "heat" and setpoint is not None:
            power = max(0.0, min(1.0, (setpoint - (self.room + self.bias)) / 1.5))
        if mode == "cool" and setpoint is not None:
            power = -max(0.0, min(1.0, ((self.room + self.bias) - setpoint) / 1.5))
        eq = self.outdoor + power * self.p_max_delta
        self.room += (eq - self.room) * dt / self.tau


def _run(target, hours, compensate=True, room=18.0, mode="heat", outdoor=5.0):
    c = ac_mod.AcController()
    t = Terrace(room=room, outdoor=outdoor)
    temps, changes, last, pauses = [], 0, None, 0
    for k in range(int(hours * 120)):
        now = T0 + timedelta(seconds=30 * k)
        cmd = c.step(now, mode, target, t.room, t.unit) if compensate else ac_mod.AcCommand(mode, target)
        if cmd.setpoint != last:
            changes, last = changes + 1, cmd.setpoint
        pauses += cmd.paused
        t.advance(cmd.mode, cmd.setpoint)
        temps.append(t.room)
    return temps, changes, pauses, c


def test_plain_setpoint_overheats_by_the_sensor_bias_compensated_holds_the_target():
    plain, _, _, _ = _run(20.0, 12, compensate=False)
    comp, changes, _, c = _run(20.0, 12)
    last4 = comp[-480:]
    assert sum(plain[-480:]) / 480 > 21.5  # the unit reads 2.5 °C low: holding its own 20 overheats the room
    assert abs(sum(last4) / 480 - 20.0) < 0.4
    assert changes < 30  # at most one change per 10 minutes, mostly far fewer
    assert c.offset is not None and -3.0 < c.offset < -2.0


def test_pause_at_the_unit_minimum_and_resume():
    # A warm afternoon: even 16 °C on the unit keeps the terrace above an 18 °C night target.
    temps, _, pauses, c = _run(18.0, 6, room=19.5, outdoor=14.0)
    assert pauses > 0


def test_cooling_compensates_too():
    temps, _, _, _ = _run(26.0, 12, room=29.0, mode="cool", outdoor=33.0)
    assert abs(sum(temps[-480:]) / 480 - 26.0) < 0.5


def test_rate_limit_and_new_target_at_once():
    c = ac_mod.AcController(min_change_s=600)
    a = c.step(T0, "heat", 20.0, 18.0, 15.0)
    b = c.step(T0 + timedelta(seconds=30), "heat", 20.0, 18.0, 17.0)  # offset moved: not yet due
    assert b.setpoint == a.setpoint
    d = c.step(T0 + timedelta(seconds=60), "heat", 22.0, 18.0, 17.0)  # new target: at once
    assert d.setpoint != a.setpoint


def test_supervisor_ac_heat_cool_and_off():
    cfg = model.HcConfig(control="ac", target_home=19.0, target_night=19.0, target_cool=26.0, season_enabled=True)
    sup = sup_mod.Supervisor(cfg)
    inp = lambda now, room, avg: model.Inputs(now=now, indoor=model.Reading(room, 0), outdoor=model.Reading(5.0, 0),
                                               outdoor_avg=avg, unit_temp=room - 2.5, unit_step=1.0, unit_min=16.0, unit_max=30.0)
    d = sup.step(inp(T0, 18.0, 5.0))
    assert d.reason == model.Reason.AC_HEAT and d.external.hvac == "heat" and d.external.target <= 17.0  # 19 − 2.5, rounded
    assert "Klíma fűt" in messages.explain(d, "hu")
    sup2 = sup_mod.Supervisor(cfg)
    d2 = sup2.step(inp(T0, 28.0, 22.0))  # summer: season off, terrace hot
    assert d2.reason == model.Reason.AC_COOL and d2.external.hvac == "cool"
    sup3 = sup_mod.Supervisor(cfg)
    d3 = sup3.step(inp(T0, 22.0, 22.0))  # summer, comfortable: off
    assert d3.external.hvac == "off"


def test_warm_room_is_not_kept_heating_by_a_rounded_setpoint():
    """11-09 live: the terrace at 19.5 °C (target 19) while the unit was set to 20 – round towards the need."""
    c = ac_mod.AcController()
    c.integral, c.offset, c.sent, c.mode, c.target = 0.9, -0.5, 20.0, "heat", 19.0
    c.changed, c._last = T0 - timedelta(minutes=20), T0 - timedelta(seconds=30)
    cmd = c.step(T0, "heat", 19.0, 19.5, 19.0)  # raw ≈ 19.4: plain rounding keeps 20 or 19 with hysteresis
    assert cmd.setpoint == 19.0


def test_slow_terrace_overshoot_and_bias_stay_small():
    c = ac_mod.AcController()
    t = Terrace(room=18.0, outdoor=5.0, tau_s=8 * 3600.0, p_max_delta=20.0)
    temps = []
    for k in range(12 * 120):
        now = T0 + timedelta(seconds=30 * k)
        cmd = c.step(now, "heat", 19.0, t.room, t.unit)
        t.advance(cmd.mode, cmd.setpoint)
        temps.append(t.room)
    assert max(temps) < 19.3 and abs(sum(temps[-480:]) / 480 - 19.0) < 0.15

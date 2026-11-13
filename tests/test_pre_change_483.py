"""0.48.3: no new start just before a scheduled lowering of the target (11-12 evening, Cirkó HC).

21:59:41 a burn started at 22.4 °C (target 22.5, demand 19 %); at 22:00 the night target of 21 °C came, the burn ran
its 5-min minimum and the room went to 22.6 – one start more than needed. Now: within `pre_change_s` of a lowering
change no new start while the room is already at or above the coming target.
"""

from datetime import datetime, timedelta, timezone

from core.messages import explain
from core.model import HcConfig, Inputs, Presence, Reading
from core.supervisor import Supervisor

LOCAL = timezone(timedelta(hours=1))
CFG = HcConfig(control="pid", pid_kp=0.5, pid_ki_per_hour=0.2, target_home=22.5, target_night=21.0,
               night_start="22:00", night_end="06:00", cycle_s=1800, min_on_s=300, min_off_s=300,
               season_enabled=False, boost_enabled=False, learning_enabled=False)


def _sup(cfg=CFG, integral=0.25):
    sup = Supervisor(cfg)
    sup.regulator.integral = integral
    return sup


def _run(sup, start, minutes, room, step_s=30):
    out = []
    for k in range(int(minutes * 60 / step_s) + 1):
        now = start + timedelta(seconds=k * step_s)
        t = room(k * step_s / 60) if callable(room) else room
        out.append((now, sup.step(Inputs(now=now, indoor=Reading(t), outdoor=Reading(9.0), presence=Presence.HOME))))
    return out


EVENING = datetime(2026, 11, 12, 21, 35, tzinfo=LOCAL)
TEN = datetime(2026, 11, 12, 22, 0, tzinfo=LOCAL)


def test_the_11_12_evening_burn_does_not_start():
    steps = _run(_sup(), EVENING, 30, 22.4)
    before = [d for now, d in steps if now < TEN]
    held = [d for now, d in steps if TEN - timedelta(minutes=30) <= now < TEN]
    assert not any(d.output for d in before)
    assert held and all(d.limited_by == "pre_change" for d in held)
    text = explain(held[-1], "hu")
    assert "22:00-kor a cél 21" in text and "nem indítok új égést" in text
    assert "At 22:00 the target goes down" in explain(held[-1], "en")


def test_without_the_hold_it_burned_before_ten():
    sup = _sup(HcConfig(**{**CFG.__dict__, "pre_change_s": 0.0}))
    steps = _run(sup, EVENING, 30, 22.4)
    assert any(d.output for now, d in steps if now < TEN)


def test_the_integral_does_not_grow_while_held():
    sup = _sup()
    seen = []
    for now, d in _run(sup, EVENING, 24, 22.4):
        if d.limited_by == "pre_change":
            seen.append(sup.regulator.integral)
    assert len(seen) > 5 and max(seen) - min(seen) < 1e-9


def test_outside_the_window_it_heats_as_usual():
    steps = _run(_sup(), datetime(2026, 11, 12, 20, 0, tzinfo=LOCAL), 30, 22.4)
    assert any(d.output for now, d in steps)


def test_a_room_colder_than_the_coming_target_still_gets_heat():
    steps = _run(_sup(), EVENING, 24, 20.6)
    assert any(d.output for now, d in steps if now < TEN)
    assert not any(d.limited_by == "pre_change" for now, d in steps)


def test_no_hold_before_the_morning_raise():
    steps = _run(_sup(), datetime(2026, 11, 13, 5, 35, tzinfo=LOCAL), 24, 20.9)
    assert any(d.output for now, d in steps)
    assert not any(d.limited_by == "pre_change" for now, d in steps)


def test_a_running_burn_is_not_cut():
    sup = _sup()
    start = datetime(2026, 11, 12, 21, 50, tzinfo=LOCAL)
    sup.pwm.output, sup.pwm.last_change, sup.pwm.cycle_start = True, start - timedelta(minutes=1), start - timedelta(minutes=1)
    steps = _run(sup, start, 3, 22.4)
    assert all(d.output for now, d in steps)


def test_a_manual_target_ending_at_ten_holds_too():
    sup = _sup()
    sup.manual_target = 23.0  # set by hand earlier in the evening: it lasts until 22:00
    steps = _run(sup, EVENING, 20, 22.6)
    assert any(d.limited_by == "pre_change" for now, d in steps)
    assert not any(d.output for now, d in steps)


def test_onoff_waits_too():
    cfg = HcConfig(control="onoff", target_home=22.5, target_night=21.0, night_start="22:00", night_end="06:00",
                   onoff_hysteresis=0.3, min_on_s=600, min_off_s=600, season_enabled=False, boost_enabled=False,
                   learning_enabled=False)
    steps = _run(Supervisor(cfg), EVENING, 24, 22.1)
    assert not any(d.output for now, d in steps)
    assert any(d.limited_by == "pre_change" for now, d in steps)
    off = HcConfig(**{**cfg.__dict__, "pre_change_s": 0.0})
    assert any(d.output for now, d in _run(Supervisor(off), EVENING, 24, 22.1))


def test_no_boost_starts_before_the_lowering():
    cfg = HcConfig(**{**CFG.__dict__, "boost_enabled": True, "boost_min_deficit": 0.8})
    sup = _sup(cfg)
    _run(sup, datetime(2026, 11, 12, 21, 30, tzinfo=LOCAL), 2, 22.4)  # arm the boost
    steps = _run(sup, EVENING, 20, 21.5)  # 1 °C under 22.5, but above the coming 21
    assert not any(d.output for now, d in steps)

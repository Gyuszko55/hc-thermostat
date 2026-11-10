"""Summer valve exercise of a zone's own actuator (0.14.0)."""

from datetime import datetime, timedelta, timezone

from core.exercise import ValveExercise
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

MONDAY = datetime(2026, 7, 6, 9, 0, tzinfo=timezone.utc)  # a summer Monday
CFG = HcConfig(valve_exercise=True, season_enabled=False, night_start="00:00", night_end="00:00",
               target_home=21.0, restart_grace_s=0)


def run(cfg, start, minutes, indoor=26.0, step_s=30):
    sup, out, now = Supervisor(cfg), [], start
    for _ in range(int(minutes * 60 / step_s)):
        out.append(sup.step(Inputs(now=now, indoor=Reading(indoor), outdoor=Reading(25.0))))
        now += timedelta(seconds=step_s)
    return sup, out


def test_opens_once_for_ten_minutes_on_the_day():
    sup, decisions = run(CFG, MONDAY, 120)  # 09:00 – 11:00
    on = [d for d in decisions if d.output]
    assert on and all(d.reason == Reason.VALVE_EXERCISE for d in on)
    assert on[0].now == MONDAY.replace(hour=10)
    assert len(on) * 30 == 600  # exactly exercise_s
    assert on[0].demand == 0.0
    assert "Szelepmozgatás" in explain(on[0], "hu") and "10:10" in explain(on[0], "hu")


def test_not_on_another_day_or_when_disabled():
    _, decisions = run(CFG, MONDAY + timedelta(days=1), 120)
    assert not any(d.output for d in decisions)
    _, decisions = run(HcConfig(**{**CFG.__dict__, "valve_exercise": False}), MONDAY, 120)
    assert not any(d.output for d in decisions)


def test_a_valve_open_recently_is_not_exercised():
    ex = ValveExercise(CFG)
    ex.step(MONDAY - timedelta(days=3), Reason.REGULATING, True)  # it heated three days ago
    at_ten = MONDAY.replace(hour=10)
    assert ex.step(at_ten, Reason.AT_TARGET, False) is False
    assert ex.next_run(at_ten) == at_ten + timedelta(days=7)


def test_never_when_switched_off_window_or_sensor_lost():
    ex = ValveExercise(CFG)
    at_ten = MONDAY.replace(hour=10)
    for reason in (Reason.DISABLED, Reason.WINDOW, Reason.SENSOR_LOST, Reason.RESTART_HOLD):
        assert ex.step(at_ten, reason, False) is False


def test_external_control_does_not_exercise():
    _, decisions = run(HcConfig(**{**CFG.__dict__, "control": "external"}), MONDAY, 120)
    assert not any(d.reason == Reason.VALVE_EXERCISE for d in decisions)


def test_weekday_from_the_options_may_be_text_and_state_survives_a_restart():
    cfg = HcConfig(**{**CFG.__dict__, "exercise_weekday": "1"})  # Tuesday, as the select sends it
    _, decisions = run(cfg, MONDAY + timedelta(days=1), 120)
    assert any(d.reason == Reason.VALVE_EXERCISE for d in decisions)
    sup, _ = run(CFG, MONDAY, 120)
    again = Supervisor(CFG)
    again.restore(sup.state())
    assert again.exercise.last_open is not None
    assert again.exercise.next_run(MONDAY.replace(hour=11)).date() == (MONDAY + timedelta(days=7)).date()


def test_runs_every_week_not_every_other_week():
    ex = ValveExercise(CFG)
    for week in range(3):
        start = MONDAY.replace(hour=10) + timedelta(days=7 * week)
        assert ex.step(start, Reason.SEASON_OFF, False) is True, week
        assert ex.step(start + timedelta(seconds=600), Reason.SEASON_OFF, False) is False

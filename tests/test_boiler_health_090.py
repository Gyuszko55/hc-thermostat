"""0.9.0: boiler health from the relay and the power draw."""

from datetime import datetime, timedelta, timezone

from core.boiler_health import BoilerHealth
from core.model import HcConfig

T0 = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)
CFG = HcConfig()


def _run(health, steps, fault=False):
    """steps: (minutes, relay_on, power W) – held until the next step; checked every 30 s."""
    states = []
    end = steps[-1][0]
    current = steps[0]
    idx = 0
    half = 0
    while half / 2 <= end:
        minute = half / 2
        while idx + 1 < len(steps) and steps[idx + 1][0] <= minute:
            idx += 1
            current = steps[idx]
        states.append((minute, health.update(T0 + timedelta(minutes=minute), current[1], current[2], None, fault)))
        half += 1
    return states


def _final(states):
    return states[-1][1]


def test_a_normal_burn_is_ok():
    # relay on, pump first for 1 min, burns 25 min, off
    states = _run(BoilerHealth(CFG), [(0, True, 108), (1, True, 120), (26, False, 109), (28, False, 6), (40, False, 6)])
    assert all(s == "ok" for _, s in states)


def test_own_flame_pause_in_a_long_burn_is_ok():
    states = _run(BoilerHealth(CFG), [(0, True, 120), (20, True, 108), (24, True, 120), (40, True, 120)])
    assert all(s == "ok" for _, s in states)


def test_no_response_when_relay_on_but_no_power():
    states = _run(BoilerHealth(CFG), [(0, True, 6), (5, True, 6)])
    assert dict(states)[2.5] == "ok" and dict(states)[3.0] == "no_response"


def test_no_flame_when_only_the_pump_runs():
    health = BoilerHealth(CFG)
    states = _run(health, [(0, True, 108), (6, True, 108)])
    assert dict(states)[4.5] == "ok" and dict(states)[5.0] == "no_flame"
    assert health.problem


def test_flame_lost_during_a_burn():
    states = _run(BoilerHealth(CFG), [(0, True, 120), (10, True, 108), (30, True, 108)])
    assert dict(states)[24.5] == "ok" and dict(states)[25.0] == "no_flame"


def test_short_cycling():
    steps = []
    for i in range(10):  # 10 starts in 50 minutes
        steps += [(i * 5, True, 120), (i * 5 + 2, False, 6)]
    steps.append((52, False, 6))
    assert _final(_run(BoilerHealth(CFG), steps)) == "short_cycling"


def test_heating_fault_is_passed_on():
    assert _final(_run(BoilerHealth(CFG), [(0, True, 120), (5, True, 120)], fault=True)) == "heating_fault"


def test_no_data_after_ten_minutes():
    states = _run(BoilerHealth(CFG), [(0, False, None), (11, False, None)])
    assert dict(states)[9.5] == "ok" and dict(states)[10.0] == "no_data"


def test_ignition_time_and_burn_length_are_measured():
    health = BoilerHealth(CFG)
    _run(health, [(0, True, 108), (1.5, True, 120), (21.5, False, 6), (25, False, 6)])
    attrs = health.attributes()
    assert attrs["last_ignition_s"] == 90 and attrs["average_burn_min"] == 20.0 and attrs["starts_last_hour"] == 1


def test_recovers_to_ok():
    states = _run(BoilerHealth(CFG), [(0, True, 108), (6, True, 120), (10, True, 120)])
    assert dict(states)[5.0] == "no_flame" and _final(states) == "ok"

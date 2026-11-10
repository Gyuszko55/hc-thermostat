"""0.8.0: an open window recognised from a fast temperature drop."""

from datetime import datetime, timedelta, timezone

from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor
from core.window_drop import DropDetector

T0 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)
CFG = HcConfig(target_home=22.0, night_start="00:00", night_end="00:00", season_enabled=False)


def _feed(det, points):
    """points: (minutes, value) – the sensor reports only these; the supervisor asks every 30 s."""
    out = []
    values = dict(points)
    current = None
    for half in range(int(max(values) * 2) + 1):
        minute = half / 2
        if minute in values:
            current = values[minute]
        out.append((minute, det.update(T0 + timedelta(minutes=minute), current)))
    return out


def _first_open(results):
    return next((m for m, is_open in results if is_open), None)


def test_airing_is_recognised_within_minutes():
    det = DropDetector(CFG)
    # 22.0 steady, window opens at 20 min; a sensor near it reports 21.8 at 26, 21.5 at 32
    results = _feed(det, [(0, 22.0), (20, 22.0), (26, 21.8), (32, 21.5), (40, 21.4)])
    assert _first_open(results) == 32  # 21.8 → 21.5 between two reports 6 min apart = 3.0 °C/h
    assert det.rate == 3.0


def test_slow_cooling_at_night_is_no_window():
    det = DropDetector(CFG)
    points = [(m, round(22.0 - m * 0.01, 2)) for m in range(0, 120, 10)]  # 0.6 °C per hour
    assert _first_open(_feed(det, points)) is None


def test_small_jitter_is_no_window():
    det = DropDetector(CFG)
    assert _first_open(_feed(det, [(0, 22.0), (5, 21.8), (10, 22.0), (15, 21.8)])) is None


def test_closed_when_it_warms_up_again():
    det = DropDetector(CFG)
    results = _feed(det, [(0, 22.0), (10, 21.5), (20, 21.3), (30, 21.5), (60, 21.6)])
    assert _first_open(results) == 10
    assert dict(results)[30] is False  # 0.2 °C back above the lowest point


def test_closed_when_it_stops_falling_and_waits_before_the_next_one():
    det = DropDetector(CFG)
    results = _feed(det, [(0, 22.0), (10, 21.5), (66, 21.3), (70, 21.0), (110, 20.5)])
    closed_at = next(m for m, is_open in results if m > 10 and not is_open)
    assert closed_at == 25  # 15 minutes without a new low
    reopened = next((m for m, is_open in results if m > 25 and is_open), None)
    assert reopened is not None and reopened >= 55  # 30 minute pause first


def test_never_longer_than_the_maximum():
    det = DropDetector(CFG)
    points = [(0, 22.0)] + [(5 + m, round(21.6 - m * 0.02, 2)) for m in range(0, 60, 5)]
    results = _feed(det, points)
    start = _first_open(results)
    assert start is not None
    assert all(not is_open for m, is_open in results if m >= start + CFG.window_drop_max_min)


def test_supervisor_pauses_and_explains():
    sup = Supervisor(CFG)
    entity = "sensor.bedroom"
    decision = None
    for minute, value in [(0, 22.0), (10, 22.0), (20, 21.4)]:
        decision = sup.step(Inputs(now=T0 + timedelta(minutes=minute), indoor=Reading(21.5), outdoor=Reading(2.0),
                                   drop_temps=((entity, Reading(value)),)))
    assert decision.reason == Reason.WINDOW and decision.output is False
    assert decision.details["window_source"] == "drop" and decision.details["drop_entity"] == entity
    assert "gyors hőesés" in explain(decision, "hu")


def test_no_drop_sensors_changes_nothing():
    sup = Supervisor(CFG)
    decision = sup.step(Inputs(now=T0, indoor=Reading(21.0), outdoor=Reading(2.0)))
    assert decision.reason != Reason.WINDOW


def test_one_step_after_a_long_silence_is_no_window():
    """Seen live on 2026-11-07: the bathroom reported 23.03 at 13:00 and 22.61 at 13:44 (0.6 °C/h)."""
    det = DropDetector(CFG)
    assert _first_open(_feed(det, [(0, 23.03), (44, 22.61), (64, 22.4), (90, 22.2)])) is None

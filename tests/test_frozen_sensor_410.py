"""0.41.0: a room thermometer that keeps repeating one value while the heat runs is treated as lost."""

from datetime import datetime, timedelta, timezone

from core.flatline import FrozenSensor
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False, boost_enabled=False)


def test_detector_needs_both_time_and_heat():
    f = FrozenSensor(HcConfig())
    t = T0
    for _ in range(int(3 * 3600 / 60)):  # 3 h, the same value, heating all the time
        assert not f.step(t, 20.0, True) or (t - T0).total_seconds() >= 3 * 3600
        t += timedelta(minutes=1)
    assert f.step(t, 20.0, True) and f.details(t)["frozen_burn_min"] >= 45
    assert not f.step(t + timedelta(minutes=1), 20.1, True)  # a new value: measuring again


def test_no_heat_no_suspicion():
    f = FrozenSensor(HcConfig())
    t = T0
    for _ in range(6 * 60):  # 6 h unchanged, but the source was off: a still room may well stay at one value
        f.step(t, 21.0, False)
        t += timedelta(minutes=1)
    assert not f.frozen


def test_little_heat_no_suspicion():
    f = FrozenSensor(HcConfig())
    t = T0
    for i in range(5 * 60):  # 5 h unchanged, heating 6 min per hour (30 min in all: below 45)
        f.step(t, 21.0, i % 60 < 6)
        t += timedelta(minutes=1)
    assert not f.frozen


def test_off_and_gaps():
    f = FrozenSensor(HcConfig(frozen_after_h=0))
    assert not f.step(T0, 20.0, True) and not f.step(T0 + timedelta(hours=5), 20.0, True)
    f = FrozenSensor(HcConfig())
    f.step(T0, 20.0, True)
    assert not f.step(T0 + timedelta(hours=4), 20.0, True)  # one 4 h gap (a restart) is not burning time


def test_supervisor_takes_the_lost_sensor_path():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi", "cycle_s": 900, "min_on_s": 300}))
    t, d = T0, None
    for _ in range(int(3.1 * 3600 / 60)):  # a stuck sensor at 19.0 under a 21 °C target: the relay keeps heating
        d = sup.step(Inputs(now=t, indoor=Reading(19.0, 30.0), outdoor=Reading(0.0, 0.0), actual_heating=True))
        t += timedelta(minutes=1)
    assert d.reason == Reason.SENSOR_LOST and d.details.get("indoor_frozen")
    assert d.demand == 0.35  # nothing learned yet: the blind share, not 100 % against a frozen 19 °C
    assert "beragadt" in explain(d, "hu") and "frozen" in explain(d, "en")
    d = sup.step(Inputs(now=t, indoor=Reading(19.1, 30.0), outdoor=Reading(0.0, 0.0), actual_heating=True))
    assert d.reason != Reason.SENSOR_LOST and not d.details.get("indoor_frozen")


def test_external_and_curve_are_not_judged():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "external"}))
    t, d = T0, None
    for _ in range(4 * 60):
        d = sup.step(Inputs(now=t, indoor=Reading(19.0, 30.0), outdoor=Reading(0.0, 0.0), actual_heating=True))
        t += timedelta(minutes=1)
    assert d.reason != Reason.SENSOR_LOST

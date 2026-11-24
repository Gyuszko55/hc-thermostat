"""0.77.3: after a restart a sleeping thermometer's restored value looks fresh but is old (11-19 14:35: 21.6 °C
restored while the room was 22.3 °C – the after-heat watch ended and the boiler burned 6 minutes for nothing)."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from core.matrix import default_timing, source_defaults
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
coord = importlib.import_module("hc_thermostat.coordinator")

T0 = datetime(2026, 11, 19, 13, 35, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(seconds):
    return T0 + timedelta(seconds=seconds)


def sup():
    c = HcConfig.from_mapping({**source_defaults("radiator", "onoff_boiler"),
                               **default_timing("radiator", "onoff_boiler"), **DAY})
    return Supervisor(c)


def step(s, sec, indoor, confirmed):
    return s.step(Inputs(now=at(sec), indoor=Reading(indoor), outdoor=Reading(5.0), uptime_s=sec,
                         indoor_confirmed=confirmed))


def test_default_wait_is_15_minutes():
    assert HcConfig().restart_sensor_wait_s == 900.0


def test_restored_reading_holds_past_the_grace():
    s = sup()
    target = s.cfg.target_home
    d = step(s, 150, target - 0.9, confirmed=False)  # grace (120 s) over, the value still the restored one
    assert d.reason == Reason.RESTART_HOLD and not d.output


def test_confirmed_reading_regulates_after_the_grace():
    s = sup()
    target = s.cfg.target_home
    d = step(s, 150, target - 0.9, confirmed=True)
    assert d.reason != Reason.RESTART_HOLD


def test_cold_house_does_not_wait():
    s = sup()
    target = s.cfg.target_home
    d = step(s, 150, target - 1.5, confirmed=False)
    assert d.reason != Reason.RESTART_HOLD


def test_wait_has_a_cap():
    s = sup()
    target = s.cfg.target_home
    d = step(s, 901, target - 0.9, confirmed=False)
    assert d.reason != Reason.RESTART_HOLD


def test_after_heat_watch_survives_a_restored_lower_value():
    s = sup()
    target = s.cfg.target_home
    # the boost ended 15 minutes before the restart; the watch runs with a peak of target - 0.6
    s._quiet_until, s._quiet_cap = at(300), at(2700)
    s._quiet_peak, s._quiet_level, s._quiet_rise, s._quiet_target = target - 0.6, target - 0.6, at(-600), target
    d = step(s, 150, target - 0.9, confirmed=False)  # restored 0.3 below the peak: not a real fall
    assert d.reason == Reason.RESTART_HOLD and s._quiet_until is not None


# --- the coordinator side: which reading counts as confirmed -------------------------------------------------------
def _st(value, reported):
    return SimpleNamespace(state=str(value), attributes={"unit_of_measurement": "°C"}, last_reported=reported,
                           last_updated=reported)


def _fake(states, started):
    states_ns = SimpleNamespace(get=lambda e: states.get(e))
    # 0.78.0: the confirmation lives in the core (RestartConfirm)
    return SimpleNamespace(hass=SimpleNamespace(states=states_ns), _started=started,
                           _restart_confirm=coord.in_.RestartConfirm(started, HcConfig().restart_sensor_wait_s),  # no settle: the 0.77.3 rule
                           cfg=HcConfig(), conf={coord.CONF_INDOOR: "sensor.a"},
                           leading_spec=lambda: SimpleNamespace(sensors=("sensor.a", "sensor.b")))


def test_coordinator_confirms_on_a_new_report():
    states = {"sensor.a": _st(21.6, T0), "sensor.b": _st(21.7, T0)}
    f = _fake(states, T0)
    check = coord.HcCoordinator._indoor_confirmed
    assert not check(f, at(30))
    assert not check(f, at(90))  # same restored stamps
    states["sensor.b"] = _st(22.3, at(170))  # the H&T woke and reported
    assert check(f, at(180))
    states["sensor.b"] = _st(22.3, at(170))
    assert check(f, at(240))  # stays confirmed


def test_coordinator_ignores_a_missing_sensor_and_caps_the_wait():
    states = {}
    f = _fake(states, T0)
    check = coord.HcCoordinator._indoor_confirmed
    assert not check(f, at(60))
    states["sensor.a"] = _st(21.6, at(70))  # restored late: the first value seen, not a confirmation
    assert not check(f, at(80))
    assert check(f, at(901))  # the wait is over


def test_running_instance_is_confirmed_at_once():
    # an instance loaded while HA runs: its start counts a day back, so it never waits
    f = _fake({"sensor.a": _st(21.6, T0)}, T0 - timedelta(days=1))
    assert coord.HcCoordinator._indoor_confirmed(f, T0)

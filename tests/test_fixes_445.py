"""0.44.5: fixes found in the issues of Versatile Thermostat and SAT (11-12 review).

- TRV head: a late report of our write (or a lost write) was taken for a change by hand (VTherm #2141/#2175).
- A window contact that is gone counted as closed without a word; after a restart an open window waited again
  (VTherm #2052/#2147).
- PWM: a start delayed by the minimum off time lost the delay from its run (VTherm #2194).
- Window by temperature drop: a thermometer that dropped out held the pause without end.
- PID: a stalled update integrated the whole gap in one step (as the AC since 0.44.1).
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from core import trv
from core.model import HcConfig, Inputs, Presence, Reading, Reason
from core.pwm import Pwm
from core.regulators import PidRegulator
from core.supervisor import Supervisor
from core.window_drop import DropDetector

T0 = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"


# --- TRV ------------------------------------------------------------------------------------------------------
def _written(t, head="climate.konyha_trv", old=22.0, new=23.5):
    p = t.plan(head, 22.5, "heat", old, want=new, now=T0)
    assert p.reason == "write"
    t.written(head, p.target, 22.5, T0)


def test_a_late_report_is_not_a_change_by_hand():
    t = trv.TrvTargets()
    _written(t)
    for s in (30, 60, 240):  # the head still shows its old target: our write is on its way
        assert t.plan("climate.konyha_trv", 22.5, "heat", 22.0, want=23.5,
                      now=T0 + timedelta(seconds=s)).reason == "pending"  # before 0.44.5: "manual"
    assert t.plan("climate.konyha_trv", 22.5, "heat", 23.5, want=23.5, now=T0 + timedelta(seconds=300)).reason == "same"


def test_a_lost_write_is_repeated_twice_then_left_alone():
    t, head = trv.TrvTargets(), "climate.konyha_trv"
    _written(t)
    now = T0
    for _ in range(2):
        now += timedelta(minutes=6)
        p = t.plan(head, 22.5, "heat", 22.0, want=23.5, now=now)
        assert p.reason == "rewrite" and p.target == 23.5
        t.written(head, p.target, 22.5, now)
    assert t.plan(head, 22.5, "heat", 22.0, want=23.5, now=now + timedelta(minutes=6)).reason == "manual"


def test_a_change_after_the_head_took_our_write_is_by_hand():
    t, head = trv.TrvTargets(), "climate.konyha_trv"
    _written(t)
    assert t.plan(head, 22.5, "heat", 23.5, want=23.5, now=T0 + timedelta(seconds=30)).reason == "same"
    assert t.plan(head, 22.5, "heat", 22.0, want=23.5, now=T0 + timedelta(seconds=60)).reason == "manual"


def test_a_new_value_on_the_head_is_by_hand_at_once():
    t, head = trv.TrvTargets(), "climate.konyha_trv"
    _written(t)
    assert t.plan(head, 22.5, "heat", 19.0, want=23.5, now=T0 + timedelta(seconds=30)).reason == "manual"


# --- window -----------------------------------------------------------------------------------------------------
CFG = HcConfig(target_home=22.5, night_start="00:00", night_end="00:00", season_enabled=False, boost_enabled=False)


def _inp(now, window, uptime):
    return Inputs(now=now, indoor=Reading(21.0), outdoor=Reading(5.0), presence=Presence.HOME,
                  window_open=window, uptime_s=uptime)


def test_a_window_open_at_start_counts_at_once():
    sup = Supervisor(CFG)
    assert sup.step(_inp(T0, True, 10.0)).reason == Reason.WINDOW  # before 0.44.5: 2 more minutes of heating
    sup = Supervisor(CFG)
    assert sup.step(_inp(T0, True, 1e9)).reason != Reason.WINDOW  # opened while running: the delay stays


def test_a_window_contact_that_is_gone_is_reported():
    coordinator = importlib_coordinator()
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: {
        "binary_sensor.konyha_ajto": SimpleNamespace(state="unavailable"),
        "sensor.bent": SimpleNamespace(state="21.0", last_reported=T0),
        "sensor.kint": SimpleNamespace(state="5.0", last_reported=T0)}.get(e)))
    me = SimpleNamespace(conf={}, cfg=HcConfig(), hass=hass, _plaus_indoor=SimpleNamespace(problem=None),
                         _plaus_outdoor=SimpleNamespace(problem=None), _sensor_bad_since={}, sensor_problems={})
    keys = coordinator
    me.conf = {keys.CONF_INDOOR: "sensor.bent", keys.CONF_OUTDOOR: "sensor.kint",
               keys.CONF_WINDOWS: ["binary_sensor.konyha_ajto"]}
    me._window_ids = lambda: keys.HcCoordinator._window_ids(me)  # 0.46.0: no rooms here – the instance's list
    keys.HcCoordinator._update_sensor_problems(me, T0)
    keys.HcCoordinator._update_sensor_problems(me, T0 + timedelta(minutes=11))
    assert me.sensor_problems == {"binary_sensor.konyha_ajto": "lost"}


def importlib_coordinator():
    import importlib
    sys.path.insert(0, str(ROOT.parent))
    return importlib.import_module("hc_thermostat.coordinator")


def test_a_drop_window_ends_when_its_thermometer_is_gone():
    cfg = HcConfig()
    d = DropDetector(cfg)
    d.since, d.low, d.low_at = T0, 20.0, T0
    assert d.update(T0 + timedelta(minutes=10), None) is True
    assert d.update(T0 + timedelta(minutes=cfg.window_drop_max_min + 1), None) is False  # before: True for ever


# --- PWM --------------------------------------------------------------------------------------------------------
def test_a_start_delayed_by_the_minimum_off_time_keeps_its_full_run():
    p = Pwm(HcConfig(cycle_s=1800.0, min_on_s=300.0, min_off_s=300.0))
    p.cycle_start, p.output, p.last_change = T0 - timedelta(minutes=30), False, T0 - timedelta(minutes=1)
    on = 0
    for k in range(60):  # 30 minutes at 40 %
        out, _ = p.step(T0 + timedelta(seconds=30 * k), 0.4)
        on += 30 if out else 0
    assert on == 720  # before 0.44.5: 480 (the 4-min wait came off the run)


# --- PID --------------------------------------------------------------------------------------------------------
def test_pid_does_not_integrate_a_stalled_update():
    reg = PidRegulator(HcConfig(pid_kp=0.5, pid_ki_per_hour=0.2, pid_ke=0.0))
    reg.update(22.5, 22.0, None, T0)
    reg.update(22.5, 22.0, None, T0 + timedelta(hours=2))
    assert reg.integral == 0.0  # before 0.44.5: 0.2 × 0.5 × 2 = 0.2


def test_version():
    assert json.loads((ROOT / "manifest.json").read_text())["version"] in ("0.44.5", "0.45.0", "0.46.0", "0.47.0", "0.48.0", "0.48.1", "0.48.2")

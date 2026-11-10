"""Gate of stage 1: simulated faults must behave."""

import json

import pytest

from core.messages import REASONS, explain
from core.model import HcConfig, Presence, Reason
from core.supervisor import Supervisor
from sim import House, Run

CFG = HcConfig(night_start="00:00", night_end="00:00")


def test_lost_sensor_uses_fallback_not_full_burn():
    run = Run(CFG, House(outdoor=0.0))
    run.run(hours=1)
    run.indoor_ok = False
    d = run.run(hours=12)
    assert d.reason == Reason.SENSOR_LOST and d.demand == CFG.sensor_lost_demand
    on = sum(1 for x in run.decisions[-1440:] if x.output)
    assert 0 < on < 1440 * 0.5


def test_lost_sensor_recovers():
    run = Run(CFG, House(outdoor=0.0))
    run.indoor_ok = False
    run.run(hours=2)
    run.indoor_ok = True
    assert run.run(minutes=5).reason in (Reason.REGULATING, Reason.AT_TARGET)


def test_stale_value_counts_as_lost():
    run = Run(CFG)
    run.indoor_age_s = CFG.sensor_max_age_s + 1
    assert run.tick().reason == Reason.SENSOR_LOST


def test_lost_sensor_in_warm_weather_does_not_heat():
    run = Run(CFG, House(outdoor=20.0))
    run.indoor_ok = False
    d = run.run(hours=1)
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0.0


def test_disabled_and_lost_sensor_protects_only_when_cold():
    run = Run(CFG, House(outdoor=-5.0), enabled=False)
    run.indoor_ok = False
    assert run.tick().demand == CFG.sensor_lost_demand
    run = Run(CFG, House(outdoor=10.0), enabled=False)
    run.indoor_ok = False
    assert run.tick().demand == 0.0


@pytest.mark.parametrize("setup", ["disabled", "window", "season", "away"])
def test_frost_protection_wins_over_everything(setup):
    run = Run(CFG, House(indoor=6.0, outdoor=-15.0))
    if setup == "disabled":
        run.enabled = False
    elif setup == "window":
        run.house.window_open = True
    elif setup == "season":
        run.outdoor_avg = 20.0
    else:
        run.presence = Presence.AWAY
    d = run.tick()
    assert d.reason == Reason.FROST and d.output is True


def test_frost_has_hysteresis():
    run = Run(CFG, enabled=False, house=House(indoor=6.9, outdoor=-10.0))
    assert run.tick().reason == Reason.FROST
    run.house.indoor = 7.2
    assert run.tick().reason == Reason.FROST
    run.house.indoor = 7.6
    assert run.tick().reason == Reason.DISABLED


def test_window_pauses_after_delay_and_resumes():
    run = Run(CFG, House(indoor=19.0, outdoor=0.0))
    run.house.window_open = True
    assert run.tick().reason != Reason.WINDOW
    assert run.run(minutes=3).reason == Reason.WINDOW
    run.house.window_open = False
    assert run.tick().reason in (Reason.REGULATING, Reason.AT_TARGET)


def test_window_stop_still_respects_minimum_on():
    run = Run(CFG, House(indoor=15.0, outdoor=0.0))
    assert run.tick().output is True
    run.house.window_open = True
    d = run.run(minutes=2.5)
    assert d.reason == Reason.WINDOW and d.output is True and d.limited_by == "min_on"
    assert run.run(minutes=3).output is False


def test_season_hysteresis():
    run = Run(CFG, House(indoor=19.0, outdoor=10.0))
    run.outdoor_avg = 14.0
    assert run.tick().reason != Reason.SEASON_OFF
    run.outdoor_avg = 16.0
    assert run.tick().reason == Reason.SEASON_OFF
    run.outdoor_avg = 14.0
    assert run.tick().reason == Reason.SEASON_OFF
    run.outdoor_avg = 12.0
    assert run.tick().reason != Reason.SEASON_OFF


def test_restart_does_not_start_when_near_target():
    run = Run(CFG, House(indoor=20.5, outdoor=0.0), uptime_s=0.0)
    d = run.run(minutes=1)
    assert d.reason == Reason.RESTART_HOLD and d.output is False


def test_restart_starts_at_once_when_far_below_target():
    run = Run(CFG, House(indoor=17.0, outdoor=0.0), uptime_s=0.0)
    assert run.tick().output is True


def test_restart_keeps_regulator_state_and_device_limits():
    cfg = HcConfig(**{**CFG.__dict__, "control": "pid"})
    run = Run(cfg, House(indoor=19.0, outdoor=0.0))
    run.run(hours=30)
    while run.tick().output:
        pass  # stop right after the burner went off
    saved = json.loads(json.dumps(run.sup.state()))
    fresh = Supervisor(cfg)
    fresh.restore(saved)
    assert fresh.regulator.integral == run.sup.regulator.integral
    assert fresh.pwm.last_change == run.sup.pwm.last_change
    run.sup, run.uptime_s = fresh, 0.0
    run.house.indoor = 15.0  # would start at once, but the minimum off time is still running
    d = run.tick()
    assert d.output is False and d.limited_by == "min_off"


def test_dead_burner_raises_fault():
    run = Run(CFG, House(indoor=17.0, outdoor=-5.0))
    run.house.burner_works = False
    assert run.run(hours=2).fault is True


def test_fault_clears_when_heat_returns():
    run = Run(CFG, House(indoor=17.0, outdoor=-5.0))
    run.house.burner_works = False
    run.run(hours=2)
    run.house.burner_works = True
    assert run.run(hours=1).fault is False


@pytest.mark.parametrize("control", ["tpi", "pid"])
@pytest.mark.parametrize("outdoor", [-15.0, -5.0, 5.0, 12.0])
def test_normal_heating_raises_no_false_fault(control, outdoor):
    cfg = HcConfig(**{**CFG.__dict__, "control": control, "season_enabled": False})
    run = Run(cfg, House(indoor=17.0, outdoor=outdoor))
    run.run(hours=72)
    assert not any(d.fault for d in run.decisions)


def test_undersized_heating_is_no_fault_while_it_holds_or_rises():
    """Full power that barely reaches the target is weak, not broken."""
    run = Run(CFG, House(indoor=16.0, outdoor=-15.0, full_power_delta=32.0))
    run.run(hours=48)
    assert not any(d.fault for d in run.decisions)


def test_open_window_raises_no_false_fault():
    run = Run(CFG, House(indoor=17.0, outdoor=-5.0))
    run.house.window_open = True
    run.run(hours=4, actual=True)
    assert not any(d.fault for d in run.decisions)


def test_shadow_watches_the_real_burner_for_faults():
    """In shadow mode the relay is independent: the fault comes from the actual burner."""
    run = Run(CFG, House(indoor=19.0, outdoor=-5.0), enabled=False)  # the decision stays off
    run.house.burner_works = False
    d = run.run(hours=2, actual=True)
    assert d.output is False and d.fault is True


def test_boost_is_time_limited_and_rearms_only_after_recovery():
    cfg = HcConfig(**{**CFG.__dict__, "boost_enabled": True, "boost_minutes_per_degree": 10.0})
    run = Run(cfg, House(indoor=19.0, outdoor=0.0))
    d = run.tick()
    assert d.reason == Reason.BOOST and d.output is True
    run.house.burner_works = False  # no progress, so only the clock can end it
    assert run.run(minutes=30).reason != Reason.BOOST


def test_external_commands():
    cfg = HcConfig(**{**CFG.__dict__, "control": "external"})
    run = Run(cfg, House(indoor=20.0, outdoor=0.0))
    d = run.tick()
    assert d.reason == Reason.EXTERNAL and (d.external.hvac, d.external.target) == ("heat", 21.0)
    run.house.window_open = True
    assert run.run(minutes=3).external.hvac == "off"
    run.house.window_open = False
    run.house.indoor = 6.0
    d = run.tick()
    assert d.reason == Reason.FROST and d.external.hvac == "heat" and d.external.target == 8.0


def test_external_stops_restart_burn_then_gives_control_back():
    cfg = HcConfig(**{**CFG.__dict__, "control": "external"})
    run = Run(cfg, House(indoor=22.0, outdoor=0.0), uptime_s=0.0)
    d = run.tick(actual=True)
    assert d.reason == Reason.RESTART_BURN and d.external.hvac == "off"
    assert run.tick(actual=False).external.hvac == "heat"


def test_every_reason_is_explained_in_both_languages():
    run = Run(CFG)
    d = run.tick()
    for reason in Reason:
        assert set(REASONS[reason]) == {"hu", "en"}
    assert "21" in explain(d, "hu-HU") and "target" in explain(d, "en")


def test_restart_with_sensors_not_loaded_yet_does_not_start():
    """Seen live: the first decision after a restart came before the indoor sensor."""
    run = Run(CFG, House(indoor=21.5, outdoor=-4.0), uptime_s=0.0)
    run.indoor_ok = False
    d = run.run(minutes=1)
    assert d.reason == Reason.RESTART_HOLD and d.output is False
    run.indoor_ok = True
    assert run.run(minutes=2).output is False


def test_sensor_still_missing_after_grace_uses_fallback():
    run = Run(CFG, House(indoor=21.5, outdoor=-4.0), uptime_s=0.0)
    run.indoor_ok = False
    assert run.run(minutes=3).reason == Reason.SENSOR_LOST

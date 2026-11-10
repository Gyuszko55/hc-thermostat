import pytest

from core.model import HcConfig, Presence, Reason
from core.pwm import Pwm
from core.regulators import PidRegulator, TpiRegulator
from sim import House, Run, START
from datetime import timedelta


DAY = HcConfig(night_start="00:00", night_end="00:00", season_enabled=False)


@pytest.mark.parametrize("control,tolerance", [("tpi", 1.0), ("pid", 0.5)])
@pytest.mark.parametrize("outdoor", [-10.0, 0.0, 10.0])
def test_holds_target(control, tolerance, outdoor):
    cfg = HcConfig(**{**DAY.__dict__, "control": control})
    run = Run(cfg, House(outdoor=outdoor))
    run.run(hours=48)
    temps = [d.indoor for d in run.decisions[-2880:]]
    assert max(temps) < cfg.target_home + 1.0
    assert min(temps) > cfg.target_home - tolerance


@pytest.mark.parametrize("control", ["tpi", "pid"])
def test_minimum_on_and_off_are_never_violated(control):
    cfg = HcConfig(**{**DAY.__dict__, "control": control})
    run = Run(cfg, House(outdoor=5.0))
    run.run(hours=72)
    durations = run.on_off_durations()
    assert durations, "the system should cycle"
    for is_on, seconds in durations:
        assert seconds >= (cfg.min_on_s if is_on else cfg.min_off_s) - 30


def test_pwm_limits_hold_when_demand_jumps():
    cfg = HcConfig(cycle_s=600, min_on_s=300, min_off_s=300)
    pwm = Pwm(cfg)
    assert pwm.step(START, 1.0) == (True, None)
    assert pwm.step(START + timedelta(seconds=60), 0.0) == (True, "min_on")
    assert pwm.step(START + timedelta(seconds=300), 0.0) == (False, None)
    assert pwm.step(START + timedelta(seconds=360), 1.0) == (False, "min_off")


def test_small_demand_stays_off_and_large_stays_on():
    cfg = HcConfig(cycle_s=900, min_on_s=300, min_off_s=300)
    pwm = Pwm(cfg)
    assert pwm._on_time(0.1) == 0.0
    assert pwm._on_time(0.9) == 900


def test_tpi_formula():
    reg = TpiRegulator(HcConfig(tpi_coef_int=0.6, tpi_coef_ext=0.01))
    assert reg.update(21, 20, 1, START) == pytest.approx(0.8)
    assert reg.update(21, 25, 1, START) == 0.0
    assert reg.update(21, 10, 1, START) == 1.0


def test_pid_integral_does_not_wind_up():
    reg = PidRegulator(HcConfig(pid_kp=0.4, pid_ki=0.001, pid_ke=0))
    t = START
    for _ in range(2000):
        t += timedelta(seconds=30)
        reg.update(21, 5, None, t)  # saturated for hours
    assert reg.integral <= 1.0
    assert reg.update(21, 21.5, None, t + timedelta(seconds=30)) <= 1.0 - 0.15


def test_outdoor_compensation_cannot_heat_over_target():
    """The old Smart Thermostat lesson: a positive output above the target must stop."""
    cfg = HcConfig(**{**DAY.__dict__, "tpi_coef_ext": 0.05})
    run = Run(cfg, House(indoor=21.5, outdoor=-10.0))
    d = run.tick()
    assert d.reason == Reason.AT_TARGET and d.demand == 0.0 and d.output is False


def test_targets_follow_presence_schedule_and_manual_override():
    cfg = HcConfig(season_enabled=False)
    run = Run(cfg)
    assert run.tick().target == cfg.target_home
    run.presence = Presence.AWAY
    assert run.tick().target == cfg.target_away
    run.presence = Presence.VACATION
    assert run.tick().target == cfg.target_vacation
    run.presence = Presence.HOME
    run.tick()
    run.sup.manual_target = 23.0
    assert run.tick().target == 23.0
    run.now = START.replace(hour=22, minute=30)
    assert run.tick().target == cfg.target_night  # the next schedule change ends it
    run.now = START.replace(hour=3)
    assert run.tick().target == cfg.target_night
    run.sup.preset = "away"
    assert run.tick().target == cfg.target_away

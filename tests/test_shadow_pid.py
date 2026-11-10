"""PID trial in shadow: the PID calculates next to the live TPI and switches nothing."""

from core.model import HcConfig
from sim import House, Run

BASE = dict(target_home=22.0, night_start="00:00", night_end="00:00", season_enabled=False, cycle_s=1800,
            min_on_s=300, min_off_s=300, boiler_power_kw=17.3, pid_kp=0.5, pid_ki_per_hour=0.5, pid_kd=0.0)


def _house():
    return House(indoor=21.0, outdoor=5.0, loss_tau_s=72 * 3600.0, full_power_delta=232.0, radiator_tau_s=900.0)


def test_shadow_switches_nothing():
    plain = Run(HcConfig(**BASE), _house())
    plain.run(hours=12)
    shadow = Run(HcConfig(**BASE, shadow_regulator=True), _house())
    shadow.run(hours=12)
    assert [d.output for d in plain.decisions] == [d.output for d in shadow.decisions]
    assert [round(d.indoor, 6) for d in plain.decisions] == [round(d.indoor, 6) for d in shadow.decisions]


def test_shadow_reports_pid_and_counts_minutes():
    run = Run(HcConfig(**BASE, shadow_regulator=True), _house())
    d = run.run(hours=6)
    assert d.shadow["control"] == "pid" and 0.0 <= d.shadow["demand"] <= 1.0
    stats = run.sup.shadow_stats
    assert stats["live_on_s"] > 0 and stats["shadow_on_s"] >= 0


def test_pid_integral_follows_the_average_error():
    cfg = HcConfig(**{**BASE, "boiler_power_kw": 0.0}, shadow_regulator=True)
    run = Run(cfg, _house())
    run.run(hours=24)
    regulating = [d for d in run.decisions[-1440:] if d.reason.value == "regulating"]
    mean_error = sum(d.target - d.indoor for d in regulating) / len(regulating)
    integral = run.decisions[-1].shadow["integral"]
    assert integral != 0 and (integral > 0) == (mean_error > 0)


def test_ki_per_hour_wins_over_ki():
    from core.regulators import PidRegulator
    from datetime import timedelta
    from sim import START
    reg = PidRegulator(HcConfig(pid_kp=0.0, pid_ki=0.0, pid_ki_per_hour=0.5, pid_ke=0.0))
    reg.update(22.0, 21.0, None, START)
    reg.update(22.0, 21.0, None, START + timedelta(hours=1))
    assert abs(reg.integral - 0.5) < 1e-9

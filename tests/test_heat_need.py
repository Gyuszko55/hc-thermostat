from datetime import timedelta

import pytest

from core.heat_need import HeatNeedEstimator
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor
from sim import House, START, STEP_S

P_KW = 13.0
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, cycle_s=1800.0)


def live(cfg, house, days, extra_kw=0.0, indoor_ok=True):
    """Runs a house whose true loss is P / full_power_delta, feeding the delivered energy."""
    sup, now, energy, last = Supervisor(cfg), START, 500.0, None
    temps = []
    for _ in range(int(days * 86400 / STEP_S)):
        last = sup.step(Inputs(now=now, indoor=Reading(house.indoor if indoor_ok else None), outdoor=Reading(house.outdoor),
                               heat_energy_kwh=energy, other_heat_kw=extra_kw))
        temps.append(last.indoor)
        energy += (P_KW if last.output else 0.0) * STEP_S / 3600 + extra_kw * STEP_S / 3600
        house.radiator += ((1.0 if last.output else 0.0) - house.radiator) * STEP_S / house.radiator_tau_s
        equilibrium = house.outdoor + (house.radiator + extra_kw / P_KW) * house.full_power_delta
        house.indoor += (equilibrium - house.indoor) * STEP_S / house.loss_tau_s
        now += timedelta(seconds=STEP_S)
    return sup, last, temps


@pytest.mark.parametrize("delta,outdoor", [(40.0, 0.0), (120.0, 0.0), (120.0, -10.0)])
def test_learns_the_true_heat_loss(delta, outdoor):
    cfg = HcConfig(**DAY, min_on_s=300.0, boiler_power_kw=0.0)
    sup, d, _ = live(cfg, House(indoor=21.0, outdoor=outdoor, full_power_delta=delta), days=8)
    truth = P_KW / delta
    assert d.loss_kw_per_k == pytest.approx(truth, rel=0.15)
    assert d.heat_need_kw == pytest.approx(truth * (cfg.target_home - outdoor), rel=0.15)


def test_all_heat_sources_count():
    cfg = HcConfig(**DAY)
    _, d, _ = live(cfg, House(indoor=21.0, outdoor=0.0, full_power_delta=60.0), days=8, extra_kw=1.0)
    assert d.loss_kw_per_k == pytest.approx(P_KW / 60.0, rel=0.15)


def test_needs_three_days_before_answering():
    cfg = HcConfig(**DAY)
    _, d, _ = live(cfg, House(indoor=21.0, outdoor=0.0), days=2.5)
    assert d.loss_kw_per_k is None and d.heat_need_kw is None


def test_mild_days_are_not_learned_from():
    est = HeatNeedEstimator()
    t = START.replace(hour=0)
    for i in range(2880 * 5):
        est.update(t + timedelta(seconds=30 * i), 21.0, 19.0, 100.0 + i * 0.001)
    assert not est.samples


def test_counter_reset_and_gaps_do_not_corrupt():
    est = HeatNeedEstimator()
    t = START.replace(hour=0)
    energy = 1000.0
    for i in range(2880 * 2 + 10):
        energy = 5.0 if i == 1000 else energy + 0.01
        est.update(t + timedelta(seconds=30 * i), 21.0, 1.0, energy)
    assert est.samples
    assert all(s[1] < 30 for s in est.samples)  # the jump to 5 and back adds nothing huge


def test_short_coverage_day_is_dropped():
    est = HeatNeedEstimator()
    t = START.replace(hour=0)
    for i in range(1000):  # about 8 hours, then the next day
        est.update(t + timedelta(seconds=30 * i), 21.0, 1.0, 10.0 + i * 0.01)
    est.update(t + timedelta(days=1), 21.0, 1.0, 30.0)
    assert not est.samples


def test_state_survives_restart():
    est = HeatNeedEstimator()
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        est.add_sample(d, 30.0, 400.0)
    fresh = HeatNeedEstimator()
    fresh.restore(est.state())
    assert fresh.loss_kw_per_k == pytest.approx(0.075)
    fresh.add_sample("2026-11-03", 999.0, 1.0)
    assert fresh.loss_kw_per_k == pytest.approx(0.075)  # a day counts once


@pytest.mark.parametrize("use_need", [False, True])
def test_low_duty_house_holds_target(use_need):
    """A well insulated house with a big boiler: about 10 % duty, like a real one."""
    cfg = HcConfig(**DAY, boiler_power_kw=P_KW if use_need else 0.0)
    _, d, temps = live(cfg, House(indoor=21.0, outdoor=0.0, full_power_delta=170.0), days=10)
    day = temps[-2880:]
    assert max(day) < cfg.target_home + 1.0 and min(day) > cfg.target_home - 1.0


def test_feedforward_uses_the_boiler_share_only():
    cfg = HcConfig(**DAY, boiler_power_kw=10.0, tpi_coef_int=0.0)
    sup = Supervisor(cfg)
    for d in ("2026-11-01", "2026-11-02", "2026-11-03"):
        sup.heat_need.add_sample(d, 24.0, 480.0)  # 0.05 kW/K
    inp = dict(now=START, indoor=Reading(21.0), outdoor=Reading(1.0))
    assert sup.step(Inputs(**inp)).demand == pytest.approx(0.1)  # 1 kW of 10 kW
    assert sup.step(Inputs(**inp, other_heat_kw=0.6)).demand == pytest.approx(0.04)
    d = sup.step(Inputs(**inp, other_heat_kw=5.0))
    assert d.demand == 0.0 and d.reason == Reason.REGULATING and d.other_heat_kw == 5.0

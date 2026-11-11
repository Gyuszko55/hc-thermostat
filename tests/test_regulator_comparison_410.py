"""0.41.0: closed-loop comparison of TPI and PID on the simulated house (tests/compare_regulators.py) as a
regression guard – both switch the burner themselves, the sensor reports 0.1 °C steps, boost and learning off."""

import pytest

from compare_regulators import REGULATORS, simulate


@pytest.mark.parametrize("outdoor", [-10.0, 0.0, 10.0])
def test_pid_holds_the_target_closely(outdoor):
    for name in ("PID (alap)", "PID (Cirkó: Kp 0,5, Ki 0,2/h)"):
        r = simulate(REGULATORS[name], outdoor=outdoor, hours=48, start_indoor=21.0, target=21.0, measure_from_h=24)
        assert r.mean_abs < 0.1 and r.max_over < 0.25 and r.max_under < 0.25, name


@pytest.mark.parametrize("outdoor", [-10.0, 0.0, 10.0])
def test_tpi_without_learning_keeps_a_known_offset(outdoor):
    """Plain TPI has no integral: it settles below the target. In real use the learning (holding offset) closes
    the gap; this pins the size so a change is noticed."""
    r = simulate(REGULATORS["TPI"], outdoor=outdoor, hours=48, start_indoor=21.0, target=21.0, measure_from_h=24)
    assert r.max_under < 0.7 and r.max_over < 0.1


def test_pid_warms_up_without_overshoot():
    r = simulate(REGULATORS["PID (Cirkó: Kp 0,5, Ki 0,2/h)"], outdoor=0.0, hours=12, start_indoor=19.0, target=21.0)
    assert r.reach_min is not None and r.reach_min < 180 and r.max_over < 0.3


def test_same_heat_for_the_same_house():
    """Both regulators burn about the same per day for the same house: neither wastes heat to hold the target."""
    t = simulate(REGULATORS["TPI"], outdoor=0.0, hours=48, start_indoor=21.0, target=21.0, measure_from_h=24)
    p = simulate(REGULATORS["PID (alap)"], outdoor=0.0, hours=48, start_indoor=21.0, target=21.0, measure_from_h=24)
    assert abs(t.burn_min_day - p.burn_min_day) / p.burn_min_day < 0.05

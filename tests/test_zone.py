from core.heat_need import HeatNeedEstimator
from core.zone import coupled


def test_closed_door_is_separate():
    assert not coupled(False, 22.0, 22.0, 2.0)


def test_open_and_warm_is_part_of_the_house():
    assert coupled(True, 22.0, 21.0, 2.0)
    assert coupled(True, 22.0, 20.0, 2.0)


def test_open_and_cold_is_not_part_of_the_house():
    assert not coupled(True, 22.0, 19.0, 2.0)


def test_warmer_zone_is_still_part_of_the_house():
    assert coupled(True, 22.0, 25.0, 2.0)


def test_missing_sensor_is_not_coupled():
    assert not coupled(True, None, 22.0, 2.0)
    assert not coupled(True, 22.0, None, 2.0)


def test_samples_of_the_old_calculation_are_dropped():
    fresh = HeatNeedEstimator()
    fresh.restore({"samples": [["2026-11-01", 90.0, 400.0]]})
    assert not fresh.samples
    good = HeatNeedEstimator()
    good.add_sample("2026-11-01", 30.0, 400.0)
    again = HeatNeedEstimator()
    again.restore(good.state())
    assert again.samples

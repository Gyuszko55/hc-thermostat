import pytest

from core.cost import ADVICE_TEXT, compare, cop_at


def test_cop_curve():
    assert cop_at(7, 4.0, 2.4) == 4.0
    assert cop_at(-7, 4.0, 2.4) == 2.4
    assert cop_at(0, 4.0, 2.4) == pytest.approx(3.2)
    assert cop_at(25, 4.0, 2.4) == 4.0
    assert cop_at(-20, 4.0, 2.4) == 2.4
    assert cop_at(-7, 4.0, 0.5) == 1.0


def test_real_prices_mild_weather():
    a = compare(99.16, 9.45, 22.96, 2.0, 4.0, 2.4, 2.0, True)
    assert a.boiler_cost == pytest.approx(10.49)
    assert a.other_cost == pytest.approx(22.96 / 3.43, abs=0.05)
    assert a.advice == "other"
    assert a.saving_per_hour > 0


def test_cheaper_source_that_cannot_reach_the_house_is_not_recommended():
    assert compare(99.16, 9.45, 22.96, 2.0, 4.0, 2.4, 2.0, False).advice == "other_zone_only"


def test_expensive_electricity_means_boiler():
    assert compare(99.16, 9.45, 70.1, 2.0, 4.0, 2.4, 2.0, True).advice == "boiler"


def test_breakeven_outdoor_temperature():
    a = compare(100.0, 10.0, 30.0, 0.0, 4.0, 2.4, 2.0, True)  # needs COP 3
    assert a.breakeven_outdoor == pytest.approx(-1.75, abs=0.06) and a.other_always is None
    dear = compare(100.0, 10.0, 70.0, 0.0, 4.0, 2.4, 2.0, True)
    assert dear.breakeven_outdoor is None and dear.other_always is False
    cheap = compare(99.16, 9.45, 22.96, 0.0, 4.0, 2.4, 2.0, True)
    assert cheap.breakeven_outdoor is None and cheap.other_always is True


def test_about_equal_is_called_equal():
    assert compare(100.0, 10.0, 32.0, 0.0, 4.0, 2.4, 2.0, True).advice == "equal"


@pytest.mark.parametrize("args", [(None, 9.45, 23.0, 2.0), (99.0, 9.45, None, 2.0), (99.0, 9.45, 23.0, None), (99.0, 0.0, 23.0, 2.0)])
def test_missing_data_is_unknown(args):
    assert compare(*args, 4.0, 2.4, 2.0, True).advice == "unknown"


def test_every_advice_has_both_languages():
    for text in ADVICE_TEXT.values():
        assert set(text) == {"hu", "en"}

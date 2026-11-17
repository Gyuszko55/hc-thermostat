"""0.51.2: the energy rating's year – its own outdoor sensor, and missing days filled from the standard climate."""

import json
from datetime import date, timedelta
from pathlib import Path

from core.energy_rating import STANDARD_MONTHS, rating, standard_year, year_of

TODAY = date(2026, 11, 15)


def test_year_of_fills_the_missing_days_from_the_standard_climate():
    rows = [(TODAY - timedelta(days=b), 5.0) for b in range(1, 158)]  # the last 157 days measured
    days, measured = year_of(rows, TODAY)
    assert len(days) == 365 and measured == 157
    assert days[-1] == 5.0 and days[-157] == 5.0
    first = TODAY - timedelta(days=365)
    assert days[0] == STANDARD_MONTHS[first.month - 1]  # not measured: the month's standard mean


def test_year_of_ignores_empty_means_and_old_days():
    rows = [(TODAY - timedelta(days=400), 99.0), (TODAY - timedelta(days=1), None), (TODAY, 7.0)]
    days, measured = year_of(rows, TODAY)
    assert measured == 0 and 99.0 not in days and 7.0 not in days  # today is not a whole day yet


def test_climate_label_by_measured_days():
    kw = dict(source="onoff_boiler", efficiency_pct=90)
    std = standard_year()
    assert rating(0.1, 0.3, 55, outdoor_days=std, measured_days=0, **kw)["climate"] == "standard"
    mixed = rating(0.1, 0.3, 55, outdoor_days=std, measured_days=157, **kw)
    assert mixed["climate"] == "mixed" and mixed["measured_days"] == 157
    assert rating(0.1, 0.3, 55, outdoor_days=std, measured_days=330, **kw)["climate"] == "measured"
    # the same days give the same figure whatever the label
    assert mixed["ep"] == rating(0.1, 0.3, 55, **kw)["ep"]


def test_a_mild_measured_part_lowers_the_figure():
    kw = dict(source="onoff_boiler", efficiency_pct=90)
    days, measured = year_of([(TODAY - timedelta(days=b), 15.0) for b in range(1, 158)], TODAY)
    assert rating(0.1, 0.3, 55, outdoor_days=days, measured_days=measured, **kw)["ep"] < rating(0.1, 0.3, 55, **kw)["ep"]


def test_the_setting_is_offered_and_translated():
    root = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
    assert json.loads((root / "manifest.json").read_text())["version"] in ("0.51.2", "0.52.0", "0.52.1", "0.53.0", "0.54.0", "0.55.0", "0.56.0", "0.56.1", "0.57.0", "0.57.1", "0.58.0", "0.59.0", "0.60.0", "0.61.0", "0.62.0", "0.63.0", "0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0")
    assert "CONF_RATING_OUTDOOR" in (root / "config_flow.py").read_text()
    assert "rating_outdoor_entity" in (root / "const.py").read_text()
    for lang in ("hu", "en"):
        assert "rating_outdoor_entity" in (root / "translations" / f"{lang}.json").read_text()

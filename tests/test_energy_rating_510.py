"""0.51.0: the energy rating estimate on the 9/2023 ÉKM scale, from the learned house model."""

import json
from pathlib import Path

import pytest

from core.energy_rating import FNREN, carrier, grade, heat_kwh, rating, standard_year


def test_the_scale():
    assert grade(0) == "A+++" and grade(38) == "A++" and grade(68) == "A+" and grade(76) == "A"
    assert grade(76.1) == "B" and grade(98.8) == "B" and grade(122) == "C" and grade(152) == "D"
    assert grade(190) == "E" and grade(236) == "F" and grade(296) == "G" and grade(380) == "H" and grade(381) == "I"


def test_a_gas_boiler_house():
    """A gas-heated house of 55 m² with insulated walls: about 100 W/K, 0.3 kW free heat."""
    days = standard_year()
    r = rating(0.1, 0.3, 55, source="onoff_boiler", efficiency_pct=90, dhw_kwh=817, aux_kwh=150)
    heat = heat_kwh(0.1, 0.3, days)
    assert r["ep"] == pytest.approx(((heat / 0.9 + 817) * 1.1 + 150 * 2.3) / 55, abs=0.1)
    assert r["grade"] in ("C", "D", "E") and r["climate"] == "standard" and r["primary_factor"] == 1.1
    assert r["ep_low"] < r["ep"] < r["ep_high"]
    assert r["percent"] == round(100 * r["ep"] / 76)


def test_a_measured_year_wins_over_the_standard_one():
    cold = [0.0] * 365
    r = rating(0.1, 0.0, 100, source="onoff_boiler", outdoor_days=cold)
    assert r["climate"] == "measured" and r["heat_kwh"] == round(365 * 24 * 0.1 * 20)
    assert rating(0.1, 0.0, 100, source="onoff_boiler", outdoor_days=cold[:100])["climate"] == "standard"


def test_carriers_and_conversions():
    assert carrier("onoff_boiler", None) == "gas" and carrier("pellet_boiler", None) == "biomass"
    assert carrier("district_heating", None) == "district" and carrier("electric_heater", None) == "electricity"
    days = [0.0] * 365
    gas = rating(0.1, 0.0, 100, source="onoff_boiler", efficiency_pct=100, outdoor_days=days)
    direct = rating(0.1, 0.0, 100, source="electric_heater", outdoor_days=days)
    hp = rating(0.1, 0.0, 100, source="heat_pump", cop_high=4.0, cop_low=2.4, outdoor_days=days)
    assert direct["ep"] == pytest.approx(gas["ep"] * FNREN["electricity"] / FNREN["gas"], rel=1e-3)
    assert hp["ep"] == pytest.approx(direct["ep"] / 3.2, rel=1e-3)
    assert rating(0.1, 0.0, 100, source="external_heat", outdoor_days=days) is None  # unknown carrier
    assert rating(0.1, 0.0, 100, source="external_heat", primary_factor=1.38, outdoor_days=days)["primary_factor"] == 1.38


def test_nothing_without_an_area_or_a_loss():
    assert rating(0.1, 0.3, 0, source="onoff_boiler") is None
    assert rating(None, 0.3, 55, source="onoff_boiler") is None


def test_version():
    root = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
    assert json.loads((root / "manifest.json").read_text())["version"] in ("0.51.0", "0.51.1", "0.51.2", "0.52.0", "0.52.1", "0.53.0", "0.54.0", "0.55.0", "0.56.0", "0.56.1", "0.57.0", "0.57.1", "0.58.0", "0.59.0", "0.60.0", "0.61.0", "0.62.0", "0.63.0", "0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4")
    tr = json.loads((root / "translations" / "hu.json").read_text())
    assert tr["entity"]["sensor"]["energy_rating"]["name"] == "Energetikai besorolás (becslés)"
    assert "house_area_m2" in tr["options"]["step"]["settings"]["sections"]["house"]["data"]

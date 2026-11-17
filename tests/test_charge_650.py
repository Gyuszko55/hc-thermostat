"""0.65.0: demand-based tank charging by the heat pump (the tester's live case: the top at 37 °C, the need at
34.5 °C, the tank spent below – the classic rule did not start), compared with the classic rule in shadow."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from hc_thermostat.core.hp_coord import (CHARGE_MODES, REASONS, CircuitNeed, HeatPumpCoordinator, HpConfig,  # noqa: E402
                                         HpInputs)

T0 = datetime(2026, 11, 16, 18, 58)
TANK = (("top", 37.0, 250.0, True), ("upper", 36.6, 250.0, True), ("lower", 35.9, 250.0, True), ("bottom", 28.5, 250.0, True))


def _inp(layers=TANK, demand=True, target=32.5, charge=9.0, trend=None, circuits=None, **kw):
    top = layers[0][1] if layers else None
    circ = circuits if circuits is not None else (CircuitNeed("rad", demand, target, 2.0, demand),
                                                  CircuitNeed("floor", demand, 31.0, 2.0, demand))
    return HpInputs(outdoor=5.1, top=top, charge=charge, trend_c_h=trend, circuits=circ, layers=layers, **kw)


def _hp(**kw):
    return HeatPumpCoordinator(HpConfig(**{"hp_charge_on": 4.0, "hp_charge_off": 10.0, "hp_min_off_s": 0, "hp_min_on_s": 0, **kw}))


def test_the_testers_case_classic_waits_demand_starts():
    hp = _hp()  # classic drives (the default)
    d = hp.step(T0, _inp())
    assert d.need == 34.5 and d.details["charge_mode"] == "classic"
    assert not d.enable and d.details["classic"] == {"heat": False, "why": "off"}
    dc = d.details["demand_charge"]
    assert dc["heat"] is True and dc["why"] == "reserve_low"
    assert dc["reserve_c"] == 2.5 and dc["start_below"] == 37.5
    # kWh above the need: 250 l × 1.163 × (2.5 + 2.1 + 1.4 + 0) / 1000
    assert dc["reserve_kwh"] == round(250 * 1.163 * 6.0 / 1000, 2)
    hp2 = _hp(hp_charge_mode="demand")
    d2 = hp2.step(T0, _inp())
    assert d2.enable and d2.heat_demand and d2.reason == "reserve_low"
    assert d2.details["classic"]["why"] == "off"  # the other rule is still shown


def test_stop_needs_the_lower_layer_and_respects_the_coil():
    hp = _hp(hp_charge_mode="demand")  # reserve 5: flow 39.5 → the tank can reach 36.5 at most
    assert hp.step(T0, _inp()).heat_demand
    warm = (("top", 41.0, 250.0, True), ("upper", 39.0, 250.0, True), ("lower", 36.0, 250.0, True), ("bottom", 30.0, 250.0, True))
    d = hp.step(T0 + timedelta(minutes=30), _inp(warm))
    assert d.details["demand_charge"]["stop_at"] == 36.5  # min(34.5 + 3, 39.5 − 3)
    assert d.heat_demand and d.reason == "charging_reserve"  # a warm top alone does not stop it
    full = (("top", 42.0, 250.0, True), ("upper", 40.0, 250.0, True), ("lower", 36.6, 250.0, True), ("bottom", 31.0, 250.0, True))
    d = hp.step(T0 + timedelta(minutes=60), _inp(full))
    assert not d.heat_demand and d.reason == "reserve_full"


def test_stop_point_never_under_the_need():
    hp = _hp(hp_charge_mode="demand", hp_reserve=0.0)
    d = hp.step(T0, _inp())
    assert d.details["demand_charge"]["stop_at"] == 34.5  # flow 34.5 − 3 would be under the need


def test_missing_stop_layer_uses_the_nearest_measured_one_above():
    layers = (("top", 37.0, 250.0, True), ("upper", 36.6, 250.0, True), ("lower", 36.0, 250.0, False), ("bottom", 28.5, 250.0, True))
    d = _hp(hp_charge_mode="demand").step(T0, _inp(layers))
    assert d.details["demand_charge"]["stop_layer"] == "upper"


def test_no_lasting_demand_starts_nothing_even_with_a_low_charge():
    hp = _hp(hp_charge_mode="demand")
    d = hp.step(T0, _inp(demand=False, charge=2.0))
    assert not d.heat_demand and d.details["demand_charge"]["why"] == "no_demand"
    assert d.details["classic"]["why"] == "low_charge"  # the classic rule would start on the percentage


def test_kwh_start_and_wood_first_and_frost():
    hp = _hp(hp_charge_mode="demand", hp_start_margin=0.0, hp_start_kwh=5.0)
    d = hp.step(T0, _inp())
    assert d.reason == "reserve_low_kwh"
    wood = _hp(hp_charge_mode="demand").step(T0, _inp(wood_signal=True))
    assert not wood.heat_demand and wood.details["demand_charge"]["why"] == "wood"
    cold = (("top", 7.0, 250.0, True), ("upper", 6.0, 250.0, True), ("lower", 6.0, 250.0, True), ("bottom", 5.0, 250.0, True))
    assert _hp(hp_charge_mode="demand").step(T0, _inp(cold, wood_signal=True)).details["demand_charge"]["why"] == "frost"


def test_enough_reserve_waits():
    warm = (("top", 45.0, 250.0, True), ("upper", 42.0, 250.0, True), ("lower", 38.0, 250.0, True), ("bottom", 30.0, 250.0, True))
    d = _hp(hp_charge_mode="demand").step(T0, _inp(warm, trend=-2.0))
    assert not d.heat_demand and d.reason == "reserve_ok"
    assert d.details["demand_charge"]["hours_left"] == round((45.0 - 34.5) / 2.0, 2)


def test_a_tank_without_circuits_keeps_the_classic_rule():
    d = _hp(hp_charge_mode="demand").step(T0, _inp(circuits=(), zones_asking=True, charge=2.0))
    assert d.details["charge_mode"] == "classic" and d.details.get("charge_mode_fallback")
    assert d.reason == "low_charge"


def test_each_rule_keeps_its_own_latch_and_it_survives_a_restart():
    hp = _hp()  # classic drives; the demand rule starts in the shadow
    hp.step(T0, _inp())
    assert hp.heating is False and hp.alt_heating is True
    data = json.loads(json.dumps(hp.state(T0)))
    hp2 = _hp()
    hp2.restore(data, T0)
    assert hp2.alt_heating is True


def test_reasons_texts_and_form():
    for r in ("reserve_low", "reserve_low_kwh", "charging_reserve", "reserve_ok", "reserve_full", "no_demand"):
        assert r in REASONS
    from hc_thermostat import config_flow as cf
    keys = {str(k) for k in cf._hpc_settings({})}
    assert {"hp_charge_mode", "hp_start_margin", "hp_start_kwh", "hp_stop_layer", "hp_stop_margin", "hp_coil_dt"} <= keys
    assert HpConfig().hp_charge_mode == "classic" and set(CHARGE_MODES) == {"classic", "demand"}
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        for top in ("config", "options"):
            assert tr[top]["step"]["hp_coord_settings"]["data"]["hp_charge_mode"]
        assert set(tr["selector"]["hp_charge_mode"]["options"]) == set(CHARGE_MODES)
        assert set(tr["selector"]["hp_stop_layer"]["options"]) == {"top", "upper", "lower", "bottom"}
        assert set(REASONS) <= set(tr["entity"]["sensor"]["hp_decision"]["state"])
    js = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "Tartalék az igény fölött" in js and "Töltési szabály (vezérel)" in js
    ov = (BASE / "www" / "hc-overview.js").read_text()
    assert "charging_reserve:" in ov and "chMode:" in ov
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0")

"""0.68.0: the demand-based charging's second step – the start timed by the tank's cooling trend: when the tank cools
steadily and at that pace its top reaches the need within the heat pump's lead time, it starts now."""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from hc_thermostat.core.hp_coord import (REASONS, TREND_MIN_C_H, CircuitNeed, HeatPumpCoordinator, HpConfig,  # noqa: E402
                                         HpInputs)

T0 = datetime(2026, 11, 17, 6, 0)
WARM = (("top", 39.5, 250.0, True), ("upper", 38.0, 250.0, True), ("lower", 36.0, 250.0, True), ("bottom", 30.0, 250.0, True))


def _inp(trend, layers=WARM):
    circ = (CircuitNeed("rad", True, 32.5, 2.0, True),)
    return HpInputs(outdoor=-3.0, top=layers[0][1], charge=30.0, trend_c_h=trend, circuits=circ, layers=layers)


def _hp(**kw):
    return HeatPumpCoordinator(HpConfig(**{"hp_charge_mode": "demand", "hp_min_off_s": 0, "hp_min_on_s": 0, **kw}))


def test_fast_cooling_starts_before_the_reserve_is_low():
    # need 34.5, top 39.5 (above need + 3: no reserve_low); −6 °C/h → 50 minutes left < 60
    d = _hp().step(T0, _inp(-6.0))
    assert d.heat_demand and d.reason == "reserve_runs_out"
    dc = d.details["demand_charge"]
    assert dc["hours_left"] == round(5.0 / 6.0, 2) and dc["lead_min"] == 60.0


def test_slow_cooling_waits():
    d = _hp().step(T0, _inp(-2.0))  # 2.5 h left
    assert not d.heat_demand and d.reason == "reserve_ok"


def test_a_barely_cooling_tank_is_no_trend():
    d = _hp(hp_lead_min=600).step(T0, _inp(-(TREND_MIN_C_H / 2)))
    assert not d.heat_demand and d.reason == "reserve_ok"


def test_switched_off_and_the_classic_rule_untouched():
    assert _hp(hp_lead_min=0).step(T0, _inp(-6.0)).reason == "reserve_ok"
    d = _hp(hp_charge_mode="classic").step(T0, _inp(-6.0))
    assert d.details["classic"]["why"] == "off" and d.details["demand_charge"]["why"] == "reserve_runs_out"


def test_texts_and_form():
    assert "reserve_runs_out" in REASONS and HpConfig().hp_lead_min == 60.0
    from hc_thermostat import config_flow as cf
    assert "hp_lead_min" in cf.HPC_SECTIONS["charge_demand"]
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        assert tr["entity"]["sensor"]["hp_decision"]["state"]["reserve_runs_out"]
        sec = tr["options"]["step"]["hp_coord_settings"]["sections"]["charge_demand"]
        assert sec["data"]["hp_lead_min"] and sec["data_description"]["hp_lead_min"]
    assert "reserve_runs_out" in (BASE / "www" / "hc-overview.js").read_text()
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3", "0.82.4", "0.82.5", "0.82.6")

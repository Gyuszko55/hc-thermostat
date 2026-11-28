"""0.64.0 (tester's third round, live on a buffer system): the mixer's target is capped by the tank's top (the heat
pump still sees the uncapped need), the heat pump's written target can be rounded up to 0.5 / 1 °C, a chart of the
heat pump's target, and a house name settable on the plant's instances."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
OV_PATH = BASE / "www" / "hc-overview.js"

from hc_thermostat.core.circuit import TANK_STALE_S, CircuitConfig, MixingCircuit, ZoneReading  # noqa: E402
from hc_thermostat.core.output_guard import ROUND_MODES, round_target  # noqa: E402

T0 = datetime(2026, 11, 16, 6, 0)


def _rad(**kw):
    return MixingCircuit(CircuitConfig.from_conf({"circuit_kind": "radiator", "circuit_margin": 3.0, "circuit_tank_cap": True, **kw}))


def test_cap_gives_the_mixer_top_minus_margin():
    c = _rad()
    out, limit, state = c.cap(T0, 38.0, 36.0, True)
    assert (out, limit, state) == (33.0, 33.0, "limited")
    out, limit, state = c.cap(T0, 30.5, 50.0, True)  # a warm tank does not limit
    assert (out, state) == (30.5, "ok")


def test_cap_limit_is_on_a_half_degree_grid():
    c = _rad()
    assert c.cap(T0, 45.0, 40.9, True)[1] == 37.5  # 37.9 → 37.5
    assert c.cap(T0, 45.0, 41.0, True)[1] == 38.0


def test_cooling_tank_lowers_at_once_warming_one_steps_up():
    c = _rad(circuit_max_rise=3.0, circuit_confirm_s=600)
    assert c.cap(T0, 44.0, 50.0, True)[0] == 44.0
    # the tank cools: down in the same step, no confirmation
    assert c.cap(T0 + timedelta(seconds=30), 44.0, 40.0, True)[0] == 37.0
    assert c.cap(T0 + timedelta(seconds=60), 44.0, 38.0, True)[0] == 35.0
    # warm again: +3 °C at most every 10 minutes
    assert c.cap(T0 + timedelta(seconds=90), 44.0, 55.0, True)[0] == 35.0
    assert c.cap(T0 + timedelta(seconds=60 + 600), 44.0, 55.0, True)[0] == 38.0
    assert c.cap(T0 + timedelta(seconds=60 + 900), 44.0, 55.0, True)[0] == 38.0
    assert c.cap(T0 + timedelta(seconds=60 + 1200), 44.0, 55.0, True)[0] == 41.0
    assert c.cap(T0 + timedelta(seconds=60 + 1800), 44.0, 55.0, True) == (44.0, 52.0, "ok")


def test_below_the_minimum_the_minimum_with_a_cold_warning():
    c = _rad()  # radiator minimum 30
    out, limit, state = c.cap(T0, 40.0, 31.0, True)
    assert (out, limit, state) == (30.0, 30.0, "cold")


def test_no_tank_reading_last_good_then_no_cap():
    c = _rad()
    assert c.cap(T0, 40.0, 36.0, True)[0] == 33.0
    out, _, state = c.cap(T0 + timedelta(seconds=TANK_STALE_S - 30), 40.0, None, True)
    assert (out, state) == (33.0, "stale")
    out, limit, state = c.cap(T0 + timedelta(seconds=TANK_STALE_S + 30), 40.0, None, True)
    assert (out, limit, state) == (40.0, None, "no_data")


def test_no_tank_or_switched_off_is_off():
    assert _rad().cap(T0, 40.0, 30.0, False) == (40.0, None, "off")
    assert _rad(circuit_tank_cap=False).cap(T0, 40.0, 30.0, True) == (40.0, None, "off")


def test_step_keeps_the_demanded_target_for_the_heat_pump():
    c = _rad(circuit_slope=1.2, circuit_confirm_s=0, circuit_min_interval_s=0)
    zones = [ZoneReading("climate.a", True, 22.0, 21.0)]
    d = c.step(T0, zones, 0.0, tank_top=36.0, tank_linked=True)
    assert d.demand_target is not None and d.demand_target > 33.0
    assert d.target == 33.0 and d.cap == 33.0 and d.cap_state == "limited"
    assert d.shortfall == round(d.demand_target - 33.0, 1)
    src = (BASE / "hp_coord_coordinator.py").read_text()
    assert "d.demand_target if d.demand_target is not None else d.target" in src


def test_cap_survives_a_restart():
    c = _rad()
    c.cap(T0, 38.0, 36.0, True)
    data = json.loads(json.dumps(c.state(T0)))
    c2 = _rad()
    c2.restore(data, T0)
    assert (c2.out, c2.limited, c2.top) == (33.0, True, 36.0)


@pytest.mark.parametrize("value,step,mode,want", [
    (36.0, 0.5, "whole_up", 36.0), (36.1, 0.5, "whole_up", 37.0), (41.5, 0.5, "whole_up", 42.0),
    (36.000000001, 0.5, "whole_up", 36.0), (36.1, 0.5, "half_up", 36.5), (36.5, 0.1, "half_up", 36.5),
    (36.2, 0.5, "device", 36.0), (36.3, 0.5, "device", 36.5), (36.24, 0.1, "device", 36.2), (36.2, 0, "device", 36.2),
])
def test_round_target(value, step, mode, want):
    assert round_target(value, step, mode) == want


def test_climate_output_writes_and_compares_the_rounded_value():
    from hc_thermostat.output_writer import OutputWriter
    hass = SimpleNamespace(config=SimpleNamespace(units=SimpleNamespace(temperature_unit="°C")))
    w = OutputWriter(hass, "climate.hp", round_mode="whole_up")
    st = SimpleNamespace(attributes={"target_temp_step": 0.5, "min_temp": 20, "max_temp": 40})
    assert w._climate_value(st, 36.1) == 37.0
    assert w._climate_value(st, 39.2) == 40.0
    assert w._climate_value(st, 40.2) == 40.0  # within the unit's limits
    assert OutputWriter(hass, "climate.hp")._climate_value(st, 36.1) == 36.0  # the old behaviour by default
    assert set(ROUND_MODES) == {"device", "half_up", "whole_up"}


def test_hp_series_from_recorder_states():
    from hc_thermostat.info import hp_series
    t = datetime(2026, 11, 16, 6, 0).astimezone()
    S = lambda s, m, **a: SimpleNamespace(state=s, attributes=a, last_updated=t + timedelta(minutes=m))  # noqa: E731
    states = {"sensor.raw": [S("36.2", 0), S("36.2", 1), S("37.4", 5)],
              "sensor.tg": [S("36.5", 0, sent=37.0), S("36.5", 3, sent=37.0), S("38", 10, sent=38.0)],
              "climate.hp": [S("heat", 0, temperature=37), S("heat", 12, temperature=38)],
              "sensor.w": [S("33.1", 0), S("unavailable", 4), S("35.0", 9)]}
    out = hp_series(states, {"raw": "sensor.raw", "target": "sensor.tg", "reported": "climate.hp", "water": "sensor.w"})
    assert [p[1] for p in out["raw"]] == [36.2, 37.4]
    assert [p[1] for p in out["sent"]] == [37.0, 38.0]
    assert [p[1] for p in out["reported"]] == [37.0, 38.0]
    assert [p[1] for p in out["water"]] == [33.1, None, 35.0]


def test_hp_chart_svg():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    t0 = 1_763_272_800_000
    hist = {"start": t0, "end": t0 + 86_400_000, "series": {
        "raw": [[t0, 36.2], [t0 + 3_600_000, 38.4]], "target": [[t0, 36.5]], "sent": [[t0, 37]],
        "reported": [[t0 + 60_000, 37]], "water": [[t0, 33], [t0 + 7_200_000, 36.5]]}}
    script = f"""
import * as OV from {json.dumps(OV_PATH.as_uri())};
console.log(JSON.stringify({{ a: OV.hpChartSvg({json.dumps(hist)}, {{ lang: "hu" }}), b: OV.hpChartSvg(null, {{ lang: "en" }}) }}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["a"].count("<path ") == 5 and "kiküldve (kerekítve)" in r["a"] and "mért víz" in r["a"]
    assert "No recorded data" in r["b"]


def test_flow_panel_and_texts():
    from hc_thermostat import config_flow as cf
    keys = {str(k) for k in cf._circuit_settings({}, "radiator")}
    assert "circuit_tank_cap" in keys
    src = (BASE / "config_flow.py").read_text()
    assert src.count("fields[vol.Optional(CONF_HOME_NAME") == 4  # buffer, circuit, heat pump coordination; 0.65.1: zone
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        for top in ("config", "options"):
            assert tr[top]["step"]["circuit_settings"]["data"]["circuit_tank_cap"]
            assert tr[top]["step"]["hp_coord"]["data"]["hp_target_round"]
            assert tr[top]["step"]["hp_coord"]["data"]["hp_water_temp_entity"]
        for step in ("buffer", "circuit", "hp_coord"):
            assert tr["options"]["step"][step]["data"]["home_name"]
        assert set(tr["selector"]["hp_target_round"]["options"]) == set(ROUND_MODES)
    js = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "hc_thermostat/hp_history" in js and "Puffer-korlát" in js and "Kiküldve" in js
    assert (BASE / "wizard.py").read_text().count("ws_hp_history") == 2
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3", "0.82.4", "0.82.5", "0.82.6", "0.82.7", "0.83.0", "0.84.0", "0.85.0", "0.86.0", "0.87.0")


def test_tank_cap_is_off_by_default_since_641():
    """0.64.1: an update must not change a live PLC setpoint by itself – the cap is switched on by hand."""
    assert CircuitConfig().circuit_tank_cap is False
    assert CircuitConfig.from_conf({"circuit_kind": "floor"}).circuit_tank_cap is False
    c = MixingCircuit(CircuitConfig.from_conf({"circuit_kind": "radiator"}))
    assert c.cap(T0, 40.0, 30.0, True) == (40.0, None, "off")
    from hc_thermostat import config_flow as cf
    form = {str(k): k for k in cf._circuit_settings({}, "radiator")}
    assert form["circuit_tank_cap"].default() is False

"""0.75.0 (a tester's request, a heat pump charging a 1000 l tank through its lower coil): the water-side heat meter
and the current COP of the heat pump coordination – kW = l/min × ΔT × 0.06977, trapezoid energy between valid readings
at most hm_max_gap_s apart, the COP of the last minutes of active running (heat over electricity), a COP curve on the
heat pump chart."""

import importlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from core.heat_meter import WATER_KW, HeatMeter, HeatMeterConfig, HmSample, heat_kw  # noqa: E402

T0 = datetime(2026, 11, 18, 11, 10, tzinfo=timezone.utc)


def at(s):
    return T0 + timedelta(seconds=s)


def run(hm, seconds, t_out=44.0, t_in=41.0, flow=48.0, p_el_w=2500.0, start=0, step=30, **kw):
    info = None
    for s in range(start, start + seconds + 1, step):
        info = hm.step(HmSample(at(s), t_out, t_in, flow, p_el_w, **kw))
    return info


# --- 1–3: the numbers ---------------------------------------------------------------------------------------------------
def test_the_testers_reading_is_10_05_kw():
    assert WATER_KW == 0.06977
    assert round(heat_kw(48, 44, 41), 2) == 10.05
    info = HeatMeter().step(HmSample(T0, 44.0, 41.0, 48.0, 2500.0))
    assert info["power_kw"] == pytest.approx(10.047, abs=0.001) and info["dt"] == 3.0 and info["valid"]


def test_no_flow_is_0_kw_and_the_total_stays():
    hm = HeatMeter()
    run(hm, 600)
    total = hm.total_kwh
    info = run(hm, 600, flow=0.0, start=630)
    assert info["power_kw"] == 0.0 and info["valid"]
    # The previous full heating interval is preserved, but no half-interval is invented at the stop.
    assert hm.total_kwh == pytest.approx(total, rel=1e-6)
    assert info["cop"] is None and info["cop_reason"] == "no_flow"


def test_10_kw_for_an_hour_is_10_kwh_and_a_restart_keeps_it():
    hm = HeatMeter()
    flow = 10.0 / (3 * WATER_KW)  # exactly 10 kW at ΔT 3 K
    run(hm, 3600, flow=flow)
    assert hm.total_kwh == pytest.approx(10.0, rel=1e-9)
    fresh = HeatMeter()
    fresh.restore(json.loads(json.dumps(hm.state())))
    assert fresh.total_kwh == pytest.approx(10.0) and fresh.info["total_kwh"] == pytest.approx(10.0)
    fresh.step(HmSample(at(7200), 44.0, 41.0, flow, 2500.0))  # first reading after the restart: no energy for the gap
    assert fresh.total_kwh == pytest.approx(10.0)
    fresh.step(HmSample(at(7230), 44.0, 41.0, flow, 2500.0))
    assert fresh.total_kwh == pytest.approx(10.0 + 10.0 * 30 / 3600)


# --- 4–5: gaps, stale and impossible readings ----------------------------------------------------------------------------
def test_a_reading_missing_for_10_minutes_adds_no_jump():
    hm = HeatMeter()
    run(hm, 300)
    before = hm.total_kwh
    for s in range(330, 930, 30):
        info = hm.step(HmSample(at(s), 44.0, None, 48.0, 2500.0))
        assert info["power_kw"] is None and not info["valid"] and info["cop"] is None
    assert hm.total_kwh == before
    hm.step(HmSample(at(930), 44.0, 41.0, 48.0, 2500.0))
    assert hm.total_kwh == before  # a new start, nothing filled in
    hm.step(HmSample(at(960), 44.0, 41.0, 48.0, 2500.0))
    assert hm.total_kwh == pytest.approx(before + 10.047 * 30 / 3600, rel=1e-3)


def test_a_long_gap_between_valid_readings_adds_nothing():
    hm = HeatMeter(HeatMeterConfig(hm_max_gap_s=120))
    hm.step(HmSample(at(0), 44.0, 41.0, 48.0, 2500.0))
    hm.step(HmSample(at(600), 44.0, 41.0, 48.0, 2500.0))  # HA was busy / restarted
    assert hm.total_kwh == 0.0


@pytest.mark.parametrize("t_out,t_in,flow", [(150.0, 41.0, 48.0), (44.0, -40.0, 48.0), (44.0, 41.0, -3.0),
                                             (44.0, 41.0, 5000.0)])
def test_impossible_readings_are_unavailable(t_out, t_in, flow):
    info = HeatMeter().step(HmSample(T0, t_out, t_in, flow, 2500.0))
    assert not info["valid"] and info["power_kw"] is None


def test_negative_delta_t_is_0_kw_never_negative_energy():
    hm = HeatMeter()
    info = run(hm, 600, t_out=38.0, t_in=41.0)
    assert info["power_kw"] == 0.0 and hm.total_kwh == 0.0 and info["cop"] is None and info["cop_reason"] == "negative_dt"


def test_flow_without_heating():
    info = run(HeatMeter(), 600, t_out=41.0, t_in=41.0, p_el_w=8.0)
    assert info["power_kw"] == 0.0 and info["cop"] is None


# --- 7: whole-degree thermometers ----------------------------------------------------------------------------------------
def test_the_uncertainty_of_a_small_delta_t_is_shown():
    info = HeatMeter().step(HmSample(T0, 44.0, 41.0, 48.0, 2500.0))
    assert info["uncertainty_pct"] == 33
    info = HeatMeter(HeatMeterConfig(hm_resolution=0.1)).step(HmSample(T0, 44.0, 41.0, 48.0, 2500.0))
    assert info["uncertainty_pct"] == 3


# --- 8–12: the COP -----------------------------------------------------------------------------------------------------
def test_cop_4_02_after_the_window_fills():
    hm = HeatMeter()
    info = run(hm, 240)
    assert info["cop"] is None and info["cop_reason"] == "warming_up" and info["cop_raw"] == 4.02
    info = run(hm, 120, start=270)
    assert info["cop"] == pytest.approx(4.02, abs=0.01)
    assert info["cop_today"] == pytest.approx(4.02, abs=0.01) and info["coverage_pct"] == 100


def test_cop_is_energy_weighted_not_a_mean_of_ratios():
    hm = HeatMeter(HeatMeterConfig(hm_cop_window_s=600, hm_cop_min_s=60))
    run(hm, 300, p_el_w=2500.0)  # COP 4.02 at 10.05 kW
    info = run(hm, 300, p_el_w=5000.0, flow=96.0, start=330)  # COP 4.02 at 20.1 kW
    assert info["cop"] == pytest.approx(4.02, abs=0.02)
    hm = HeatMeter(HeatMeterConfig(hm_cop_window_s=3600, hm_cop_min_s=60))
    run(hm, 600, p_el_w=2500.0)  # 10.05 kW / 2.5 kW
    info = run(hm, 600, p_el_w=1000.0, flow=9.6, start=630)  # 2.01 kW / 1 kW = 2.01
    # energy-weighted: (10.05·600 + 2.01·600) / (2.5·600 + 1·600) ≈ 3.45 – the mean of the ratios would be 3.0
    assert info["cop"] == pytest.approx(12.06 / 3.5, abs=0.05)


def test_kw_power_reading_converts():
    hp = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    now = T0
    st = {"sensor.p_w": SimpleNamespace(entity_id="sensor.p_w", state="2500", attributes={"unit_of_measurement": "W"}, last_reported=now, last_updated=now),
          "sensor.p_kw": SimpleNamespace(entity_id="sensor.p_kw", state="2.5", attributes={"unit_of_measurement": "kW"}, last_reported=now, last_updated=now),
          "sensor.p_old": SimpleNamespace(entity_id="sensor.p_old", state="2.5", attributes={"unit_of_measurement": "kW"}, last_reported=now - timedelta(minutes=20), last_updated=now - timedelta(minutes=20)),
          "sensor.hz": SimpleNamespace(entity_id="sensor.hz", state="55", attributes={"unit_of_measurement": "Hz"}, last_reported=now, last_updated=now),
          "sensor.flow_h": SimpleNamespace(entity_id="sensor.flow_h", state="2880", attributes={"unit_of_measurement": "L/h"}, last_reported=now, last_updated=now),
          "sensor.flow_x": SimpleNamespace(entity_id="sensor.flow_x", state="48", attributes={"unit_of_measurement": "kg"}, last_reported=now, last_updated=now)}
    hass = SimpleNamespace(states=SimpleNamespace(get=st.get))
    assert hp.read_power_w(hass, "sensor.p_w", now, 300) == 2500.0 == hp.read_power_w(hass, "sensor.p_kw", now, 300)
    assert hp.read_power_w(hass, "sensor.p_old", now, 300) is None  # stuck at 2.5 kW: no COP from it
    assert hp.read_power_w(hass, "sensor.hz", now, 300) is None and not hp.power_unit(hass, "sensor.hz")
    assert hp.power_unit(hass, "sensor.p_kw")
    assert hp.read_flow_lmin(hass, "sensor.flow_h", now, 300) == pytest.approx(48.0)
    assert hp.read_flow_lmin(hass, "sensor.flow_x", now, 300) is None
    a = HeatMeter().step(HmSample(T0, 44.0, 41.0, 48.0, hp.read_power_w(hass, "sensor.p_kw", now, 300)))
    assert a["cop_raw"] == 4.02


def test_no_flow_and_standby_power_is_no_cop():
    info = run(HeatMeter(), 900, flow=0.0, p_el_w=100.0)
    assert info["cop"] is None and info["cop_raw"] is None and info["cop_reason"] == "no_flow"


def test_without_a_power_or_frequency_signal_heat_is_measured_unconfirmed_and_no_cop():
    hm = HeatMeter()
    info = run(hm, 900, p_el_w=None, power_source=False)
    assert info["cop"] is None and info["cop_reason"] == "no_power_meter" and hm.total_kwh > 2.4
    assert info["heat_reason"] is None and info["heat_gate"] == "none" and info["heat_confirmed"] is False


def test_stale_power_defrost_and_a_short_stop_give_no_spike():
    hm = HeatMeter()
    run(hm, 600)
    info = hm.step(HmSample(at(630), 44.0, 41.0, 48.0, None))  # the power meter went quiet
    assert info["cop"] is None and info["cop_reason"] == "stale_power"
    info = hm.step(HmSample(at(660), 40.0, 42.0, 48.0, 2500.0, busy=True))
    assert info["cop"] is None and info["cop_reason"] == "defrost" and info["power_kw"] == 0.0
    # back to heating: a new window – no COP until hm_cop_min_s of active running, so no start-up spike
    seen = [hm.step(HmSample(at(s), 44.0, 41.0, 48.0, 2500.0))["cop"] for s in range(690, 990, 30)]
    assert all(c is None for c in seen)
    assert run(hm, 120, start=990)["cop"] == pytest.approx(4.02, abs=0.01)


def test_below_the_compressor_threshold_and_an_implausible_cop():
    info = run(HeatMeter(), 600, p_el_w=60.0)  # pump only: 60 W, under hp_running_w 100 W
    assert info["cop"] is None and info["cop_reason"] == "not_running"
    info = run(HeatMeter(), 600, p_el_w=500.0)  # 10 kW from 0.5 kW: COP 20 – a wrong reading
    assert info["cop"] is None and info["cop_raw"] is None and info["cop_reason"] == "implausible"


def test_the_day_starts_again_at_midnight():
    hm = HeatMeter()
    start = datetime(2026, 11, 18, 23, 50, tzinfo=timezone.utc)
    for s in range(0, 1201, 30):
        hm.step(HmSample(start + timedelta(seconds=s), 44.0, 41.0, 48.0, 2500.0))
    assert hm.day == "2026-11-19" and hm.day_heat_kwh < hm.total_kwh
    # the interval ending at 00:00:00 already belongs to the new day: 21 intervals of 30 s after midnight
    assert hm.day_heat_kwh == pytest.approx(10.047 * 630 / 3600, rel=0.01)


# --- 6: optional, nothing changes without it ----------------------------------------------------------------------------
def test_the_coordinator_step_reads_its_entities():
    hp = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    now = T0
    def S(v, unit, eid):
        return SimpleNamespace(entity_id=eid, state=v, attributes={"unit_of_measurement": unit}, last_reported=now, last_updated=now)
    st = {"sensor.out": S("44", "°C", "sensor.out"), "sensor.in": S("41", "°C", "sensor.in"),
          "sensor.flow": S("48", "L/min", "sensor.flow"), "binary_sensor.run": S("on", None, "binary_sensor.run")}
    conf = {"hp_flow_out_temp_entity": "sensor.out", "hp_flow_in_temp_entity": "sensor.in",
            "hp_water_flow_entity": "sensor.flow", "hp_running_entity": "binary_sensor.run"}
    fake = SimpleNamespace(hass=SimpleNamespace(states=SimpleNamespace(get=st.get)), conf=conf,
                           heat_meter=HeatMeter(), hp=SimpleNamespace(cfg=SimpleNamespace(hp_running_w=100.0)))
    fake.power_entity = lambda: hp.HpCoordCoordinator.power_entity(fake)
    info = hp.HpCoordCoordinator.heat_step(fake, now)
    assert info["power_kw"] == pytest.approx(10.047, abs=0.001) and info["power_entity"] is None
    assert info["cop_reason"] == "no_power_meter"  # a binary "runs" signal: heat yes (unconfirmed), COP no
    assert info["heat_confirmed"] is False
    st["sensor.pw"] = S("2.5", "kW", "sensor.pw")
    conf["hp_power_entity"] = "sensor.pw"
    info = hp.HpCoordCoordinator.heat_step(fake, now + timedelta(seconds=30))
    assert info["power_entity"] == "sensor.pw" and info["cop_raw"] == 4.02
    assert info["power_kw"] == pytest.approx(10.047, abs=0.001)
    fake.heat_meter = None
    assert hp.HpCoordCoordinator.heat_step(fake, now) is None


def test_settings_errors_and_translations():
    from hc_thermostat import config_flow as cf
    keys = {str(k) for k in cf._hpc_settings({})}
    sec = cf.HPC_SECTIONS["heat_meter"]
    assert set(sec) <= keys and "hp_flow_out_temp_entity" in sec and "hm_cop_window_s" in sec
    base = {"hp_flow_min": 25, "hp_flow_max": 55, "hp_cold_on_below": 0, "hp_cold_release_above": 5,
            "hp_charge_on": 0, "hp_charge_off": 0}
    assert cf._hpc_errors(base) == {}
    assert cf._hpc_errors({**base, "hp_flow_out_temp_entity": "sensor.a"}) == {"hp_water_flow_entity": "heat_meter_three"}
    three = {"hp_flow_out_temp_entity": "sensor.a", "hp_flow_in_temp_entity": "sensor.a", "hp_water_flow_entity": "sensor.f"}
    assert cf._hpc_errors({**base, **three}) == {"hp_flow_in_temp_entity": "heat_meter_same"}
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        for top in ("config", "options"):
            s = tr[top]["step"]["hp_coord_settings"]["sections"]["heat_meter"]
            assert s["name"] and all(s["data"][k] and s["data_description"][k] for k in sec)
            assert tr[top]["error"]["heat_meter_three"] and tr[top]["error"]["heat_meter_same"]
        for k in ("hp_heat_power", "hp_heat_energy", "hp_heat_energy_today", "hp_cop", "hp_cop_today"):
            assert tr["entity"]["sensor"][k]["name"]
        assert set(tr["selector"]["hm_power_scope"]["options"]) == {"unit", "compressor"}
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3")


def test_sensors_are_made_only_with_the_heat_meter():
    src = (BASE / "sensor.py").read_text()
    assert 'getattr(c, "heat_meter", None) is not None' in src
    for cls in ("HcHmPower", "HcHmEnergy", "HcHmEnergyToday", "HcHpCop", "HcHpCopToday"):
        assert f"class {cls}(" in src
    assert "SensorStateClass.TOTAL_INCREASING" in src


# --- 13: the chart ------------------------------------------------------------------------------------------------------
def test_hp_series_has_the_cop():
    info = importlib.import_module("hc_thermostat.info")
    ts = lambda m: SimpleNamespace(timestamp=lambda: T0.timestamp() + m * 60)  # noqa: E731
    S = lambda v, m: SimpleNamespace(state=v, attributes={}, last_updated=ts(m))  # noqa: E731
    out = info.hp_series({"sensor.cop": [S("3.9", 0), S("4.1", 5), S("unavailable", 9), S("4.0", 30)]},
                         {"cop": "sensor.cop"})
    assert [p[1] for p in out["cop"]] == [3.9, 4.1, None, 4.0]


def test_hp_chart_with_the_cop_curve():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    t0 = 1_763_272_800_000
    hist = {"start": t0, "end": t0 + 86_400_000, "series": {
        "raw": [[t0, 36.2]], "target": [[t0, 36.5]],
        "cop": [[t0, 3.9], [t0 + 600_000, 4.1], [t0 + 900_000, None], [t0 + 3_600_000, 4.0], [t0 + 3_900_000, 4.2]]}}
    ov = (BASE / "www" / "hc-overview.js").as_uri()
    script = f"""
import * as OV from {json.dumps(ov)};
const h = {json.dumps(hist)};
console.log(JSON.stringify({{ on: OV.hpChartSvg(h, {{ lang: "hu" }}), off: OV.hpChartSvg(h, {{ lang: "en", cop: false }}) }}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert "aktuális COP (jobb tengely)" in r["on"] and ">COP<" in r["on"]
    cop_path = [p for p in r["on"].split("<path ") if 'stroke="#00897b"' in p.split(">")[0]][0].split(">")[0]
    assert cop_path.count("M") == 2  # broken at the missing value
    assert "COP" not in r["off"].replace("hccurve", "")
    js = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "_heatRows" in js and "data-cop" in js and "hc-info:cop" in js

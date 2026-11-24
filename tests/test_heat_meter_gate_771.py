"""Production-only heat metering: compressor-Hz priority and a separate 200 W fallback threshold."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
from core.heat_meter import HeatMeter, HeatMeterConfig, HmSample  # noqa: E402

T0 = datetime(2026, 11, 18, 17, 0, tzinfo=timezone.utc)


def sample(sec, watts=2500, delta=3, flow=48, **kw):
    return HmSample(T0 + timedelta(seconds=sec), 41 + delta, 41, flow, watts, **kw)


def test_pump_only_frost_circulation_never_creates_produced_heat():
    m = HeatMeter()
    for t in range(0, 601, 30):
        out = m.step(sample(t, watts=80, delta=1))
    assert out["raw_power_kw"] == pytest.approx(3.349, abs=0.001)
    assert out["power_kw"] == 0
    assert out["heat_reason"] == "not_running"
    assert m.total_kwh == 0
    assert out["cop"] is None


def test_compressor_heat_is_counted_above_200_w():
    m = HeatMeter()
    for t in range(0, 3601, 30):
        out = m.step(sample(t, watts=2500))
    assert out["power_kw"] == pytest.approx(10.047, abs=0.001)
    assert m.total_kwh == pytest.approx(10.04688, abs=0.005)
    assert out["heat_gate"] == "electric_power"
    assert out["heat_min_power_w"] == 200


def test_threshold_is_independent_of_hp_running_threshold():
    m = HeatMeter(HeatMeterConfig(hm_heat_min_power_w=200))
    assert m.step(sample(0, watts=150, running_w=100))["power_kw"] == 0
    assert m.step(sample(30, watts=200, running_w=100))["power_kw"] == 0
    assert m.step(sample(60, watts=201, running_w=100))["power_kw"] > 0
    assert m.total_kwh == 0  # first active sample starts the interval
    m.step(sample(90, watts=201))
    assert m.total_kwh > 0


def test_stop_restart_does_not_integrate_phantom_half_intervals():
    m = HeatMeter()
    m.step(sample(0))
    m.step(sample(30))
    old = m.total_kwh
    m.step(sample(60, watts=80, delta=1))
    m.step(sample(90, watts=80, delta=1))
    assert m.total_kwh == old
    m.step(sample(120))
    assert m.total_kwh == old  # first compressor-ON sample is new baseline
    m.step(sample(150))
    assert m.total_kwh > old


def test_hz_overrides_watts_and_0_hz_produces_nothing():
    m = HeatMeter()
    for t in range(0, 301, 30):
        out = m.step(sample(t, watts=80, compressor_source=True, compressor_active=True))
    assert m.total_kwh > 0  # valid compressor Hz can measure heat without an eligible COP
    assert out["cop"] is None
    old = m.total_kwh
    for t in range(330, 481, 30):
        out = m.step(sample(t, watts=2500, compressor_source=True, compressor_active=False))
    assert out["power_kw"] == 0 and out["heat_reason"] == "not_running"
    assert m.total_kwh == old


def test_missing_hz_never_falls_back_to_high_watts():
    m = HeatMeter()
    m.step(sample(0, watts=2500, compressor_source=True, compressor_active=True))
    m.step(sample(30, watts=2500, compressor_source=True, compressor_active=True))
    old = m.total_kwh
    out = m.step(sample(60, watts=2500, compressor_source=True, compressor_active=None))
    assert out["power_kw"] is None and out["heat_reason"] == "stale_compressor"
    m.step(sample(90, watts=2500, compressor_source=True, compressor_active=True))
    assert m.total_kwh == old
    m.step(sample(120, watts=2500, compressor_source=True, compressor_active=True))
    assert m.total_kwh > old


def test_no_signal_configured_keeps_metering_but_unconfirmed():
    m = HeatMeter()
    for t in range(0, 601, 30):
        out = m.step(sample(t, watts=None, power_source=False))
    assert m.total_kwh > 0 and out["power_kw"] > 0
    assert out["heat_gate"] == "none" and out["heat_confirmed"] is False


def test_configured_but_stale_power_still_pauses_counter():
    m = HeatMeter()
    for t in range(0, 601, 30):
        out = m.step(sample(t, watts=None, power_source=True))
    assert m.total_kwh == 0 and out["power_kw"] is None
    assert out["heat_reason"] == "stale_power"


def test_confirmed_when_power_above_threshold():
    m = HeatMeter()
    for t in range(0, 121, 30):
        out = m.step(sample(t, watts=2500))
    assert out["heat_confirmed"] is True and out["heat_gate"] == "electric_power"


def test_defrost_is_not_production_even_with_compressor_running():
    m = HeatMeter()
    for t in range(0, 301, 30):
        out = m.step(sample(t, watts=2500, compressor_source=True, compressor_active=True, busy=True))
    assert m.total_kwh == 0 and out["power_kw"] == 0
    assert out["heat_reason"] == "defrost"


def test_read_hz_needs_correct_unit_fresh_nonnegative_value():
    hp = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    def st(v, unit, age=0):
        stamp = T0 - timedelta(seconds=age)
        return SimpleNamespace(state=v, attributes={"unit_of_measurement": unit},
                               last_reported=stamp, last_updated=stamp)
    values = {"sensor.hz": st("45", "Hz"), "sensor.stop": st("0", "Hz"),
              "sensor.old": st("45", "Hz", 601), "sensor.fake": st("1", "kW"),
              "sensor.bad": st("nan", "Hz")}
    hass = SimpleNamespace(states=SimpleNamespace(get=values.get))
    assert hp.read_compressor_active(hass, "sensor.hz", T0, 300) is True
    assert hp.read_compressor_active(hass, "sensor.stop", T0, 300) is False
    for eid in ("sensor.old", "sensor.fake", "sensor.bad", "sensor.missing"):
        assert hp.read_compressor_active(hass, eid, T0, 300) is None


def test_coordinator_hz_override_even_with_low_power():
    hp = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    def st(v, unit):
        return SimpleNamespace(state=v, attributes={"unit_of_measurement": unit},
                               last_reported=T0, last_updated=T0, entity_id="sensor.test")
    d = {"sensor.out": st("44", "°C"), "sensor.in": st("41", "°C"),
         "sensor.flow": st("48", "L/min"), "sensor.power": st("80", "W"),
         "sensor.hz": st("47", "Hz")}
    conf = {"hp_flow_out_temp_entity": "sensor.out", "hp_flow_in_temp_entity": "sensor.in",
            "hp_water_flow_entity": "sensor.flow", "hp_power_entity": "sensor.power",
            "hm_compressor_entity": "sensor.hz"}
    fake = SimpleNamespace(hass=SimpleNamespace(states=SimpleNamespace(get=d.get)), conf=conf,
                           heat_meter=HeatMeter(), hp=SimpleNamespace(cfg=SimpleNamespace(hp_running_w=100)))
    fake.power_entity = lambda: hp.HpCoordCoordinator.power_entity(fake)
    info = hp.HpCoordCoordinator.heat_step(fake, T0)
    assert info["power_kw"] == pytest.approx(10.047, abs=0.001)
    assert info["heat_gate"] == "compressor_hz" and info["compressor_entity"] == "sensor.hz"

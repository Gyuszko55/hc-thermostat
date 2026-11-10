"""0.32.0: district heating (zone valve, TRV heads, return limit) and the fan coil (fan follows the valve)."""

from datetime import datetime, timedelta, timezone

from core.fancoil import FanCoil
from core.matrix import Status, cell, controls, default_timing, source_defaults
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


# --- matrix ------------------------------------------------------------------------------------------------------
def test_district_heating_cells_and_controls():
    assert cell("radiator_single", "district_heating").status == Status.RECOMMENDED
    assert cell("radiator_trv", "district_heating").status == Status.RECOMMENDED
    assert cell("mixed_rtl", "district_heating").status == Status.POSSIBLE
    assert cell("room_unit", "district_heating").status == Status.NOT_RECOMMENDED
    assert controls("district_heating") == ["tpi", "pid", "external"]
    assert default_timing("radiator_single", "district_heating") == {"cycle_s": 1800.0, "min_on_s": 600.0, "min_off_s": 300.0}


def test_fan_coil_cells_and_controls():
    for source in ("onoff_boiler", "modulating_boiler", "heat_pump", "district_heating"):
        assert cell("fan_coil", source).status == Status.RECOMMENDED
        assert controls(source, "fan_coil") == ["tpi", "pid", "external"]
    assert cell("fan_coil", "electric_heater").status == Status.NOT_RECOMMENDED
    assert controls("heat_pump") == ["curve", "onoff", "external"]  # elsewhere unchanged
    assert source_defaults("fan_coil", "heat_pump") == {"fan_coil": True}  # the valve, not the heat pump, is switched
    assert default_timing("fan_coil", "heat_pump")["cycle_s"] == 900.0


# --- fan ---------------------------------------------------------------------------------------------------------
def fan(**kw):
    return FanCoil(HcConfig.from_mapping({"fan_min_pct": 30, "fan_overrun_s": 120, "fan_min_coil": 30, **kw}))


def test_fan_follows_the_demand_and_runs_on():
    f = fan()
    assert f.step(at(0), True, 0.5, None) == (65, "heating")  # 30 + 70 × 0.5 = 65
    assert f.step(at(1), True, 1.0, None) == (100, "heating")
    assert f.step(at(2), False, 0.0, None) == (30, "overrun")
    assert f.step(at(3), False, 0.0, None) == (30, "overrun")
    assert f.step(at(5), False, 0.0, None) == (0, "off")


def test_no_cold_draught():
    f = fan()
    assert f.step(at(0), True, 0.8, 22.0) == (0, "cold_coil")
    assert f.step(at(2), True, 0.8, 35.0)[1] == "heating"


def test_fan_coil_instance_reports_the_fan():
    sup = Supervisor(HcConfig.from_mapping({**source_defaults("fan_coil", "heat_pump"), **default_timing("fan_coil", "heat_pump"),
                                            **DAY, "control": "pid"}))
    d = sup.step(Inputs(now=at(0), indoor=Reading(18.0), outdoor=Reading(0.0)))
    assert d.output and d.details["fan_why"] == "heating" and d.details["fan_pct"] >= 30
    assert "Ventilátor" in explain(d, "hu")


# --- return limit ----------------------------------------------------------------------------------------------------
def test_return_limit_closes_the_valve_with_hysteresis():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi", "return_max": 45.0, "cycle_s": 1800, "min_on_s": 600}))
    step = lambda m, r: sup.step(Inputs(now=at(m), indoor=Reading(18.0), outdoor=Reading(0.0), return_temp=Reading(r)))
    assert step(0, 40.0).output
    d = step(1, 46.0)  # inside the minimum run, still closes
    assert not d.output and d.limited_by == "return_limit" and d.details["return"] == 46.0
    assert "Visszatérő-korlát: a visszatérő víz 46 °C (határ 45 °C)" in explain(d, "hu")
    assert step(10, 43.0).limited_by == "return_limit"  # within 3 °C
    assert step(20, 41.5).output


def test_no_return_limit_by_default():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi"}))
    d = sup.step(Inputs(now=at(0), indoor=Reading(18.0), outdoor=Reading(0.0), return_temp=Reading(60.0)))
    assert d.output and "fan_pct" not in d.details

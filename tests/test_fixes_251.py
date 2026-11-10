"""0.25.1: fixes from an outside review – AC frost setpoint in the unit's range, patient floor sensor while the relay
is off, relay mode for a modulating boiler, the floor limit in curve mode, a default limit for a water floor."""

from datetime import datetime, timedelta, timezone

from core.matrix import controls, source_defaults
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def test_ac_frost_setpoint_fits_the_unit():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "ac"}))
    d = sup.step(Inputs(now=at(0), indoor=Reading(6.0), outdoor=Reading(-8.0), unit_min=16.0, unit_max=30.0, unit_step=1.0))
    assert d.reason == Reason.FROST
    assert d.external.hvac == "heat" and d.external.target == 16.0  # was 8 °C, which the unit refuses


def test_ac_lost_sensor_target_fits_the_unit():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "ac", "target_home": 14.0}))
    d = sup.step(Inputs(now=at(0), indoor=Reading(), outdoor=Reading(-8.0), unit_min=16.0, unit_max=30.0))
    assert d.external.hvac == "heat" and d.external.target == 16.0


def efloor(**kw):
    return Supervisor(HcConfig.from_mapping({**source_defaults("floor_single", "electric_heater"), **DAY,
                                             "control": "tpi", "cycle_s": 1800, "min_on_s": 300, "min_off_s": 300, **kw}))


def test_a_silent_cold_floor_sensor_does_not_block_the_start():
    sup = efloor()
    d = sup.step(Inputs(now=at(0), indoor=Reading(18.0), outdoor=Reading(0.0), floor=Reading(20.0, age_s=3600)))
    assert d.reason == Reason.REGULATING and d.output  # an hour old, relay off: still believed
    d = sup.step(Inputs(now=at(1), indoor=Reading(18.0), outdoor=Reading(0.0), floor=Reading(20.0, age_s=8000)))
    assert d.reason == Reason.FLOOR_LIMIT and d.details["floor_why"] == "lost" and not d.output


def test_while_heating_a_silent_floor_sensor_stops_sooner():
    sup = efloor()
    assert sup.step(Inputs(now=at(0), indoor=Reading(18.0), outdoor=Reading(0.0), floor=Reading(22.0))).output
    d = sup.step(Inputs(now=at(1), indoor=Reading(18.0), outdoor=Reading(0.0), floor=Reading(22.0, age_s=2000)))
    assert d.reason == Reason.FLOOR_LIMIT and not d.output  # heating and silent for half an hour


def test_modulating_boiler_offers_relay_mode():
    assert controls("modulating_boiler") == ["curve", "tpi", "pid", "external"]
    assert controls("onoff_boiler") == ["tpi", "pid", "external"]
    assert controls("heat_pump") == ["curve", "onoff", "external"]  # 0.26.0: on/off with long runs
    assert controls("air_conditioner") == ["ac", "external"]
    assert controls("electric_heater") == ["tpi", "pid", "external"]


def test_curve_mode_floor_limit_stops_at_once():
    cfg = HcConfig.from_mapping({**DAY, "control": "curve", "floor_max": 29.0, "heat_pump": True})
    sup = Supervisor(cfg)
    d = sup.step(Inputs(now=at(0), indoor=Reading(19.0), outdoor=Reading(0.0), floor=Reading(25.0)))
    assert d.output and d.flow_setpoint is not None
    d = sup.step(Inputs(now=at(2), indoor=Reading(19.0), outdoor=Reading(0.0), floor=Reading(29.2)))
    assert d.reason == Reason.FLOOR_LIMIT and not d.output and d.flow_setpoint is None  # not after 20 minutes


def test_water_floor_has_a_default_limit():
    assert source_defaults("floor_single", "onoff_boiler") == {"floor_max": 29.0}
    assert source_defaults("floor_zones", "heat_pump") == {"floor_max": 29.0, "heat_pump": True}
    assert source_defaults("radiator_single", "onoff_boiler") == {}
    sup = Supervisor(HcConfig.from_mapping({**source_defaults("floor_single", "onoff_boiler"), **DAY, "control": "tpi"}))
    assert sup.step(Inputs(now=at(0), indoor=Reading(18.0), outdoor=Reading(0.0))).reason == Reason.REGULATING  # no sensor: no limit
    assert sup.step(Inputs(now=at(1), indoor=Reading(18.0), outdoor=Reading(0.0), floor=Reading(29.5))).reason == Reason.FLOOR_LIMIT

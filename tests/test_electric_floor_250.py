"""0.25.0: electric floor heating (matrix, long cycle), floor temperature limit, no blind heat on a lost sensor for
electric heat, and a target taken over from a source entity (a wall thermostat's knob)."""

from datetime import datetime, timedelta, timezone

from core.matrix import Status, cell, default_timing, electric_floor, source_defaults
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor
from core.target_source import TargetFollower, WriteLog, source_value

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def electric_floor_cfg(**kw):
    return HcConfig.from_mapping({**source_defaults("floor_single", "electric_heater"),
                                  **default_timing("floor_single", "electric_heater"), **DAY, **kw})


def step(sup, minute, indoor=19.0, floor=22.0, outdoor=5.0):
    return sup.step(Inputs(now=at(minute), indoor=Reading(indoor), outdoor=Reading(outdoor),
                           floor=Reading(floor) if floor is not None else Reading()))


# --- matrix ------------------------------------------------------------------------------------------------
def test_electric_floor_is_a_recommended_combination():
    for system in ("floor_single", "floor_zones"):
        assert electric_floor(system, "electric_heater")
        c = cell(system, "electric_heater")
        assert c.status == Status.RECOMMENDED and "padlóhőfok-limit" in c.text_hu
    assert cell("radiator_single", "electric_heater").status == Status.NOT_RECOMMENDED  # still not a radiator source
    assert cell("room_unit", "electric_heater").status == Status.RECOMMENDED


def test_electric_floor_gets_a_30_minute_cycle():
    assert default_timing("floor_single", "electric_heater") == {"cycle_s": 1800.0, "min_on_s": 300.0, "min_off_s": 300.0}
    assert default_timing("floor_single", "onoff_boiler")["cycle_s"] == 3600.0  # a water floor keeps its long cycle
    assert default_timing("room_unit", "electric_heater")["cycle_s"] == 600.0
    assert default_timing("floor_single")["cycle_s"] == 3600.0  # old callers without a source


def test_source_defaults():
    assert source_defaults("floor_single", "electric_heater") == {"sensor_lost_demand": 0.0, "floor_max": 27.0, "floor_required": True}
    assert source_defaults("room_unit", "electric_heater") == {"sensor_lost_demand": 0.0}
    assert source_defaults("radiator_single", "onoff_boiler") == {}
    # an explicit setting of the instance wins over the default
    cfg = HcConfig.from_mapping({**source_defaults("floor_single", "electric_heater"), "floor_max": 29.0})
    assert cfg.floor_max == 29.0 and cfg.floor_required


# --- floor limit -------------------------------------------------------------------------------------------
def test_floor_limit_stops_at_once_and_releases_with_hysteresis():
    sup = Supervisor(electric_floor_cfg(control="tpi"))
    d = step(sup, 0, indoor=18.0, floor=24.0)
    assert d.reason == Reason.REGULATING and d.output  # cold room, floor fine: heats
    d = step(sup, 1, indoor=18.0, floor=27.0)  # one minute later, inside the minimum run time
    assert d.reason == Reason.FLOOR_LIMIT and not d.output and d.demand == 0
    assert d.details["floor"] == 27.0 and d.details["floor_max"] == 27.0
    d = step(sup, 10, indoor=18.0, floor=26.5)  # still within the hysteresis: stays off
    assert d.reason == Reason.FLOOR_LIMIT and not d.output
    d = step(sup, 20, indoor=18.0, floor=25.9)  # 1.1 °C below: free again (after the minimum pause)
    assert d.reason == Reason.REGULATING


def test_floor_limit_wins_over_boost_and_frost():
    sup = Supervisor(electric_floor_cfg(control="tpi", boost_enabled=True))
    d = step(sup, 0, indoor=15.0, floor=28.0)
    assert d.reason == Reason.FLOOR_LIMIT and not d.output
    sup = Supervisor(electric_floor_cfg(control="tpi"))
    d = step(sup, 0, indoor=5.0, floor=28.0)  # frost by the room, but the floor is hot: no heat
    assert d.reason == Reason.FLOOR_LIMIT and not d.output


def test_electric_floor_does_not_heat_without_a_fresh_floor_reading():
    sup = Supervisor(electric_floor_cfg(control="pid"))
    d = step(sup, 0, indoor=18.0, floor=None)
    assert d.reason == Reason.FLOOR_LIMIT and not d.output and d.details["floor_why"] == "lost"
    assert "Padlószenzor nélkül nem fűt" in explain(d, "hu")
    old = sup.step(Inputs(now=at(5), indoor=Reading(18.0), outdoor=Reading(5.0), floor=Reading(24.0, age_s=8000)))
    assert old.reason == Reason.FLOOR_LIMIT  # a reading older than 2 hours does not count (0.25.1: 2 h with the relay off)


def test_water_floor_limit_is_optional():
    cfg = HcConfig.from_mapping({**DAY, "control": "tpi"})
    sup = Supervisor(cfg)
    assert step(sup, 0, indoor=18.0, floor=None).reason == Reason.REGULATING  # no limit set: nothing changes
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi", "floor_max": 29.0}))
    assert step(sup, 0, indoor=18.0, floor=None).reason == Reason.REGULATING  # no reading, not required: heats
    assert step(sup, 1, indoor=18.0, floor=29.5).reason == Reason.FLOOR_LIMIT


def test_floor_limit_switches_an_external_thermostat_off():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "external", "floor_max": 27.0}))
    d = step(sup, 0, indoor=18.0, floor=27.5)
    assert d.reason == Reason.FLOOR_LIMIT and d.external.hvac == "off"
    d = step(sup, 1, indoor=18.0, floor=25.0)
    assert d.reason == Reason.EXTERNAL and d.external.hvac == "heat"


def test_floor_reading_shows_in_the_details():
    sup = Supervisor(electric_floor_cfg(control="tpi"))
    d = step(sup, 0, indoor=18.0, floor=23.4)
    assert d.details["floor"] == 23.4
    text = explain(step(sup, 1, indoor=18.0, floor=27.2), "hu")
    assert "Padlóhőfok-limit: a padló 27,2 °C, a határ 27 °C" in text


# --- lost indoor sensor --------------------------------------------------------------------------------------
def test_electric_heat_does_not_run_blind():
    sup = Supervisor(electric_floor_cfg(control="tpi"))
    d = step(sup, 0, indoor=None, floor=22.0, outdoor=-5.0)
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0 and not d.output
    assert "vakon nem fűt" in explain(d, "hu")
    heater = Supervisor(HcConfig.from_mapping({**source_defaults("room_unit", "electric_heater"), **DAY, "control": "tpi"}))
    assert step(heater, 0, indoor=None, floor=None, outdoor=-5.0).demand == 0


def test_floor_sensor_still_guards_against_frost():
    sup = Supervisor(electric_floor_cfg(control="tpi"))
    d = step(sup, 0, indoor=None, floor=6.0, outdoor=-10.0)
    assert d.reason == Reason.FROST and d.output


def test_a_boiler_keeps_its_fallback():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi"}))
    d = step(sup, 0, indoor=None, floor=None, outdoor=-5.0)
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0.35
    assert "vakon" not in explain(d, "hu")


# --- target source ---------------------------------------------------------------------------------------------
def test_follower_takes_over_a_turned_knob_but_not_its_own_start_value():
    f = TargetFollower()
    assert f.changed(21.0, 21.0, False) is None  # first look: only remembered
    assert f.changed(21.0, 21.0, False) is None  # unchanged
    assert f.changed(22.5, 21.0, False) == 22.5  # turned by hand
    assert f.changed(22.5, 22.5, False) is None
    assert f.changed(None, 22.5, False) is None  # unavailable: nothing


def test_follower_ignores_what_an_hc_instance_wrote():
    f = TargetFollower()
    f.changed(21.0, 21.0, False)
    assert f.changed(19.0, 21.0, True) is None  # the schedule of the instance that controls the wall thermostat
    assert f.changed(20.0, 21.0, False) == 20.0
    assert f.changed(21.0, 21.0, False) is None  # already the target here


def test_write_log():
    log = WriteLog()
    log.note("climate.wall", 21.0, T0)
    assert log.recent("climate.wall", 21.0, T0 + timedelta(seconds=60))
    assert not log.recent("climate.wall", 21.5, T0 + timedelta(seconds=60))
    assert not log.recent("climate.wall", 21.0, T0 + timedelta(seconds=300))
    assert not log.recent("climate.other", 21.0, T0)


def test_source_value():
    assert source_value("climate", "heat", {"temperature": 22.5}) == 22.5
    assert source_value("climate", "off", {"temperature": None}) is None
    assert source_value("number", "21.5", {}) == 21.5
    assert source_value("input_number", "unavailable", {}) is None
    assert source_value("number", "abc", {}) is None

"""0.39.3: fixes from the second outside review (first made on 0.33.0).

1. On/off control (heat pump, pellet boiler) with a lost room sensor: the fallback demand is a share of the time.
2. Central modulating boiler: a floor zone without its own mixing loop caps the flow setpoint.
3. Storage heater with a power signal: the hours really charged are counted, lost blocks are made up.
4. Buffer tank: old readings do not count, and a charge cannot run without end.
5. Fan coil: a fan with speed steps is not commanded again at every update.
"""

from datetime import datetime, timedelta, timezone

from core.buffer import BufferCharger, BufferConfig, fresh
from core.central import CentralBoiler, CentralConfig, ZoneState
from core.curve import zone_flow_limit
from core.fancoil import fan_at_level, fan_level
from core.matrix import default_timing, source_defaults
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


# --- 1. on/off control without a room reading -----------------------------------------------------------------
def _run_lost(sup, minutes, outdoor=0.0):
    """Minutes the source is on over a period, with no room reading (the restart grace is long over)."""
    on = 0
    for m in range(minutes):
        d = sup.step(Inputs(now=at(m), indoor=Reading(None), outdoor=Reading(outdoor), uptime_s=10_000))
        assert d.reason == Reason.SENSOR_LOST
        on += d.output
    return on


def test_heat_pump_without_a_room_reading_runs_a_share_of_the_time():
    cfg = HcConfig.from_mapping({**source_defaults("floor_single", "heat_pump"), **DAY, "control": "onoff"})
    on = _run_lost(Supervisor(cfg), 600)
    assert 0.25 <= on / 600 <= 0.5  # about the 35 % fallback, in minimum runs – not without end


def test_pellet_boiler_without_a_room_reading_pauses_too():
    cfg = HcConfig.from_mapping({**default_timing("radiator_single", "pellet_boiler"), **DAY, "control": "onoff"})
    sup = Supervisor(cfg)
    on = _run_lost(sup, 600)
    assert 0 < on < 600 * 0.85  # 45 minute burns with at least the 20 minute pause between them
    d = sup.step(Inputs(now=at(600), indoor=Reading(None), outdoor=Reading(0.0), uptime_s=10_000))
    assert d.details["fallback_run_s"] == 2700 and d.details["fallback_pause_s"] >= 1200


def test_on_off_with_a_room_reading_is_unchanged():
    cfg = HcConfig.from_mapping({**source_defaults("floor_single", "heat_pump"), **DAY, "control": "onoff"})
    sup = Supervisor(cfg)
    assert sup.step(Inputs(now=at(0), indoor=Reading(20.0), outdoor=Reading(0.0))).output
    assert sup.step(Inputs(now=at(60), indoor=Reading(20.5), outdoor=Reading(0.0))).output  # until the target


# --- 2. a floor zone caps the central flow ----------------------------------------------------------------------
def zone(name, flow=None, wants=True, limit=None, **kw):
    return ZoneState(name, wants, demand=0.5 if wants else 0.0, valve_open=True if wants else None,
                     valve_on_since=T0 if wants else None, trv=True, flow_request=flow, flow_limit=limit, **kw)


def test_floor_zone_without_a_mixer_caps_the_flow():
    boiler = CentralBoiler(CentralConfig())
    d = boiler.step(T0, [zone("floor", 32.0, limit=45.0), zone("radiators", 62.0)])
    assert d.output and d.flow_setpoint == 45.0 and d.details["flow_capped_by"] == "floor"
    assert d.details["flow_by"] == "radiators"


def test_no_cap_when_the_floor_zone_is_shut_or_has_its_own_mixer():
    boiler = CentralBoiler(CentralConfig())
    d = boiler.step(T0, [zone("floor", wants=False, limit=45.0), zone("radiators", 62.0)])
    assert d.flow_setpoint == 62.0 and "flow_capped_by" not in d.details
    d = CentralBoiler(CentralConfig()).step(T0, [zone("floor", 32.0), zone("radiators", 62.0)])  # own mixer: no limit sent
    assert d.flow_setpoint == 62.0


def test_a_closing_floor_valve_still_caps_and_the_cap_beats_the_minimum():
    boiler = CentralBoiler(CentralConfig(central_valve_open_s=180, central_flow_min=50))
    closing = ZoneState("floor", False, valve_off_since=T0 - timedelta(seconds=60), flow_limit=45.0)
    d = boiler.step(T0, [closing, zone("radiators", 62.0)])
    assert d.flow_setpoint == 45.0  # below central_flow_min: the floor comes first
    later = ZoneState("floor", False, valve_off_since=T0 - timedelta(seconds=600), flow_limit=45.0)
    assert boiler.step(at(1), [later, zone("radiators", 62.0)]).flow_setpoint == 62.0


def test_zone_flow_limit_is_published_only_by_floor_zones_without_a_mixer():
    cfg = HcConfig.from_mapping({"flow_max": 45.0})
    assert zone_flow_limit({"role": "zone", "system": "floor_zones"}, cfg) == 45.0
    assert zone_flow_limit({"role": "zone", "system": "floor_zones", "zone_own_mixer": True}, cfg) is None
    assert zone_flow_limit({"role": "zone", "system": "radiator_zones"}, cfg) is None
    assert zone_flow_limit({"role": "standalone", "system": "floor_single"}, cfg) is None


# --- 3. storage heater: power in blocks -------------------------------------------------------------------------
def t(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=timezone.utc)


def _storage():
    return Supervisor(HcConfig.from_mapping({**DAY, "control": "storage", "target_home": 21.0, "storage_charge_h": 8.0,
                                             "curve_design_outdoor": -15.0}))


def _night(sup, power_at):
    """Step every 5 minutes through the 22:00–06:00 window; returns the minutes charged."""
    on, now = 0, t(10, 22)
    while now < t(11, 6):
        d = sup.step(Inputs(now=now, indoor=Reading(20.0), outdoor=Reading(3.0), outdoor_avg=3.0,
                            power_available=power_at(now)))
        on += 5 if d.output else 0
        now += timedelta(minutes=5)
    return on, d


def test_power_in_blocks_still_gives_the_whole_charge():
    # Half charge = 4 h. The power is on 22:00–00:00 and 03:00–06:00 only: timed to the end of the window
    # (02:00–06:00) only 3 hours would have been charged.
    on, d = _night(_storage(), lambda now: now < t(11, 0) or now >= t(11, 3))
    assert 235 <= on <= 245
    assert d.details["charge_why"] == "done" and "kész" in explain(d, "hu")


def test_with_a_signal_the_charge_stops_when_the_hours_are_full():
    on, d = _night(_storage(), lambda now: True)
    assert 235 <= on <= 245 and d.details["charged_h"] >= 4.0


def test_too_little_power_charges_all_it_can():
    on, d = _night(_storage(), lambda now: t(11, 1) <= now < t(11, 3))
    assert 115 <= on <= 125 and d.details["charge_why"] == "no_power"


def test_without_a_signal_the_charge_is_still_timed_to_the_end_of_the_window():
    sup = _storage()
    d = sup.step(Inputs(now=t(10, 23), indoor=Reading(20.0), outdoor=Reading(3.0), outdoor_avg=3.0))
    assert not d.output and d.details["charge_start"] == "02:00" and "charged_h" not in d.details


def test_charged_hours_survive_a_restart():
    sup = _storage()
    now = t(10, 22)
    while now < t(11, 0):
        sup.step(Inputs(now=now, indoor=Reading(20.0), outdoor=Reading(3.0), outdoor_avg=3.0, power_available=True))
        now += timedelta(minutes=5)
    again = _storage()
    again.storage.restore(sup.storage.state())
    d = again.step(Inputs(now=t(11, 0, 5), indoor=Reading(20.0), outdoor=Reading(3.0), outdoor_avg=3.0, power_available=True))
    assert d.output and 1.8 <= d.details["charged_h"] <= 2.1


# --- 4. buffer tank ---------------------------------------------------------------------------------------------
def test_old_tank_reading_does_not_count():
    assert fresh(40.0, 120.0, 3600.0) == 40.0
    assert fresh(40.0, 7200.0, 3600.0) is None  # the sensor died and kept its last value
    assert fresh(40.0, 7200.0, 0.0) == 40.0  # 0: any age
    assert fresh(None, 10.0, 3600.0) is None


def test_a_charge_cannot_run_without_end():
    b = BufferCharger(BufferConfig(buffer_max_charge_s=6 * 3600, buffer_min_off_s=1200))
    assert b.step(at(0), 40.0, 30.0).output
    assert b.step(at(359), 41.0, 30.0).output  # the bottom sensor is stuck: never "full"
    d = b.step(at(360), 41.0, 30.0)
    assert not d.output and d.reason == "max_charge"
    assert b.step(at(370), 41.0, 30.0).reason == "max_charge"  # still in the pause, and it says why
    assert b.step(at(381), 41.0, 30.0).output  # then it may try again


def test_max_charge_off_and_frost_waits_out_the_pause():
    b = BufferCharger(BufferConfig(buffer_max_charge_s=0))
    b.step(at(0), 40.0, 30.0)
    assert b.step(at(1000), 41.0, 30.0).output
    f = BufferCharger(BufferConfig(buffer_max_charge_s=3600, buffer_min_off_s=1200))
    f.step(at(0), 5.0, 5.0)
    assert f.step(at(60), 5.0, 5.0).reason == "max_charge"  # a frozen-looking tank that never warms: a stuck sensor
    assert not f.step(at(70), 5.0, 5.0).output
    assert f.step(at(81), 5.0, 5.0).reason == "frost"


def test_timed_out_state_survives_a_restart():
    b = BufferCharger(BufferConfig(buffer_max_charge_s=3600))
    b.step(at(0), 40.0, 30.0)
    b.step(at(60), 41.0, 30.0)
    again = BufferCharger(BufferConfig(buffer_max_charge_s=3600))
    again.restore(b.state())
    assert again.step(at(65), 41.0, 30.0).reason == "max_charge"


# --- 5. fan with speed steps ------------------------------------------------------------------------------------
def test_three_speed_fan_levels():
    step = 100 / 3
    assert fan_level(45, step) == (1, 33)
    assert fan_level(65, step) == (2, 66)
    assert fan_level(100, step) == (3, 100)
    assert fan_level(5, step) == (1, 33)  # running at all means at least the lowest speed
    assert fan_level(0, step) == (0, 0)
    assert fan_at_level(33, 1, step) and fan_at_level(66, 2, step) and not fan_at_level(66, 1, step)


def test_fine_fan_is_set_as_before():
    assert fan_level(45, 1) == (45, 45) and fan_level(45, None) == (45, 45)
    assert fan_at_level(45, 45, 1) and not fan_at_level(40, 45, None) and not fan_at_level(None, 45, None)


# --- 6. wall thermostat: lost contact, and tempering without a room thermometer (0.39.3) -------------------------
def _wall(system="radiator_single", source="onoff_boiler", **kw):
    from core.matrix import floor_system
    return Supervisor(HcConfig.from_mapping({**source_defaults(system, source), **default_timing(system, source), **DAY,
                                             "floor_system": floor_system(system), "demand_contact": True, **kw}))


def _wall_step(sup, minute, call, indoor=None, floor=None, now=None):
    return sup.step(Inputs(now=now or at(minute), indoor=Reading(indoor), outdoor=Reading(5.0), floor=Reading(floor),
                           call=call, uptime_s=10_000))


def test_lost_contact_with_a_room_reading_regulates_by_the_room():
    sup = _wall(control="tpi", target_home=21.0)
    d = _wall_step(sup, 0, None, indoor=25.0)  # warm room: no blind 35 % on top of it
    assert d.reason == Reason.AT_TARGET and not d.output and d.details["contact_lost"]
    assert "fali termosztát jele elveszett" in explain(d, "hu")
    sup = _wall(control="tpi", target_home=21.0)
    d = _wall_step(sup, 0, None, indoor=19.0)  # cold room: it heats, by its own target
    assert d.reason in (Reason.REGULATING, Reason.BOOST) and d.demand > 0 and d.details["contact_lost"]


def test_lost_contact_without_a_room_reading_is_the_lost_sensor_path():
    d = _wall_step(_wall(control="tpi"), 0, None)
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0.35 and "contact_lost" not in d.details


def test_contact_back_ends_the_backup():
    sup = _wall(control="tpi", target_home=21.0)
    _wall_step(sup, 0, None, indoor=19.0)
    d = _wall_step(sup, 1, False, indoor=19.0)
    assert d.reason == Reason.THERMOSTAT_IDLE and "contact_lost" not in d.details


def test_no_tempering_against_the_wall_thermostat_without_a_room_thermometer():
    floor = dict(system="floor_single", source="electric_heater", control="tpi", floor_temper=True)
    d = _wall_step(_wall(**floor), 0, False, floor=21.0)  # by day: the room target + offset means nothing here
    assert d.reason == Reason.THERMOSTAT_IDLE and not d.output
    night = dict(floor, night_start="22:00", night_end="06:00", floor_temper_night=24.0)
    d = _wall_step(_wall(**night), 0, False, floor=21.0, now=datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc))
    assert d.reason == Reason.FLOOR_TEMPER and d.output and d.details["floor_target"] == 24.0  # the absolute night value
    d = _wall_step(_wall(**night), 0, False, floor=21.0)  # the same instance by day: nothing
    assert d.reason == Reason.THERMOSTAT_IDLE


def test_tempering_with_a_room_thermometer_is_unchanged():
    floor = dict(system="floor_single", source="electric_heater", control="tpi", floor_temper=True, target_home=21.0)
    d = _wall_step(_wall(**floor), 0, False, indoor=21.2, floor=21.0)
    assert d.reason == Reason.FLOOR_TEMPER and d.output


# --- 1b. the on/off share stays behind the floor fallback (0.36.0) -----------------------------------------------
def test_on_off_floor_fallback_follows_the_floor_not_the_share():
    from core.matrix import floor_system
    cfg = HcConfig.from_mapping({**source_defaults("floor_single", "heat_pump"), **DAY, "control": "onoff",
                                 "floor_system": floor_system("floor_single"), "target_home": 21.0})
    sup = Supervisor(cfg)
    on = 0
    for m in range(120):  # the floor stays under its target: the heat pump runs on, well past one minimum run
        d = sup.step(Inputs(now=at(m), indoor=Reading(None), outdoor=Reading(0.0), floor=Reading(20.0), uptime_s=10_000))
        on += d.output
    assert d.details.get("floor_fallback") and "fallback_pause_s" not in d.details and on >= 115

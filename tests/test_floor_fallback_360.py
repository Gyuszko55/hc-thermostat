"""0.36.0: a lost room thermometer – the floor sensor keeps the floor warm instead of a blind demand."""

from datetime import datetime, timedelta, timezone

from core.matrix import default_timing, floor_system, source_defaults
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def cfg(system="floor_single", source="onoff_boiler", **kw):
    return HcConfig.from_mapping({**source_defaults(system, source), **default_timing(system, source), **DAY,
                                  "floor_system": floor_system(system), **kw})


def lost(sup, minute, floor=22.0, outdoor=5.0, **kw):
    return sup.step(Inputs(now=at(minute), indoor=Reading(), outdoor=Reading(outdoor),
                           floor=Reading(floor) if floor is not None else Reading(), **kw))


def test_on_by_default():
    assert HcConfig().floor_fallback


def test_electric_floor_continues_on_the_floor_sensor():
    sup = Supervisor(cfg(source="electric_heater", control="tpi"))
    d = lost(sup, 0, floor=22.0)  # target 21 + 2: the floor is held at 23 °C
    assert d.reason == Reason.SENSOR_LOST and d.demand == 1.0 and d.output
    assert d.details["floor_fallback"] and d.details["floor"] == 22.0 and d.details["floor_target"] == 23.0
    assert "no_blind" not in d.details
    d = lost(sup, 10, floor=23.0)  # warm enough: off (the minimum run of 5 minutes is over)
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0.0 and not d.output
    d = lost(sup, 20, floor=22.8)  # inside the hysteresis
    assert d.demand == 0.0
    d = lost(sup, 30, floor=22.7)
    assert d.demand == 1.0 and d.output


def test_water_floor_replaces_the_blind_percentage():
    sup = Supervisor(cfg(control="tpi"))
    d = lost(sup, 0, floor=24.0)
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0.0 and not d.output  # floor warm: no blind 35 %
    d = lost(sup, 10, floor=22.0)
    assert d.demand == 1.0 and d.output


def test_onoff_follows_the_floor():
    sup = Supervisor(cfg(source="heat_pump", control="onoff"))
    assert lost(sup, 0, floor=22.0).output
    d = lost(sup, 30, floor=23.2)
    assert d.reason == Reason.SENSOR_LOST and not d.output


def test_no_floor_reading_keeps_the_old_behaviour():
    sup = Supervisor(cfg(control="tpi"))
    d = lost(sup, 0, floor=None)
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0.35 and "floor_fallback" not in d.details
    sup = Supervisor(cfg(source="electric_heater", control="tpi"))
    d = lost(sup, 0, floor=None)  # electric floor: no floor reading, no heat (floor sensor required)
    assert not d.output and "floor_fallback" not in d.details


def test_option_off_keeps_the_old_behaviour():
    sup = Supervisor(cfg(control="tpi", floor_fallback=False))
    d = lost(sup, 0, floor=24.0)
    assert d.demand == 0.35
    sup = Supervisor(cfg(source="electric_heater", control="tpi", floor_fallback=False))
    d = lost(sup, 0, floor=22.0)
    assert d.demand == 0.0 and d.details.get("no_blind")


def test_other_systems_and_controls_keep_the_old_behaviour():
    sup = Supervisor(cfg(system="radiator_single", control="tpi"))
    assert lost(sup, 0, floor=22.0).demand == 0.35
    sup = Supervisor(cfg(source="modulating_boiler", control="curve"))
    d = lost(sup, 0, floor=22.0)
    assert "floor_fallback" not in d.details


def test_frost_first_floor_limit_wins_restart_waits():
    sup = Supervisor(cfg(source="electric_heater", control="tpi"))
    assert lost(sup, 0, floor=6.0).reason == Reason.FROST
    sup = Supervisor(cfg(control="tpi", floor_temper_offset=10.0))  # floor target 31 above the 29 limit
    d = lost(sup, 0, floor=29.5)
    assert d.reason == Reason.FLOOR_LIMIT and not d.output
    sup = Supervisor(cfg(control="tpi"))
    assert lost(sup, 0, floor=20.0, uptime_s=10).reason == Reason.RESTART_HOLD


def test_window_and_warm_weather_do_not_heat_the_floor():
    sup = Supervisor(cfg(control="tpi", window_delay_s=0))
    d = lost(sup, 0, floor=20.0, window_open=True)
    assert d.demand == 0.0 and not d.output
    sup = Supervisor(cfg(control="tpi"))
    d = lost(sup, 0, floor=20.0, outdoor=20.0)
    assert d.demand == 0.0 and not d.output


def test_night_value_counts_too():
    sup = Supervisor(cfg(control="tpi", floor_temper_night=20.0, night_start="22:00", night_end="06:00"))
    d = sup.step(Inputs(now=T0.replace(hour=23), indoor=Reading(), outdoor=Reading(5.0), floor=Reading(19.0)))
    assert d.details["floor_target"] == 20.0 and d.demand == 1.0


def test_texts():
    sup = Supervisor(cfg(source="electric_heater", control="tpi"))
    d = lost(sup, 0, floor=22.4)
    assert explain(d, "hu") == "A szobahőmérő nem jelez: a padlót tartom 23 °C-on (most 22,4 °C)."
    assert explain(d, "en") == "The room thermometer is silent: holding the floor at 23 °C (now 22.4 °C)."

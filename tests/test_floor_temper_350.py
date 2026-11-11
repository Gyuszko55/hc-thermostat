"""0.35.0: floor tempering – the floor slab is kept warm while the room is warm enough (opt-in)."""

from datetime import datetime, timedelta, timezone

from core.floor import temper_offset
from core.matrix import default_timing, floor_system, source_defaults
from core.messages import explain
from core.model import HcConfig, Inputs, Presence, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def cfg(system="floor_single", source="onoff_boiler", **kw):
    return HcConfig.from_mapping({**source_defaults(system, source), **default_timing(system, source), **DAY,
                                  "floor_system": floor_system(system), "floor_temper": True, **kw})


def step(sup, minute, indoor=21.5, floor=22.0, outdoor=5.0, **kw):
    return sup.step(Inputs(now=at(minute), indoor=Reading(indoor) if indoor is not None else Reading(),
                           outdoor=Reading(outdoor), floor=Reading(floor) if floor is not None else Reading(), **kw))


def test_default_offset_and_floor_system():
    assert temper_offset(0.0) == 2.0 and temper_offset(3.5) == 3.5
    assert HcConfig().temper_offset == 2.0
    assert floor_system("floor_single") and floor_system("floor_zones") and not floor_system("radiator_single")
    assert not HcConfig().floor_temper  # opt-in


def test_tempering_starts_and_stops_with_hysteresis():
    sup = Supervisor(cfg(control="tpi"))
    d = step(sup, 0, indoor=21.5, floor=22.0)  # the room is at target (21 + 0.3 overshoot), the floor below 23
    assert d.reason == Reason.FLOOR_TEMPER and d.demand == 1.0 and d.output
    assert d.details["floor"] == 22.0 and d.details["floor_target"] == 23.0
    d = step(sup, 20, indoor=21.5, floor=23.0)  # the floor reached its target: off (after the minimum run)
    assert d.reason == Reason.AT_TARGET and d.demand == 0.0 and not d.output
    d = step(sup, 40, indoor=21.5, floor=22.8)  # inside the hysteresis: stays off
    assert d.reason == Reason.AT_TARGET and not d.output
    d = step(sup, 60, indoor=21.5, floor=22.7)  # 0.3 °C below: on again
    assert d.reason == Reason.FLOOR_TEMPER and d.output


def test_room_margin_stops_tempering():
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, indoor=21.9, floor=22.0).reason == Reason.FLOOR_TEMPER
    d = step(sup, 20, indoor=22.0, floor=22.0)  # target 21 + margin 1.0: the room is warm, no more floor heat
    assert d.reason == Reason.AT_TARGET and not d.output


def test_regulating_demand_is_raised_only_when_lower():
    sup = Supervisor(cfg(control="tpi"))
    d = step(sup, 0, indoor=20.9, floor=21.0)  # just below the target: small regulator demand, cold floor
    assert d.reason == Reason.FLOOR_TEMPER and d.demand == 1.0 and d.output
    sup = Supervisor(cfg(control="tpi"))
    d = step(sup, 0, indoor=15.0, floor=21.0)  # a cold room asks for everything by itself
    assert d.reason == Reason.REGULATING and d.demand == 1.0


def test_night_value_is_an_absolute_floor_target():
    night = dict(night_start="22:00", night_end="06:00")
    sup = Supervisor(cfg(control="tpi", floor_temper_night=21.0, **night))
    d = sup.step(Inputs(now=T0.replace(hour=23), indoor=Reading(19.5), outdoor=Reading(5.0), floor=Reading(20.5)))
    assert d.reason == Reason.FLOOR_TEMPER and d.details["floor_target"] == 21.0  # target_night 19 (+2 would be 21 too)
    sup = Supervisor(cfg(control="tpi", floor_temper_night=20.0, **night))
    d = sup.step(Inputs(now=T0.replace(hour=23), indoor=Reading(19.5), outdoor=Reading(5.0), floor=Reading(20.5)))
    assert d.reason == Reason.AT_TARGET  # floor 20.5 above the night floor target 20
    sup = Supervisor(cfg(control="tpi", floor_temper_night=20.0, **night))
    d = sup.step(Inputs(now=T0.replace(hour=12), indoor=Reading(21.5), outdoor=Reading(5.0), floor=Reading(22.0)))
    assert d.details["floor_target"] == 23.0  # by day: target + offset


def test_sleep_preset_uses_the_night_value():
    sup = Supervisor(cfg(control="tpi", floor_temper_night=24.0))
    sup.set_preset("sleep", at(0))
    d = step(sup, 0, indoor=19.5, floor=22.0)
    assert d.reason == Reason.FLOOR_TEMPER and d.details["floor_target"] == 24.0


def test_floor_limit_wins():
    sup = Supervisor(cfg(control="tpi", floor_temper_offset=10.0))  # floor target 31, above the 29 limit
    d = step(sup, 0, indoor=21.5, floor=29.0)
    assert d.reason == Reason.FLOOR_LIMIT and not d.output


def test_window_off_and_summer_block_it():
    sup = Supervisor(cfg(control="tpi", window_delay_s=0))
    assert step(sup, 0, window_open=True).reason == Reason.WINDOW
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, enabled=False).reason == Reason.DISABLED
    sup = Supervisor(cfg(control="tpi", season_enabled=True))
    sup.season_on = False
    d = sup.step(Inputs(now=at(0), indoor=Reading(21.5), outdoor=Reading(20.0), outdoor_avg=20.0, floor=Reading(22.0)))
    assert d.reason == Reason.SEASON_OFF and not d.output


def test_frost_and_boost_stay():
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, indoor=5.0, floor=10.0).reason == Reason.FROST
    sup = Supervisor(cfg(control="tpi", boost_enabled=True))
    assert step(sup, 0, indoor=19.0, floor=20.0).reason == Reason.BOOST


def test_off_by_default_and_not_for_other_systems_or_controls():
    sup = Supervisor(cfg(control="tpi", floor_temper=False))
    assert step(sup, 0).reason == Reason.AT_TARGET
    sup = Supervisor(cfg(system="radiator_single", control="tpi"))  # no floor system
    assert step(sup, 0).reason == Reason.AT_TARGET
    for control in ("curve", "external"):
        sup = Supervisor(cfg(source="modulating_boiler", control=control))
        assert step(sup, 0).reason not in (Reason.FLOOR_TEMPER,)
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, floor=None).reason == Reason.AT_TARGET  # no floor reading: no tempering
    sup = Supervisor(cfg(control="tpi"))
    d = sup.step(Inputs(now=at(0), indoor=Reading(21.5), outdoor=Reading(5.0), floor=Reading(22.0, age_s=8000)))
    assert d.reason == Reason.AT_TARGET  # a stale floor reading does not count


def test_electric_floor_tempers_too():
    sup = Supervisor(cfg(source="electric_heater", control="pid"))
    d = step(sup, 0, indoor=21.5, floor=22.0)
    assert d.reason == Reason.FLOOR_TEMPER and d.output


def test_learning_is_not_fed_while_tempering():
    sup = Supervisor(cfg(control="tpi", learning_enabled=True, learning_settle_s=0))
    calls = []
    sup.learner.regulating = lambda *a: calls.append(a)
    step(sup, 0, indoor=20.9, floor=21.0)  # regulating, but the floor tempering raises the demand
    step(sup, 1, indoor=21.5, floor=21.0)  # at target, tempering
    assert calls == []
    step(sup, 2, indoor=21.5, floor=23.5)  # the floor is warm: an ordinary at-target minute counts again
    assert len(calls) == 1


def test_pwm_minimum_times_hold():
    sup = Supervisor(cfg(control="tpi"))  # water floor: 900 s minimum run and pause
    assert step(sup, 0, floor=22.0).output
    d = step(sup, 5, floor=23.2)  # tempering over after 5 minutes: the minimum run still holds
    assert d.reason == Reason.AT_TARGET and d.output and d.limited_by == "min_on"
    assert not step(sup, 16, floor=23.2).output
    d = step(sup, 20, floor=22.0)  # wants again inside the minimum pause
    assert d.reason == Reason.FLOOR_TEMPER and not d.output and d.limited_by == "min_off"
    assert step(sup, 32, floor=22.0).output


def test_onoff_tempering_run_does_not_become_a_regulating_run():
    sup = Supervisor(cfg(control="onoff"))
    d = step(sup, 0, indoor=20.9, floor=22.0)  # regulating band, the room alone would not start (21 - 0.3)
    assert d.reason == Reason.FLOOR_TEMPER and d.output
    d = step(sup, 20, indoor=20.9, floor=23.1)  # floor warm: off, the run was the tempering's
    assert d.reason == Reason.REGULATING and not d.output
    sup = Supervisor(cfg(control="onoff"))
    d = step(sup, 0, indoor=20.5, floor=22.0)  # the room itself asks: an ordinary run
    assert d.reason == Reason.REGULATING and d.output
    d = step(sup, 20, indoor=20.9, floor=23.1)
    assert d.reason == Reason.REGULATING and d.output  # runs on to the target as before


def test_texts():
    sup = Supervisor(cfg(control="tpi"))
    d = step(sup, 0, indoor=21.5, floor=22.4)
    assert explain(d, "hu") == "Padlótemperálás: a padló 22,4 °C, a cél 23 °C (a szoba már elég meleg)."
    assert explain(d, "en") == "Floor tempering: floor 22.4 °C, target 23 °C (the room is warm enough)."

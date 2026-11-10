"""0.26.0: heat pump – on/off control with long runs, adjustable minimum run and pause, defrost and hot water seen
as the heat pump's own work (no fault, no run without command)."""

from datetime import datetime, timedelta, timezone

from core.boiler_health import BoilerHealth, health_kind
from core.matrix import controls, source_defaults
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.regulators import controller_attributes
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def hp(**kw):
    return Supervisor(HcConfig.from_mapping({**source_defaults("floor_single", "heat_pump"), **DAY, "control": "onoff", **kw}))


def step(sup, minute, indoor, **kw):
    return sup.step(Inputs(now=at(minute), indoor=Reading(indoor), outdoor=Reading(2.0), **kw))


def test_heat_pump_offers_on_off():
    assert controls("heat_pump") == ["curve", "onoff", "external"]
    assert source_defaults("radiator_single", "heat_pump") == {"heat_pump": True}


def test_on_off_runs_long_and_waits_for_the_hysteresis():
    sup = hp()  # target 21, on below 20.7, off at 21.3; run at least 20 min, pause at least 10 min
    assert not step(sup, 0, 20.9).output  # inside the hysteresis: does not start
    d = step(sup, 1, 20.6)
    assert d.output and d.demand == 1.0 and d.reason == Reason.REGULATING
    assert step(sup, 5, 21.1).output  # on until the target is passed – no pulses
    d = step(sup, 8, 21.35)
    assert d.reason == Reason.AT_TARGET and d.output and d.limited_by == "min_on"  # only 7 minutes: runs on
    d = step(sup, 21, 21.4)
    assert not d.output  # 20 minutes reached
    assert not step(sup, 25, 20.8).output  # cooled a bit, still above 20.7
    d = step(sup, 27, 20.6)
    assert not d.output and d.limited_by == "min_off"  # wants to start, but the pause is 10 minutes
    assert step(sup, 31, 20.6).output


def test_minimum_times_are_adjustable():
    sup = hp(hp_min_on_s=1800, hp_min_off_s=900)
    assert step(sup, 0, 20.0).output
    assert step(sup, 25, 21.5).output  # 25 < 30 minutes
    assert not step(sup, 30, 21.5).output


def test_curve_uses_the_adjustable_times():
    sup = Supervisor(HcConfig.from_mapping({**source_defaults("floor_single", "heat_pump"), **DAY, "control": "curve",
                                            "hp_min_on_s": 2400}))
    assert step(sup, 0, 19.0).output
    d = step(sup, 30, 22.0)  # far above the target, but only 30 of 40 minutes
    assert d.output and d.limited_by == "min_on"


def test_floor_limit_stops_on_off_at_once():
    sup = hp(floor_max=29.0)
    assert step(sup, 0, 20.0, floor=Reading(25.0)).output
    d = step(sup, 2, 20.0, floor=Reading(29.1))
    assert d.reason == Reason.FLOOR_LIMIT and not d.output


def heat_long(sup, hp_mode=None):
    """Heats for 90 minutes while the house cools: a fault, unless the heat pump is busy elsewhere."""
    t, d = 20.0, None
    for m in range(0, 91):
        t -= 0.01
        d = sup.step(Inputs(now=at(m), indoor=Reading(t), outdoor=Reading(-5.0), actual_heating=True, hp_mode=hp_mode))
    return d


def test_defrost_and_hot_water_are_no_heating_fault():
    assert heat_long(hp()).fault
    assert not heat_long(hp(), "dhw").fault
    assert not heat_long(hp(), "defrost").fault


def test_decision_says_what_the_heat_pump_does():
    d = step(hp(), 0, 20.0, hp_mode="defrost")
    assert d.details["hp_mode"] == "defrost"
    assert "A hőszivattyú most leolvaszt" in explain(d, "hu")
    assert "makes hot water" in explain(step(hp(), 0, 20.0, hp_mode="dhw"), "en")


def run_health(kind, minutes, busy=False):
    h = BoilerHealth(HcConfig(power_burn_w=300.0), kind)
    state = "ok"
    for m in range(minutes + 1):
        state = h.update(at(m), relay_on=False, power=1500.0, flame=None, heating_fault=False, busy=busy)
    return state


def test_heat_pump_may_run_for_hot_water_without_command():
    assert health_kind("heat_pump") == "heat_pump"
    assert run_health("electric", 10) == "uncommanded_burn"  # an electric heater: 5 minutes is suspicious
    assert run_health("heat_pump", 30) == "ok"  # a heat pump making hot water by itself: like a combi boiler
    assert run_health("heat_pump", 50) == "uncommanded_burn"
    assert run_health("heat_pump", 60, busy=True) == "ok"  # it says so: never counted


def test_attributes():
    sup = hp()
    a = controller_attributes(sup.cfg, sup, 1.0, T0)
    assert a["onoff_hysteresis"] == 0.3 and a["hp_min_on_s"] == 1200.0 and a["hp_min_off_s"] == 600.0

"""Stage 3: the central boiler reads its zone thermostats."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
cc = importlib.import_module("hc_thermostat.central_coordinator")
central = importlib.import_module("hc_thermostat.core.central")

T0 = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)


def _hass(states):
    return SimpleNamespace(states=SimpleNamespace(get=lambda e: states.get(e)))


def _zone(action, control="tpi", demand=40, fault=False, state="heat"):
    return SimpleNamespace(state=state, attributes={"hvac_action": action, "control_type": control, "demand": demand,
                                                    "fault": fault})


def test_relay_zone_waits_for_the_valve_then_the_boiler_starts():
    states = {"climate.floor": _zone("heating")}
    valve_on = {}
    boiler = central.CentralBoiler()
    zones = cc.read_zones(_hass(states), ["climate.floor"], valve_on, T0)
    assert zones[0].wants_heat and zones[0].valve_open is None and zones[0].demand == 0.4
    assert boiler.step(T0, zones).reason == "waiting_valves"
    later = T0 + timedelta(minutes=3)
    zones = cc.read_zones(_hass(states), ["climate.floor"], valve_on, later)
    assert zones[0].valve_on_since == T0  # remembered from the first time
    assert boiler.step(later, zones).output is True


def test_trv_zone_counts_open_at_once():
    states = {"climate.bedroom": _zone("heating", control="external")}
    zones = cc.read_zones(_hass(states), ["climate.bedroom"], {}, T0)
    assert zones[0].valve_open is True
    assert central.CentralBoiler().step(T0, zones).output is True


def test_idle_or_off_zone_does_not_ask_and_forgets_its_valve_time():
    valve_on = {"climate.a": T0}
    zones = cc.read_zones(_hass({"climate.a": _zone("idle")}), ["climate.a"], valve_on, T0)
    assert not zones[0].wants_heat and "climate.a" not in valve_on
    zones = cc.read_zones(_hass({"climate.a": _zone("heating", state="off")}), ["climate.a"], {}, T0)
    assert not zones[0].wants_heat


def test_missing_or_faulty_zone_is_a_fault():
    zones = cc.read_zones(_hass({"climate.b": _zone("heating", fault=True)}), ["climate.a", "climate.b"], {}, T0)
    assert zones[0].fault and zones[1].fault
    assert central.CentralBoiler().step(T0, zones).output is False


def _fb(state, **attrs):
    return SimpleNamespace(state=state, attributes=attrs)


def _fb_zone(action="heating"):
    z = _zone(action)
    z.attributes["valve_feedback"] = "binary_sensor.end_switch"
    return z


def test_feedback_open_readings():
    f = central.feedback_open
    assert f("on") is True and f("off") is False
    assert f("open") is True and f("closing") is False
    assert f("35") is True and f("5") is False  # position sensor in %
    assert f("open", {"current_position": 10}) is False  # valve entity: the position decides
    assert f("unavailable") is None and f(None) is None and f("weird") is None


def test_end_switch_starts_the_boiler_before_the_opening_time():
    states = {"climate.floor": _fb_zone(), "binary_sensor.end_switch": _fb("on")}
    zones = cc.read_zones(_hass(states), ["climate.floor"], {}, T0)
    assert zones[0].valve_open is True
    assert central.CentralBoiler().step(T0, zones).output is True


def test_closed_feedback_holds_the_boiler_even_after_the_opening_time():
    states = {"climate.floor": _fb_zone(), "binary_sensor.end_switch": _fb("off")}
    valve_on, boiler = {}, central.CentralBoiler()
    cc.read_zones(_hass(states), ["climate.floor"], valve_on, T0)
    later = T0 + timedelta(minutes=5)  # past the 180 s opening time
    d = boiler.step(later, cc.read_zones(_hass(states), ["climate.floor"], valve_on, later))
    assert d.output is False and d.reason == "waiting_valves" and d.details["stuck"] == []
    late = T0 + timedelta(minutes=11)
    d = boiler.step(late, cc.read_zones(_hass(states), ["climate.floor"], valve_on, late))
    assert d.output is False and d.details["stuck"] == ["climate.floor"]


def test_unavailable_feedback_falls_back_to_the_opening_time():
    states = {"climate.floor": _fb_zone(), "binary_sensor.end_switch": _fb("unavailable")}
    valve_on, boiler = {}, central.CentralBoiler()
    assert boiler.step(T0, cc.read_zones(_hass(states), ["climate.floor"], valve_on, T0)).output is False
    later = T0 + timedelta(minutes=3)
    assert boiler.step(later, cc.read_zones(_hass(states), ["climate.floor"], valve_on, later)).output is True


def test_feedback_closing_stops_the_boiler_at_once():
    states = {"climate.floor": _fb_zone(), "binary_sensor.end_switch": _fb("on")}
    valve_on, boiler = {}, central.CentralBoiler()
    assert boiler.step(T0, cc.read_zones(_hass(states), ["climate.floor"], valve_on, T0)).output is True
    states["binary_sensor.end_switch"] = _fb("off")  # valve shut although the zone still asks
    soon = T0 + timedelta(minutes=1)  # inside the 5 min minimum run
    d = boiler.step(soon, cc.read_zones(_hass(states), ["climate.floor"], valve_on, soon))
    assert d.output is False and d.reason == "valves_closed"

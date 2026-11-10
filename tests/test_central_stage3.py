"""Stage 3 preparation: the central boiler for several zones."""

from datetime import datetime, timedelta, timezone

from core.central import CentralBoiler, CentralConfig, ZoneState

T0 = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def test_no_zone_asks_no_boiler():
    c = CentralBoiler()
    d = c.step(T0, [ZoneState("living", False), ZoneState("bedroom", False)])
    assert d.output is False and d.reason == "no_demand"


def test_waits_for_a_thermoelectric_valve_to_open():
    c = CentralBoiler()
    zone = lambda: [ZoneState("floor", True, 0.6, valve_on_since=T0)]  # noqa: E731
    assert c.step(at(1), zone()).reason == "waiting_valves"
    assert c.step(at(2.9), zone()).output is False
    d = c.step(at(3), zone())
    assert d.output is True and d.open_zones == ("floor",)


def test_valve_feedback_wins_over_the_timer():
    c = CentralBoiler()
    d = c.step(at(0.5), [ZoneState("floor", True, 0.5, valve_on_since=T0, valve_open=True)])
    assert d.output is True


def test_trv_zone_counts_open_at_once_when_it_reports_so():
    c = CentralBoiler()
    d = c.step(T0, [ZoneState("bedroom_trv", True, 0.4, valve_open=True)])
    assert d.output is True


def test_boiler_keeps_minimum_run_while_a_valve_is_open():
    c = CentralBoiler()
    c.step(T0, [ZoneState("a", True, 0.5, valve_open=True)])
    d = c.step(at(2), [ZoneState("a", False, 0.0, valve_open=True)])  # still open, closing
    assert d.output is True and d.reason == "min_on"
    assert c.step(at(5), [ZoneState("a", False, 0.0, valve_open=True)]).output is False


def test_boiler_stops_at_once_when_every_valve_closes():
    c = CentralBoiler()
    c.step(T0, [ZoneState("a", True, 0.5, valve_open=True)])
    d = c.step(at(1), [ZoneState("a", True, 0.5, valve_open=False)])
    assert d.output is False


def test_minimum_pause_between_runs():
    c = CentralBoiler()
    c.step(T0, [ZoneState("a", True, 0.5, valve_open=True)])
    c.step(at(6), [ZoneState("a", False, valve_open=False)])
    d = c.step(at(8), [ZoneState("a", True, 0.5, valve_open=True)])
    assert d.output is False and d.reason == "min_off"
    assert c.step(at(11), [ZoneState("a", True, 0.5, valve_open=True)]).output is True


def test_two_zones_needed_or_enough_demand():
    c = CentralBoiler(CentralConfig(central_min_zones=2, central_min_demand=0.8))
    assert c.step(T0, [ZoneState("a", True, 0.3, valve_open=True)]).reason == "no_demand"
    assert c.step(at(1), [ZoneState("a", True, 0.9, valve_open=True)]).output is True  # one big demand
    c2 = CentralBoiler(CentralConfig(central_min_zones=2))
    d = c2.step(T0, [ZoneState("a", True, 0.2, valve_open=True), ZoneState("b", True, 0.2, valve_open=False)])
    assert d.output is True and d.asking == ("a", "b") and d.open_zones == ("a",)


def test_a_faulty_zone_does_not_count():
    c = CentralBoiler()
    d = c.step(T0, [ZoneState("a", True, 0.9, valve_open=True, fault=True)])
    assert d.output is False and d.reason == "no_demand"

"""0.39.0: weekly pump exercise of the central boiler – the pump alone, never the boiler."""

import asyncio
import importlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
central = importlib.import_module("hc_thermostat.core.central")

MONDAY_10 = datetime(2026, 11, 9, 10, 0, tzinfo=timezone.utc)  # a Monday


def boiler(**cfg):
    cfg.setdefault("central_pump_bypass", True)  # an open circuit; the closed-valve cases set it False
    b = central.CentralBoiler(central.CentralConfig(central_min_on_s=0, central_min_off_s=0, **cfg))
    b.has_pump = True
    return b


def idle_zone(name="climate.floor"):
    return central.ZoneState(name, False)


def at(b, seconds, zones=None, start=MONDAY_10, **kw):
    return b.step(start + timedelta(seconds=seconds), zones if zones is not None else [idle_zone()], **kw)


def test_runs_once_a_week_for_the_given_time():
    b = boiler()
    d = at(b, 0)
    assert d.pump and not d.output and d.details["pump_exercise"]
    assert d.details["pump_exercise_until"] == (MONDAY_10 + timedelta(seconds=60)).isoformat()
    assert at(b, 30).pump
    d = at(b, 60)
    assert not d.pump and "pump_exercise" not in d.details
    assert b.exercise.last_run == MONDAY_10 + timedelta(seconds=60)
    assert not at(b, 90).pump  # done for this week


def test_pump_entity_on_during_the_exercise_does_not_end_it():
    b = boiler()
    assert at(b, 0).pump
    assert at(b, 30, pump_on=True).pump  # live: the pump entity is on because of the exercise


def test_not_when_the_pump_ran_lately():
    b = boiler()
    b.exercise.last_run = MONDAY_10 - timedelta(days=2)
    assert not at(b, 0).pump
    b = boiler()
    d = at(b, -3600, pump_on=True)  # an hour before, someone ran the pump
    assert not d.pump and b.exercise.last_run == MONDAY_10 - timedelta(hours=1)
    assert not at(b, 0).pump


def test_not_on_another_day_or_time():
    b = boiler()
    assert not at(b, 0, start=MONDAY_10 + timedelta(days=1)).pump
    assert not at(b, -60).pump  # before the start time
    b = boiler(central_pump_exercise_weekday=2, central_pump_exercise_time="06:30:00")
    wednesday = datetime(2026, 11, 11, 6, 30, tzinfo=timezone.utc)
    assert at(b, 10, start=wednesday).pump


def test_off_without_a_pump_or_with_zero_time():
    b = boiler(central_pump_exercise_s=0)
    assert not at(b, 0).pump and b.exercise.next_run(MONDAY_10) is None
    b = boiler()
    b.has_pump = False
    assert not at(b, 0).pump


def test_never_with_a_zone_asking_and_the_boiler_does_not_start():
    b = boiler()
    asking = [central.ZoneState("climate.floor", True, 0.5)]
    d = at(b, 0, zones=asking)  # a zone asks: the valves are opening, no exercise
    assert not d.details.get("pump_exercise")
    b = boiler()
    assert at(b, 0).pump
    d = at(b, 20, zones=asking)  # a zone starts asking: the exercise stops, the normal logic takes over
    assert not d.details.get("pump_exercise") and not d.output  # waiting for the valve


def test_not_right_after_a_restart():
    b = boiler()
    assert not at(b, 0, uptime_s=60).pump
    assert at(b, 10, uptime_s=400).pump


def test_state_survives_and_next_run():
    b = boiler()
    at(b, 0)
    at(b, 60)
    saved = b.exercise.state()
    b2 = boiler()
    b2.exercise.restore(saved)
    assert not at(b2, 0, start=MONDAY_10 + timedelta(days=1)).pump
    nxt = b2.exercise.next_run(MONDAY_10 + timedelta(hours=1))
    assert nxt == MONDAY_10 + timedelta(days=7)


def test_central_coordinator_keeps_the_last_run():
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from custom_components.hc_thermostat.central_coordinator import CentralCoordinator

    entry = SimpleNamespace(data={"name": "Kazán", "role": "central", "zone_entities": ["climate.floor"],
                                  "boiler_entity": "switch.boiler", "pump_entity": "switch.pump", "mode": "shadow",
                                  "central_pump_exercise_weekday": "0", "central_pump_exercise_time": "10:00:00"},
                            options={}, entry_id="c390", title="Kazán", domain="hc_thermostat",
                            async_on_unload=lambda f: None)

    async def run():
        hass = HomeAssistant(tempfile.mkdtemp())
        try:
            c = CentralCoordinator(hass, entry)
            assert c.central.has_pump
            await c.async_load()
            hass.states.async_set("climate.floor", "heat", {"hvac_action": "idle"})
            hass.states.async_set("switch.pump", "on")
            d = await c._async_update_data()
            assert not d.output and c.central.exercise.last_run is not None  # the pump entity ran: counted
            c.central.exercise.last_run = datetime(2026, 1, 1, tzinfo=timezone.utc)
            await c.async_save()
            c2 = CentralCoordinator(hass, entry)
            await c2.async_load()
            assert c2.central.exercise.last_run == datetime(2026, 1, 1, tzinfo=timezone.utc)
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


def test_never_against_closed_valves_waits_for_an_open_circuit():
    b = boiler(central_pump_bypass=False)
    closed = [central.ZoneState("climate.floor", False, valve_open=False)]
    assert not at(b, 0, zones=closed).pump  # every valve shut, no bypass: no exercise
    opened = [central.ZoneState("climate.floor", False, valve_open=True)]  # the zone's valve exercise opened it
    d = at(b, 200, zones=opened)
    assert d.pump and d.details["pump_exercise"] and not d.output
    assert at(b, 230, zones=opened).pump
    d = at(b, 260, zones=opened)
    assert not d.pump and b.exercise.last_run == MONDAY_10 + timedelta(seconds=260)


def test_valve_closing_mid_run_stops_the_exercise():
    b = boiler(central_pump_bypass=False)
    opened = [central.ZoneState("climate.floor", False, valve_open=True)]
    closed = [central.ZoneState("climate.floor", False, valve_open=False)]
    assert at(b, 0, zones=opened).pump
    assert not at(b, 20, zones=closed).pump
    assert b.exercise.last_run is None  # not counted: it runs again once a circuit is open


def test_a_zone_valve_exercise_opens_the_circuit_after_the_opening_time():
    b = boiler(central_pump_bypass=False)
    ex = [central.ZoneState("climate.floor", False, exercise_since=MONDAY_10)]
    assert not at(b, 60, zones=ex).pump  # the actuator is still opening (central_valve_open_s 180)
    d = at(b, 180, zones=ex)
    assert d.pump and d.details["pump_exercise"] and not d.output


def test_read_zones_reports_a_valve_exercise():
    rz = importlib.import_module("hc_thermostat.central_coordinator").read_zones
    states = {"climate.floor": SimpleNamespace(state="heat", attributes={"hvac_action": "idle", "valve_exercising": True})}
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    ex: dict = {}
    zones = rz(hass, ["climate.floor"], {}, MONDAY_10, {}, ex)
    assert zones[0].exercise_since == MONDAY_10 and not zones[0].wants_heat
    states["climate.floor"].attributes["valve_exercising"] = False
    zones = rz(hass, ["climate.floor"], {}, MONDAY_10 + timedelta(seconds=600), {}, ex)
    assert zones[0].exercise_since is None and ex == {}

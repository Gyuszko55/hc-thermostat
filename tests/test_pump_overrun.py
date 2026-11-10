"""0.16.0: pump overrun at the central boiler – the pump runs on after the boiler, only while a circuit is open."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
cc = importlib.import_module("hc_thermostat.central_coordinator")
central = importlib.import_module("hc_thermostat.core.central")

T0 = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)


def _zone(action, control="tpi", feedback=None):
    attrs = {"hvac_action": action, "control_type": control, "demand": 40, "fault": False}
    if feedback:
        attrs["valve_feedback"] = feedback
    return SimpleNamespace(state="heat", attributes=attrs)


def _hass(states):
    return SimpleNamespace(states=SimpleNamespace(get=lambda e: states.get(e)))


class Run:
    def __init__(self, states, ids, **cfg):
        self.states, self.ids = states, ids
        self.boiler = central.CentralBoiler(central.CentralConfig(central_min_on_s=0, central_min_off_s=0, **cfg))
        self.valve_on, self.valve_off = {}, {}

    def at(self, seconds):
        now = T0 + timedelta(seconds=seconds)
        zones = cc.read_zones(_hass(self.states), self.ids, self.valve_on, now, self.valve_off)
        return self.boiler.step(now, zones)


def test_pump_runs_with_the_boiler_and_on_while_the_valve_closes():
    states = {"climate.floor": _zone("heating")}
    r = Run(states, ["climate.floor"], central_valve_open_s=180, central_pump_overrun_s=120)
    r.at(0)
    d = r.at(200)
    assert d.output and d.pump
    states["climate.floor"] = _zone("idle")  # the zone is warm: its relay drops, the actuator starts closing
    d = r.at(230)
    assert not d.output and d.pump and d.details["pump_until"]
    assert r.at(330).pump  # 100 s: still inside both the overrun and the closing time
    assert not r.at(350).pump  # overrun over


def test_overrun_stops_when_the_valve_has_closed():
    states = {"climate.floor": _zone("heating")}
    r = Run(states, ["climate.floor"], central_valve_open_s=60, central_pump_overrun_s=600)
    r.at(0)
    assert r.at(90).pump
    states["climate.floor"] = _zone("idle")
    assert r.at(120).pump
    assert not r.at(190).pump  # 70 s after switching off: a 60 s actuator is shut, the pump must not push


def test_feedback_decides_during_the_overrun():
    states = {"climate.floor": _zone("heating", feedback="binary_sensor.end"), "binary_sensor.end": SimpleNamespace(state="on", attributes={})}
    r = Run(states, ["climate.floor"], central_pump_overrun_s=600)
    assert r.at(0).pump
    states["climate.floor"] = _zone("idle", feedback="binary_sensor.end")
    assert r.at(30).pump  # end switch still open
    states["binary_sensor.end"] = SimpleNamespace(state="off", attributes={})
    assert not r.at(60).pump  # closed: stop at once


def test_bypass_runs_the_full_overrun_and_zero_turns_it_off():
    states = {"climate.bed": _zone("heating", control="external")}
    r = Run(states, ["climate.bed"], central_pump_overrun_s=300, central_pump_bypass=True)
    assert r.at(0).pump
    states["climate.bed"] = _zone("idle", control="external")
    assert r.at(30).pump and r.at(320).pump and not r.at(330).pump
    states2 = {"climate.bed": _zone("heating", control="external")}
    r2 = Run(states2, ["climate.bed"], central_pump_overrun_s=0, central_pump_bypass=True)
    r2.at(0)
    states2["climate.bed"] = _zone("idle", control="external")
    assert not r2.at(30).pump


def test_trv_zone_without_feedback_does_not_keep_the_pump():
    states = {"climate.bed": _zone("heating", control="external")}
    r = Run(states, ["climate.bed"], central_pump_overrun_s=300)
    assert r.at(0).pump
    states["climate.bed"] = _zone("idle", control="external")
    assert not r.at(30).pump  # the TRV may already be shut


def test_boiler_restart_during_overrun_keeps_the_pump_and_clears_the_overrun():
    states = {"climate.floor": _zone("heating")}
    r = Run(states, ["climate.floor"], central_valve_open_s=60, central_pump_overrun_s=300)
    r.at(-60)
    r.at(0)
    states["climate.floor"] = _zone("idle")
    assert r.at(30).details.get("pump_until")
    states["climate.floor"] = _zone("heating")
    d = r.at(60)  # asks again 30 s after closing began: the boiler waits for the opening time again,
    assert not d.output and d.pump  # but the pump keeps going – the actuator was not shut yet
    d = r.at(120)
    assert d.output and d.pump and "pump_until" not in d.details


def test_pump_relay_is_switched_only_in_active_mode():
    calls = []

    async def call(domain, service, data, blocking=False):
        calls.append((service, data["entity_id"]))

    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: SimpleNamespace(state="off", attributes={})),
                           services=SimpleNamespace(async_call=call))
    coord = SimpleNamespace(hass=hass, conf={cc.CONF_PUMP: "switch.pump"})
    asyncio.run(cc.CentralCoordinator._switch_pump(coord, True))
    assert calls == [("turn_on", "switch.pump")]
    coord.conf = {}
    asyncio.run(cc.CentralCoordinator._switch_pump(coord, True))
    assert len(calls) == 1  # no pump configured: nothing

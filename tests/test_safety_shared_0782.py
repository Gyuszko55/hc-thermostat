"""0.78.2 (security review M3): the life-safety latch is shared – an HC instance without safety inputs of its own (a
central boiler, a buffer, a mixing circuit, a room, a heat pump coordination) stops with the house as well."""

import asyncio
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT / "custom_components"))

hub_mod = importlib.import_module("hc_thermostat.safety_hub")
fs = importlib.import_module("hc_thermostat.failsafe")
central_mod = importlib.import_module("hc_thermostat.central_coordinator")
buffer_mod = importlib.import_module("hc_thermostat.buffer_coordinator")
circuit_mod = importlib.import_module("hc_thermostat.circuit_coordinator")
central = importlib.import_module("hc_thermostat.core.central")
buffer = importlib.import_module("hc_thermostat.core.buffer")
circuit = importlib.import_module("hc_thermostat.core.circuit")

T0 = datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc)


class _Hass:
    def __init__(self, states, tripped=None):
        self._s = states
        self.calls = []
        self.data = {}
        self.config = SimpleNamespace(language="en")
        self.states = SimpleNamespace(get=self._s.get)
        self.services = SimpleNamespace(async_call=self._call)
        if tripped is not None:
            hub = SimpleNamespace(watched={"other": ["binary_sensor.smoke"]},
                                  latch=SimpleNamespace(tripped=tripped, by=["binary_sensor.smoke"] if tripped else []),
                                  check=lambda now: tripped)
            self.data["hc_thermostat_safety"] = hub

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))
        st = self._s.get(data.get("entity_id"))
        if st is not None and service in ("turn_on", "turn_off"):
            st.state = service[5:]


def _st(eid, state, **attrs):
    return SimpleNamespace(entity_id=eid, state=state, attributes=attrs, last_changed=T0, last_updated=T0,
                           last_reported=T0)


def test_stop_held_own_shared_none():
    assert hub_mod.stop_held(_Hass({}), T0) == (False, [])  # no instance watches anything
    assert hub_mod.stop_held(_Hass({}, tripped=False), T0) == (False, [])
    assert hub_mod.stop_held(_Hass({}, tripped=True), T0) == (True, ["binary_sensor.smoke"])
    broken = _Hass({}, tripped=True)
    broken.data["hc_thermostat_safety"].check = lambda now: 1 / 0
    assert hub_mod.stop_held(broken, T0)[0] is True  # a failing check: what the latch knew


def _central(hass, mode="shadow"):
    c = object.__new__(central_mod.CentralCoordinator)
    c.hass, c.mode, c.config_entry = hass, mode, SimpleNamespace(title="Central", entry_id="C1")
    c.conf = {central_mod.CONF_BOILER: "switch.boiler", central_mod.CONF_PUMP: "switch.pump"}
    c.central = central.CentralBoiler(central.CentralConfig(central_valve_open_s=0))
    c._valve_on, c._valve_off, c._exercise_on, c._started = {}, {}, {}, T0
    c.keep_alive = central_mod.KeepAlive(0)
    c._last_flow, c._last_save, c.zones = None, T0, []
    c._saved_run = c.central.exercise.last_run
    c.data = None
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)
    return c


def test_central_boiler_stops_with_the_house_even_in_shadow():
    states = {"switch.boiler": _st("switch.boiler", "on"), "switch.pump": _st("switch.pump", "on"),
              "climate.zone": _st("climate.zone", "heat", hvac_action="heating", demand=80)}
    hass = _Hass(states, tripped=True)
    c = _central(hass)
    c.conf[central_mod.CONF_ZONES] = ["climate.zone"]
    d = asyncio.run(c._async_update_data())
    assert d.output is False and d.reason == "safety_stop" and d.details["safety_stop"] == ["binary_sensor.smoke"]
    assert ("homeassistant", "turn_off", {"entity_id": "switch.boiler"}) in hass.calls


def test_central_untouched_without_a_stop():
    hass = _Hass({"switch.boiler": _st("switch.boiler", "on")}, tripped=False)
    d = asyncio.run(_central(hass)._async_update_data())
    assert d.reason != "safety_stop" and hass.calls == []  # shadow: nothing written


def test_buffer_stops_charging():
    hass = _Hass({"switch.source": _st("switch.source", "on")}, tripped=True)
    c = object.__new__(buffer_mod.BufferCoordinator)
    c.hass, c.mode, c.config_entry = hass, "shadow", SimpleNamespace(title="Buffer", entry_id="B1")
    c.conf = {buffer_mod.CONF_BOILER: "switch.source"}
    c.buffer = buffer.BufferCharger(buffer.BufferConfig())
    c.buffer._switch(T0, True)
    c._update_stock = lambda now, max_age: None
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)

    async def save():
        pass

    c.async_save = save
    d = asyncio.run(c._async_update_data())
    assert d.output is False and d.reason == "safety_stop" and c.buffer.output is False
    assert hass.calls == [("homeassistant", "turn_off", {"entity_id": "switch.source"})]


def test_circuit_lowest_flow_forced():
    hass = _Hass({}, tripped=True)
    c = object.__new__(circuit_mod.CircuitCoordinator)
    c.hass, c.config_entry, c.conf = hass, SimpleNamespace(title="Circuit", entry_id="K1"), {}
    cfg = circuit.CircuitConfig()
    c.circuit = circuit.MixingCircuit(cfg)
    c.buffer_coordinator = lambda: None
    c._cap_state, c._last_save, c._started = "off", T0, T0
    c._step_watch = lambda now, d: None
    written = []

    async def save():
        pass

    async def tick(now):
        pass

    async def apply(now, want, writing, up, force=False):
        written.append((want, force))

    c.async_save = save
    c.write = SimpleNamespace(tick=tick, writing=lambda now: False, note_conflict=lambda out: None)
    c.out = SimpleNamespace(apply=apply)
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)
    d = asyncio.run(c._async_update_data())
    assert d.reason == "safety_stop" and written == [(cfg.circuit_flow_min, True)]


def test_room_and_hp_use_the_shared_latch():
    for f in ("coordinator.py", "hp_coord_coordinator.py"):
        assert "stop_held(self.hass, now" in (BASE / f).read_text()


def test_texts():
    src = (BASE / "sensor.py").read_text()
    assert src.count('"safety_stop"]') == 2
    for lang in ("en", "hu"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())["entity"]["sensor"]
        assert tr["central_decision"]["state"]["safety_stop"] and tr["buffer_decision"]["state"]["safety_stop"]
    assert "HC stopped all heating" not in (BASE / "safety_hub.py").read_text()

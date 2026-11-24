"""0.78.2 (security review H2): the central boiler, buffer, mixing circuit and heat pump coordination switch their heat
off after FAILSAFE_AFTER failed steps in a row, like the room thermostat; a working step clears it."""

import asyncio
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(PKG.parent))
fs = importlib.import_module("hc_thermostat.failsafe")
central_mod = importlib.import_module("hc_thermostat.central_coordinator")
buffer_mod = importlib.import_module("hc_thermostat.buffer_coordinator")
circuit_mod = importlib.import_module("hc_thermostat.circuit_coordinator")
hp_mod = importlib.import_module("hc_thermostat.hp_coord_coordinator")
central = importlib.import_module("hc_thermostat.core.central")
buffer = importlib.import_module("hc_thermostat.core.buffer")
circuit = importlib.import_module("hc_thermostat.core.circuit")
hp = importlib.import_module("hc_thermostat.core.hp_coord")

T0 = datetime(2026, 11, 20, 18, 0, tzinfo=timezone.utc)


class _St(SimpleNamespace):
    pass


class _Hass:
    def __init__(self, states):
        self._s = states
        self.calls = []
        self.config = SimpleNamespace(language="hu")
        self.states = SimpleNamespace(get=self._s.get)
        self.services = SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))
        eid = data.get("entity_id")
        if service in ("turn_on", "turn_off") and eid in self._s:
            self._s[eid].state = service[5:]


def _st(eid, state, **attrs):
    return _St(entity_id=eid, state=state, attributes=attrs, last_changed=T0, last_updated=T0, last_reported=T0)


class _Boom:
    def __init__(self, cfg):
        self.cfg = cfg

    def step(self, *a, **k):
        raise RuntimeError("boom")


@pytest.fixture
def issues(monkeypatch):
    shown = {}
    monkeypatch.setattr(fs.ir, "async_create_issue",
                        lambda hass, domain, issue_id, **k: shown.__setitem__(issue_id, k))
    monkeypatch.setattr(fs.ir, "async_delete_issue", lambda hass, domain, issue_id: shown.pop(issue_id, None))
    return shown


def _entry():
    return SimpleNamespace(title="Probe", entry_id="E1")


def _fail_three(update):
    for _ in range(fs.FAILSAFE_AFTER - 1):
        with pytest.raises(RuntimeError):
            asyncio.run(update())
    return asyncio.run(update())


def test_step_failsafe_counts_and_clears(issues):
    f = fs.StepFailsafe(_Hass({}), _entry())
    results = []
    for _ in range(fs.FAILSAFE_AFTER + 1):
        try:
            raise RuntimeError("x")
        except RuntimeError:
            results.append(f.failed())
    assert results == [False] * (fs.FAILSAFE_AFTER - 1) + [True, True]
    assert "failsafe_E1" in issues and issues["failsafe_E1"]["translation_key"] == "sensor_problem"
    assert "Hibatűrés" not in issues["failsafe_E1"]["translation_placeholders"]["problems"]  # the hu words
    assert "biztonsági okból ki van kapcsolva" in issues["failsafe_E1"]["translation_placeholders"]["problems"]
    f.ok()
    assert f.errors == 0 and "failsafe_E1" not in issues


def test_central_boiler_goes_off(issues):
    hass = _Hass({"switch.boiler": _st("switch.boiler", "on"), "switch.pump": _st("switch.pump", "on"),
                  "number.flow": _st("number.flow", "60", min=25, max=80, step=1)})
    c = object.__new__(central_mod.CentralCoordinator)
    c.hass, c.mode, c.config_entry = hass, "active", _entry()
    c.conf = {central_mod.CONF_BOILER: "switch.boiler", central_mod.CONF_PUMP: "switch.pump",
              central_mod.CONF_FLOW: "number.flow"}
    c.central = _Boom(central.CentralConfig())
    c.central.exercise = SimpleNamespace(last_run=None)
    c._valve_on, c._valve_off, c._exercise_on, c._started = {}, {}, {}, T0
    c.keep_alive = central_mod.KeepAlive(0)
    c._last_flow, c._saved_run, c._last_save = 60.0, None, T0
    c.data = central.CentralDecision(T0, True, "heating", pump=True, flow_setpoint=60.0)
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)
    d = _fail_three(c._async_update_data)
    assert d.output is False and d.reason == "failsafe" and d.flow_setpoint is None and d.pump is True
    assert ("homeassistant", "turn_off", {"entity_id": "switch.boiler"}) in hass.calls
    assert ("number", "set_value", {"entity_id": "number.flow", "value": 25.0}) in hass.calls
    assert not any(c_[2].get("entity_id") == "switch.pump" for c_ in hass.calls)  # the overrun pump keeps running


def test_buffer_heat_source_goes_off(issues):
    hass = _Hass({"switch.source": _st("switch.source", "on")})
    c = object.__new__(buffer_mod.BufferCoordinator)
    c.hass, c.mode, c.config_entry = hass, "active", _entry()
    c.conf = {buffer_mod.CONF_BOILER: "switch.source"}
    real = buffer.BufferCharger(buffer.BufferConfig())
    real._switch(T0, True)

    def boom(*a, **k):
        raise RuntimeError("boom")

    real.step = boom
    c.buffer = real
    c._update_stock = lambda now, max_age: None
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)
    saved = []

    async def save():
        saved.append(True)

    c.async_save = save
    d = _fail_three(c._async_update_data)
    assert d.output is False and d.reason == "failsafe" and real.output is False and saved
    assert hass.calls == [("homeassistant", "turn_off", {"entity_id": "switch.source"})]


def test_circuit_gets_its_lowest_flow(issues):
    c = object.__new__(circuit_mod.CircuitCoordinator)
    hass = _Hass({})
    c.hass, c.config_entry, c.conf = hass, _entry(), {}
    cfg = circuit.CircuitConfig()
    c.circuit = _Boom(cfg)
    c.buffer_coordinator = lambda: None
    c._cap_state, c._last_save, c._started = "off", T0, T0
    c._step_watch = lambda now, d: None
    written = []

    async def save():
        pass

    async def tick(now):
        pass

    async def apply(now, want, writing, up, force=False):
        written.append(want)

    c.async_save = save
    c.write = SimpleNamespace(tick=tick, writing=lambda now: True, note_conflict=lambda out: None)
    c.out = SimpleNamespace(apply=apply)
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)
    d = _fail_three(c._async_update_data)
    assert d.reason == "failsafe" and d.demand is False and written == [cfg.circuit_flow_min] and c.usable == {}


def test_heat_pump_gets_no_on(issues):
    c = object.__new__(hp_mod.HpCoordCoordinator)
    hass = _Hass({})
    c.hass, c.config_entry, c.conf = hass, _entry(), {}
    cfg = hp.HpConfig()
    c.hp = _Boom(cfg)
    c.hp.enable = c.hp.heating = c.hp.cold_latched = c.hp.summer = False
    c.inputs = lambda now: None
    c.safety, c.heat_meter, c._last_save, c._started = None, None, T0, T0
    c._target_check = lambda now, d, writing: None
    written = []

    async def save():
        pass

    async def tick(now):
        pass

    def writer(name):
        async def apply(now, want, writing, up, force=False):
            written.append((name, want))
        return SimpleNamespace(apply=apply)

    c.async_save = save
    c.write = SimpleNamespace(tick=tick, writing=lambda now: True, note_conflict=lambda out: None)
    for n in ("target", "switch", "demand", "summer", "exercise"):
        setattr(c, f"out_{n}", writer(n))
    c.data = hp.HpDecision(T0, True, True, "heating", 45.0, 45.0, "changed", summer=False)
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)
    d = _fail_three(c._async_update_data)
    assert d.reason == "failsafe" and "failsafe" in hp.REASONS
    assert written == [("target", cfg.hp_flow_min), ("switch", False), ("demand", False), ("summer", False),
                       ("exercise", False)]


def test_failsafe_reason_is_an_option_and_translated():
    src = (PKG / "sensor.py").read_text()
    assert src.count('"failsafe", "safety_stop"]') == 2  # central + buffer decision options (0.78.2 M3: + safety_stop)
    for lang in ("en", "hu"):
        tr = json.loads((PKG / "translations" / f"{lang}.json").read_text())["entity"]["sensor"]
        for key in ("central_decision", "buffer_decision", "hp_decision"):
            assert tr[key]["state"]["failsafe"]

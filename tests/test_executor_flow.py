"""Stage 4 (EXPERIMENTAL): writing the flow setpoint – never in shadow mode."""

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
executor_mod = importlib.import_module("hc_thermostat.executor")
model = importlib.import_module("hc_thermostat.core.model")

NOW = datetime(2026, 11, 9, 6, 0, tzinfo=timezone.utc)


class FakeHass:
    def __init__(self, states):
        self._states = states
        self.calls = []
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))
        self.services = SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def _state(value, **attrs):
    return SimpleNamespace(state=str(value), attributes=attrs)


def _decision(output, flow):
    return model.Decision(NOW, model.Reason.REGULATING, 22.0, 21.0, 0.0, output=output, flow_setpoint=flow)


def _apply(ex, d):
    asyncio.run(ex.apply(d))


def test_shadow_mode_writes_nothing():
    hass = FakeHass({"number.ch_setpoint": _state(30, min=10), "switch.ch_enable": _state("off")})
    ex = executor_mod.Executor(hass, "shadow", None, None, "number.ch_setpoint", "switch.ch_enable")
    _apply(ex, _decision(True, 55.0))
    assert hass.calls == []


def test_active_writes_the_flow_and_switches_enable():
    hass = FakeHass({"number.ch_setpoint": _state(30, min=10), "switch.ch_enable": _state("off")})
    ex = executor_mod.Executor(hass, "active", None, None, "number.ch_setpoint", "switch.ch_enable")
    _apply(ex, _decision(True, 55.0))
    assert ("homeassistant", "turn_on", {"entity_id": "switch.ch_enable"}) in hass.calls
    assert ("number", "set_value", {"entity_id": "number.ch_setpoint", "value": 55.0}) in hass.calls


def test_small_changes_are_not_chased():
    hass = FakeHass({"input_number.flow": _state(55, min=10)})
    ex = executor_mod.Executor(hass, "active", None, None, "input_number.flow")
    _apply(ex, _decision(True, 55.0))
    _apply(ex, _decision(True, 55.3))
    assert len(hass.calls) == 1 and hass.calls[0][0] == "input_number"


def test_off_without_enable_switch_writes_the_lowest_setpoint():
    hass = FakeHass({"number.flow": _state(55, min=10)})
    ex = executor_mod.Executor(hass, "active", None, None, "number.flow")
    _apply(ex, _decision(False, None))
    assert hass.calls == [("number", "set_value", {"entity_id": "number.flow", "value": 10.0})]


def test_off_with_enable_switch_only_switches_it_off():
    hass = FakeHass({"number.flow": _state(55, min=10), "switch.ch_enable": _state("on")})
    ex = executor_mod.Executor(hass, "active", None, None, "number.flow", "switch.ch_enable")
    _apply(ex, _decision(False, None))
    assert hass.calls == [("homeassistant", "turn_off", {"entity_id": "switch.ch_enable"})]


def test_unavailable_target_is_left_alone():
    hass = FakeHass({"number.flow": _state("unavailable")})
    ex = executor_mod.Executor(hass, "active", None, None, "number.flow")
    _apply(ex, _decision(True, 50.0))
    assert hass.calls == []


def _cool(output, flow):
    return model.Decision(NOW, model.Reason.FLOOR_COOL if output else model.Reason.SEASON_OFF, 26.0, 27.0, 30.0,
                          output=output, flow_setpoint=flow, details={"mode": "cool"})


def test_floor_cooling_switches_the_cool_mode_and_writes_its_own_flow():
    hass = FakeHass({"number.ch_setpoint": _state(30, min=20, max=55), "number.cool_setpoint": _state(25, min=7, max=25),
                     "switch.hp_cool": _state("off")})
    ex = executor_mod.Executor(hass, "active", None, None, "number.ch_setpoint", cool_mode="switch.hp_cool",
                               cool_flow="number.cool_setpoint")
    _apply(ex, _cool(True, 19.5))
    assert ("homeassistant", "turn_on", {"entity_id": "switch.hp_cool"}) in hass.calls
    assert ("number", "set_value", {"entity_id": "number.cool_setpoint", "value": 19.5}) in hass.calls


def test_stopped_cooling_writes_the_warmest_setpoint_not_the_coldest():
    hass = FakeHass({"number.ch_setpoint": _state(18, min=7, max=30)})
    ex = executor_mod.Executor(hass, "active", None, None, "number.ch_setpoint")
    _apply(ex, _cool(False, None))
    assert hass.calls == [("number", "set_value", {"entity_id": "number.ch_setpoint", "value": 30.0})]


def test_heating_decision_switches_the_cool_mode_off():
    hass = FakeHass({"number.ch_setpoint": _state(30, min=10), "switch.hp_cool": _state("on")})
    ex = executor_mod.Executor(hass, "active", None, None, "number.ch_setpoint", cool_mode="switch.hp_cool")
    _apply(ex, _decision(True, 40.0))
    assert ("homeassistant", "turn_off", {"entity_id": "switch.hp_cool"}) in hass.calls

"""0.39.3, the Home Assistant side: a fan with speed steps is commanded once, and the central boiler reads a
floor zone's flow limit."""

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
executor_mod = importlib.import_module("hc_thermostat.executor")
model = importlib.import_module("hc_thermostat.core.model")
cc = importlib.import_module("hc_thermostat.central_coordinator")

NOW = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)


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


def _fan_decision(pct):
    return model.Decision(NOW, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.2, output=pct > 0,
                          details={"fan_pct": pct, "fan_why": "heating"})


def _fan_calls(hass, pct):
    ex = executor_mod.Executor(hass, "active", None, None, fan="fan.coil")
    asyncio.run(ex.apply(_fan_decision(pct)))
    return [c for c in hass.calls if c[0] == "fan"]


def test_three_speed_fan_is_not_commanded_again():
    step = 100 / 3
    hass = FakeHass({"fan.coil": _state("on", percentage=33, percentage_step=step)})
    assert _fan_calls(hass, 45) == []  # 45 % is the lowest of three speeds, and it runs there already
    hass = FakeHass({"fan.coil": _state("on", percentage=33, percentage_step=step)})
    assert _fan_calls(hass, 65) == [("fan", "set_percentage", {"entity_id": "fan.coil", "percentage": 66})]
    hass = FakeHass({"fan.coil": _state("off", percentage=0, percentage_step=step)})
    assert _fan_calls(hass, 45) == [("fan", "set_percentage", {"entity_id": "fan.coil", "percentage": 33})]


def test_fine_fan_and_off_as_before():
    hass = FakeHass({"fan.coil": _state("on", percentage=40, percentage_step=1)})
    assert _fan_calls(hass, 45) == [("fan", "set_percentage", {"entity_id": "fan.coil", "percentage": 45})]
    hass = FakeHass({"fan.coil": _state("on", percentage=45)})
    assert _fan_calls(hass, 45) == []
    hass = FakeHass({"fan.coil": _state("on", percentage=33, percentage_step=100 / 3)})
    assert _fan_calls(hass, 0) == [("fan", "turn_off", {"entity_id": "fan.coil"})]


def test_read_zones_takes_the_flow_limit():
    attrs = {"hvac_action": "heating", "control_type": "tpi", "demand": 60, "fault": False, "flow_request": 33.5,
             "flow_limit": 45.0}
    states = {"climate.floor": SimpleNamespace(state="heat", attributes=attrs)}
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: states.get(e)))
    assert cc.read_zones(hass, ["climate.floor"], {}, NOW)[0].flow_limit == 45.0
    attrs["flow_limit"] = None
    assert cc.read_zones(hass, ["climate.floor"], {}, NOW)[0].flow_limit is None


def test_buffer_reading_without_a_sensor_or_too_old():
    bc = importlib.import_module("hc_thermostat.buffer_coordinator")
    from datetime import timedelta
    fresh_state = SimpleNamespace(state="55.0", last_reported=NOW - timedelta(minutes=5), last_updated=NOW)
    old_state = SimpleNamespace(state="55.0", last_reported=NOW - timedelta(hours=2), last_updated=NOW)
    hass = FakeHass({"sensor.top": fresh_state, "sensor.old": old_state, "sensor.bad": SimpleNamespace(state="unknown", last_reported=NOW)})
    assert bc._temp(hass, None, NOW, 3600) is None  # no bottom sensor configured: no reading, no error
    assert bc._temp(hass, "sensor.missing", NOW, 3600) is None  # not loaded yet
    assert bc._temp(hass, "sensor.bad", NOW, 3600) is None
    assert bc._temp(hass, "sensor.top", NOW, 3600) == 55.0
    assert bc._temp(hass, "sensor.old", NOW, 3600) is None  # a dead sensor keeps its value

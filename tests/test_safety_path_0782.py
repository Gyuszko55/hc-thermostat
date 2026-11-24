"""0.78.2 (security review H1): the life-safety stop reaches the output on every path – shadow, "HC supervision
paused", the write guard's grace / conflict / given-up states and a failing decision step do not hold it back."""

import asyncio
import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(PKG.parent))
model = importlib.import_module("hc_thermostat.core.model")
executor_mod = importlib.import_module("hc_thermostat.executor")
writer_mod = importlib.import_module("hc_thermostat.output_writer")
coord_mod = importlib.import_module("hc_thermostat.coordinator")
hp_mod = importlib.import_module("hc_thermostat.hp_coord_coordinator")
hp = importlib.import_module("hc_thermostat.core.hp_coord")
fs = importlib.import_module("hc_thermostat.failsafe")

T0 = datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc)


class _Hass:
    def __init__(self, states):
        self._s = states
        self.calls = []
        self.data = {}
        self.config = SimpleNamespace(language="en", units=SimpleNamespace(temperature_unit="°C"))
        self.states = SimpleNamespace(get=self._s.get)
        self.services = SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))
        eid = data.get("entity_id")
        st = self._s.get(eid)
        if st is None:
            return
        if service in ("turn_on", "turn_off"):
            st.state = service[5:]
        elif service == "set_hvac_mode":
            st.state = data["hvac_mode"]
        elif service == "set_value":
            st.state = str(data["value"])


def _st(eid, state, **attrs):
    return SimpleNamespace(entity_id=eid, state=state, attributes=attrs, last_changed=T0, last_updated=T0,
                           last_reported=T0)


def _stop(external=None):
    return model.Decision(T0, model.Reason.SAFETY_STOP, 7.0, None, None, demand=0.0, output=False,
                          limited_by="safety_stop", external=external)


# --- the room thermostat's executor -------------------------------------------------------------------------------
@pytest.mark.parametrize("mode,paused", [("shadow", False), ("active", True), ("shadow", True)])
def test_stop_goes_out_in_shadow_and_paused(mode, paused):
    hass = _Hass({"switch.boiler": _st("switch.boiler", "on")})
    ex = executor_mod.Executor(hass, mode, "switch.boiler", None)
    ex.paused = paused
    asyncio.run(ex.apply(_stop()))
    assert hass.calls == [("homeassistant", "turn_off", {"entity_id": "switch.boiler"})]


def test_an_ordinary_decision_still_waits_in_shadow_and_paused():
    hass = _Hass({"switch.boiler": _st("switch.boiler", "on")})
    for mode, paused in (("shadow", False), ("active", True)):
        ex = executor_mod.Executor(hass, mode, "switch.boiler", None)
        ex.paused = paused
        asyncio.run(ex.apply(model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.0, output=False)))
    assert hass.calls == []


def test_paused_managed_thermostat_is_switched_off():
    hass = _Hass({"climate.ac": _st("climate.ac", "heat", temperature=24.0, min_temp=16, max_temp=30,
                                    hvac_modes=["off", "heat"])})
    ex = executor_mod.Executor(hass, "active", None, "climate.ac")
    ex.paused = True
    asyncio.run(ex.apply(_stop(model.ExternalCommand("off", 7.0))))
    assert any(c[1] == "set_hvac_mode" and c[2]["hvac_mode"] == "off" for c in hass.calls)


# --- the output writer --------------------------------------------------------------------------------------------
def test_forced_write_ignores_shadow_grace_and_conflict():
    hass = _Hass({"switch.hp": _st("switch.hp", "on")})
    w = writer_mod.OutputWriter(hass, "switch.hp", onoff=True)
    w.guard.conflict, w.guard.failed = True, True  # someone else switched it on, HC gave up
    assert asyncio.run(w.apply(T0, False, False, 0.0)) == "shadow" and hass.calls == []  # not forced: nothing
    assert asyncio.run(w.apply(T0, False, False, 0.0, force=True)) == "safety"
    assert hass.calls == [("homeassistant", "turn_off", {"entity_id": "switch.hp"})]
    asyncio.run(w.apply(T0, False, False, 0.0, force=True))  # already off: not written again
    assert len(hass.calls) == 1


def test_forced_target_to_a_number():
    hass = _Hass({"number.flow": _st("number.flow", "50", min=20, max=60, step=1, unit_of_measurement="°C")})
    w = writer_mod.OutputWriter(hass, "number.flow")
    assert asyncio.run(w.apply(T0, 25.0, False, 0.0, force=True)) == "safety"
    assert hass.calls == [("number", "set_value", {"entity_id": "number.flow", "value": 25.0})]


def test_forced_write_on_an_unavailable_output():
    hass = _Hass({"switch.hp": _st("switch.hp", "unavailable")})
    w = writer_mod.OutputWriter(hass, "switch.hp", onoff=True)
    assert asyncio.run(w.apply(T0, False, True, 999.0, force=True)) == "unavailable" and hass.calls == []


# --- a failing step with the latch held ---------------------------------------------------------------------------
class _Hub:
    def __init__(self, tripped=True, raises=False):
        self.latch = SimpleNamespace(tripped=tripped, by=["binary_sensor.smoke"])
        self._raises = raises

    def check(self, now):
        if self._raises:
            raise RuntimeError("states")
        return self.latch.tripped


def _room(hub):
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass, c.mode, c.step_errors, c.sensor_problems = _Hass({}), "active", 0, {}
    c.config_entry = SimpleNamespace(title="Probe")
    c.cfg = SimpleNamespace(frost_temp=7.0)
    c.managed, c.safety = False, hub
    c.data = model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.6, output=True)
    return c


@pytest.mark.parametrize("hub", [_Hub(), _Hub(raises=True)])
def test_room_failing_step_with_the_latch_gives_the_stop_at_once(hub):
    c = _room(hub)
    assert c._safety_held(T0) is True
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        d = c._safety_fallback(T0)
    assert d.reason == model.Reason.SAFETY_STOP and d.output is False and d.demand == 0.0 and d.flow_setpoint is None
    assert c.step_errors == 1 and d.details["safety_by"] == ["binary_sensor.smoke"]


def test_room_update_uses_the_safety_fallback_before_the_failsafe():
    src = (PKG / "coordinator.py").read_text()
    body = src[src.index("    async def _async_update_data"):src.index("    async def _failsafe")]
    assert body.index("if self._safety_held(now):") < body.index("decision = await self._failsafe(now)")


def test_room_without_safety_inputs_never_holds():
    assert _room(None)._safety_held(T0) is False


def _hp(stop_hub, step_raises):
    c = object.__new__(hp_mod.HpCoordCoordinator)
    hass = _Hass({})
    c.hass, c.config_entry, c.conf = hass, SimpleNamespace(title="Probe", entry_id="E1"), {}
    cfg = hp.HpConfig()

    class _Core:
        def __init__(self):
            self.cfg = cfg
            self.enable = self.heating = self.cold_latched = self.summer = False

        def step(self, now, inputs):
            if step_raises:
                raise RuntimeError("boom")
            return hp.HpDecision(now, True, True, "heating", 45.0, 45.0, "changed")

    c.hp = _Core()
    c.inputs = lambda now: None
    c.safety, c.heat_meter, c._last_save, c._started = stop_hub, None, T0, T0
    c._target_check = lambda now, d, writing: None
    c.data = None
    written = []

    async def save():
        pass

    async def tick(now):
        pass

    def writer(name):
        async def apply(now, want, writing, up, force=False):
            written.append((name, want, force))
        return SimpleNamespace(apply=apply)

    c.async_save = save
    c.write = SimpleNamespace(tick=tick, writing=lambda now: False, note_conflict=lambda out: None)  # shadow
    for n in ("target", "switch", "demand", "summer", "exercise"):
        setattr(c, f"out_{n}", writer(n))
    c.failsafe = fs.StepFailsafe(hass, c.config_entry)
    return c, cfg, written


@pytest.mark.parametrize("step_raises", [False, True])
def test_heat_pump_stop_is_forced_even_when_the_step_fails(monkeypatch, step_raises):
    monkeypatch.setattr(fs.ir, "async_create_issue", lambda *a, **k: None)
    monkeypatch.setattr(fs.ir, "async_delete_issue", lambda *a, **k: None)
    c, cfg, written = _hp(_Hub(), step_raises)
    d = asyncio.run(c._async_update_data())  # the very first failure: no raise, the stop
    assert d.reason == "safety_stop" and d.enable is False and d.heat_demand is False and d.exercise is False
    assert written == [("target", cfg.hp_flow_min, True), ("switch", False, True), ("demand", False, True),
                       ("summer", False, False), ("exercise", False, True)]


def test_heat_pump_without_a_stop_is_not_forced():
    c, cfg, written = _hp(None, False)
    d = asyncio.run(c._async_update_data())
    assert d.reason == "heating" and all(f is False for _, _, f in written)

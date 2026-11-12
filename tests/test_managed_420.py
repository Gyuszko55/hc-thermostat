"""0.42.0: managing existing thermostat integrations – adapters, two-way following, the pause switch."""

import asyncio
import importlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))
adapters = importlib.import_module("core.adapters")
model = importlib.import_module("core.model")
sup_mod = importlib.import_module("core.supervisor")
ts = importlib.import_module("core.target_source")
messages = importlib.import_module("core.messages")

Reason, Reading = model.Reason, model.Reading
T0 = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

GREE = {"hvac_modes": ["off", "auto", "cool", "dry", "fan_only", "heat"], "min_temp": 16, "max_temp": 30,
        "target_temp_step": 1, "temperature": 19}
SMART = {"hvac_modes": ["heat", "off"], "min_temp": 7, "max_temp": 35, "target_temp_step": 0.1,
         "preset_modes": ["none", "away", "eco"], "hvac_action": "idle", "temperature": 21.0}


# --- adapters ------------------------------------------------------------------------------------------------
def test_adapter_for_known_and_unknown_platforms():
    assert adapters.adapter_for("smart_thermostat").key == "smart_thermostat"
    assert adapters.adapter_for("better_thermostat").key == "better_thermostat"
    assert adapters.adapter_for("gree").key == "gree"
    assert adapters.adapter_for("generic_thermostat").key == "generic"
    assert adapters.adapter_for(None).key == "generic"


def test_capabilities_come_from_the_live_attributes():
    caps = adapters.adapter_for("smart_thermostat").capabilities(SMART)
    assert caps.hvac_modes == ("heat", "off") and caps.min_temp == 7 and caps.max_temp == 35
    assert caps.step == 0.1 and caps.preset_modes == ("none", "away", "eco") and caps.has_action
    caps = adapters.adapter_for("gree").capabilities({**GREE, "min_temp": 17, "target_temp_step": 0.5})
    assert caps.min_temp == 17 and caps.step == 0.5 and not caps.has_action  # never hard-coded
    empty = adapters.adapter_for(None).capabilities({})
    assert empty.step is None and empty.min_temp is None and empty.hvac_modes == ()


def test_gree_whole_degrees_and_range():
    g = adapters.adapter_for("gree")
    assert g.fit_target(22.5, GREE) == 23.0  # half up, not banker's rounding
    assert g.fit_target(21.4, GREE) == 21.0
    assert g.fit_target(8.0, GREE) == 16.0  # frost target below the unit's minimum
    assert g.fit_target(31.2, GREE) == 30.0


def test_smart_thermostat_tenths():
    s = adapters.adapter_for("smart_thermostat")
    assert s.fit_target(21.37, SMART) == 21.4
    assert s.fit_target(21.3, SMART) == 21.3
    assert s.fit_target(21.5, SMART) == 21.5
    assert s.fit_target(5.0, SMART) == 7.0


def test_no_step_only_clamps():
    a = adapters.adapter_for(None)
    assert a.fit_target(21.37, {"min_temp": 5, "max_temp": 30}) == 21.37
    assert a.fit_target(None, {}) is None


def test_actual_heating_from_hvac_action():
    a = adapters.adapter_for("smart_thermostat")
    assert a.actual_heating({"hvac_action": "heating"}) is True
    assert a.actual_heating({"hvac_action": "idle"}) is False
    assert a.actual_heating({"hvac_action": "off"}) is False
    assert a.actual_heating({}) is None
    assert adapters.adapter_for("gree").actual_heating({"hvac_action": "heating"}) is None


def test_heat_mode_and_notes():
    a = adapters.adapter_for(None)
    assert a.heat_mode(SMART) == "heat"
    assert a.heat_mode({"hvac_modes": ["off", "heat_cool"]}) == "heat_cool"
    d = adapters.adapter_for("better_thermostat").describe(SMART)
    assert d["name"] == "Better Thermostat" and d["notes_en"] and d["notes_hu"] and d["step"] == 0.1


# --- two-way: the pure parts -----------------------------------------------------------------------------
def test_mode_watch():
    w = ts.ModeWatch()
    assert w.changed("heat", "off", own_write=True) is None  # HC switched it off itself
    assert w.changed("heat", "off", own_write=False) is True and w.off_by_hand
    assert w.changed("off", "heat", own_write=True) is None and w.off_by_hand  # frost protection by HC
    assert w.changed("heat", "unavailable", own_write=False) is None
    assert w.changed("off", "heat", own_write=False) is False and not w.off_by_hand


def test_write_log_modes():
    log = ts.WriteLog()
    log.note_mode("climate.x", "off", T0)
    assert log.recent_mode("climate.x", "off", T0 + timedelta(seconds=30))
    assert not log.recent_mode("climate.x", "heat", T0)
    assert not log.recent_mode("climate.x", "off", T0 + timedelta(seconds=300))
    assert log.recent_mode("climate.x", "off", T0, consume=True)  # the change it caused has been seen
    assert not log.recent_mode("climate.x", "off", T0)  # ... a later "off" is someone else's


def _sup(**kw):
    cfg = model.HcConfig(**{"control": "external", "season_enabled": False, "night_start": "22:00",
                            "night_end": "06:00", **kw})
    return sup_mod.Supervisor(cfg)


def _inputs(i=0, indoor=20.0, **kw):
    return model.Inputs(now=T0 + timedelta(seconds=30 * i), indoor=Reading(indoor), outdoor=Reading(5.0), **kw)


def test_managed_off_is_respected_and_frost_overrides():
    sup = _sup()
    d = sup.step(_inputs(0, managed_off=True))
    assert d.reason == Reason.MANAGED_OFF and d.external.hvac == "off" and not d.output
    assert "kikapcsolták" in messages.explain(d, "hu") and "switched off by hand" in messages.explain(d, "en")
    d = sup.step(_inputs(1, indoor=5.0, managed_off=True))
    assert d.reason == Reason.FROST and d.external.hvac == "heat"
    d = sup.step(_inputs(2, managed_off=False))
    assert d.reason == Reason.EXTERNAL and d.external.hvac == "heat"


def test_ac_control_ignores_managed_off():
    sup = _sup(control="ac")
    d = sup.step(_inputs(0, managed_off=True, unit_temp=19.0, unit_step=1.0, unit_min=16.0, unit_max=30.0))
    assert d.reason != Reason.MANAGED_OFF


def test_paused_and_adopted_texts():
    d = model.Decision(T0, Reason.EXTERNAL, 22.0, 21.0, 5.0, external=model.ExternalCommand("heat", 22.0),
                       manual=True, manual_until=T0 + timedelta(hours=3), details={"paused": True, "adopted": 22.0})
    hu, en = messages.explain(d, "hu"), messages.explain(d, "en")
    assert "A felügyelet szünetel: nem írok a termosztátra." in hu and "átvettem" in hu
    assert "Supervision paused: not writing to the thermostat." in en and "Adopted the 22 °C" in en


# --- the executor ------------------------------------------------------------------------------------------
class FakeHass:
    def __init__(self, states):
        self._states = states
        self.calls = []
        self.data = {}
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))
        self.services = SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def _executor(hass, adapter=None, exact=False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from custom_components.hc_thermostat.executor import Executor
    ex = Executor(hass, "active", None, "climate.unit", exact_mode=exact)
    if adapter:
        ex.adapter = adapters.adapter_for(adapter)
    return ex


def _ext(hvac, target):
    return model.Decision(T0, Reason.EXTERNAL, target, 20.0, 5.0, external=model.ExternalCommand(hvac, target),
                          output=hvac == "heat")


def test_executor_rounds_to_the_unit_step():
    hass = FakeHass({"climate.unit": SimpleNamespace(state="heat", attributes=GREE)})
    asyncio.run(_executor(hass, "gree").apply(_ext("heat", 22.5)))
    assert hass.calls == [("climate", "set_temperature", {"entity_id": "climate.unit", "temperature": 23.0})]
    hass = FakeHass({"climate.unit": SimpleNamespace(state="heat", attributes={**GREE, "temperature": 23})})
    asyncio.run(_executor(hass, "gree").apply(_ext("heat", 22.5)))
    assert hass.calls == []  # already there after rounding


def test_executor_paused_writes_nothing():
    hass = FakeHass({"climate.unit": SimpleNamespace(state="off", attributes=SMART)})
    ex = _executor(hass, "smart_thermostat")
    ex.paused = True
    asyncio.run(ex.apply(_ext("heat", 22.0)))
    assert hass.calls == []
    ex.paused = False
    asyncio.run(ex.apply(_ext("heat", 22.0)))
    assert ("climate", "set_hvac_mode", {"entity_id": "climate.unit", "hvac_mode": "heat"}) in hass.calls


def test_executor_ac_setpoint_unchanged():
    """AC control already steps and clamps its setpoint: the executor writes it as before."""
    hass = FakeHass({"climate.unit": SimpleNamespace(state="heat", attributes=GREE)})
    d = model.Decision(T0, Reason.AC_HEAT, 21.0, 20.0, 5.0, external=model.ExternalCommand("heat", 22.0), output=True)
    asyncio.run(_executor(hass, "gree", exact=True).apply(d))
    assert hass.calls == [("climate", "set_temperature", {"entity_id": "climate.unit", "temperature": 22.0})]


def test_executor_own_writes_are_logged():
    hass = FakeHass({"climate.unit": SimpleNamespace(state="off", attributes=SMART)})
    asyncio.run(_executor(hass, "smart_thermostat").apply(_ext("heat", 22.37)))
    from custom_components.hc_thermostat.executor import write_log
    now = datetime.now(timezone.utc)
    assert write_log(hass).recent_mode("climate.unit", "heat", now)
    assert write_log(hass).recent("climate.unit", 22.4, now)


# --- through the coordinator with a real Home Assistant core ----------------------------------------------
def _entry(**data):
    base = {"name": "Probe", "role": "standalone", "heat_source": "electric_heater", "system": "radiator",
            "control": "external", "external_climate": "climate.managed", "indoor_entity": "sensor.room",
            "mode": "active", "season_enabled": False}
    return SimpleNamespace(data={**base, **data}, options={}, entry_id="e420", title="Probe", domain="hc_thermostat",
                           async_on_unload=lambda f: None)


def _run(test, **entry):
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from homeassistant.util import dt as dt_util
    from custom_components.hc_thermostat.coordinator import HcCoordinator

    async def run():
        hass = HomeAssistant(tempfile.mkdtemp())
        try:
            hass.states.async_set("sensor.room", "20.0")
            hass.states.async_set("climate.managed", "heat", {**SMART, "temperature": 20.0})

            async def set_mode(call):
                st = hass.states.get(call.data["entity_id"])
                hass.states.async_set(call.data["entity_id"], call.data["hvac_mode"], dict(st.attributes))

            async def set_temp(call):
                st = hass.states.get(call.data["entity_id"])
                hass.states.async_set(call.data["entity_id"], st.state,
                                      {**st.attributes, "temperature": call.data["temperature"]})

            hass.services.async_register("climate", "set_hvac_mode", set_mode)
            hass.services.async_register("climate", "set_temperature", set_temp)
            c = HcCoordinator(hass, _entry(**entry))
            c._started = dt_util.utcnow() - timedelta(hours=1)

            async def refresh():
                c.data = await c._async_update_data()
                await hass.async_block_till_done()

            c.async_request_refresh = refresh
            c.async_save = lambda: asyncio.sleep(0)
            unsub = c.async_track_managed()
            await refresh()
            await test(hass, c, refresh)
            unsub()
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())


def _hand(hass, state=None, **attrs):
    st = hass.states.get("climate.managed")
    hass.states.async_set("climate.managed", state or st.state, {**st.attributes, **attrs})


def test_coordinator_adopts_a_target_set_on_the_thermostat():
    async def t(hass, c, refresh):
        target = c.data.target
        assert hass.states.get("climate.managed").attributes["temperature"] == target  # HC wrote its own target
        assert c.supervisor.manual_target is None  # ... and did not take it back as a hand on the knob
        _hand(hass, temperature=23.4)
        await hass.async_block_till_done()
        assert c.supervisor.manual_target == 23.4
        await refresh()
        assert c.data.target == 23.4 and c.data.manual and c.data.details.get("adopted") == 23.4
        assert c.managed_info()["adopted"]["target"] == 23.4
        hc_wrote = target  # written by HC a moment ago, its echo already seen
        _hand(hass, temperature=hc_wrote)  # back to the value HC wrote a moment ago: still a hand on the knob
        await hass.async_block_till_done()
        assert c.supervisor.manual_target == hc_wrote
    _run(t)


def test_coordinator_respects_off_by_hand_and_continues_when_on_again():
    async def t(hass, c, refresh):
        _hand(hass, "off")
        await hass.async_block_till_done()
        await refresh()
        assert c.data.reason == Reason.MANAGED_OFF and hass.states.get("climate.managed").state == "off"
        await refresh()
        assert hass.states.get("climate.managed").state == "off"  # not switched back on
        for t in ("17.0", "14.0", "11.0", "8.0", "5.0"):  # frost: heat after all (believable steps)
            hass.states.async_set("sensor.room", t)
            await refresh()
        assert c.data.reason == Reason.FROST and hass.states.get("climate.managed").state == "heat"
        assert c.managed_off  # HC's own frost switching does not clear it
        for t in ("8.0", "11.0", "14.0", "17.0", "20.0"):
            hass.states.async_set("sensor.room", t)
            await refresh()
        assert c.data.reason == Reason.MANAGED_OFF and hass.states.get("climate.managed").state == "off"
        _hand(hass, "heat")
        await hass.async_block_till_done()
        await refresh()
        assert c.data.reason == Reason.EXTERNAL and not c.managed_off
        # within two minutes of HC's own switching, a hand switching to the same mode still counts as a hand
        _hand(hass, "off")
        await hass.async_block_till_done()
        await refresh()
        assert c.data.reason == Reason.MANAGED_OFF
        _hand(hass, "heat")
        await hass.async_block_till_done()
        assert not c.managed_off
    _run(t)


def test_adopt_manual_off_keeps_the_old_behaviour():
    async def t(hass, c, refresh):
        _hand(hass, "off", temperature=24.0)
        await hass.async_block_till_done()
        await refresh()
        assert c.data.reason == Reason.EXTERNAL and c.supervisor.manual_target is None
        assert hass.states.get("climate.managed").state == "heat"  # switched back on, as before 0.42.0
    _run(t, adopt_manual=False)


def test_target_source_option_still_works_on_another_entity():
    async def t(hass, c, refresh):
        hass.states.async_set("number.knob", "21.0")
        unsub = c.async_track_target_source()
        hass.states.async_set("number.knob", "22.5")
        await hass.async_block_till_done()
        assert c.supervisor.manual_target == 22.5
        unsub()
    pytest.importorskip("homeassistant")
    _run(t, target_source_entity="number.knob")


def test_pause_writes_nothing_and_resume_adopts():
    async def t(hass, c, refresh):
        before = hass.states.get("climate.managed").attributes["temperature"]
        await c.async_set_paused(True)
        c.supervisor.manual_target = 25.0  # HC target changed while paused
        await refresh()
        assert hass.states.get("climate.managed").attributes["temperature"] == before
        assert c.data.details.get("paused") and "szünetel" in messages.explain(c.data, "hu")
        assert c.log[-1]["text_en"].endswith("Supervision paused: not writing to the thermostat.")
        _hand(hass, temperature=19.5)  # someone sets the thermostat during the pause
        await hass.async_block_till_done()
        await c.async_set_paused(False)
        assert c.supervisor.manual_target == 19.5 and not c.paused
        await refresh()
        assert hass.states.get("climate.managed").attributes["temperature"] == 19.5  # no jump back
    _run(t)


def test_actual_heating_from_hvac_action_unless_a_flame_sensor_is_set():
    async def t(hass, c, refresh):
        _hand(hass, hvac_action="heating")
        await hass.async_block_till_done()
        await refresh()
        assert c.actual is True and c.last_inputs.actual_heating is True
        _hand(hass, hvac_action="idle")
        await refresh()
        assert c.actual is False
    _run(t)

    async def t2(hass, c, refresh):
        hass.states.async_set("binary_sensor.flame", "on")
        _hand(hass, hvac_action="idle")
        await refresh()
        assert c.actual is True  # the configured flame sensor wins
    _run(t2, flame_entity="binary_sensor.flame")


def test_detection_via_the_entity_registry(monkeypatch):
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    coord = importlib.import_module("custom_components.hc_thermostat.coordinator")

    class FakeRegistry:
        def async_get(self, entity_id):
            return SimpleNamespace(platform="smart_thermostat") if entity_id == "climate.managed" else None

        def async_get_entity_id(self, domain, platform, unique_id):
            return "switch.probe_hc_supervision_paused" if unique_id == "e420_supervision_paused" else None

    monkeypatch.setattr(coord.er, "async_get", lambda hass: FakeRegistry())

    async def t(hass, c, refresh):
        assert c.managed_platform == "smart_thermostat" and c.adapter.key == "smart_thermostat"
        assert c._executor.adapter.key == "smart_thermostat"
        assert c.supervision_switch_id() == "switch.probe_hc_supervision_paused"
        info = c.managed_info()
        assert info["adapter_name"] == "Smart Thermostat (PID)" and info["capabilities"]["step"] == 0.1
    _run(t)


def test_relay_controls_get_no_pause_switch():
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    switch = importlib.import_module("custom_components.hc_thermostat.switch")
    added = []
    for control, managed in (("tpi", False), ("pid", False), ("onoff", False), ("curve", False), ("storage", False),
                             ("external", True), ("ac", True)):
        entry = SimpleNamespace(data={"role": "standalone"}, runtime_data=SimpleNamespace(managed=managed, config_entry=SimpleNamespace(entry_id="e", title="T")))
        asyncio.run(switch.async_setup_entry(None, entry, lambda ents, control=control: added.append((control, ents))))
    assert [c for c, _ in added] == ["external", "ac"]


def test_coordinator_managed_only_for_external_and_ac():
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from custom_components.hc_thermostat.coordinator import HcCoordinator

    async def run():
        hass = HomeAssistant(tempfile.mkdtemp())
        try:
            relay = HcCoordinator(hass, _entry(control="tpi", actuator_entity="switch.boiler", external_climate=None))
            assert not relay.managed and relay.managed_info() is None and relay.supervision_switch_id() is None
            ac = HcCoordinator(hass, _entry(control="ac", heat_source="air_conditioner"))
            assert ac.managed and not ac._two_way and not ac.managed_off
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())

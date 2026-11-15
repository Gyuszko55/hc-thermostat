"""0.56.0: writing the targets out – one writer per target, conflict detection, grace after a start, keep-alive,
the supervised trial that ends by itself, the pause switch; the outputs a number / input_number / climate / switch."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
og = importlib.import_module("hc_thermostat.core.output_guard")

T0 = datetime(2026, 11, 15, 16, 0, tzinfo=timezone.utc)
UP = 1e6  # long after the start


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


# --- the guard --------------------------------------------------------------------------------------------------------
def test_writes_only_on_difference_and_never_in_the_grace():
    g = og.OutputGuard()
    assert g.decide(at(0), 40.0, 35.0, at(-60), uptime_s=60) == (False, "grace")
    assert g.decide(at(0), 40.0, 35.0, at(-60), UP) == (True, "write")
    g.wrote(at(0), 40.0)
    assert g.decide(at(1), 40.0, 40.0, at(0), UP) == (False, "in_sync")
    assert g.decide(at(1), 40.1, 40.0, at(0), UP) == (False, "in_sync")  # within the tolerance
    assert g.decide(at(2), None, 40.0, at(0), UP) == (False, "no_value")
    assert g.decide(at(2), 42.0, None, None, UP) == (False, "unavailable")


def test_keepalive_resends_an_unchanged_value():
    g = og.OutputGuard(keepalive_s=600)
    g.wrote(at(0), 40.0)
    assert g.decide(at(5), 40.0, 40.0, at(0), UP) == (False, "in_sync")
    assert g.decide(at(10), 40.0, 40.0, at(0), UP) == (True, "keepalive")


def test_someone_elses_write_is_a_conflict_until_they_give_way():
    g = og.OutputGuard()
    g.wrote(at(0), 40.0)
    assert g.decide(at(1), 40.0, 40.0, at(0), UP)[1] == "in_sync"
    # the PLC (or a person) wrote 45 a minute later: HC does not fight it
    assert g.decide(at(2), 40.0, 45.0, at(1), UP) == (False, "conflict") and g.conflict and g.conflict_value == 45.0
    assert g.decide(at(3), 38.0, 45.0, at(1), UP) == (False, "conflict")
    assert g.decide(at(4), 38.0, 40.0, at(3.5), UP) == (True, "write")  # its value is HC's again: back to writing
    assert not g.conflict


def test_own_write_settling_is_not_a_conflict():
    g = og.OutputGuard()
    g.wrote(at(0), 40.0)
    # the output reports an old value a moment after HC's write (the device has not confirmed yet)
    # 0.56.1: HC waits for the confirmation instead of writing again at once
    assert g.decide(at(0.03), 40.0, 38.0, at(0.02), UP) == (False, "confirming")


def test_trial_and_active():
    assert og.effective("shadow", None, 4, at(0)) == (False, None)
    assert og.effective("active", None, 4, at(0)) == (True, None)
    assert og.effective("trial", None, 4, at(0)) == (False, None)
    assert og.effective("trial", at(0), 4, at(239)) == (True, at(240))
    assert og.effective("trial", at(0), 4, at(240)) == (False, at(240))


# --- Home Assistant side ----------------------------------------------------------------------------------------------
class FakeHass:
    def __init__(self, states, unit="°C"):
        self._states = states
        self.calls = []
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))
        self.services = SimpleNamespace(async_call=self._call)
        self.config = SimpleNamespace(units=SimpleNamespace(temperature_unit=unit))
        self.updated = []
        self.config_entries = SimpleNamespace(async_update_entry=lambda e, options: self.updated.append(options))

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def st(entity_id, state, changed=None, **attrs):
    return SimpleNamespace(entity_id=entity_id, state=str(state), attributes=attrs, last_changed=changed or at(-60),
                           last_updated=changed or at(-60))


def run(coro):
    return asyncio.run(coro)


def writer(hass, eid, **kw):
    ow = importlib.import_module("hc_thermostat.output_writer")
    return ow.OutputWriter(hass, eid, **kw)


def test_number_write_is_clamped_and_stepped():
    hass = FakeHass({"number.plc_rad": st("number.plc_rad", 30, min=20, max=50, step=1, unit_of_measurement="°C")})
    w = writer(hass, "number.plc_rad")
    assert run(w.apply(at(0), 41.5, True, UP)) == "write"
    assert hass.calls == [("number", "set_value", {"entity_id": "number.plc_rad", "value": 42.0})]
    hass.calls.clear()
    assert run(w.apply(at(1), 58.0, True, UP)) == "write"
    assert hass.calls[0][2]["value"] == 50.0  # the PLC register's own maximum


def test_landed_value_counts_as_in_sync():
    hass = FakeHass({"number.p": st("number.p", 42, min=20, max=50, step=1, unit_of_measurement="°C")})
    w = writer(hass, "number.p")
    assert run(w.apply(at(0), 41.6, True, UP)) == "in_sync"  # 41.6 would land as 42: nothing to write
    assert hass.calls == []


def test_shadow_paused_and_unset_write_nothing():
    hass = FakeHass({"number.p": st("number.p", 30, min=20, max=50, step=0.5)})
    w = writer(hass, "number.p")
    assert run(w.apply(at(0), 40.0, False, UP)) == "shadow"
    assert run(writer(hass, None).apply(at(0), 40.0, True, UP)) == "none"
    assert hass.calls == []


def test_onoff_switch_and_climate():
    hass = FakeHass({"switch.hp": st("switch.hp", "off"),
                     "climate.hp": st("climate.hp", "off", hvac_modes=["off", "heat", "cool"], temperature=35)})
    w = writer(hass, "switch.hp", onoff=True)
    assert run(w.apply(at(0), True, True, UP)) == "write"
    assert hass.calls[-1] == ("homeassistant", "turn_on", {"entity_id": "switch.hp"})
    c = writer(hass, "climate.hp", onoff=True)
    run(c.apply(at(0), True, True, UP))
    assert hass.calls[-1] == ("climate", "set_hvac_mode", {"entity_id": "climate.hp", "hvac_mode": "heat"})
    t = writer(hass, "climate.hp")
    run(t.apply(at(0), 42.0, True, UP))
    assert hass.calls[-1] == ("climate", "set_temperature", {"entity_id": "climate.hp", "temperature": 42.0})


def test_failed_write_is_reported_not_raised():
    hass = FakeHass({"number.p": st("number.p", 30, min=20, max=50)})

    async def boom(*a, **k):
        raise RuntimeError("PLC offline")
    hass.services.async_call = boom
    w = writer(hass, "number.p")
    assert run(w.apply(at(0), 40.0, True, UP)) == "error"
    assert w.error == "PLC offline" and w.guard.writes == 0


def test_trial_ends_by_itself_and_conflict_is_notified(monkeypatch):
    ow = importlib.import_module("hc_thermostat.output_writer")
    notes = []
    monkeypatch.setattr(ow.pn, "async_create", lambda hass, msg, title=None, notification_id=None: notes.append(notification_id))
    monkeypatch.setattr(ow.pn, "async_dismiss", lambda hass, nid: notes.append("dismiss:" + nid))
    hass = FakeHass({})
    entry = SimpleNamespace(entry_id="e1", title="Radiator circuit", options={"mode": "trial"})
    wc = ow.WriteControl(hass, entry, {"mode": "trial", "trial_hours": 2, "trial_start": at(0).isoformat()})
    assert wc.writing(at(60)) and wc.status(at(60)) == "trial"
    wc.paused = True
    assert not wc.writing(at(60)) and wc.status(at(60)) == "paused"
    wc.paused = False
    run(wc.tick(at(119)))
    assert hass.updated == []
    run(wc.tick(at(121)))
    assert hass.updated == [{"mode": "shadow", "trial_start": None}] and notes == ["hc_trial_e1"]
    run(wc.tick(at(122)))
    assert len(hass.updated) == 1  # once
    w = SimpleNamespace(entity_id="number.p", status="conflict", guard=SimpleNamespace(conflict_value=45, last_value=40))
    wc.note_conflict(w)
    wc.note_conflict(w)
    w.status = "in_sync"
    wc.note_conflict(w)
    assert notes[1:] == ["hc_conflict_e1_number.p", "dismiss:hc_conflict_e1_number.p"]
    assert ow.WriteControl(hass, entry, {}).mode == "shadow"
    assert ow.WriteControl(hass, entry, {"mode": "nonsense"}).mode == "shadow"


def test_settings_need_an_output_and_a_confirmation_and_a_trial_start():
    cf = importlib.import_module("hc_thermostat.config_flow")
    assert cf._write_errors("circuit", {"mode": "shadow"}) == {}
    assert cf._write_errors("circuit", {"mode": "active", "confirm": True}) == {"mode": "no_output"}
    assert cf._write_errors("hp_coord", {"mode": "trial", "hp_switch_entity": "switch.hp"}) == {"confirm": "confirm_active"}
    assert cf._write_errors("hp_coord", {"mode": "trial", "hp_switch_entity": "switch.hp", "confirm": True}) == {}
    out = cf._with_trial({"mode": "trial", "confirm": True}, {"mode": "shadow"})
    assert "confirm" not in out and out["trial_start"]
    keep = cf._with_trial({"mode": "trial"}, {"mode": "trial", "trial_start": "2026-11-15T10:00:00+00:00"})
    assert keep["trial_start"] == "2026-11-15T10:00:00+00:00"  # editing during a trial keeps its start
    assert cf._with_trial({"mode": "active"}, {"mode": "trial", "trial_start": "x"})["trial_start"] is None


def test_no_service_call_outside_the_writer():
    base = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
    for name in ("circuit_coordinator.py", "hp_coord_coordinator.py", "core/hp_coord.py", "core/circuit.py",
                 "core/output_guard.py"):
        assert "async_call" not in (base / name).read_text("utf8")

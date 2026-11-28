"""0.88.0: every save shows what changes first, the settings before it go to the history, and an earlier one can be
restored from the menu (config_flow.py, history.py)."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

cf = importlib.import_module("hc_thermostat.config_flow")
hist = importlib.import_module("hc_thermostat.history")
rd = importlib.import_module("hc_thermostat.readiness")
BASE = ROOT / "custom_components" / "hc_thermostat"


def _setup(monkeypatch, options, stored=None):
    saved = {"items": list(stored or [])}

    async def load(hass, entry_id):
        return list(saved["items"])

    async def push(hass, entry_id, opts, changed):
        saved["items"].insert(0, {"at": "2026-11-28T13:05:00+00:00", "options": dict(opts), "changed": changed})

    async def labels(hass, lang):
        return {"target_comfort": "Komfort cél", "target_eco": "Eco cél"}

    async def ready(hass, entry, lang=None, conf=None):
        return {"ready": True, "head": "Élesíthető", "items": []}
    monkeypatch.setattr(hist, "async_load", load)
    monkeypatch.setattr(hist, "async_push", push)
    monkeypatch.setattr(hist, "async_labels", labels)
    monkeypatch.setattr(rd, "async_check", ready)
    monkeypatch.setattr(cf.OptionsFlow, "async_create_entry", lambda self, **kw: ("create", kw), raising=False)
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data={"role": "standalone", "control": "tpi", "indoor_entity": "sensor.living",
                                  "actuator_entity": "switch.boiler"},
                            options=options, title="Kazán HC", entry_id="e1", runtime_data=None)
    type(flow).config_entry = property(lambda self: entry)
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="hu"), states=SimpleNamespace(get=lambda e: None))
    flow.async_show_menu = lambda **kw: ("menu", kw)
    flow.async_show_form = lambda **kw: ("form", kw)
    return flow, saved


def test_a_save_shows_what_changes_then_keeps_the_old_one(monkeypatch):
    flow, saved = _setup(monkeypatch, {"mode": "active", "target_comfort": 21.0})
    menu = asyncio.run(flow.async_step_init())[1]["menu_options"]
    assert "restore" not in menu  # nothing to go back to yet
    kind, kw = flow.async_create_entry(data={"mode": "active", "target_comfort": 21.5})
    assert kind == "form" and kw["step_id"] == "confirm_changes"
    assert kw["description_placeholders"]["changes"] == "- Komfort cél: 21 → 21,5"
    assert saved["items"] == []  # nothing saved before the confirmation
    kind, kw = asyncio.run(flow.async_step_confirm_changes({}))
    assert kind == "create" and kw["data"]["target_comfort"] == 21.5
    assert saved["items"][0]["options"] == {"mode": "active", "target_comfort": 21.0}
    assert saved["items"][0]["changed"] == ["target_comfort"]


def test_no_change_and_going_live_save_straight(monkeypatch):
    flow, saved = _setup(monkeypatch, {"mode": "shadow", "target_comfort": 21.0})
    asyncio.run(flow.async_step_init())
    assert flow.async_create_entry(data={"mode": "active", "target_comfort": 21.0})[0] == "create"
    assert flow.async_create_entry(data={"mode": "shadow", "target_comfort": 21.0})[0] == "create"
    assert saved["items"] == []


def test_restore_an_earlier_setting_keeps_the_mode(monkeypatch):
    old = {"at": "2026-11-27T08:00:00+00:00", "options": {"mode": "shadow", "target_comfort": 20.0, "target_eco": 17.0},
           "changed": ["target_comfort", "target_eco"]}
    flow, saved = _setup(monkeypatch, {"mode": "active", "target_comfort": 21.5, "target_eco": 18.0}, [old])
    menu = asyncio.run(flow.async_step_init())[1]["menu_options"]
    assert menu[-2:] == ["restore", "go_shadow"]
    kind, kw = asyncio.run(flow.async_step_restore())
    assert kind == "form" and kw["step_id"] == "restore"
    label = kw["data_schema"].schema
    kind, kw = asyncio.run(flow.async_step_restore({"version": "0"}))
    assert kw["step_id"] == "restore_confirm"
    assert kw["description_placeholders"]["changes"] == "- Komfort cél: 21,5 → 20\n- Eco cél: 18 → 17" or \
        kw["description_placeholders"]["changes"] == "- Eco cél: 18 → 17\n- Komfort cél: 21,5 → 20"
    kind, kw = asyncio.run(flow.async_step_restore_confirm({}))
    assert kind == "create" and kw["data"] == {"mode": "active", "target_comfort": 20.0, "target_eco": 17.0}
    assert saved["items"][0]["options"]["target_comfort"] == 21.5  # a restore can be undone too
    assert label


def test_the_history_label_and_translations(monkeypatch):
    flow, _ = _setup(monkeypatch, {})
    asyncio.run(flow.async_step_init())
    text = flow._history_label({"at": "2026-11-27T08:00:00+00:00", "changed": ["target_comfort", "target_eco", "a", "b"]}, "hu")
    assert text.endswith("előtti állapot (akkor változott: Komfort cél, Eco cél, a +1)")
    for lang in ("hu", "en"):
        st = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]["step"]
        assert {"confirm_changes", "restore", "restore_confirm"} <= set(st) and "restore" in st["init"]["menu_options"]
        assert "{changes}" in st["confirm_changes"]["description"] and "{changes}" in st["restore_confirm"]["description"]

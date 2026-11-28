"""0.89.0: the recommendation, the goals and the advice in the settings menu (config_flow.py, tuning_ha.py)."""

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
th = importlib.import_module("hc_thermostat.tuning_ha")
BASE = ROOT / "custom_components" / "hc_thermostat"
DATA = {"role": "standalone", "control": "tpi", "system": "radiator", "heat_source": "gas_boiler",
        "indoor_entity": "sensor.living", "actuator_entity": "switch.boiler"}


def _flow(monkeypatch, options, stats=None):
    saved = []

    async def load(hass, entry_id):
        return []

    async def push(hass, entry_id, opts, changed):
        saved.append((dict(opts), changed))

    async def labels(hass, lang):
        return {"cycle_s": "Ciklusidő", "min_on_s": "Legrövidebb működés", "min_off_s": "Legrövidebb szünet"}

    async def ready(hass, entry, lang=None, conf=None):
        return {"ready": True, "head": "Élesíthető", "items": []}

    async def numbers(hass, entry, conf):
        return stats
    monkeypatch.setattr(hist, "async_load", load)
    monkeypatch.setattr(hist, "async_push", push)
    monkeypatch.setattr(hist, "async_labels", labels)
    monkeypatch.setattr(rd, "async_check", ready)
    monkeypatch.setattr(th, "async_stats", numbers)
    monkeypatch.setattr(cf.OptionsFlow, "async_create_entry", lambda self, **kw: ("create", kw), raising=False)
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data=dict(DATA), options=options, title="Kazán HC", entry_id="e1", runtime_data=None)
    type(flow).config_entry = property(lambda self: entry)
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="hu"), states=SimpleNamespace(get=lambda e: None))
    flow.async_show_menu = lambda **kw: ("menu", kw)
    flow.async_show_form = lambda **kw: ("form", kw)
    asyncio.run(flow.async_step_init())
    return flow, saved


def test_the_menu_has_the_goal_and_the_recommendation(monkeypatch):
    flow, _ = _flow(monkeypatch, {"mode": "shadow"})
    menu = asyncio.run(flow.async_step_init())[1]["menu_options"]
    assert menu == ["targets", "presets", "check", "sensors", "rooms", "goal", "profile", "settings", "change_control",
                    "go_live"]


def test_the_recommendation_ticks_nothing_and_goes_through_the_comparison(monkeypatch):
    flow, saved = _flow(monkeypatch, {"mode": "active", "cycle_s": 600.0, "min_off_s": 600.0, "min_on_s": 120.0})
    kind, kw = asyncio.run(flow.async_step_profile())
    assert kw["step_id"] == "profile" and "Ciklusidő: 10 perc → 15 perc – rövidebb a javasoltnál" in kw["description_placeholders"]["list"]
    assert asyncio.run(flow.async_step_profile({"adopt": []}))[0] == "menu"  # nothing ticked: nothing changes
    kind, kw = asyncio.run(flow.async_step_profile({"adopt": ["cycle_s"]}))
    assert kw["step_id"] == "confirm_changes" and kw["description_placeholders"]["changes"] == "- Ciklusidő: 10 → 15 perc"
    kind, kw = asyncio.run(flow.async_step_confirm_changes({}))
    assert kind == "create" and kw["data"] == {"mode": "active", "cycle_s": 900.0, "min_off_s": 600.0, "min_on_s": 120.0}
    assert saved[0][1] == ["cycle_s"]
    flow, _ = _flow(monkeypatch, {})
    assert "Minden beállítás" in asyncio.run(flow.async_step_profile())[1]["description_placeholders"]["list"]


def test_a_goal_shows_a_preview_with_the_estimate_then_saves(monkeypatch):
    flow, saved = _flow(monkeypatch, {"mode": "active"}, {"days": 7, "starts_day": 21.0, "dev_c": 0.2})
    kind, kw = asyncio.run(flow.async_step_goal())
    assert kw["step_id"] == "goal"
    kind, kw = asyncio.run(flow.async_step_goal({"goal": "fewer_switching"}))
    prev = kw["description_placeholders"]["preview"]
    assert kw["step_id"] == "goal_preview" and "- Ciklusidő: 15 perc → 25 perc" in prev
    assert "napi indítás kb. 21 → 13" in prev and "durva becslés" in prev
    kind, kw = asyncio.run(flow.async_step_goal_preview({}))
    assert kind == "create" and kw["data"]["cycle_s"] == 1500.0 and kw["data"]["mode"] == "active"
    assert sorted(saved[0][1]) == ["cycle_s", "min_off_s", "min_on_s"]
    flow, _ = _flow(monkeypatch, {"control": "external"})
    flow._goal = "steadier"
    assert "nem változtat semmit" in asyncio.run(flow.async_step_goal_preview())[1]["description_placeholders"]["preview"]
    flow, _ = _flow(monkeypatch, {"mode": "shadow"}, {"days": 7, "starts_day": 21.0})
    flow._goal = "fewer_switching"
    assert "becslés" not in asyncio.run(flow.async_step_goal_preview())[1]["description_placeholders"]["preview"]


def test_the_check_page_carries_the_advice(monkeypatch):
    flow, _ = _flow(monkeypatch, {"mode": "active"}, {"days": 7, "starts_day": 30.0, "short_runs_pct": 80})
    th._CACHE.clear()
    kw = asyncio.run(flow.async_step_check())[1]
    assert "Sok rövid menet" in kw["description_placeholders"]["advice"]
    for lang in ("hu", "en"):
        st = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]["step"]
        assert "{advice}" in st["check"]["description"] and {"profile", "goal", "goal_preview"} <= set(st)
        assert {"goal", "profile"} <= set(st["init"]["menu_options"])

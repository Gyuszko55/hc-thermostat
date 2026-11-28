"""0.86.0: the options menu by task – order, the status line, the read-only check page, the thermometers and windows
step, the presets on their own; the other roles keep their own forms."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

cf = importlib.import_module("hc_thermostat.config_flow")
rd = importlib.import_module("hc_thermostat.readiness")
TR = {lang: json.loads((ROOT / f"custom_components/hc_thermostat/translations/{lang}.json").read_text()) for lang in ("hu", "en")}


def _flow(options, data=None, runtime=None):
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data=data or {"role": "standalone", "control": "tpi", "indoor_entity": "sensor.living",
                                          "actuator_entity": "switch.boiler"},
                            options=options, title="Boiler HC", entry_id="e1", runtime_data=runtime)
    type(flow).config_entry = property(lambda self: entry)
    flow.hass = SimpleNamespace(config=SimpleNamespace(language="hu"))
    flow.async_show_menu = lambda **kw: ("menu", kw)
    flow.async_show_form = lambda **kw: ("form", kw)
    flow.async_create_entry = lambda **kw: ("create", kw)
    return flow


class _Coord:
    def plain_summary(self, lang=None):
        return {"state": "idle", "headline": "Nem fűt", "lines": ["A ház elérte a célt (bent 22,6 °C, cél 22,5 °C).",
                                                                 "A cél 22,5 °C: nappali, otthoni cél."],
                "shadow": True, "note": "Árnyék mód: ezt tenné, de nem kapcsol."}


def test_the_menu_by_task_with_a_status_line(monkeypatch):
    async def ready(hass, entry, lang=None, conf=None):
        return {"ready": True, "head": "Élesíthető, 1 figyelmeztetéssel", "items": [{"id": "short_shadow", "level": "warn",
                "title": "Csak 3 órája fut árnyék módban (javasolt: 24 óra)", "fix": "Nézd át az árnyék döntéseket"}]}
    monkeypatch.setattr(rd, "async_check", ready)
    kind, kw = asyncio.run(_flow({"mode": "shadow"}, runtime=_Coord()).async_step_init())
    assert kind == "menu" and kw["menu_options"] == ["targets", "presets", "check", "sensors", "rooms", "goal", "profile", "settings",
                                                     "change_control", "go_live"]
    assert kw["description_placeholders"]["status"] == (
        "**Most:** Nem fűt – A ház elérte a célt (bent 22,6 °C, cél 22,5 °C).\n\n"
        "**Élesítés:** Élesíthető, 1 figyelmeztetéssel.\n\n")
    live = asyncio.run(_flow({"mode": "active"}, runtime=_Coord()).async_step_init())[1]
    assert live["menu_options"][-1] == "go_shadow" and "**Élesítés:** élesen fut." in live["description_placeholders"]["status"]
    # not loaded: no "now" line, the go-live line only; the menu still opens
    status = asyncio.run(_flow({"mode": "shadow"}).async_step_init())[1]["description_placeholders"]["status"]
    assert status == "**Élesítés:** Élesíthető, 1 figyelmeztetéssel.\n\n"

    async def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(rd, "async_check", broken)
    assert asyncio.run(_flow({"mode": "shadow"}).async_step_init())[1]["description_placeholders"]["status"] == ""
    # an external thermostat instance has no rooms item
    ext = _flow({}, data={"role": "standalone", "control": "external", "external_climate": "climate.t"})
    assert "rooms" not in asyncio.run(ext.async_step_init())[1]["menu_options"]


def test_the_other_roles_keep_their_own_forms():
    for role in ("central", "buffer"):
        kind, kw = asyncio.run(_flow({}, data={"role": role}).async_step_init())
        assert kind == "form" and kw["step_id"] == role


def test_the_check_page_is_read_only_and_goes_back(monkeypatch):
    async def ready(hass, entry, lang=None, conf=None):
        return {"ready": False, "head": "Még nem élesíthető: 1 akadály", "items": [
            {"id": "entity_unavailable", "level": "block", "title": "Benti hőmérő nem elérhető: sensor.living",
             "fix": "Nézd meg az eszközt"}]}
    monkeypatch.setattr(rd, "async_check", ready)
    flow = _flow({"mode": "shadow"}, runtime=_Coord())
    kind, kw = asyncio.run(flow.async_step_check())
    ph = kw["description_placeholders"]
    assert kind == "form" and kw["step_id"] == "check" and not kw["data_schema"].schema
    assert ph["summary"].startswith("*Árnyék mód: ezt tenné, de nem kapcsol.*\n\n**Nem fűt**\n- A ház elérte a célt")
    assert ph["checklist"].startswith("**Még nem élesíthető: 1 akadály**\n- ⛔ Benti hőmérő nem elérhető")
    assert asyncio.run(flow.async_step_check({}))[0] == "menu"  # OK: back to the menu, nothing saved


def test_thermometers_and_windows_save_only_their_keys():
    flow = _flow({"mode": "active", "target_home": 22.5, "window_entities": ["binary_sensor.old"]})
    kind, kw = asyncio.run(flow.async_step_sensors())
    assert kind == "form" and [str(k) for k in kw["data_schema"].schema] == [
        "indoor_entity", "outdoor_entity", "window_entities", "presence_entities"]
    assert asyncio.run(flow.async_step_sensors({"outdoor_entity": "sensor.out"}))[1]["errors"] == {"indoor_entity": "indoor_required"}
    kind, kw = asyncio.run(flow.async_step_sensors({"indoor_entity": "sensor.new", "window_entities": []}))
    assert kind == "create" and kw["data"] == {"mode": "active", "target_home": 22.5, "indoor_entity": "sensor.new",
                                               "outdoor_entity": None, "window_entities": None, "presence_entities": None}
    curve = _flow({}, data={"role": "standalone", "control": "curve", "flow_setpoint_entity": "number.flow"})
    assert asyncio.run(curve.async_step_sensors({"indoor_entity": "sensor.t"}))[1]["errors"] == {"outdoor_entity": "outdoor_required"}
    rooms = _flow({"rooms": [{"area": "living"}]})
    kind, kw = asyncio.run(rooms.async_step_sensors())
    assert "indoor_entity" not in [str(k) for k in kw["data_schema"].schema]  # the rooms give it
    assert "**Helyiségek**" in kw["description_placeholders"]["rooms"]
    trv = _flow({}, data={"role": "standalone", "control": "trv"})
    assert asyncio.run(trv.async_step_sensors({}))[0] == "create"  # TRV heads only: no indoor thermometer needed


def test_presets_from_the_menu_save_on_their_own():
    flow = _flow({"mode": "active", "target_home": 22.5})
    asyncio.run(flow.async_step_init())
    kind, kw = asyncio.run(flow.async_step_presets({"target_comfort": 23.0}))
    assert kind == "create" and kw["data"] == {"mode": "active", "target_home": 22.5, "target_comfort": 23.0}


def test_texts_in_both_languages():
    for lang in ("hu", "en"):
        st, err = TR[lang]["options"]["step"], TR[lang]["options"]["error"]
        assert set(st["init"]["menu_options"]) >= {"targets", "presets", "check", "sensors", "rooms", "settings",
                                                    "change_control", "go_live", "go_shadow"}
        assert "{status}" in st["init"]["description"]
        assert "{summary}" in st["check"]["description"] and "{checklist}" in st["check"]["description"]
        assert set(st["sensors"]["data"]) == {"indoor_entity", "outdoor_entity", "window_entities", "presence_entities"}
        assert "{rooms}" in st["sensors"]["description"] and err["outdoor_required"] and err["indoor_required"]

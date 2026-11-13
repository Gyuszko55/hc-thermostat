"""0.46.0: rooms from ticked areas – the options step by step (areas, one section per room, own schedules), per room
window / door contacts (a TRV room's own heads only; elsewhere the boiler as before), HC's room groups, the home's
name, the wizard's area check list."""

import asyncio
import importlib
import json
import sys
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
rm = importlib.import_module("hc_thermostat.core.room_model")
rf = importlib.import_module("hc_thermostat.room_form")
cf = importlib.import_module("hc_thermostat.config_flow")
groups = importlib.import_module("hc_thermostat.room_groups")
from test_rooms_430 import T0, _coordinator, _decision, _state  # noqa: E402

PKG = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

ROOMS = [
    {"key": "nappali", "name": "Nappali", "area": "nappali", "sensors": ["sensor.n1"], "windows": ["binary_sensor.terasz_ajto"]},
    {"key": "konyha", "name": "Konyha", "area": "konyha", "sensors": ["sensor.k1"], "trvs": ["climate.konyha_trv"],
     "windows": ["binary_sensor.konyha_ajto"]},
    {"key": "halo", "name": "Háló", "area": "halo", "sensors": ["sensor.h1"], "windows": ["binary_sensor.halo_ablak"]},
]

AREAS = {"areas": [
    {"area": "konyha", "name": "Konyha", "sensors": [{"id": "sensor.k1"}, {"id": "sensor.k2"}, {"id": "sensor.trv_local", "head": True}],
     "trvs": [{"id": "climate.konyha_trv", "head": True}, {"id": "climate.gree", "head": False}],
     "presence": [{"id": "binary_sensor.konyha_mozgas"}], "windows": [{"id": "binary_sensor.konyha_ajto"}]},
    {"area": "szerver", "name": "Szerver", "sensors": [{"id": "sensor.rack"}], "trvs": [], "presence": [], "windows": []},
    {"area": "udvar", "name": "Udvar", "outdoor": True, "sensors": [{"id": "sensor.kint"}], "trvs": [], "presence": [],
     "windows": []},
    {"area": "halo", "name": "Háló", "sensors": [{"id": "sensor.h1"}], "trvs": [], "presence": [], "windows": []},
], "tracking": [{"id": "sensor.phone_room"}], "temperature": [], "climates": []}


# --- windows -----------------------------------------------------------------------------------------------------
def test_a_trv_rooms_window_is_its_own_the_others_stop_the_boiler():
    specs = rm.parse_rooms(ROOMS)
    assert rm.own_windows(specs, "nappali") == {"binary_sensor.konyha_ajto"}
    general = rm.general_windows(["binary_sensor.konyha_ajto", "binary_sensor.bejarat"], specs, "nappali")
    # the kitchen door is ticked in the TRV kitchen: from then on it closes only the kitchen's head
    assert general == ["binary_sensor.bejarat", "binary_sensor.terasz_ajto", "binary_sensor.halo_ablak"]
    # without rooms: the instance's list exactly as before (the live Cirkó until its kitchen door is ticked)
    assert rm.general_windows(["binary_sensor.konyha_ajto"], [], None) == ["binary_sensor.konyha_ajto"]


def test_the_room_holds_frost_after_the_window_delay_and_resumes_at_once():
    spec = rm.parse_rooms(ROOMS)[1]
    c = rm.RoomControl()
    assert not c.update_window(T0, True, 120)
    assert c.target(spec, T0, 21.0, "home", 7.0, 15.0, window=c.window_open).target == 21.0
    assert c.update_window(T0 + timedelta(seconds=130), True, 120)
    t = c.target(spec, T0, 21.0, "home", 7.0, 15.0, window=c.window_open)
    assert t.reason == "window" and t.target == 7.0
    assert not c.update_window(T0 + timedelta(seconds=140), False, 120)
    assert c.target(spec, T0, 21.0, "home", 7.0, 15.0, window=c.window_open).target == 21.0


def test_in_the_coordinator_the_kitchen_door_closes_the_kitchen_head_not_the_boiler(monkeypatch):
    states = {"sensor.n1": _state(21.0), "sensor.k1": _state(21.0), "sensor.h1": _state(20.0),
              "climate.konyha_trv": _state("heat", temperature=21.0, current_temperature=21.0, target_temp_step=0.5),
              "binary_sensor.konyha_ajto": _state("on"), "binary_sensor.terasz_ajto": _state("off"),
              "binary_sensor.halo_ablak": _state("off")}
    c, clock = _coordinator(monkeypatch, states, {"rooms": ROOMS, "leading_room": "nappali",
                                                  "window_entities": ["binary_sensor.konyha_ajto"]})
    assert c._window_open() is False  # the boiler goes on
    c._update_presence(T0)
    clock["now"] = T0 + timedelta(minutes=3)
    c._update_presence(clock["now"])
    asyncio.run(c._apply_trvs(_decision(now=clock["now"])))
    k = c.room_states["konyha"]
    assert k["reason"] == "window" and k["target"] == c.cfg.frost_temp and k["window"] is True
    assert c.hass.calls[-1][2]["temperature"] == c.cfg.frost_temp
    states["binary_sensor.halo_ablak"] = _state("on")  # a window of a room without a TRV: the boiler stops, as before
    assert c._window_open() is True
    assert set(c._window_ids()) == {"binary_sensor.terasz_ajto", "binary_sensor.halo_ablak"}


# --- groups ------------------------------------------------------------------------------------------------------
def test_groups_only_where_a_room_has_two_or_more(monkeypatch):
    rooms = [{**ROOMS[0], "sensors": ["sensor.n1", "sensor.n2"]}, {**ROOMS[1], "presence": ["sensor.p1", "binary_sensor.m"]},
             ROOMS[2]]
    states = {"sensor.n1": _state(21.0), "sensor.n2": _state(22.0), "sensor.p1": _state("Nappali", area_id="nappali"),
              "binary_sensor.m": _state("off")}
    c, _ = _coordinator(monkeypatch, states, {"rooms": rooms, "leading_room": "nappali", "role": "standalone",
                                              "control": "pid"})
    got = {(s.key, k) for s, k in groups.groups_of(c, groups.KINDS)}
    assert got == {("nappali", "temperature"), ("konyha", "presence")}
    assert c.room_group_value("nappali", "temperature") == 21.5
    assert c.room_group_value("konyha", "presence") is False  # the phone is in the living room, no motion
    states["binary_sensor.m"] = _state("on")
    assert c.room_group_value("konyha", "presence") is True
    c.conf = {"role": "standalone", "control": "pid", "room_sensors": ["sensor.n1", "sensor.n2"]}
    c._specs = None
    assert groups.groups_of(c, groups.KINDS) == []  # the legacy shape gets no groups (it stays as it was)
    assert groups.group_unique_id("e1", "konyha", "presence") == "e1_roomgrp_konyha_presence"


# --- the options: step 1 -----------------------------------------------------------------------------------------
def test_the_area_list_shows_what_each_has_and_leaves_outdoor_out():
    opts = rf.area_options("hu", AREAS, [], {"szerver": "Iroda HC"})
    labels = {o["value"]: o["label"] for o in opts}
    assert "udvar" not in labels
    assert labels["konyha"] == "Konyha – 3 hőmérő · 2 szelepfej · 1 jelenlét · 1 ablak/ajtó"
    assert labels["szerver"].endswith("(másik HC-példány: Iroda HC)")
    with_custom = rf.area_options("en", AREAS, [{"key": "muhely", "name": "Műhely", "area": None}], {})
    assert with_custom[-1] == {"value": "custom:muhely", "label": "Műhely (no area)"}


def test_a_ticked_area_comes_filled_and_an_unticked_one_goes():
    rooms = rf.pick_rooms(["konyha", "halo"], [], AREAS, "Műhely, Garázs")
    k = rooms[0]
    assert k["sensors"] == ["sensor.k1", "sensor.k2"]  # not the head's own thermometer
    assert k["trvs"] == ["climate.konyha_trv"]  # a real head only (not the Gree)
    assert k["presence"] == ["binary_sensor.konyha_mozgas"] and k["windows"] == ["binary_sensor.konyha_ajto"]
    assert rooms[1]["presence"] == [] and rooms[1]["trvs"] == []
    assert [r["name"] for r in rooms[2:]] == ["Műhely", "Garázs"] and rooms[2]["area"] is None
    kept = rf.pick_rooms(["halo", "custom:muhely"], rooms, AREAS, "")
    assert [r["key"] for r in kept] == ["halo", "muhely"]  # the kitchen unticked: gone; nothing is re-filled


# --- step 2 ------------------------------------------------------------------------------------------------------
class _States:
    def __init__(self, states):
        self._s = states

    def get(self, e):
        return self._s.get(e)


def _hass(lang="hu"):
    states = {"sensor.k1": _state(22.7, friendly_name="Konyha TH01", unit_of_measurement="°C", device_class="temperature"),
              "sensor.k2": _state(22.1, friendly_name="Konyha TH02", unit_of_measurement="°C", device_class="temperature"),
              "climate.konyha_trv": _state("heat", friendly_name="Konyha TRV"),
              "binary_sensor.kamra": _state("off", friendly_name="Kamra ajtó", device_class="door"),
              "sensor.other_t": _state(20.0, friendly_name="Másik", unit_of_measurement="°C"),
              "binary_sensor.motion": _state("off", device_class="motion")}
    return SimpleNamespace(states=_States(states), config=SimpleNamespace(language=lang))


def test_a_section_has_check_boxes_and_the_trv_fields_only_where_they_count():
    hass = _hass()
    room = rf.pick_rooms(["konyha"], [], AREAS, "")[0]
    cands = rf.room_candidates(room, AREAS["areas"][0], AREAS["tracking"], set())
    sec = rf.room_section(hass, "hu", room, cands, "nappali", 1, 3)
    keys = [str(k) for k in sec.schema.schema]
    assert keys[:2] == ["Név", "Hőmérők"] and "Szelepfejek" in keys and "Ablak / ajtó" in keys and "Jelenlét" in keys
    assert "Cél" in keys and "Kalibrálás – Konyha TRV" in keys and sec.options["collapsed"] is False  # new: open
    sensors = next(v for k, v in sec.schema.schema.items() if str(k) == "Hőmérők").config["options"]
    assert sensors[0]["label"] == "Konyha TH01 (22,7 °C)" and sensors[-1]["label"].endswith("(fej)")
    heads = next(v for k, v in sec.schema.schema.items() if str(k) == "Szelepfejek").config["options"]
    assert heads[0]["label"] == "Konyha TRV"  # an on / off state is not shown
    as_leading = rf.room_section(hass, "hu", {**room, "new": False}, cands, "konyha", 1, 3)
    lead_keys = [str(k) for k in as_leading.schema.schema]
    assert "Cél" not in lead_keys and "Jelenlét" not in lead_keys and as_leading.options["collapsed"] is True


def test_a_section_reads_back_and_another_area_device_is_sorted_in():
    hass = _hass()
    room = rf.pick_rooms(["konyha"], [], AREAS, "")[0]
    w = rf.WORDS["hu"]
    out = rf.read_section(hass, "hu", room, {
        w["name"]: " Konyha ", w["sensors"]: ["sensor.k1"], w["trvs"]: ["climate.konyha_trv"], w["presence"]: [],
        w["windows"]: [], w["more"]: ["binary_sensor.kamra", "sensor.other_t", "binary_sensor.motion"],
        w["mode"]: "own", w["offset"]: 0.5, w["absent_min"]: 20, w["setback"]: 1.5, w["demand"]: True,
        "Kalibrálás – Konyha TRV": "head", w["position"]: 2})
    assert out["name"] == "Konyha" and out["sensors"] == ["sensor.k1", "sensor.other_t"]
    assert out["windows"] == ["binary_sensor.kamra"] and out["presence"] == ["binary_sensor.motion"]
    assert out["mode"] == "own" and out["demand"] is True and out["head_sensors"] == {"climate.konyha_trv": "head"}
    assert rm.parse_room(out).windows == ["binary_sensor.kamra"]


def test_problems_are_said_with_the_rooms_name():
    rooms = [{"key": "a", "name": "A", "sensors": ["sensor.x"]}, {"key": "b", "name": "B", "sensors": ["sensor.x"]}]
    name = lambda e: e.upper()
    assert rf.check_rooms("hu", rooms, None, False, set(), {}, name) == \
        "B: a(z) SENSOR.X hőmérő egy másik helyiségben is be van jelölve."
    rooms = [{"key": "a", "name": "A", "sensors": ["sensor.x"], "trvs": ["climate.t"]}, {"key": "b", "name": "B"}]
    assert rf.check_rooms("en", rooms, None, False, set(), {}, name) == "B: a room needs a thermometer or a TRV head."
    assert "leading room (A)" in rf.check_rooms("en", rooms[:1], "a", False, set(), {}, name)
    assert rf.check_rooms("en", rooms[:1], "a", True, set(), {}, name) is None
    assert "another HC instance" in rf.check_rooms("en", rooms[:1], None, False, set(), {"climate.t": "X"}, name)


def test_order_and_summary_with_roles():
    rooms = rf.order_rooms([{"key": "a", "name": "A", "_position": 2}, {"key": "b", "name": "B", "_position": 1,
                                                                         "trvs": ["climate.t"]},
                            {"key": "c", "name": "C", "_position": 3}])
    assert [r["key"] for r in rooms] == ["b", "a", "c"] and "_position" not in rooms[0]
    text = rf.summary("hu", rooms, "a")
    assert "1. B: szelepfejes" in text and "2. A: vezető" in text and "3. C: megfigyelt" in text


# --- the options flow end to end (Home Assistant stubbed) -----------------------------------------------------------
def _flow(monkeypatch, options):
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data={"role": "standalone", "control": "pid", "indoor_entity": "sensor.n1"}, options=options,
                            title="Boiler HC", entry_id="e1")
    type(flow).config_entry = property(lambda self: entry)
    flow.hass = _hass()
    flow.async_show_menu = lambda **kw: ("menu", kw)
    flow.async_show_form = lambda **kw: ("form", kw)
    flow.async_create_entry = lambda **kw: ("create", kw)
    monkeypatch.setattr(cf, "rooms_candidates", lambda hass: AREAS)
    monkeypatch.setattr(cf, "areas_of_other_instances", lambda hass, entry_id=None: {"szerver": "Iroda HC"})
    monkeypatch.setattr(cf, "excluded_climates", lambda hass, entry_id=None: [])
    monkeypatch.setattr(cf, "heads_of_other_instances", lambda hass, entry_id=None: {})
    monkeypatch.setattr(cf, "room_specs_for", lambda hass, conf: (rm.parse_rooms(conf.get("rooms") or []),
                                                                   conf.get("leading_room")))
    monkeypatch.setattr(flow, "_hc_climates", lambda ids: [])
    monkeypatch.setattr(cf, "area_id_of", lambda hass, e: {"sensor.n1": "halo"}.get(e))
    return flow


def test_options_rooms_step_by_step(monkeypatch):
    flow = _flow(monkeypatch, {"mode": "shadow", "target_home": 21.5, "window_entities": ["binary_sensor.x"]})
    kind, kw = asyncio.run(flow.async_step_rooms())
    assert kind == "form" and kw["step_id"] == "rooms"
    kind, kw = asyncio.run(flow.async_step_rooms({"areas": ["szerver"]}))
    assert kw["errors"] == {"base": "room_problem"} and "Iroda HC" in kw["description_placeholders"]["problem"]
    kind, kw = asyncio.run(flow.async_step_rooms({"home_name": "Próba ház", "areas": ["halo", "konyha"]}))
    assert kw["step_id"] == "room_details"
    sections = [str(k) for k in kw["data_schema"].schema]
    assert next(k for k in kw["data_schema"].schema if str(k) == "leading_room").default() == "halo"  # the house thermometer's area
    assert sections[:3] == ["leading_room", "confirm", "room_tolerance"] and sections[3:] == ["Háló", "Konyha"]
    w = rf.WORDS["hu"]
    answer = {"leading_room": "halo", "confirm": False, "room_tolerance": 0.7,
              "Háló": {w["name"]: "Háló", w["sensors"]: ["sensor.h1"], w["position"]: 1},
              "Konyha": {w["name"]: "Konyha", w["sensors"]: ["sensor.k1", "sensor.k2"], w["trvs"]: ["climate.konyha_trv"],
                         w["presence"]: [], w["windows"]: ["binary_sensor.konyha_ajto"], w["mode"]: "own",
                         w["offset"]: 0, w["absent_min"]: 15, w["setback"]: 2, w["demand"]: False,
                         "Kalibrálás – Konyha TRV": "room", w["position"]: 2}}
    kind, kw = asyncio.run(flow.async_step_room_details(answer))
    assert kind == "form" and kw["step_id"] == "room_own" and [str(k) for k in kw["data_schema"].schema] == ["Konyha"]
    kind, kw = asyncio.run(flow.async_step_room_own({"Konyha": {w["target_home"]: 22.0, w["target_night"]: 19.5,
                                                                w["target_away"]: 17.0, w["night_start"]: "22:30:00",
                                                                w["night_end"]: "06:00:00"}}))
    assert kind == "create"
    data = kw["data"]
    assert data["target_home"] == 21.5 and data["window_entities"] == ["binary_sensor.x"]  # the rest stays
    assert data["home_name"] == "Próba ház" and data["room_tolerance"] == 0.7 and data["leading_room"] == "halo"
    konyha = next(r for r in data["rooms"] if r["key"] == "konyha")
    assert konyha["windows"] == ["binary_sensor.konyha_ajto"] and konyha["target_home"] == 22.0
    assert konyha["night_start"] == "22:30" and "new" not in konyha
    assert data["room_trvs"] == ["climate.konyha_trv"]  # the legacy keys next to them


def test_options_settings_keep_the_rooms(monkeypatch):
    flow = _flow(monkeypatch, {"rooms": ROOMS, "leading_room": "nappali", "home_name": "Ház", "room_tolerance": 0.6,
                               "target_home": 21.0})
    flow._settings = {"target_home": 22.0, "mode": "shadow"}
    kind, kw = asyncio.run(flow.async_step_presets({"presets_enabled": ["home"]}))
    assert kind == "create" and kw["data"]["rooms"] == ROOMS and kw["data"]["home_name"] == "Ház"
    assert kw["data"]["target_home"] == 22.0 and kw["data"]["room_tolerance"] == 0.6


def test_a_problem_shows_the_form_again_with_the_text(monkeypatch):
    flow = _flow(monkeypatch, {})
    asyncio.run(flow.async_step_rooms({"areas": ["halo", "konyha"]}))
    w = rf.WORDS["hu"]
    kind, kw = asyncio.run(flow.async_step_room_details({"leading_room": "-", "Háló": {w["name"]: "Háló", w["sensors"]: ["sensor.k1"]},
                                                         "Konyha": {w["name"]: "Konyha", w["sensors"]: ["sensor.k1"]}}))
    assert kind == "form" and kw["errors"] == {"base": "room_problem"}
    assert "hőmérő egy másik helyiségben" in kw["description_placeholders"]["problem"]


# --- texts, wizard, house drawing ----------------------------------------------------------------------------------
def test_texts_and_wizard_and_house_title():
    for lang in ("hu", "en"):
        tr = json.loads((PKG / "translations" / f"{lang}.json").read_text())
        st = tr["options"]["step"]
        assert {"rooms", "room_details", "room_own"} <= set(st) and "room" not in st
        assert tr["options"]["error"]["room_problem"] == "{problem}"
        assert st["init"]["menu_options"]["rooms"]
    js = (PKG / "www" / "hc-wizard-panel.js").read_text()
    assert "data-rm-area" in js and "data-rm-multi" in js and 'home_name: s.home_name || ""' in js
    assert "s.roomList = []; s.leading = null;" in js  # a new instance: nothing ticked by itself
    assert "s.home_name = (e && e.home_name)" in js and "\"home_name\": conf.get(CONF_HOME_NAME)" in (PKG / "wizard.py").read_text()
    assert "conf.home_name || info.title" in (PKG / "www" / "hc-house-view.js").read_text()
    assert "role_watch" in (PKG / "www" / "hc-info-panel.js").read_text()
    assert json.loads((PKG / "manifest.json").read_text())["version"] in ("0.46.0", "0.47.0", "0.48.0", "0.48.1", "0.48.2")

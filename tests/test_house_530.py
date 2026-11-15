"""0.53.0: one house, several heat sources (which instances the HC info panel draws as one house), and the rooms of the
house a heat source does not heat (measured only)."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT.parent))

house = importlib.import_module("hc_thermostat.core.house")
rm = importlib.import_module("hc_thermostat.core.room_model")
rf = importlib.import_module("hc_thermostat.room_form")
cf = importlib.import_module("hc_thermostat.config_flow")
info = importlib.import_module("hc_thermostat.info")
rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
F = house.Facts


# --- which instances are one house -----------------------------------------------------------------------------------
def _home():
    """A typical home: a boiler with three rooms and a terrace zone, an AC on the terrace, an oil radiator in the
    bedroom, a shadow trial led from the living room, and two simulations without areas."""
    return [
        F("boiler", "Kazán", rooms=(("nappali", "nappali"), ("konyha", "konyha"), ("haloszoba", "haloszoba")),
          leading_area="nappali", zone_area="terasz"),
        F("ac", "Klíma", rooms=(("terasz", "terasz"),), leading_area="terasz"),
        F("oil", "Olajradiátor", rooms=(("haloszoba", "haloszoba"),), leading_area="haloszoba"),
        F("trial", "HC Thermostat", rooms=(("nappali", "nappali"),), leading_area="nappali"),
        F("sim", "OT szimuláció", leading_area=None),
        F("sim2", "Padlós ház szimuláció", leading_area="courtyard"),
    ]


def test_the_ac_and_the_oil_radiator_join_the_boiler_house_by_area():
    links = house.houses(_home())
    assert links["ac"].host == "boiler" and links["ac"].why == "area"
    assert links["ac"].area == "terasz" and links["ac"].room is None  # the zone: not one of the host's listed rooms
    assert links["oil"].host == "boiler" and links["oil"].room == "haloszoba"
    assert links["boiler"].host == "boiler" and links["boiler"].members == ["ac", "oil"]


def test_an_instance_led_from_the_host_leading_room_is_an_alternative_not_a_part():
    links = house.houses(_home())
    assert links["trial"].host == "trial" and links["trial"].why == "own"
    assert links["sim"].host == "sim" and links["sim2"].host == "sim2"


def test_own_and_a_named_house_win_over_the_area():
    facts = _home()
    facts[1] = F("ac", "Klíma", rooms=(("terasz", "terasz"),), leading_area="terasz", link="own")
    facts[4] = F("sim", "OT szimuláció", link="boiler")
    links = house.houses(facts)
    assert links["ac"].host == "ac"
    assert links["sim"].host == "boiler" and links["sim"].why == "named"
    assert links["boiler"].members == ["oil", "sim"]


def test_the_same_home_name_is_one_house_hosted_by_the_most_rooms():
    facts = [F("down", "Földszint", home_name="Kertház", rooms=(("a", "a"), ("b", "b"))),
             F("up", "Emelet", home_name=" kertház ", rooms=(("c", "c"), ("d", "d"), ("e", "e"))),
             F("pellet", "Pellet", home_name="Kertház"),
             F("other", "Másik", home_name="Fonyód", rooms=(("x", "x"), ("y", "y")))]
    links = house.houses(facts)
    assert links["up"].host == "up" and links["down"].host == "up" and links["pellet"].host == "up"
    assert links["down"].why == "home_name" and links["other"].host == "other"
    assert links["up"].members == ["down", "pellet"]


def test_a_chain_resolves_and_a_loop_is_cut():
    links = house.houses([F("a", link="b"), F("b", link="c"), F("c", rooms=(("r", "r"), ("s", "s")))])
    assert links["a"].host == "c" and links["b"].host == "c" and links["c"].members == ["a", "b"]
    links = house.houses([F("a", link="b"), F("b", link="a")])
    assert links["a"].host == "a" and links["b"].host == "b"


def test_a_central_boiler_or_buffer_joins_the_house_of_most_of_its_zones():
    facts = [F("host", rooms=(("a", "a"), ("b", "b"))), F("z1", rooms=(("a", "a"),), leading_area="a", role="zone"),
             F("z2", link="host", role="zone"), F("central", role="central", zone_entries=("z1", "z2", "missing"))]
    links = house.houses(facts)
    assert links["z1"].host == "host" and links["central"].host == "host" and links["central"].why == "zones"


def test_a_one_room_host_never_takes_members():
    links = house.houses([F("ac1", rooms=(("t", "t"),), leading_area="t"), F("ac2", rooms=(("t", "t"),), leading_area="t")])
    assert links["ac1"].host == "ac1" and links["ac2"].host == "ac2"


# --- measured-only rooms ---------------------------------------------------------------------------------------------
def test_a_measured_only_room_drops_its_heads_and_is_saved_as_such():
    spec = rm.parse_room({"name": "Előszoba", "sensors": ["sensor.e"], "trvs": ["climate.t"], "demand": True,
                          "heated": False})
    assert spec.heated is False and spec.trvs == [] and spec.demand is False
    assert spec.as_dict()["heated"] is False
    assert "heated" not in rm.parse_room({"name": "Konyha", "sensors": ["sensor.k"]}).as_dict()
    assert rm.parse_room({"name": "Konyha", "heated": None}).heated is True  # only an explicit False


def test_the_leading_room_is_always_heated():
    opts = rm.rooms_options([{"key": "n", "name": "Nappali", "sensors": ["sensor.n"], "heated": False},
                             {"key": "e", "name": "Előszoba", "sensors": ["sensor.e"], "heated": False}], "n", "sensor.n")
    by = {r["key"]: r for r in opts["rooms"]}
    assert "heated" not in by["n"] and by["e"]["heated"] is False
    specs, leading = rooms_ha.room_specs_for(None, {"rooms": [{"key": "n", "name": "N", "sensors": ["sensor.n"], "heated": False},
                                                             {"key": "e", "name": "E", "sensors": ["sensor.e"], "heated": False}],
                                                   "leading_room": "n"})
    assert leading == "n" and [s.heated for s in specs] == [True, False]


def test_the_room_form_offers_measured_only_and_checks_it():
    w = rf.WORDS["hu"]
    room = {"key": "e", "name": "Előszoba", "sensors": ["sensor.e"], "trvs": [], "heated": False}
    out = rf.read_section(None, "hu", {**room, "heated": True}, {w["name"]: "Előszoba", w["unheated"]: True})
    assert out["heated"] is False
    back = rf.read_section(None, "hu", room, {w["name"]: "Előszoba", w["unheated"]: False})
    assert "heated" not in back
    assert not rf.shows_trv_fields(room, "n", {"trvs": ["climate.x"]})
    bad = [{"key": "n", "name": "Nappali", "sensors": ["sensor.n"]}, {**room, "trvs": ["climate.t"]}]
    assert "szelepfej" in rf.check_rooms("hu", bad, "n", False, set(), {}, str)
    assert rf.check_rooms("hu", [bad[0], room], "n", False, set(), {}, str) is None
    assert "csak mérés" in rf.summary("hu", [bad[0], room], "n")


def test_the_room_list_and_the_picker_know_measured_only_rooms(monkeypatch):
    specs = [rm.RoomSpec(key="n", name="Nappali", sensors=["sensor.n"]), rm.RoomSpec(key="e", name="Előszoba", heated=False),
             rm.RoomSpec(key="k", name="Konyha", sensors=["sensor.k"])]
    rt = SimpleNamespace(room_specs=lambda: (specs, "n"), other_rooms=lambda: specs[1:], room_states={}, measures={})
    entry = SimpleNamespace(entry_id="e1", runtime_data=rt)
    monkeypatch.setattr(info, "_room_entities", lambda hass, entry: {"k": "climate.konyha_hc"})
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: None))
    listed = {r["key"]: r for r in info._room_list(hass, entry)}
    assert listed["e"]["heated"] is False and listed["k"]["heated"] is True
    assert [r["key"] for r in info._rooms_brief(hass, entry)] == ["k"]


# --- the info data ---------------------------------------------------------------------------------------------------
def test_house_facts_and_the_house_keys_of_the_info(monkeypatch):
    areas = {"sensor.n": "nappali", "sensor.t": "terasz", "sensor.zone": "terasz"}
    monkeypatch.setattr(rooms_ha, "area_id_of", lambda hass, e: areas.get(e))
    boiler = SimpleNamespace(entry_id="b", title="Kazán", data={"role": "standalone"},
                             options={"zone_temp_entity": "sensor.zone"},
                             runtime_data=SimpleNamespace(room_specs=lambda: ([rm.RoomSpec(key="n", name="N", area="nappali"),
                                                                                rm.RoomSpec(key="k", name="K", area="konyha")], "n")))
    ac = SimpleNamespace(entry_id="a", title="Klíma", data={"role": "standalone", "indoor_entity": "sensor.t"}, options={},
                         runtime_data=SimpleNamespace())
    f = info.house_facts(None, boiler)
    assert f.rooms == (("n", "nappali"), ("k", "konyha")) and f.leading_area == "nappali" and f.zone_area == "terasz"
    assert info.house_facts(None, ac).leading_area == "terasz"
    monkeypatch.setattr(info, "_loaded", lambda hass: [boiler, ac])
    links = info.house_links(None)
    assert info._house_brief(links, "a") == {"house": "b", "house_area": "terasz", "house_room": None, "house_why": "area",
                                             "house_members": []}
    assert info._house_brief(links, "b") == {"house": None, "house_members": ["a"]}
    assert info._house_brief({}, "x") == {"house": None, "house_members": []}


def test_house_links_never_raise(monkeypatch):
    monkeypatch.setattr(info, "_loaded", lambda hass: 1 / 0)
    assert info.house_links(None) == {}


# --- the setting ---------------------------------------------------------------------------------------------------
def _flow(options, others):
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data={"role": "standalone", "control": "tpi", "heat_source": "air_conditioner",
                                  "system": "room_unit", "indoor_entity": "sensor.t"},
                            options=options, title="Klíma", entry_id="me")
    type(flow).config_entry = property(lambda self: entry)
    flow.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: None),
                                config_entries=SimpleNamespace(async_entries=lambda domain: [entry, *others]),
                                config=SimpleNamespace(language="hu"))
    return flow


def test_the_house_setting_lists_the_other_instances_and_forgets_a_deleted_one():
    others = [SimpleNamespace(entry_id="b", title="Kazán")]
    flow = _flow({}, others)
    sel = cf._house_select(flow, {})
    values = [o["value"] for o in sel.config["options"]]
    assert values == ["auto", "own", "b"]
    assert any("Kazán" in o["label"] for o in sel.config["options"])
    assert cf._house_value(flow, {"house_link": "b"}) == "b"
    assert cf._house_value(flow, {"house_link": "gone"}) == "auto"
    assert cf._house_value(flow, {}) == "auto"
    assert "house_link" in cf.SETTINGS_SECTIONS["adjoining"]


def test_translations_and_the_panels_carry_the_house():
    for lang in ("hu", "en"):
        d = json.loads((ROOT / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        sec = d["options"]["step"]["settings"]["sections"]["adjoining"]
        assert sec["data"]["house_link"] and sec["data_description"]["house_link"]
    view = (ROOT / "www" / "hc-house-view.js").read_text(encoding="utf-8")
    assert "x.members" in view and "member:" in view and "it.heated === false" in view and "plant" in view
    panel = (ROOT / "www" / "hc-info-panel.js").read_text(encoding="utf-8")
    assert "house_members" in panel and "memberpick" in panel and "_houseSources" in panel
    wizard = (ROOT / "www" / "hc-wizard-panel.js").read_text(encoding="utf-8")
    assert "data-rm-unheated" in wizard

"""0.52.0: chosen presence / heat pump values, the season limits and the lowest believable room temperature on the
settings, and the natural gas's heating value as a field."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT.parent))

cf = importlib.import_module("hc_thermostat.config_flow")
fl = importlib.import_module("hc_thermostat.core.fuel")
st = importlib.import_module("hc_thermostat.core.states")
Presence = importlib.import_module("hc_thermostat.core.model").Presence


# --- 1. presence ---------------------------------------------------------------------------------------------------
def test_the_built_in_words_still_work():
    assert st.presence([("input_select.h", "Otthon")])[0] == Presence.HOME
    assert st.presence([("input_select.h", "Szabadság")])[0] == Presence.VACATION
    assert st.presence([("person.a", "not_home"), ("person.b", "home")])[0] == Presence.HOME
    assert st.presence([("person.a", "Munkahely")]) == (Presence.AWAY, [])  # a zone: away, never warned
    assert st.presence([])[0] == Presence.HOME and st.presence([("person.a", "unavailable")])[0] == Presence.HOME


def test_an_unknown_word_is_away_and_reported_until_values_are_chosen():
    result, unknown = st.presence([("input_select.h", "Itthon")])
    assert result == Presence.AWAY and unknown == [("input_select.h", "Itthon")]  # before 0.52.0: silently away
    assert st.presence([("input_select.h", "Távol")]) == (Presence.AWAY, [])  # a known away word: no warning
    assert st.presence([("input_select.h", "Itthon")], home=["Itthon"], vacation=["Nyaralás"]) == (Presence.HOME, [])
    assert st.presence([("sensor.h", "nyaralás ")], home="Itthon", vacation="Nyaralás, Üdülés")[0] == Presence.VACATION
    # values chosen: anything else is deliberately away, no warning
    assert st.presence([("input_select.h", "Vendég")], home=["Itthon"]) == (Presence.AWAY, [])


def test_the_coordinator_warns_once_per_value(caplog):
    co = importlib.import_module("hc_thermostat.coordinator")
    states = {"input_select.h": SimpleNamespace(state="Itthon")}
    c = SimpleNamespace(conf={"presence_entities": ["input_select.h"]}, hass=SimpleNamespace(
        states=SimpleNamespace(get=states.get)), config_entry=SimpleNamespace(title="Kazán"))
    with caplog.at_level("WARNING"):
        assert co.HcCoordinator._presence(c) == Presence.AWAY
        assert co.HcCoordinator._presence(c) == Presence.AWAY
    assert sum("Itthon" in r.getMessage() for r in caplog.records) == 1
    c.conf["presence_home_states"] = ["Itthon"]
    assert co.HcCoordinator._presence(c) == Presence.HOME


# --- 5. heat pump busy ----------------------------------------------------------------------------------------------
def test_heat_pump_busy_values():
    assert st.busy("Defrost") and st.busy("on") and not st.busy("heating")
    assert st.busy("Abtauen", ["abtauen", "Warmwasser"]) and st.busy("WARMWASSER", "Abtauen, Warmwasser")
    assert not st.busy(None, ["x"])


# --- 2. the lowest believable room temperature ------------------------------------------------------------------------
def test_the_believable_floor_follows_the_frost_target():
    assert st.indoor_floor(3.0, 7.0) == 3.0
    assert st.indoor_floor(3.0, 4.0) == 2.0  # a frost target of 4 °C: a real 3.5 °C room is believed
    assert st.indoor_floor(-5.0, 7.0) == -5.0


# --- 6. the gas's heating value -------------------------------------------------------------------------------------
def test_the_gas_heating_value_is_used_everywhere_gas_counts():
    assert fl.energy_factor("gas_m3", 90, None, None, None) == round(9.61 * 0.9, 3)  # default: as before
    assert fl.energy_factor("gas_m3", 90, None, None, None, 10.55) == round(10.55 * 0.9, 3)
    assert fl.energy_factor("auto", 90, "m³", "onoff_boiler", None, 10.55) == round(10.55 * 0.9, 3)
    assert fl.energy_factor("auto", 90, None, "modulating_boiler", None, 10.55) == round(10.55 * 0.9, 3)
    assert fl.energy_factor("custom", 90, "m³", "onoff_boiler", 8.65, 10.55) == 8.65  # a typed number stays
    assert fl.energy_factor("pellet_kg", 90, None, None, None, 10.55) == round(4.8 * 0.9, 3)
    assert fl.gas_value(None) == 9.61 and fl.gas_value(99) == 9.61 and fl.gas_value("10.2") == 10.2


# --- the settings form ---------------------------------------------------------------------------------------------
def _options_flow(options, data=None, states=None):
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data=data or {"role": "standalone", "control": "tpi", "heat_source": "onoff_boiler",
                                          "system": "radiator_single", "indoor_entity": "sensor.nappali"},
                            options=options, title="Kazán", entry_id="e1")
    type(flow).config_entry = property(lambda self: entry)
    flow.hass = SimpleNamespace(states=SimpleNamespace(get=(states or {}).get))
    flow.async_show_form = lambda **kw: ("form", kw)
    flow.async_create_entry = lambda **kw: ("create", kw)
    flow.async_step_presets = lambda: asyncio.sleep(0, result=("presets", flow._settings))
    return flow


def _section_keys(schema, name):
    marker = next(k for k in schema.schema if str(k) == name)
    return {str(k): k for k in schema.schema[marker].schema.schema}, schema.schema[marker].schema.schema


def test_the_presence_values_are_offered_from_the_source():
    states = {"input_select.h": SimpleNamespace(state="Itthon", attributes={"options": ["Itthon", "Távol", "Nyaralás"]})}
    flow = _options_flow({"mode": "shadow"}, {"role": "standalone", "control": "tpi", "heat_source": "onoff_boiler",
                                             "system": "radiator_single", "indoor_entity": "sensor.n",
                                             "presence_entities": ["input_select.h", "person.a"]}, states)
    schema = asyncio.run(flow.async_step_settings())[1]["data_schema"]
    keys, inner = _section_keys(schema, "functions")
    assert {"presence_home_states", "presence_vacation_states", "season_off_above", "season_on_below"} <= set(keys)
    picker = inner[keys["presence_home_states"]]
    assert picker.config["options"] == ["Itthon", "Távol", "Nyaralás"] and picker.config["multiple"]
    assert picker.config["custom_value"]
    # only persons: nothing to choose
    flow = _options_flow({"mode": "shadow"}, {"role": "standalone", "control": "tpi", "heat_source": "onoff_boiler",
                                             "system": "radiator_single", "indoor_entity": "sensor.n",
                                             "presence_entities": ["person.a"]})
    keys, _ = _section_keys(asyncio.run(flow.async_step_settings())[1]["data_schema"], "functions")
    assert "presence_home_states" not in keys


def test_the_heat_pump_values_are_offered_for_a_mode_sensor():
    states = {"sensor.hp_mode": SimpleNamespace(state="Heizen", attributes={"options": ["Heizen", "Abtauen", "Warmwasser"]})}
    flow = _options_flow({"mode": "shadow", "hp_defrost_entity": "sensor.hp_mode"},
                         {"role": "standalone", "control": "onoff", "heat_source": "heat_pump",
                          "system": "radiator_single", "indoor_entity": "sensor.n"}, states)
    keys, inner = _section_keys(asyncio.run(flow.async_step_settings())[1]["data_schema"], "devices")
    assert inner[keys["hp_busy_states"]].config["options"] == ["Heizen", "Abtauen", "Warmwasser"]


def test_the_season_and_believable_limits_are_checked_and_saved():
    flow = _options_flow({"mode": "shadow"})
    keys, inner = _section_keys(asyncio.run(flow.async_step_settings())[1]["data_schema"], "protection")
    assert keys["plaus_indoor_min"].default() == 3.0
    base = {"mode": "shadow", "frost_temp": 7.0}
    kind, kw = asyncio.run(flow.async_step_settings({**base, "functions": {"season_off_above": 14.0,
                                                                           "season_on_below": 14.0}}))
    assert kind == "form" and kw["errors"] == {"base": "season_order"}
    kind, kw = asyncio.run(flow.async_step_settings({**base, "protection": {"plaus_indoor_min": 6.0}}))
    assert kind == "form" and kw["errors"] == {"base": "plaus_frost"}
    kind, saved = asyncio.run(flow.async_step_settings({**base, "functions": {
        "season_off_above": 17.0, "season_on_below": 12.0, "presence_home_states": ["Itthon"]},
        "protection": {"plaus_indoor_min": 0.0}}))
    assert kind == "presets" and saved["season_off_above"] == 17.0 and saved["plaus_indoor_min"] == 0.0
    assert saved["presence_home_states"] == ["Itthon"]


def test_the_gas_value_is_a_field_and_works_the_factor_out():
    flow = _options_flow({"mode": "shadow", "heat_fuel": "gas_m3"})
    keys, _ = _section_keys(asyncio.run(flow.async_step_settings())[1]["data_schema"], "energy")
    assert keys["gas_heating_value"].default() == 9.61
    kind, saved = asyncio.run(flow.async_step_settings({"mode": "shadow", "energy": {
        "heat_fuel": "gas_m3", "heat_efficiency": 90.0, "gas_heating_value": 10.55, "energy_factor": 1.0}}))
    assert saved["energy_factor"] == round(10.55 * 0.9, 3)


def test_texts_and_version():
    for lang in ("hu", "en"):
        t = json.loads((ROOT / "translations" / f"{lang}.json").read_text())
        assert t["options"]["error"]["season_order"] and t["options"]["error"]["plaus_frost"]
        assert t["config"]["step"]["entities"]["sections"]["more"]["data"]["gas_heating_value"]
        rating = t["options"]["step"]["settings"]["sections"]["house"]["data_description"]["house_area_m2"]
        assert ("Magyar skála" if lang == "hu" else "Hungarian scale") in rating
    assert json.loads((ROOT / "manifest.json").read_text())["version"] in ("0.52.0", "0.52.1", "0.53.0", "0.54.0", "0.55.0", "0.56.0", "0.56.1", "0.57.0", "0.57.1")

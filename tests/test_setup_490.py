"""0.49.0: a simpler setup – fold-out sections (entities step, settings), another control without a new instance,
pre-filled pickers in the manual setup, and the energy factor worked out of a fuel."""

import asyncio
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import voluptuous as vol

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT.parent))

cf = importlib.import_module("hc_thermostat.config_flow")
fl = importlib.import_module("hc_thermostat.core.fuel")
rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")


def _tr(lang):
    return json.loads((ROOT / "translations" / f"{lang}.json").read_text())


def _keys(schema) -> list[str]:
    return [str(k) for k in schema.schema]


def _section(schema, name):
    marker = next(k for k in schema.schema if str(k) == name)
    return schema.schema[marker]


# --- 5. the fuel -------------------------------------------------------------------------------------------------
def test_energy_factor_from_the_fuel():
    assert fl.energy_factor("auto", 90, "m³", "onoff_boiler", None) == round(9.61 * 0.9, 3)
    assert fl.energy_factor("auto", 90, "m3", "modulating_boiler", None) == round(9.61 * 0.9, 3)
    assert fl.energy_factor("auto", 90, "kWh", "electric_heater", None) == 1.0
    assert fl.energy_factor("auto", 90, "GJ", "district_heating", None) == round(1000 / 3.6, 4)  # no burner
    assert fl.energy_factor("auto", 90, "kWh", "onoff_boiler", None) == 0.9
    assert fl.energy_factor("auto", 95, None, "onoff_boiler", None) == round(9.61 * 0.95, 3)  # no meter: the source
    assert fl.energy_factor("auto", 90, None, "heat_pump", 3.5) == 3.5  # a heat pump: the typed number
    assert fl.energy_factor("auto", 90, None, "heat_pump", None) == fl.DEFAULT_FACTOR
    assert fl.energy_factor("custom", 90, "m³", "onoff_boiler", 7.7) == 7.7
    assert fl.energy_factor("lpg_kg", 90, None, None, None) == round(12.8 * 0.9, 3)
    assert fl.energy_factor("electric_kwh", 50, None, None, None) == 1.0  # no efficiency for electric heat
    # an instance saved before 0.49.0 keeps its number; a new one starts on automatic
    assert fl.default_fuel({"energy_factor": 8.55}) == "custom"
    assert fl.default_fuel({}) == "auto"
    assert fl.default_fuel({"heat_fuel": "oil_l", "energy_factor": 9.0}) == "oil_l"


# --- 1. the entities step: the few fields on top, the rest folds out ---------------------------------------------
def _flow(data):
    flow = cf.HcConfigFlow()
    flow._data = dict(data)
    flow.hass = None
    flow.async_show_form = lambda **kw: ("form", kw)
    flow.async_create_entry = lambda **kw: ("create", kw)
    return flow


BOILER = {"name": "Kazán", "role": "standalone", "heat_source": "onoff_boiler", "system": "radiator_single",
          "control": "tpi"}


def test_the_entities_step_folds_out_what_a_first_setup_does_not_need(monkeypatch):
    monkeypatch.setattr(cf, "excluded_climates", lambda hass, entry_id=None: [])
    flow = _flow(BOILER)
    kind, kw = asyncio.run(flow.async_step_entities())
    schema = kw["data_schema"]
    assert kind == "form" and _keys(schema) == ["indoor_entity", "demand_entity", "actuator_entity", "outdoor_entity",
                                                "window_entities", "presence_entities", "more"]
    more = _section(schema, "more")
    inner = _keys(more.schema)
    assert {"heat_energy_entity", "heat_fuel", "heat_efficiency", "energy_factor", "reference_entity",
            "target_source_entity"} <= set(inner)
    assert more.options["collapsed"] is True
    # the answer comes nested; it is stored on one level, the energy factor worked out of the fuel
    flow.async_step_basics = lambda: asyncio.sleep(0, result=("basics", flow._data))
    kind, data = asyncio.run(flow.async_step_entities({
        "indoor_entity": "sensor.nappali", "actuator_entity": "switch.kazan",
        "more": {"heat_fuel": "auto", "heat_efficiency": 90.0, "energy_factor": 8.55}}))
    assert kind == "basics" and "more" not in data
    assert data["heat_fuel"] == "auto" and data["energy_factor"] == round(9.61 * 0.9, 3) and data["mode"] == "shadow"


def test_a_field_still_to_fill_stays_on_top(monkeypatch):
    monkeypatch.setattr(cf, "excluded_climates", lambda hass, entry_id=None: [])
    flow = _flow({**BOILER, "heat_source": "electric_heater", "system": "floor_single"})  # an electric floor
    kind, kw = asyncio.run(flow.async_step_entities())
    assert "floor_entity" in _keys(kw["data_schema"])  # required here: never hidden in a closed section
    flow = _flow({**BOILER, "control": "external"})
    keys = _keys(asyncio.run(flow.async_step_entities())[1]["data_schema"])
    assert keys[:2] == ["indoor_entity", "external_climate"] and "actuator_entity" not in keys


def test_grouping_opens_a_section_with_a_required_field():
    fields = {vol.Required("a", default=1): int, vol.Optional("b"): int, vol.Required("c"): int, vol.Optional("d"): int}
    out = cf._grouped(fields, {"b": "x", "c": "y", "d": "x"}, ("y", "x"))
    assert _keys(vol.Schema(out)) == ["a", "y", "x"]
    assert out[next(k for k in out if str(k) == "y")].options["collapsed"] is False
    assert out[next(k for k in out if str(k) == "x")].options["collapsed"] is True
    assert cf._flat({"a": 1, "x": {"b": 2, "d": 3}, "y": {"c": 4}}, ("x", "y")) == {"a": 1, "b": 2, "d": 3, "c": 4}


# --- 4. pre-filled pickers --------------------------------------------------------------------------------------
def _state(entity_id, state="21.0", **attrs):
    return SimpleNamespace(entity_id=entity_id, domain=entity_id.split(".")[0], state=state, attributes=attrs)


class _States:
    def __init__(self, states):
        self._s = states

    def async_all(self, domain=None):
        return [s for s in self._s if domain is None or s.domain == domain]

    def get(self, entity_id):
        return next((s for s in self._s if s.entity_id == entity_id), None)


def _hass(states):
    return SimpleNamespace(states=_States(states))


def test_the_manual_setup_suggests_what_home_assistant_tells(monkeypatch):
    monkeypatch.setattr(rooms_ha, "area_id_of", lambda hass, e: None)
    hass = _hass([
        _state("sensor.kinti_homerseklet", "4.0", device_class="temperature", unit_of_measurement="°C"),
        _state("weather.otthon", "cloudy", temperature=4.0),
        _state("sensor.nappali_homerseklet", "21.4", device_class="temperature", unit_of_measurement="°C"),
        _state("sensor.halo_homerseklet", "20.1", device_class="temperature", unit_of_measurement="°C"),
        _state("sensor.huto_homerseklet", "4.0", device_class="temperature", unit_of_measurement="°C"),
        _state("person.a", "home"), _state("person.b", "not_home"),
        _state("sensor.gazora", "8788.5", device_class="gas", unit_of_measurement="m³"),
    ])
    sug = rooms_ha.suggest_entities(hass)
    assert sug == {"outdoor_entity": "sensor.kinti_homerseklet", "indoor_entity": "sensor.nappali_homerseklet",
                   "presence_entities": ["person.a", "person.b"], "heat_energy_entity": "sensor.gazora"}
    # two rooms, none of them the living room: no guess; no outdoor sensor: the weather entity
    hass = _hass([_state("sensor.a", "21", device_class="temperature", unit_of_measurement="°C"),
                  _state("sensor.b", "20", device_class="temperature", unit_of_measurement="°C"),
                  _state("weather.otthon", "sunny", temperature=3.0)])
    assert rooms_ha.suggest_entities(hass) == {"outdoor_entity": "weather.otthon"}


def test_the_entities_step_is_pre_filled(monkeypatch):
    monkeypatch.setattr(cf, "excluded_climates", lambda hass, entry_id=None: [])
    monkeypatch.setattr(cf, "suggest_entities", lambda hass: {
        "indoor_entity": "sensor.nappali", "outdoor_entity": "weather.otthon", "presence_entities": ["person.a"],
        "heat_energy_entity": "sensor.gazora"})
    flow = _flow(BOILER)
    flow.hass = object()
    schema = asyncio.run(flow.async_step_entities())[1]["data_schema"]
    sug = {str(k): (k.description or {}).get("suggested_value") for k in schema.schema}
    assert sug["indoor_entity"] == "sensor.nappali" and sug["outdoor_entity"] == "weather.otthon"
    assert sug["presence_entities"] == ["person.a"] and sug["actuator_entity"] is None  # never a guessed relay
    inner = {str(k): (k.description or {}).get("suggested_value") for k in _section(schema, "more").schema.schema}
    assert inner["heat_energy_entity"] == "sensor.gazora"
    flow = _flow({**BOILER, "heat_source": "electric_heater"})
    flow.hass = object()
    inner = {str(k): (k.description or {}).get("suggested_value")
             for k in _section(asyncio.run(flow.async_step_entities())[1]["data_schema"], "more").schema.schema}
    assert inner["heat_energy_entity"] is None  # a gas meter belongs to a gas boiler only


# --- 2. the settings: the targets on top, the rest by topic -----------------------------------------------------
def _options_flow(options, data=None):
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data=data or {"role": "standalone", "control": "tpi", "heat_source": "onoff_boiler",
                                          "system": "radiator_single", "indoor_entity": "sensor.nappali"},
                            options=options, title="Kazán", entry_id="e1")
    type(flow).config_entry = property(lambda self: entry)
    flow.async_show_menu = lambda **kw: ("menu", kw)
    flow.async_show_form = lambda **kw: ("form", kw)
    flow.async_create_entry = lambda **kw: ("create", kw)
    return flow


def test_the_settings_fold_out_by_topic_and_are_stored_flat():
    flow = _options_flow({"mode": "shadow", "energy_factor": 8.55})
    kind, kw = asyncio.run(flow.async_step_settings())
    schema = kw["data_schema"]
    keys = _keys(schema)
    assert keys[:2] == ["mode", "confirm"] and "target_home" in keys and "cycle_s" not in keys
    assert [k for k in keys if k in cf.SETTINGS_SECTIONS] == ["regulation", "functions", "protection", "devices",
                                                               "energy", "adjoining"]
    assert keys[-1] == "measures"
    energy = _section(schema, "energy")
    fuel = next(k for k in energy.schema.schema if str(k) == "heat_fuel")
    assert fuel.default() == "custom"  # saved before 0.49.0: the number stays
    # a nested answer: the timing error is shown above the form, a good one is stored on one level
    answer = {"mode": "shadow", "target_home": 21.0, "regulation": {"cycle_s": 900, "min_on_s": 300, "min_off_s": 300,
                                                                     "valve_delay_s": 600},
              "energy": {"heat_fuel": "gas_m3", "heat_efficiency": 95.0, "energy_factor": 8.55}}
    kind, kw = asyncio.run(flow.async_step_settings(answer))
    assert kind == "form" and kw["errors"] == {"base": "cycle_too_short"}
    answer["regulation"]["cycle_s"] = 1800
    flow.async_step_presets = lambda: asyncio.sleep(0, result=("presets", flow._settings))
    kind, saved = asyncio.run(flow.async_step_settings(answer))
    assert kind == "presets" and "regulation" not in saved and "energy" not in saved
    assert saved["cycle_s"] == 1800 and saved["energy_factor"] == round(9.61 * 0.95, 3)


def test_every_field_of_a_section_has_a_text():
    for lang in ("hu", "en"):
        st = _tr(lang)["options"]["step"]["settings"]
        for name, keys in cf.SETTINGS_SECTIONS.items():
            sec = st["sections"][name]
            assert sec["name"] and sec["description"]
            for k in keys:
                assert sec["data"].get(k), (lang, name, k)
        ent = _tr(lang)["config"]["step"]["entities"]
        assert ent["sections"]["more"]["data"]["heat_fuel"] and ent["data"]["indoor_entity"]
        assert set(_tr(lang)["selector"]["heat_fuel"]["options"]) == set(fl.FUELS)
        assert "szoba" not in json.dumps(_tr("hu")["options"]["step"], ensure_ascii=False)


# --- 3. another control without a new instance ------------------------------------------------------------------
def test_the_control_changes_to_an_external_thermostat_in_shadow_mode(monkeypatch):
    flow = _options_flow({"mode": "active", "actuator_entity": "switch.kazan", "demand_entity": "binary_sensor.fali"})
    flow._taken = lambda: ["climate.hc_kazan"]
    assert "change_control" in asyncio.run(flow.async_step_init())[1]["menu_options"]
    kind, kw = asyncio.run(flow.async_step_change_control())
    assert kind == "form" and next(k for k in kw["data_schema"].schema if str(k) == "control").default() == "tpi"
    kind, kw = asyncio.run(flow.async_step_change_control({"control": "external"}))
    assert kind == "form" and kw["step_id"] == "change_entities"
    keys = _keys(kw["data_schema"])
    assert keys == ["indoor_entity", "external_climate", "outdoor_entity"]
    indoor = next(k for k in kw["data_schema"].schema if str(k) == "indoor_entity")
    assert indoor.description["suggested_value"] == "sensor.nappali"
    kind, kw = asyncio.run(flow.async_step_change_entities({"indoor_entity": "sensor.nappali",
                                                            "external_climate": "climate.hc_kazan"}))
    assert kind == "form" and kw["errors"] == {"external_climate": "climate_taken"}
    kind, kw = asyncio.run(flow.async_step_change_entities({"indoor_entity": "sensor.nappali",
                                                            "external_climate": "climate.btt"}))
    assert kind == "create"
    data = kw["data"]
    assert data["control"] == "external" and data["mode"] == "shadow" and data["external_climate"] == "climate.btt"
    assert "demand_entity" not in data and data["actuator_entity"] == "switch.kazan"  # the rest stays


def test_rooms_keep_tpi_and_a_curve_gets_its_defaults():
    flow = _options_flow({"rooms": [{"key": "nappali"}]})
    kind, kw = asyncio.run(flow.async_step_change_control({"control": "external"}))
    assert kind == "form" and kw["errors"] == {"control": "rooms_need_valves"}
    flow = _options_flow({}, data={"role": "standalone", "control": "tpi", "heat_source": "modulating_boiler",
                                   "system": "radiator_single", "indoor_entity": "sensor.nappali"})
    flow._new_control = "curve"
    keys = _keys(asyncio.run(flow.async_step_change_entities())[1]["data_schema"])
    assert keys == ["indoor_entity", "flow_setpoint_entity", "heat_enable_entity", "outdoor_entity"]
    kind, kw = asyncio.run(flow.async_step_change_entities({"indoor_entity": "sensor.nappali",
                                                            "flow_setpoint_entity": "number.elore",
                                                            "outdoor_entity": "sensor.kint"}))
    assert kind == "create" and kw["data"]["control"] == "curve" and "curve_slope" in kw["data"]
    for lang in ("hu", "en"):
        st = _tr(lang)["options"]["step"]
        assert st["change_control"]["title"] and st["change_entities"]["data"]["external_climate"]
        assert _tr(lang)["options"]["error"]["rooms_need_valves"]


def test_version():
    assert json.loads((ROOT / "manifest.json").read_text())["version"] == "0.49.0"

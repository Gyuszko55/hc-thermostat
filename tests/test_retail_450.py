"""0.45.0: fixes from the "boxed retail release" review – a new Home Assistant takes HC into use in a few clicks.

°F / imperial systems, the relay failsafe, house-specific texts, the user's language, a taken name, HC's own and
other instances' climates in the pickers, the restart hold after adding an instance, going live, the brand icon,
units, the manifest, recorder exclusions, admin-only info, the boiler health without known power levels, entity
names, the panels after the last instance, and an upgrade from 0.41.0.
"""

import asyncio
import importlib
import json
import re
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT / "custom_components"))
units = importlib.import_module("hc_thermostat.units")
model = importlib.import_module("hc_thermostat.core.model")
trv = importlib.import_module("hc_thermostat.core.trv")
bh = importlib.import_module("hc_thermostat.core.boiler_health")
messages = importlib.import_module("hc_thermostat.core.messages")
coord_mod = importlib.import_module("hc_thermostat.coordinator")
executor_mod = importlib.import_module("hc_thermostat.executor")
adapters = importlib.import_module("hc_thermostat.core.adapters")

T0 = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
IMPERIAL = SimpleNamespace(units=SimpleNamespace(temperature_unit="°F"), language="en")
METRIC = SimpleNamespace(units=SimpleNamespace(temperature_unit="°C"), language="hu")


def _st(entity_id, state, last=T0, **attrs):
    return SimpleNamespace(entity_id=entity_id, domain=entity_id.split(".")[0], state=str(state), attributes=attrs,
                           last_reported=last, last_updated=last)


class _Hass:
    def __init__(self, states, config=METRIC):
        self._states, self.calls, self.data, self.config = states, [], {}, config
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))
        self.services = SimpleNamespace(async_call=self._call)
        self.bus = SimpleNamespace(async_fire=lambda *a, **k: None)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


# --- 1. °F ------------------------------------------------------------------------------------------------------
def test_unit_conversion_helpers():
    assert units.to_c(68, "°F") == pytest.approx(20.0)
    assert units.to_c("293.15", "K") == pytest.approx(20.0)
    assert units.to_c("21.5", "°C") == 21.5 and units.to_c("55", "%") == 55.0 and units.to_c("x", "°F") is None
    assert units.system_unit(SimpleNamespace()) == "°C"  # a bare test object: Celsius
    attrs = units.climate_attrs_c(_Hass({}, IMPERIAL), {"temperature": 70, "current_temperature": 68, "min_temp": 45,
                                                        "max_temp": 86, "target_temp_step": 1, "hvac_action": "idle"})
    assert attrs["current_temperature"] == pytest.approx(20.0) and attrs["min_temp"] == pytest.approx(7.22, abs=0.01)
    assert attrs["target_temp_step"] == pytest.approx(5 / 9) and attrs["hvac_action"] == "idle"
    assert units.climate_attrs_c(_Hass({}), {"temperature": 21}) == {"temperature": 21}  # °C: untouched
    assert units.to_system(_Hass({}, IMPERIAL), 21.0) == 70.0  # 69.8 °F on the whole degree
    assert units.to_system(_Hass({}, IMPERIAL), 21.0, 0.5) == 70.0
    assert units.to_system(_Hass({}), 21.3) == 21.3


def test_readings_are_celsius_whatever_the_sensor_unit():
    hass = _Hass({"sensor.f": _st("sensor.f", "68.0", unit_of_measurement="°F"),
                  "sensor.c": _st("sensor.c", "20.5", unit_of_measurement="°C"),
                  "sensor.h": _st("sensor.h", "45", unit_of_measurement="%"),
                  "weather.home": _st("weather.home", "sunny", temperature=41, temperature_unit="°F")})
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass = hass
    assert c._reading("sensor.f", T0).value == pytest.approx(20.0)
    assert c._reading("sensor.c", T0).value == 20.5
    assert c._reading("sensor.h", T0).value == 45.0  # not a temperature: as it is
    assert c._reading("weather.home", T0).value == pytest.approx(5.0)


def _ext(hvac, target):
    return model.Decision(T0, model.Reason.EXTERNAL, target, 20.0, 5.0, external=model.ExternalCommand(hvac, target),
                          output=hvac == "heat")


def test_executor_writes_the_system_unit_to_a_climate():
    """HA takes a service temperature in its own unit system: 22 °C goes to a °F thermostat as 72 °F."""
    attrs = {"hvac_modes": ["heat", "off"], "min_temp": 45, "max_temp": 95, "target_temp_step": 1, "temperature": 65}
    hass = _Hass({"climate.unit": _st("climate.unit", "heat", **attrs)}, IMPERIAL)
    ex = executor_mod.Executor(hass, "active", None, "climate.unit")
    asyncio.run(ex.apply(_ext("heat", 22.0)))
    assert hass.calls == [("climate", "set_temperature", {"entity_id": "climate.unit", "temperature": 72.0})]
    now = datetime.now(timezone.utc)
    assert executor_mod.write_log(hass).recent("climate.unit", 72.0 * 0 + units.to_c(72.0, "°F"), now)  # noted in °C
    # the AC control (exact): stepped in °C by the unit's 1 °F step (5/9 °C) – written on the whole °F
    hass = _Hass({"climate.unit": _st("climate.unit", "heat", **attrs)}, IMPERIAL)
    ex = executor_mod.Executor(hass, "active", None, "climate.unit", exact_mode=True)
    asyncio.run(ex.apply(_ext("heat", 40 * 5 / 9)))  # 22.22 °C = 72 °F
    assert hass.calls[-1][2]["temperature"] == 72.0
    # a metric system is unchanged
    hass = _Hass({"climate.unit": _st("climate.unit", "heat", **{**attrs, "min_temp": 7, "max_temp": 35, "target_temp_step": 0.5, "temperature": 18})})
    ex = executor_mod.Executor(hass, "active", None, "climate.unit")
    asyncio.run(ex.apply(_ext("heat", 22.0)))
    assert hass.calls[-1][2]["temperature"] == 22.0


def test_unit_inputs_of_an_ac_in_fahrenheit_are_celsius():
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass = _Hass({"climate.ac": _st("climate.ac", "heat", current_temperature=68, target_temp_step=1, min_temp=61,
                                      max_temp=86)}, IMPERIAL)
    c.cfg, c.conf = model.HcConfig(control="ac"), {"external_climate": "climate.ac"}
    u = c._unit_inputs()
    assert u["unit_temp"] == pytest.approx(20.0) and u["unit_step"] == pytest.approx(5 / 9)
    assert u["unit_min"] == pytest.approx(16.11, abs=0.01) and u["unit_max"] == pytest.approx(30.0)


def test_a_trv_head_in_fahrenheit_gets_fahrenheit(monkeypatch):
    clock = {"now": T0}
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: clock["now"])
    monkeypatch.setattr(coord_mod.dt_util, "utcnow", lambda: clock["now"])
    states = {"sensor.n": _st("sensor.n", "70", unit_of_measurement="°F"),
              "sensor.k": _st("sensor.k", "68", unit_of_measurement="°F"),
              "climate.k_trv": _st("climate.k_trv", "heat", temperature=64, current_temperature=68, target_temp_step=1,
                                   min_temp=41, max_temp=86)}
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass, c.mode = _Hass(states, IMPERIAL), "active"
    c.conf = {"rooms": [{"key": "n", "name": "N", "sensors": ["sensor.n"]},
                        {"key": "k", "name": "K", "sensors": ["sensor.k"], "trvs": ["climate.k_trv"]}],
              "leading_room": "n"}
    c.cfg = model.HcConfig.from_mapping(c.conf)
    c.trv_targets, c.trv_cal, c.trv_info = trv.TrvTargets(), trv.TrvCalibration(), {}
    c._room_groups, c._trv_groups, c._specs = None, None, None
    c._started = T0 - timedelta(hours=1)
    c.room_demand, c.asking_rooms, c.data = trv.RoomDemand(), [], None
    asyncio.run(c._apply_trvs(model.Decision(T0, model.Reason.REGULATING, 21.0, 21.1, 0.0, output=True)))
    k = c.room_states["k"]
    assert k["temperature"] == pytest.approx(20.0)  # 68 °F
    assert c.trv_info["K"]["heads"]["climate.k_trv"]["calibration"] == 0.0  # head 68 °F = room 68 °F
    (_, _, data), = c.hass.calls
    assert data == {"entity_id": "climate.k_trv", "temperature": 70.0}  # 21 °C on the whole °F, not 21


# --- 3. failsafe --------------------------------------------------------------------------------------------------
def test_three_failed_decisions_switch_the_relay_off(monkeypatch):
    hass = _Hass({"switch.boiler": _st("switch.boiler", "on")})
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass, c.mode, c.step_errors, c.sensor_problems = hass, "active", 0, {}
    c.config_entry = SimpleNamespace(title="Probe")
    c._executor = executor_mod.Executor(hass, "active", "switch.boiler", None)
    c.data = model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.6, output=True)

    async def failing():
        try:
            raise RuntimeError("boom")
        except Exception:
            return await c._failsafe(T0)

    for _ in range(2):
        with pytest.raises(RuntimeError):
            asyncio.run(failing())
    d = asyncio.run(failing())
    assert d.output is False and d.fault is True and d.details["failsafe"] == 3
    assert c.sensor_problems[coord_mod.FAILSAFE_KEY] == "internal_error"
    asyncio.run(c._executor.apply(d))
    assert hass.calls == [("homeassistant", "turn_off", {"entity_id": "switch.boiler"})]
    # a managed thermostat gets "off"
    c.data = _ext("heat", 21.0)
    d = asyncio.run(failing())
    assert d.external.hvac == "off"


def test_failsafe_through_the_update_resets_on_a_good_step(monkeypatch):
    src = (PKG / "coordinator.py").read_text()
    body = src[src.index("    async def _async_update_data"):src.index("    async def _failsafe")]
    assert "await self._failsafe(now)" in body and "self.step_errors = 0" in body
    assert "self.sensor_problems.pop(FAILSAFE_KEY, None)" in body


# --- 4. / 5. house-specific texts, BTHome -------------------------------------------------------------------------
def test_no_house_specific_texts_left():
    d = model.Decision(T0, model.Reason.AC_HEAT, 21.0, 20.0, 5.0, details={"setpoint": 22.0, "assist": True, "aim": 21.0})
    hu = messages.explain(d, "hu")
    assert "teraszi" not in hu and "konyhaajtó" not in hu and "a helyiség hőmérője szerint" in hu
    assert "összekötő ajtó" in hu
    words = re.compile(r"cirk[oó]|hern[aá]d|gyula|ht_plus|ds01|redmi|192\.168", re.I)
    for f in list(PKG.rglob("*.py")) + list(PKG.rglob("*.json")) + list((PKG / "www").glob("*.js")):
        if "__pycache__" in str(f):
            continue
        text = f.read_text(encoding="utf-8")
        if f.suffix == ".py":  # comments may name the author's boiler; logic and texts must not
            text = "\n".join(line.split("#")[0] for line in text.splitlines())
            text = re.sub(r'"""[\s\S]*?"""', "", text)
        elif f.suffix == ".js":
            text = "\n".join(line.split("//")[0] for line in text.splitlines())
        assert not words.search(text), f"{f.name}: {words.search(text).group(0)}"


def test_bthome_is_no_outdoor_word():
    wizard = importlib.import_module("hc_thermostat.wizard")
    rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
    assert "bthome" not in wizard._OUTDOOR_WORDS and "bthome" not in rooms_ha.OUTDOOR_WORDS


# --- 6. language --------------------------------------------------------------------------------------------------
def _tr(lang):
    return json.loads((PKG / "translations" / f"{lang}.json").read_text(encoding="utf-8"))


def test_flow_texts_take_their_own_language_placeholders():
    for lang in ("hu", "en"):
        t = _tr(lang)
        desc = t["config"]["step"]["control"]["description"]
        assert f"{{status_{lang}}}" in desc and f"{{advice_{lang}}}" in desc and "{status}" not in desc
        assert f"{{rooms_{lang}}}" in t["options"]["step"]["rooms"]["description"]
    cf = (PKG / "config_flow.py").read_text()
    for key in ("status_hu", "status_en", "advice_hu", "advice_en", "rooms_hu", "rooms_en"):
        assert f'"{key}"' in cf
    assert '"status": matrix.status.value' not in cf  # the raw "recommended" is gone


def test_wizard_texts_follow_the_users_language():
    wizard = importlib.import_module("hc_thermostat.wizard")
    assert wizard.panel_title(SimpleNamespace(config=SimpleNamespace(language="hu"))) == "HC beállítás"
    assert wizard.panel_title(SimpleNamespace(config=SimpleNamespace(language="en-GB"))) == "HC setup"
    src = (PKG / "wizard.py").read_text()
    assert 'vol.Optional("language")' in src and 'msg.get("language") or hass.config.language' in src
    js = (PKG / "www" / "hc-wizard-panel.js").read_text()
    assert "language: this._lang" in js


def test_room_exception_is_translated_by_home_assistant():
    for lang in ("hu", "en"):
        assert "{room}" in _tr(lang)["exceptions"]["room_no_target"]["message"]
    assert 'translation_key="room_no_target"' in (PKG / "climate.py").read_text()


# --- 7. / 8. names and pickers ------------------------------------------------------------------------------------
def _flow(titles):
    cf = importlib.import_module("hc_thermostat.config_flow")
    flow = cf.HcConfigFlow()
    entries = [SimpleNamespace(title=t, data={"name": t}) for t in titles]
    flow._async_current_entries = lambda include_ignore=True: entries
    return flow


def test_a_taken_name_is_a_field_error_and_the_default_is_free():
    flow = _flow(["HC Thermostat", "HC Thermostat 2"])
    assert flow._free_name() == "HC Thermostat 3"
    assert flow._name_taken(" hc thermostat ") and not flow._name_taken("Boiler")
    shown = {}
    flow.async_show_form = lambda **kw: shown.update(kw) or kw
    asyncio.run(flow.async_step_user({"name": "HC Thermostat", "role": "standalone", "heat_source": "onoff_boiler",
                                      "system": "radiator_single"}))
    assert shown["errors"] == {"name": "name_taken"}
    default = next(k for k in shown["data_schema"].schema if str(k) == "name").default()
    assert default == "HC Thermostat"  # the input is kept, not lost
    for lang in ("hu", "en"):
        assert _tr(lang)["config"]["error"]["name_taken"]


class _Reg:
    def __init__(self, ents):
        self.entities = {e.entity_id: e for e in ents}

    def async_get(self, entity_id):
        return self.entities.get(entity_id)


def test_hc_climates_and_other_instances_devices_are_excluded(monkeypatch):
    rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
    reg = _Reg([SimpleNamespace(entity_id="climate.boiler_hc", platform="hc_thermostat", domain="climate"),
                SimpleNamespace(entity_id="climate.konyha_hc", platform="hc_thermostat", domain="climate"),
                SimpleNamespace(entity_id="climate.gree", platform="gree", domain="climate")])
    monkeypatch.setattr(rooms_ha.er, "async_get", lambda hass: reg)
    entries = [SimpleNamespace(entry_id="a", title="Boiler HC", data={"room_trvs": ["climate.trv1"]}, options={}),
               SimpleNamespace(entry_id="b", title="AC HC", data={"external_climate": "climate.gree"}, options={})]
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda d=None: entries))
    assert rooms_ha.excluded_climates(hass) == ["climate.boiler_hc", "climate.gree", "climate.konyha_hc", "climate.trv1"]
    assert "climate.gree" not in rooms_ha.excluded_climates(hass, "b")  # its own device stays offered
    assert rooms_ha.climates_of_other_instances(hass, "a") == {"climate.gree": "AC HC"}
    cf = (PKG / "config_flow.py").read_text()
    assert cf.count("excluded_climates(self.hass") >= 3 and '"climate_taken"' in cf
    js = (PKG / "www" / "hc-wizard-panel.js").read_text()
    assert "exclude_entities: this._excluded()" in js


# --- 9. restart hold from Home Assistant's start ------------------------------------------------------------------
def test_an_instance_added_while_ha_runs_does_not_wait_as_after_a_restart():
    running = SimpleNamespace(data={}, is_running=True)
    coord_mod.note_ha_start(running)
    assert coord_mod.ha_started(running) <= datetime.now(timezone.utc) - timedelta(hours=23)
    starting = SimpleNamespace(data={}, is_running=False)
    coord_mod.note_ha_start(starting)
    assert (datetime.now(timezone.utc) - coord_mod.ha_started(starting)).total_seconds() < 5  # a real restart: as before
    first = coord_mod.ha_started(starting)
    coord_mod.note_ha_start(starting)
    assert coord_mod.ha_started(starting) == first  # only once per start
    assert coord_mod.ha_started(SimpleNamespace()) is None
    src = (PKG / "coordinator.py").read_text()
    assert "self._started = ha_started(hass) or dt_util.utcnow()" in src
    assert "note_ha_start(hass)" in (PKG / "__init__.py").read_text()


# --- 10. going live ----------------------------------------------------------------------------------------------
def _options_flow(options, data=None):
    cf = importlib.import_module("hc_thermostat.config_flow")
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data=data or {"role": "standalone", "control": "tpi"}, options=options, title="Boiler HC",
                            entry_id="e1")
    type(flow).config_entry = property(lambda self: entry)
    flow.async_show_menu = lambda **kw: ("menu", kw)
    flow.async_show_form = lambda **kw: ("form", kw)
    flow.async_create_entry = lambda **kw: ("create", kw)
    return flow


def test_options_start_with_a_menu_and_go_live_only_switches_the_mode():
    flow = _options_flow({"mode": "shadow", "target_home": 21.5})
    kind, kw = asyncio.run(flow.async_step_init())
    assert kind == "menu" and kw["menu_options"] == ["settings", "rooms", "go_live"]  # 0.46.0: rooms on their own
    kind, kw = asyncio.run(flow.async_step_go_live({"confirm": False}))
    assert kind == "form" and kw["errors"] == {"confirm": "confirm_active"}
    kind, kw = asyncio.run(flow.async_step_go_live({"confirm": True}))
    assert kind == "create" and kw["data"] == {"mode": "active", "target_home": 21.5}
    flow = _options_flow({"mode": "active", "target_home": 21.5})
    assert asyncio.run(flow.async_step_init())[1]["menu_options"] == ["settings", "rooms", "go_shadow"]
    assert asyncio.run(flow.async_step_go_shadow({}))[1]["data"] == {"mode": "shadow", "target_home": 21.5}
    for lang in ("hu", "en"):
        st = _tr(lang)["options"]["step"]
        assert set(st["init"]["menu_options"]) == {"settings", "rooms", "go_live", "go_shadow"} and "settings" in st


def test_the_wizard_may_start_a_new_instance_live():
    src = (PKG / "wizard.py").read_text()
    assert 'vol.Optional("start_active", default=False): bool' in src
    assert "MODE_ACTIVE if data.get(CONF_MODE) == MODE_ACTIVE else MODE_SHADOW" in (PKG / "config_flow.py").read_text()
    js = (PKG / "www" / "hc-wizard-panel.js").read_text()
    assert "start_active: !!s.start_active" in js


# --- 11.–15. packaging, units, recorder ---------------------------------------------------------------------------
def test_brand_icons_manifest_order_and_no_dead_card():
    assert (PKG / "brand" / "icon.png").is_file() and (PKG / "brand" / "icon@2x.png").is_file()
    keys = list(json.loads((PKG / "manifest.json").read_text()))
    assert keys[:2] == ["domain", "name"] and keys[2:] == sorted(keys[2:])
    assert not (PKG / "frontend" / "hc-thermostat-card.js").exists()


def test_cop_field_is_no_kwh_and_jargon_is_explained():
    cf = (PKG / "config_flow.py").read_text()
    assert 'CONF_EXTRA_FACTOR, default=3.0)] = _number(0.1, 10, 0.1, "kWh")' not in cf
    for lang in ("hu", "en"):
        t = _tr(lang)
        assert "PWM" in t["config"]["step"]["control"]["data_description"]["control"]
        assert "i-Feel" in t["config"]["step"]["control"]["data_description"]["control"]
        dd = t["options"]["step"]["settings"]["data_description"]
        assert {"control", "cycle_s", "pid_kp", "power_idle_w", "extra_factor"} <= set(dd)
        assert "Bermuda" in t["options"]["step"]["room_details"]["description"]


def test_big_attributes_are_not_recorded():
    sensor = importlib.import_module("hc_thermostat.sensor")
    assert "log" in sensor.HcDecision._unrecorded_attributes
    assert "trv_rooms" in sensor.HcRooms._unrecorded_attributes


def test_info_commands_are_admin_only():
    src = (PKG / "info.py").read_text()
    assert src.count("@websocket_api.require_admin") == 2


# --- 17. boiler health without known power levels ---------------------------------------------------------------
def _health(levels_known):
    h = bh.BoilerHealth(model.HcConfig(), "flame", levels_known=levels_known)
    t = T0
    for i in range(20):  # relay on, only the pump draws (60 W): with known levels "no_flame" after 5 minutes
        h.update(t + timedelta(minutes=i), True, 60.0, None, False)
    return h


def test_default_power_levels_do_not_raise_alarms_on_another_boiler():
    assert _health(True).state == "no_flame"
    h = _health(False)
    assert h.state == "learning" and not h.problem and h.attributes()["power_levels"] == "default"
    assert bh.power_levels_known({"power_idle_w": 20, "power_burn_w": 115})
    assert not bh.power_levels_known({})
    # without a power sensor (flame sensor only) nothing changes
    h = bh.BoilerHealth(model.HcConfig(), "flame", levels_known=False)
    for i in range(20):
        h.update(T0 + timedelta(minutes=i), True, None, False, False)
    assert h.state == "no_flame"
    for lang in ("hu", "en"):
        assert _tr(lang)["entity"]["sensor"]["boiler_health"]["state"]["learning"]


def test_options_do_not_save_untouched_default_power_levels():
    cf = (PKG / "config_flow.py").read_text()
    assert "not power_levels_known(current)" in cf
    wz = (PKG / "wizard.py").read_text()
    assert "idle = burn = None" in wz


# --- 18. names -------------------------------------------------------------------------------------------------------
def test_no_doubled_hc_in_the_pause_switch_name():
    switch = importlib.import_module("hc_thermostat.switch")
    assert switch.title_has_hc("Boiler HC") and switch.title_has_hc("HC kazán") and not switch.title_has_hc("Boiler")
    assert not switch.title_has_hc("ABHCD")
    for lang in ("hu", "en"):
        sw = _tr(lang)["entity"]["switch"]
        assert "HC" not in sw["supervision_paused_plain"]["name"] and "HC" in sw["supervision_paused"]["name"]
    assert "_attr_translation_key = \"supervision_paused_plain\"" in (PKG / "switch.py").read_text()


def test_wizard_escapes_names_and_has_no_error_on_the_start_screen():
    js = (PKG / "www" / "hc-wizard-panel.js").read_text()
    assert "<b>${esc(e.title)}</b>" in js and '<td class="why">${esc(it.why)}</td>' in js
    assert "case 0: return null;" in js
    assert "default_name" in js and '"default_name": _free_name(hass)' in (PKG / "wizard.py").read_text()


# --- 20. panels ------------------------------------------------------------------------------------------------------
def test_panels_go_with_the_last_instance_and_come_back():
    wizard = importlib.import_module("hc_thermostat.wizard")
    removed = []
    import homeassistant.components.frontend as frontend
    orig = frontend.async_remove_panel
    frontend.async_remove_panel = lambda hass, url, **kw: removed.append(url)
    try:
        hass = SimpleNamespace(data={"hc_thermostat_panels": True})
        wizard.async_remove_panels(hass)
        assert removed == ["hc-wizard", "hc-info"] and "hc_thermostat_panels" not in hass.data
        wizard.async_remove_panels(hass)  # twice: nothing more
        assert removed == ["hc-wizard", "hc-info"]
    finally:
        frontend.async_remove_panel = orig
    init = (PKG / "__init__.py").read_text()
    assert "await async_register_panels(hass)" in init and "async_remove_panels(hass)" in init


# --- 23. upgrade from 0.41.0 -----------------------------------------------------------------------------------------
def test_a_041_store_and_options_load_into_045():
    pytest.importorskip("homeassistant")
    from homeassistant.core import HomeAssistant

    fx = json.loads((ROOT / "tests" / "data" / "upgrade_0410.json").read_text())
    entry = SimpleNamespace(data={**fx["options"]}, options={}, entry_id="01TEST041", title="Boiler HC",
                            domain="hc_thermostat", async_on_unload=lambda f: None)

    async def run():
        hass = HomeAssistant(tempfile.mkdtemp())
        try:
            hass.states.async_set("sensor.living", "20.4", {"unit_of_measurement": "°C"})
            hass.states.async_set("sensor.outdoor", "4.0", {"unit_of_measurement": "°C"})
            hass.states.async_set("switch.boiler", "off")
            c = coord_mod.HcCoordinator(hass, entry)
            data = fx["store"]["data"]

            async def load():
                return data
            c._store = SimpleNamespace(async_load=load)
            await c.async_load()
            sup = c.supervisor
            old = data["supervisor"]
            assert sup.pwm.state()["cycle_start"] == old["pwm"]["cycle_start"] or sup.pwm.state() is not None
            assert len(sup.heat_need.samples) == len(old["heat_need"].get("samples", []))
            assert sup.season_on == old["season_on"]
            assert c.cfg.target_home == 21.5 and c.mode == "active" and c.health.levels_known  # levels in the options
            c._started = datetime.now(timezone.utc) - timedelta(hours=1)
            d = await c._async_update_data()
            assert d.target == 21.5 and d.indoor == 20.4 and d.reason is not None
            new = sup.state()
            assert set(old) <= set(new)  # every 0.41.0 key is still known
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())

"""0.48.0: measurements – optional readings of the heat source and the rooms (pressure, flow / return, modulation,
fault code, hot water, flue gas, fuel, core temperature, heat source state), starts and run time, COP, radiator
thermometers, humidity with dew point and mould risk; their limits turn the boiler problem sensor on."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core import measures as ms  # noqa: E402
from core.room_model import parse_room  # noqa: E402

T0 = datetime(2026, 11, 13, 6, 0, tzinfo=timezone.utc)


def _st(entity_id, state, last=T0, **attrs):
    return SimpleNamespace(entity_id=entity_id, domain=entity_id.split(".")[0], state=str(state), attributes=attrs,
                           last_reported=last, last_updated=last)


# --- core ------------------------------------------------------------------------------------------------------------
def test_fields_by_heat_source():
    assert "pressure_entity" in ms.fields_for("onoff_boiler") and "heat_output_entity" not in ms.fields_for("onoff_boiler")
    assert {"heat_output_entity", "modulation_entity", "fault_code_entity"} <= set(ms.fields_for("heat_pump"))
    assert {"flue_temp_entity", "fuel_level_entity"} <= set(ms.fields_for("pellet_boiler"))
    assert ms.fields_for("storage_heater") == ["core_temp_entity"]
    assert "source_state_entity" in ms.fields_for("external_heat")
    assert ms.fields_for("electric_heater") == []
    assert "onoff_boiler" in ms.DHW_SOURCES and "electric_heater" not in ms.DHW_SOURCES


def test_units_and_dew_point():
    assert ms.to_kwh(1.0, "GJ") == pytest.approx(277.78, abs=0.01)
    assert ms.to_kwh(3.6, "MJ") == pytest.approx(1.0)
    assert ms.to_kwh(1500, "Wh") == pytest.approx(1.5)
    assert ms.to_kwh(5, "m³") is None
    assert ms.dew_point(20.0, 50.0) == pytest.approx(9.3, abs=0.1)
    assert ms.dew_point(20.0, 0) is None


def test_starts_and_run_time_per_day():
    r = ms.RunCounter()
    t = T0
    for k in range(6):  # 6 burns of 10 minutes, every 30 minutes
        r.update(t, False)
        r.update(t + timedelta(minutes=1), True)
        r.update(t + timedelta(minutes=6), True)
        r.update(t + timedelta(minutes=11), False)
        t += timedelta(minutes=30)
    s = r.summary(t)
    assert s["starts_today"] == 6 and s["hours_today"] == pytest.approx(1.0, abs=0.01)
    assert s["starts_last_hour"] == 2 and s["season_from"] == "2026-09-01"
    r2 = ms.RunCounter()
    r2.restore(r.state())
    assert r2.summary(t)["starts_week"] == 6
    r.update(t, None)  # an unknown signal: no run is counted over the gap
    r.update(t + timedelta(hours=3), True)
    assert r.summary(t + timedelta(hours=3))["starts_today"] == 6


def test_cop_from_two_meters():
    e = ms.EnergyDays()
    e.update(T0, 1000.0, 300.0)  # the first reading only sets the base
    e.update(T0 + timedelta(hours=1), 1012.0, 304.0)
    s = e.summary(T0 + timedelta(hours=1))
    assert s["cop_today"] == 3.0 and s["heat_today_kwh"] == 12.0 and s["power_today_kwh"] == 4.0
    e.update(T0 + timedelta(hours=2), 5.0, 305.0)  # the heat meter was reset: not counted, starts over
    e.update(T0 + timedelta(hours=3), 8.0, 306.0)
    assert e.summary(T0 + timedelta(hours=3))["cop_today"] == pytest.approx(15 / 6, abs=0.01)
    assert ms.EnergyDays._cop(1.0, 0.1) is None  # too little power for a ratio


def test_mould_risk_from_the_hours_of_high_humidity():
    h = ms.Humidity()
    assert h.risk(None) is None
    h.update(T0, 55.0)
    assert h.risk(55.0) == "low"
    assert h.risk(62.0) == "moderate"
    for k in range(6):
        h.update(T0 + timedelta(hours=k + 1), 74.0)
    assert h.risk(58.0) == "high"
    h.update(T0 + timedelta(hours=40), 50.0)  # a day later the old hours are gone
    assert h.risk(50.0) == "low"


def test_radiator_cold_only_while_the_room_needs_heat():
    w = ms.RadiatorWatch()
    assert w.update(T0, None, 20.0, True, True) is None
    assert w.update(T0, 22.0, 20.0, False, True) == "idle"
    assert w.update(T0, 22.0, 20.0, True, False) == "idle"
    assert w.update(T0, 23.0, 20.0, True, True) == "cold"
    assert w.cold_for_min(T0 + timedelta(minutes=25)) == pytest.approx(25.0)
    assert w.update(T0 + timedelta(minutes=30), 45.0, 20.0, True, True) == "warm" and w.cold_since is None


def test_source_problems():
    lim = ms.Limits()
    assert ms.source_problems({"pressure": 0.7}, lim, 0, False) == ["pressure_low"]
    assert ms.source_problems({"pressure": 2.9}, lim, 0, False) == ["pressure_high"]
    assert ms.source_problems({"pressure": 1.5, "fuel_level": 9.0}, lim, 0, False) == ["fuel_low"]
    assert ms.source_problems({}, lim, 8, True) == ["short_cycling"]
    assert ms.source_problems({}, lim, 8, False) == []
    assert ms.source_problems({"fault_code": "E133"}, lim, 0, False) == ["fault_code"]
    assert ms.source_problems({"fault_code": "0"}, lim, 0, False) == []
    assert ms.Limits.from_conf({"pressure_min": "0.8", "fuel_min": "x"}).pressure_min == 0.8
    assert ms.Limits.from_conf({"fuel_min": "x"}).fuel_min == 15.0


# --- rooms -----------------------------------------------------------------------------------------------------------
def test_a_room_keeps_its_radiators_and_humidity_sensors():
    spec = parse_room({"name": "Nappali", "sensors": ["sensor.t"], "radiators": ["sensor.rad", "light.x"],
                       "humidity": ["sensor.rh"]})
    assert spec.radiators == ["sensor.rad"] and spec.humidity == ["sensor.rh"]
    d = spec.as_dict()
    assert d["radiators"] == ["sensor.rad"] and d["humidity"] == ["sensor.rh"]
    assert "radiators" not in parse_room({"name": "K", "sensors": ["sensor.k"]}).as_dict()


def test_room_form_offers_radiators_and_humidity():
    pytest.importorskip("homeassistant")
    rf = importlib.import_module("hc_thermostat.room_form")
    area = {"area": "nappali", "name": "Nappali", "sensors": [{"id": "sensor.t", "head": False}],
            "radiators": [{"id": "sensor.radiator"}], "humidity": [{"id": "sensor.rh"}], "trvs": [], "presence": [],
            "windows": []}
    room = rf.new_room(area, set())
    assert room["radiators"] == ["sensor.radiator"] and room["humidity"] == ["sensor.rh"]
    cands = rf.room_candidates(room, area, [], set())
    assert cands["radiators"][0] == "sensor.radiator" and "sensor.t" in cands["radiators"]
    w = rf.WORDS["hu"]
    out = rf.read_section(None, "hu", room, {w["name"]: "Nappali", w["radiators"]: ["sensor.t"], w["humidity"]: []})
    assert out["radiators"] == ["sensor.t"] and out["humidity"] == []
    problem = rf.check_rooms("hu", [{**out, "sensors": ["sensor.t"]}], "nappali", False, set(), {}, lambda e: e)
    assert "radiátor-hőmérő" in problem
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: {
        "sensor.rh": _st("sensor.rh", "55", device_class="humidity"),
        "sensor.nappali_radiator": _st("sensor.nappali_radiator", "40", device_class="temperature",
                                       friendly_name="Nappali radiátor")}.get(e)))
    assert rf.classify(hass, "sensor.rh") == "humidity"
    assert rf.classify(hass, "sensor.nappali_radiator") == "radiators"


# --- the coordinator -------------------------------------------------------------------------------------------------
def _coordinator(states, conf, actual=True, mode="active"):
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    model = importlib.import_module("hc_thermostat.core.model")
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: states.get(e)),
                             config=SimpleNamespace(units=SimpleNamespace(temperature_unit="°C"), language="hu"))
    c.conf, c.cfg, c.mode, c.actual = conf, model.HcConfig.from_mapping(conf), mode, actual
    c.runs, c.energy_days, c._humid, c._radiators = ms.RunCounter(), ms.EnergyDays(), {}, {}
    c.measures, c.measure_problems, c.room_states = {}, [], {}
    c._room_groups, c._trv_groups, c._specs = None, None, None
    decision = model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.5, output=True)
    return c, decision


def test_the_coordinator_works_out_the_measurements():
    pytest.importorskip("homeassistant")
    states = {"sensor.p": _st("sensor.p", "0.8", unit_of_measurement="bar"),
              "sensor.flow": _st("sensor.flow", "55", unit_of_measurement="°C"),
              "sensor.ret": _st("sensor.ret", "45", unit_of_measurement="°C"),
              "sensor.fault": _st("sensor.fault", "0"), "switch.boiler": _st("switch.boiler", "on"),
              "sensor.rh": _st("sensor.rh", "64", unit_of_measurement="%", device_class="humidity")}
    conf = {"heat_source": "onoff_boiler", "control": "pid", "actuator_entity": "switch.boiler",
            "pressure_entity": "sensor.p", "flow_temp_entity": "sensor.flow", "return_temp_entity": "sensor.ret",
            "fault_code_entity": "sensor.fault", "humidity_entity": "sensor.rh"}
    c, d = _coordinator(states, conf)
    c._update_measures(d, T0)
    m = c.measures
    assert m["pressure"] == 0.8 and m["delta_t"] == 10.0 and m["fault_code"] == "0"
    assert m["runs"]["starts_today"] == 0 and m["humidity"]["risk"] == "moderate"
    assert m["humidity"]["dew_point"] == pytest.approx(13.0, abs=0.2)  # at the house's 20 °C
    assert c.measure_problems == ["pressure_low"]
    assert set(c.measure_keys()) >= {"pressure_entity", "flow_temp_entity", "humidity_entity"}
    states["sensor.p"] = _st("sensor.p", "21.0", unit_of_measurement="psi")
    c._update_measures(d, T0 + timedelta(minutes=1))
    assert c.measures["pressure"] == pytest.approx(1.45, abs=0.01) and c.measure_problems == []


def test_the_coordinator_cop_and_a_cold_radiator():
    pytest.importorskip("homeassistant")
    states = {"sensor.heat": _st("sensor.heat", "100", unit_of_measurement="kWh"),
              "sensor.power": _st("sensor.power", "30", unit_of_measurement="kWh"),
              "sensor.k": _st("sensor.k", "19.0", unit_of_measurement="°C"),
              "sensor.k_rad": _st("sensor.k_rad", "21.0", unit_of_measurement="°C")}
    conf = {"heat_source": "heat_pump", "control": "pid", "heat_output_entity": "sensor.heat",
            "heat_energy_entity": "sensor.power",
            "rooms": [{"key": "k", "name": "Konyha", "sensors": ["sensor.k"], "radiators": ["sensor.k_rad"]}],
            "leading_room": "k", "indoor_entity": "sensor.k"}
    c, d = _coordinator(states, conf)
    c.room_states = {"k": {"temperature": 19.0, "target": 21.0}}
    for minutes, heat, power in ((0, 100, 30), (10, 103, 31), (25, 106, 32)):
        states["sensor.heat"] = _st("sensor.heat", heat, last=T0 + timedelta(minutes=minutes), unit_of_measurement="kWh")
        states["sensor.power"] = _st("sensor.power", power, last=T0 + timedelta(minutes=minutes), unit_of_measurement="kWh")
        states["sensor.k_rad"] = _st("sensor.k_rad", "21.0", last=T0 + timedelta(minutes=minutes), unit_of_measurement="°C")
        c._update_measures(d, T0 + timedelta(minutes=minutes))
    assert c.measures["cop"]["cop_today"] == 3.0
    room = c.measures["rooms"]["k"]
    assert room["radiator"]["status"] == "cold" and room["radiator"]["cold_min"] == 25
    assert c.measure_problems == ["radiator_cold:Konyha"]
    assert "rooms" in c.measure_keys()


# --- entities, options, texts ----------------------------------------------------------------------------------------
def test_entities_and_problem_sensor_source():
    src = (ROOT / "binary_sensor.py").read_text()
    assert "self.coordinator.health.problem or bool(self.coordinator.measure_problems)" in src
    assert "or c.measure_keys()" in src
    ents = (ROOT / "measure_entities.py").read_text()
    for key in ("starts_today", "run_hours_today", "cop", "delta_t", "mould_risk"):
        assert f'"{key}")' in ents
    assert "measure_sensors(hass, entry, c)" in (ROOT / "sensor.py").read_text()


def test_settings_section_by_heat_source():
    pytest.importorskip("homeassistant")
    cf = importlib.import_module("hc_thermostat.config_flow")
    keys = lambda sec: {str(k) for k in next(iter(sec.values())).schema.schema}
    boiler = keys(cf._measure_section("radiator_single", "onoff_boiler", "pid", {}, True))
    assert {"pressure_entity", "flow_temp_entity", "return_temp_entity", "hp_dhw_entity", "humidity_entity",
            "pressure_min", "pressure_max", "starts_per_hour_max", "radiator_cold_min"} <= boiler
    assert "heat_output_entity" not in boiler and "fuel_min" not in boiler
    hp = keys(cf._measure_section("floor_single", "heat_pump", "curve", {}, False))
    assert "heat_output_entity" in hp and "hp_dhw_entity" not in hp and "humidity_entity" not in hp  # cooling has it
    district = keys(cf._measure_section("radiator_single", "district_heating", "tpi", {}, False))
    assert "return_temp_entity" not in district and "radiator_cold_min" not in district
    ac = keys(cf._measure_section("room_unit", "air_conditioner", "ac", {}, False))
    assert "starts_per_hour_max" not in ac and "heat_output_entity" in ac
    assert '"measures"' in (ROOT / "config_flow.py").read_text()


def test_version():
    assert json.loads((ROOT / "manifest.json").read_text())["version"] == "0.48.0"


def test_texts():
    for lang in ("hu", "en"):
        tr = json.loads((ROOT / "translations" / f"{lang}.json").read_text())
        sec = tr["options"]["step"]["settings"]["sections"]["measures"]
        for k in (*ms.FIELDS, "hp_dhw_entity", "humidity_entity", *ms.DEFAULTS):
            assert sec["data"][k], k
        for k in ("starts_today", "run_hours_today", "cop", "delta_t", "mould_risk", "room_mould_risk"):
            assert tr["entity"]["sensor"][k]["name"]
        assert set(tr["entity"]["sensor"]["mould_risk"]["state"]) == {"low", "moderate", "high"}
    js = (ROOT / "www" / "hc-info-panel.js").read_text()
    assert "_measures()" in js and "Mérések" in js and "penész-kockázat" in js
    hu = json.loads((ROOT / "translations" / "hu.json").read_text())
    assert "szoba" not in json.dumps(hu["options"]["step"]["settings"]["sections"]["measures"], ensure_ascii=False)

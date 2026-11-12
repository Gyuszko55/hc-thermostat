"""0.42.0: a thermometer per TRV head (`trv_sensors`), the narrowed list of thermometers for a head, legacy
`trv_calibration`, and HC info by a head's entity id."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
trv = importlib.import_module("hc_thermostat.core.trv")
rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
info = importlib.import_module("hc_thermostat.info")
wizard = importlib.import_module("hc_thermostat.wizard")

T0 = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)
ROOMS = {"Konyha": ["sensor.konyha_th"], "Háló": ["sensor.halo_th"]}
TRVS = {"Konyha": ["climate.konyha_trv"], "Háló": ["climate.halo_trv"], "Fürdő": ["climate.furdo_trv"]}


# --- which thermometer each head follows ---------------------------------------------------------------------------
def test_per_head_sensors_win_and_an_unlisted_head_uses_its_own():
    conf = {"trv_sensors": {"climate.konyha_trv": "sensor.konyha_th", "climate.halo_trv": "head"},
            "trv_calibration": True}  # the old switch no longer counts once trv_sensors is saved
    assert trv.trv_sources(conf, ROOMS, TRVS) == {
        "climate.konyha_trv": ["sensor.konyha_th"], "climate.halo_trv": [], "climate.furdo_trv": []}


def test_empty_trv_sensors_means_every_head_on_its_own():
    assert trv.trv_sources({"trv_sensors": {}, "trv_calibration": True}, ROOMS, TRVS) == {
        "climate.konyha_trv": [], "climate.halo_trv": [], "climate.furdo_trv": []}


def test_legacy_calibration_follows_the_room_thermometers():
    assert trv.trv_sources({"trv_calibration": True}, ROOMS, TRVS) == {
        "climate.konyha_trv": ["sensor.konyha_th"], "climate.halo_trv": ["sensor.halo_th"], "climate.furdo_trv": []}
    assert trv.trv_sources({}, ROOMS, TRVS) == {"climate.konyha_trv": [], "climate.halo_trv": [], "climate.furdo_trv": []}


def test_a_new_thermometer_drops_what_was_learned():
    cal = trv.TrvCalibration()
    cal.set_source("climate.k", ["sensor.a"])
    cal.update("climate.k", 22.0, 21.4, T0)
    assert cal.set_source("climate.k", ["sensor.a"]) is False and round(cal.offset["climate.k"], 2) == 0.6  # same: kept
    assert cal.set_source("climate.k", ["sensor.b"]) is True and "climate.k" not in cal.offset  # another: dropped
    cal.update("climate.k", 22.0, 21.0, T0)
    assert cal.set_source("climate.k", []) is True and "climate.k" not in cal.offset  # its own sensor: none


def test_a_head_learned_before_0_42_keeps_its_offset():
    cal = trv.TrvCalibration()
    cal.restore({"climate.k": 0.6})  # no sources saved yet: learned against the room thermometer
    assert cal.set_source("climate.k", ["sensor.konyha_th"]) is False and cal.offset["climate.k"] == 0.6
    again = trv.TrvCalibration()
    again.restore(cal.state(), dict(cal.source))
    assert again.source == {"climate.k": "sensor.konyha_th"}


# --- in the coordinator ---------------------------------------------------------------------------------------------
class _Hass:
    def __init__(self, states):
        self._states, self.calls, self.data = states, [], {}
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))
        self.services = SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def _state(value, last=T0, **attrs):
    return SimpleNamespace(state=str(value), attributes=attrs, last_reported=last)


def _coordinator(monkeypatch, states, conf):
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    model = importlib.import_module("hc_thermostat.core.model")
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: T0)
    monkeypatch.setattr(coord_mod.dt_util, "utcnow", lambda: T0)
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass, c.conf, c.mode = _Hass(states), conf, "active"
    c.cfg = model.HcConfig.from_mapping(conf)
    c.trv_targets, c.trv_cal, c.trv_info = trv.TrvTargets(), trv.TrvCalibration(), {}
    c._room_groups = {"Konyha": ["sensor.konyha_th"]}
    c._trv_groups = {"Konyha": ["climate.konyha_trv"], "Háló": ["climate.halo_trv"]}
    return c, model


STATES = {
    "sensor.konyha_th": _state(21.0),
    "sensor.halo_other": _state(19.0),  # a thermometer chosen for the bedroom head (any area may be chosen)
    "climate.konyha_trv": _state("heat", temperature=21.0, current_temperature=21.6, target_temp_step=0.5),
    "climate.halo_trv": _state("heat", temperature=21.0, current_temperature=20.0, target_temp_step=0.5),
}


def test_each_head_is_calibrated_against_its_own_choice(monkeypatch):
    c, model = _coordinator(monkeypatch, dict(STATES), {"trv_sensors": {"climate.halo_trv": "sensor.halo_other"}})
    asyncio.run(c._apply_trvs(model.Decision(T0, model.Reason.REGULATING, 21.0, 21.0, 0.0)))
    heads = {h: v for r in c.trv_info.values() for h, v in r["heads"].items()}
    assert heads["climate.konyha_trv"]["sensor"] == "head" and heads["climate.konyha_trv"]["calibration"] == 0.0
    assert heads["climate.halo_trv"]["sensor"] == "sensor.halo_other" and heads["climate.halo_trv"]["calibration"] == 1.0
    written = {d["entity_id"]: d["temperature"] for _, _, d in c.hass.calls}
    assert written == {"climate.halo_trv": 22.0}  # 21 + 1 calibration; the kitchen head already holds 21


def test_legacy_switch_still_uses_the_room_thermometer(monkeypatch):
    c, model = _coordinator(monkeypatch, dict(STATES), {"trv_calibration": True})
    asyncio.run(c._apply_trvs(model.Decision(T0, model.Reason.REGULATING, 21.0, 21.0, 0.0)))
    k = c.trv_info["Konyha"]["heads"]["climate.konyha_trv"]
    assert k["sensor"] == "sensor.konyha_th" and k["calibration"] == 0.6
    assert c.trv_info["Háló"]["heads"]["climate.halo_trv"]["calibration"] == 0.0  # no room thermometer there
    assert c.trv_cal.source["climate.konyha_trv"] == "sensor.konyha_th"


def test_switching_to_the_same_sensor_explicitly_keeps_the_learned_offset(monkeypatch):
    c, model = _coordinator(monkeypatch, dict(STATES), {"trv_calibration": True})
    asyncio.run(c._apply_trvs(model.Decision(T0, model.Reason.REGULATING, 21.0, 21.0, 0.0)))
    c.conf = {"trv_sensors": {"climate.konyha_trv": "sensor.konyha_th"}}  # what the wizard / options save then
    c.hass._states["climate.konyha_trv"] = _state("heat", temperature=21.5, current_temperature=21.0, target_temp_step=0.5)
    asyncio.run(c._apply_trvs(model.Decision(T0 + timedelta(seconds=1), model.Reason.REGULATING, 21.0, 21.0, 0.0)))
    assert 0.5 < c.trv_info["Konyha"]["heads"]["climate.konyha_trv"]["calibration"] <= 0.6  # kept, barely moved


def test_a_trv_room_without_room_sensor_reads_the_chosen_thermometer(monkeypatch):
    c, _ = _coordinator(monkeypatch, dict(STATES), {"trv_sensors": {"climate.halo_trv": "sensor.halo_other"}})
    readings = c._room_readings(T0)
    assert readings["Háló"] == 19.0 and readings["Konyha"] == 21.0


# --- the thermometers offered for a head ------------------------------------------------------------------------------
def _s(id_, name, area, device=None, available=True):
    return {"id": id_, "name": name, "area": area, "device": device, "available": available}


def test_candidates_are_the_area_s_thermometers_by_name():
    sensors = [_s("sensor.konyha_trv_local_temperature", "Konyha TRV local", "konyha", device="dev_trv"),
               _s("sensor.konyha_th", "Konyha TH", "konyha"), _s("sensor.b", "Asztali hőmérő", "konyha"),
               _s("sensor.dead", "Halott", "konyha", available=False), _s("sensor.nappali", "Nappali", "nappali")]
    picked, fallback = rooms_ha.pick_trv_candidates("konyha", "dev_trv", sensors)
    assert [p["id"] for p in picked] == ["sensor.b", "sensor.konyha_th"] and fallback is False


def test_no_thermometer_in_the_area_lists_every_one():
    sensors = [_s("sensor.own", "Own", "furdo", device="dev_trv"), _s("sensor.n", "Nappali", "nappali"),
               _s("sensor.k", "Konyha", "konyha"), _s("sensor.x", "X", None)]
    picked, fallback = rooms_ha.pick_trv_candidates("furdo", "dev_trv", sensors)
    assert [p["id"] for p in picked] == ["sensor.k", "sensor.n", "sensor.x"] and fallback is True
    assert rooms_ha.pick_trv_candidates(None, None, sensors)[1] is True  # a head without an area


class _Reg:
    """Entity, device and area registries in one."""

    def __init__(self, entities, devices, areas):
        self.entities, self.devices, self.areas = entities, devices, areas

    def async_get(self, key):
        return self.entities.get(key) or self.devices.get(key)

    def async_get_area(self, area_id):
        return SimpleNamespace(name=self.areas[area_id]) if area_id in self.areas else None


def _fake_ha(monkeypatch):
    reg = _Reg(
        entities={"climate.konyha_trv": SimpleNamespace(area_id=None, device_id="dev_trv"),
                  "sensor.konyha_trv_local_temperature": SimpleNamespace(area_id=None, device_id="dev_trv"),
                  "sensor.konyha_th_temperature": SimpleNamespace(area_id=None, device_id="dev_th"),
                  "sensor.nappali_temperature": SimpleNamespace(area_id="nappali", device_id=None),
                  "sensor.konyha_hum": SimpleNamespace(area_id="konyha", device_id=None),
                  "sensor.hc_learned": SimpleNamespace(area_id="konyha", device_id=None, platform="hc_thermostat")},
        devices={"dev_trv": SimpleNamespace(area_id="konyha"), "dev_th": SimpleNamespace(area_id="konyha")},
        areas={"konyha": "Konyha", "nappali": "Nappali"})
    for mod in (rooms_ha.er, rooms_ha.dr, rooms_ha.ar):
        monkeypatch.setattr(mod, "async_get", lambda hass, reg=reg: reg)
    states = [SimpleNamespace(entity_id="sensor.konyha_trv_local_temperature", state="21.6",
                              attributes={"device_class": "temperature", "friendly_name": "Konyha TRV local", "unit_of_measurement": "°C"}),
              SimpleNamespace(entity_id="sensor.konyha_th_temperature", state="21.0",
                              attributes={"device_class": "temperature", "friendly_name": "Konyha TH", "unit_of_measurement": "°C"}),
              SimpleNamespace(entity_id="sensor.nappali_temperature", state="22.0",
                              attributes={"unit_of_measurement": "°C", "friendly_name": "Nappali"}),
              SimpleNamespace(entity_id="sensor.hc_learned", state="0.8",
                              attributes={"unit_of_measurement": "°C", "friendly_name": "HC tanult"}),
              SimpleNamespace(entity_id="sensor.konyha_hum", state="50",
                              attributes={"device_class": "humidity", "unit_of_measurement": "%"})]
    return SimpleNamespace(states=SimpleNamespace(async_all=lambda domain=None: states))


def test_candidates_from_the_registries_use_the_device_area(monkeypatch):
    hass = _fake_ha(monkeypatch)
    out = rooms_ha.trv_sensor_candidates(hass, "climate.konyha_trv")
    assert out["room"] == "Konyha" and out["fallback"] is False
    assert [c["id"] for c in out["candidates"]] == ["sensor.konyha_th_temperature"]
    assert out["suggest"] == "sensor.konyha_th_temperature"


def test_current_sensors_for_a_legacy_instance(monkeypatch):
    hass = _fake_ha(monkeypatch)
    legacy = {"room_trvs": ["climate.konyha_trv"], "room_sensors": ["sensor.konyha_th_temperature"], "trv_calibration": True}
    assert rooms_ha.current_trv_sensors(hass, legacy) == {"climate.konyha_trv": "sensor.konyha_th_temperature"}
    assert rooms_ha.current_trv_sensors(hass, {**legacy, "trv_calibration": False}) == {}
    assert rooms_ha.current_trv_sensors(hass, {**legacy, "trv_sensors": {}}) == {}


# --- the wizard writes ------------------------------------------------------------------------------------------------
def test_wizard_trv_options():
    trv_in = {"room_trvs": ["climate.konyha_trv", "climate.konyha_trv", "light.x"],
              "trv_sensors": {"climate.konyha_trv": "sensor.konyha_th", "climate.gone": "sensor.y"},
              "trv_offsets": {"Konyha": "1.5", "Háló": 0, "Fürdő": 9}, "room_trv_demand": True}
    assert wizard.trv_options("pid", trv_in) == {
        "room_trvs": ["climate.konyha_trv"], "trv_sensors": {"climate.konyha_trv": "sensor.konyha_th"},
        "trv_offsets": {"Konyha": 1.5, "Fürdő": 5.0}, "room_trv_demand": True}
    assert wizard.trv_options("external", trv_in) is None and wizard.trv_options("tpi", None) is None
    assert wizard.trv_options("tpi", {"room_trvs": [], "room_trv_demand": True})["room_trv_demand"] is False


# --- HC info by a head ------------------------------------------------------------------------------------------------
class _Conn:
    def __init__(self):
        self.result = self.error = None
        self.user = SimpleNamespace(is_admin=True)  # 0.45.0: the info commands are admins only

    def send_result(self, _id, result):
        self.result = result

    def send_error(self, _id, code, message):
        self.error = code


def test_info_by_a_trv_head_returns_its_host(monkeypatch):
    host = SimpleNamespace(entry_id="e1", title="Cirkó HC", data={"role": "standalone"},
                           options={"room_trvs": ["climate.konyha_trv"]}, runtime_data=object())
    other = SimpleNamespace(entry_id="e2", title="Terasz", data={}, options={}, runtime_data=object())
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: [other, host]),
                           states=SimpleNamespace(get=lambda e: SimpleNamespace(state="heat", attributes={"friendly_name": "Konyha TRV"})))
    monkeypatch.setattr(info, "entry_of_entity", lambda hass, entity_id: None)
    monkeypatch.setattr(info, "_instance", lambda hass, entry: {"entry_id": entry.entry_id})
    conn = _Conn()
    info.ws_info(hass, conn, {"id": 1, "type": "hc_thermostat/info", "entity_id": "climate.konyha_trv"})
    assert conn.result == {"entry_id": "e1", "via_trv": "climate.konyha_trv"}
    conn = _Conn()
    info.ws_info(hass, conn, {"id": 2, "type": "hc_thermostat/info", "entity_id": "climate.unknown"})
    assert conn.error == "not_found"
    conn = _Conn()
    info.ws_info_list(hass, conn, {"id": 3})
    assert [x["trvs"] for x in conn.result] == [[], [{"entity_id": "climate.konyha_trv", "name": "Konyha TRV"}]]

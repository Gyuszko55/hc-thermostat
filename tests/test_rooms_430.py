"""0.43.0: rooms of one boiler – the room list (saved or derived from the legacy options), room targets, presence,
TRV rooms against their thermometer group, rooms without a TRV following the house, the leading room, room demand,
the options the wizard / options flow write, and HC info by a room climate."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
rm = importlib.import_module("hc_thermostat.core.room_model")
trv = importlib.import_module("hc_thermostat.core.trv")
rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
info = importlib.import_module("hc_thermostat.info")
wizard = importlib.import_module("hc_thermostat.wizard")
model = importlib.import_module("hc_thermostat.core.model")

T0 = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)  # 18:00 – day by the default night window
NIGHT = datetime(2026, 11, 11, 23, 0, tzinfo=timezone.utc)

# the live "Cirkó HC" shape (0.41.0 options)
CIRKO = {"indoor_entity": "sensor.ht_plus_temperature", "control": "pid", "role": "standalone",
         "room_sensors": ["sensor.konyha_th_temperature", "sensor.haloszoba_th_temperature"],
         "room_trvs": ["climate.konyha_trv"], "trv_calibration": True, "room_trv_demand": False}
CIRKO_SENSORS = {"Konyha": ["sensor.konyha_th_temperature"], "Hálószoba": ["sensor.haloszoba_th_temperature"]}
CIRKO_TRVS = {"Konyha": ["climate.konyha_trv"]}
KEYS = {"Nappali": "nappali", "Konyha": "konyha", "Hálószoba": "haloszoba"}


def key_of(name, ids):
    return KEYS.get(name, rm.slugify(name)), KEYS.get(name)


# --- the room list -----------------------------------------------------------------------------------------------------
def test_live_cirko_shape_becomes_three_rooms_with_the_same_behaviour():
    specs, leading = rm.legacy_rooms(CIRKO, CIRKO_SENSORS, CIRKO_TRVS, key_of, "Nappali")
    assert leading == "nappali"
    by = {s.key: s for s in specs}
    assert list(by) == ["nappali", "konyha", "haloszoba"]
    assert by["nappali"].sensors == ["sensor.ht_plus_temperature"] and not by["nappali"].trvs
    k = by["konyha"]
    assert k.trvs == ["climate.konyha_trv"] and k.sensors == ["sensor.konyha_th_temperature"]
    assert k.mode == "follow" and k.offset == 0.0 and k.presence == [] and k.demand is False
    assert k.head_sources() == {"climate.konyha_trv": ["sensor.konyha_th_temperature"]}  # calibrated as before
    h = by["haloszoba"]
    assert h.sensors == ["sensor.haloszoba_th_temperature"] and not h.trvs


@pytest.mark.parametrize("conf", [
    {"trv_calibration": True},
    {},
    {"trv_sensors": {"climate.konyha_trv": "sensor.konyha_th_temperature"}},
    {"trv_sensors": {"climate.konyha_trv": "sensor.other"}},
    {"trv_sensors": {}, "trv_calibration": True},
])
def test_derived_head_sources_equal_the_legacy_rule(conf):
    groups = {"Konyha": ["sensor.konyha_th_temperature"]}
    trvs = {"Konyha": ["climate.konyha_trv"], "Fürdő": ["climate.furdo_trv"]}
    specs, _ = rm.legacy_rooms(conf, groups, trvs, key_of)
    derived = {h: src for s in specs for h, src in s.head_sources().items()}
    assert derived == trv.trv_sources(conf, groups, trvs)


def test_legacy_offsets_and_demand_per_room():
    conf = {"trv_offsets": {"Hálószoba": -2, "Fürdő": "1.5"}, "room_trv_demand": True}
    specs, leading = rm.legacy_rooms(conf, {"Hálószoba": ["sensor.h"]}, {"Hálószoba": ["climate.h"], "Fürdő": ["climate.f"]}, key_of)
    by = {s.name: s for s in specs}
    assert leading is None and by["Hálószoba"].offset == -2.0 and by["Fürdő"].offset == 1.5
    assert by["Hálószoba"].demand and by["Fürdő"].demand


def test_a_leading_area_that_is_also_a_room_is_not_doubled():
    specs, leading = rm.legacy_rooms({"indoor_entity": "sensor.n"}, {"Nappali": ["sensor.n2"]}, {}, key_of, "Nappali")
    assert leading is None and [s.name for s in specs] == ["Nappali"]


def test_parse_is_lenient_and_keys_unique():
    specs = rm.parse_rooms([
        {"name": "Konyha", "area": "konyha", "sensors": ["sensor.a", "sensor.a", "light.x"], "trvs": ["climate.k"],
         "offset": 9, "absent_min": "x", "setback": -3, "mode": "weird", "demand": True,
         "head_sensors": {"climate.k": "head", "climate.gone": "sensor.y"}},
        {"name": "Konyha 2", "key": "konyha"},
        "junk", {"name": ""},
        {"name": "Fürdő", "trvs": [], "demand": True, "mode": "own", "target_home": 23, "night_start": "21:30"},
    ])
    k, k2, f = specs
    assert k.key == "konyha" and k.sensors == ["sensor.a"] and k.offset == 5.0 and k.absent_min == 15.0
    assert k.setback == 0.0 and k.mode == "follow" and k.head_sensors == {"climate.k": "head"} and k.demand
    assert k2.key == "konyha_2" and f.key == "furdo" and f.demand is False  # no TRV: never asks the boiler
    assert f.mode == "own" and f.target_home == 23.0 and f.night_start == "21:30"
    again = rm.parse_rooms([s.as_dict() for s in specs])
    assert [s.as_dict() for s in again] == [s.as_dict() for s in specs]


def test_rooms_options_write_the_list_the_leading_room_and_the_legacy_keys():
    rooms = [{"key": "nappali", "name": "Nappali", "sensors": []},
             {"key": "konyha", "name": "Konyha", "sensors": ["sensor.k1", "sensor.k2"], "trvs": ["climate.k"],
              "offset": -1, "demand": True},
             {"key": "halo", "name": "Háló", "sensors": ["sensor.h"]},
             {"key": "furdo", "name": "Fürdő", "trvs": ["climate.f"], "head_sensors": {"climate.f": "sensor.x"}}]
    out = rm.rooms_options(rooms, "nappali", "sensor.main")
    assert out["leading_room"] == "nappali" and out["rooms"][0]["sensors"] == ["sensor.main"]  # gets the house one
    assert "indoor_entity" not in out
    assert out["room_sensors"] == ["sensor.k1", "sensor.k2", "sensor.h"]
    assert out["room_trvs"] == ["climate.k", "climate.f"]
    assert out["trv_sensors"] == {"climate.k": "sensor.k1", "climate.f": "sensor.x"}
    assert out["trv_offsets"] == {"Konyha": -1.0} and out["room_trv_demand"] is True
    moved = rm.rooms_options([{"key": "nappali", "name": "Nappali", "sensors": ["sensor.n1", "sensor.n2"]}], "nappali", "sensor.main")
    assert moved["indoor_entity"] == "sensor.n1"  # the leading room's thermometers are the house's
    assert rm.rooms_options(rooms, "nope", "sensor.main")["leading_room"] is None


# --- presence ------------------------------------------------------------------------------------------------------------
def test_presence_sources():
    p = rm.presence_of
    assert p("Konyha", {"area_id": "konyha"}, "sensor", "konyha", "Konyha") is True
    assert p("konyha", {}, "input_select", "konyha", "Konyha") is True  # area id as the state
    assert p("Nappali", {"area_id": "nappali"}, "sensor", "konyha", "Konyha") is False
    assert p("not_home", {"area_id": None}, "sensor", "konyha", "Konyha") is False
    assert p("unknown", {}, "sensor", "konyha", "Konyha") is None and p(None, {}, "sensor", "konyha", "Konyha") is None
    assert p("on", {}, "binary_sensor", "konyha", "Konyha") is True and p("off", {}, "binary_sensor", "k", "K") is False
    assert p("unavailable", {}, "binary_sensor", "k", "K") is None


def test_absent_only_after_the_delay_and_back_at_once():
    pr = rm.RoomPresence()
    assert pr.update(T0, [True], 900) == rm.PRESENT
    assert pr.update(T0 + timedelta(minutes=1), [False, None], 900) == rm.LEAVING
    assert pr.update(T0 + timedelta(minutes=15), [False], 900) == rm.LEAVING
    assert pr.update(T0 + timedelta(minutes=16), [False], 900) == rm.ABSENT
    assert pr.update(T0 + timedelta(minutes=17), [None], 900) == rm.ABSENT  # unknown: holds
    assert pr.update(T0 + timedelta(minutes=18), [False, True], 900) == rm.PRESENT and pr.absent_since is None


def test_presence_is_restart_safe():
    pr = rm.RoomPresence()
    assert pr.update(T0, [None, None], 900) == rm.PRESENT  # nothing known after a start: present
    assert pr.update(T0, [False], 900, settling=True) == rm.PRESENT  # the sources wake up: no clock yet
    assert pr.update(T0 + timedelta(minutes=6), [False], 900) == rm.LEAVING  # settled: the clock starts now
    assert pr.update(T0 + timedelta(minutes=20), [False], 900) == rm.LEAVING
    assert pr.update(T0 + timedelta(minutes=22), [False], 900) == rm.ABSENT
    again = rm.RoomPresence()
    again.restore(pr.state())
    assert again.update(T0 + timedelta(hours=2), [None], 900) == rm.ABSENT  # absent before the restart stays
    fresh = rm.RoomPresence()
    fresh.restore({"absent_since": (T0 - timedelta(minutes=5)).isoformat(), "absent": False})
    assert fresh.update(T0, [False], 900, settling=True) == rm.LEAVING  # not concluded while settling


# --- the room's target ---------------------------------------------------------------------------------------------------
def _spec(**kw):
    return rm.RoomSpec(key="k", name="Konyha", trvs=["climate.k"], **kw)


def test_follow_target_with_offset():
    c = rm.RoomControl()
    t = c.target(_spec(offset=-1.5), T0, 21.0, "home", 7.0, 15.0)
    assert (t.target, t.reason) == (19.5, "follow")
    assert c.target(_spec(offset=-1.5), T0, 17.0, "away", 7.0, 15.0).target == 15.5  # the house is away already


def test_own_schedule_and_household():
    spec = _spec(mode="own", target_home=22.0, target_night=18.5, target_away=16.0)
    c = rm.RoomControl()
    assert c.target(spec, T0, 21.0, "home", 7.0, 15.0).target == 22.0
    assert c.target(spec, NIGHT, 21.0, "home", 7.0, 15.0).reason == "night"
    assert c.target(spec, T0, 21.0, "away", 7.0, 15.0).target == 16.0
    assert c.target(spec, T0, 21.0, "vacation", 7.0, 14.0).target == 14.0


def test_absent_sets_back_but_never_below_frost_and_not_while_the_household_is_away():
    spec = _spec(presence=["sensor.x"], setback=3.0)
    c = rm.RoomControl()
    c.presence_state = rm.ABSENT
    assert c.target(spec, T0, 21.0, "home", 7.0, 15.0).target == 18.0
    assert c.target(_spec(presence=["sensor.x"], setback=10.0), T0, 9.0, "home", 7.0, 15.0).target == 7.0
    t = c.target(spec, T0, 17.0, "away", 7.0, 15.0)
    assert t.target == 17.0 and t.reason == "follow"
    c.presence_state = rm.LEAVING
    assert c.target(spec, T0, 21.0, "home", 7.0, 15.0).target == 21.0  # not yet


def test_manual_and_preset_hold_until_the_automatic_target_changes():
    spec = _spec(presence=["sensor.x"])
    c = rm.RoomControl()
    c.target(spec, T0, 21.0, "home", 7.0, 15.0)
    c.manual = 23.0
    assert c.target(spec, T0, 21.0, "home", 7.0, 15.0).reason == "manual"
    assert c.target(spec, T0, 19.0, "home", 7.0, 15.0, commit=False).target == 19.0  # a look does not forget it
    assert c.manual == 23.0
    assert c.target(spec, T0, 19.0, "home", 7.0, 15.0).target == 19.0 and c.manual is None  # the schedule moved
    c.set_preset("away")
    assert c.target(spec, T0, 19.0, "home", 7.0, 15.0).target == 17.0
    c.presence_state = rm.ABSENT  # really absent now: a presence change ends the preset
    t = c.target(spec, T0, 19.0, "home", 7.0, 15.0)
    assert t.reason == "absent" and c.preset is None
    c.set_preset("home")
    assert c.target(spec, T0, 19.0, "home", 7.0, 15.0).target == 19.0
    c.enabled = False
    assert c.target(spec, T0, 19.0, "home", 7.0, 15.0).reason == "off"
    again = rm.RoomControl()
    again.restore(c.state())
    assert again.enabled is False and again.preset == "home"


# --- in the coordinator --------------------------------------------------------------------------------------------------
class _Hass:
    def __init__(self, states):
        self._states, self.calls, self.data = states, [], {}
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))
        self.services = SimpleNamespace(async_call=self._call)
        self.bus = SimpleNamespace(async_fire=lambda *a, **k: None)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def _state(value, last=T0, **attrs):
    return SimpleNamespace(state=str(value), attributes=attrs, last_reported=last)


def _coordinator(monkeypatch, states, conf, now=T0):
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    clock = {"now": now}
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: clock["now"])
    monkeypatch.setattr(coord_mod.dt_util, "utcnow", lambda: clock["now"])
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass, c.conf, c.mode = _Hass(states), conf, "active"
    c.cfg = model.HcConfig.from_mapping(conf)
    c.trv_targets, c.trv_cal, c.trv_info = trv.TrvTargets(), trv.TrvCalibration(), {}
    c._room_groups, c._trv_groups, c._specs = None, None, None
    c._started = now - timedelta(hours=1)
    c.room_demand, c.asking_rooms, c.data = trv.RoomDemand(), [], None
    return c, clock


ROOMS = [
    {"key": "nappali", "name": "Nappali", "sensors": ["sensor.n1", "sensor.n2"]},
    {"key": "konyha", "name": "Konyha", "sensors": ["sensor.k1", "sensor.k2"], "trvs": ["climate.konyha_trv"],
     "presence": ["sensor.phone_room", "binary_sensor.konyha_mozgas"], "absent_min": 15, "setback": 2},
    {"key": "halo", "name": "Háló", "sensors": ["sensor.h1"]},
]


def _states():
    return {"sensor.n1": _state(21.0), "sensor.n2": _state(22.0), "sensor.k1": _state(20.0),
            "sensor.k2": _state("unavailable"), "sensor.h1": _state(19.0),
            "climate.konyha_trv": _state("heat", temperature=21.0, current_temperature=21.0, target_temp_step=0.5,
                                         hvac_action="heating"),
            "sensor.phone_room": _state("Konyha", area_id="konyha"), "binary_sensor.konyha_mozgas": _state("off")}


def _decision(target=21.0, indoor=21.5, now=T0, output=True):
    return model.Decision(now, model.Reason.REGULATING, target, indoor, 0.0, output=output)


def test_trv_room_head_is_calibrated_against_the_group_mean_and_presence_moves_it(monkeypatch):
    states = _states()
    c, clock = _coordinator(monkeypatch, states, {"rooms": ROOMS, "leading_room": "nappali"})
    c._update_presence(T0)
    asyncio.run(c._apply_trvs(_decision()))
    k = c.room_states["konyha"]
    assert k["temperature"] == 20.0 and k["target"] == 21.0 and k["presence"] == "present"  # k2 dropped out
    assert c.trv_info["Konyha"]["heads"]["climate.konyha_trv"]["calibration"] == 1.0  # head 21 vs room 20
    assert [d for _, _, d in c.hass.calls] == [{"entity_id": "climate.konyha_trv", "temperature": 22.0}]
    # The occupant leaves the kitchen: 15 minutes later the room sets back by 2 °C
    states["sensor.phone_room"] = _state("Nappali", area_id="nappali")
    states["climate.konyha_trv"] = _state("heat", temperature=22.0, current_temperature=21.0, target_temp_step=0.5)
    for minutes in (1, 10):
        clock["now"] = T0 + timedelta(minutes=minutes)
        c._update_presence(clock["now"])
        asyncio.run(c._apply_trvs(_decision(now=clock["now"])))
    assert c.room_states["konyha"]["presence"] == "leaving" and len(c.hass.calls) == 1
    clock["now"] = T0 + timedelta(minutes=17)
    c._update_presence(clock["now"])
    asyncio.run(c._apply_trvs(_decision(now=clock["now"])))
    assert c.room_states["konyha"]["presence"] == "absent" and c.room_states["konyha"]["target"] == 19.0
    assert c.hass.calls[-1][2] == {"entity_id": "climate.konyha_trv", "temperature": 20.0}  # 19 + 1 calibration
    # motion in the kitchen: back at once
    states["binary_sensor.konyha_mozgas"] = _state("on")
    clock["now"] = T0 + timedelta(minutes=18)
    c._update_presence(clock["now"])
    asyncio.run(c._apply_trvs(_decision(now=clock["now"])))
    assert c.room_states["konyha"]["target"] == 21.0


def test_room_without_trv_follows_the_house_and_the_leading_room_is_the_host(monkeypatch):
    c, _ = _coordinator(monkeypatch, _states(), {"rooms": ROOMS, "leading_room": "nappali"})
    asyncio.run(c._apply_trvs(_decision(target=20.5)))
    h = c.room_states["halo"]
    assert h["target"] == 20.5 and h["reason"] == "house" and h["temperature"] == 19.0 and h["heating"] is True
    assert [s.key for s in c.other_rooms()] == ["konyha", "halo"]  # the leading room gets no climate of its own
    assert c.room_states["nappali"]["leading"] and c.room_states["nappali"]["temperature"] == 21.5
    assert c._room_readings(T0) == {"Konyha": 20.0, "Háló": 19.0}


def test_leading_room_group_gives_the_house_reading(monkeypatch):
    c, _ = _coordinator(monkeypatch, _states(), {"rooms": ROOMS, "leading_room": "nappali", "indoor_entity": "sensor.n1"})
    assert c._indoor_reading(T0).value == 21.5
    legacy, _ = _coordinator(monkeypatch, _states(), {"indoor_entity": "sensor.n1"})
    assert legacy._indoor_reading(T0).value == 21.0  # without saved rooms: the one thermometer as before


def test_household_away_gives_the_household_target(monkeypatch):
    own = [ROOMS[0], {**ROOMS[1], "mode": "own", "target_home": 22, "target_away": 16}]
    c, _ = _coordinator(monkeypatch, _states(), {"rooms": own, "leading_room": "nappali"})
    c.supervisor = SimpleNamespace(active_preset=lambda now: "away")
    asyncio.run(c._apply_trvs(_decision(target=17.0)))
    assert c.room_states["konyha"]["target"] == 16.0 and c.room_states["konyha"]["reason"] == "household_away"


def test_room_demand_only_where_allowed(monkeypatch):
    rooms = [ROOMS[0], {**ROOMS[1], "presence": [], "demand": True},
             {"key": "furdo", "name": "Fürdő", "trvs": ["climate.furdo_trv"], "demand": False}]
    states = {**_states(), "climate.furdo_trv": _state("heat", temperature=21, current_temperature=15.0, hvac_action="heating")}
    c, _ = _coordinator(monkeypatch, states, {"rooms": rooms, "leading_room": "nappali"})
    c.data = _decision()
    states["sensor.k1"] = _state(19.5)
    assert c._room_demand(T0) == []
    assert c._room_demand(T0 + timedelta(minutes=31)) == ["Konyha"]  # far below for half an hour; Fürdő not allowed


def test_manual_on_room_holds_until_presence_changes(monkeypatch):
    states = _states()
    c, clock = _coordinator(monkeypatch, states, {"rooms": ROOMS, "leading_room": "nappali"})
    c._update_presence(T0)
    asyncio.run(c._apply_trvs(_decision()))
    c._ctl("konyha").manual = 23.0
    asyncio.run(c._apply_trvs(_decision()))
    assert c.room_states["konyha"]["target"] == 23.0 and c.room_states["konyha"]["reason"] == "manual"
    states["sensor.phone_room"] = _state("Háló", area_id="halo")
    for minutes in (1, 20):
        clock["now"] = T0 + timedelta(minutes=minutes)
        c._update_presence(clock["now"])
        asyncio.run(c._apply_trvs(_decision(now=clock["now"])))
    assert c.room_states["konyha"]["target"] == 19.0 and c._ctl("konyha").manual is None


def test_legacy_cirko_runs_unchanged_and_gets_room_states(monkeypatch):
    states = {"sensor.ht_plus_temperature": _state(21.2), "sensor.konyha_th_temperature": _state(20.5),
              "sensor.haloszoba_th_temperature": _state(19.0),
              "climate.konyha_trv": _state("heat", temperature=21.0, current_temperature=22.0, target_temp_step=0.5)}
    c, _ = _coordinator(monkeypatch, states, dict(CIRKO))
    c._room_groups, c._trv_groups = dict(CIRKO_SENSORS), dict(CIRKO_TRVS)
    asyncio.run(c._apply_trvs(_decision()))
    # as 0.42.0: house target 21 + the head's 1.5 °C calibration → 22.5 on the head
    assert [d for _, _, d in c.hass.calls] == [{"entity_id": "climate.konyha_trv", "temperature": 22.5}]
    assert c.trv_info["Konyha"]["target"] == 21.0 and c.trv_info["Konyha"]["offset"] == 0.0
    assert set(c.room_states) == {"konyha", "haloszoba"}  # no area registry in the test: no leading room known
    assert c.room_states["haloszoba"]["reason"] == "house" and c.room_states["konyha"]["presence"] is None


def test_store_round_trip_keeps_room_controls(monkeypatch):
    c, _ = _coordinator(monkeypatch, _states(), {"rooms": ROOMS, "leading_room": "nappali"})
    c._ctl("konyha").manual = 22.5
    c._ctl("konyha").enabled = False
    data = {k: v.state() for k, v in c._ctls().items()}
    d, _ = _coordinator(monkeypatch, _states(), {"rooms": ROOMS, "leading_room": "nappali"})
    for k, v in data.items():
        d._ctl(k).restore(v)
    assert d._ctl("konyha").manual == 22.5 and d._ctl("konyha").enabled is False


# --- the wizard and HC info ----------------------------------------------------------------------------------------------
def test_wizard_rooms_drop_hc_climates_and_double_heads(monkeypatch):
    reg = SimpleNamespace(async_get=lambda e: SimpleNamespace(platform="hc_thermostat") if e == "climate.cirko_hc" else None)
    monkeypatch.setattr(importlib.import_module("homeassistant.helpers.entity_registry"), "async_get", lambda hass: reg)
    rooms = [{"key": "nappali", "name": "Nappali", "sensors": ["sensor.main"]},
             {"key": "konyha", "name": "Konyha", "trvs": ["climate.konyha_trv", "climate.cirko_hc"]},
             {"key": "halo", "name": "Háló", "trvs": ["climate.konyha_trv", "climate.halo_trv"]}]
    out = wizard.wizard_rooms(None, "pid", rooms, "nappali", "sensor.main")
    assert [r["trvs"] for r in out["rooms"]] == [[], ["climate.konyha_trv"], ["climate.halo_trv"]]
    assert wizard.wizard_rooms(None, "onoff", rooms, None, None) is None
    assert wizard.wizard_rooms(None, "tpi", None, None, None) is None
    assert wizard.wizard_rooms(None, "tpi", [], None, None)["room_trvs"] == []


class _Conn:
    def __init__(self):
        self.result = self.error = None
        self.user = SimpleNamespace(is_admin=True)  # 0.45.0: the info commands are admins only

    def send_result(self, _id, result):
        self.result = result

    def send_error(self, _id, code, message):
        self.error = code


def test_info_by_a_room_climate_returns_its_host_with_the_room(monkeypatch):
    host = SimpleNamespace(entry_id="e1", title="Cirkó HC", data={"role": "standalone"}, options={}, runtime_data=object())
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: [host]),
                           states=SimpleNamespace(get=lambda e: None))
    monkeypatch.setattr(info, "entry_of_entity", lambda hass, entity_id: "e1")
    monkeypatch.setattr(info, "room_of_entity", lambda hass, entity_id: "konyha" if entity_id == "climate.konyha_hc" else None)
    monkeypatch.setattr(info, "_instance", lambda hass, entry: {"entry_id": entry.entry_id})
    conn = _Conn()
    info.ws_info(hass, conn, {"id": 1, "type": "hc_thermostat/info", "entity_id": "climate.konyha_hc"})
    assert conn.result == {"entry_id": "e1", "via_room": "konyha"}
    conn = _Conn()
    info.ws_info(hass, conn, {"id": 2, "type": "hc_thermostat/info", "entity_id": "climate.cirko_hc"})
    assert conn.result == {"entry_id": "e1"}


def test_room_of_entity_reads_the_unique_id(monkeypatch):
    ents = {"climate.konyha_hc": SimpleNamespace(platform="hc_thermostat", config_entry_id="e1", unique_id="e1_room_konyha"),
            "climate.cirko_hc": SimpleNamespace(platform="hc_thermostat", config_entry_id="e1", unique_id="e1_thermostat"),
            "climate.other": SimpleNamespace(platform="x", config_entry_id="e9", unique_id="e9_room_a")}
    monkeypatch.setattr(importlib.import_module("homeassistant.helpers.entity_registry"), "async_get",
                        lambda hass: SimpleNamespace(async_get=lambda e: ents.get(e)))
    assert info.room_of_entity(None, "climate.konyha_hc") == "konyha"
    assert info.room_of_entity(None, "climate.cirko_hc") is None and info.room_of_entity(None, "climate.other") is None


def test_info_by_a_head_also_names_its_room():
    spec = rm.RoomSpec(key="konyha", name="Konyha", trvs=["climate.konyha_trv"])
    rt = SimpleNamespace(room_specs=lambda: ([spec], None), all_heads=lambda: ["climate.konyha_trv"])
    host = SimpleNamespace(entry_id="e1", data={}, options={}, runtime_data=rt)
    assert info.entry_of_trv([host], "climate.konyha_trv") == "e1"
    assert info.room_of_head(host, "climate.konyha_trv") == "konyha"


# --- the room climate ----------------------------------------------------------------------------------------------------
def test_room_without_trv_rejects_a_target(monkeypatch):
    climate = importlib.import_module("hc_thermostat.climate")
    exc = importlib.import_module("homeassistant.exceptions")
    c, _ = _coordinator(monkeypatch, _states(), {"rooms": ROOMS, "leading_room": "nappali"})
    c.config_entry = SimpleNamespace(entry_id="e1", title="Cirkó HC")
    ent = object.__new__(climate.HcRoomClimate)
    ent.coordinator, ent._key, ent._name, ent._trv = c, "halo", "Háló", False
    ent.hass = SimpleNamespace(config=SimpleNamespace(language="hu"))
    with pytest.raises(exc.ServiceValidationError, match="kazánon át"):
        asyncio.run(ent.async_set_temperature(temperature=23))
    trv_ent = object.__new__(climate.HcRoomClimate)
    trv_ent.coordinator, trv_ent._key, trv_ent._name, trv_ent._trv = c, "konyha", "Konyha", True

    async def _refresh():
        return None
    c.async_request_refresh = _refresh
    asyncio.run(trv_ent.async_set_temperature(temperature=23))
    assert c._ctl("konyha").manual == 23.0
    asyncio.run(trv_ent.async_set_preset_mode("away"))
    assert c._ctl("konyha").preset == "away" and c._ctl("konyha").manual is None

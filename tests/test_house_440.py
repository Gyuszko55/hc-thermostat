"""0.44.0: the house drawing of HC info – the info fields it reads (entity areas, areas and floors, sun, today's heat
energy from the recorder, pipe temperatures), the room order of the options flow."""

import asyncio
import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
info = importlib.import_module("hc_thermostat.info")
rm = importlib.import_module("hc_thermostat.core.room_model")
rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
config_flow = importlib.import_module("hc_thermostat.config_flow")

NOW = datetime(2026, 11, 11, 18, 0, tzinfo=timezone.utc)
ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"


def _st(value, **attrs):
    return SimpleNamespace(state=str(value), attributes=attrs)


class _Hass:
    def __init__(self, states):
        self._states, self.tasks = states, []
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))

    def async_create_task(self, coro, eager_start=False):
        self.tasks.append(coro)


def _entry(conf, specs=None):
    rt = SimpleNamespace(room_specs=lambda: (specs or [], None)) if specs is not None else SimpleNamespace()
    return SimpleNamespace(entry_id="e1", runtime_data=rt)


CONF = {"indoor_entity": "sensor.nappali", "window_entities": ["binary_sensor.ablak", "binary_sensor.bejarat"],
        "room_sensors": ["sensor.konyha"], "room_trvs": ["climate.konyha_trv"], "heat_energy_entity": "sensor.gaz",
        "return_temp_entity": "sensor.visszatero", "control": "pid"}
AREAS = {"sensor.nappali": "nappali", "binary_sensor.ablak": "nappali", "sensor.konyha": "konyha",
         "climate.konyha_trv": "konyha", "sensor.halo": "haloszoba", "binary_sensor.halo_mozgas": "haloszoba"}


def _registries(monkeypatch):
    monkeypatch.setattr(rooms_ha, "area_id_of", lambda hass, e: AREAS.get(e))
    areas = [SimpleNamespace(id="nappali", name="Nappali", floor_id="fsz", icon="mdi:sofa"),
             SimpleNamespace(id="haloszoba", name="Hálószoba", floor_id="emelet", icon=None)]
    floors = [SimpleNamespace(floor_id="fsz", name="Földszint", level=0), SimpleNamespace(floor_id="emelet", name="Emelet", level=1)]
    monkeypatch.setattr(importlib.import_module("homeassistant.helpers.area_registry"), "async_get",
                        lambda hass: SimpleNamespace(async_list_areas=lambda: areas))
    monkeypatch.setattr(importlib.import_module("homeassistant.helpers.floor_registry"), "async_get",
                        lambda hass: SimpleNamespace(async_list_floors=lambda: floors))


def test_house_fields_areas_floors_sun_pipes(monkeypatch):
    _registries(monkeypatch)
    info._today_cache.clear()
    hass = _Hass({"sun.sun": _st("below_horizon", elevation=-12.5, next_rising="2026-11-12T06:10:00+00:00"),
                  "sensor.visszatero": _st("38.46"), "sensor.gaz": _st("94.1", unit_of_measurement="m³")})
    specs = [rm.RoomSpec(key="haloszoba", name="Hálószoba", sensors=["sensor.halo"], presence=["binary_sensor.halo_mozgas"])]
    out = info._house(hass, _entry(CONF, specs), CONF)
    json.dumps(out)
    # every listed entity with an area, the rooms' own ones too; one without an area is left out
    assert out["entity_areas"] == {"sensor.nappali": "nappali", "binary_sensor.ablak": "nappali", "sensor.konyha": "konyha",
                                   "climate.konyha_trv": "konyha", "sensor.halo": "haloszoba",
                                   "binary_sensor.halo_mozgas": "haloszoba"}
    assert out["areas"][0] == {"area_id": "nappali", "name": "Nappali", "floor_id": "fsz", "icon": "mdi:sofa"}
    assert out["floors"] == [{"floor_id": "fsz", "name": "Földszint", "level": 0}, {"floor_id": "emelet", "name": "Emelet", "level": 1}]
    assert out["sun"]["state"] == "below_horizon" and out["sun"]["elevation"] == -12.5
    assert out["pipes"] == {"flow": None, "return": 38.46}
    # today's gas: nothing cached yet – a background read is scheduled, the panel does not wait
    assert out["heat_today"] is None and len(hass.tasks) == 1
    hass.tasks[0].close()


def test_house_fields_never_raise_without_registries(monkeypatch):
    monkeypatch.setattr(rooms_ha, "area_id_of", lambda hass, e: (_ for _ in ()).throw(RuntimeError("no registry")))
    monkeypatch.setattr(importlib.import_module("homeassistant.helpers.area_registry"), "async_get",
                        lambda hass: (_ for _ in ()).throw(RuntimeError("no registry")))
    out = info._house(_Hass({}), _entry({}), {"indoor_entity": "sensor.x"})
    assert out == {"entity_areas": {}, "areas": [], "floors": [], "sun": None, "heat_today": None, "pipes": None}


def _fake_recorder(monkeypatch, change=None, history=None):
    rec_mod = importlib.import_module("homeassistant.components.recorder")
    stats_mod = importlib.import_module("homeassistant.components.recorder.statistics")
    hist_mod = importlib.import_module("homeassistant.components.recorder.history")
    calls = []

    class _Rec:
        async def async_add_executor_job(self, fn, *args):
            return fn(*args)

    monkeypatch.setattr(rec_mod, "get_instance", lambda hass: _Rec())

    def stat(hass, start, end, sid, types, units):
        calls.append((start, sid, types))
        return {"change": change} if change is not None else {}

    monkeypatch.setattr(stats_mod, "statistic_during_period", stat)
    monkeypatch.setattr(hist_mod, "state_changes_during_period",
                        lambda hass, start, end, eid, **kw: {eid: [SimpleNamespace(state=v) for v in (history or [])]})
    return calls


def test_heat_today_from_statistics_since_local_midnight_cached(monkeypatch):
    info._today_cache.clear()
    calls = _fake_recorder(monkeypatch, change=2.371)
    hass = _Hass({"sensor.gaz": _st("94.1", unit_of_measurement="m³")})
    assert info.heat_today(hass, "sensor.gaz", NOW) is None
    asyncio.run(hass.tasks.pop())
    got = info.heat_today(hass, "sensor.gaz", NOW)
    assert got["value"] == 2.371 and got["unit"] == "m³" and got["source"] == "statistics"
    start, sid, types = calls[0]
    assert sid == "sensor.gaz" and types == {"change"} and start.hour == 0 and start.minute == 0
    assert not hass.tasks  # fresh for 5 minutes: no new read
    later = NOW.replace(minute=6)
    assert info.heat_today(hass, "sensor.gaz", later)["value"] == 2.371 and len(hass.tasks) == 1  # stale: refreshed,
    hass.tasks.pop().close()                                                                      # the old value shown
    tomorrow = NOW.replace(day=12)
    assert info.heat_today(hass, "sensor.gaz", tomorrow) is None  # a new day never shows yesterday's value
    hass.tasks.pop().close()


def test_heat_today_falls_back_to_the_history_and_survives_a_reset(monkeypatch):
    info._today_cache.clear()
    _fake_recorder(monkeypatch, change=None, history=["10.0", "11.5", "unavailable", "0.2", "1.0"])
    hass = _Hass({"sensor.e": _st("1.0", unit_of_measurement="kWh")})
    info.heat_today(hass, "sensor.e", NOW)
    asyncio.run(hass.tasks.pop())
    got = info.heat_today(hass, "sensor.e", NOW)
    assert got["source"] == "history" and abs(got["value"] - 2.3) < 1e-9 and got["unit"] == "kWh"  # 1.5 + 0.8


def test_heat_today_failure_is_not_stuck(monkeypatch):
    info._today_cache.clear()
    rec_mod = importlib.import_module("homeassistant.components.recorder")
    monkeypatch.setattr(rec_mod, "get_instance", lambda hass: (_ for _ in ()).throw(KeyError("recorder")))
    hass = _Hass({})
    info.heat_today(hass, "sensor.gaz", NOW)
    asyncio.run(hass.tasks.pop())
    assert info._today_cache["sensor.gaz"]["busy"] is False and info.heat_today(hass, "sensor.gaz", NOW) is None


def test_room_list_carries_the_area_and_keeps_the_option_order(monkeypatch):
    specs = [rm.RoomSpec(key="nappali", name="Nappali", area="nappali", sensors=["sensor.nappali"]),
             rm.RoomSpec(key="konyha", name="Konyha", area="konyha", sensors=["sensor.konyha"], trvs=["climate.konyha_trv"]),
             rm.RoomSpec(key="haloszoba", name="Hálószoba", area="haloszoba", sensors=["sensor.halo"])]
    rt = SimpleNamespace(room_specs=lambda: (specs, "nappali"), room_states={})
    monkeypatch.setattr(info, "_room_entities", lambda hass, entry: {})
    climate = importlib.import_module("hc_thermostat.climate")
    monkeypatch.setattr(climate, "room_title", lambda hass, s: s.name)
    out = info._room_list(_Hass({}), SimpleNamespace(entry_id="e1", runtime_data=rt))
    assert [(r["key"], r["area"], r["leading"]) for r in out] == [("nappali", "nappali", True), ("konyha", "konyha", False),
                                                                   ("haloszoba", "haloszoba", False)]


def test_position_field_is_translated_and_the_house_view_is_served():
    for lang in ("en", "hu"):
        tr = json.loads((ROOT / "translations" / f"{lang}.json").read_text())
        assert tr["options"]["step"]["room_details"]["title"]  # 0.46.0: the place is a field of the room's section
    js = (ROOT / "www" / "hc-house-view.js").read_text()
    assert "export function fromInfo" in js and 'customElements.define("hc-house-view"' in js
    panel = (ROOT / "www" / "hc-info-panel.js").read_text()
    assert "hc-house-view.js${new URL(import.meta.url).search}" in panel  # cache-busting with the panel's ?v=
    assert json.loads((ROOT / "manifest.json").read_text())["version"] in ("0.44.0", "0.44.1", "0.44.2", "0.44.3", "0.44.4", "0.44.5", "0.45.0", "0.46.0", "0.47.0", "0.48.0", "0.48.1", "0.48.2", "0.48.3")

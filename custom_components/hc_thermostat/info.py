"""Info panel (0.34.0): everything one HC instance knows, read only – for the "HC info" sidebar panel.

`hc_thermostat/info_list` lists the instances; `hc_thermostat/info` returns one instance's data: what it is (source,
system, control, role), the decision with its text, the inputs it decided on (with their age), the devices it reads
and switches (with their live state), presets and targets, every setting, the supervisor's inner state (regulator,
PWM, learning, heat need, season, fault…), boiler health, cost advice, rooms and TRVs, and the decision log.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, PRESETS
from .core.messages import explain
from .units import state_value_c


def jsonable(value: Any) -> Any:
    """Plain JSON from dataclasses, enums, datetimes, deques, sets and tuples (recursively)."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)) or type(value).__name__ == "deque":
        return [jsonable(v) for v in value]
    if isinstance(value, float):
        return round(value, 4)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


def _entities(hass, conf: dict) -> dict:
    """Every configured entity (keys ending in _entity / _entities, and the lists of zones, rooms, TRVs) with its
    live state, unit and the attributes that matter for a thermostat or a sensor."""
    out: dict = {}
    for key, value in conf.items():
        ids = value if isinstance(value, list) else [value]
        if not (key.endswith(("_entity", "_entities")) or key in ("room_sensors", "room_trvs")) or not ids:
            continue
        items = []
        for entity_id in ids:
            if not isinstance(entity_id, str) or "." not in entity_id:
                continue
            st = hass.states.get(entity_id)
            a = st.attributes if st is not None else {}
            items.append({"entity_id": entity_id, "name": a.get("friendly_name", entity_id),
                          "state": st.state if st is not None else None, "unit": a.get("unit_of_measurement"),
                          "last_changed": st.last_changed.isoformat() if st is not None else None,
                          **{k: a[k] for k in ("current_temperature", "temperature", "hvac_action", "percentage",
                                               "current_position", "min", "max") if k in a}})
        if items:
            out[key] = items
    return out


def _instance(hass, entry) -> dict:
    c = entry.runtime_data
    conf = dict(c.conf)
    role = conf.get("role", "standalone")
    base = {"entry_id": entry.entry_id, "title": entry.title, "role": role, "mode": c.mode,
            "heat_source": conf.get("heat_source"), "system": conf.get("system"), "control": conf.get("control"),
            "entities": _entities(hass, conf), "conf": jsonable(conf)}
    if role in ("central", "buffer"):
        d = c.data
        extra = {"decision": jsonable(d)}
        if role == "central":
            extra["zones"] = jsonable(c.zones)
            extra["config"] = jsonable(c.central.cfg)
            extra["state"] = {"output": c.central.output, "last_change": jsonable(c.central.last_change),
                              "pump_until": jsonable(c.central.pump_until),
                              "pump_last_run": jsonable(c.central.exercise.last_run),
                              "pump_exercise_next": jsonable(c.central.exercise.next_run(d.now)) if d and c.central.has_pump else None}
        else:
            extra["config"] = jsonable(c.buffer.cfg)
            extra["state"] = c.buffer.state()
        return {**base, **extra}
    sup, d = c.supervisor, c.data
    preset_modes = [p for p in PRESETS if p == "auto" or p in set(c.cfg.presets_enabled)]
    return {
        **base,
        "enabled": c.enabled,
        "decision": jsonable(d),
        "text_hu": explain(d, "hu", c.room_wording) if d else None,
        "text_en": explain(d, "en", c.room_wording) if d else None,
        "inputs": jsonable(getattr(c, "last_inputs", None)),
        "config": jsonable(c.cfg),
        "presets": {"modes": preset_modes, "current": sup.preset or "auto", "boosting": sup.boosting,
                    "preset_until": jsonable(sup.preset_until), "manual_target": sup.manual_target,
                    "targets": {k: getattr(c.cfg, k) for k in ("target_home", "target_night", "target_away",
                                                                 "target_vacation", "target_comfort", "target_eco",
                                                                 "target_cool", "frost_temp")},
                    "night": [c.cfg.night_start, c.cfg.night_end]},
        "state": jsonable(sup.state()),
        "live": {"season_on": sup.season_on, "fault": sup.fault, "boost_forecast": None,
                 "floor_temper_on": sup.temper_on if c.cfg.floor_temper else None,
                 "floor_limit": {"value": c.cfg.floor_limit, "from": c.cfg.floor_limit_from,
                                 "temper_offset": c.cfg.temper_offset} if c.cfg.floor_system else None,
                 "learned": {"afterheat": jsonable(sup.learner.afterheat(d.outdoor)) if d else None,
                             "minutes_per_degree": jsonable(sup.learner.minutes_per_degree(d.outdoor)) if d else None,
                             "tpi_coef_int": jsonable(sup.learner.tpi_coef_int), "tpi_offset": jsonable(sup.learner.tpi_offset)},
                 "loss_kw_per_k": jsonable(sup.heat_need.loss_kw_per_k),
                 "load": jsonable(sup.load.details(d.now)) if sup.load is not None and d else None},
        "health": {"state": c.health.state, **jsonable(c.health.attributes())} if getattr(c, "health", None) else None,
        "climate": _climate(hass, entry),
        "cost": jsonable(c.cost),
        "rooms": {"advice": jsonable(c.room_advice), "asking": list(c.asking_rooms), "trv": jsonable(c.trv_info)},
        "room_list": _room_list(hass, entry),  # 0.43.0: every room of this boiler with its state
        "zone": jsonable(c.zone),
        "sensor_problems": jsonable(getattr(c, "sensor_problems", None)),
        "actual": c.actual,
        "managed": jsonable(c.managed_info()) if hasattr(c, "managed_info") else None,  # 0.42.0
        "log": jsonable(list(c.log)[-60:]),
        **_house(hass, entry, conf),  # 0.44.0: what the house drawing needs (areas, sun, today's heat energy)
    }


def _room_list(hass, entry) -> list[dict]:
    c = entry.runtime_data
    if not hasattr(c, "room_specs"):
        return []
    specs, leading = c.room_specs()
    ids = _room_entities(hass, entry)
    from .climate import room_title
    out = []
    for s in specs:
        st = (getattr(c, "room_states", {}) or {}).get(s.key) or {}
        out.append(jsonable({**st, "key": s.key, "name": room_title(hass, s), "area": s.area, "leading": s.key == leading, "trv": bool(s.trvs),
                             "trvs": list(s.trvs), "sensors": list(s.sensors), "presence_sources": list(s.presence),
                             "absent_min": s.absent_min, "setback": s.setback, "mode": s.mode, "offset": s.offset,
                             "demand_allowed": s.demand, "entity_id": ids.get(s.key),
                             "own": {"home": s.target_home, "night": s.target_night, "away": s.target_away,
                                     "night_start": s.night_start, "night_end": s.night_end} if s.mode == "own" else None,
                             "names": {e: _name(hass, e) for e in [*s.sensors, *s.trvs, *s.presence]}}))
    return out


# --- 0.44.0: the house drawing ------------------------------------------------------------------------------------
TODAY_TTL_S = 300.0  # today's heat energy is read from the recorder at most every 5 minutes per entity
_today_cache: dict[str, dict] = {}  # entity_id -> {"value", "unit", "source", "day", "at", "busy"}


def _house(hass, entry, conf: dict) -> dict:
    """Read only and cheap: the area of every listed entity (room sensors, heads, windows…), the home's areas and
    floors (the drawing's rooms and storeys), the sun, today's heat energy (recorder, cached) and the pipe
    temperatures when sensors for them are configured. Never raises: a missing piece is left out."""
    out: dict = {}
    try:
        out["entity_areas"] = _entity_areas(hass, _listed_ids(entry, conf))
    except Exception:
        out["entity_areas"] = {}
    try:
        out["areas"], out["floors"] = _areas_floors(hass)
    except Exception:
        out["areas"], out["floors"] = [], []
    sun = hass.states.get("sun.sun")
    out["sun"] = {"state": sun.state, "elevation": sun.attributes.get("elevation"),
                  "next_rising": sun.attributes.get("next_rising"), "next_setting": sun.attributes.get("next_setting")} if sun is not None else None
    energy = conf.get("heat_energy_entity")
    out["heat_today"] = heat_today(hass, energy) if isinstance(energy, str) and "." in energy else None
    pipes = {}
    for key, conf_key in (("flow", "coil_temp_entity"), ("return", "return_temp_entity")):
        eid = conf.get(conf_key)
        st = hass.states.get(eid) if isinstance(eid, str) else None
        value = state_value_c(st) if st is not None else None  # 0.45.0: in °C
        pipes[key] = round(value, 2) if value is not None else None
    out["pipes"] = pipes if any(v is not None for v in pipes.values()) else None
    return out


def _listed_ids(entry, conf: dict) -> list[str]:
    """Every entity the instance lists: the configured ones and its rooms' thermometers, heads and presence sources."""
    ids: list[str] = []
    for key, value in conf.items():
        if key.endswith(("_entity", "_entities")) or key in ("room_sensors", "room_trvs"):
            ids += [v for v in (value if isinstance(value, list) else [value]) if isinstance(v, str) and "." in v]
    c = entry.runtime_data
    if hasattr(c, "room_specs"):
        try:
            for s in c.room_specs()[0]:
                ids += [*s.sensors, *s.trvs, *s.presence]
        except Exception:
            pass
    return list(dict.fromkeys(ids))


def _entity_areas(hass, ids: list[str]) -> dict[str, str]:
    """entity_id -> area id (the entity's own, else its device's); entities without an area are left out."""
    from .rooms_ha import area_id_of
    out = {}
    for entity_id in ids:
        try:
            area = area_id_of(hass, entity_id)
        except Exception:
            area = None
        if area:
            out[entity_id] = area
    return out


def _areas_floors(hass) -> tuple[list[dict], list[dict]]:
    from homeassistant.helpers import area_registry as ar, floor_registry as fr
    areas = [{"area_id": a.id, "name": a.name, "floor_id": a.floor_id, "icon": a.icon}
             for a in ar.async_get(hass).async_list_areas()]
    floors = [{"floor_id": f.floor_id, "name": f.name, "level": f.level} for f in fr.async_get(hass).async_list_floors()]
    return areas, floors


def heat_today(hass, entity_id: str, now: datetime | None = None) -> dict | None:
    """Today's heat energy (m³ or kWh since local midnight) of a meter: the cached value; a stale or missing one is
    refreshed in the background (recorder statistics `change`, else the state history), so the panel never waits."""
    from homeassistant.util import dt as dt_util
    now = now or dt_util.now()
    day = now.date().isoformat()
    st = hass.states.get(entity_id)
    unit = st.attributes.get("unit_of_measurement") if st is not None else None
    cached = _today_cache.get(entity_id)
    fresh = cached is not None and cached.get("day") == day and (now.timestamp() - cached.get("at", 0)) < TODAY_TTL_S
    busy = (cached or {}).get("busy") and now.timestamp() - (cached or {}).get("busy_at", 0) < 60  # a lost read: retry
    if not fresh and not busy:
        _today_cache[entity_id] = {**(cached or {}), "busy": True, "busy_at": now.timestamp()}
        try:
            hass.async_create_task(_refresh_today(hass, entity_id, now), eager_start=False)
        except TypeError:  # an older core without eager_start
            hass.async_create_task(_refresh_today(hass, entity_id, now))
        except Exception:
            _today_cache[entity_id] = {**(cached or {}), "busy": False}
    if cached is None or cached.get("day") != day or cached.get("value") is None:
        return None
    return {"entity_id": entity_id, "value": cached["value"], "unit": cached.get("unit") or unit,
            "source": cached.get("source"), "at": cached.get("at_iso")}


async def _refresh_today(hass, entity_id: str, now: datetime) -> None:
    try:
        await _read_today(hass, entity_id, now)
    except Exception:  # never stuck "busy": the next panel refresh tries again
        _today_cache[entity_id] = {**_today_cache.get(entity_id, {}), "busy": False, "day": now.date().isoformat(),
                                   "at": now.timestamp()}


async def _read_today(hass, entity_id: str, now: datetime) -> None:
    from homeassistant.util import dt as dt_util
    start = dt_util.start_of_local_day(now)
    value, source = None, None
    try:
        from homeassistant.components.recorder import get_instance
        rec = get_instance(hass)
    except Exception:
        rec = None
    if rec is not None:
        try:
            from homeassistant.components.recorder.statistics import statistic_during_period
            stats = await rec.async_add_executor_job(statistic_during_period, hass, start, None, entity_id, {"change"}, None)
            if stats and stats.get("change") is not None:
                value, source = float(stats["change"]), "statistics"
        except Exception:
            value = None
        if value is None:
            try:
                value = await rec.async_add_executor_job(_history_change, hass, entity_id, start, now)
                source = "history" if value is not None else None
            except Exception:
                value = None
    st = hass.states.get(entity_id)
    _today_cache[entity_id] = {"value": round(max(0.0, value), 3) if value is not None else None, "source": source,
                               "unit": st.attributes.get("unit_of_measurement") if st is not None else None,
                               "day": now.date().isoformat(), "at": now.timestamp(), "at_iso": now.isoformat(), "busy": False}


def _history_change(hass, entity_id: str, start: datetime, end: datetime) -> float | None:
    """A meter without statistics: its value now minus its value at the start of the day (state history)."""
    from homeassistant.components.recorder import history
    states = history.state_changes_during_period(hass, start, end, entity_id, no_attributes=True,
                                                 include_start_time_state=True).get(entity_id) or []
    values = []
    for s in states:
        try:
            values.append(float(s.state))
        except (TypeError, ValueError):
            continue
    if len(values) < 2:
        return 0.0 if values else None
    # a meter that was reset during the day: the sum of the rises
    return sum(max(0.0, b - a) for a, b in zip(values, values[1:]))


def _name(hass, entity_id: str) -> str:
    st = hass.states.get(entity_id)
    return st.attributes.get("friendly_name", entity_id) if st is not None else entity_id


def _room_entities(hass, entry) -> dict[str, str]:
    """Room key -> its climate entity id."""
    from homeassistant.helpers import entity_registry as er
    prefix = f"{entry.entry_id}_room_"
    try:
        return {e.unique_id[len(prefix):]: e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
                if e.domain == "climate" and (e.unique_id or "").startswith(prefix)}
    except Exception:
        return {}


def room_of_entity(hass, entity_id: str) -> str | None:
    """0.43.0: the room key of a room climate (its unique id is <entry_id>_room_<key>)."""
    from homeassistant.helpers import entity_registry as er
    try:
        e = er.async_get(hass).async_get(entity_id)
    except Exception:
        return None
    if e is None or e.platform != DOMAIN or not e.config_entry_id:
        return None
    prefix = f"{e.config_entry_id}_room_"
    return e.unique_id[len(prefix):] if (e.unique_id or "").startswith(prefix) else None


def _climate(hass, entry) -> dict | None:
    """The instance's own climate entity and the attributes it shows (flow request, valve exercise …)."""
    from homeassistant.helpers import entity_registry as er
    for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if e.domain == "climate" and "_room_" not in (e.unique_id or ""):
            st = hass.states.get(e.entity_id)
            return {"entity_id": e.entity_id, "state": st.state if st else None,
                    "attributes": jsonable(dict(st.attributes)) if st else {}}
    return None


def entry_of_entity(hass, entity_id: str) -> str | None:
    """The HC config entry behind a climate entity (the dial card opens the panel by entity)."""
    from homeassistant.helpers import entity_registry as er
    e = er.async_get(hass).async_get(entity_id)
    return e.config_entry_id if e is not None and e.platform == DOMAIN else None


def entry_of_trv(entries, entity_id: str) -> str | None:
    """0.42.0: the instance a TRV head belongs to (its `room_trvs`; 0.43.0: its rooms) – the dial card shows a TRV
    room by its head."""
    for e in entries:
        heads = _heads(e)
        if entity_id in heads:
            return e.entry_id
    return None


def _heads(entry) -> list[str]:
    c = getattr(entry, "runtime_data", None)
    if hasattr(c, "all_heads"):
        try:
            return c.all_heads()
        except Exception:
            pass
    return list({**entry.data, **entry.options}.get("room_trvs") or [])


def room_of_head(entry, head: str) -> str | None:
    c = getattr(entry, "runtime_data", None)
    if not hasattr(c, "room_specs"):
        return None
    try:
        return next((s.key for s in c.room_specs()[0] if head in s.trvs), None)
    except Exception:
        return None


def _trvs(hass, entry) -> list[dict]:
    out = []
    for head in _heads(entry):
        st = hass.states.get(head)
        out.append({"entity_id": head, "name": st.attributes.get("friendly_name", head) if st is not None else head})
    return out


def _loaded(hass) -> list:
    return [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None) is not None]


@websocket_api.require_admin  # 0.45.0: the HC info panel is admins only, so is its data
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info_list"})
@callback
def ws_info_list(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], [
        {"entry_id": e.entry_id, "title": e.title, "role": e.data.get("role", "standalone"),
         "heat_source": e.data.get("heat_source"), "system": e.data.get("system"),
         "control": {**e.data, **e.options}.get("control"), "mode": {**e.data, **e.options}.get("mode"),
         "trvs": _trvs(hass, e), "rooms": _rooms_brief(hass, e)}
        for e in _loaded(hass)])


def _rooms_brief(hass, entry) -> list[dict]:
    """0.43.0: the rooms under their host in the picker (the leading room is the host itself)."""
    c = entry.runtime_data
    if not hasattr(c, "room_specs"):
        return []
    try:
        ids = _room_entities(hass, entry)
        from .climate import room_title
        return [{"key": s.key, "name": room_title(hass, s), "trv": bool(s.trvs), "entity_id": ids.get(s.key)}
                for s in c.other_rooms()]
    except Exception:
        return []


@websocket_api.require_admin  # 0.45.0: the HC info panel is admins only, so is its data
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info", vol.Optional("entry_id"): str,
                                  vol.Optional("entity_id"): str, vol.Optional("room"): str})
@callback
def ws_info(hass: HomeAssistant, connection, msg) -> None:
    entity_id, via_trv, via_room = msg.get("entity_id"), None, msg.get("room")
    entry_id = msg.get("entry_id") or (entry_of_entity(hass, entity_id) if entity_id else None)
    if entry_id is not None and entity_id and not via_room:
        via_room = room_of_entity(hass, entity_id)  # 0.43.0: a room climate: its host, with the room
    if entry_id is None and entity_id and (entry_id := entry_of_trv(_loaded(hass), entity_id)):
        via_trv = entity_id  # a TRV head: its host instance
    entry = next((e for e in _loaded(hass) if e.entry_id == entry_id), None)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "no such HC instance")
        return
    result = _instance(hass, entry)
    if via_trv:
        result["via_trv"] = via_trv
        if (key := room_of_head(entry, via_trv)):
            result["via_room"] = key
    if via_room:
        result["via_room"] = via_room
    connection.send_result(msg["id"], result)

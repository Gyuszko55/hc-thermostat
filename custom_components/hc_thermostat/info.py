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
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PRESETS
from .core.matrix import timing_advice
from .core.messages import explain
from .core import week  # 0.72.0
from .units import finite, state_value_c


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


_SECRET_KEYS = ("guard_token", "guard_password")  # 0.78.2


def _instance(hass, entry) -> dict:
    c = entry.runtime_data
    # 0.78.2: the guard's token and the device password never leave Home Assistant (the panel shows only "set")
    conf = {k: ("********" if k in _SECRET_KEYS and v else v) for k, v in dict(c.conf).items()}
    role = conf.get("role", "standalone")
    base = {"entry_id": entry.entry_id, "title": entry.title, "role": role, "mode": c.mode,
            "heat_source": conf.get("heat_source"), "system": conf.get("system"), "control": conf.get("control"),
            "entities": _entities(hass, conf), "conf": jsonable(conf)}
    if role == "circuit":  # 0.54.0, shadow only
        return {**base, "mode": c.write.mode, "write": jsonable(c.write.info(c.data.now)) if c.data else {},
                "outputs": {"target": jsonable(c.out.info())}, "decision": jsonable(c.data), "zones": jsonable(c.zones),
                "config": jsonable(c.circuit.cfg), "buffer": jsonable(c.usable),
                "state": jsonable(c.circuit.state(c.data.now)) if c.data else {}}
    if role == "hp_coord":  # 0.55.0, shadow only
        return {**base, "mode": c.write.mode, "write": jsonable(c.write.info(c.data.now)) if c.data else {},
                "outputs": jsonable(c.outputs()), "decision": jsonable(c.data), "config": jsonable(c.hp.cfg),
                "inputs": jsonable(c.inputs(c.data.now)) if c.data else None, "offset": c.offset,
                "wood": jsonable(c.wood_info(c.data.now)) if c.data and hasattr(c, "wood_info") else None,
                "state": jsonable(c.hp.state(c.data.now)) if c.data else {},
                "water": c.water_temp() if hasattr(c, "water_temp") else None,  # 0.64.0
                "heat": jsonable(c.heat_info()) if hasattr(c, "heat_info") else None}  # 0.75.0
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
            extra["stock"] = jsonable(c.stock)  # 0.54.0: the stratified tank
            extra["trend"] = jsonable(c.trend)
            extra["circuits"] = [{"entry_id": e.entry_id, "title": e.title, "target": cc.data.target if cc.data else None,
                                  "demand_target": cc.data.demand_target if cc.data else None,  # 0.64.0
                                  "cap_state": cc.data.cap_state if cc.data else None,
                                  **jsonable(cc.usable or {})} for e, cc in c.circuits()]
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
                    "night": [c.cfg.night_start, c.cfg.night_end],
                    # 0.72.0: the weekly program (stored form) and its levels' temperatures
                    "week": week.to_raw(sup.week), "week_level": week.level_at(sup.week, dt_util.now()) if sup.week else None,
                    "levels": {lv: sup.level_target(lv) for lv in week.LEVELS}},
        "state": jsonable(sup.state()),
        "switch_log": list(c.switch_log.items)[-100:] if hasattr(c, "switch_log") else [],  # 0.79.0
        "live": {"season_on": sup.season_on, "fault": sup.fault, "boost_forecast": None,
                 "floor_temper_on": sup.temper_on if c.cfg.floor_temper else None,
                 "floor_limit": {"value": c.cfg.floor_limit, "from": c.cfg.floor_limit_from,
                                 "temper_offset": c.cfg.temper_offset} if c.cfg.floor_system else None,
                 "learned": {"afterheat": jsonable(sup.learner.afterheat(d.outdoor)) if d else None,
                             "minutes_per_degree": jsonable(sup.learner.minutes_per_degree(d.outdoor)) if d else None,
                             "tpi_coef_int": jsonable(sup.learner.tpi_coef_int), "tpi_offset": jsonable(sup.learner.tpi_offset)},
                 # 0.69.0: how the room answers its runs (measured, shown only) and a timing suggestion
                 "response": jsonable(sup.response.info()),
                 "timing": jsonable(timing_advice("floor_single" if c.cfg.floor_system else None, c.cfg.cycle_s,
                                                  c.cfg.valve_delay_s, c.cfg.min_on_s)
                                    if c.cfg.control in ("tpi", "pid") else None),
                 "loss_kw_per_k": jsonable(sup.heat_need.loss_kw_per_k),
                 # 0.50.0: the house model
                 "house": {"loss_w_k": jsonable(None if sup.heat_need.loss_kw_per_k is None
                                                else round(sup.heat_need.loss_kw_per_k * 1000, 1)),
                           "gains_kw": round(sup.heat_need.gains_kw, 2), "source": sup.heat_need.source,
                           "fit": jsonable(sup.heat_need.fit()), "tau_h": jsonable(sup.tau.tau_h),
                           "tau_source": sup.tau.source, "tau_stretches": len(sup.tau.samples),
                           "optimal_start": jsonable(sup.early_start),
                           "rating": jsonable(c.energy_rating()) if hasattr(c, "energy_rating") else None},
                 "load": jsonable(sup.load.details(d.now)) if sup.load is not None and d else None},
        "health": {"state": c.health.state, **jsonable(c.health.attributes())} if getattr(c, "health", None) else None,
        "climate": (clim := _climate(hass, entry)),
        "circuits": _circuits_of(hass, (clim or {}).get("entity_id")),  # 0.59.0: the mixing circuits this zone is in
        "cost": jsonable(c.cost),
        "rooms": {"advice": jsonable(c.room_advice), "asking": list(c.asking_rooms), "trv": jsonable(c.trv_info)},
        "room_list": _room_list(hass, entry),  # 0.43.0: every room of this boiler with its state
        "zone": jsonable(c.zone),
        "sensor_problems": jsonable(getattr(c, "sensor_problems", None)),
        "actual": c.actual,
        "managed": jsonable(c.managed_info()) if hasattr(c, "managed_info") else None,  # 0.42.0
        "log": jsonable(list(c.log)[-60:]),
        # 0.48.0: the measurements and their problems (core/measures.py)
        "measures": jsonable({k: v for k, v in (getattr(c, "measures", None) or {}).items() if k != "rooms"}),
        "measure_problems": list(getattr(c, "measure_problems", None) or []),
        **_house(hass, entry, conf),  # 0.44.0: what the house drawing needs (areas, sun, today's heat energy)
    }


def _circuits_of(hass, entity_id: str | None) -> list[dict]:
    """0.59.0: the mixing circuits that list this zone (a bathroom can be in a radiator and a floor circuit): their
    given-out flow targets are what the zone's water gets – not the zone's own flow request."""
    out: list[dict] = []
    if not entity_id:
        return out
    try:
        for e in _loaded(hass):
            conf = {**e.data, **e.options}
            if conf.get("role") != "circuit" or entity_id not in (conf.get("zone_entities") or []):
                continue
            c = e.runtime_data
            d = getattr(c, "data", None)
            out.append({"entry_id": e.entry_id, "title": e.title,
                        "kind": getattr(getattr(getattr(c, "circuit", None), "cfg", None), "circuit_kind", None)
                        or conf.get("circuit_kind") or "radiator",
                        "target": getattr(d, "target", None), "demand": getattr(d, "demand", None)})
    except Exception:
        return out
    return out


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
                             "windows": list(s.windows), "radiators": list(s.radiators), "humidity": list(s.humidity),
                             "measures": ((getattr(c, "measures", None) or {}).get("rooms") or {}).get(s.key),
                             "absent_min": s.absent_min, "setback": s.setback, "mode": s.mode, "offset": s.offset,
                             "demand_allowed": s.demand, "entity_id": ids.get(s.key), "heated": s.heated,
                             "own": {"home": s.target_home, "night": s.target_night, "away": s.target_away,
                                     "night_start": s.night_start, "night_end": s.night_end,
                                     "comfort": s.target_comfort, "eco": s.target_eco,  # 0.72.0
                                     "week": week.to_raw(s.week)} if s.mode == "own" else None,
                             "names": {e: _name(hass, e) for e in [*s.sensors, *s.trvs, *s.presence, *s.windows,
                                                                   *s.radiators, *s.humidity]}}))
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
        v = finite(s.state)
        if v is not None:
            values.append(v)
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
    # 0.79.2: an HC Lite instance (a Shelly script heats) has no HC decision data – the panels leave it out
    return [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None) is not None
            and e.data.get("role") != "lite"]


# --- 0.53.0: one house, several heat sources -----------------------------------------------------------------------
def _area(hass, entity_id) -> str | None:
    if not isinstance(entity_id, str) or "." not in entity_id:
        return None
    try:
        from .rooms_ha import area_id_of
        return area_id_of(hass, entity_id)
    except Exception:
        return None


def house_facts(hass, entry) -> "Facts":
    """What core/house.py needs of one instance: its rooms with their areas, the leading room's area (else the main
    thermometer's), the zone's area, its zones (central / buffer), the home name and the house setting."""
    from .core.house import Facts
    conf = {**entry.data, **entry.options}
    c = entry.runtime_data
    rooms: list[tuple[str, str | None]] = []
    leading_area = None
    if hasattr(c, "room_specs"):
        try:
            specs, leading = c.room_specs()
            rooms = [(s.key, s.area or (_area(hass, s.sensors[0]) if s.sensors else None)) for s in specs]
            leading_area = next((a for k, a in rooms if k == leading), None)
        except Exception:
            rooms = []
    if leading_area is None:
        leading_area = _area(hass, conf.get("indoor_entity"))
    zones = []
    for z in conf.get("zone_entities") or []:
        e = entry_of_entity(hass, z) if isinstance(z, str) else None
        if e:
            zones.append(e)
    return Facts(entry_id=entry.entry_id, title=entry.title, role=conf.get("role", "standalone"),
                 link=str(conf.get("house_link") or "auto"), home_name=str(conf.get("home_name") or ""),
                 rooms=tuple(rooms), leading_area=leading_area,
                 zone_area=_area(hass, conf.get("zone_temp_entity")) if conf.get("zone_temp_entity") else None,
                 zone_entries=tuple(zones),
                 feeds_from=tuple(t for t in (conf.get("circuit_buffer"), conf.get("hp_buffer")) if isinstance(t, str) and t))


def house_links(hass) -> dict:
    """entry id -> core.house.Link of every loaded instance; {} when it cannot be worked out (never raises)."""
    from .core.house import houses
    try:
        facts = []
        for e in _loaded(hass):
            try:
                facts.append(house_facts(hass, e))
            except Exception:
                continue
        return houses(facts)
    except Exception:
        return {}


def _house_brief(links: dict, entry_id: str) -> dict:
    link = links.get(entry_id)
    if link is None:
        return {"house": None, "house_members": []}
    if link.host != entry_id:
        return {"house": link.host, "house_area": link.area, "house_room": link.room, "house_why": link.why,
                "house_members": []}
    return {"house": None, "house_members": list(link.members)}


@websocket_api.require_admin  # 0.45.0: the HC info panel is admins only, so is its data
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info_list"})
@callback
def ws_info_list(hass: HomeAssistant, connection, msg) -> None:
    links = house_links(hass)  # 0.53.0: which instances the panel shows as one house
    connection.send_result(msg["id"], [
        {"entry_id": e.entry_id, "title": e.title, "role": e.data.get("role", "standalone"),
         "heat_source": e.data.get("heat_source"), "system": e.data.get("system"),
         "control": {**e.data, **e.options}.get("control"), "mode": {**e.data, **e.options}.get("mode"),
         "trvs": _trvs(hass, e), "rooms": _rooms_brief(hass, e), **_house_brief(links, e.entry_id)}
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
                for s in c.other_rooms() if s.heated]  # 0.53.0: a measured-only room has no thermostat to pick
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
    result.update(_house_brief(house_links(hass), entry.entry_id))  # 0.53.0
    if via_trv:
        result["via_trv"] = via_trv
        if (key := room_of_head(entry, via_trv)):
            result["via_room"] = key
    if via_room:
        result["via_room"] = via_room
    ai = getattr(entry.runtime_data, "ai", None)  # 0.71.0: the house's AI analysis (the leading instance keeps it)
    if ai is not None:
        result["ai_report"] = jsonable({**(ai.report or {}), "configured": bool(ai.ai_entity), "running": ai.running})
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/ai_report_run", vol.Required("entry_id"): str})
@websocket_api.async_response
async def ws_ai_report_run(hass: HomeAssistant, connection, msg) -> None:
    """0.71.0: make the house's AI analysis now (the panel's button)."""
    entry = next((e for e in _loaded(hass) if e.entry_id == msg["entry_id"]), None)
    ai = getattr(getattr(entry, "runtime_data", None), "ai", None)
    if ai is None:
        connection.send_error(msg["id"], "not_found", "no AI analysis for this instance")
        return
    from .ai_report import AiLimited
    try:
        report = await ai.async_run(manual=True)  # 0.78.2: rate limited
    except AiLimited as err:
        connection.send_error(msg["id"], "rate_limited", str(err))
        return
    connection.send_result(msg["id"], jsonable({**report, "configured": bool(ai.ai_entity), "running": False}))


# --- 0.72.0: the weekly program, edited on the panel -------------------------------------------------------------------
LEVEL_KEYS = {"comfort": "target_comfort", "home": "target_home", "sleep": "target_night", "eco": "target_eco"}


def week_options(options: dict, conf: dict, room: str | None, program, targets: dict | None, house: dict) -> dict:
    """The entry's new options with the weekly program (None: removed – the night window again) and the levels'
    temperatures of the instance (room None) or of one heated TRV room (which becomes an own-schedule room)."""
    from .core.room_model import FOLLOW, OWN, parse_rooms
    parsed = week.parse(program) if program else None
    raw = week.to_raw(parsed)
    temps = {lv: round(min(30.0, max(5.0, float(v))), 1) for lv, v in (targets or {}).items()
             if lv in LEVEL_KEYS and finite(v) is not None}
    out = dict(options)
    if room is None:
        if raw:
            out["week_program"] = raw
        else:
            out.pop("week_program", None)
        out.update({LEVEL_KEYS[lv]: v for lv, v in temps.items()})
        return out
    rooms = [dict(r) if isinstance(r, dict) else r for r in (conf.get("rooms") or [])]
    specs = parse_rooms(rooms)
    # parse_rooms keeps the order and skips nothing that is a dict with a name: match by position
    dicts = [r for r in rooms if isinstance(r, dict) and parse_rooms([r])]
    spec_raw = next((rd for sp, rd in zip(specs, dicts) if sp.key == room), None)
    spec = next((sp for sp in specs if sp.key == room), None)
    if spec is None or spec_raw is None:
        raise ValueError("unknown room")
    if not spec.trvs or not spec.heated:
        raise ValueError("only a room with its own TRV heads can have its own program")
    if spec.mode == FOLLOW and not raw:  # nothing to remove: it follows the house as before
        return out
    if spec.mode == FOLLOW:  # becomes an own-schedule room, its targets taken from the house's (plus its offset)
        spec_raw.update(mode=OWN, target_home=round(house["home"] + spec.offset, 1),
                        target_night=round(house["sleep"] + spec.offset, 1),
                        target_away=round(house["away"] + spec.offset, 1),
                        target_comfort=round(house["comfort"] + spec.offset, 1),
                        target_eco=round(house["eco"] + spec.offset, 1))
    if raw:
        spec_raw["week"] = raw
    else:
        spec_raw.pop("week", None)
    spec_raw.update({LEVEL_KEYS[lv]: v for lv, v in temps.items()})
    out["rooms"] = rooms
    return out


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/week_set", vol.Required("entry_id"): str,
                                  vol.Optional("room"): vol.Any(str, None), vol.Optional("program"): vol.Any(dict, None),
                                  vol.Optional("targets"): vol.Any(dict, None)})
@websocket_api.async_response
async def ws_week_set(hass: HomeAssistant, connection, msg) -> None:
    """0.72.0: save a weekly program (the instance's or a room's); the instance reloads with it."""
    entry = next((e for e in _loaded(hass) if e.entry_id == msg["entry_id"]), None)
    c = getattr(entry, "runtime_data", None)
    sup = getattr(c, "supervisor", None)
    if entry is None or sup is None:
        connection.send_error(msg["id"], "not_found", "no thermostat instance with this id")
        return
    cfg = c.cfg
    house = {"comfort": cfg.target_comfort, "home": cfg.target_home, "sleep": cfg.target_night,
             "eco": cfg.target_eco, "away": cfg.target_away}
    try:
        options = week_options(dict(entry.options), {**entry.data, **entry.options}, msg.get("room"),
                               msg.get("program"), msg.get("targets"), house)
    except ValueError as err:
        connection.send_error(msg["id"], "invalid", str(err))
        return
    hass.config_entries.async_update_entry(entry, options=options)  # the update listener reloads the instance
    connection.send_result(msg["id"], {"saved": True})


# --- 0.64.0: the heat pump target chart ---------------------------------------------------------------------------------
HP_HISTORY_MAX_H = 72


def _num_or_none(value) -> float | None:
    return finite(value)


def hp_series(states: dict, ids: dict) -> dict:
    """The chart's series from recorder states: raw / given-out target (HC's own sensors), what was sent (the target
    sensor's `sent`), what the unit reports (a climate's `temperature`, else the number's state) and the water."""
    def pts(entity_id, pick):
        out, last = [], object()
        for st in states.get(entity_id) or []:
            v = pick(st)
            if v == last:
                continue
            last = v
            ts = getattr(st, "last_updated", None) or getattr(st, "last_changed", None)
            if ts is not None:
                out.append([int(ts.timestamp() * 1000), v])
        return out

    def state_v(st):
        return None if st.state in ("unavailable", "unknown") else _num_or_none(st.state)

    rep = ids.get("reported")
    pick_rep = (lambda st: _num_or_none(st.attributes.get("temperature"))) if rep and rep.startswith("climate.") else state_v
    return {"raw": pts(ids.get("raw"), state_v) if ids.get("raw") else [],
            "target": pts(ids.get("target"), state_v) if ids.get("target") else [],
            "sent": pts(ids.get("target"), lambda st: _num_or_none(st.attributes.get("sent"))) if ids.get("target") else [],
            "reported": pts(rep, pick_rep) if rep else [],
            "water": pts(ids.get("water"), state_v) if ids.get("water") else [],
            # 0.75.0: the current COP (unavailable = None: the line breaks there)
            "cop": pts(ids.get("cop"), state_v) if ids.get("cop") else []}


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/hp_history", vol.Required("entry_id"): str,
                                  vol.Optional("hours", default=24): vol.All(vol.Coerce(float), vol.Range(min=1, max=HP_HISTORY_MAX_H))})
@websocket_api.async_response
async def ws_hp_history(hass: HomeAssistant, connection, msg) -> None:
    from homeassistant.helpers import entity_registry as er
    from homeassistant.util import dt as dt_util
    entry = next((e for e in _loaded(hass) if e.entry_id == msg["entry_id"]), None)
    if entry is None or {**entry.data, **entry.options}.get("role") != "hp_coord":
        connection.send_error(msg["id"], "not_found", "no such heat pump coordination instance")
        return
    conf = {**entry.data, **entry.options}
    reg = er.async_get(hass)
    ids = {"raw": reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_hp_raw"),
           "target": reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_hp_target"),
           "reported": conf.get("hp_target_entity") or None, "water": conf.get("hp_water_temp_entity") or None,
           "cop": reg.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_hp_cop")}
    wanted = [e for e in ids.values() if e]
    end = dt_util.utcnow()
    start = end - timedelta(hours=msg["hours"])
    states: dict = {}
    if wanted:
        try:
            from homeassistant.components.recorder import get_instance, history
            states = await get_instance(hass).async_add_executor_job(
                lambda: history.get_significant_states(hass, start, end, wanted, None, True, False, False, False))
        except Exception as err:  # no recorder, or the query failed: an empty chart, not an error page
            connection.send_result(msg["id"], {"start": int(start.timestamp() * 1000), "end": int(end.timestamp() * 1000),
                                               "ids": ids, "series": {}, "error": str(err)})
            return
    connection.send_result(msg["id"], {"start": int(start.timestamp() * 1000), "end": int(end.timestamp() * 1000),
                                       "ids": ids, "series": hp_series(states, ids)})

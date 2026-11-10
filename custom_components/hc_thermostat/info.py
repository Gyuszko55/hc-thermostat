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
                              "pump_until": jsonable(c.central.pump_until)}
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
                 "learned": {"afterheat": jsonable(sup.learner.afterheat(d.outdoor)) if d else None,
                             "minutes_per_degree": jsonable(sup.learner.minutes_per_degree(d.outdoor)) if d else None,
                             "tpi_coef_int": jsonable(sup.learner.tpi_coef_int), "tpi_offset": jsonable(sup.learner.tpi_offset)},
                 "loss_kw_per_k": jsonable(sup.heat_need.loss_kw_per_k),
                 "load": jsonable(sup.load.details(d.now)) if sup.load is not None and d else None},
        "health": {"state": c.health.state, **jsonable(c.health.attributes())} if getattr(c, "health", None) else None,
        "climate": _climate(hass, entry),
        "cost": jsonable(c.cost),
        "rooms": {"advice": jsonable(c.room_advice), "asking": list(c.asking_rooms), "trv": jsonable(c.trv_info)},
        "zone": jsonable(c.zone),
        "sensor_problems": jsonable(getattr(c, "sensor_problems", None)),
        "actual": c.actual,
        "log": jsonable(list(c.log)[-60:]),
    }


def _climate(hass, entry) -> dict | None:
    """The instance's own climate entity and the attributes it shows (flow request, valve exercise …)."""
    from homeassistant.helpers import entity_registry as er
    for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id):
        if e.domain == "climate":
            st = hass.states.get(e.entity_id)
            return {"entity_id": e.entity_id, "state": st.state if st else None,
                    "attributes": jsonable(dict(st.attributes)) if st else {}}
    return None


def entry_of_entity(hass, entity_id: str) -> str | None:
    """The HC config entry behind a climate entity (the dial card opens the panel by entity)."""
    from homeassistant.helpers import entity_registry as er
    e = er.async_get(hass).async_get(entity_id)
    return e.config_entry_id if e is not None and e.platform == DOMAIN else None


def _loaded(hass) -> list:
    return [e for e in hass.config_entries.async_entries(DOMAIN) if getattr(e, "runtime_data", None) is not None]


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info_list"})
@callback
def ws_info_list(hass: HomeAssistant, connection, msg) -> None:
    connection.send_result(msg["id"], [
        {"entry_id": e.entry_id, "title": e.title, "role": e.data.get("role", "standalone"),
         "heat_source": e.data.get("heat_source"), "system": e.data.get("system"),
         "control": {**e.data, **e.options}.get("control"), "mode": {**e.data, **e.options}.get("mode")}
        for e in _loaded(hass)])


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/info", vol.Optional("entry_id"): str,
                                  vol.Optional("entity_id"): str})
@callback
def ws_info(hass: HomeAssistant, connection, msg) -> None:
    entry_id = msg.get("entry_id") or (entry_of_entity(hass, msg["entity_id"]) if msg.get("entity_id") else None)
    entry = next((e for e in _loaded(hass) if e.entry_id == entry_id), None)
    if entry is None:
        connection.send_error(msg["id"], "not_found", "no such HC instance")
        return
    connection.send_result(msg["id"], _instance(hass, entry))

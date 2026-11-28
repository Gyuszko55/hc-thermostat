"""0.83.0: the go-live checklist – the facts from Home Assistant for core/readiness.py.

`async_check(hass, entry)` gathers what an instance stands on (its inputs and outputs with their states, another HC
instance or an automation on the same output, its shadow run, the life-safety stop, the local guard, its targets)
and returns the judged list in words; `static_check(hass, conf)` does the same from the settings alone, for an
instance the setup wizard is about to create. Read only: nothing here switches or changes a setting. The local
guard is asked for its status with a bodiless GET (no lease), at most every five minutes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (CONF_ACTUATOR, CONF_BOILER, CONF_BUFFER_BOTTOM, CONF_BUFFER_LOWER, CONF_BUFFER_TOP,
                    CONF_BUFFER_UPPER, CONF_CIRCUIT_BUFFER, CONF_CIRCUIT_OUTPUT, CONF_CONTROL, CONF_EXTERNAL,
                    CONF_FLAME, CONF_FLOOR, CONF_FLOW, CONF_HEAT_ENABLE, CONF_HP_BUFFER, CONF_HP_DEMAND_OUT,
                    CONF_HP_EXERCISE_OUT, CONF_HP_SUMMER_OUT, CONF_HP_SWITCH, CONF_HP_TARGET_OUT, CONF_INDOOR,
                    CONF_MODE, CONF_OUTDOOR, CONF_PRESENCE, CONF_PUMP, CONF_ROLE, CONF_ROOM_TRVS, CONF_ROOMS,
                    CONF_WINDOWS, CONF_ZONES, DOMAIN, MODE_SHADOW)
from .core.readiness import EntityFact, Facts, evaluate, render

_LOGGER = logging.getLogger(__name__)
_UNAVAILABLE = ("unavailable",)
_NO_WATCH: dict = {}
_HP_OUTS = (CONF_HP_TARGET_OUT, CONF_HP_SWITCH, CONF_HP_DEMAND_OUT, CONF_HP_SUMMER_OUT, CONF_HP_EXERCISE_OUT)


def _list(v) -> list[str]:
    if isinstance(v, str):
        return [v] if v else []
    return [x for x in (v or []) if isinstance(x, str) and x]


def _heads(conf: dict) -> list[str]:
    heads = _list(conf.get(CONF_ROOM_TRVS))
    for r in conf.get("rooms") or []:
        if isinstance(r, dict):
            heads += _list(r.get("trvs"))
    return list(dict.fromkeys(heads))


def _room_sensors(conf: dict) -> list[str]:
    out = _list(conf.get(CONF_ROOMS))
    for r in conf.get("rooms") or []:
        if isinstance(r, dict):
            out += _list(r.get("sensors"))
    return list(dict.fromkeys(out))


def outputs_of(conf: dict) -> list[tuple[str, str]]:
    """(setting, entity) of everything an instance writes to."""
    role, control = conf.get(CONF_ROLE, "standalone"), conf.get(CONF_CONTROL, "tpi")
    if role == "central":
        keys = [CONF_BOILER, CONF_PUMP, CONF_FLOW]
    elif role == "buffer":
        keys = [CONF_BOILER]
    elif role == "circuit":
        keys = [CONF_CIRCUIT_OUTPUT]
    elif role == "hp_coord":
        keys = list(_HP_OUTS)
    elif role == "lite":
        keys = []
    else:
        keys = ([] if control == "trv" else [CONF_ACTUATOR]) + [CONF_EXTERNAL, CONF_FLOW, CONF_HEAT_ENABLE]
    out = [(k, e) for k in keys for e in _list(conf.get(k))]
    if role in ("standalone", "zone"):
        out += [("trv_heads", h) for h in _heads(conf)]
    return out


def inputs_of(conf: dict) -> list[tuple[str, str, str]]:
    """(setting, entity, kind) of what an instance reads; kind "core" for what the decision stands on."""
    role, control = conf.get(CONF_ROLE, "standalone"), conf.get(CONF_CONTROL, "tpi")
    out: list[tuple[str, str, str]] = []

    def add(key, kind):
        out.extend((key, e, kind) for e in _list(conf.get(key)))

    if role == "buffer":
        add(CONF_BUFFER_TOP, "core")
        for k in (CONF_BUFFER_UPPER, CONF_BUFFER_LOWER, CONF_BUFFER_BOTTOM):
            add(k, "input")
    elif role in ("central", "circuit"):
        add(CONF_ZONES, "input")
        add(CONF_OUTDOOR, "core" if role == "circuit" else "input")
    elif role in ("standalone", "zone"):
        add(CONF_INDOOR, "core")
        add(CONF_OUTDOOR, "core" if control == "curve" else "input")
        out.extend(("room_sensors", e, "input") for e in _room_sensors(conf))
        for k in (CONF_FLOOR, CONF_WINDOWS, CONF_PRESENCE, CONF_FLAME):
            add(k, "input")
    return out


def missing_of(hass, conf: dict) -> list[str]:
    """What the instance needs and has not been given (setting keys)."""
    role, control = conf.get(CONF_ROLE, "standalone"), conf.get(CONF_CONTROL, "tpi")
    missing: list[str] = []
    if role in ("standalone", "zone"):
        if not conf.get(CONF_INDOOR) and control not in ("external", "ac", "trv") and not _room_sensors(conf):
            missing.append(CONF_INDOOR)
        if control == "curve" and not conf.get(CONF_OUTDOOR):
            missing.append(CONF_OUTDOOR)
        if not outputs_of(conf):
            missing.append("output")
    elif role == "central":
        if not _list(conf.get(CONF_ZONES)):
            missing.append(CONF_ZONES)
        if not conf.get(CONF_BOILER):
            missing.append(CONF_BOILER)
    elif role == "buffer":
        if not conf.get(CONF_BUFFER_TOP):
            missing.append(CONF_BUFFER_TOP)
    elif role == "circuit":
        if not conf.get(CONF_CIRCUIT_OUTPUT):
            missing.append(CONF_CIRCUIT_OUTPUT)
        if conf.get(CONF_CIRCUIT_BUFFER) and not _loaded(hass, conf.get(CONF_CIRCUIT_BUFFER)):
            missing.append(CONF_CIRCUIT_BUFFER)
    elif role == "hp_coord":
        if not any(conf.get(k) for k in _HP_OUTS):
            missing.append("output")
        if not conf.get(CONF_HP_BUFFER) or not _loaded(hass, conf.get(CONF_HP_BUFFER)):
            missing.append(CONF_HP_BUFFER)
    return missing


def _out_kind(key: str) -> str:
    return "trv" if key == "trv_heads" else "output"  # one head of many: a warning, not a blocker


def _loaded(hass, entry_id) -> bool:
    get = getattr(hass.config_entries, "async_get_entry", None)
    e = get(entry_id) if isinstance(entry_id, str) and get is not None else None
    return e is not None and getattr(e, "runtime_data", None) is not None


def _entity_fact(hass, key: str, entity_id: str, kind: str, now: datetime, problems: dict | None) -> EntityFact:
    """`problems`: the instance's own sensor watch (a room thermostat's); None for an instance without one, whose
    sensors are then judged by the age of their last report."""
    st = hass.states.get(entity_id)
    if st is None:
        return EntityFact(key, entity_id, kind, exists=False, available=False)
    if problems is None:
        problems = _NO_WATCH
    age = None
    if kind != "output" and entity_id.split(".")[0] == "sensor" and problems is _NO_WATCH:
        seen = getattr(st, "last_reported", None) or st.last_updated
        age = (now - seen).total_seconds()
    return EntityFact(key, entity_id, kind, available=st.state not in _UNAVAILABLE, age_s=age,
                      problem=problems.get(entity_id))


def _hc_conflicts(hass, entry_id: str | None, outs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    mine = {e for _, e in outs}
    found: list[tuple[str, str]] = []
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry_id:
            continue
        theirs = {e for _, e in outputs_of({**other.data, **other.options})}
        found += [(e, other.title) for e in sorted(mine & theirs)]
    return found


def _automations(hass, outs: list[tuple[str, str]]) -> list[tuple[str, list[str]]]:
    """The automations / scripts whose actions name an output – a trigger or a condition on it is no conflict."""
    found: dict[str, list[str]] = {}
    for domain, attr in (("automation", "action_script"), ("script", "script")):
        comp = (getattr(hass, "data", None) or {}).get(domain)
        for ent in list(getattr(comp, "entities", None) or []):
            try:
                refs = set(getattr(getattr(ent, attr, None), "referenced_entities", None) or ())
            except Exception:  # a broken automation must not stop the check
                continue
            st = hass.states.get(ent.entity_id)
            name = (st.attributes.get("friendly_name") if st else None) or ent.entity_id
            for _, e in outs:
                if e in refs:
                    found.setdefault(e, []).append(name)
    return sorted(found.items())


def _settings(c, conf: dict) -> dict | None:
    """0.85.0: the regulation settings in effect and the system's recommended values (core/readiness.setting_risks)."""
    cfg = getattr(c, "cfg", None)
    if cfg is None or not hasattr(cfg, "cycle_s"):
        return None
    from .core.matrix import default_timing
    g = lambda k: getattr(cfg, k, None)  # noqa: E731
    return {"pwm": cfg.control in ("tpi", "pid"), "curve": cfg.control == "curve",
            "rec": default_timing(conf.get("system") or "", conf.get("heat_source")),
            "cycle_s": g("cycle_s"), "min_on_s": g("min_on_s"), "min_off_s": g("min_off_s"),
            "floor": bool(g("floor_system")), "electric_floor": bool(g("floor_required")),
            "floor_limit": cfg.floor_limit if g("floor_system") else None,
            "heat_pump": bool(g("heat_pump")) and cfg.control in ("curve", "onoff"),
            "hp_min_on_s": g("hp_min_on_s"), "hp_min_off_s": g("hp_min_off_s"), "frost_temp": g("frost_temp"),
            "flow_max": g("flow_max"), "guard": bool(conf.get("guard_url")),
            "guard_every_s": g("guard_every_s"), "guard_ttl_s": g("guard_ttl_s")}


def _targets(c) -> tuple[dict | None, tuple[str, str] | None]:
    cfg = getattr(c, "cfg", None)
    if cfg is None or not hasattr(cfg, "target_home"):
        return None, None
    keys = ("target_home", "target_night", "target_away", "target_vacation", "frost_temp")
    return {k: float(getattr(cfg, k)) for k in keys}, (str(cfg.night_start or ""), str(cfg.night_end or ""))


def static_check(hass, conf: dict, lang: str | None = None, entry_id: str | None = None) -> dict:
    """From the settings alone (a new instance from the wizard): inputs, outputs, one writer."""
    now = dt_util.utcnow()
    outs = outputs_of(conf)
    ents = [_entity_fact(hass, k, e, kind, now, {}) for k, e, kind in inputs_of(conf)]  # no age: nothing ran yet
    ents += [_entity_fact(hass, k, e, _out_kind(k), now, {}) for k, e in outs]
    facts = Facts(role=conf.get(CONF_ROLE, "standalone"), control=conf.get(CONF_CONTROL), entities=ents,
                  missing=missing_of(hass, conf), hc_conflicts=_hc_conflicts(hass, entry_id, outs),
                  automations=_automations(hass, outs), static=True)
    return render(evaluate(facts), _lang(hass, lang))


def _lang(hass, lang: str | None) -> str:
    return lang or str(getattr(getattr(hass, "config", None), "language", "") or "en")


async def async_check(hass: HomeAssistant, entry, lang: str | None = None, conf: dict | None = None) -> dict:
    """`conf`: settings about to be saved with the same form (they count over the stored ones)."""
    c = getattr(entry, "runtime_data", None)
    conf = {**entry.data, **entry.options, **(conf or {})}
    role = conf.get(CONF_ROLE, "standalone")
    if role == "lite":  # HC Lite goes live on its own device – not judged here (yet)
        return {"ready": None, "blocks": 0, "warns": 0, "head": "", "items": [], "levels": {}}
    if c is None:  # not loaded (yet): from the settings alone
        return static_check(hass, conf, lang, entry.entry_id)
    now = dt_util.utcnow()
    mode = getattr(getattr(c, "write", None), "mode", None) or getattr(c, "mode", None) or conf.get(CONF_MODE)
    live = mode not in (None, MODE_SHADOW)
    problems = dict(c.sensor_problems or {}) if role in ("standalone", "zone") else None
    outs = outputs_of(conf)
    ents = [_entity_fact(hass, k, e, kind, now, problems) for k, e, kind in inputs_of(conf)]
    ents += [_entity_fact(hass, k, e, _out_kind(k), now, {}) for k, e in outs]

    since = getattr(c, "mode_since", None)
    shadow_h = None if live or since is None else max(0.0, (now - since).total_seconds() / 3600)
    errors = getattr(c, "step_errors", None)
    if errors is None:
        errors = getattr(getattr(c, "failsafe", None), "errors", 0) or 0
    day_ago = now - timedelta(days=1)
    faults = 0
    for row in list(getattr(c, "log", None) or []):
        try:
            if row.get("fault") and datetime.fromisoformat(row["time"]) >= day_ago:
                faults += 1
        except (TypeError, ValueError, KeyError, AttributeError):
            continue

    hub = getattr(c, "safety", None)
    safety = bool(hub.latch.tripped) if hub is not None and getattr(hub, "latch", None) is not None else None
    guard_sender = getattr(c, "guard", None)
    guard = None
    if guard_sender is not None:
        guard = await guard_sender.probe(now) if not live else (
            "ok" if guard_sender.link.problem(now) is None else guard_sender.link.problem(now))
    targets, night = _targets(c) if role in ("standalone", "zone") else (None, None)
    facts = Facts(role=role, live=live, control=conf.get(CONF_CONTROL), entities=ents,
                  missing=missing_of(hass, conf), hc_conflicts=_hc_conflicts(hass, entry.entry_id, outs),
                  automations=_automations(hass, outs), decided=getattr(c, "data", None) is not None,
                  shadow_h=shadow_h, step_errors=int(errors), faults_24h=faults, safety=safety, guard=guard,
                  guard_fits=role in ("standalone", "zone") and bool(conf.get(CONF_ACTUATOR))
                  and conf.get(CONF_CONTROL) != "trv",
                  targets=targets, night=night,
                  settings=_settings(c, conf) if role in ("standalone", "zone") else None)
    return render(evaluate(facts), _lang(hass, lang))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/readiness", vol.Required("entry_id"): str,
                                  vol.Optional("language"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_readiness(hass: HomeAssistant, connection, msg) -> None:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "no such HC instance")
        return
    connection.send_result(msg["id"], await async_check(hass, entry, msg.get("language")))

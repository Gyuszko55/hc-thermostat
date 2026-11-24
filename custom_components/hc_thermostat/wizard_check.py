"""0.78.2 (security review L1/L2): what the setup wizard's websocket commands take – the same as the panel's pickers
and the options flow's fields offer, nothing more.

The panel narrows every picker to the domains that fit (a relay: switch / input_boolean, a flow target: number /
input_number, ...) and the options flow gives every number its range; the websocket commands themselves took any
JSON before: an actuator could be a `lock.*` or a `light.*`, a cycle a string or NaN, a list any length. They are
admin only, so this is no privilege matter – it keeps a malformed request from making an instance that fails on
load or drives something it should not.
"""

from __future__ import annotations

import math
import re

from .const import (CONF_ACTUATOR, CONF_BOILER_POWER, CONF_COIL, CONF_DEMAND, CONF_DISCHARGE, CONF_ENERGY_FACTOR,
                    CONF_EXTERNAL, CONF_FAN, CONF_FLAME, CONF_FLOOR, CONF_FLOW, CONF_HEAT_ENABLE, CONF_HEAT_ENERGY,
                    CONF_HP_DEFROST, CONF_HP_DHW, CONF_INDOOR, CONF_OUTDOOR, CONF_POWER_AVAILABLE, CONF_PRESENCE,
                    CONF_RETURN, CONF_ROOMS, CONF_TARGET_SOURCE, CONF_WINDOWS)

ENTITY_ID = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")
MAX_LIST = 50  # entities in one multiple field, rooms / circuits in one request
MAX_NAME = 100  # a name, a prefix, a home name

_T = ("sensor",)
_RELAY = ("switch", "input_boolean")
_FLAG = ("binary_sensor", "sensor", "switch", "input_boolean")
# wizard/apply: key -> (allowed domains, multiple)
ENTITY_DOMAINS: dict[str, tuple[tuple[str, ...], bool]] = {
    CONF_INDOOR: (_T, False), CONF_OUTDOOR: (("sensor", "weather"), False),
    CONF_ACTUATOR: (_RELAY, False), CONF_EXTERNAL: (("climate",), False), "assist_climate": (("climate",), False),
    CONF_FLAME: (("binary_sensor",), False), CONF_BOILER_POWER: (_T, False), CONF_HEAT_ENERGY: (_T, False),
    CONF_FLOW: (("number", "input_number"), False), CONF_HEAT_ENABLE: (_RELAY, False),
    CONF_WINDOWS: (("binary_sensor",), True),
    CONF_PRESENCE: (("person", "binary_sensor", "sensor", "input_select"), True),
    CONF_ROOMS: (_T, True), CONF_FLOOR: (_T, False),
    CONF_TARGET_SOURCE: (("climate", "number", "input_number"), False),
    CONF_HP_DEFROST: (_FLAG, False), CONF_HP_DHW: (_FLAG, False),
    CONF_POWER_AVAILABLE: (("binary_sensor", "switch", "input_boolean"), False),
    CONF_DISCHARGE: (("switch", "input_boolean", "fan"), False), CONF_FAN: (("fan",), False),
    CONF_COIL: (_T, False), CONF_RETURN: (_T, False),
    CONF_DEMAND: (("binary_sensor", "input_boolean", "switch"), False),
}

_TIME = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d(:[0-5]\d)?$")
# wizard/apply settings: key -> (low, high) for numbers, "time", "bool", or a tuple of allowed strings
SETTING_RULES: dict[str, object] = {
    "cycle_s": (300, 7200), "min_on_s": (0, 3600), "min_off_s": (0, 3600), "keep_alive_s": (0, 600),
    "power_idle_w": (0, 500), "power_burn_w": (0, 5000), "boiler_power_kw": (0, 100), CONF_ENERGY_FACTOR: (0.01, 100),
    "target_home": (5, 30), "target_night": (5, 30), "target_away": (5, 30), "target_cool": (20, 30),
    "night_start": "time", "night_end": "time", "curve_slope": (0.1, 4), "flow_max": (25, 90), "flow_min": (15, 50),
    "room_tolerance": (0, 5), "ac_min_change_s": (120, 3600), "floor_max": (0, 40), "hp_min_on_s": (300, 7200),
    "hp_min_off_s": (120, 3600), "onoff_hysteresis": (0.1, 2), "floor_temper": "bool", "floor_temper_offset": (0, 8),
    "floor_temper_night": (0, 30), "floor_fallback": "bool", "floor_covering": "covering", "floor_probe": "probe",
    "valve_delay_s": (0, 1800),
}


class Invalid(ValueError):
    """A request value that does not fit; args[0] is the key."""


def entity(value, domains: tuple[str, ...], key: str) -> str:
    if not isinstance(value, str) or not ENTITY_ID.match(value) or value.split(".", 1)[0] not in domains:
        raise Invalid(key)
    return value


def entities(value, domains: tuple[str, ...], key: str) -> list[str]:
    items = value if isinstance(value, list) else [value]
    if len(items) > MAX_LIST:
        raise Invalid(key)
    return [entity(v, domains, key) for v in items]


def check_entities(ents: dict) -> dict:
    """The wizard's entities, every one in a domain its field allows (unknown keys are dropped by the caller)."""
    out = {}
    for key, value in ents.items():
        domains, multiple = ENTITY_DOMAINS.get(key, ((), False))
        out[key] = entities(value, domains, key) if multiple else entity(value, domains, key)
    return out


def number(value, lo: float, hi: float, key: str) -> float:
    if isinstance(value, bool):
        raise Invalid(key)
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise Invalid(key) from None
    if not math.isfinite(v) or not lo <= v <= hi:
        raise Invalid(key)
    return v


def check_settings(sets: dict) -> dict:
    from .core.floor import COVERINGS, PROBES
    out = {}
    for key, value in sets.items():
        rule = SETTING_RULES.get(key)
        if isinstance(rule, tuple):
            out[key] = number(value, rule[0], rule[1], key)
        elif rule == "time":
            if not isinstance(value, str) or not _TIME.match(value):
                raise Invalid(key)
            out[key] = value
        elif rule == "bool":
            if not isinstance(value, bool):
                raise Invalid(key)
            out[key] = value
        elif rule in ("covering", "probe"):
            allowed = ("none",) + tuple(COVERINGS) if rule == "covering" else tuple(PROBES)
            if value not in allowed:
                raise Invalid(key)
            out[key] = value
        else:
            raise Invalid(key)
    return out


def text(value, key: str, max_len: int = MAX_NAME) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > max_len:
        raise Invalid(key)
    return value


# --- wizard/system ----------------------------------------------------------------------------------------------------
_SYS_BUFFER = {"top": _T, "upper": _T, "lower": _T, "bottom": _T, "charge": ("sensor", "input_number"),
               "relay": _RELAY, "dhw_pump": _FLAG, "dhw_temp": _T, "dhw_heater": _FLAG}
_SYS_HP = {"running": ("sensor", "binary_sensor", "climate", "switch"), "switch": ("switch", "input_boolean", "climate"),
           "target": ("number", "input_number", "climate")}
_SYS_OUT = ("number", "input_number", "climate")


def _opt_entities(d: dict, spec: dict, where: str) -> None:
    for k, domains in spec.items():
        if d.get(k):
            entity(d[k], domains, f"{where}.{k}")


def check_system(msg: dict) -> None:
    """wizard/system: raises Invalid(key) on the first value that does not fit."""
    text(msg.get("home_name"), "home_name")
    text(msg.get("prefix"), "prefix")
    entity(msg.get("outdoor"), ("sensor", "weather"), "outdoor")
    buf = msg.get("buffer")
    if not isinstance(buf, dict):
        raise Invalid("buffer")
    _opt_entities(buf, _SYS_BUFFER, "buffer")
    for k, (lo, hi) in (("volume_l", (0, 20000)), ("base_temp", (10, 50))):
        if buf.get(k) is not None:
            number(buf[k], lo, hi, f"buffer.{k}")
    hp, wood = msg.get("heat_pump"), msg.get("wood")
    for name, d in (("heat_pump", hp), ("wood", wood)):
        if d is not None and not isinstance(d, dict):
            raise Invalid(name)
    if hp:
        _opt_entities(hp, _SYS_HP, "heat_pump")
    if wood:
        _opt_entities(wood, {"signal": _FLAG, "temp": _T}, "wood")
        for k, (lo, hi) in (("wood_on_above", (30, 95)), ("wood_off_below", (25, 90)), ("wood_confirm_s", (0, 3600))):
            if wood.get(k) is not None:
                number(wood[k], lo, hi, f"wood.{k}")
    circuits, rooms = msg.get("circuits") or [], msg.get("rooms") or []
    if not isinstance(circuits, list) or len(circuits) > MAX_LIST:
        raise Invalid("circuits")
    if not isinstance(rooms, list) or len(rooms) > MAX_LIST:
        raise Invalid("rooms")
    for c in circuits:
        if not isinstance(c, dict):
            raise Invalid("circuits")
        _opt_entities(c, {"output": _SYS_OUT, "pump": _FLAG, "flow": _T}, "circuit")
        for k, (lo, hi) in (("circuit_slope", (0.1, 4)), ("circuit_shift", (-10, 10)),
                            ("circuit_flow_min", (15, 60)), ("circuit_flow_max", (20, 90))):
            if c.get(k) is not None:
                number(c[k], lo, hi, f"circuit.{k}")
    for r in rooms:
        if not isinstance(r, dict) or not isinstance(r.get("circuits") or [], list):
            raise Invalid("rooms")
        if r.get("entry_id") is not None and not isinstance(r["entry_id"], str):
            raise Invalid("room.entry_id")
        text(r.get("name"), "room.name")
        _opt_entities(r, {"indoor": _T, "actuator": _RELAY}, "room")
        if r.get("valve_delay_s") is not None:
            number(r["valve_delay_s"], 0, 1800, "room.valve_delay_s")


def existing_zone_ok(hass, entry_id: str, domain: str) -> bool:
    """wizard/system: a room given as an existing instance must be an HC instance that can be a zone (not a central
    boiler, a buffer, a circuit or a heat pump coordination – nor another integration's entry)."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != domain:
        return False
    return {**entry.data, **entry.options}.get("role", "standalone") in ("standalone", "zone")

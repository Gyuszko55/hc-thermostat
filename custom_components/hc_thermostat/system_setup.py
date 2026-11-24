"""0.61.0 – one setup path for a buffer system (HC setup panel → "Buffer system"): the real system is described once –
the tank and its thermometers, the heat pump on its coil, wood (a signal or the boiler's thermometer), the radiator
and / or floor mixing circuit, the rooms with their thermometer, zone valve and the circuits they are on – and every
HC instance it needs is created in the right order and linked:

1. a zone instance per new room (role zone, "heat source with its own control", TPI on its valve; a room on both
   circuits is ONE zone – a bathroom with radiator and floor on one thermostat); existing zones can be picked instead;
2. the buffer tank (its zones: all rooms; its own relay is optional – here it is left empty, the heat pump
   coordination drives the heat pump);
3. one mixing circuit per circuit type, with its rooms (the bathroom in both), the tank and the PLC output if given;
4. the heat pump coordination (when there is a heat pump), on the tank, with its running signal, wood and outputs.

Everything starts in shadow mode and gets the same home name, so the HC info panel shows one house. Nothing is
switched or written. Websocket: hc_thermostat/wizard/system (admin only).
"""

from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import (CONF_ACTUATOR, CONF_BOILER, CONF_BUFFER_BOTTOM, CONF_BUFFER_CHARGE, CONF_BUFFER_LOWER,
                    CONF_BUFFER_TOP, CONF_BUFFER_UPPER, CONF_CIRCUIT_BUFFER, CONF_CIRCUIT_OUTPUT, CONF_CONTROL,
                    CONF_HEAT_SOURCE, CONF_HOME_NAME, CONF_HP_BUFFER, CONF_HP_RUNNING, CONF_HP_SWITCH,
                    CONF_HP_TARGET_OUT, CONF_INDOOR, CONF_MODE, CONF_OUTDOOR, CONF_ROLE, CONF_SYSTEM, CONF_WOOD,
                    CONF_WOOD_TEMP, CONF_ZONES, DOMAIN, MODE_SHADOW)
from .core.circuit import DEFAULTS as CIRCUIT_DEFAULTS
from .core.matrix import default_timing
from . import wizard_check as wc  # 0.78.2

_LOGGER = logging.getLogger(__name__)
KINDS = ("radiator", "floor")
CLIMATE_WAIT_S = 30.0

NAMES = {
    "hu": {"buffer": "Puffer", "radiator": "Radiátoros kör", "floor": "Padlófűtési kör", "hp": "Hőszivattyú koordináció"},
    "en": {"buffer": "Buffer tank", "radiator": "Radiator circuit", "floor": "Floor circuit", "hp": "Heat pump coordination"},
}


def zone_system(kinds) -> str:
    """The room's system from the circuits it is on: radiator, floor, or both (one thermostat for two emitters)."""
    ks = set(kinds or ())
    if ks >= {"radiator", "floor"}:
        return "mixed_mixing"
    return "floor_single" if "floor" in ks else "radiator_single"


def plan(msg: dict, lang: str = "hu") -> dict:
    """What would be created, from the request (pure; no Home Assistant). Raises ValueError on a missing piece."""
    names = NAMES["hu" if str(lang).startswith("hu") else "en"]
    prefix = str(msg.get("prefix") if msg.get("prefix") is not None else "HC").strip()
    home = str(msg.get("home_name") or "").strip()
    outdoor = msg.get("outdoor")
    if not outdoor:
        raise ValueError("missing_outdoor")
    buf = msg.get("buffer") or {}
    if not buf.get("top"):
        raise ValueError("missing_buffer_top")
    rooms = msg.get("rooms") or []
    if not rooms:
        raise ValueError("missing_rooms")
    circuits = [c for c in (msg.get("circuits") or []) if c.get("kind") in KINDS]
    kinds = {c["kind"] for c in circuits}
    title = lambda n: f"{prefix} {n}".strip()  # noqa: E731
    zones, seen = [], set()
    for r in rooms:
        rk = [k for k in (r.get("circuits") or []) if k in kinds]
        if r.get("entry_id"):
            zones.append({"existing": r["entry_id"], "circuits": rk})
            continue
        name = str(r.get("name") or "").strip()
        if not name or not r.get("indoor") or not r.get("actuator"):
            raise ValueError("room_incomplete")
        if name.casefold() in seen:
            raise ValueError("room_twice")
        seen.add(name.casefold())
        system = zone_system(rk)
        data = {"name": title(name), CONF_ROLE: "zone", CONF_HEAT_SOURCE: "external_heat", CONF_SYSTEM: system,
                CONF_CONTROL: "tpi", CONF_INDOOR: r["indoor"], CONF_ACTUATOR: r["actuator"], CONF_OUTDOOR: outdoor,
                **default_timing(system, "external_heat"), "valve_exercise": True, CONF_MODE: MODE_SHADOW}
        if r.get("valve_delay_s") is not None:
            data["valve_delay_s"] = float(r["valve_delay_s"])
        if home:
            data[CONF_HOME_NAME] = home
        zones.append({"data": data, "circuits": rk})
    tank = {"name": title(names["buffer"]), CONF_ROLE: "buffer", CONF_BUFFER_TOP: buf["top"], CONF_MODE: MODE_SHADOW,
            "buffer_volume_l": float(buf.get("volume_l") or 0), "buffer_base_temp": float(buf.get("base_temp") or 30.0)}
    for k, key in (("upper", CONF_BUFFER_UPPER), ("lower", CONF_BUFFER_LOWER), ("bottom", CONF_BUFFER_BOTTOM),
                   ("charge", CONF_BUFFER_CHARGE), ("relay", CONF_BOILER),
                   ("dhw_pump", "dhw_pump_entity"), ("dhw_temp", "dhw_temp_entity"),
                   ("dhw_heater", "dhw_heater_entity")):  # 0.63.0: hot water, drawn only
        if buf.get(k):
            tank[key] = buf[k]
    if home:
        tank[CONF_HOME_NAME] = home
    circs = []
    for c in circuits:
        d = {"name": title(names[c["kind"]]), CONF_ROLE: "circuit", "circuit_kind": c["kind"], CONF_OUTDOOR: outdoor,
             **CIRCUIT_DEFAULTS[c["kind"]], CONF_MODE: MODE_SHADOW}
        for k in ("circuit_slope", "circuit_shift", "circuit_flow_min", "circuit_flow_max"):
            if c.get(k) is not None:
                d[k] = float(c[k])
        if c.get("output"):
            d[CONF_CIRCUIT_OUTPUT] = c["output"]
        for k, key in (("pump", "circuit_pump_entity"), ("flow", "circuit_flow_entity")):  # 0.63.0: PLC readings, shown
            if c.get(k):
                d[key] = c[k]
        if home:
            d[CONF_HOME_NAME] = home
        circs.append(d)
    hp = None
    h = msg.get("heat_pump") or {}
    wood = msg.get("wood") or {}
    if h.get("enabled"):
        hp = {"name": title(names["hp"]), CONF_ROLE: "hp_coord", CONF_OUTDOOR: outdoor, CONF_MODE: MODE_SHADOW}
        for k, key in (("running", CONF_HP_RUNNING), ("switch", CONF_HP_SWITCH), ("target", CONF_HP_TARGET_OUT)):
            if h.get(k):
                hp[key] = h[k]
        if wood.get("signal"):
            hp[CONF_WOOD] = wood["signal"]
        elif wood.get("temp"):
            hp[CONF_WOOD_TEMP] = wood["temp"]
            for k in ("wood_on_above", "wood_off_below", "wood_confirm_s"):
                if wood.get(k) is not None:
                    hp[k] = float(wood[k])
            if hp.get("wood_off_below", 60.0) >= hp.get("wood_on_above", 65.0):
                raise ValueError("wood_order")
        if home:
            hp[CONF_HOME_NAME] = home
    return {"zones": zones, "buffer": tank, "circuits": circs, "hp": hp}


async def _climate_of(hass, entry_id: str, timeout: float = CLIMATE_WAIT_S) -> str | None:
    """The new instance's own climate entity, once its platform has registered it."""
    from homeassistant.helpers import entity_registry as er
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while True:
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry_id):
            if e.domain == "climate" and "_room_" not in (e.unique_id or ""):
                return e.entity_id
        if loop.time() >= end:
            return None
        await asyncio.sleep(0.5)


async def _create(hass, data: dict) -> str | None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "wizard"}, data=data)
    return getattr(result.get("result"), "entry_id", None)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "hc_thermostat/wizard/system",
    vol.Optional("home_name"): vol.Any(str, None), vol.Optional("prefix"): vol.Any(str, None),
    vol.Required("outdoor"): str, vol.Required("buffer"): dict, vol.Optional("heat_pump"): vol.Any(dict, None),
    vol.Optional("wood"): vol.Any(dict, None), vol.Optional("circuits", default=[]): list, vol.Required("rooms"): list,
    vol.Optional("dry_run", default=False): bool,
})
@websocket_api.async_response
async def ws_system(hass: HomeAssistant, connection, msg) -> None:
    try:  # 0.78.2 (security review): every value as the panel offers it; an existing room is an HC zone
        wc.check_system(msg)
        bad = [r["entry_id"] for r in msg["rooms"] if r.get("entry_id") and not wc.existing_zone_ok(hass, r["entry_id"], DOMAIN)]
        if bad:
            raise wc.Invalid("room.entry_id")
    except wc.Invalid as err:
        connection.send_error(msg["id"], "invalid_value", f"{err} does not fit")
        return
    try:
        p = plan(msg, hass.config.language or "hu")
    except ValueError as err:
        connection.send_error(msg["id"], str(err), str(err))
        return
    taken = {e.title.strip().casefold() for e in hass.config_entries.async_entries(DOMAIN)}
    new_names = [z["data"]["name"] for z in p["zones"] if "data" in z] + [p["buffer"]["name"]] \
        + [c["name"] for c in p["circuits"]] + ([p["hp"]["name"]] if p["hp"] else [])
    clash = [n for n in new_names if n.casefold() in taken]
    if clash:
        connection.send_error(msg["id"], "name_taken", ", ".join(clash))
        return
    if msg.get("dry_run"):
        connection.send_result(msg["id"], {"plan": p, "created": []})
        return
    created, zone_climate = [], []
    try:
        for z in p["zones"]:  # 1. the rooms
            entry_id = z.get("existing") or await _create(hass, z["data"])
            if entry_id is None:
                raise RuntimeError("zone_not_created")
            if "data" in z:
                created.append({"entry_id": entry_id, "title": z["data"]["name"], "role": "zone"})
            climate = await _climate_of(hass, entry_id)
            if climate is None:
                raise RuntimeError(f"zone_climate_missing:{entry_id}")
            zone_climate.append((climate, z["circuits"]))
        tank = {**p["buffer"], CONF_ZONES: [c for c, _ in zone_climate]}  # 2. the tank
        tank_id = await _create(hass, tank)
        if tank_id is None:
            raise RuntimeError("buffer_not_created")
        created.append({"entry_id": tank_id, "title": tank["name"], "role": "buffer"})
        for c in p["circuits"]:  # 3. the mixing circuits (a room on both circuits is in both)
            data = {**c, CONF_CIRCUIT_BUFFER: tank_id,
                    CONF_ZONES: [cl for cl, kinds in zone_climate if c["circuit_kind"] in kinds]}
            cid = await _create(hass, data)
            created.append({"entry_id": cid, "title": c["name"], "role": "circuit"})
        if p["hp"]:  # 4. the heat pump coordination
            hid = await _create(hass, {**p["hp"], CONF_HP_BUFFER: tank_id})
            created.append({"entry_id": hid, "title": p["hp"]["name"], "role": "hp_coord"})
    except Exception as err:  # noqa: BLE001 – report what was made, so it can be finished or removed by hand
        _LOGGER.exception("HC buffer system setup stopped")
        connection.send_result(msg["id"], {"created": created, "error": str(err)})
        return
    connection.send_result(msg["id"], {"created": created, "error": None})

"""Graphical setup wizard (sidebar panel "HC setup"): what can be worked out from the chosen devices is worked
out here, with the reason, and only the rest is asked.

Websocket commands (admin only):
- hc_thermostat/wizard/start   – heat sources, systems, the matrix, control types, existing instances,
                                  candidate entities and first suggestions;
- hc_thermostat/wizard/derive  – settings calculated from the source, system, control and the chosen devices;
- hc_thermostat/wizard/trv     – per TRV head: its room and the thermometers offered for it (0.42.0);
- hc_thermostat/wizard/rooms   – the home's areas with their thermometers, TRV heads and presence sources, the
                                  room-tracking sensors, and a first room list (0.43.0);
- hc_thermostat/wizard/apply   – create a new instance (always in shadow mode) or update an existing one.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import statistics

import voluptuous as vol

from homeassistant.components import panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTUATOR, CONF_BOILER_POWER, CONF_CONTROL, CONF_ENERGY_FACTOR, CONF_EXTERNAL, CONF_EXTRA_FACTOR,
    CONF_FLAME, CONF_FLOW, CONF_HEAT_ENABLE, CONF_HEAT_ENERGY, CONF_HEAT_SOURCE, CONF_INDOOR, CONF_MODE,
    CONF_OUTDOOR, CONF_PRESENCE, CONF_ROLE, CONF_ROOMS, CONF_SYSTEM, CONF_WINDOWS, DOMAIN, MODE_ACTIVE, MODE_SHADOW,
    CONF_FLOOR, CONF_TARGET_SOURCE, CONF_HP_DEFROST, CONF_HP_DHW, CONF_POWER_AVAILABLE, CONF_DISCHARGE, CONF_FAN,
    CONF_COIL, CONF_RETURN, CONF_DEMAND, CONF_ROOM_TRVS, CONF_ROOM_TRV_DEMAND, CONF_TRV_OFFSETS, CONF_TRV_SENSORS,
)
from .core.matrix import (
    SOURCES, SYSTEMS, cell, controls, curve_supported, default_curve, default_timing, electric_floor, own_control_supported,
)
from .core.model import HcConfig
from .info import ws_info, ws_info_list
from .units import climate_attrs_c
from .core.room_model import CONF_LEADING, CONF_ROOM_LIST, parse_rooms, rooms_options
from .rooms_ha import (
    climates_of_other_instances, excluded_climates, hc_climates,
    area_id_of, area_name, current_trv_sensors, room_specs_for, rooms_candidates, suggest_room_sensors,
    trv_sensor_candidates,
)

STATIC_URL = "/hc_thermostat_static"
PANEL_URL = "hc-wizard"
_OUTDOOR_WORDS = ("kulso", "külső", "kinti", "outdoor", "outside", "udvar", "kert")  # 0.45.0: not "bthome" (indoor ones too)
GAS_KWH_PER_M3 = 9.61  # typical Hungarian calorific value (MVM bills: 34.6 MJ/m³)
BOILER_EFFICIENCY = 0.9

# What the wizard may write: entity and setting keys (anything else in a request is ignored)
ENTITY_KEYS = (CONF_INDOOR, CONF_OUTDOOR, CONF_ACTUATOR, CONF_EXTERNAL, CONF_FLAME, CONF_BOILER_POWER, CONF_HEAT_ENERGY,
               CONF_FLOW, CONF_HEAT_ENABLE, CONF_WINDOWS, CONF_PRESENCE, CONF_ROOMS, "assist_climate", CONF_FLOOR,
               CONF_TARGET_SOURCE, CONF_HP_DEFROST, CONF_HP_DHW, CONF_POWER_AVAILABLE, CONF_DISCHARGE, CONF_FAN, CONF_COIL,
               CONF_RETURN, CONF_DEMAND)
SETTING_KEYS = ("cycle_s", "min_on_s", "min_off_s", "keep_alive_s", "power_idle_w", "power_burn_w", "boiler_power_kw",
                CONF_ENERGY_FACTOR, "target_home", "target_night", "target_away", "target_cool", "night_start",
                "night_end", "curve_slope", "flow_max", "flow_min", "room_tolerance", "ac_min_change_s", "floor_max",
                "hp_min_on_s", "hp_min_off_s", "onoff_hysteresis", "floor_temper", "floor_temper_offset", "floor_temper_night",
                "floor_fallback", "floor_covering", "floor_probe")


async def async_setup_wizard(hass: HomeAssistant) -> None:
    """Serve the panel and register it in the sidebar (admins only); safe to call once per HA start."""
    if hass.data.get(f"{DOMAIN}_wizard"):
        return
    hass.data[f"{DOMAIN}_wizard"] = True
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "www"), False)])
    await async_register_panels(hass)
    websocket_api.async_register_command(hass, ws_info_list)
    websocket_api.async_register_command(hass, ws_info)
    websocket_api.async_register_command(hass, ws_start)
    websocket_api.async_register_command(hass, ws_derive)
    websocket_api.async_register_command(hass, ws_apply)
    websocket_api.async_register_command(hass, ws_trv)
    websocket_api.async_register_command(hass, ws_rooms)


INFO_URL = "hc-info"
_PANELS = f"{DOMAIN}_panels"


async def async_register_panels(hass: HomeAssistant) -> None:
    """The two sidebar panels (admins only); again after async_remove_panels (0.45.0)."""
    if hass.data.get(_PANELS):
        return
    hass.data[_PANELS] = True
    version = await hass.async_add_executor_job(_version)
    await panel_custom.async_register_panel(
        hass, frontend_url_path=PANEL_URL, webcomponent_name="hc-wizard-panel",
        sidebar_title=panel_title(hass), sidebar_icon="mdi:auto-fix", module_url=f"{STATIC_URL}/hc-wizard-panel.js?v={version}",
        require_admin=True, config={})
    # info panel (0.34.0): everything an instance knows, read only
    await panel_custom.async_register_panel(
        hass, frontend_url_path=INFO_URL, webcomponent_name="hc-info-panel",
        sidebar_title="HC info", sidebar_icon="mdi:information-outline", module_url=f"{STATIC_URL}/hc-info-panel.js?v={version}",
        require_admin=True, config={})


@callback
def async_remove_panels(hass: HomeAssistant) -> None:
    """0.45.0: the last instance was deleted – no empty HC panels in the sidebar (the next instance brings them back)."""
    if not hass.data.pop(_PANELS, None):
        return
    from homeassistant.components import frontend
    for url in (PANEL_URL, INFO_URL):
        try:
            frontend.async_remove_panel(hass, url)
        except Exception:  # already gone
            pass


def panel_title(hass) -> str:
    """0.45.0: the sidebar title in Home Assistant's language (it is one text for every user)."""
    return "HC beállítás" if str(hass.config.language or "").startswith("hu") else "HC setup"


def _version() -> str:
    import json
    return json.loads((Path(__file__).parent / "manifest.json").read_text())["version"]


def _controls(source: str, system: str | None = None) -> list[str]:
    return controls(source, system)


def _st_info(hass, state) -> dict:
    a = state.attributes
    return {"id": state.entity_id, "name": a.get("friendly_name", state.entity_id), "state": state.state,
            "unit": a.get("unit_of_measurement"), "area": area_name(hass, area_id_of(hass, state.entity_id))}


def _candidates(hass) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {k: [] for k in ("temperature", "outdoor", "relay", "climate", "power", "energy",
                                                 "opening", "person", "binary")}
    for st in hass.states.async_all():
        dom, a = st.domain, st.attributes
        dc = a.get("device_class")
        info = None
        if dom == "sensor" and dc == "temperature":
            info = _st_info(hass, st)
            text = f"{st.entity_id} {info['name']} {info['area'] or ''}".lower()
            out["outdoor" if any(w in text for w in _OUTDOOR_WORDS) else "temperature"].append(info)
        elif dom == "weather":
            out["outdoor"].append(_st_info(hass, st))
        elif dom in ("switch", "input_boolean"):
            out["relay"].append(_st_info(hass, st))
        elif dom == "climate":
            if a.get("hc_mode") is None:  # not one of ours
                out["climate"].append(_st_info(hass, st))
        elif dom == "sensor" and dc == "power":
            out["power"].append(_st_info(hass, st))
        elif dom == "sensor" and (dc in ("gas", "energy") or a.get("state_class") in ("total", "total_increasing")):
            out["energy"].append(_st_info(hass, st))
        elif dom == "binary_sensor" and dc in ("door", "window", "opening", "garage_door"):
            out["opening"].append(_st_info(hass, st))
        elif dom == "person":
            out["person"].append(_st_info(hass, st))
        if dom == "binary_sensor":
            out["binary"].append(_st_info(hass, st))
    for v in out.values():
        v.sort(key=lambda x: (x["area"] or "~", x["name"]))
    return out


def _entries(hass) -> list[dict]:
    res = []
    for e in hass.config_entries.async_entries(DOMAIN):
        conf = {**e.data, **e.options}
        res.append({"entry_id": e.entry_id, "title": e.title, "role": conf.get(CONF_ROLE, "standalone"),
                    "heat_source": conf.get(CONF_HEAT_SOURCE), "system": conf.get(CONF_SYSTEM),
                    "control": conf.get(CONF_CONTROL), "mode": conf.get(CONF_MODE, MODE_SHADOW),
                    "conf": {k: v for k, v in conf.items() if k in ENTITY_KEYS + SETTING_KEYS},
                    # 0.42.0: the TRV heads as they work now (legacy calibration → the room thermometer it follows)
                    "trv": {CONF_ROOM_TRVS: list(conf.get(CONF_ROOM_TRVS) or []),
                            CONF_TRV_SENSORS: current_trv_sensors(hass, conf),
                            CONF_TRV_OFFSETS: dict(conf.get(CONF_TRV_OFFSETS) or {}),
                            CONF_ROOM_TRV_DEMAND: bool(conf.get(CONF_ROOM_TRV_DEMAND, False))},
                    # 0.43.0: the rooms as they work now (saved, or derived from the options above)
                    **_rooms_of(hass, conf)})
    return res


def _rooms_of(hass, conf: dict) -> dict:
    if conf.get(CONF_ROLE, "standalone") != "standalone" or conf.get(CONF_CONTROL) not in ("tpi", "pid"):
        return {"rooms": [], "leading_room": None}
    try:
        specs, leading = room_specs_for(hass, conf)
    except Exception:  # a broken registry must not hide the instance
        return {"rooms": [], "leading_room": None}
    return {"rooms": [s.as_dict() for s in specs], "leading_room": leading}


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "hc_thermostat/wizard/rooms",
                                  vol.Optional("indoor"): vol.Any(str, None)})
@callback
def ws_rooms(hass: HomeAssistant, connection, msg) -> None:
    """The areas with what can go into a room; `suggest`: a room per area that has a thermometer or a TRV head, the
    main thermometer's area leading."""
    cand = rooms_candidates(hass)
    indoor = msg.get("indoor")
    lead_area = area_id_of(hass, indoor) if indoor else None
    suggest = []
    if indoor and lead_area is None:
        # 0.44.2: a main thermometer without an area still has its room – the leading one (before: no leading room,
        # and a later leading room silently replaced the main thermometer)
        st = hass.states.get(indoor)
        name = (st.attributes.get("friendly_name") if st is not None else None) or indoor
        suggest.append({"key": "main", "name": str(name), "area": None, "sensors": [indoor], "trvs": [],
                        "mode": "follow", "offset": 0.0, "presence": [], "absent_min": 15.0, "setback": 2.0,
                        "demand": False})
        lead_area = "main"
    for a in cand["areas"]:
        # 0.44.2: only real heads that no other HC instance drives are suggested; outdoor areas are no rooms
        heads = [t["id"] for t in a["trvs"] if t.get("head") and not t.get("taken_by")]
        sensors = [s["id"] for s in a["sensors"] if not s.get("head")][:1]
        if a["area"] == lead_area:
            sensors = [indoor]
        elif a.get("outdoor") or not (sensors or heads):
            continue
        suggest.append({"key": a["area"], "name": a["name"], "area": a["area"], "sensors": sensors,
                        "trvs": heads, "mode": "follow", "offset": 0.0, "presence": [],
                        "absent_min": 15.0, "setback": 2.0, "demand": False})
    connection.send_result(msg["id"], {**cand, "suggest": suggest, "suggest_leading": lead_area})


def wizard_rooms(hass, control: str, rooms, leading, indoor: str | None, entry_id: str | None = None) -> dict | None:
    """The room options the wizard writes (tpi / pid only; None: leave them as they are). HC's own climates are no
    TRV heads; a head is in one room only."""
    if not isinstance(rooms, list) or control not in ("tpi", "pid"):
        return None
    from homeassistant.helpers import entity_registry as er
    try:
        reg = er.async_get(hass)
        ours = lambda e: (x := reg.async_get(e)) is not None and x.platform == DOMAIN
    except Exception:
        ours = lambda e: False
    from .rooms_ha import heads_of_other_instances
    others = heads_of_other_instances(hass, entry_id)
    seen: set[str] = set()
    clean = []
    for r in rooms:
        if not isinstance(r, dict):
            continue
        heads = [h for h in r.get("trvs") or [] if isinstance(h, str) and h.startswith("climate.") and not ours(h)
                 and h not in seen and h not in others]  # 0.44.2: nor a head another HC instance drives
        seen.update(heads)
        clean.append({**r, "trvs": heads})
    if not parse_rooms(clean):
        return {CONF_ROOM_LIST: [], CONF_LEADING: None, "room_sensors": [], "room_trvs": [], "trv_sensors": {},
                "trv_offsets": {}, "room_trv_demand": False}
    return rooms_options(clean, leading, indoor)


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "hc_thermostat/wizard/trv", vol.Required("heads"): [str]})
@callback
def ws_trv(hass: HomeAssistant, connection, msg) -> None:
    """Per head: its name, room (the key of its offset) and the thermometers offered for it."""
    out = {}
    for head in msg["heads"]:
        st = hass.states.get(head)
        out[head] = {"name": st.attributes.get("friendly_name", head) if st is not None else head,
                     **trv_sensor_candidates(hass, head)}
    connection.send_result(msg["id"], out)


def trv_options(control: str, trv: dict | None) -> dict | None:
    """The TRV options the wizard writes (tpi / pid only; None: leave them as they are). Every head not given a
    thermometer uses its own; the old switch trv_calibration is replaced by trv_sensors."""
    if trv is None or control not in ("tpi", "pid"):
        return None
    heads = [h for h in dict.fromkeys(trv.get(CONF_ROOM_TRVS) or []) if isinstance(h, str) and h.startswith("climate.")]
    sensors = {h: v for h, v in (trv.get(CONF_TRV_SENSORS) or {}).items()
               if h in heads and isinstance(v, str) and v.startswith("sensor.")}
    offsets = {}
    for room, v in (trv.get(CONF_TRV_OFFSETS) or {}).items():
        try:
            if (value := max(-5.0, min(5.0, float(v)))) != 0.0:
                offsets[str(room)] = value
        except (TypeError, ValueError):
            continue
    return {CONF_ROOM_TRVS: heads, CONF_TRV_SENSORS: sensors, CONF_TRV_OFFSETS: offsets,
            CONF_ROOM_TRV_DEMAND: bool(trv.get(CONF_ROOM_TRV_DEMAND, False)) and bool(heads)}


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "hc_thermostat/wizard/start"})
@callback
def ws_start(hass: HomeAssistant, connection, msg) -> None:
    matrix = {f"{sy}|{so}": {"status": (c := cell(sy, so)).status.value, "hu": c.text_hu, "en": c.text_en}
              for sy in SYSTEMS for so in SOURCES}
    cand = _candidates(hass)
    suggest = {
        CONF_OUTDOOR: next((c["id"] for c in cand["outdoor"] if c["id"].startswith("sensor.")), None),
        CONF_PRESENCE: [c["id"] for c in cand["person"]],
    }
    connection.send_result(msg["id"], {
        "sources": list(SOURCES), "systems": list(SYSTEMS), "matrix": matrix,
        "controls": {so: _controls(so) for so in SOURCES},
        "controls_fan_coil": {so: _controls(so, "fan_coil") for so in SOURCES}, "entries": _entries(hass),
        "candidates": cand, "suggest": suggest, "language": hass.config.language,
        # 0.45.0: the climates a thermostat / AC / TRV picker must not offer: HC's own, and per instance the ones
        # another instance drives ("" = a new instance)
        "hc_climates": hc_climates(hass),
        "taken_climates": {e.entry_id: sorted(climates_of_other_instances(hass, e.entry_id))
                           for e in hass.config_entries.async_entries(DOMAIN)} | {"": sorted(climates_of_other_instances(hass))},
        "default_name": _free_name(hass),
    })


def _free_name(hass, base: str = "HC Thermostat") -> str:
    """0.45.0: a default name no instance has yet."""
    titles = {str(e.title).strip().casefold() for e in hass.config_entries.async_entries(DOMAIN)}
    name, n = base, 1
    while name.casefold() in titles:
        n += 1
        name = f"{base} {n}"
    return name


def _power_levels(hass, entity_id: str) -> tuple[float, float, int] | None:
    """Idle and burning draw from the last two days of a power sensor: a burner or compressor shows two levels."""
    from homeassistant.components.recorder import history

    start = dt_util.utcnow() - timedelta(days=2)
    states = history.state_changes_during_period(hass, start, entity_id=entity_id, no_attributes=True).get(entity_id, [])
    values = sorted(v for s in states if (v := _num(s.state)) is not None)
    if len(values) < 20:
        return None
    lo = statistics.median(values[: max(1, len(values) // 3)])
    hi = values[int(len(values) * 0.95)]
    if hi < lo * 3 or hi - lo < 15:
        return None
    return round(max(lo * 2, lo + 5), 0), round(lo + (hi - lo) * 0.8, 0), len(values)


def _r1(v):
    return round(v, 1) if isinstance(v, (int, float)) else v


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "hc_thermostat/wizard/derive",
    vol.Required("heat_source"): str, vol.Required("system"): str, vol.Required("control"): str,
    vol.Optional("entities", default={}): dict,
    vol.Optional("language"): vol.Any(str, None),  # 0.45.0: the user's language (the panel's hass.language)
})
@websocket_api.async_response
async def ws_derive(hass: HomeAssistant, connection, msg) -> None:
    source, system, control, ent = msg["heat_source"], msg["system"], msg["control"], msg["entities"]
    lang = "hu" if str(msg.get("language") or hass.config.language or "en").startswith("hu") else "en"
    T = (lambda hu, en: hu) if lang == "hu" else (lambda hu, en: en)
    items: list[dict] = []

    def add(key, value, why, unit=None, editable=True, options=None):
        # options: a choice, as [value, label hu, label en] lists
        items.append({"key": key, "value": value, "why": why, "unit": unit, "editable": editable,
                      **({"options": options} if options else {})})

    base = HcConfig()
    if control in ("tpi", "pid"):
        t = default_timing(system, source)
        floor = system.startswith("floor")
        room = system == "room_unit"
        efloor = electric_floor(system, source)
        why = T("elektromos padlófűtés: 30 perces ciklus, 5 perces minimum (az esztrich lassan egyenlít ki)" if efloor
                else "padlófűtés: lassú, hosszú ciklus" if floor else "elektromos fűtő: gyorsan melegszik, 10 perces ciklus, 2 perces minimum (kíméli a relét/dugaljat)" if room
                else "radiátor: 15 perces ciklus, 5 perces minimális égés",
                "electric floor heating: 30 minute cycle, 5 minute minimum (the screed evens out slowly)" if efloor
                else "floor heating: slow, long cycle" if floor else "electric heater: warms quickly, 10 minute cycle, 2 minute minimum (spares the relay/plug)" if room
                else "radiators: 15 minute cycle, 5 minute minimum burn")
        add("cycle_s", t["cycle_s"], why, "s")
        add("min_on_s", t["min_on_s"], why, "s")
        add("min_off_s", t["min_off_s"], why, "s")
    if system.startswith("floor") and control in ("tpi", "pid", "onoff", "curve"):
        # floor limit (0.37.0): 0 = by the covering and where the sensor sits
        add("floor_max", 0.0,
            T("padlóhőfok-limit: e fölött nem fűt; 0 = a burkolat és a szenzor helye szerint (burkolat nélkül elektromos padlónál 27 °C, vizes padlónál 29 °C)",
              "floor limit: no heat above it; 0 = by the covering and the probe position (without a covering: 27 °C electric, 29 °C water floor)"), "°C")
        add("floor_covering", "none", T("a padló burkolata: ebből jön a limit és a temperálás eltérése",
                                        "the floor covering: gives the limit and the tempering offset"),
            options=[["none", "Nincs megadva", "Not set"], ["tiles", "Csempe", "Tiles"], ["laminate", "Laminált", "Laminate"],
                     ["wood", "Fa/parketta", "Wood / parquet"], ["vinyl", "Vinyl", "Vinyl"], ["carpet", "Szőnyeg", "Carpet"]])
        add("floor_probe", "surface", T("hol van a padlószenzor: mélyebben melegebbet mér, ott magasabb a limit (elektromos padlónál mindig a burkolat alatti érték); a mélyebb helyek határa becslés – fa, parketta, laminált alatt burkolat alatti szenzor ajánlott",
                                        "where the floor sensor sits: deeper it reads warmer, so the limit is higher (an electric floor always uses the under-covering value); the deeper limits are estimates – under wood, parquet, laminate a sensor right under the covering is recommended"),
            options=[["surface", "A burkolat alatt", "Under the covering"], ["screed", "Az esztrichben, a csövek között (becslés)", "In the screed, between the pipes (estimate)"],
                     ["above_pipe", "Cső fölött (becslés)", "Above a supply pipe (estimate)"]])
    if system.startswith("floor") and control in ("tpi", "pid", "onoff"):
        # floor tempering (0.35.0): comfort, off by default
        add("floor_temper", False, T("padlótemperálás: a padló meleg marad akkor is, ha a helyiség már elég meleg (padlószenzor kell)",
                                     "floor tempering: the floor stays warm even when the room is warm enough (needs a floor sensor)"))
        add("floor_temper_offset", 0.0, T("a padló célja a helyiség célja fölött; 0 = a burkolat szerint (csempe 2 °C, más 3 °C, nincs megadva 2 °C)",
                                          "the floor target above the room target; 0 = by the covering (tiles 2 °C, others 3 °C, not set 2 °C)"), "°C")
        add("floor_temper_night", 0.0, T("a padló célja éjjel / alvás presetben; 0 = mint nappal",
                                         "the floor target at night / in the sleep preset; 0 = as by day"), "°C")
        add("floor_fallback", True, T("ha a helyiséghőmérő kiesik, a padlószenzor szerint tartja a padlót (vakon fűtés helyett)",
                                      "if the room thermometer is lost, the floor is held by the floor sensor (instead of blind heat)"))
    if source == "heat_pump" and control in ("curve", "onoff"):
        why = T("hőszivattyú: hosszú futások, ritka indítás (kíméli a kompresszort)", "heat pump: long runs, few starts (spares the compressor)")
        add("hp_min_on_s", base.hp_min_on_s, why, "s")
        add("hp_min_off_s", base.hp_min_off_s, why, "s")
        if control == "onoff":
            add("onoff_hysteresis", base.onoff_hysteresis, T("ennyivel a cél alatt indul, a cél fölött áll le",
                "starts this far below the target, stops above it"), "°C")
    if control == "curve":
        c = default_curve(system, source)
        why = T("kezdő fűtési görbe a rendszer és a hőforrás szerint", "starting heating curve for this system and source")
        add("curve_slope", c["curve_slope"], why)
        add("flow_max", c["flow_max"], why, "°C")
        add("flow_min", c["flow_min"], why, "°C")
    if control == "ac" and (st := hass.states.get(ent.get(CONF_EXTERNAL) or "")):
        a = climate_attrs_c(hass, st.attributes)  # 0.45.0: a °F unit shown in °C
        add("unit_step", round(a.get("target_temp_step") or 1, 2), T("a klíma lépésköze (a készülékből)", "the unit's step (from the device)"), "°C", False)
        add("unit_range", f"{_r1(a.get('min_temp'))}–{_r1(a.get('max_temp'))}", T("a klíma határai: ezen kívül nem állítható, a határon a HC szünetet tart",
            "the unit's limits: the HC pauses when pinned there"), "°C", False)
        add("target_cool", 26.0, T("nyári hűtési cél (évszak szerint)", "summer cooling target (by season)"), "°C")
        add("ac_min_change_s", 600, T("legfeljebb 10 percenként változtat a klíma célján (kompresszorkímélés)",
            "at most one setpoint change per 10 minutes (spares the compressor)"), "s")
    if (pw := ent.get(CONF_BOILER_POWER)):
        levels = None
        if "recorder" in hass.config.components:
            from homeassistant.components.recorder import get_instance
            levels = await get_instance(hass).async_add_executor_job(_power_levels, hass, pw)
        if levels:
            idle, burn, n = levels
            why = T(f"az elmúlt 2 nap {n} méréséből: készenlét és fűtés két szintje", f"from {n} readings of the last 2 days: standby and heating levels")
        elif source in ("electric_heater", "storage_heater"):
            idle, burn = 5.0, 300.0
            why = T("alapérték (kevés mérés): a fűtő készenlétben szinte semmit, fűtéskor több száz W-ot vesz fel",
                    "default (few readings): a heater draws almost nothing on standby and hundreds of W while heating")
        else:
            # 0.45.0: no measured levels – nothing is written; the boiler health learns ("learning") until the
            # levels are set in the options (the 20 W / 115 W defaults are one boiler's)
            idle = burn = None
        if idle is not None:
            add("power_idle_w", idle, why, "W")
            add("power_burn_w", burn, why, "W")
    if (gas := ent.get(CONF_HEAT_ENERGY)) and (st := hass.states.get(gas)):
        unit = (st.attributes.get("unit_of_measurement") or "").lower()
        if "m³" in unit or unit in ("m3", "m^3"):
            add(CONF_ENERGY_FACTOR, round(GAS_KWH_PER_M3 * BOILER_EFFICIENCY, 2),
                T(f"gáz m³-ben: {str(GAS_KWH_PER_M3).replace('.', ',')} kWh/m³ fűtőérték × {int(BOILER_EFFICIENCY * 100)} % hatásfok",
                  f"gas in m³: {GAS_KWH_PER_M3} kWh/m³ × {int(BOILER_EFFICIENCY * 100)} % efficiency"), "kWh/m³")
        elif "kwh" in unit and source.startswith("electric"):
            add(CONF_ENERGY_FACTOR, 1.0, T("elektromos fűtés: 1 kWh villany = 1 kWh hő", "electric heating: 1 kWh of power = 1 kWh of heat"))
        elif "kwh" in unit:
            add(CONF_ENERGY_FACTOR, BOILER_EFFICIENCY, T("energia kWh-ban: a hatásfokkal", "energy in kWh: times the efficiency"))
        elif "mj" in unit:
            add(CONF_ENERGY_FACTOR, round(BOILER_EFFICIENCY / 3.6, 3), T("energia MJ-ban: ÷ 3,6 × hatásfok", "energy in MJ: ÷ 3.6 × efficiency"))
    if control in ("tpi", "pid", "curve") and source in ("onoff_boiler", "modulating_boiler", "heat_pump", "electric_boiler"):
        # a whole-house source: its output turns the learned heat need into a base demand (a room heater has none)
        add("boiler_power_kw", base.boiler_power_kw or 0.0, T("a kazán hasznos teljesítménye (adattábla); 0 = a hőigényből számolt alapigény ki",
            "the boiler's output (nameplate); 0 = no heat-need feed-forward"), "kW")
    targets = {"target_home": 21.0, "target_night": 19.0, "target_away": 17.0} if control != "ac" else \
        {"target_home": 21.0, "target_night": 19.0, "target_away": 16.0}
    for k, v in targets.items():
        add(k, v, T("kezdő cél, a presetek a beállításokban finomíthatók", "starting target; presets can be refined in the options"), "°C")
    add("night_start", "22:00:00", T("éjszakai cél kezdete", "night target from"))
    add("night_end", "06:00:00", T("éjszakai cél vége", "night target until"))
    rooms = []
    if control in ("tpi", "pid") and ent.get(CONF_INDOOR):
        rooms = suggest_room_sensors(hass, {CONF_INDOOR: ent.get(CONF_INDOOR), CONF_OUTDOOR: ent.get(CONF_OUTDOOR)})
    c = cell(system, source)
    connection.send_result(msg["id"], {"items": items, "rooms": rooms,
                                       "matrix": {"status": c.status.value, "text": c.text_hu if lang == "hu" else c.text_en}})


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "hc_thermostat/wizard/apply",
    vol.Optional("entry_id"): vol.Any(str, None),
    vol.Required("name"): str,
    vol.Required("heat_source"): vol.In(SOURCES), vol.Required("system"): vol.In(SYSTEMS), vol.Required("control"): str,
    vol.Optional("entities", default={}): dict, vol.Optional("settings", default={}): dict,
    vol.Optional("trv"): vol.Any(dict, None),
    vol.Optional("rooms"): vol.Any(list, None), vol.Optional("leading_room"): vol.Any(str, None),
    vol.Optional("start_active", default=False): bool,  # 0.45.0: a new instance may start live (confirmed in the panel)
})
@websocket_api.async_response
async def ws_apply(hass: HomeAssistant, connection, msg) -> None:
    source, system, control = msg["heat_source"], msg["system"], msg["control"]
    if control not in _controls(source, system):
        connection.send_error(msg["id"], "invalid_control", "control not offered for this heat source")
        return
    ents = {k: v for k, v in msg["entities"].items() if k in ENTITY_KEYS and v not in (None, "", [])}
    sets = {k: v for k, v in msg["settings"].items() if k in SETTING_KEYS and v not in (None, "")}
    if not ents.get(CONF_INDOOR) and not (control in ("tpi", "pid", "onoff") and ents.get(CONF_DEMAND)):
        # 0.38.0: a relay control may take its demand from a wired wall thermostat instead
        connection.send_error(msg["id"], "missing_indoor", "an indoor thermometer (or a wall thermostat contact) is required")
        return
    need = {"tpi": CONF_ACTUATOR, "pid": CONF_ACTUATOR, "onoff": CONF_ACTUATOR, "storage": CONF_ACTUATOR, "external": CONF_EXTERNAL, "ac": CONF_EXTERNAL,
            "curve": CONF_FLOW}[control]
    if not ents.get(need):
        connection.send_error(msg["id"], "missing_device", f"{need} is required")
        return
    if electric_floor(system, source) and control in ("tpi", "pid") and not ents.get(CONF_FLOOR):
        connection.send_error(msg["id"], "missing_floor", "an electric floor needs a floor temperature sensor")
        return
    trv = trv_options(control, msg.get("trv"))
    rooms = wizard_rooms(hass, control, msg.get("rooms"), msg.get("leading_room"), ents.get(CONF_INDOOR), msg.get("entry_id"))
    if rooms is not None:  # 0.43.0: the rooms card replaces the TRV card (and the room thermometer list)
        trv = rooms
        ents.pop(CONF_ROOMS, None)
        ents.update({k: v for k, v in rooms.items() if k == CONF_INDOOR})
    if trv is not None:
        ents.pop(CONF_ROOM_TRVS, None)
    if (entry_id := msg.get("entry_id")):
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry is None or entry.domain != DOMAIN:
            connection.send_error(msg["id"], "not_found", "no such HC instance")
            return
        if ents.get(CONF_EXTERNAL) in excluded_climates(hass, entry_id):
            connection.send_error(msg["id"], "climate_taken", "an HC thermostat, or driven by another HC instance")
            return
        data = {**entry.data, CONF_HEAT_SOURCE: source, CONF_SYSTEM: system, CONF_CONTROL: control}
        options = {**entry.options, **ents, **sets}
        if trv is not None:
            options.update(trv)
            options.pop("trv_calibration", None)
            data.pop("trv_calibration", None)
        hass.config_entries.async_update_entry(entry, title=msg["name"] or entry.title, data=data, options=options)
        connection.send_result(msg["id"], {"entry_id": entry.entry_id, "created": False})
        return
    name = msg["name"].strip() or "HC Thermostat"
    if any(e.title.strip().casefold() == name.casefold() for e in hass.config_entries.async_entries(DOMAIN)):
        connection.send_error(msg["id"], "name_taken", "an HC instance with this name exists")
        return
    if ents.get(CONF_EXTERNAL) in excluded_climates(hass):
        connection.send_error(msg["id"], "climate_taken", "an HC thermostat, or driven by another HC instance")
        return
    mode = MODE_ACTIVE if msg.get("start_active") else MODE_SHADOW
    data = {"name": name, CONF_ROLE: "standalone", CONF_HEAT_SOURCE: source, CONF_SYSTEM: system,
            CONF_CONTROL: control, **ents, **sets, **(trv or {}), CONF_MODE: mode}
    if control == "curve":
        data = {**default_curve(system, source), **data}
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "wizard"}, data=data)
    entry_id = getattr(result.get("result"), "entry_id", None)
    connection.send_result(msg["id"], {"entry_id": entry_id, "created": True})

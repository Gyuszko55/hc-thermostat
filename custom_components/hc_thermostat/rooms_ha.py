"""Room thermometers in Home Assistant: which room each one is in, and a first suggestion of which to use."""

from __future__ import annotations

import statistics

from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from .const import CONF_INDOOR, CONF_OUTDOOR, CONF_REFERENCE, CONF_ROOMS, CONF_ZONE_TEMP, DOMAIN
from .units import state_value_c

PLAUSIBLE = (10.0, 32.0)  # a living room is in this range; fridges, freezers and radiators are not
SKIP_WORDS = ("hűtő", "huto", "fagyaszt", "radiátor", "radiator", "fridge", "freezer", "kazán", "boiler",
              "medence", "pool", "talaj", "soil", "akkumul", "battery", "processz", "cpu")
BATHROOM_WORDS = ("fürdő", "furdo", "bath")
# 0.44.2: outdoor places are no rooms (their thermometers came in as rooms: Udvar, Kert)
OUTDOOR_WORDS = ("udvar", "kert", "kültér", "kulter", "kinti", "külső", "kulso", "outdoor", "outside", "garden",
                 "yard", "courtyard", "exterior")


def _words(*texts) -> str:
    return " ".join(str(t or "") for t in texts).casefold()


def is_outdoor_area(hass, area_id: str | None) -> bool:
    """0.44.2: an area that is outside (by its id or name)."""
    return bool(area_id) and any(w in _words(area_id, area_name(hass, area_id)) for w in OUTDOOR_WORDS)


def _hc_entries(hass) -> list:
    try:
        return list(hass.config_entries.async_entries("hc_thermostat"))
    except AttributeError:
        return []


def hc_outdoor_sensors(hass) -> set[str]:
    """0.44.2: the outdoor thermometers of every HC instance – never a room's thermometer."""
    out = set()
    for entry in _hc_entries(hass):
        e = {**entry.data, **entry.options}.get(CONF_OUTDOOR)
        if isinstance(e, str) and e:
            out.add(e)
    return out


def heads_of_other_instances(hass, entry_id: str | None = None) -> dict[str, str]:
    """0.44.2: TRV head -> the title of the HC instance that already drives it (other than `entry_id`). Two
    instances writing the same head fight each other."""
    out: dict[str, str] = {}
    for entry in _hc_entries(hass):
        if entry.entry_id == entry_id:
            continue
        conf = {**entry.data, **entry.options}
        heads = list(conf.get("room_trvs") or [])
        for r in conf.get("rooms") or []:
            if isinstance(r, dict):
                heads += [h for h in r.get("trvs") or [] if isinstance(h, str)]
        for h in heads:
            out.setdefault(h, entry.title)
    return out


def climates_of_other_instances(hass, entry_id: str | None = None) -> dict[str, str]:
    """0.45.0: every climate another HC instance writes to – its TRV heads and its managed thermostat / AC unit –
    -> that instance's title."""
    out = dict(heads_of_other_instances(hass, entry_id))
    for entry in _hc_entries(hass):
        if entry.entry_id == entry_id:
            continue
        conf = {**entry.data, **entry.options}
        ext = conf.get("external_climate")
        if isinstance(ext, str) and ext.startswith("climate."):
            out.setdefault(ext, entry.title)
    return out


def hc_climates(hass) -> list[str]:
    """0.45.0: the climate entities HC itself made (an HC thermostat is never a device HC drives)."""
    try:
        reg = er.async_get(hass)
    except Exception:
        return []
    return sorted(e.entity_id for e in list(reg.entities.values()) if e.platform == DOMAIN and e.domain == "climate")


def excluded_climates(hass, entry_id: str | None = None) -> list[str]:
    """0.45.0: what a thermostat / AC unit / TRV head picker must not offer to an instance."""
    return sorted(set(hc_climates(hass)) | set(climates_of_other_instances(hass, entry_id)))


def looks_like_head(hass, entity_id: str) -> bool:
    """0.44.2: a climate that is a radiator valve head (TRV) – by its id / name / device, or a valve entity on its
    device – and not a whole thermostat (e.g. another integration's climate)."""
    ent_reg = er.async_get(hass)
    st = hass.states.get(entity_id)
    e = ent_reg.async_get(entity_id)
    text = _words(entity_id, st.attributes.get("friendly_name") if st else None)
    dev = dr.async_get(hass).async_get(e.device_id) if e is not None and e.device_id else None
    if dev is not None:
        text += " " + _words(dev.name, dev.model, getattr(dev, "model_id", None))
    if any(w in text for w in HEAD_WORDS + ("thermostatic", "radiator valve")):
        return True
    if dev is not None:
        for x in er.async_entries_for_device(ent_reg, dev.id):
            if any(w in x.entity_id for w in ("valve", "szelep", "pi_heating", "position")):
                return True
    return False


def area_id_of(hass, entity_id: str) -> str | None:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id and (device := dr.async_get(hass).async_get(entry.device_id)):
        return device.area_id
    return None


def area_name(hass, area_id: str | None) -> str | None:
    area = ar.async_get(hass).async_get_area(area_id) if area_id else None
    return area.name if area else None


def group_by_room(hass, entity_ids: list[str]) -> dict[str, list[str]]:
    """Room name -> its thermometers (several in one room are combined by their mean, 0.43.0)."""
    rooms: dict[str, list[str]] = {}
    for entity_id in entity_ids:
        name = area_name(hass, area_id_of(hass, entity_id)) or entity_id
        rooms.setdefault(name, []).append(entity_id)
    return rooms


def room_value(values: list[float]) -> float | None:
    """A room's thermometer group: the mean of the available ones (0.43.0; before: the median)."""
    return statistics.fmean(values) if values else None


def suggest_room_sensors(hass, conf: dict) -> list[str]:
    """Temperature sensors in the other rooms of the home.

    Left out: the main, outdoor, reference and zone thermometers and every sensor in their rooms (the main room
    is the reference itself, the outdoor and zone rooms are not part of the home), bathrooms, sensors whose name
    says they measure something else, and readings no living room has.
    """
    skip_ids = {conf.get(k) for k in (CONF_INDOOR, CONF_OUTDOOR, CONF_REFERENCE, CONF_ZONE_TEMP)} - {None}
    outdoor = hc_outdoor_sensors(hass)  # 0.44.2: no other instance's outdoor thermometer either, nor its area
    skip_areas = {area_id_of(hass, e) for e in skip_ids | outdoor} - {None}
    skip_ids |= outdoor
    out = []
    for state in hass.states.async_all("sensor"):
        if state.attributes.get("device_class") != "temperature" or state.entity_id in skip_ids:
            continue
        area = area_id_of(hass, state.entity_id)
        if area is None or area in skip_areas or is_outdoor_area(hass, area):
            continue
        name = f"{state.entity_id} {state.attributes.get('friendly_name', '')} {area_name(hass, area) or ''}".lower()
        if any(w in name for w in SKIP_WORDS + BATHROOM_WORDS + OUTDOOR_WORDS):
            continue
        value = state_value_c(state)  # 0.45.0: °F thermometers too
        if value is None:
            continue
        if PLAUSIBLE[0] <= value <= PLAUSIBLE[1]:
            out.append(state.entity_id)
    return sorted(out)


# --- 0.42.0: the thermometer of a TRV head -------------------------------------------------------------------------
def _is_temperature(state) -> bool:
    a = state.attributes
    return a.get("device_class") == "temperature" or a.get("unit_of_measurement") in ("°C", "°F")


def pick_trv_candidates(head_area: str | None, head_device: str | None, sensors: list[dict]) -> tuple[list[dict], bool]:
    """The thermometers offered for one head. sensors: {id, name, area, device, available} of every temperature
    sensor. Those in the head's area, else (none there, or the head has no area) all of them – the bool says so;
    never one on the head's own device, never an unavailable one; by name."""
    usable = [s for s in sensors if s.get("available") and not (head_device and s.get("device") == head_device)]
    usable.sort(key=lambda s: (str(s.get("name") or s["id"]).casefold(), s["id"]))
    same = [s for s in usable if head_area and s.get("area") == head_area]
    return (same, False) if same else (usable, True)


def trv_sensor_candidates(hass, head: str) -> dict:
    """{area, room, candidates: [{id, name, area, state, unit}], fallback, suggest} for one TRV head."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(head)
    head_device = entry.device_id if entry is not None else None
    head_area = area_id_of(hass, head)
    sensors = []
    for state in hass.states.async_all("sensor"):
        if not _is_temperature(state):
            continue
        e = ent_reg.async_get(state.entity_id)
        if e is not None and getattr(e, "platform", None) == "hc_thermostat":
            continue  # HC's own values (learned offsets, targets) are no thermometers
        sensors.append({"id": state.entity_id, "name": state.attributes.get("friendly_name", state.entity_id),
                        "area": area_id_of(hass, state.entity_id), "device": e.device_id if e is not None else None,
                        "available": state.state not in ("unavailable", "unknown"),
                        "state": state.state, "unit": state.attributes.get("unit_of_measurement")})
    picked, fallback = pick_trv_candidates(head_area, head_device, sensors)
    return {"area": head_area, "room": area_name(hass, head_area) or head, "fallback": fallback,
            "candidates": [{"id": s["id"], "name": s["name"], "area": area_name(hass, s["area"]), "state": s["state"],
                            "unit": s["unit"]} for s in picked],
            "suggest": picked[0]["id"] if picked and not fallback else None}


def current_trv_sensors(hass, conf: dict) -> dict[str, str]:
    """The thermometer each head uses now, for prefilling a form: `trv_sensors` as saved, else (legacy calibration
    on) the first room thermometer in the head's room; a head on its own sensor is left out."""
    heads = list(conf.get("room_trvs") or [])
    chosen = conf.get("trv_sensors")
    if isinstance(chosen, dict):
        return {h: s for h, s in chosen.items() if h in heads and isinstance(s, str) and "." in s}
    if not conf.get("trv_calibration"):
        return {}
    rooms = group_by_room(hass, list(conf.get(CONF_ROOMS) or []))
    trvs = group_by_room(hass, heads)
    return {h: rooms[room][0] for room, hs in trvs.items() for h in hs if rooms.get(room)}


# --- 0.43.0: rooms ------------------------------------------------------------------------------------------------
def room_key_of(hass, name: str, entity_ids: list[str]) -> tuple[str, str | None]:
    """A room's key (its area id, else its name as a slug) and its area id."""
    from .core.room_model import slugify
    area = None
    for entity_id in entity_ids:
        try:
            area = area_id_of(hass, entity_id)
        except Exception:  # no registries (tests)
            area = None
        if area:
            break
    return slugify(area or name), area


def room_specs_for(hass, conf: dict, sensor_groups: dict | None = None, trv_groups: dict | None = None):
    """(rooms, leading room key) of an instance: the saved `rooms` list, else derived from the legacy options."""
    from .core.room_model import CONF_LEADING, CONF_ROOM_LIST, legacy_rooms, parse_rooms
    raw = conf.get(CONF_ROOM_LIST)
    if isinstance(raw, list) and raw:
        specs = parse_rooms(raw)
        leading = conf.get(CONF_LEADING)
        return specs, leading if any(s.key == leading for s in specs) else None
    if sensor_groups is None:
        sensor_groups = group_by_room(hass, list(conf.get(CONF_ROOMS) or []))
    if trv_groups is None:
        trv_groups = group_by_room(hass, list(conf.get("room_trvs") or []))
    leading_name = None
    if conf.get(CONF_INDOOR):
        try:
            leading_name = area_name(hass, area_id_of(hass, conf[CONF_INDOOR]))
        except Exception:
            leading_name = None
    return legacy_rooms(conf, sensor_groups, trv_groups, lambda n, ids: room_key_of(hass, n, ids), leading_name)


PRESENCE_CLASSES = ("motion", "occupancy", "presence")
HEAD_WORDS = ("trv", "fej", "valve", "szelep", "local_temperature", "local temperature")


def _bermuda_like(state, area_names: set[str]) -> bool:
    """A sensor that tells which room someone is in: an area_id attribute (Bermuda), or a state that is an area name."""
    a = state.attributes
    if state.domain == "sensor" and ("area_id" in a or str(a.get("device_class", "")).startswith("bermuda")):
        return True
    if state.domain == "input_select":
        return any(str(o).casefold() in area_names for o in a.get("options") or [])
    return state.domain == "sensor" and str(state.state).casefold() in area_names and a.get("device_class") is None


def rooms_candidates(hass) -> dict:
    """For the wizard's rooms card: every area with its thermometers, TRV heads (climates not of HC) and presence
    sources (motion / occupancy binary sensors there), plus the room-tracking sensors (Bermuda-like) of the home."""
    areas = {a.id: a.name for a in ar.async_get(hass).async_list_areas()}
    names = {n.casefold() for n in areas.values()} | {k.casefold() for k in areas}
    ent_reg = er.async_get(hass)
    by_area: dict[str, dict] = {k: {"area": k, "name": n, "sensors": [], "trvs": [], "presence": []} for k, n in areas.items()}
    tracking, temps, climates = [], [], []
    for st in hass.states.async_all():
        e = ent_reg.async_get(st.entity_id)
        if e is not None and getattr(e, "platform", None) == "hc_thermostat":
            continue
        dom, a = st.domain, st.attributes
        area = area_id_of(hass, st.entity_id)
        item = {"id": st.entity_id, "name": a.get("friendly_name", st.entity_id), "state": st.state,
                "unit": a.get("unit_of_measurement"), "area": area, "area_name": areas.get(area)}
        if dom == "sensor" and _is_temperature(st):
            name = f"{st.entity_id} {item['name']}".lower()
            if any(w in name for w in SKIP_WORDS):
                continue
            temps.append(item)
            if area in by_area:
                by_area[area]["sensors"].append(item)
        elif dom == "climate" and a.get("hc_mode") is None:
            climates.append(item)
            if area in by_area:
                by_area[area]["trvs"].append(item)
        elif dom in ("binary_sensor", "input_boolean") and (a.get("device_class") in PRESENCE_CLASSES or dom == "input_boolean"):
            if area in by_area:
                by_area[area]["presence"].append(item)
        if _bermuda_like(st, names):
            tracking.append(item)
    key = lambda x: (str(x["name"]).casefold(), x["id"])
    # a head's own thermometer (on the TRV's device, or named so) is not the room's: listed last, never suggested first
    head_devices = {e.device_id for c in climates if (e := ent_reg.async_get(c["id"])) is not None and e.device_id}
    for v in by_area.values():
        for x in v["sensors"]:
            e = ent_reg.async_get(x["id"])
            x["head"] = bool((e is not None and e.device_id in head_devices)
                             or any(w in f"{x['id']} {x['name']}".lower() for w in HEAD_WORDS))
        v["sensors"].sort(key=lambda x: (x["head"], *key(x)))
    for v in by_area.values():
        for k in ("trvs", "presence"):
            v[k].sort(key=key)
    # 0.44.2: outdoor areas, real heads and heads another HC instance already drives
    taken = climates_of_other_instances(hass)  # 0.45.0: their managed thermostats too
    outdoor = hc_outdoor_sensors(hass)
    for k, v in by_area.items():
        v["outdoor"] = is_outdoor_area(hass, k) or any(x["id"] in outdoor for x in v["sensors"])
        for x in v["trvs"]:
            x["head"] = looks_like_head(hass, x["id"])
            if x["id"] in taken:
                x["taken_by"] = taken[x["id"]]
    for x in climates:
        x["head"] = looks_like_head(hass, x["id"])
        if x["id"] in taken:
            x["taken_by"] = taken[x["id"]]
    return {"areas": sorted(by_area.values(), key=lambda x: str(x["name"]).casefold()),
            "tracking": sorted(tracking, key=key), "temperature": sorted(temps, key=key),
            "climates": sorted(climates, key=key)}

"""0.46.0: the rooms in the options – areas ticked in a list, then every room in its own fold-out section.

Step 1 (rooms): the home's name, the areas as a check list (with what each has), rooms without an area.
Step 2 (room_details): the leading room and the tolerance on top, then one section per room with the area's devices
    as check boxes, already ticked for a new room: thermometers (several: their mean – HC's group), TRV heads,
    presence sources, window / door contacts; a TRV room (not the leading one) also its target, presence setback,
    boiler demand and per head calibration.
Step 3 (room_own): only the rooms set to their own schedule.

The section names are the rooms' names and the field names are plain words in Home Assistant's language: a form built
at run time has no translation keys for them (Home Assistant shows the key itself).
"""

from __future__ import annotations

from homeassistant.data_entry_flow import section
import voluptuous as vol
from homeassistant.helpers.selector import (
    BooleanSelector, EntitySelector, EntitySelectorConfig, NumberSelector, NumberSelectorConfig, NumberSelectorMode,
    SelectSelector, SelectSelectorConfig, SelectSelectorMode, TextSelector, TimeSelector,
)

from .core.room_model import FOLLOW, HEAD, OWN, parse_room, slugify

CUSTOM = "custom:"
WORDS = {
    "hu": {"name": "Név", "sensors": "Hőmérők", "trvs": "Szelepfejek", "presence": "Jelenlét",
           "windows": "Ablak / ajtó", "more": "Más eszköz hozzáadása (másik területről)", "mode": "Cél",
           "offset": "Eltérés a ház céljától", "absent_min": "Távollét ennyi perc után (jelenléttel)",
           "setback": "Csökkentés távollétben", "demand": "Rövid égést kérhet a kazántól, ha messze a célja alatt van",
           "position": "Helye a házrajzon (sorszám)", "cal": "Kalibrálás – {head}",
           "target_home": "Otthon hőfok", "target_night": "Éjszakai hőfok", "target_away": "Háztartás távol hőfok",
           "night_start": "Éjszaka kezdete", "night_end": "Éjszaka vége",
           "follow": "A ház célját követi (+ eltérés)", "own": "Saját menetrend",
           "cal_room": "A helyiség hőmérője – kalibrálás", "cal_head": "A fej saját hőmérője – nincs kalibrálás",
           "head": "fej", "tracker": "helyiség-követő", "no_area": "terület nélkül", "taken": "másik HC-példány: {who}",
           "n_sensors": "hőmérő", "n_trvs": "szelepfej", "n_presence": "jelenlét", "n_windows": "ablak/ajtó",
           "nothing": "nincs eszköz", "radiators": "Radiátor-hőmérő (kap-e meleget)",
           "humidity": "Páratartalom (harmatpont, penész-kockázat)"},
    "en": {"name": "Name", "sensors": "Thermometers", "trvs": "TRV heads", "presence": "Presence",
           "windows": "Window / door", "more": "Add another device (from another area)", "mode": "Target",
           "offset": "Offset from the house target", "absent_min": "Absent after minutes (with presence)",
           "setback": "Setback while absent", "demand": "May ask the boiler for short burns when far below its target",
           "position": "Place in the house drawing (number)", "cal": "Calibration – {head}",
           "target_home": "Home temperature", "target_night": "Night temperature", "target_away": "Household away temperature",
           "night_start": "Night starts", "night_end": "Night ends",
           "follow": "Follows the house target (+ offset)", "own": "Own schedule",
           "cal_room": "The room's thermometer – calibrated", "cal_head": "The head's own thermometer – no calibration",
           "head": "head", "tracker": "room tracker", "no_area": "no area", "taken": "other HC instance: {who}",
           "n_sensors": "thermometer(s)", "n_trvs": "TRV head(s)", "n_presence": "presence", "n_windows": "window/door",
           "nothing": "no devices", "radiators": "Radiator thermometer (does it get heat)",
           "humidity": "Humidity (dew point, mould risk)"},
}
PROBLEMS = {
    "hu": {"room_name": "{room}: adj nevet a helyiségnek.", "room_name_taken": "{room}: van már ilyen nevű helyiség.",
           "room_empty": "{room}: egy helyiséghez hőmérő vagy szelepfej kell.",
           "trv_is_hc": "{room}: HC termosztát nem lehet szelepfej.",
           "trv_taken": "{room}: a(z) {what} szelepfej egy másik helyiségben is be van jelölve.",
           "trv_other_instance": "{room}: a(z) {what} szelepfejet már egy másik HC-példány vezérli.",
           "sensor_taken": "{room}: a(z) {what} hőmérő egy másik helyiségben is be van jelölve.",
           "radiator_is_room": "{room}: a(z) {what} nem lehet egyszerre a helyiség hőmérője és radiátor-hőmérő.",
           "leading_trv": "A vezető helyiségben ({room}) szelepfej van: pipáld be a megerősítést (a fejei a ház céljét kapják).",
           "area_taken": "{room}: ezen a területen már egy másik HC-példánynak van helyisége ({what}).",
           "no_rooms": "Jelölj be legalább egy területet, vagy adj meg egy helyiséget terület nélkül."},
    "en": {"room_name": "{room}: give the room a name.", "room_name_taken": "{room}: a room with this name exists.",
           "room_empty": "{room}: a room needs a thermometer or a TRV head.",
           "trv_is_hc": "{room}: a HC thermostat cannot be a TRV head.",
           "trv_taken": "{room}: the TRV head {what} is ticked in another room too.",
           "trv_other_instance": "{room}: the TRV head {what} is driven by another HC instance.",
           "sensor_taken": "{room}: the thermometer {what} is ticked in another room too.",
           "radiator_is_room": "{room}: {what} cannot be the room's thermometer and a radiator thermometer at once.",
           "leading_trv": "The leading room ({room}) has a TRV head: tick the confirmation (its heads get the house target).",
           "area_taken": "{room}: another HC instance has a room in this area ({what}).",
           "no_rooms": "Tick at least one area, or give a room without an area."},
}
MORE_DOMAINS = ["sensor", "climate", "binary_sensor", "person", "device_tracker", "input_select", "input_boolean"]


def lang_of(hass) -> str:
    return "hu" if str(getattr(getattr(hass, "config", None), "language", "") or "").startswith("hu") else "en"


def problem_text(lang: str, code: str, room: str = "", what: str = "") -> str:
    return PROBLEMS[lang][code].format(room=room, what=what)


def _number(lo: float, hi: float, step: float, unit: str = "") -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(min=lo, max=hi, step=step, unit_of_measurement=unit,
                                               mode=NumberSelectorMode.BOX))


def _checks(options: list[dict]) -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(options=options, multiple=True, mode=SelectSelectorMode.LIST))


def _fmt(value) -> str:
    try:
        return f"{float(value):.1f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


# --- step 1: the areas ---------------------------------------------------------------------------------------------
def area_label(lang: str, area: dict, taken_by: str | None = None) -> str:
    w = WORDS[lang]
    bits = [f"{len(area[k])} {w['n_' + k]}" for k in ("sensors", "trvs", "presence", "windows") if area.get(k)]
    text = f"{area['name']} – {' · '.join(bits) if bits else w['nothing']}"
    return f"{text} ({w['taken'].format(who=taken_by)})" if taken_by else text


def area_options(lang: str, cand: dict, rooms: list[dict], taken: dict[str, str]) -> list[dict]:
    """The check list: every indoor area (an outdoor one only when it is already a room), then the rooms without an
    area. Value: the area id, or custom:<room key>."""
    used = {r.get("area") for r in rooms if r.get("area")}
    out = [{"value": a["area"], "label": area_label(lang, a, taken.get(a["area"]))}
           for a in cand.get("areas") or [] if not a.get("outdoor") or a["area"] in used]
    known = {o["value"] for o in out}
    for r in rooms:
        if r.get("area") and r["area"] not in known:  # an area that is gone from the registry
            out.append({"value": r["area"], "label": r["name"]})
        elif not r.get("area"):
            out.append({"value": CUSTOM + r["key"], "label": f"{r['name']} ({WORDS[lang]['no_area']})"})
    return out


def chosen_values(rooms: list[dict]) -> list[str]:
    return [r["area"] if r.get("area") else CUSTOM + r["key"] for r in rooms]


def new_room(area: dict, taken_heads: set[str]) -> dict:
    """A room for a newly ticked area, filled from what the area has: its thermometers (not a head's own), its real
    heads that no other room or instance drives, its motion / occupancy sensors and its contacts."""
    sensors = [s["id"] for s in area.get("sensors") or [] if not s.get("head")]
    heads = [t["id"] for t in area.get("trvs") or []
             if t.get("head") and not t.get("taken_by") and t["id"] not in taken_heads]
    presence = [p["id"] for p in area.get("presence") or [] if p["id"].startswith("binary_sensor.")]
    windows = [w["id"] for w in area.get("windows") or []]
    return {"key": area["area"], "name": area["name"], "area": area["area"], "sensors": sensors, "trvs": heads,
            "mode": FOLLOW, "offset": 0.0, "presence": presence if heads else [], "absent_min": 15.0,
            "setback": 2.0, "demand": False, "windows": windows, "new": True,
            "radiators": [r["id"] for r in area.get("radiators") or []],  # 0.48.0
            "humidity": [h["id"] for h in area.get("humidity") or []]}


def pick_rooms(selected: list[str], rooms: list[dict], cand: dict, custom_new: str | None) -> list[dict]:
    """The rooms after step 1: the kept ones in their order, then the newly ticked areas, then new rooms without an
    area (names separated by commas)."""
    by_area = {a["area"]: a for a in cand.get("areas") or []}
    keep = [r for r in rooms if (r["area"] if r.get("area") else CUSTOM + r["key"]) in selected]
    have = {r.get("area") for r in keep}
    taken_heads = {h for r in keep for h in r.get("trvs") or []}
    out = list(keep)
    for value in selected:
        if value.startswith(CUSTOM) or value in have or value not in by_area:
            continue
        room = new_room(by_area[value], taken_heads)
        taken_heads.update(room["trvs"])
        out.append(room)
    keys = {r["key"] for r in out}
    for name in [n.strip() for n in str(custom_new or "").split(",") if n.strip()]:
        key, n = slugify(name), 2
        while key in keys:
            key, n = f"{slugify(name)}_{n}", n + 1
        keys.add(key)
        out.append({"key": key, "name": name, "area": None, "sensors": [], "trvs": [], "mode": FOLLOW,
                    "offset": 0.0, "presence": [], "absent_min": 15.0, "setback": 2.0, "demand": False,
                    "windows": [], "new": True})
    return out


def leading_guess(rooms: list[dict], indoor: str | None, indoor_area: str | None) -> str | None:
    """The room the house thermometer is in (by its list, else by its area) – it drives the boiler already."""
    for r in rooms:
        if indoor and indoor in (r.get("sensors") or []):
            return r["key"]
    return next((r["key"] for r in rooms if indoor_area and r.get("area") == indoor_area), None)


# --- step 2: one section per room --------------------------------------------------------------------------------
def _item_label(hass, entity_id: str, suffix: str = "") -> str:
    st = hass.states.get(entity_id) if hass is not None else None
    name = str(st.attributes.get("friendly_name") or entity_id) if st is not None else entity_id
    unit = st.attributes.get("unit_of_measurement") if st is not None else None
    if unit and st.state not in ("unknown", "unavailable", ""):  # a measured value; an on / off state says little
        name = f"{name} ({_fmt(st.state)} {unit})"
    return f"{name} ({suffix})" if suffix else name


def _options(hass, ids: list[str], marks: dict[str, str] | None = None) -> list[dict]:
    marks = marks or {}
    return [{"value": e, "label": _item_label(hass, e, marks.get(e, ""))} for e in dict.fromkeys(ids)]


def room_candidates(room: dict, area: dict | None, tracking: list[dict], excluded: set[str]) -> dict[str, list]:
    """What a room's check boxes offer: the area's devices plus whatever the room already has (from anywhere).
    Heads that another room of this form or another instance drives are left out (unless the room has them)."""
    area = area or {}
    mine = lambda k: list(room.get(k) or [])
    return {
        "sensors": [*[s["id"] for s in area.get("sensors") or [] if not s.get("head")],
                    *[s["id"] for s in area.get("sensors") or [] if s.get("head")], *mine("sensors")],
        "trvs": [*[t["id"] for t in area.get("trvs") or [] if t["id"] not in excluded and not t.get("taken_by")],
                 *mine("trvs")],
        "presence": [*[p["id"] for p in area.get("presence") or []], *[x["id"] for x in tracking], *mine("presence")],
        "windows": [*[w["id"] for w in area.get("windows") or []], *mine("windows")],
        # 0.48.0: radiator thermometers (named so, then the area's other thermometers) and humidity sensors
        "radiators": [*[r["id"] for r in area.get("radiators") or []],
                      *[s["id"] for s in area.get("sensors") or [] if not s.get("head")], *mine("radiators")],
        "humidity": [*[h["id"] for h in area.get("humidity") or []], *mine("humidity")],
        "heads_own": [s["id"] for s in area.get("sensors") or [] if s.get("head")],
        "trackers": [x["id"] for x in tracking],
    }


def shows_trv_fields(room: dict, leading: str | None, cands: dict) -> bool:
    """The target / presence / demand fields: a room that is (or can be) a TRV room and is not the leading one."""
    return room["key"] != leading and bool(room.get("trvs") or cands["trvs"])


def cal_labels(hass, lang: str, heads: list[str]) -> dict[str, str]:
    """Head -> its calibration field's name (the head's name; the entity id when two heads share a name)."""
    names = {h: _item_label(hass, h).split(" (")[0] for h in heads}
    double = {n for n in names.values() if list(names.values()).count(n) > 1}
    return {h: WORDS[lang]["cal"].format(head=h if n in double else n) for h, n in names.items()}


def room_section(hass, lang: str, room: dict, cands: dict, leading: str | None, position: int, total: int):
    w = WORDS[lang]
    head_marks = {e: w["head"] for e in cands["heads_own"]}
    track_marks = {e: w["tracker"] for e in cands["trackers"]}
    fields: dict = {
        vol.Required(w["name"], default=room["name"]): TextSelector(),
        vol.Optional(w["sensors"], default=list(room.get("sensors") or [])): _checks(_options(hass, cands["sensors"], head_marks)),
    }
    if cands["trvs"]:
        fields[vol.Optional(w["trvs"], default=list(room.get("trvs") or []))] = _checks(_options(hass, cands["trvs"]))
    trv_room = shows_trv_fields(room, leading, cands)
    if trv_room and cands["presence"]:
        fields[vol.Optional(w["presence"], default=list(room.get("presence") or []))] = \
            _checks(_options(hass, cands["presence"], track_marks))
    if cands["windows"]:
        fields[vol.Optional(w["windows"], default=list(room.get("windows") or []))] = _checks(_options(hass, cands["windows"]))
    if cands.get("radiators"):
        fields[vol.Optional(w["radiators"], default=list(room.get("radiators") or []))] = \
            _checks(_options(hass, cands["radiators"]))
    if cands.get("humidity"):
        fields[vol.Optional(w["humidity"], default=list(room.get("humidity") or []))] = \
            _checks(_options(hass, cands["humidity"]))
    fields[vol.Optional(w["more"])] = EntitySelector(EntitySelectorConfig(domain=MORE_DOMAINS, multiple=True))
    if trv_room:
        mode = room.get("mode") if room.get("mode") in (FOLLOW, OWN) else FOLLOW
        fields[vol.Required(w["mode"], default=mode)] = SelectSelector(SelectSelectorConfig(
            options=[{"value": FOLLOW, "label": w["follow"]}, {"value": OWN, "label": w["own"]}],
            mode=SelectSelectorMode.DROPDOWN))
        fields[vol.Required(w["offset"], default=float(room.get("offset") or 0.0))] = _number(-5, 5, 0.5, "°C")
        fields[vol.Required(w["absent_min"], default=float(room.get("absent_min") or 15.0))] = _number(1, 720, 1, "min")
        fields[vol.Required(w["setback"], default=float(room.get("setback", 2.0)))] = _number(0, 10, 0.5, "°C")
        fields[vol.Required(w["demand"], default=bool(room.get("demand")))] = BooleanSelector()
        labels = cal_labels(hass, lang, list(room.get("trvs") or []))
        for head in room.get("trvs") or []:
            current = (room.get("head_sensors") or {}).get(head, "room")
            opts = [{"value": "room", "label": w["cal_room"]}, {"value": HEAD, "label": w["cal_head"]},
                    *[o for o in _options(hass, cands["sensors"]) if o["value"] not in (room.get("sensors") or [])]]
            if current not in [o["value"] for o in opts]:
                opts.append({"value": current, "label": _item_label(hass, current)})
            fields[vol.Required(labels[head], default=current)] = \
                SelectSelector(SelectSelectorConfig(options=opts, mode=SelectSelectorMode.DROPDOWN))
    fields[vol.Required(w["position"], default=position)] = _number(1, max(1, total), 1)
    return section(vol.Schema(fields), {"collapsed": not room.get("new")})


def classify(hass, entity_id: str) -> str | None:
    """A device added from another area: which list it goes into."""
    domain = entity_id.split(".")[0]
    st = hass.states.get(entity_id) if hass is not None else None
    attrs = st.attributes if st is not None else {}
    if domain == "climate":
        return "trvs"
    if domain == "binary_sensor":
        from .rooms_ha import WINDOW_CLASSES
        return "windows" if attrs.get("device_class") in WINDOW_CLASSES else "presence"
    if domain == "sensor":
        if attrs.get("device_class") == "humidity":
            return "humidity"
        if attrs.get("device_class") == "temperature" or str(attrs.get("unit_of_measurement") or "") in ("°C", "°F"):
            from .rooms_ha import RADIATOR_WORDS
            name = f"{entity_id} {attrs.get('friendly_name') or ''}".lower()
            return "radiators" if any(x in name for x in RADIATOR_WORDS) else "sensors"
        return "presence"  # a room tracker (Bermuda-like) – its state is the area
    if domain in ("person", "device_tracker", "input_select", "input_boolean"):
        return "presence"
    return None


def read_section(hass, lang: str, room: dict, data: dict) -> dict:
    """One section's answer back into a room dict (the fields not shown keep the room's values)."""
    w = WORDS[lang]
    out = {**room, "name": str(data.get(w["name"], room["name"]) or "").strip()}
    for k in ("sensors", "trvs", "presence", "windows", "radiators", "humidity"):
        if w[k] in data:
            out[k] = list(data.get(w[k]) or [])
    for e in data.get(w["more"]) or []:
        kind = classify(hass, e)
        if kind and e not in out.get(kind, []):
            out[kind] = [*(out.get(kind) or []), e]
    if w["mode"] in data:
        out["mode"] = data[w["mode"]] if data[w["mode"]] in (FOLLOW, OWN) else FOLLOW
        out["offset"] = float(data.get(w["offset"], 0.0))
        out["absent_min"] = float(data.get(w["absent_min"], 15.0))
        out["setback"] = float(data.get(w["setback"], 2.0))
        out["demand"] = bool(data.get(w["demand"]))
        heads = {}
        labels = cal_labels(hass, lang, list(out.get("trvs") or []))
        for head in out.get("trvs") or []:
            value = data.get(labels[head], (room.get("head_sensors") or {}).get(head, "room"))
            if value and value != "room":
                heads[head] = value
        out["head_sensors"] = heads
    else:
        out["head_sensors"] = {h: v for h, v in (room.get("head_sensors") or {}).items() if h in (out.get("trvs") or [])}
    if not out.get("trvs"):
        out["demand"] = False
    try:
        out["_position"] = float(data.get(w["position"], 0))
    except (TypeError, ValueError):
        out["_position"] = 0.0
    out.pop("new", None)
    return out


def check_rooms(lang: str, rooms: list[dict], leading: str | None, confirm: bool, hc_climates: set[str],
                other_heads: dict[str, str], name_of) -> str | None:
    """The first problem as a text, or None."""
    seen_names: set[str] = set()
    heads: dict[str, str] = {}
    sensors: dict[str, str] = {}
    for r in rooms:
        label = r["name"] or r["key"]
        if not r["name"]:
            return problem_text(lang, "room_name", label)
        if r["name"].casefold() in seen_names:
            return problem_text(lang, "room_name_taken", label)
        seen_names.add(r["name"].casefold())
        if not r.get("sensors") and not r.get("trvs") and r["key"] != leading:
            return problem_text(lang, "room_empty", label)
        for h in r.get("trvs") or []:
            if h in hc_climates:
                return problem_text(lang, "trv_is_hc", label)
            if h in other_heads:
                return problem_text(lang, "trv_other_instance", label, name_of(h))
            if h in heads:
                return problem_text(lang, "trv_taken", label, name_of(h))
            heads[h] = r["key"]
        for s in r.get("sensors") or []:
            if s in sensors:
                return problem_text(lang, "sensor_taken", label, name_of(s))
            sensors[s] = r["key"]
        for s in r.get("radiators") or []:
            if s in (r.get("sensors") or []):
                return problem_text(lang, "radiator_is_room", label, name_of(s))
    lead = next((r for r in rooms if r["key"] == leading), None)
    if lead is not None and lead.get("trvs") and not confirm:
        return problem_text(lang, "leading_trv", lead["name"])
    return None


def order_rooms(rooms: list[dict]) -> list[dict]:
    """By the numbers given (a tie keeps the old order); the helper keys go."""
    ranked = sorted(enumerate(rooms), key=lambda x: (x[1].get("_position") or x[0] + 1, x[0]))
    return [{k: v for k, v in r.items() if k != "_position"} for _, r in ranked]


# --- step 3: own schedules ---------------------------------------------------------------------------------------
def own_section(lang: str, room: dict):
    w = WORDS[lang]
    temp = _number(5, 30, 0.5, "°C")
    spec = parse_room({**room, "name": room.get("name") or "x"})
    return section(vol.Schema({
        vol.Required(w["target_home"], default=spec.target_home): temp,
        vol.Required(w["target_night"], default=spec.target_night): temp,
        vol.Required(w["target_away"], default=spec.target_away): temp,
        vol.Required(w["night_start"], default=spec.night_start): TimeSelector(),
        vol.Required(w["night_end"], default=spec.night_end): TimeSelector(),
    }), {"collapsed": False})


def read_own(lang: str, room: dict, data: dict) -> dict:
    w = WORDS[lang]
    return {**room, "target_home": float(data.get(w["target_home"], 21.0)),
            "target_night": float(data.get(w["target_night"], 19.0)),
            "target_away": float(data.get(w["target_away"], 17.0)),
            "night_start": str(data.get(w["night_start"], "22:00"))[:5],
            "night_end": str(data.get(w["night_end"], "06:00"))[:5]}


def summary(lang: str, rooms: list[dict], leading: str | None) -> str:
    """The rooms as text lines, with their role."""
    hu = lang == "hu"
    if not rooms:
        return "–"
    lines = []
    for i, r in enumerate(rooms, 1):
        n = lambda k: len(r.get(k) or [])
        if r["key"] == leading:
            role = "vezető (a kazánt vezérli)" if hu else "leading (drives the boiler)"
        elif r.get("trvs"):
            role = "szelepfejes" if hu else "TRV room"
        else:
            role = "megfigyelt (csak a kazánon át fűthető)" if hu else "watched (heated only through the boiler)"
        bits = [role, f"{n('sensors')} {'hőmérő' if hu else 'thermometer(s)'}"]
        if n("trvs"):
            bits.append(f"{n('trvs')} {'szelepfej' if hu else 'TRV head(s)'}")
        if n("windows"):
            bits.append(f"{n('windows')} {'ablak/ajtó' if hu else 'window/door'}")
        lines.append(f"{i}. {r['name']}: " + ", ".join(bits))
    return "\n".join(lines)

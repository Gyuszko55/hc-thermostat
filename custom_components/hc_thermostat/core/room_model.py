"""0.43.0 – the rooms of one boiler: "one room, one thermometer (or a group), none or several TRV heads, one boiler".

System level: the host instance (one boiler) is driven by the *leading room* (a room without a regulating TRV: its
thermometer is the house thermometer, `indoor_entity`). The house target is the host's schedule / presets / household
presence as before.

Room level (every other room):
- its temperature is the mean of its available thermometers (a dropped one is ignored);
- a TRV room regulates locally: every head gets the room's effective target, calibrated against the room's
  thermometers (`head_sensors` may give a head another thermometer, or "head": its own, no calibration); a room
  without a thermometer leaves its heads on their own sensors;
- a room without a TRV can only be reached through the boiler: it shows the house target and gets the radiator
  valve advice (core/rooms.py RoomMonitor); it never drives the boiler;
- room target: `follow` = the house target + `offset` (it follows night, away, presets and a manual house target),
  or `own` = its own home / night / away targets and night window (household vacation: the house's vacation target);
- per room presence (optional): sources whose state is the room's area (Bermuda-like phone room sensors, an
  input_select) or binary sensors (motion / occupancy: on = present). Present → the room's target; absent for
  `absent_min` minutes → the target − `setback` (never below the frost limit); while the household is away or on
  vacation the household target counts and no setback is added. Restart-safe: unknown sources hold the last state, and
  for a while after a start a "nobody here" does not start the absence clock;
- a manual target or preset set on the room's climate holds until the room's automatic target changes (schedule,
  presence, the house target it follows).

Storage: one `rooms` list in the host's options (dicts, see RoomSpec.as_dict) and `leading_room` (a room key). Without
`rooms` the list is derived from the legacy options (`room_sensors`, `room_trvs`, `trv_sensors`, `trv_offsets`,
`trv_calibration`, `room_trv_demand`), grouped by area: the behaviour stays exactly as before.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
import re
import statistics
import unicodedata

CONF_ROOM_LIST = "rooms"
CONF_LEADING = "leading_room"
FOLLOW, OWN = "follow", "own"
HEAD = "head"  # head_sensors value: the head's own thermometer, no calibration
DEFAULT_ABSENT_MIN = 15.0
DEFAULT_SETBACK = 2.0
SETTLE_S = 300.0  # after a start: "nobody here" does not start the absence clock yet
ROOM_PRESETS = ["auto", "home", "away"]

PRESENT, LEAVING, ABSENT = "present", "leaving", "absent"


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", plain).strip("_") or "room"


def _num(value, default: float, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _time_text(value, default: str) -> str:
    try:
        parts = [int(p) for p in str(value).split(":")[:2]]
        return f"{parts[0]:02d}:{(parts[1] if len(parts) > 1 else 0):02d}" if 0 <= parts[0] < 24 else default
    except (TypeError, ValueError):
        return default


def _ids(value, prefix: tuple[str, ...]) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    return [v for v in dict.fromkeys(value) if isinstance(v, str) and v.startswith(prefix)]


@dataclass
class RoomSpec:
    key: str
    name: str
    area: str | None = None
    sensors: list[str] = field(default_factory=list)
    trvs: list[str] = field(default_factory=list)
    head_sensors: dict[str, str] = field(default_factory=dict)  # head -> thermometer | "head"; absent: the room's
    mode: str = FOLLOW
    offset: float = 0.0
    target_home: float = 21.0
    target_night: float = 19.0
    target_away: float = 17.0
    night_start: str = "22:00"
    night_end: str = "06:00"
    presence: list[str] = field(default_factory=list)
    absent_min: float = DEFAULT_ABSENT_MIN
    setback: float = DEFAULT_SETBACK
    demand: bool = False  # a TRV room far below its target may ask the boiler for short burns

    @property
    def has_trv(self) -> bool:
        return bool(self.trvs)

    def head_sources(self) -> dict[str, list[str]]:
        """Head -> the thermometers its calibration follows ([]: its own sensor, no calibration)."""
        out = {}
        for head in self.trvs:
            chosen = self.head_sensors.get(head)
            if chosen == HEAD:
                out[head] = []
            elif isinstance(chosen, str) and "." in chosen:
                out[head] = [chosen]
            else:
                out[head] = list(self.sensors)
        return out

    def as_dict(self) -> dict:
        out = {"key": self.key, "name": self.name, "area": self.area, "sensors": list(self.sensors),
               "trvs": list(self.trvs), "mode": self.mode, "offset": self.offset,
               "presence": list(self.presence), "absent_min": self.absent_min, "setback": self.setback,
               "demand": self.demand}
        if self.head_sensors:
            out["head_sensors"] = dict(self.head_sensors)
        if self.mode == OWN:
            out.update(target_home=self.target_home, target_night=self.target_night, target_away=self.target_away,
                       night_start=self.night_start, night_end=self.night_end)
        return out


def parse_room(raw: dict, taken: set[str] | None = None) -> RoomSpec | None:
    """One room from the options (or the wizard); None when it is not a room. Lenient: bad values fall back."""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    key = slugify(raw.get("key") or raw.get("area") or name) if (raw.get("key") or raw.get("area") or name) else ""
    if not key:
        return None
    if taken is not None:
        base, n = key, 2
        while key in taken:
            key, n = f"{base}_{n}", n + 1
        taken.add(key)
    trvs = _ids(raw.get("trvs"), ("climate.",))
    heads = {}
    for head, value in (raw.get("head_sensors") or {}).items() if isinstance(raw.get("head_sensors"), dict) else ():
        if head in trvs and isinstance(value, str) and (value == HEAD or value.startswith("sensor.")):
            heads[head] = value
    mode = raw.get("mode") if raw.get("mode") in (FOLLOW, OWN) else FOLLOW
    return RoomSpec(
        key=key, name=name or key, area=raw.get("area") if isinstance(raw.get("area"), str) and raw.get("area") else None,
        sensors=_ids(raw.get("sensors"), ("sensor.",)), trvs=trvs, head_sensors=heads,
        mode=mode, offset=_num(raw.get("offset"), 0.0, -5.0, 5.0),
        target_home=_num(raw.get("target_home"), 21.0, 5.0, 30.0),
        target_night=_num(raw.get("target_night"), 19.0, 5.0, 30.0),
        target_away=_num(raw.get("target_away"), 17.0, 5.0, 30.0),
        night_start=_time_text(raw.get("night_start"), "22:00"), night_end=_time_text(raw.get("night_end"), "06:00"),
        presence=_ids(raw.get("presence"), ("sensor.", "binary_sensor.", "input_select.", "input_boolean.", "person.",
                                            "device_tracker.", "input_text.", "switch.")),
        absent_min=_num(raw.get("absent_min"), DEFAULT_ABSENT_MIN, 1.0, 720.0),
        setback=_num(raw.get("setback"), DEFAULT_SETBACK, 0.0, 10.0),
        demand=bool(raw.get("demand")) and bool(trvs),
    )


def parse_rooms(raw) -> list[RoomSpec]:
    taken: set[str] = set()
    out = []
    for item in raw if isinstance(raw, list) else []:
        spec = parse_room(item, taken)
        if spec is not None:
            out.append(spec)
    return out


def legacy_rooms(conf: dict, sensor_groups: dict[str, list[str]], trv_groups: dict[str, list[str]],
                 key_of, leading_name: str | None = None) -> tuple[list[RoomSpec], str | None]:
    """The room list of an instance saved before 0.43.0 (room name -> entities, grouped by area as before).

    key_of(name, entity_ids) -> (key, area_id). Behaviour stays the same: every room follows the house target with
    its `trv_offsets` value, no presence; the heads follow the thermometers `trv_sensors` / `trv_calibration` gave them;
    `room_trv_demand` is allowed for every TRV room. The leading room is the main thermometer's area (when known and
    not also one of the other rooms)."""
    chosen = conf.get("trv_sensors")
    offsets = conf.get("trv_offsets") or {}
    demand = bool(conf.get("room_trv_demand"))
    taken: set[str] = set()
    specs: list[RoomSpec] = []
    leading = None
    indoor = conf.get("indoor_entity")
    names = list(dict.fromkeys([*sensor_groups, *trv_groups]))
    if leading_name and indoor and leading_name not in names:
        key, area = key_of(leading_name, [indoor])
        key = _unique(key, taken)
        specs.append(RoomSpec(key=key, name=leading_name, area=area, sensors=[indoor]))
        leading = key
    for name in names:
        sensors, heads = list(sensor_groups.get(name, [])), list(trv_groups.get(name, []))
        head_sensors: dict[str, str] = {}
        if isinstance(chosen, dict):
            for head in heads:
                s = chosen.get(head)
                if isinstance(s, str) and "." in s:
                    if sensors != [s]:
                        head_sensors[head] = s
                else:
                    head_sensors[head] = HEAD
        elif not conf.get("trv_calibration"):
            head_sensors = {h: HEAD for h in heads}
        try:
            offset = float(offsets.get(name, 0.0)) if isinstance(offsets, dict) else 0.0
        except (TypeError, ValueError):
            offset = 0.0
        key, area = key_of(name, sensors + heads)
        specs.append(RoomSpec(key=_unique(key, taken), name=name, area=area, sensors=sensors, trvs=heads,
                              head_sensors=head_sensors, offset=offset, demand=demand and bool(heads)))
    return specs, leading


def _unique(key: str, taken: set[str]) -> str:
    base, n = key, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    taken.add(key)
    return key


def rooms_to_legacy(specs: list[RoomSpec], leading: str | None) -> dict:
    """The pre-0.43.0 options written next to `rooms` (so 0.42.0 still works after a rollback, and the cards that
    read `room_trvs` keep working)."""
    others = [s for s in specs if s.key != leading]
    sensors = list(dict.fromkeys(e for s in others for e in s.sensors if e.startswith("sensor.")))
    heads = list(dict.fromkeys(h for s in specs for h in s.trvs))
    trv_sensors = {}
    for s in specs:
        for head, src in s.head_sources().items():
            if src and src[0].startswith("sensor."):
                trv_sensors[head] = src[0]
    offsets = {s.name: s.offset for s in others if s.trvs and s.mode == FOLLOW and s.offset}
    return {"room_sensors": sensors, "room_trvs": heads, "trv_sensors": trv_sensors, "trv_offsets": offsets,
            "room_trv_demand": any(s.demand for s in specs if s.trvs and s.key != leading)}


def rooms_options(rooms: list[dict], leading: str | None, indoor: str | None) -> dict:
    """What the rooms write into the options: the list, the leading room, the legacy keys next to them (a rollback to
    0.42.0 and the cards keep working) and the house thermometer: the leading room's thermometers include it (an
    empty leading room gets it; one without it gives its first thermometer to the house: `indoor_entity`)."""
    specs = parse_rooms(rooms)
    if leading not in {s.key for s in specs}:
        leading = None
    out: dict = {}
    for s in specs:
        if s.key == leading:
            if not s.sensors and indoor:
                s.sensors = [indoor]
            elif s.sensors and indoor not in s.sensors:
                out["indoor_entity"] = s.sensors[0]
            s.demand = False  # the leading room drives the boiler itself
    out[CONF_ROOM_LIST] = [s.as_dict() for s in specs]
    out[CONF_LEADING] = leading
    out.update(rooms_to_legacy(specs, leading))
    return out


def group_mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


# --- presence --------------------------------------------------------------------------------------------------------
def presence_of(state: str | None, attributes: dict, domain: str, area_id: str | None, area_name: str | None) -> bool | None:
    """One source: True (here), False (not here) or None (unknown). On/off entities: on = here; others: their state
    (or their area_id attribute, Bermuda) names this room."""
    if state is None or state in ("unknown", "unavailable", ""):
        return None
    if domain in ("binary_sensor", "input_boolean", "switch"):
        return state == "on" if state in ("on", "off") else None
    names = {n.casefold() for n in (area_id, area_name) if n}
    if not names:
        return None
    if str(state).casefold() in names:
        return True
    attr = attributes.get("area_id") if isinstance(attributes, dict) else None
    if isinstance(attr, str) and attr and str(state).casefold() not in ("not_home", "away"):
        return attr.casefold() in names
    return False


class RoomPresence:
    """Present / leaving / absent of one room from its sources (see the module text)."""

    def __init__(self) -> None:
        self.absent_since: datetime | None = None
        self.absent = False

    def update(self, now: datetime, observations: list[bool | None], delay_s: float, settling: bool = False) -> str:
        known = [o for o in observations if o is not None]
        if any(known):
            self.absent_since, self.absent = None, False
            return PRESENT
        if not known:  # nothing to go by (a restart, sensors unknown): hold what was
            return ABSENT if self.absent else (LEAVING if self.absent_since is not None else PRESENT)
        if self.absent:
            return ABSENT
        if settling:  # just started: a "nobody here" may be the sources still waking up
            return LEAVING if self.absent_since is not None else PRESENT
        if self.absent_since is None:
            self.absent_since = now
        if (now - self.absent_since).total_seconds() >= delay_s:
            self.absent = True
            return ABSENT
        return LEAVING

    def state(self) -> dict:
        return {"absent_since": self.absent_since.isoformat() if self.absent_since else None, "absent": self.absent}

    def restore(self, data: dict) -> None:
        since = (data or {}).get("absent_since")
        try:
            self.absent_since = datetime.fromisoformat(since) if since else None
        except (TypeError, ValueError):
            self.absent_since = None
        self.absent = bool((data or {}).get("absent")) and self.absent_since is not None


# --- the room's target -----------------------------------------------------------------------------------------------
def _parse_time(text: str) -> time:
    parts = [int(p) for p in str(text).split(":")]
    return time(parts[0], parts[1] if len(parts) > 1 else 0)


def is_night(now: datetime, start: str, end: str) -> bool:
    s, e, current = _parse_time(start), _parse_time(end), now.time()
    if s == e:
        return False
    if s <= e:
        return s <= current < e
    return current >= s or current < e


@dataclass
class RoomTarget:
    target: float
    reason: str  # off | manual | preset_home | preset_away | follow | home | night | household_away | household_vacation | absent
    auto: float  # the automatic target (without a manual target / preset)
    base: float  # the target while present (before the setback)


class RoomControl:
    """A TRV room's target: automatic (follow / own schedule, household, presence), a manual target or preset on its
    climate until the automatic target changes, and on / off."""

    def __init__(self) -> None:
        self.presence = RoomPresence()
        self.manual: float | None = None
        self.preset: str | None = None  # None (auto) | "home" (as if present) | "away" (as if absent)
        self.enabled = True
        self.presence_state = PRESENT
        self._auto_key: tuple | None = None

    def target(self, spec: RoomSpec, now: datetime, house: float, household: str, frost: float,
               vacation: float, commit: bool = True) -> RoomTarget:
        """household: home | away | vacation (the host's active preset / household presence). commit=False: only
        look (a manual target that the change would end is left out, but not forgotten)."""
        if spec.mode == OWN:
            if household == "vacation":
                base, why = vacation, "household_vacation"
            elif household == "away":
                base, why = spec.target_away, "household_away"
            elif is_night(now, spec.night_start, spec.night_end):
                base, why = spec.target_night, "night"
            else:
                base, why = spec.target_home, "home"
        else:
            base, why = house + spec.offset, "follow"
        auto = base
        setback_ok = bool(spec.presence) and household == "home"
        if setback_ok and self.presence_state == ABSENT:
            auto, why = max(frost, base - spec.setback), "absent"
        auto = max(frost, auto)
        key = (why, round(auto, 2))
        changed = self._auto_key is not None and key != self._auto_key
        manual, preset = (None, None) if changed else (self.manual, self.preset)
        if commit:
            self.manual, self.preset = manual, preset  # a manual setting lasts until the next change
            self._auto_key = key
        if not self.enabled:
            return RoomTarget(frost, "off", auto, base)
        if manual is not None:
            return RoomTarget(max(frost, manual), "manual", auto, base)
        if preset == "home":
            return RoomTarget(max(frost, base), "preset_home", auto, base)
        if preset == "away":
            return RoomTarget(max(frost, base - spec.setback), "preset_away", auto, base)
        return RoomTarget(auto, why, auto, base)

    def set_preset(self, preset: str | None) -> None:
        self.manual = None
        self.preset = preset if preset in ("home", "away") else None

    def state(self) -> dict:
        return {"manual": self.manual, "preset": self.preset, "enabled": self.enabled,
                "auto_key": list(self._auto_key) if self._auto_key else None, "presence": self.presence.state()}

    def restore(self, data: dict) -> None:
        data = data or {}
        self.manual = float(data["manual"]) if isinstance(data.get("manual"), (int, float)) else None
        self.preset = data.get("preset") if data.get("preset") in ("home", "away") else None
        self.enabled = bool(data.get("enabled", True))
        key = data.get("auto_key")
        self._auto_key = (str(key[0]), float(key[1])) if isinstance(key, list) and len(key) == 2 else None
        self.presence.restore(data.get("presence") or {})
        self.presence_state = ABSENT if self.presence.absent else PRESENT

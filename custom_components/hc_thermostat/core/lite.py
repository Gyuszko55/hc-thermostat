"""0.79.2: HC Lite – a whole thermostat as a Shelly script (guard/shelly/hc_lite.js); HC only sets it up and reads it.

No Home Assistant here: the settings the instance sends (`settings_payload`), whether the device holds them
(`needs_push`) and how the device's status reads (`view`). The device heats on its own with or without HC.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

CTL = ("hyst", "tpi", "pid")  # 0.79.4: pid = TPI + an integral (the script's version 2)
NO_SENSOR = ("duty", "off")
SENSORS = ("bthomesensor", "temperature", "push")  # 0.79.6: push = a Wi-Fi H&T sends its reading
MODES = ("auto", "away", "off")
SOURCES = ("gas", "hp")  # 0.80.0: the heat source – a gas boiler, or a heat pump (which may also cool)
HVACS = ("heat", "cool")
PRESETS = ("off", "window", "vacation", "away", "comfort", "sleep", "manual", "schedule")  # 0.82.0, as the script reports


@dataclass(frozen=True)
class LiteSettings:
    sp_day: float = 21.0
    sp_night: float = 19.0
    sp_away: float = 16.0
    frost: float = 7.0
    day: str = "06:00"
    night: str = "22:00"
    day_we: str = "07:00"
    night_we: str = "23:00"
    ctl: str = "hyst"
    hyst: float = 0.4
    cycle: int = 1800
    kp: float = 0.5
    bias: float = 0.15
    ti: int = 14400  # 0.79.4: pid integral time, s
    boost: float = 1.0  # 0.79.8: boost from this many °C below the target (0: none)
    boost_end: float = 0.3  # 0.79.8: … until this close
    pre: int = 30  # 0.79.7: preheat, min per °C below the day target (0: none)
    pre_max: int = 120  # 0.79.7: the longest preheat, min
    min_on: int = 300
    min_off: int = 300
    max_on: int = 7200
    ns: str = "duty"
    don: int = 600
    doff: int = 2400
    sensor: str = "bthomesensor"
    sensor_id: int = 200
    sensor_max_age: int = 1800
    shadow: bool = True  # a new instance starts in shadow, as every HC instance does
    src: str = "gas"  # 0.80.0: gas | hp
    sc_day: float = 25.0  # 0.80.0: cooling targets (hp)
    sc_night: float = 26.0
    sc_away: float = 28.0
    hum_id: int = -1  # 0.80.0: the room's humidity: bthomesensor 200.., an add-on humidity 100.. (-1: none / the push)
    dew_id: int = -1  # 0.80.0: an add-on probe on the cooled flow pipe (-1: none)
    dew_margin: float = 2.0  # 0.80.0: cooling stops while the pipe is below dew point + this
    buf: tuple = ()  # 0.80.0: up to 3 buffer probes (add-on temperature ids), shown only
    bufn: tuple = ()  # 0.80.0: their names
    cf_delta: float = 1.0  # 0.82.0: comfort = the program's target + this …
    cf_time: int = 7200  # 0.82.0: … for this long (s)
    btn: int = -1  # 0.82.0: the BLU device (bthomedevice id) whose button pushes the relay takes (-1: none)

    @classmethod
    def from_conf(cls, conf: dict[str, Any]) -> "LiteSettings":
        base = cls()
        vals: dict[str, Any] = {}
        for f in fields(cls):
            key = f"lite_{f.name}"
            raw = conf.get(key, getattr(base, f.name))
            vals[f.name] = _clean(f.name, raw, getattr(base, f.name))
        return cls(**vals)


_RANGES = {"sp_day": (5, 30), "sp_night": (5, 30), "sp_away": (5, 30), "frost": (3, 12), "hyst": (0.1, 3),
           "cycle": (600, 7200), "kp": (0.05, 3), "bias": (0, 0.8), "ti": (1800, 86400), "boost": (0, 5), "boost_end": (0, 2), "pre": (0, 120), "pre_max": (0, 360), "min_on": (0, 3600), "min_off": (0, 3600),
           "max_on": (0, 86400), "don": (60, 7200), "doff": (60, 14400), "sensor_id": (0, 299),
           "sensor_max_age": (300, 7200), "sc_day": (16, 30), "sc_night": (16, 30), "sc_away": (16, 30),
           "hum_id": (-1, 299), "dew_id": (-1, 199), "dew_margin": (0.5, 5),
           "cf_delta": (0.5, 3), "cf_time": (1800, 21600), "btn": (-1, 299)}
_CHOICES = {"ctl": CTL, "ns": NO_SENSOR, "sensor": SENSORS, "src": SOURCES}


def _items(raw: Any) -> list:
    """A list, or a form's text "100, 102" / "top, bottom"."""
    if isinstance(raw, (list, tuple)):
        return list(raw)
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()]
    return []


def _buf(raw: Any) -> tuple:
    out = []
    for p in _items(raw):
        try:
            v = int(float(p))
        except (TypeError, ValueError):
            continue
        if 100 <= v <= 199 and len(out) < 3:
            out.append(v)
    return tuple(out)


def _clock(v: Any) -> str | None:
    """"6:00", "06:00" or a time selector's "06:00:00" → "06:00"; anything else None."""
    parts = str(v).split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    return f"{h:02d}:{m:02d}" if 0 <= h <= 23 and 0 <= m <= 59 else None


def _clean(name: str, raw: Any, default: Any) -> Any:
    if name in ("day", "night", "day_we", "night_we"):
        return _clock(raw) or default
    if name in _CHOICES:
        return raw if raw in _CHOICES[name] else default
    if name == "shadow":
        return bool(raw)
    if name == "buf":
        return _buf(raw)
    if name == "bufn":
        return tuple(str(p)[:16] for p in _items(raw)[:3])
    lo, hi = _RANGES[name]
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    if not lo <= v <= hi:
        return default
    return int(round(v)) if isinstance(default, int) else round(v, 2)


def settings_payload(s: LiteSettings) -> dict[str, Any]:
    """What the script's `set` takes (the same names as its own settings)."""
    return {f.name: (list(getattr(s, f.name)) if isinstance(getattr(s, f.name), tuple) else getattr(s, f.name)) for f in fields(s)}


def needs_push(device_cfg: dict[str, Any] | None, payload: dict[str, Any]) -> bool:
    """The device holds other settings than the instance (a new device, a reset, a change made elsewhere)."""
    if not isinstance(device_cfg, dict):
        return True
    for k, v in payload.items():
        d = device_cfg.get(k)
        if isinstance(v, float) or isinstance(d, float):
            try:
                if abs(float(d) - float(v)) > 1e-6:
                    return True
            except (TypeError, ValueError):
                return True
        elif d != v:
            return True
    return False


def sync_action(device_cfg: dict[str, Any] | None, payload: dict[str, Any], device_rev: Any, known_rev: int | None) -> str:
    """0.79.9: who is right when the device holds other settings than the instance.

    The script counts its settings revision up on every change, from HC or from its own web page. HC keeps the
    revision it last synced: a higher one on the device means a change made on the relay (the web set-up), which HC
    takes over ("adopt"); otherwise HC's own settings are the newer ones and go to the device ("push"). An older
    script without a revision, or a first sync, keeps the old rule: HC pushes."""
    if not needs_push(device_cfg, payload):
        return "none"
    if isinstance(device_rev, int) and not isinstance(device_rev, bool) and isinstance(known_rev, int) and device_rev > known_rev:
        return "adopt"
    return "push"


def options_from_device(device_cfg: dict[str, Any]) -> dict[str, Any]:
    """The device's settings as the instance's options (lite_*), cleaned the same way as the form's."""
    s = LiteSettings.from_conf({f"lite_{k}": v for k, v in (device_cfg or {}).items()})
    return {f"lite_{k}": (", ".join(map(str, v)) if isinstance(v, list) else v) for k, v in settings_payload(s).items()}


@dataclass(frozen=True)
class LiteView:
    temp: float | None
    target: float | None
    mode: str           # auto | away | off
    heating: bool       # the relay is on (in shadow: it would be)
    shadow: bool
    real_relay: bool | None
    period: str | None
    reason: str | None
    demand: float | None
    hold: dict | None
    starts_today: int | None
    on_min_today: int | None
    version: int | None
    integral: float | None = None  # 0.79.4: pid – the learnt part of the demand
    hvac: str = "heat"  # 0.80.0: heat | cool
    src: str = "gas"  # 0.80.0: gas | hp
    humidity: float | None = None
    dew_point: float | None = None
    pipe: float | None = None
    dew_stop: bool = False
    dew_warn: bool = False
    buffer: tuple = ()  # 0.80.0: ((name, °C or None), ...)
    preset: str = "schedule"  # 0.82.0: off | window | vacation | away | comfort | sleep | manual | schedule
    psrc: str | None = None  # 0.82.0: who asked for it: ha | web | button
    puntil: int | None = None  # 0.82.0: its end (unixtime), None: open-ended / by the program
    vacation: int | None = None
    window_s: int | None = None
    we_today: bool = False
    btn_ev: str | None = None


def view(status: dict[str, Any] | None) -> LiteView | None:
    if not isinstance(status, dict) or "mode" not in status:
        return None
    num = lambda k: status.get(k) if isinstance(status.get(k), (int, float)) and not isinstance(status.get(k), bool) else None  # noqa: E731
    mode = status.get("mode") if status.get("mode") in MODES else "auto"
    rr = status.get("real_relay")
    cfg = status.get("cfg") if isinstance(status.get("cfg"), dict) else {}
    return LiteView(temp=num("temp"), target=num("sp"), mode=mode, heating=bool(status.get("relay")),
                    shadow=bool(status.get("shadow")), real_relay=rr if isinstance(rr, bool) else None,
                    period=status.get("period"), reason=status.get("reason"), demand=num("demand"),
                    hold=status.get("hold") if isinstance(status.get("hold"), dict) else None,
                    starts_today=num("starts_today"), on_min_today=num("on_min_today"), version=num("v"),
                    integral=num("integral"), hvac="cool" if status.get("hvac") == "cool" else "heat",
                    src=cfg.get("src") if cfg.get("src") in SOURCES else "gas", humidity=num("hum"), dew_point=num("dew"),
                    pipe=num("pipe"), dew_stop=status.get("dew_stop") is True, dew_warn=status.get("dew_warn") is True,
                    buffer=_buffer(cfg, status.get("buf")),
                    preset=status.get("preset") if status.get("preset") in PRESETS else "schedule",
                    psrc=status.get("psrc") if status.get("psrc") in ("ha", "web", "button") else None,
                    puntil=_int(status.get("puntil")), vacation=_int(status.get("vac")), window_s=_int(status.get("win_s")),
                    we_today=status.get("we_today") is True,
                    btn_ev=status.get("btn_ev") if isinstance(status.get("btn_ev"), str) else None)


def _int(v: Any) -> int | None:
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _buffer(cfg: dict, vals: Any) -> tuple:
    ids = cfg.get("buf") if isinstance(cfg.get("buf"), list) else []
    names = cfg.get("bufn") if isinstance(cfg.get("bufn"), list) else []
    vals = vals if isinstance(vals, list) else []
    out = []
    for i, _ in enumerate(ids[:3]):
        v = vals[i] if i < len(vals) and isinstance(vals[i], (int, float)) and not isinstance(vals[i], bool) else None
        n = names[i] if i < len(names) and isinstance(names[i], str) and names[i] else None
        out.append((n, v))
    return tuple(out)


# ---------------------------------------------------------------------------------------------------------------- 0.82.0
# Home Assistant's side of the presets: presence, a calendar and windows turn into commands for the relay. The relay
# keeps every one of them with an end, so a lost Home Assistant never leaves it stuck. Pure: the instance gathers the
# inputs, this decides, the instance sends.

AWAY_FOR_S = 43200  # away from presence: 12 hours, renewed while still away
AWAY_RENEW_S = 39600  # renewed when less than 11 hours are left
AWAY_AFTER_S = 1200  # everyone away for 20 minutes
WINDOW_AFTER_S = 120  # a window open for 2 minutes
WINDOW_FOR_S = 3600  # frost while open, at most an hour
VACATION_WORDS = ("szabadság", "szabadsag", "nyaralás", "nyaralas", "távol", "tavol", "vacation", "holiday", "away")
HOME_DAY_WORDS = ("otthon", "itthon", "home office", "homeoffice", "home-office", "wfh")


def presence_away(domain: str, state: str | None) -> bool | None:
    """Away (True), home (False) or unknown (None) from a presence entity's state."""
    if state is None or state in ("unknown", "unavailable", ""):
        return None
    st = state.strip().lower()
    if domain in ("person", "device_tracker"):
        return st != "home"
    if st in ("home", "on", "otthon", "present", "igen", "jelen"):
        return False
    if st in ("not_home", "off", "away", "távol", "tavol", "szabadság", "szabadsag", "vacation", "nem", "absent"):
        return True
    return None


def calendar_kind(message: str | None) -> str | None:
    """"vacation", "home" (the weekend program today) or None from a calendar event's title."""
    m = (message or "").strip().lower()
    if not m:
        return None
    if any(w in m for w in VACATION_WORDS):
        return "vacation"
    if any(w in m for w in HOME_DAY_WORDS):
        return "home"
    return None


def plan_commands(now: float, v: LiteView | None, memo: dict, *, away: bool | None = None, away_since: float | None = None,
                  event: tuple[str | None, float | None] | None = None, today: str | None = None,
                  window_since: float | None = None, has_windows: bool = False) -> list[dict]:
    """The commands to send now (each with src "ha"); `memo` remembers what was sent for which episode.

    Presence: everyone away 20 min → away for 12 h (renewed while away); someone back → home, also over a vacation.
    A first look after a restart only takes a "home" as the starting point, so a hand-set away is kept.
    A gesture on the relay (the button) wins until the next real presence change: one episode, one command.
    Calendar: an active "vacation" event → vacation until its end (once per event); a "home" event → the weekend
    program today (once a day). Windows: any open for 2 min → frost for at most an hour (once per opening); closed
    → back."""
    out: list[dict] = []
    if v is None:
        return out
    if away is not None and away_since is not None:
        first = "pres" not in memo
        if not away:
            if first:
                memo["pres"] = away_since
            elif memo.get("pres") != away_since:
                memo["pres"] = away_since
                if v.preset in ("away", "vacation"):
                    out.append({"preset": "home"})
        elif now - away_since >= AWAY_AFTER_S:
            if memo.get("pres") != away_since:
                memo["pres"] = away_since
                if v.preset not in ("off", "vacation", "away"):
                    out.append({"mode": "away", "for": AWAY_FOR_S})
            elif v.preset == "away" and v.psrc == "ha" and v.puntil is not None and v.puntil - now < AWAY_RENEW_S:
                out.append({"mode": "away", "for": AWAY_FOR_S})
    if event is not None:
        kind, end = calendar_kind(event[0]), event[1]
        if kind == "vacation" and end is not None and end > now:
            key = f"{event[0]}|{int(end)}"
            if memo.get("cal") != key:
                memo["cal"] = key
                out.append({"vacation": int(end)})
        elif kind == "home" and today and memo.get("we") != today:
            memo["we"] = today
            if not v.we_today:
                out.append({"we_today": True})
    if has_windows:
        if window_since is not None and now - window_since >= WINDOW_AFTER_S:
            if memo.get("win") != window_since:
                memo["win"] = window_since
                out.append({"window": True, "for": WINDOW_FOR_S})
        elif window_since is None and memo.get("win") is not None:
            memo["win"] = None
            if v.preset == "window":
                out.append({"window": False})
    for c in out:
        c["src"] = "ha"
    return out

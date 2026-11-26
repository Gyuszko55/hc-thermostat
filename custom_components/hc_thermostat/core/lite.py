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
           "sensor_max_age": (300, 7200)}
_CHOICES = {"ctl": CTL, "ns": NO_SENSOR, "sensor": SENSORS}


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
    return {f.name: getattr(s, f.name) for f in fields(s)}


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
    return {f"lite_{k}": v for k, v in settings_payload(s).items()}


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


def view(status: dict[str, Any] | None) -> LiteView | None:
    if not isinstance(status, dict) or "mode" not in status:
        return None
    num = lambda k: status.get(k) if isinstance(status.get(k), (int, float)) and not isinstance(status.get(k), bool) else None  # noqa: E731
    mode = status.get("mode") if status.get("mode") in MODES else "auto"
    rr = status.get("real_relay")
    return LiteView(temp=num("temp"), target=num("sp"), mode=mode, heating=bool(status.get("relay")),
                    shadow=bool(status.get("shadow")), real_relay=rr if isinstance(rr, bool) else None,
                    period=status.get("period"), reason=status.get("reason"), demand=num("demand"),
                    hold=status.get("hold") if isinstance(status.get("hold"), dict) else None,
                    starts_today=num("starts_today"), on_min_today=num("on_min_today"), version=num("v"),
                    integral=num("integral"))

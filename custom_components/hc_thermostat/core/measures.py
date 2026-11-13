"""0.48.0: measurements – optional readings of the heat source and the rooms, and what HC works out of them.

Everything here is information: none of it changes a heating decision (the hot water signal of a combi boiler, which
pauses the fault watch like a heat pump's, is read by the coordinator as before). A reading that crosses its limit
(low or high water pressure, little fuel left, too many starts in an hour, a radiator that stays cold while its room
needs heat, a fault code) is a "measurement problem": the info panel lists it and the boiler problem sensor goes on.

- starts and run time: from the real heating signal (flame, else the reference / relay), per local day, kept for
  the season (from 1 September);
- COP: the heat given off (a heat meter) over the power taken (the instance's energy meter), from the increase of
  both meters per local day (a meter that resets or jumps back starts over, it is not counted);
- ΔT: flow − return;
- per room: radiator surface temperature (warm or not while the room needs heat), relative humidity, dew point and
  a mould risk from the hours of high humidity of the last day.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import math
import re

WATER_SOURCES = ("onoff_boiler", "modulating_boiler", "heat_pump", "electric_boiler", "district_heating",
                 "pellet_boiler", "external_heat")

# option key -> the heat sources that offer it
FIELDS: dict[str, tuple[str, ...]] = {
    "pressure_entity": WATER_SOURCES,
    "flow_temp_entity": WATER_SOURCES,
    "return_temp_entity": WATER_SOURCES,  # district heating had it before (return limit)
    "modulation_entity": ("modulating_boiler", "heat_pump", "air_conditioner"),
    "fault_code_entity": ("modulating_boiler", "heat_pump", "pellet_boiler", "external_heat", "air_conditioner"),
    "heat_output_entity": ("heat_pump", "air_conditioner"),
    "flue_temp_entity": ("pellet_boiler",),
    "fuel_level_entity": ("pellet_boiler",),
    "core_temp_entity": ("storage_heater",),
    "source_state_entity": ("external_heat",),
}
# the hot water signal (a heat pump had it before): combi boilers too
DHW_SOURCES = ("heat_pump", "onoff_boiler", "modulating_boiler")

DEFAULTS = {"pressure_min": 1.0, "pressure_max": 2.5, "fuel_min": 15.0, "starts_per_hour_max": 6.0,
            "radiator_cold_min": 20.0}

_NO_FAULT = {"", "0", "0.0", "none", "no", "ok", "off", "false", "no error", "no_error", "nincs", "nincs hiba",
             "normal", "normál", "unknown", "unavailable"}
_KEEP_DAYS = 400
_HUMID_HIGH = 70.0  # % – a wall a few degrees colder than the air is near condensation (mould grows from ~80 %)
_HUMID_MID = 60.0
_HIGH_HOURS = 6  # hours of high humidity within the last 24 for "high"
_RADIATOR_WARM = 5.0  # °C above the room: the radiator gets heat
_RADIATOR_WARM_MIN = 30.0  # … and at least this warm


def fields_for(source: str | None) -> list[str]:
    return [k for k, sources in FIELDS.items() if source in sources]


def to_kwh(value: float | None, unit: str | None) -> float | None:
    """An energy reading in kWh (Wh, kWh, MWh, MJ, GJ); None for an unknown unit."""
    if value is None:
        return None
    u = str(unit or "").strip().lower()
    factor = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0, "mj": 1 / 3.6, "gj": 1000 / 3.6}.get(u)
    return value * factor if factor is not None else None


def dew_point(temp: float | None, humidity: float | None) -> float | None:
    """Magnus formula, °C."""
    if temp is None or humidity is None or not 0 < humidity <= 100:
        return None
    a, b = 17.62, 243.12
    g = math.log(humidity / 100.0) + a * temp / (b + temp)
    return round(b * g / (a - g), 1)


def fault_active(state: str | None, ok_values: tuple[str, ...] = ()) -> bool:
    """0.48.1: "00", "F.00", "0x00", "E-0" are no fault either (only zeros after a letter prefix), and the values
    the options give as "no fault"."""
    if state is None:
        return False
    text = str(state).strip().lower()
    if text in _NO_FAULT or text in {v.strip().lower() for v in ok_values if str(v).strip()}:
        return False
    return not re.fullmatch(r"(0x|[a-z]{1,3}[.\-_ ]?)?0+(\.0+)?", text)


def season_start(day: date) -> date:
    return date(day.year if day.month >= 9 else day.year - 1, 9, 1)


@dataclass
class Limits:
    pressure_min: float = DEFAULTS["pressure_min"]
    pressure_max: float = DEFAULTS["pressure_max"]
    fuel_min: float = DEFAULTS["fuel_min"]
    starts_per_hour_max: float = DEFAULTS["starts_per_hour_max"]
    radiator_cold_min: float = DEFAULTS["radiator_cold_min"]
    fault_ok: tuple[str, ...] = ()  # 0.48.1: the source's own "no fault" values

    @classmethod
    def from_conf(cls, conf: dict) -> "Limits":
        out = cls()
        for k, v in DEFAULTS.items():
            try:
                setattr(out, k, float(conf.get(k, v)))
            except (TypeError, ValueError):
                setattr(out, k, v)
        out.fault_ok = tuple(x.strip() for x in str(conf.get("fault_ok_values") or "").split(",") if x.strip())
        return out


class RunCounter:
    """Starts and run time of the heat source, per local day."""

    def __init__(self) -> None:
        self.days: dict[str, dict] = {}
        self.on: bool | None = None
        self.since: datetime | None = None
        self.recent: deque[datetime] = deque(maxlen=200)  # start times (the last hour counts)

    def update(self, now: datetime, on: bool | None) -> None:
        if on is None:
            self.on, self.since = None, None
            return
        day = self.days.setdefault(now.date().isoformat(), {"starts": 0, "on_s": 0.0})
        if self.on and self.since is not None:  # the time since the last look (a long gap – a restart – is not counted)
            day["on_s"] += max(0.0, min((now - self.since).total_seconds(), 600.0))
        if on and self.on is False:
            day["starts"] += 1
            self.recent.append(now)
        self.on, self.since = on, now
        self._trim(now)

    def _trim(self, now: datetime) -> None:
        if len(self.days) > _KEEP_DAYS:
            for k in sorted(self.days)[:-_KEEP_DAYS]:
                del self.days[k]

    def starts_last_hour(self, now: datetime) -> int:
        return sum(1 for t in self.recent if now - t <= timedelta(hours=1))

    def summary(self, now: datetime) -> dict:
        today = now.date()
        week = {(today - timedelta(days=i)).isoformat() for i in range(7)}
        season = season_start(today).isoformat()
        sums = lambda keys: (sum(self.days[k]["starts"] for k in keys), sum(self.days[k]["on_s"] for k in keys) / 3600)
        t = self.days.get(today.isoformat(), {"starts": 0, "on_s": 0.0})
        ws, wh = sums([k for k in self.days if k in week])
        ss, sh = sums([k for k in self.days if k >= season])
        return {"starts_today": t["starts"], "hours_today": round(t["on_s"] / 3600, 2),
                "starts_week": ws, "hours_week": round(wh, 1), "starts_season": ss, "hours_season": round(sh, 1),
                "starts_last_hour": self.starts_last_hour(now), "season_from": season}

    def state(self) -> dict:
        return {"days": self.days, "recent": [t.isoformat() for t in self.recent]}

    def restore(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        days = data.get("days")
        if isinstance(days, dict):
            self.days = {k: {"starts": int(v.get("starts", 0)), "on_s": float(v.get("on_s", 0.0))}
                         for k, v in days.items() if isinstance(v, dict)}
        for t in data.get("recent") or []:
            try:
                self.recent.append(datetime.fromisoformat(t))
            except (TypeError, ValueError):
                pass


class EnergyDays:
    """The increase of two meters (heat given off, power taken) per local day – the COP."""

    def __init__(self) -> None:
        self.days: dict[str, dict] = {}
        self.last: dict[str, float] = {}

    def update(self, now: datetime, heat_kwh: float | None, power_kwh: float | None) -> None:
        day = self.days.setdefault(now.date().isoformat(), {"heat": 0.0, "power": 0.0})
        for key, value in (("heat", heat_kwh), ("power", power_kwh)):
            if value is None:
                continue
            last = self.last.get(key)
            if last is not None and 0 <= value - last < 100.0:  # a reset or a jump back starts over
                day[key] += value - last
            self.last[key] = value
        if len(self.days) > _KEEP_DAYS:
            for k in sorted(self.days)[:-_KEEP_DAYS]:
                del self.days[k]

    @staticmethod
    def _cop(heat: float, power: float) -> float | None:
        return round(heat / power, 2) if power >= 0.2 and heat > 0 else None

    def summary(self, now: datetime) -> dict:
        today = now.date()
        week = {(today - timedelta(days=i)).isoformat() for i in range(7)}
        season = season_start(today).isoformat()
        pick = lambda keys: (sum(self.days[k]["heat"] for k in keys), sum(self.days[k]["power"] for k in keys))
        th, tp = pick([k for k in self.days if k == today.isoformat()])
        wh, wp = pick([k for k in self.days if k in week])
        sh, sp = pick([k for k in self.days if k >= season])
        return {"cop_today": self._cop(th, tp), "cop_week": self._cop(wh, wp), "cop_season": self._cop(sh, sp),
                "heat_today_kwh": round(th, 2), "power_today_kwh": round(tp, 2),
                "heat_season_kwh": round(sh, 1), "power_season_kwh": round(sp, 1), "season_from": season}

    def state(self) -> dict:
        return {"days": self.days, "last": self.last}

    def restore(self, data: dict) -> None:
        if not isinstance(data, dict):
            return
        if isinstance(data.get("days"), dict):
            self.days = {k: {"heat": float(v.get("heat", 0.0)), "power": float(v.get("power", 0.0))}
                         for k, v in data["days"].items() if isinstance(v, dict)}
        if isinstance(data.get("last"), dict):
            self.last = {k: float(v) for k, v in data["last"].items() if isinstance(v, (int, float))}


class Humidity:
    """Hourly humidity samples of one room (the last day): the mould risk."""

    def __init__(self) -> None:
        self.hours: dict[str, float] = {}  # "YYYY-MM-DDTHH" -> highest relative humidity of that hour

    def update(self, now: datetime, rh: float | None) -> None:
        if rh is None or not 0 < rh <= 100:
            return
        key = now.strftime("%Y-%m-%dT%H")
        self.hours[key] = max(rh, self.hours.get(key, 0.0))
        cut = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H")
        for k in [k for k in self.hours if k <= cut]:
            del self.hours[k]

    def risk(self, rh: float | None) -> str | None:
        if rh is None and not self.hours:
            return None
        high = sum(1 for v in self.hours.values() if v >= _HUMID_HIGH)
        if high >= _HIGH_HOURS:
            return "high"
        if high or (rh is not None and rh >= _HUMID_MID):
            return "moderate"
        return "low"


class RadiatorWatch:
    """A radiator that stays cold while its room needs heat and the heat source runs.

    0.48.1 (outside review): the minutes of heating are added up – a PWM burn of 5–12 minutes never reached the
    20-minute limit when every pause started the count again. It starts again only when the radiator got warm or the
    room needs no more heat. "Warm": above the room by 40 % of the flow's lead over it when the flow is measured
    (at least 3 °C), else 5 °C and 30 °C – a heat pump's lukewarm water 3 °C and 25 °C."""

    def __init__(self) -> None:
        self.cold_s = 0.0
        self.last: datetime | None = None

    @property
    def cold_since(self):  # kept for the info panel and the old tests: "cold" while minutes are counted
        return self.last if self.cold_s > 0 else None

    @staticmethod
    def warm(radiator: float, room: float | None, flow: float | None = None, low_temp: bool = False) -> bool:
        base = room if room is not None else 20.0
        if flow is not None and flow > base:
            return radiator >= base + max(3.0, 0.4 * (flow - base))
        if low_temp:
            return radiator >= max(25.0, base + 3.0)
        return radiator >= max(_RADIATOR_WARM_MIN, base + _RADIATOR_WARM)

    def update(self, now: datetime, radiator: float | None, room: float | None, heating: bool,
               needs_heat: bool, flow: float | None = None, low_temp: bool = False) -> str | None:
        """'warm', 'cold' (minutes of heating counted, the caller compares them to the limit), 'idle' or None."""
        last, self.last = self.last, now
        if radiator is None:
            self.cold_s = 0.0
            return None
        if self.warm(radiator, room, flow, low_temp):
            self.cold_s = 0.0
            return "warm"
        if not needs_heat:
            self.cold_s = 0.0
            return "idle"
        if heating and last is not None:
            self.cold_s += max(0.0, min((now - last).total_seconds(), 600.0))
        return "cold" if self.cold_s > 0 or heating else "idle"

    def cold_for_min(self, now: datetime | None = None) -> float:
        return self.cold_s / 60


def source_problems(values: dict, limits: Limits, starts_last_hour: int, counted: bool) -> list[str]:
    """The heat source's measurement problems (codes)."""
    out = []
    p = values.get("pressure")
    if isinstance(p, (int, float)):
        if p < limits.pressure_min:
            out.append("pressure_low")
        elif p > limits.pressure_max:
            out.append("pressure_high")
    fuel = values.get("fuel_level")
    if isinstance(fuel, (int, float)) and limits.fuel_min > 0 and fuel < limits.fuel_min:
        out.append("fuel_low")
    if counted and limits.starts_per_hour_max > 0 and starts_last_hour > limits.starts_per_hour_max:
        out.append("short_cycling")
    if fault_active(values.get("fault_code"), limits.fault_ok):
        out.append("fault_code")
    return out

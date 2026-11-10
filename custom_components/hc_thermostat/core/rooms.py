"""Room thermometers next to the main one (single zone): the main thermometer stays in charge.

Each room's deviation from the main thermometer is gathered only in quiet times (the house is regulating or
at its target: no heat-up, after-heat, open window or restart) as hourly means. Over the last 72 hours, with at
least 36 such hours, a room whose mean deviation is beyond the tolerance gets advice: without a TRV the radiator
valve should be turned down (warmer room) or up (colder room). The room readings never switch the boiler.

Advice is announced when it first appears, again after `REPEAT_S` if it still stands, and once more when the
room is back within the tolerance ("ok").
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import statistics

WINDOW_H = 72
MIN_HOURS = 36
MIN_SAMPLES_PER_HOUR = 20  # 10 minutes of quiet 30 s steps make an hour count
REPEAT_S = 3 * 24 * 3600.0

DOWN, UP, OK, LEARNING = "down", "up", "ok", "learning"


@dataclass(frozen=True)
class RoomAdvice:
    room: str
    advice: str  # down | up | ok | learning
    deviation: float | None  # mean (room − main) over the window, °C
    hours: int


@dataclass(frozen=True)
class Announcement:
    room: str
    advice: str  # down | up | ok
    deviation: float
    hours: int


class RoomMonitor:
    def __init__(self, tolerance: float = 0.5) -> None:
        self.tolerance = tolerance
        self.hours: dict[str, deque[tuple[str, float]]] = {}  # room -> (hour start iso, mean deviation)
        self._hour: str | None = None
        self._acc: dict[str, list[float]] = {}
        self.announced: dict[str, tuple[str, str]] = {}  # room -> (advice, when iso)

    # --- gathering ------------------------------------------------------------------------------------
    def update(self, now: datetime, main: float | None, rooms: dict[str, float | None], quiet: bool) -> None:
        hour = now.replace(minute=0, second=0, microsecond=0).isoformat()
        if self._hour is not None and hour != self._hour:
            self._close_hour()
        self._hour = hour
        if not quiet or main is None:
            return
        for room, value in rooms.items():
            if value is not None:
                self._acc.setdefault(room, []).append(value - main)

    def _close_hour(self) -> None:
        for room, values in self._acc.items():
            if len(values) >= MIN_SAMPLES_PER_HOUR:
                self.add_hour(room, self._hour, statistics.fmean(values))
        self._acc = {}

    def add_hour(self, room: str, hour_iso: str, deviation: float) -> None:
        hours = self.hours.setdefault(room, deque(maxlen=WINDOW_H * 2))
        if not any(h == hour_iso for h, _ in hours):
            hours.append((hour_iso, deviation))

    # --- judging --------------------------------------------------------------------------------------
    def advice(self, now: datetime, rooms: list[str]) -> list[RoomAdvice]:
        since = now - timedelta(hours=WINDOW_H)
        out = []
        for room in rooms:
            recent = [d for h, d in self.hours.get(room, ()) if datetime.fromisoformat(h) >= since]
            if len(recent) < MIN_HOURS:
                out.append(RoomAdvice(room, LEARNING, round(statistics.fmean(recent), 2) if recent else None, len(recent)))
                continue
            mean = statistics.fmean(recent)
            kind = DOWN if mean > self.tolerance else UP if mean < -self.tolerance else OK
            out.append(RoomAdvice(room, kind, round(mean, 2), len(recent)))
        return out

    def announcements(self, now: datetime, advice: list[RoomAdvice]) -> list[Announcement]:
        """What to tell now: new advice, advice standing for REPEAT_S again, or back to ok after advice."""
        out = []
        for a in advice:
            if a.advice == LEARNING or a.deviation is None:
                continue
            last = self.announced.get(a.room)
            if a.advice == OK:
                if last is not None and last[0] != OK:
                    out.append(Announcement(a.room, OK, a.deviation, a.hours))
                    self.announced[a.room] = (OK, now.isoformat())
                continue
            if last is None or last[0] != a.advice or (now - datetime.fromisoformat(last[1])).total_seconds() >= REPEAT_S:
                out.append(Announcement(a.room, a.advice, a.deviation, a.hours))
                self.announced[a.room] = (a.advice, now.isoformat())
        return out

    # --- persistence ----------------------------------------------------------------------------------
    def state(self) -> dict:
        return {"hours": {r: list(h) for r, h in self.hours.items()}, "announced": dict(self.announced)}

    def restore(self, data: dict) -> None:
        for room, hours in (data.get("hours") or {}).items():
            for hour_iso, deviation in hours:
                self.add_hour(room, hour_iso, float(deviation))
        self.announced = {r: tuple(v) for r, v in (data.get("announced") or {}).items()}


def room_text(a: Announcement, lang: str = "hu", trv: bool = False) -> str:
    d, days = abs(a.deviation), max(1, round(a.hours / 24))
    if trv and a.advice in (DOWN, UP):
        dtxt = f"{d:.1f}".replace(".", ",") if lang == "hu" else f"{d:.1f}"
        if lang == "hu":
            if a.advice == DOWN:
                return (f"{a.room}: az utóbbi ~{days} napban átlagosan {dtxt} °C-kal melegebb a fő hőmérőnél, pedig a "
                        "termosztátfej a ház célját kapja. Nézd meg a fejet: lehet, hogy nem zár (beragadt szeleptüske, "
                        "rossz adapter), vagy a saját hőmérője túl hideget mér (kalibrálás, pl. Better Thermostat).")
            return (f"{a.room}: az utóbbi ~{days} napban átlagosan {dtxt} °C-kal hidegebb a fő hőmérőnél, pedig a "
                    "termosztátfej a ház célját kapja. Lehet, hogy a radiátor kevés ehhez a helyiséghez, vagy a fej nem "
                    "nyit eléggé (saját hőmérője túl meleget mér a radiátor mellett).")
        if a.advice == DOWN:
            return (f"{a.room}: over ~{days} days {dtxt} °C warmer than the main thermometer although its TRV head has the "
                    "house target. Check the head: it may not close (stuck pin, wrong adapter) or its own sensor reads too low.")
        return (f"{a.room}: over ~{days} days {dtxt} °C colder than the main thermometer although its TRV head has the "
                "house target. The radiator may be too small for the room, or the head does not open enough.")
    if lang == "hu":
        dtxt = f"{d:.1f}".replace(".", ",")
        if a.advice == OK:
            signed = f"{a.deviation:+.1f}".replace(".", ",")
            return f"{a.room}: rendben, az eltérés a fő hőmérőtől most {signed} °C."
        how = "kicsit (kb. negyed osztással)" if d < 1.0 else "kb. fél osztással"
        if a.advice == DOWN:
            return (f"{a.room}: az utóbbi ~{days} napban átlagosan {dtxt} °C-kal melegebb a fő hőmérőnél. "
                    f"Vedd lejjebb a radiátor termofejét {how}.")
        return (f"{a.room}: az utóbbi ~{days} napban átlagosan {dtxt} °C-kal hidegebb a fő hőmérőnél. "
                f"Vedd feljebb a radiátor termofejét {how}.")
    if a.advice == OK:
        return f"{a.room}: fine, now {a.deviation:+.1f} °C from the main thermometer."
    how = "a little (about a quarter step)" if d < 1.0 else "about half a step"
    if a.advice == DOWN:
        return f"{a.room}: over ~{days} days {d:.1f} °C warmer than the main thermometer. Turn the radiator valve down {how}."
    return f"{a.room}: over ~{days} days {d:.1f} °C colder than the main thermometer. Turn the radiator valve up {how}."

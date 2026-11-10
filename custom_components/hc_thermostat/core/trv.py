"""TRV rooms of a single zone: the main thermometer stays in charge of the boiler.

A room with a thermostatic radiator valve head (climate entity) gets the house target: its head then throttles a
warm room by itself, so no "turn the valve" advice is needed there. A target set on the head by hand is respected
until the house target changes. Optionally a TRV room that stays well below its target while its head is open
may ask for short burns (`RoomDemand`) – only while the main thermometer is not above its own target.

0.30.0 – per room target and calibration:
- every TRV room may have an offset to the house target (`trv_offsets`, e.g. bedroom −2, bathroom +1), so it still
  follows the schedule (night, away);
- calibration (`trv_calibration`): a head measures next to the hot radiator and closes too early. Where the room has
  its own thermometer, the difference head − room is followed slowly (30 minute smoothing, at most ±5 °C) and added
  to the target written to the head: the head then aims at the right room temperature by its own sensor. A change
  that only comes from the calibration is written at most every 30 minutes (battery, valve motor).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

MIN_CHANGE = 0.25  # °C – smaller differences are not written to the head
DEMAND_GAP = 1.0  # °C below the target …
DEMAND_HOLD_S = 30 * 60.0  # … for this long before the room may ask for heat
CAL_TAU_S = 30 * 60.0  # calibration smoothing
CAL_MAX = 5.0  # °C – a larger difference is a misplaced sensor, not a calibration
CAL_REWRITE_S = 30 * 60.0  # a calibration-only change is written this seldom


@dataclass
class TrvPlan:
    """Which target to write to one head (None: leave it)."""

    target: float | None
    reason: str  # write | same | manual | off | unavailable


class TrvTargets:
    def __init__(self) -> None:
        self.sent: dict[str, float] = {}  # head -> target last written by us
        self.for_house: dict[str, float] = {}  # head -> house (room) target that write was for
        self.last_write: dict[str, datetime] = {}

    def plan(self, head: str, house_target: float, state: str | None, current_target: float | None,
             lo: float | None = None, hi: float | None = None, want: float | None = None,
             now: datetime | None = None) -> TrvPlan:
        """house_target: the room's own target (house target + offset); want: what to write (with calibration)."""
        if state in (None, "unavailable", "unknown"):
            return TrvPlan(None, "unavailable")
        if state == "off":
            return TrvPlan(None, "off")  # switched off on purpose: not ours to turn on
        want = house_target if want is None else want
        if lo is not None:
            want = max(want, lo)
        if hi is not None:
            want = min(want, hi)
        sent, for_house = self.sent.get(head), self.for_house.get(head)
        if (sent is not None and for_house == house_target and current_target is not None
                and abs(current_target - sent) >= MIN_CHANGE):
            return TrvPlan(None, "manual")  # changed on the head since our write: respect it until the house target changes
        if current_target is not None and abs(current_target - want) < MIN_CHANGE:
            self.sent[head], self.for_house[head] = current_target, house_target
            return TrvPlan(None, "same")
        last = self.last_write.get(head)
        if (now is not None and last is not None and for_house == house_target
                and (now - last).total_seconds() < CAL_REWRITE_S):
            return TrvPlan(None, "wait")  # only the calibration moved: spare the battery
        return TrvPlan(want, "write")

    def written(self, head: str, target: float, house_target: float, now: datetime | None = None) -> None:
        self.sent[head], self.for_house[head] = target, house_target
        if now is not None:
            self.last_write[head] = now

    def state(self) -> dict:
        return {"sent": dict(self.sent), "for_house": dict(self.for_house),
                "last_write": {h: t.isoformat() for h, t in self.last_write.items()}}

    def restore(self, data: dict) -> None:
        self.sent = {k: float(v) for k, v in (data.get("sent") or {}).items()}
        self.for_house = {k: float(v) for k, v in (data.get("for_house") or {}).items()}
        self.last_write = {k: datetime.fromisoformat(v) for k, v in (data.get("last_write") or {}).items()}


class TrvCalibration:
    """Head sensor − room thermometer, smoothed; added to the target written to the head."""

    def __init__(self) -> None:
        self.offset: dict[str, float] = {}
        self._last: dict[str, datetime] = {}

    def update(self, head: str, head_temp: float | None, room_temp: float | None, now: datetime) -> float:
        if head_temp is None or room_temp is None:
            return self.offset.get(head, 0.0)  # no fresh pair: keep what was learned
        raw = max(-CAL_MAX, min(CAL_MAX, head_temp - room_temp))
        last = self._last.get(head)
        self._last[head] = now
        if head not in self.offset:
            self.offset[head] = raw  # first pair: start from it
        else:
            dt = (now - last).total_seconds() if last is not None else 0.0  # restored: the first pair only times
            a = 1.0 - math.exp(-max(dt, 0.0) / CAL_TAU_S)
            self.offset[head] += a * (raw - self.offset[head])
        return round(self.offset[head], 2)

    def state(self) -> dict:
        return {h: round(v, 3) for h, v in self.offset.items()}

    def restore(self, data: dict) -> None:
        self.offset = {k: float(v) for k, v in (data or {}).items()}


class RoomDemand:
    """A TRV room far below its target with its head open for a while asks for heat."""

    def __init__(self) -> None:
        self.since: dict[str, datetime] = {}

    def update(self, now: datetime, rooms: dict[str, tuple[float | None, float | None, bool]]) -> list[str]:
        """rooms: name -> (room temperature, room target, head heating). Returns the rooms asking now."""
        asking = []
        for room, (temp, target, heating) in rooms.items():
            if temp is None or target is None or not heating or temp > target - DEMAND_GAP:
                self.since.pop(room, None)
                continue
            start = self.since.setdefault(room, now)
            if (now - start).total_seconds() >= DEMAND_HOLD_S:
                asking.append(room)
        for room in set(self.since) - set(rooms):
            self.since.pop(room)
        return sorted(asking)

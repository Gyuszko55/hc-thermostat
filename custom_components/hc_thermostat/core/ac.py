"""Air conditioner (air-to-air heat pump) by an external room thermometer – a "virtual i-Feel".

A modern inverter unit regulates itself: it must not be switched on and off to regulate, only its setpoint is
moved so that it holds the target measured by the room thermometer instead of its own sensor (which, inside the
indoor unit, reads warmer or colder than the room). Setpoint written to the unit:

    target + offset + integral

- offset: the smoothed difference between the unit's own reading and the room thermometer (`OFFSET_TAU_S`);
- integral: a slow correction of what is left (`ac_ki_per_hour` °C of setpoint per °C error per hour, ±`INTEGRAL_MAX`),
;
- rounded to the unit's step and limits – towards what the room needs once it is more than `BAND` past the target –,
  changed at most every `ac_min_change_s` (a new target or mode at once), with a hysteresis of 3/4 step except for a
  step in the needed direction.

Pause: a unit cannot be set below its minimum (heating) or above its maximum (cooling). When the setpoint is
pinned there and the room is still past the target for `PAUSE_AFTER_S`, the unit is switched off – the only
switching, and a slow one – and back on when the room falls (heating) / rises (cooling) past the target.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

OFFSET_TAU_S = 20 * 60.0
INTEGRAL_MAX = 2.0
BAND = 0.2  # room past the target by more than this: round the setpoint towards the correction
PAUSE_AFTER_S = 10 * 60.0
PAUSE_MARGIN = 0.3  # room past the target by this much (with the setpoint pinned) starts the pause clock
RESUME_MARGIN = 0.2  # room back past the target the other way by this much ends the pause


@dataclass(frozen=True)
class AcCommand:
    mode: str  # heat | cool | off
    setpoint: float | None
    paused: bool = False


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class AcController:
    def __init__(self, ki_per_hour: float = 0.5, min_change_s: float = 600.0) -> None:
        self.ki_per_hour = ki_per_hour
        self.min_change_s = min_change_s
        self.offset: float | None = None
        self.integral = 0.0
        self.sent: float | None = None
        self.changed: datetime | None = None
        self.mode: str | None = None
        self.target: float | None = None
        self.paused = False
        self._pinned_since: datetime | None = None
        self._last: datetime | None = None

    def step(self, now: datetime, mode: str, target: float, room: float | None, unit: float | None,
             step: float = 1.0, lo: float = 16.0, hi: float = 30.0) -> AcCommand:
        dt = 0.0 if self._last is None else max((now - self._last).total_seconds(), 0.0)
        self._last = now
        new_mode, new_target = mode != self.mode, target != self.target
        if new_mode:
            self.integral, self.paused, self._pinned_since = 0.0, False, None
        if unit is not None and room is not None:
            diff = unit - room
            self.offset = diff if self.offset is None else self.offset + (diff - self.offset) * min(1.0, dt / OFFSET_TAU_S)
        offset = self.offset or 0.0
        error = None if room is None else target - room  # >0: the room is colder than wanted
        if error is not None and dt > 0 and not self.paused:
            candidate = _clamp(self.integral + self.ki_per_hour * error * dt / 3600, -INTEGRAL_MAX, INTEGRAL_MAX)
            raw = target + offset + candidate
            # Anti-windup: do not push further past a limit the unit cannot follow.
            if not ((raw > hi and error > 0) or (raw < lo and error < 0)):
                self.integral = candidate
        raw = target + offset + self.integral
        # With a whole-degree unit the right value often lies between two steps: round towards what the room
        # needs (down when it is already warm, up when it is cold), and let such a step through the hysteresis.
        if error is not None and error < -BAND:
            wanted = _clamp(math.floor(raw / step) * step, lo, hi)
        elif error is not None and error > BAND:
            wanted = _clamp(math.ceil(raw / step) * step, lo, hi)
        else:
            wanted = _clamp(round(raw / step) * step, lo, hi)
        helps = error is not None and self.sent is not None and (
            (error < -BAND and wanted < self.sent) or (error > BAND and wanted > self.sent))

        # Pause at the unit's limit when the room is still past the target.
        if mode in ("heat", "cool") and room is not None:
            pinned = (mode == "heat" and wanted <= lo and room >= target + PAUSE_MARGIN) or \
                     (mode == "cool" and wanted >= hi and room <= target - PAUSE_MARGIN)
            if self.paused:
                if (mode == "heat" and room <= target - RESUME_MARGIN) or (mode == "cool" and room >= target + RESUME_MARGIN) or new_target:
                    self.paused, self._pinned_since = False, None
            elif pinned:
                self._pinned_since = self._pinned_since or now
                if (now - self._pinned_since).total_seconds() >= PAUSE_AFTER_S:
                    self.paused = True
            else:
                self._pinned_since = None

        due = self.changed is None or (now - self.changed).total_seconds() >= self.min_change_s
        if self.sent is None or new_mode or new_target or (
                wanted != self.sent and (abs(raw - self.sent) >= 0.75 * step or helps) and due):
            if wanted != self.sent:
                self.changed = now
            self.sent = wanted
        self.mode, self.target = mode, target
        if mode == "off":
            return AcCommand("off", None)
        return AcCommand("off" if self.paused else mode, self.sent, self.paused)

    @property
    def raw_offset(self) -> float:
        return round((self.offset or 0.0) + self.integral, 2)

    def state(self) -> dict:
        return {"offset": self.offset, "integral": self.integral, "sent": self.sent, "mode": self.mode,
                "target": self.target, "paused": self.paused,
                "changed": self.changed.isoformat() if self.changed else None}

    def restore(self, data: dict) -> None:
        self.offset = data.get("offset")
        self.integral = float(data.get("integral") or 0.0)
        self.sent = data.get("sent")
        self.mode = data.get("mode")
        self.target = data.get("target")
        self.paused = bool(data.get("paused"))
        self.changed = datetime.fromisoformat(data["changed"]) if data.get("changed") else None

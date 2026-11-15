"""0.54.0 – the worked-out target is not the target given out: a mixing circuit (and later the heat pump) gets a new
flow target only now and then.

The raw target may move every 30 seconds (a zone valve opening, a noisy thermometer); the given-out target changes only
when all of these hold:
- the raw target is at least `deadband` °C away from the given-out one,
- it stayed on that side for `confirm_s` (a short TPI pulse or a zone opening for a few minutes does not count),
- at least `min_interval_s` passed since the last change;
then it moves to the raw target, a rise by at most `max_rise` °C at a time (lowering is never limited: cooler water is
the safe side). Values go out in 0.5 °C steps.

Exceptions:
- a limit the given-out target is outside of (the maximum was lowered): it is clamped at once;
- a large, confirmed difference (`urgent` °C, 0 = never) waits only `URGENT_CONFIRM_S` (2 minutes), not the confirmation and the interval (a sudden,
  lasting cold spell, a tank running out) – the rise limit still holds;
- no raw target (no outdoor reading, the inputs lost): the given-out target stays, nothing new goes out.

Over a restart the given-out target and the time of its last change are kept; one saved longer than `RESTORE_MAX_S`
ago is forgotten and the next raw target is taken as a fresh start (within its limits).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

STEP = 0.5
RESTORE_MAX_S = 6 * 3600.0
URGENT_CONFIRM_S = 120.0  # even an urgent change must last this long (not one noisy reading)


@dataclass
class HoldConfig:
    deadband: float = 1.5
    confirm_s: float = 600.0
    min_interval_s: float = 1500.0
    max_rise: float = 3.0  # °C per change; 0 = no limit
    urgent: float = 5.0  # °C; 0 = never


@dataclass(frozen=True)
class HoldResult:
    value: float | None  # the given-out target
    raw: float | None  # the worked-out target within the limits
    reason: str  # start | changed | ramp | urgent | limit | deadband | confirming | min_interval | no_input
    changed: bool
    next_allowed: datetime | None = None  # when the interval allows the next change


def _round(v: float) -> float:
    return round(round(v / STEP) * STEP, 1)


class SetpointHold:
    def __init__(self, cfg: HoldConfig | None = None) -> None:
        self.cfg = cfg or HoldConfig()
        self.value: float | None = None
        self.last_change: datetime | None = None
        self.pending_since: datetime | None = None
        self.pending_dir = 0

    def _set(self, now: datetime, v: float, lo: float, hi: float) -> None:
        self.value, self.last_change = max(lo, min(hi, _round(v))), now  # a limit off the 0.5 grid stays the limit
        self.pending_since, self.pending_dir = None, 0

    def _next(self) -> datetime | None:
        if self.last_change is None:
            return None
        return self.last_change + timedelta(seconds=self.cfg.min_interval_s)

    def step(self, now: datetime, raw: float | None, lo: float, hi: float) -> HoldResult:
        cfg = self.cfg
        if raw is None:
            self.pending_since, self.pending_dir = None, 0
            return HoldResult(self.value, None, "no_input", False, self._next())
        raw = max(lo, min(hi, raw))
        if self.value is None:
            self._set(now, raw, lo, hi)
            return HoldResult(self.value, raw, "start", True, self._next())
        if self.value > hi or self.value < lo:  # a limit moved: at once
            self._set(now, max(lo, min(hi, self.value)), lo, hi)
            return HoldResult(self.value, raw, "limit", True, self._next())
        diff = raw - self.value
        if abs(diff) < cfg.deadband:
            self.pending_since, self.pending_dir = None, 0
            return HoldResult(self.value, raw, "deadband", False, self._next())
        direction = 1 if diff > 0 else -1
        if direction != self.pending_dir:
            self.pending_since, self.pending_dir = now, direction
        urgent = cfg.urgent > 0 and abs(diff) >= cfg.urgent
        waited = (now - self.pending_since).total_seconds()
        since = (now - self.last_change).total_seconds() if self.last_change else None
        held = None
        if waited < cfg.confirm_s:
            held = "confirming"
        elif since is not None and 0 <= since < cfg.min_interval_s:
            held = "min_interval"
        if held and not (urgent and waited >= URGENT_CONFIRM_S):
            return HoldResult(self.value, raw, held, False, self._next())
        move = diff if diff < 0 or cfg.max_rise <= 0 else min(diff, cfg.max_rise)
        self._set(now, self.value + move, lo, hi)
        reason = "urgent" if held else "ramp" if move < diff else "changed"
        return HoldResult(self.value, raw, reason, True, self._next())

    def state(self, now: datetime | None = None) -> dict:
        return {"value": self.value, "last_change": self.last_change.isoformat() if self.last_change else None,
                "saved": now.isoformat() if now else None}

    def restore(self, data: dict, now: datetime) -> None:
        value, last = data.get("value"), data.get("last_change")
        if not isinstance(value, (int, float)) or not last:
            return
        try:
            when = datetime.fromisoformat(last)
            saved = datetime.fromisoformat(data["saved"]) if data.get("saved") else when
        except ValueError:
            return
        if (now - saved).total_seconds() > RESTORE_MAX_S:
            return  # HC was down too long: start afresh
        self.value, self.last_change = float(value), when

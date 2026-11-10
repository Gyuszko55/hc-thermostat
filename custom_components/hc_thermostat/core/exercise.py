"""Summer valve exercise for zone instances (stage 3).

A manifold actuator or zone valve that stays closed for months can seize. A zone instance (role "zone",
own relay) opens its valve once a week for a few minutes when it has not been open for `exercise_idle_days`:
on `exercise_weekday` (0 = Monday) from `exercise_time`, for `exercise_s` seconds. The zone reports itself
idle meanwhile, so a central boiler does not start for it. Only when the zone would not heat anyway
(summer rest, at target, no demand) – never when switched off, with an open window, a lost sensor or
right after a restart. A TRV zone (external control) exercises itself.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

from .model import HcConfig, Reason

ALLOWED = (Reason.SEASON_OFF, Reason.AT_TARGET, Reason.REGULATING, Reason.AFTERHEAT)


def _start(text: str) -> time:
    hours, minutes = (int(x) for x in str(text).split(":")[:2])
    return time(hours, minutes)


class ValveExercise:
    def __init__(self, cfg: HcConfig) -> None:
        self.cfg = cfg
        self.last_open: datetime | None = None  # the last time the valve was open (heating or exercise)
        self.running_since: datetime | None = None

    def state(self) -> dict:
        return {"last_open": self.last_open.isoformat() if self.last_open else None}

    def restore(self, data: dict) -> None:
        if data.get("last_open"):
            self.last_open = datetime.fromisoformat(data["last_open"])

    def _idle(self, at: datetime) -> bool:
        # 12 hours slack: last week's run ended a few minutes after this week's start time.
        limit = timedelta(days=float(self.cfg.exercise_idle_days)) - timedelta(hours=12)
        return self.last_open is None or at - self.last_open >= limit

    def _due(self, now: datetime) -> bool:
        cfg = self.cfg
        if now.weekday() != int(cfg.exercise_weekday):
            return False
        start = datetime.combine(now.date(), _start(cfg.exercise_time), tzinfo=now.tzinfo)
        if not start <= now < start + timedelta(seconds=cfg.exercise_s):
            return False
        return self._idle(start)

    def step(self, now: datetime, reason: Reason, output: bool) -> bool:
        """True while the valve is being exercised (the zone's own output is off)."""
        if output:
            self.last_open, self.running_since = now, None
            return False
        if not self.cfg.valve_exercise or reason not in ALLOWED:
            self.running_since = None
            return False
        if self.running_since is None:
            if not self._due(now):
                return False
            self.running_since = now
        if (now - self.running_since).total_seconds() >= self.cfg.exercise_s:
            self.last_open, self.running_since = now, None  # done for this week
            return False
        return True

    def next_run(self, now: datetime) -> datetime | None:
        """When the next exercise may start (for the attributes)."""
        if not self.cfg.valve_exercise:
            return None
        start = _start(self.cfg.exercise_time)
        day = now.date()
        for _ in range(15):
            at = datetime.combine(day, start, tzinfo=now.tzinfo)
            if at.weekday() == int(self.cfg.exercise_weekday) and at + timedelta(seconds=self.cfg.exercise_s) > now and self._idle(at):
                return max(at, now) if at <= now else at
            day += timedelta(days=1)
        return None

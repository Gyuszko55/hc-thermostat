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

ALLOWED = (Reason.SEASON_OFF, Reason.AT_TARGET, Reason.REGULATING, Reason.AFTERHEAT, Reason.THERMOSTAT_IDLE)


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


class PumpExercise:
    """Weekly pump exercise of a central boiler (0.39.0): a circulation pump that stands still all summer can seize.

    The pump runs alone for `central_pump_exercise_s` seconds (0 = off) on `central_pump_exercise_weekday` from
    `central_pump_exercise_time` (or later that day, once allowed), when it has not run for
    `central_pump_exercise_idle_days` – only while the boiler is off, no zone asks and a circuit is open (a bypass, or
    a valve that is open, e.g. by the zones' own valve exercise: never against closed valves; the caller decides
    that), and never right after a restart. The boiler does not start.
    """

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.last_run: datetime | None = None  # the last time the pump ran (with the boiler, overrun or exercise)
        self.running_since: datetime | None = None

    @property
    def length_s(self) -> float:
        return float(self.cfg.central_pump_exercise_s or 0.0)

    @property
    def until(self) -> datetime | None:
        return self.running_since + timedelta(seconds=self.length_s) if self.running_since else None

    def state(self) -> dict:
        return {"last_run": self.last_run.isoformat() if self.last_run else None}

    def restore(self, data: dict) -> None:
        if data.get("last_run"):
            self.last_run = datetime.fromisoformat(data["last_run"])

    def _idle(self, at: datetime) -> bool:
        limit = timedelta(days=float(self.cfg.central_pump_exercise_idle_days)) - timedelta(hours=12)  # as the valves
        return self.last_run is None or at - self.last_run >= limit

    def _start_at(self, day) -> datetime:
        return datetime.combine(day, _start(self.cfg.central_pump_exercise_time))

    def _due(self, now: datetime) -> bool:
        if now.weekday() != int(self.cfg.central_pump_exercise_weekday):
            return False
        # From the start time to the end of that day: the pump waits for an open circuit (e.g. the zones' own
        # weekly valve exercise, which opens the valves at the same time), then runs once.
        start = self._start_at(now.date()).replace(tzinfo=now.tzinfo)
        return start <= now and self._idle(start)

    def step(self, now: datetime, pump_running: bool, allowed: bool) -> bool:
        """True while the pump is being exercised. pump_running: the pump runs anyway (boiler, overrun, by hand) –
        while an exercise runs the pump entity is on because of it, so that does not end the exercise."""
        if pump_running and self.running_since is None:
            self.last_run, self.running_since = now, None
            return False
        if self.length_s <= 0 or not allowed:
            self.running_since = None
            return False
        if self.running_since is None:
            if not self._due(now):
                return False
            self.running_since = now
        if (now - self.running_since).total_seconds() >= self.length_s:
            self.last_run, self.running_since = now, None  # done for this week
            return False
        return True

    def next_run(self, now: datetime) -> datetime | None:
        """When the next exercise may start (for the attributes)."""
        if self.length_s <= 0:
            return None
        day = now.date()
        for _ in range(15):
            at = self._start_at(day).replace(tzinfo=now.tzinfo)
            if at.weekday() == int(self.cfg.central_pump_exercise_weekday) and at + timedelta(seconds=self.length_s) > now and self._idle(at):
                return max(at, now)
            day += timedelta(days=1)
        return None

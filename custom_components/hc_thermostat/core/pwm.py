"""Turns a demand into on/off while always respecting the device limits."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .model import HcConfig


class Pwm:
    def __init__(self, cfg: HcConfig) -> None:
        self._cfg = cfg
        self.output = False
        self.last_change: datetime | None = None
        self.cycle_start: datetime | None = None
        self._deferred = False  # refused by the load limit: the cycle starts again when the room is granted

    def _on_time(self, demand: float) -> float:
        cfg = self._cfg
        on_time = max(0.0, min(1.0, demand)) * cfg.cycle_s
        if on_time < cfg.min_on_s:
            return 0.0
        if cfg.cycle_s - on_time < cfg.min_off_s:
            return cfg.cycle_s
        return on_time

    def step(self, now: datetime, demand: float,
             allow_on: Callable[[bool], bool] | None = None) -> tuple[bool, str | None]:
        """allow_on(renew): a shared load limit (0.28.0) – asked before switching on, and by a zone that stays on
        into a new cycle (renew=True); refused, the cycle starts again later and the relay stays (or goes) off."""
        cfg = self._cfg
        new_cycle = self.cycle_start is None or (now - self.cycle_start).total_seconds() >= cfg.cycle_s
        if new_cycle:
            self.cycle_start = now
        want = (now - self.cycle_start).total_seconds() < self._on_time(demand)
        if not want and not self.output and not new_cycle and not self._deferred and self._on_time(demand) > 0 \
                and not self._burned_this_cycle() and self._off_long_enough(now):
            # 0.44.2: a demand that grows past the minimum run only mid-cycle (the cycle began below it) used to wait
            # for the next cycle – up to a whole cycle (30 min) with the room under its target. Start a cycle now.
            self.cycle_start, want = now, True
        if allow_on is not None and want and self.output and new_cycle and not allow_on(True):
            self.output, self.last_change = False, now  # its minimum run is long over: hand over to a waiting zone
            return False, "load_limit"
        if want == self.output:
            return self.output, None
        if self.last_change is not None:
            since = (now - self.last_change).total_seconds()
            if self.output and since < cfg.min_on_s:
                return self.output, "min_on"
            if not self.output and since < cfg.min_off_s:
                return self.output, "min_off"
        if want and allow_on is not None and not allow_on(False):
            self.cycle_start, self._deferred = now, True  # the on-time starts when the room is granted: staggered
            return False, "load_limit"
        if want and (self._deferred or not self._burned_this_cycle()):
            # 0.44.5 (as Versatile Thermostat #2194): a start delayed by the minimum off time used to lose the delay
            # from its run (40 %, 30-min cycle: 8 instead of 12 min). The cycle begins when the burner really starts.
            self.cycle_start = now
        self._deferred = False
        self.output, self.last_change = want, now
        return self.output, None

    def _burned_this_cycle(self) -> bool:
        """On now, or switched within this cycle (an on, or the off of a run that reached into it)."""
        return self.output or (self.last_change is not None and self.cycle_start is not None
                               and self.last_change > self.cycle_start)

    def _off_long_enough(self, now: datetime) -> bool:
        return self.last_change is None or (now - self.last_change).total_seconds() >= self._cfg.min_off_s

    def force_off(self, now: datetime) -> bool:
        """Off at once, ignoring the minimum run time: a safety limit (floor temperature) was hit."""
        if self.output:
            self.output, self.last_change = False, now
        return False

    def state(self) -> dict:
        return {
            "output": self.output,
            "last_change": self.last_change.isoformat() if self.last_change else None,
            "cycle_start": self.cycle_start.isoformat() if self.cycle_start else None,
        }

    def restore(self, data: dict) -> None:
        self.output = bool(data.get("output", False))
        self.last_change = datetime.fromisoformat(data["last_change"]) if data.get("last_change") else None
        self.cycle_start = datetime.fromisoformat(data["cycle_start"]) if data.get("cycle_start") else None

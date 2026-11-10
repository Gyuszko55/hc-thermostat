"""Is a temperature reading believable? (0.23.0)

A sensor can be fresh and still wrong: a flat battery, a broken probe or a bad radio packet gives 0 °C, -40 °C
or 45 °C. Believed, 0 °C starts the frost protection at full power and 45 °C never lets the heating start.

- out of range (`lo` … `hi`): the reading counts as lost – the lost-sensor rules apply;
- a jump of more than `jump` °C from the last believed value: the last believed value is kept; the new level
  is believed only when it holds for `confirm_s` (a real change, e.g. a moved sensor), and dropped when the
  readings come back (a glitch).
"""

from __future__ import annotations

from datetime import datetime

from .model import Reading


class Plausibility:
    def __init__(self, lo: float, hi: float, jump: float | None = None, confirm_s: float = 600.0) -> None:
        self.lo, self.hi, self.jump, self.confirm_s = lo, hi, jump, confirm_s
        self.accepted: float | None = None
        self._suspect_since: datetime | None = None
        self.problem: str | None = None  # None | "out_of_range" | "jump"

    def check(self, now: datetime, reading: Reading) -> Reading:
        value = reading.value
        if value is None:
            self.problem = None
            return reading
        if not self.lo <= value <= self.hi:
            self.problem = "out_of_range"
            return Reading()
        if self.jump is None or self.accepted is None or abs(value - self.accepted) <= self.jump:
            self.accepted, self._suspect_since, self.problem = value, None, None
            return reading
        # a jump: keep the last believed value until the new level has held long enough
        self._suspect_since = self._suspect_since or now
        if (now - self._suspect_since).total_seconds() >= self.confirm_s:
            self.accepted, self._suspect_since, self.problem = value, None, None
            return reading
        self.problem = "jump"
        return Reading(self.accepted, reading.age_s)

    def state(self) -> dict:
        return {"accepted": self.accepted}

    def restore(self, data: dict) -> None:
        value = data.get("accepted")
        self.accepted = float(value) if isinstance(value, (int, float)) else None

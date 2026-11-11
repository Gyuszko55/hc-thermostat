"""A frozen room thermometer (0.41.0): a sensor that keeps reporting the same value looks fresh – its age is
counted from the last report – but it no longer measures (stuck firmware, a dead probe behind a working radio).

While the value has not changed at all for `frozen_after_h` hours and the heat source has run at least
`frozen_burn_min` minutes in that time, the reading does not count: the instance takes the lost-sensor path
(floor fallback, heat-need demand or the blind share) until the value changes again. A real room warms by at
least one step of the sensor while it is heated that long – the house this was measured on (2026-11) stayed at
one value for at most 1.4 h, with at most 17 burning minutes in it, so the defaults (3 h, 45 min) leave a wide
margin.
"""

from __future__ import annotations

from datetime import datetime


class FrozenSensor:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.value: float | None = None
        self.since: datetime | None = None
        self.burn_s = 0.0
        self._last: datetime | None = None
        self.frozen = False

    def step(self, now: datetime, value: float | None, heating: bool) -> bool:
        """True while the reading is frozen. value: the fresh reading (None: no reading – nothing to judge);
        heating: the heat source runs now (counted from the previous step on)."""
        hours, burn_min = float(self.cfg.frozen_after_h or 0), float(self.cfg.frozen_burn_min or 0)
        dt = 0.0 if self._last is None else max((now - self._last).total_seconds(), 0.0)
        self._last = now
        if hours <= 0 or value is None:
            self.value, self.since, self.burn_s, self.frozen = value, (now if value is not None else None), 0.0, False
            return False
        if self.value is None or value != self.value:
            self.value, self.since, self.burn_s, self.frozen = value, now, 0.0, False
            return False
        if heating and dt <= 600:  # a long gap is a restart: not counted
            self.burn_s += dt
        self.frozen = ((now - self.since).total_seconds() >= hours * 3600 and self.burn_s >= burn_min * 60)
        return self.frozen

    def details(self, now: datetime) -> dict:
        return {"indoor_frozen": True, "frozen_value": self.value,
                "frozen_h": round((now - self.since).total_seconds() / 3600, 1) if self.since else None,
                "frozen_burn_min": round(self.burn_s / 60)}

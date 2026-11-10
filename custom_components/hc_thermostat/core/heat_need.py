"""Learns how much heat the house loses, from delivered energy and temperatures.

The heating has to replace this loss. The loss factor (kW/K) is the ratio of the
heat delivered and the degree hours over whole days, so internal and solar gains
are included in it.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

_MAX_GAP_S = 600.0
_MIN_COVERAGE_S = 20 * 3600.0
_MIN_DELTA = 5.0
_MIN_SAMPLES = 3
_WINDOW = 14
MODEL = 2  # Samples of another calculation are not comparable and are dropped.


class HeatNeedEstimator:
    def __init__(self) -> None:
        self.samples: deque[tuple[str, float, float]] = deque(maxlen=30)  # date, kWh, degree hours
        self._day: str | None = None
        self._last: datetime | None = None
        self._last_energy: float | None = None
        self._kwh = 0.0
        self._degree_hours = 0.0
        self._covered_s = 0.0

    def add_sample(self, day: str, kwh: float, degree_hours: float) -> None:
        if not any(s[0] == day for s in self.samples):
            self.samples.append((day, kwh, degree_hours))

    def _finish_day(self) -> None:
        if self._covered_s >= _MIN_COVERAGE_S and self._kwh > 0 and self._day:
            hours = self._covered_s / 3600
            if self._degree_hours / hours >= _MIN_DELTA:
                # Scale to a whole day so a short gap does not bias the ratio.
                self.add_sample(self._day, self._kwh, self._degree_hours * 24 / hours)
        self._kwh = self._degree_hours = self._covered_s = 0.0

    def update(self, now: datetime, indoor: float | None, outdoor: float | None, energy_kwh: float | None) -> None:
        day = now.date().isoformat()
        if self._day is not None and day != self._day:
            self._finish_day()
        self._day = day
        dt = 0.0 if self._last is None else (now - self._last).total_seconds()
        self._last = now
        if energy_kwh is not None:
            if self._last_energy is not None and energy_kwh > self._last_energy:
                self._kwh += energy_kwh - self._last_energy
            self._last_energy = energy_kwh
        if indoor is not None and outdoor is not None and 0 < dt <= _MAX_GAP_S:
            self._degree_hours += (indoor - outdoor) * dt / 3600
            self._covered_s += dt

    @property
    def loss_kw_per_k(self) -> float | None:
        recent = list(self.samples)[-_WINDOW:]
        if len(recent) < _MIN_SAMPLES:
            return None
        degree_hours = sum(s[2] for s in recent)
        return sum(s[1] for s in recent) / degree_hours if degree_hours > 0 else None

    def state(self) -> dict:
        return {"model": MODEL, "samples": list(self.samples)}

    def restore(self, data: dict) -> None:
        if data.get("model") == MODEL:
            self.samples.extend(tuple(s) for s in data.get("samples", []))

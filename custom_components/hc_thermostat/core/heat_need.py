"""Learns how much heat the house loses, from delivered energy and temperatures.

The heating has to replace this loss. Until 0.50.0 the loss factor (kW/K) was the
ratio of the heat delivered and the degree hours over whole days, so the internal
and solar gains were folded into it: right in the weather it was learned in, too
low in a cold spell (a house losing 160 W/K with 0.7 kW of free heat looks like
125 W/K at 4 °C outside and needs twice that at -10 °C).

0.50.0, the house model: a straight line through the days, daily heat (kW) against
the mean indoor - outdoor difference. Its slope is the loss factor H (kW/K), its
intercept the free heat G (kW: people, appliances, sun): need = H x (target -
outdoor) - G. The line needs days of different weather; until then (or when it
does not fit) the ratio stays. Values given by hand (`house_loss_w_k`,
`house_gains_kw`) are the starting point: the learned line is blended in with the
number of days behind it.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime

_MAX_GAP_S = 600.0
_MIN_COVERAGE_S = 20 * 3600.0
_MIN_DELTA = 5.0
_MIN_SAMPLES = 3
_WINDOW = 14
_FIT_WINDOW = 30  # 0.50.0: the line uses every kept day
_FIT_MIN_SAMPLES = 10
_FIT_MIN_SPREAD = 4.0  # K between the mildest and the coldest day
_FIT_MIN_R = 0.7
PRIOR_DAYS = 14.0  # a value given by hand weighs as much as this many learned days
MODEL = 2  # Samples of another calculation are not comparable and are dropped.


class HeatNeedEstimator:
    def __init__(self, manual_loss_kw_per_k: float = 0.0, manual_gains_kw: float = 0.0) -> None:
        self.manual_loss = max(float(manual_loss_kw_per_k or 0.0), 0.0)  # 0 = not given
        self.manual_gains = float(manual_gains_kw or 0.0) if self.manual_loss > 0 else 0.0
        self.samples: deque[tuple[str, float, float]] = deque(maxlen=30)  # date, kWh, degree hours
        self.since: str | None = None  # 0.50.0: learned again from this day (the house changed: insulation)
        self._day: str | None = None
        self._last: datetime | None = None
        self._last_energy: float | None = None
        self._kwh = 0.0
        self._degree_hours = 0.0
        self._covered_s = 0.0

    def add_sample(self, day: str, kwh: float, degree_hours: float) -> None:
        if self.since is not None and day < self.since:
            return  # before the house changed
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
    def ratio_kw_per_k(self) -> float | None:
        """The plain ratio of the last two weeks (free heat folded in): the fallback, and the only value before
        0.50.0."""
        recent = list(self.samples)[-_WINDOW:]
        if len(recent) < _MIN_SAMPLES:
            return None
        degree_hours = sum(s[2] for s in recent)
        return sum(s[1] for s in recent) / degree_hours if degree_hours > 0 else None

    def fit(self) -> dict | None:
        """The line through the kept days: H (kW/K), G (kW), r, days; None while it cannot be trusted."""
        recent = list(self.samples)[-_FIT_WINDOW:]
        if len(recent) < _FIT_MIN_SAMPLES:
            return None
        xs = [s[2] / 24 for s in recent]  # mean indoor - outdoor of the day
        ys = [s[1] / 24 for s in recent]  # mean heat of the day, kW
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        if max(xs) - min(xs) < _FIT_MIN_SPREAD or sxx <= 0 or syy <= 0:
            return None
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        slope = sxy / sxx
        r = sxy / (sxx * syy) ** 0.5
        if slope <= 0 or r < _FIT_MIN_R:
            return None
        gains = slope * mx - my  # need = slope x dT - gains
        # the free heat cannot cover the whole mean need, nor be negative: that is a constant extra consumption in
        # the meter (hot water) or a poor line (a real house: 49 W/K with -0.38 kW from 28 mild days)
        if not 0.0 <= gains < slope * mx:
            return None
        return {"loss": slope, "gains": gains, "r": r, "days": n}

    def model(self) -> tuple[float, float, str] | None:
        """(H kW/K, G kW, source): "fit" (learned, blended with a hand-given value), "manual", "ratio"; or None."""
        fitted = self.fit()
        if fitted is not None:
            if self.manual_loss > 0:
                w = PRIOR_DAYS / (PRIOR_DAYS + fitted["days"])
                return (w * self.manual_loss + (1 - w) * fitted["loss"],
                        w * self.manual_gains + (1 - w) * fitted["gains"], "fit")
            return fitted["loss"], fitted["gains"], "fit"
        if self.manual_loss > 0:
            return self.manual_loss, self.manual_gains, "manual"
        ratio = self.ratio_kw_per_k
        return (ratio, 0.0, "ratio") if ratio is not None else None

    @property
    def loss_kw_per_k(self) -> float | None:
        m = self.model()
        return m[0] if m else None

    @property
    def gains_kw(self) -> float:
        m = self.model()
        return m[1] if m else 0.0

    @property
    def source(self) -> str | None:
        m = self.model()
        return m[2] if m else None

    def need_kw(self, target: float, outdoor: float) -> float | None:
        """The heat the house needs at this target and outdoor temperature (all sources together)."""
        m = self.model()
        if m is None:
            return None
        return max(m[0] * (target - outdoor) - m[1], 0.0)

    def balance_point(self, target: float) -> float | None:
        """The outdoor temperature above which the free heat alone holds the target."""
        m = self.model()
        if m is None or m[0] <= 0:
            return None
        return target - m[1] / m[0]

    def reset(self, today: str) -> None:
        """0.50.0: the house changed (insulation, new windows): forget the days, and do not seed them again from
        the statistics before today."""
        self.samples.clear()
        self.since = today
        self._kwh = self._degree_hours = self._covered_s = 0.0
        self._day = None

    def state(self) -> dict:
        return {"model": MODEL, "samples": list(self.samples), "since": self.since}

    def restore(self, data: dict) -> None:
        self.since = data.get("since") or self.since
        if data.get("model") == MODEL:
            self.samples.extend(tuple(s) for s in data.get("samples", []))

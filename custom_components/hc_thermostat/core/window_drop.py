"""Open window recognised from a fast temperature drop, for rooms without a window sensor.

A thermometer near the window drops fast when it is opened. Room thermometers report only on a change,
a few times an hour, and after a long silence one report may hold a slow drop of the whole silence. So a
value is kept with the time it was FIRST reported, and the rate is measured between reports: an open
window shows as reports coming fast one after the other, a slow cooling as one step after a long silence.
The last value from before the look-back window is kept as an anchor (it was valid until the next report).

Open: a drop of at least `window_drop_min` °C from an earlier report at `window_drop_rate` °C/h or faster
(over at least `window_drop_min_span_min` minutes).
Closed again: the reading rose `window_drop_recover` °C above its lowest point, or it has not fallen for
`window_drop_quiet_min` minutes, or after `window_drop_max_min` minutes at the latest. After that a pause of
`window_drop_cooldown_min` minutes, so one airing is not counted twice.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta


class DropDetector:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.samples: deque[tuple[datetime, float]] = deque()
        self.since: datetime | None = None  # open since
        self.low: float | None = None
        self.low_at: datetime | None = None
        self.rate: float | None = None  # °C per hour when it was recognised
        self.cooldown_until: datetime | None = None

    @property
    def open(self) -> bool:
        return self.since is not None

    def update(self, now: datetime, value: float | None) -> bool:
        cfg = self.cfg
        if value is None:
            # 0.44.5: a thermometer that drops out must not hold the pause beyond its longest time
            if self.open and now - self.since >= timedelta(minutes=cfg.window_drop_max_min):
                self.since = None
                self.cooldown_until = now + timedelta(minutes=cfg.window_drop_cooldown_min)
                self.samples.clear()
            return self.open
        if not self.samples or self.samples[-1][1] != value:
            self.samples.append((now, value))  # a new report: kept with the time it first appeared
        limit = now - timedelta(minutes=cfg.window_drop_lookback_min)
        while len(self.samples) > 1 and self.samples[1][0] <= limit:
            self.samples.popleft()  # the last one before the window stays as the anchor
        if self.open:
            if value < self.low:
                self.low, self.low_at = value, now
            if (value >= self.low + cfg.window_drop_recover
                    or now - self.low_at >= timedelta(minutes=cfg.window_drop_quiet_min)
                    or now - self.since >= timedelta(minutes=cfg.window_drop_max_min)):
                self.since = None
                self.cooldown_until = now + timedelta(minutes=cfg.window_drop_cooldown_min)
                self.samples.clear()
                self.samples.append((now, value))
                return False
            return True
        if self.cooldown_until is not None and now < self.cooldown_until:
            return False
        best = 0.0
        for at, earlier in self.samples:
            drop = earlier - value
            if drop >= cfg.window_drop_min:
                hours = max((now - at).total_seconds(), cfg.window_drop_min_span_min * 60) / 3600
                best = max(best, drop / hours)
        if best >= cfg.window_drop_rate:
            self.since, self.low, self.low_at, self.rate = now, value, now, round(best, 1)
            return True
        return False

"""0.50.0: the thermal inertia of the house – its time constant τ – and what it predicts.

Without heat the room approaches its equilibrium exponentially:

    T(t) = Teq + (T0 - Teq) * exp(-t / τ),   Teq = outdoor + free heat / loss factor

τ (hours) is learned from quiet stretches: no burn for at least `tau_min_quiet_h`
hours, starting `tau_settle_min` minutes after the last burn (the radiators have
given their heat), window closed, room and outdoor readings fresh. Each stretch
gives τ = hours / ln(ΔT0 / ΔT1) with ΔT = room - Teq; the median of the kept
stretches is the learned value, blended with a hand-given value (`house_tau_h`)
by the number of stretches behind it.

Uses (core/supervisor.py): how far the room falls until a target change – the
optimal start before the night end and the hold before a scheduled lowering.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from datetime import datetime

_KEEP = 21  # stretches kept
_MIN_SAMPLES = 3
PRIOR_SAMPLES = 5.0  # a value given by hand weighs as much as this many stretches
_MIN_DELTA = 6.0  # K between the room and its equilibrium at the start
_MIN_DROP = 0.2  # K the room must fall over the stretch (sensor resolution)
_TAU_MIN_H, _TAU_MAX_H = 5.0, 1000.0
_EDGE_S = 900.0  # the start and the end of a stretch are the mean of this long (sensor noise)
_MAX_GAP_S = 900.0


def predict(indoor: float, equilibrium: float, tau_h: float, hours: float) -> float:
    """The room after `hours` without heat."""
    if hours <= 0 or tau_h <= 0:
        return indoor
    return equilibrium + (indoor - equilibrium) * math.exp(-hours / tau_h)


class TauEstimator:
    def __init__(self, manual_tau_h: float = 0.0, min_quiet_h: float = 3.0, settle_min: float = 60.0) -> None:
        self.manual = max(float(manual_tau_h or 0.0), 0.0)
        self.min_quiet_s = max(float(min_quiet_h), 1.0) * 3600
        self.settle_s = max(float(settle_min), 0.0) * 60
        self.samples: deque[tuple[str, float]] = deque(maxlen=_KEEP)  # (ISO start, τ hours)
        self._run: list[tuple[datetime, float, float]] = []  # (time, room, equilibrium) of the running stretch
        self._last_heat: datetime | None = None
        self._last: datetime | None = None

    # --- learning ---------------------------------------------------------------
    def update(self, now: datetime, heating: bool, quiet_ok: bool, indoor: float | None,
               equilibrium: float | None) -> None:
        """One step. `heating`: the burner (or the output) runs; `quiet_ok`: nothing else disturbs (window closed, no
        other heat source counted, regulating at home); `equilibrium`: outdoor + free heat / loss (None: unknown)."""
        gap = self._last is not None and (now - self._last).total_seconds() > _MAX_GAP_S
        self._last = now
        if heating:
            self._close(now)
            self._last_heat = now
            return
        if gap or not quiet_ok or indoor is None or equilibrium is None:
            self._close(now)
            return
        if self._last_heat is not None and (now - self._last_heat).total_seconds() < self.settle_s:
            return  # the radiators still give their heat
        self._run.append((now, indoor, equilibrium))

    def _close(self, now: datetime) -> None:
        run, self._run = self._run, []
        if len(run) < 4:
            return
        span = (run[-1][0] - run[0][0]).total_seconds()
        if span < self.min_quiet_s:
            return
        head = [p for p in run if (p[0] - run[0][0]).total_seconds() <= _EDGE_S]
        tail = [p for p in run if (run[-1][0] - p[0]).total_seconds() <= _EDGE_S]
        t0 = statistics.fmean(p[1] for p in head)
        t1 = statistics.fmean(p[1] for p in tail)
        eq = statistics.fmean(p[2] for p in run)
        d0, d1 = t0 - eq, t1 - eq
        if d0 < _MIN_DELTA or d1 <= 0 or t0 - t1 < _MIN_DROP:
            return
        mid = lambda pts: statistics.fmean(p[0].timestamp() for p in pts)  # noqa: E731
        hours = (mid(tail) - mid(head)) / 3600
        if hours <= 0:
            return
        tau = hours / math.log(d0 / d1)
        if _TAU_MIN_H <= tau <= _TAU_MAX_H:
            self.samples.append((run[0][0].isoformat(), round(tau, 1)))

    # --- the value ----------------------------------------------------------------
    @property
    def learned_h(self) -> float | None:
        if len(self.samples) < _MIN_SAMPLES:
            return None
        return statistics.median(s[1] for s in self.samples)

    @property
    def tau_h(self) -> float | None:
        learned = self.learned_h
        if learned is None:
            return self.manual or None
        if self.manual > 0:
            n = len(self.samples)
            return (PRIOR_SAMPLES * self.manual + n * learned) / (PRIOR_SAMPLES + n)
        return learned

    @property
    def source(self) -> str | None:
        if self.learned_h is not None:
            return "learned"
        return "manual" if self.manual > 0 else None

    def reset(self) -> None:
        self.samples.clear()
        self._run = []

    # --- persistence --------------------------------------------------------------
    def state(self) -> dict:
        return {"samples": [list(s) for s in self.samples],
                "last_heat": self._last_heat.isoformat() if self._last_heat else None}

    def restore(self, data: dict) -> None:
        for s in data.get("samples") or []:
            if isinstance(s, (list, tuple)) and len(s) == 2:
                self.samples.append((str(s[0]), float(s[1])))
        if data.get("last_heat"):
            self._last_heat = datetime.fromisoformat(data["last_heat"])

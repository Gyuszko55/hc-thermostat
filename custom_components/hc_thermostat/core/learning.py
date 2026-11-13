"""Learns how this house answers the heating: after-heat of a boost, and how hard the TPI has to push.

Boost (after each one, once the peak is known):
- after-heat per outdoor band = (peak - temperature at the stop) / f(flame minutes), see Supervisor.boost_forecast;
- minutes per degree per band = flame minutes / (peak - temperature at the start), for the safety limit;
- trim = a small correction from the overshoot left over.
TPI (once a day, from the regulating hours at home):
- strength (tpi_coef_int): up when the house stayed well below the target for hours, down on overshoot;
- holding offset: a very slow integral that removes a steady small shortfall.

Every step is small and bounded; a disturbed boost (window, a jump in the reading, a target change) teaches nothing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime

BANDS = ("cold", "mild", "warm")  # outdoor below 0 °C, 0..10 °C, above 10 °C
BAND_CENTRE = {"cold": -5.0, "mild": 5.0, "warm": 15.0}  # the reference of a band learned before 0.48.2
# 0.48.2: within (and across) the bands, every 10 °C warmer outside a boost needs this much less burning and its
# after-heat lifts the house this much more (a house that loses less heat); bounded to 0.7–1.4
OUTDOOR_SLOPE = 0.2


def band(outdoor: float | None) -> str:
    if outdoor is None:
        return "mild"
    return "cold" if outdoor < 0 else "warm" if outdoor > 10 else "mild"


def _step_towards(old: float, measured: float, gain: float, max_step: float, low: float, high: float) -> float:
    change = max(-max_step, min(max_step, gain * (measured - old)))
    return round(max(low, min(high, old + change)), 3)


@dataclass
class BoostRecord:
    start: datetime
    target: float
    indoor_start: float
    outdoor: float | None
    flame_min: float = 0.0
    indoor_stop: float | None = None
    peak: float | None = None
    disturbed: bool = False
    last_indoor: float | None = None


@dataclass
class Learned:
    afterheat: dict = field(default_factory=dict)  # band -> °C
    minutes_per_degree: dict = field(default_factory=dict)  # band -> min/°C
    trim: float = 0.0
    tpi_coef_int: float | None = None
    tpi_offset: float = 0.0
    boosts: int = 0
    days: int = 0
    last_boost: dict | None = None
    outdoor_ref: dict = field(default_factory=dict)  # 0.48.2: band -> the outdoor temperature it was learned at


def outdoor_factor(outdoor: float | None, ref: float | None) -> float:
    """How much more burning a boost needs at `outdoor` than at `ref` (after-heat: the inverse)."""
    if outdoor is None or ref is None:
        return 1.0
    return max(0.7, min(1.4, 1.0 + OUTDOOR_SLOPE * (ref - outdoor) / 10.0))


class Learner:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.learned = Learned()
        self.boost: BoostRecord | None = None
        self._day: str | None = None
        self._reg_s = 0.0
        self._err_s = 0.0  # integral of (target - indoor) over the regulating time
        self._under_s = 0.0  # time spent more than 0.3 °C below the target
        self._over_s = 0.0  # time spent more than 0.2 °C above the target

    # --- what the supervisor uses ------------------------------------------------
    @property
    def _on(self) -> bool:
        return bool(self.cfg.learning_enabled)

    def _learned_at(self, table: dict, outdoor: float | None) -> tuple[float | None, float | None]:
        """0.48.2: the value of the outdoor's band, else of the nearest band learned (before: the default), with the
        outdoor temperature it was learned at."""
        if not self._on or not table:
            return None, None
        own = band(outdoor)
        order = sorted(BANDS, key=lambda b: abs(BANDS.index(b) - BANDS.index(own)))
        for b in order:
            if b in table:
                return table[b], self.learned.outdoor_ref.get(b, BAND_CENTRE[b])
        return None, None

    def afterheat(self, outdoor: float | None) -> float:
        value, ref = self._learned_at(self.learned.afterheat, outdoor)
        if value is None:
            return self.cfg.boost_afterheat
        return round(max(0.2, min(2.0, value / outdoor_factor(outdoor, ref))), 3)  # warmer: more of a lift

    def minutes_per_degree(self, outdoor: float | None) -> float:
        value, ref = self._learned_at(self.learned.minutes_per_degree, outdoor)
        if value is None:
            return self.cfg.boost_minutes_per_degree
        return round(max(5.0, min(60.0, value * outdoor_factor(outdoor, ref))), 3)  # warmer: fewer minutes

    @property
    def trim(self) -> float:
        return self.learned.trim if self._on and self.learned.boosts else self.cfg.boost_trim

    @property
    def tpi_coef_int(self) -> float:
        learned = self.learned.tpi_coef_int
        return learned if self._on and learned is not None else self.cfg.tpi_coef_int

    @property
    def tpi_offset(self) -> float:
        return self.learned.tpi_offset if self._on else 0.0

    # --- boost ------------------------------------------------------------------------
    def boost_started(self, now: datetime, target: float, indoor: float, outdoor: float | None) -> None:
        self.boost = BoostRecord(now, target, indoor, outdoor, last_indoor=indoor)

    def observe(self, indoor: float | None, target: float, window: bool) -> None:
        """Every step while a boost or its after-heat runs."""
        rec = self.boost
        if rec is None or indoor is None:
            return
        if window or target != rec.target or (rec.last_indoor is not None and abs(indoor - rec.last_indoor) > 0.5):
            rec.disturbed = True
        rec.last_indoor = indoor
        rec.peak = indoor if rec.peak is None else max(rec.peak, indoor)

    def boost_stopped(self, indoor: float, flame_min: float) -> None:
        if self.boost is not None:
            self.boost.indoor_stop, self.boost.flame_min = indoor, flame_min

    def boost_finished(self, peak_found: bool) -> None:
        """The after-heat is over: learn from it, if it was clean."""
        rec, self.boost = self.boost, None
        if not self.cfg.learning_enabled or rec is None or rec.indoor_stop is None or rec.peak is None:
            return
        summary = {"start": rec.start.isoformat(), "target": rec.target, "indoor_start": rec.indoor_start,
                   "indoor_stop": rec.indoor_stop, "peak": rec.peak, "flame_min": round(rec.flame_min, 1),
                   "outdoor": rec.outdoor, "used": False}
        self.learned.last_boost = summary
        if rec.disturbed or not peak_found or rec.flame_min < 5:
            return
        cfg, key = self.cfg, band(rec.outdoor)
        f = rec.flame_min / (rec.flame_min + cfg.boost_afterheat_ref_min)
        measured_u = max(rec.peak - rec.indoor_stop, 0.0) / f
        # 0.48.2: the band's value is kept at its reference outdoor temperature – the measurement is brought there.
        # A band learned before 0.48.2 has its centre as the reference; a new band takes this boost's outdoor.
        ref = self.learned.outdoor_ref.get(key)
        if ref is None:
            ref = BAND_CENTRE[key] if key in self.learned.afterheat or rec.outdoor is None else round(rec.outdoor, 1)
            self.learned.outdoor_ref[key] = ref
        to_ref = outdoor_factor(rec.outdoor, ref)  # < 1: this boost was warmer outside than the reference
        start_u = self.learned.afterheat.get(key, self.afterheat(ref))
        self.learned.afterheat[key] = _step_towards(start_u, measured_u * to_ref, 0.5, 0.2, 0.2, 2.0)
        rise = rec.peak - rec.indoor_start
        if rise >= 0.3:
            start_m = self.learned.minutes_per_degree.get(key, self.minutes_per_degree(ref))
            self.learned.minutes_per_degree[key] = _step_towards(start_m, rec.flame_min / rise / to_ref,
                                                                 0.5, 3.0, 5.0, 60.0)
        self.learned.trim = _step_towards(self.trim, self.trim + (rec.peak - rec.target), 0.25, 0.1, -0.3, 0.5)
        self.learned.boosts += 1
        summary["used"] = True

    # --- TPI, once a day ----------------------------------------------------------------
    def regulating(self, now: datetime, dt: float, target: float, indoor: float) -> None:
        """Called for every regulating step at home (not boost, after-heat or window)."""
        day = now.date().isoformat()
        if self._day is not None and day != self._day:
            self._finish_day()
        self._day = day
        if dt <= 0 or dt > 600:
            return
        error = target - indoor
        self._reg_s += dt
        self._err_s += error * dt
        if error > 0.3:
            self._under_s += dt
        if error < -0.2:
            self._over_s += dt

    def _finish_day(self) -> None:
        reg, err, under, over = self._reg_s, self._err_s, self._under_s, self._over_s
        self._reg_s = self._err_s = self._under_s = self._over_s = 0.0
        if not self.cfg.learning_enabled or reg < 4 * 3600:
            return
        coef = self.tpi_coef_int
        if under >= 3 * 3600 and over < 1800:
            self.learned.tpi_coef_int = round(min(coef + 0.1, 1.2), 2)
        elif over >= 2 * 3600 and under < 1800:
            self.learned.tpi_coef_int = round(max(coef - 0.1, 0.3), 2)
        mean_error = err / reg
        self.learned.tpi_offset = _step_towards(
            self.learned.tpi_offset, self.learned.tpi_offset + coef * mean_error, 0.5, 0.05, -0.2, 0.3)
        self.learned.days += 1

    # --- persistence ------------------------------------------------------------------
    def reset(self) -> None:
        self.learned = Learned()
        self.boost = None

    def state(self) -> dict:
        boost = None
        if self.boost is not None:  # 0.48.2: a restart during the after-heat no longer loses the boost's lesson
            boost = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in asdict(self.boost).items()}
        return {"learned": asdict(self.learned), "day": self._day, "reg_s": self._reg_s, "err_s": self._err_s,
                "under_s": self._under_s, "over_s": self._over_s, "boost": boost}

    def restore(self, data: dict) -> None:
        learned = data.get("learned") or {}
        known = set(Learned.__dataclass_fields__)
        self.learned = Learned(**{k: v for k, v in learned.items() if k in known})
        self._day = data.get("day")
        self._reg_s = float(data.get("reg_s", 0.0))
        self._err_s = float(data.get("err_s", 0.0))
        self._under_s = float(data.get("under_s", 0.0))
        self._over_s = float(data.get("over_s", 0.0))
        raw = data.get("boost")
        if isinstance(raw, dict):
            try:
                known_b = set(BoostRecord.__dataclass_fields__)
                vals = {k: v for k, v in raw.items() if k in known_b}
                vals["start"] = datetime.fromisoformat(vals["start"])
                self.boost = BoostRecord(**vals)
            except (KeyError, TypeError, ValueError):
                self.boost = None

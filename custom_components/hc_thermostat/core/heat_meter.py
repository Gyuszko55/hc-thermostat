"""0.75.0 (a tester's request, a heat pump charging a 1000 l tank through its lower coil): the heat pump's water-side
heat meter and its COP, from three readings – flow (outlet) and return (inlet) water temperature and the water flow.

    P_thermal [kW] = flow [l/min] × (T_out − T_in) [K] × 0.06977 × factor      (water: 4.186 kJ/(kg·K) / 60 s)

It measures the heat the water circuit carries off the heat pump – not the tank's net gain. The energy is integrated
by the trapezoid rule between two valid readings at most `hm_max_gap_s` apart: a gap (a reading missing, stale or
impossible, a restart, a long pause) adds nothing and is never filled in. No flow (below `hm_min_flow`) is 0 kW; a
negative ΔT (defrost, the water circulating backwards through a cold unit) is 0 kW too – heating only, the counter
never goes down.

The COP takes the electric power HC already reads (the "runs" power meter, or an own power sensor). The current COP is
the energy-weighted COP of the last `hm_cop_window_s` of *active* running – heat over electricity of the same intervals,
never an average of momentary ratios – and only while the heat pump heats now: water flowing, ΔT above zero, a fresh
electric reading above the compressor threshold, no defrost. A run starts its window afresh (no spike from the start of
a run mixed with the end of the last), and the COP is shown only after `hm_cop_min_s` of active running. Otherwise it
is None (unavailable, a gap on the chart) – never 0, never infinite; above `hm_cop_max` it is implausible: None.
The day's COP is the day's heat over the day's electricity on the same active intervals, with its coverage.

Whole-degree thermometers (many Tuya units) make a small ΔT very uncertain: ± resolution / ΔT is shown with it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, fields
from datetime import datetime

WATER_KW = 0.06977  # kW per l/min and K for water (4.186 kJ/(kg·K) × 1 kg/l / 60 s)
TEMP_MIN, TEMP_MAX = -20.0, 100.0  # a water thermometer outside these is broken
FLOW_MAX = 2000.0  # l/min
STATE_VERSION = 1


@dataclass(frozen=True)
class HeatMeterConfig:
    hm_factor: float = 1.0  # heat capacity against pure water (a glycol mix is below 1)
    hm_max_age_s: float = 300.0  # a reading not reported for this long is stale (temperatures, flow, power)
    hm_max_gap_s: float = 120.0  # two readings further apart than this: no energy for the gap
    hm_min_flow: float = 0.5  # l/min: below this the water stands
    hm_resolution: float = 1.0  # °C: the thermometers' resolution (shown as the ΔT's uncertainty)
    hm_cop_window_s: float = 600.0  # the current COP's window
    hm_cop_min_s: float = 300.0  # active running needed in the window before a COP is shown
    hm_cop_max: float = 10.0  # above this a COP is implausible (a stale or wrong reading)
    hm_power_scope: str = "unit"  # what the power meter measures: "unit" (the whole unit) | "compressor"

    @classmethod
    def from_conf(cls, conf: dict) -> "HeatMeterConfig":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in conf.items() if k in known and v is not None})


@dataclass(frozen=True)
class HmSample:
    now: datetime
    t_out: float | None  # °C, None: missing / stale / not a number
    t_in: float | None
    flow: float | None  # l/min
    p_el_w: float | None = None  # W, None: no fresh electric reading
    running_w: float = 100.0  # the compressor's threshold (hp_running_w)
    busy: bool = False  # defrost / hot water: not heating the circuit
    power_source: bool = True  # an electric power reading is configured at all


def heat_kw(flow: float, t_out: float, t_in: float, factor: float = 1.0) -> float:
    """The water's heat flow in kW (never negative)."""
    return max(0.0, flow * max(0.0, t_out - t_in) * WATER_KW * factor)


class HeatMeter:
    def __init__(self, cfg: HeatMeterConfig | None = None) -> None:
        self.cfg = cfg or HeatMeterConfig()
        self.total_kwh = 0.0
        self.total_el_kwh = 0.0  # electricity of the active intervals (the all-time COP)
        self.total_cop_heat_kwh = 0.0  # heat of the same intervals
        self.day: str | None = None
        self.day_heat_kwh = 0.0
        self.day_el_kwh = 0.0
        self.day_cop_heat_kwh = 0.0
        self.day_cop_s = 0.0  # active time with a valid electric reading
        self.day_heat_s = 0.0  # time the water carried heat
        self._last: tuple | None = None  # (time, P_th kW, P_el kW or None, active)
        self._window: deque = deque()  # (end time, dt s, heat kWh, electricity kWh) of active intervals
        self.info: dict = {}

    # --- one reading ------------------------------------------------------------------------------------------------
    def step(self, s: HmSample) -> dict:
        cfg = self.cfg
        day = s.now.date().isoformat()
        if day != self.day:
            self.day, self.day_heat_kwh, self.day_el_kwh, self.day_cop_heat_kwh = day, 0.0, 0.0, 0.0
            self.day_cop_s = self.day_heat_s = 0.0
        valid = all(v is not None for v in (s.t_out, s.t_in, s.flow)) \
            and TEMP_MIN <= s.t_out <= TEMP_MAX and TEMP_MIN <= s.t_in <= TEMP_MAX and 0.0 <= s.flow <= FLOW_MAX
        if not valid:
            self._last = None  # the counting pauses; the next valid reading starts again from there
            self._window.clear()
            self.info = {"valid": False, "reason": "missing", "power_kw": None, "cop": None, "cop_raw": None,
                         "cop_reason": "missing", **self._totals()}
            return self.info
        flowing = s.flow >= cfg.hm_min_flow
        dt_c = s.t_out - s.t_in
        p_th = heat_kw(s.flow, s.t_out, s.t_in, cfg.hm_factor) if flowing else 0.0
        p_el = None if s.p_el_w is None or s.p_el_w < 0 else s.p_el_w / 1000.0
        cop_reason = None
        if not s.power_source:
            cop_reason = "no_power_meter"
        elif p_el is None:
            cop_reason = "stale_power"
        elif not flowing:
            cop_reason = "no_flow"
        elif s.busy:
            cop_reason = "defrost"
        elif dt_c <= 0:
            cop_reason = "negative_dt"
        elif s.p_el_w <= s.running_w:
            cop_reason = "not_running"
        active = cop_reason is None
        # the interval since the last valid reading
        if self._last is not None:
            t0, p0, e0, a0 = self._last
            dt = (s.now - t0).total_seconds()
            if 0 < dt <= cfg.hm_max_gap_s:
                e_th = (p0 + p_th) / 2 * dt / 3600
                self.total_kwh += e_th
                self.day_heat_kwh += e_th
                if p0 > 0 or p_th > 0:
                    self.day_heat_s += dt
                if a0 and active and e0 is not None:
                    e_el = (e0 + p_el) / 2 * dt / 3600
                    self.day_el_kwh += e_el
                    self.day_cop_heat_kwh += e_th
                    self.day_cop_s += dt
                    self.total_el_kwh += e_el
                    self.total_cop_heat_kwh += e_th
                    self._window.append((s.now, dt, e_th, e_el))
        self._last = (s.now, p_th, p_el, active)
        if not active:
            self._window.clear()  # a new run starts its own window
        while self._window and (s.now - self._window[0][0]).total_seconds() > cfg.hm_cop_window_s:
            self._window.popleft()
        cop = cop_raw = None
        if active:
            cop_raw = p_th / p_el if p_el > 0 else None
            if cop_raw is not None and not 0 < cop_raw <= cfg.hm_cop_max:
                cop_raw = None
            span = sum(w[1] for w in self._window)
            e_th_w, e_el_w = sum(w[2] for w in self._window), sum(w[3] for w in self._window)
            if span < cfg.hm_cop_min_s:
                cop_reason = "warming_up"
            elif e_el_w <= 0:
                cop_reason = "stale_power"
            else:
                value = e_th_w / e_el_w
                if 0 < value <= cfg.hm_cop_max:
                    cop = round(value, 2)
                else:
                    cop_reason = "implausible"
        self.info = {"valid": True, "reason": None, "power_kw": round(p_th, 3), "dt": round(dt_c, 2),
                     "flow": round(s.flow, 2), "t_out": s.t_out, "t_in": s.t_in,
                     "uncertainty_pct": round(100 * cfg.hm_resolution / dt_c) if dt_c > 0 and flowing else None,
                     "p_el_kw": None if p_el is None else round(p_el, 3), "cop": cop,
                     "cop_raw": None if cop_raw is None else round(cop_raw, 2), "cop_reason": cop_reason,
                     "active": active, "window_s": round(sum(w[1] for w in self._window)), **self._totals()}
        return self.info

    def _totals(self) -> dict:
        cop_day = self.day_cop_heat_kwh / self.day_el_kwh if self.day_el_kwh > 0.001 else None
        cop_all = self.total_cop_heat_kwh / self.total_el_kwh if self.total_el_kwh > 0.001 else None
        return {"total_kwh": round(self.total_kwh, 3), "today_kwh": round(self.day_heat_kwh, 3),
                "today_el_kwh": round(self.day_el_kwh, 3),
                "cop_today": None if cop_day is None or cop_day > self.cfg.hm_cop_max else round(cop_day, 2),
                "cop_total": None if cop_all is None or cop_all > self.cfg.hm_cop_max else round(cop_all, 2),
                # the share of today's heat-carrying time with a valid electric reading
                "coverage_pct": round(100 * self.day_cop_s / self.day_heat_s) if self.day_heat_s >= 60 else None}

    # --- persistence ------------------------------------------------------------------------------------------------
    def state(self) -> dict:
        return {"v": STATE_VERSION, "total_kwh": self.total_kwh, "total_el_kwh": self.total_el_kwh,
                "total_cop_heat_kwh": self.total_cop_heat_kwh, "day": self.day, "day_heat_kwh": self.day_heat_kwh,
                "day_el_kwh": self.day_el_kwh, "day_cop_heat_kwh": self.day_cop_heat_kwh, "day_cop_s": self.day_cop_s,
                "day_heat_s": self.day_heat_s}

    def restore(self, data: dict | None) -> None:
        """The counters come back; the last reading does not – the time while HA was down adds nothing."""
        if not data or data.get("v") != STATE_VERSION:
            return
        try:
            for key in ("total_kwh", "total_el_kwh", "total_cop_heat_kwh", "day_heat_kwh", "day_el_kwh",
                        "day_cop_heat_kwh", "day_cop_s", "day_heat_s"):
                setattr(self, key, max(0.0, float(data.get(key) or 0.0)))
            self.day = data.get("day")
        except (TypeError, ValueError):
            pass
        self.info = self._totals()

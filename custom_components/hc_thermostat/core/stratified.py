"""0.54.0 – a stratified buffer tank: up to four thermometers at different heights, what the tank holds and what a
circuit can still use of it. Information only – it switches nothing.

The tank is split into layers, one per thermometer (top, upper, lower, bottom), each with its share of the volume
(`buffer_share_*`, % – default an equal share of the given thermometers). A thermometer with no fresh reading takes
the temperature of its nearest neighbour that has one (the result is then marked `estimated`).

- stored heat (kWh) = Σ volume_i × 1.163 Wh/(l·K) × max(0, T_i − base), base = `buffer_base_temp` (25 °C: below it the
  water heats nothing). With no volume given there are no kWh, only the percentage and the trend in °C/h.
- charge (%) = Σ share_i × (T_i − base) / (full − base), each layer clamped to 0…100 %, full = `buffer_off`. An existing
  percentage sensor of the tank (`buffer_charge_entity`) is taken over unchanged when given; the method says which.
- usable heat for a circuit asking for `flow` °C: only the layers at or above flow + margin reach the circuit; each gives
  its heat down to the circuit's return (flow − its ΔT): Σ volume_i × 1.163 × (T_i − return). Satisfied: the top at
  or above flow + margin. Four thermometers make this an estimate, more so while the tank charges or empties fast.
- trend: the change of the stored heat (kWh/h) and of the weighted mean temperature (°C/h) over the last
  `TREND_WINDOW_S`; charging / emptying beyond a small band, else steady.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

KWH_PER_L_K = 0.001163  # 1 m³ of water, 1 K ≈ 1.163 kWh
LAYERS = ("top", "upper", "lower", "bottom")
TREND_WINDOW_S = 1800.0
TREND_MIN_SPAN_S = 600.0
TREND_BAND_C_H = 0.5  # °C/h of the mean temperature: within this the tank is steady


@dataclass(frozen=True)
class Layer:
    name: str
    temp: float | None  # None: no reading and no neighbour either
    share: float  # 0..1 of the volume
    measured: bool  # False: the temperature is the neighbour's


@dataclass(frozen=True)
class Stock:
    layers: tuple[Layer, ...]
    volume_l: float
    base: float
    full: float
    top: float | None
    bottom: float | None
    mean: float | None  # weighted mean temperature
    stored_kwh: float | None  # None without a volume
    capacity_kwh: float | None  # stored heat of a tank at `full` all through
    charge_layers: float | None  # % worked out from the layers
    charge: float | None  # % shown: the taken-over sensor when given, else the layers'
    charge_method: str  # external | layers | none
    estimated: bool  # a layer's temperature was taken from its neighbour
    details: dict = field(default_factory=dict)

    def usable(self, flow: float | None, circuit_dt: float, margin: float) -> dict:
        """What a circuit asking for `flow` °C gets of the tank: usable kWh (None without a volume), whether the top is
        warm enough, the warmest water it can get."""
        if flow is None or self.top is None:
            return {"flow": flow, "satisfied": None, "usable_kwh": None, "reach": None}
        need = flow + margin
        ret = flow - circuit_dt
        reach = [l for l in self.layers if l.temp is not None and l.temp >= need]
        kwh = None
        if self.volume_l > 0:
            kwh = round(sum(self.volume_l * l.share * KWH_PER_L_K * (l.temp - ret) for l in reach), 2)
        return {"flow": flow, "need": round(need, 1), "return": round(ret, 1), "satisfied": self.top >= need,
                "usable_kwh": kwh, "reach": len(reach)}


def shares(given: list[str], conf: dict) -> dict[str, float]:
    """The share of each given layer (0..1, summing to 1); missing or zero settings share equally."""
    raw = {n: float(conf.get(f"buffer_share_{n}") or 0) for n in given}
    if not given:
        return {}
    even = 100 / len(given)
    raw = {n: (v if v > 0 else even) for n, v in raw.items()}  # an unset layer counts as an even share
    total = sum(raw.values())
    return {n: raw[n] / total for n in given}


def stock(readings: dict[str, float | None], given: list[str], conf: dict, external: float | None = None) -> Stock:
    """readings: layer -> °C (None: no fresh reading); given: the layers that have a thermometer, top first."""
    base = float(conf.get("buffer_base_temp", 25.0) or 25.0)
    full = float(conf.get("buffer_off", 65.0) or 65.0)
    volume = float(conf.get("buffer_volume_l", 0.0) or 0.0)
    order = [n for n in LAYERS if n in given]
    part = shares(order, conf)
    temps = [readings.get(n) for n in order]
    layers, estimated = [], False
    for i, n in enumerate(order):
        t, measured = temps[i], temps[i] is not None
        if t is None:
            near = sorted((abs(j - i), j) for j, v in enumerate(temps) if v is not None)
            if near:
                d = near[0][0]
                same = [temps[j] for k, j in near if k == d]  # equally near above and below: their mean
                t = sum(same) / len(same)
                estimated = True
        layers.append(Layer(n, None if t is None else round(t, 2), part[n], measured))
    known = [l for l in layers if l.temp is not None]
    top = layers[0].temp if layers else None
    bottom = layers[-1].temp if len(layers) > 1 else None
    mean = round(sum(l.temp * l.share for l in known) / sum(l.share for l in known), 2) if known else None
    stored = capacity = None
    if volume > 0 and known:
        stored = round(sum(volume * l.share * KWH_PER_L_K * max(0.0, l.temp - base) for l in known), 2)
        capacity = round(volume * KWH_PER_L_K * max(0.0, full - base), 2)
    charge_layers = None
    if known and full > base:
        charge_layers = round(100 * sum(l.share * max(0.0, min(1.0, (l.temp - base) / (full - base))) for l in known)
                              / sum(l.share for l in known), 1)
    if external is not None:
        charge, method = round(float(external), 1), "external"
    elif charge_layers is not None:
        charge, method = charge_layers, "layers"
    else:
        charge, method = None, "none"
    return Stock(tuple(layers), volume, base, full, top, bottom, mean, stored, capacity, charge_layers, charge, method,
                 estimated)


class StockTrend:
    """The change of the tank over the last half hour: kWh/h (with a volume) and °C/h of the mean temperature."""

    def __init__(self) -> None:
        self._points: deque[tuple[datetime, float | None, float]] = deque()

    def add(self, now: datetime, s: Stock) -> dict:
        if s.mean is not None:
            self._points.append((now, s.stored_kwh, s.mean))
        while self._points and (now - self._points[0][0]).total_seconds() > TREND_WINDOW_S:
            self._points.popleft()
        return self.trend()

    def trend(self) -> dict:
        if len(self._points) < 2:
            return {"state": None, "kwh_per_h": None, "c_per_h": None}
        (t0, e0, m0), (t1, e1, m1) = self._points[0], self._points[-1]
        span = (t1 - t0).total_seconds()
        if span < TREND_MIN_SPAN_S:
            return {"state": None, "kwh_per_h": None, "c_per_h": None}
        c_h = (m1 - m0) * 3600 / span
        kwh_h = (e1 - e0) * 3600 / span if e0 is not None and e1 is not None else None
        state = "charging" if c_h > TREND_BAND_C_H else "emptying" if c_h < -TREND_BAND_C_H else "steady"
        return {"state": state, "kwh_per_h": None if kwh_h is None else round(kwh_h, 2), "c_per_h": round(c_h, 2)}

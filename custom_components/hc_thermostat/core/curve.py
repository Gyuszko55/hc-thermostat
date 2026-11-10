"""Heating curve with room correction, for modulating boilers and heat pumps (stage 4 – EXPERIMENTAL).

Not yet tested on a real OpenTherm / eBUS boiler or heat pump; developed against the simulator only.

flow = target + slope × (target − outdoor) + shift          (the weather-compensated curve)
     + room_kp × (target − indoor) + integral                (room correction; the integral grows by
                                                              room_ki_per_hour × error per hour, bounded)
clamped to [flow_min, flow_max]. There is no heat demand when the flow would not be at least
`flow_off_delta` above the room: then the heat source is switched off instead of running cold.
Typical slopes: radiators 1.2-1.6, floor heating 0.4-0.7.
"""

from __future__ import annotations

from datetime import datetime


class CurveRegulator:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.integral = 0.0
        self._last: datetime | None = None

    def base(self, target: float, outdoor: float) -> float:
        cfg = self.cfg
        return target + cfg.curve_slope * max(target - outdoor, 0.0) + cfg.curve_shift

    def update(self, target: float, indoor: float, outdoor: float | None, now: datetime) -> float | None:
        """The flow setpoint in °C, or None when there is no heat demand."""
        cfg = self.cfg
        if outdoor is None:
            outdoor = cfg.curve_design_outdoor  # no outdoor reading: assume the design day (safe side)
        dt = 0.0 if self._last is None else max((now - self._last).total_seconds(), 0.0)
        self._last = now
        error = target - indoor
        limit = cfg.room_integral_limit
        self.integral = max(-limit, min(limit, self.integral + cfg.room_ki_per_hour * error * dt / 3600))
        flow = self.base(target, outdoor) + cfg.room_kp * error + self.integral
        flow = max(cfg.flow_min, min(cfg.flow_max, flow))
        if flow < indoor + cfg.flow_off_delta or indoor >= target + cfg.overshoot_stop:
            return None
        return round(flow, 1)

    def hold(self, now: datetime) -> None:
        self._last = now

    def state(self) -> dict:
        return {"integral": self.integral}

    def restore(self, data: dict) -> None:
        self.integral = float(data.get("integral", 0.0))


def flow_request(cfg, target: float | None, indoor: float | None, outdoor: float | None) -> float | None:
    """The flow a zone asks of a central modulating boiler: its own curve plus a room correction (0.27.0).

    No integral here: the zone already regulates its valve (PWM/PID); the request only tells the boiler how
    warm the water should be. None when the zone has no target or room reading.
    """
    if target is None or indoor is None:
        return None
    if outdoor is None:
        outdoor = cfg.curve_design_outdoor
    flow = target + cfg.curve_slope * max(target - outdoor, 0.0) + cfg.curve_shift + cfg.room_kp * max(target - indoor, 0.0)
    return round(max(cfg.flow_min, min(cfg.flow_max, flow)), 1)


class RunGate:
    """Minimum run and pause times for a heat source switched by demand (no PWM)."""

    def __init__(self) -> None:
        self.output = False
        self.last_change: datetime | None = None

    def force_off(self, now: datetime) -> bool:
        """Off at once, ignoring the minimum run time (a safety limit)."""
        if self.output:
            self.output, self.last_change = False, now
        return False

    def step(self, now: datetime, want: bool, min_on_s: float, min_off_s: float) -> tuple[bool, str | None]:
        if want == self.output:
            return self.output, None
        if self.last_change is not None:
            since = (now - self.last_change).total_seconds()
            if self.output and since < min_on_s:
                return True, "min_on"
            if not self.output and since < min_off_s:
                return False, "min_off"
        self.output, self.last_change = want, now
        return self.output, None

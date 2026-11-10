"""Central boiler for several zones (stage 3).

Every zone is its own HC instance: a manifold valve actuator on a relay (floor heating, long cycle) or a
TRV through the external-thermostat mode. The zones only open and close their own valves; the central
boiler decides when the boiler and its pump may run:

- it heats when at least `central_min_zones` zones ask for heat, or their summed demand reaches
  `central_min_demand` (a single tiny demand alone does not start the boiler);
- it starts only when at least one asking zone's valve is open: a thermoelectric actuator needs
  `central_valve_open_s` seconds after being switched on (or a position/end switch says it is open),
  so the pump never runs against closed circuits;
- when the last valve closes, the boiler stops at once (even inside its minimum run time: a closed circuit
  is worse than a short burn);
- a valve whose feedback still says closed `central_stuck_s` seconds after its zone asked is reported as
  stuck (the zone does not count as open, the boiler does not start for it);
- otherwise the boiler limits hold: `central_min_on_s` / `central_min_off_s`;
- pump overrun: after the boiler stops, the pump runs on for `central_pump_overrun_s` seconds to carry the
  heat out of the boiler – but only while a circuit is open: a valve whose feedback says open, a relay zone
  that stopped asking less than `central_valve_open_s` ago (a thermoelectric actuator closes about as slowly
  as it opens), or always when the system has a bypass (`central_pump_bypass`). TRV zones without feedback
  do not count: their valve may already be shut.
- modulating boiler (0.27.0): every zone publishes the flow its own curve asks for (`flow_request`); while
  the boiler runs, the flow setpoint is the highest request of the open asking zones (of all asking zones
  while the valves are still opening), or `central_flow_default` when no zone sends one, clamped to
  [`central_flow_min`, `central_flow_max`]. So the coldest / steepest zone sets the water temperature and
  the other zones throttle with their valves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass(frozen=True)
class ZoneState:
    name: str
    wants_heat: bool  # the zone's own decision (its valve should be open)
    demand: float = 0.0  # 0..1
    valve_on_since: datetime | None = None  # when the zone switched its valve on (None: off)
    valve_open: bool | None = None  # feedback from a position or end switch, when there is one
    fault: bool = False  # zone sensor lost or similar: it does not count
    valve_off_since: datetime | None = None  # when the zone stopped asking (its relay valve is closing)
    trv: bool = False  # the zone drives a TRV (external thermostat), not a relay valve
    flow_request: float | None = None  # °C: the flow the zone's own curve asks for (modulating boiler)


@dataclass(frozen=True)
class CentralDecision:
    now: datetime
    output: bool
    reason: str  # no_demand | waiting_valves | heating | min_on | min_off | valves_closed
    asking: tuple = ()  # zones that ask for heat
    open_zones: tuple = ()  # asking zones whose valve is open
    demand: float = 0.0
    details: dict = field(default_factory=dict)
    pump: bool = False  # the pump should run (with the boiler, or in its overrun)
    flow_setpoint: float | None = None  # modulating boiler: the flow to write (None: off)


@dataclass
class CentralConfig:
    central_min_zones: int = 1
    central_min_demand: float = 0.0  # summed demand that also starts the boiler (0 = off)
    central_valve_open_s: float = 180.0
    central_min_on_s: float = 300.0
    central_min_off_s: float = 300.0
    central_stuck_s: float = 600.0  # feedback still closed this long after the zone asked: stuck valve
    central_keep_alive_s: float = 0.0  # resend "on" to the boiler relay this often while on; 0 = off
    central_pump_overrun_s: float = 180.0  # pump runs on this long after the boiler stops; 0 = off
    central_pump_bypass: bool = False  # a bypass or always-open circuit: the overrun never meets closed valves
    central_flow_min: float = 25.0  # modulating boiler: lowest flow setpoint
    central_flow_max: float = 75.0  # ... highest flow setpoint
    central_flow_default: float = 55.0  # ... when no asking zone sends a request


OPEN_PERCENT = 20.0  # a valve position at or above this lets enough water through


def feedback_open(state: str | None, attrs: dict | None = None) -> bool | None:
    """Valve feedback from an end switch (binary_sensor), a position sensor (%) or a valve/cover entity.

    None when there is no usable reading: the central boiler then falls back to the opening time.
    """
    attrs = attrs or {}
    if state in (None, "unavailable", "unknown"):
        return None
    position = attrs.get("current_position")
    if isinstance(position, (int, float)):
        return position >= OPEN_PERCENT
    if state in ("on", "open", "opening"):
        return True
    if state in ("off", "closed", "closing"):
        return False
    try:
        return float(state) >= OPEN_PERCENT
    except ValueError:
        return None


class CentralBoiler:
    def __init__(self, cfg: CentralConfig | None = None) -> None:
        self.cfg = cfg or CentralConfig()
        self.output = False
        self.last_change: datetime | None = None
        self.pump_until: datetime | None = None

    def _circuit_open(self, zones: list[ZoneState], now: datetime) -> bool:
        """Is there still an open circuit for the pump overrun?"""
        if self.cfg.central_pump_bypass:
            return True
        for z in zones:
            if z.fault:
                continue
            if z.valve_open is not None:  # feedback (or an asking TRV zone): it knows
                if z.valve_open:
                    return True
                continue
            if z.trv:
                continue
            if z.valve_on_since is not None and self._valve_open(z, now):
                return True
            if (z.valve_off_since is not None
                    and (now - z.valve_off_since).total_seconds() < self.cfg.central_valve_open_s):
                return True
        return False

    def _pump(self, now: datetime, was_on: bool, zones: list[ZoneState]) -> tuple[bool, datetime | None]:
        cfg = self.cfg
        if self.output:
            self.pump_until = None
            return True, None
        if was_on and cfg.central_pump_overrun_s > 0:
            self.pump_until = now + timedelta(seconds=cfg.central_pump_overrun_s)
        if self.pump_until is None or now >= self.pump_until or not self._circuit_open(zones, now):
            self.pump_until = None
            return False, None
        return True, self.pump_until

    def _valve_open(self, zone: ZoneState, now: datetime) -> bool:
        if zone.valve_open is not None:
            return zone.valve_open
        return zone.valve_on_since is not None and (now - zone.valve_on_since).total_seconds() >= self.cfg.central_valve_open_s

    def _flow(self, asking: list[ZoneState], open_zones: list[ZoneState]) -> tuple[float, str | None]:
        """Flow setpoint while the boiler runs: the highest request (open zones first), and whose it is."""
        cfg = self.cfg
        pool = [z for z in (open_zones or asking) if z.flow_request is not None]
        if pool:
            top = max(pool, key=lambda z: z.flow_request)
            flow, by = top.flow_request, top.name
        else:
            flow, by = cfg.central_flow_default, None
        return round(max(cfg.central_flow_min, min(cfg.central_flow_max, flow)), 1), by

    def step(self, now: datetime, zones: list[ZoneState]) -> CentralDecision:
        cfg = self.cfg
        asking = [z for z in zones if z.wants_heat and not z.fault]
        open_zones = [z for z in asking if self._valve_open(z, now)]
        any_open = any(self._valve_open(z, now) for z in zones)  # a closing valve still makes a circuit
        demand = round(sum(max(0.0, min(1.0, z.demand)) for z in asking), 3)
        stuck = [z.name for z in asking if z.valve_open is False and z.valve_on_since is not None
                 and (now - z.valve_on_since).total_seconds() >= cfg.central_stuck_s]
        enough = len(asking) >= cfg.central_min_zones or (cfg.central_min_demand > 0 and demand >= cfg.central_min_demand)
        since = (now - self.last_change).total_seconds() if self.last_change else None

        if not asking or not enough:
            want, reason = False, "no_demand"
        elif not open_zones:
            want, reason = False, "waiting_valves"
        else:
            want, reason = True, "heating"

        if self.output and not want and not any_open:
            # No open circuit: stop now, whatever the minimum run time says.
            reason = "valves_closed" if asking else reason
        elif want != self.output and since is not None:
            if self.output and since < cfg.central_min_on_s:
                want, reason = True, "min_on"
            elif not self.output and since < cfg.central_min_off_s:
                want, reason = False, "min_off"
        was_on = self.output
        if want != self.output:
            self.output, self.last_change = want, now
        pump, pump_until = self._pump(now, was_on and not self.output, zones)
        details = {"stuck": stuck}
        if pump_until is not None:
            details["pump_until"] = pump_until.isoformat()
        flow = None
        if self.output:
            flow, details["flow_by"] = self._flow(asking, open_zones)
            details["flow_requests"] = {z.name: z.flow_request for z in asking if z.flow_request is not None}
        return CentralDecision(now, self.output, reason, tuple(z.name for z in asking),
                               tuple(z.name for z in open_zones), demand, details, pump, flow)

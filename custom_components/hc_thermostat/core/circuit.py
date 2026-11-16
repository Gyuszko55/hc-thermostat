"""0.54.0 – a mixing circuit fed from a buffer tank: the flow target it should get. Shadow only (information): HC works
the target out and shows it; the PLC / mixer keeps driving its own valve, pump and safety limits. Writing the target to
a number comes later (0.56.0) and only after a supervised trial.

The rooms keep their own HC zones (TPI / PWM on their valves). The circuit only reads them:
- a zone has a lasting demand when it asked for heat (hvac_action heating) at any time in the last `circuit_hold_s`
  (30 minutes): a TPI pulse switching off for some minutes does not drop the demand;
- raw target = curve at the room target + room correction:
      t_room + slope × max(t_room − outdoor, 0) + shift + kp × min(deficit, DEFICIT_CAP)
  t_room: the highest target of the zones with a lasting demand; with none (0.62.0) the highest target of all the
  circuit's zones, so a TPI / PWM pause does not drop the water to a 20 °C room's curve – whether the water flows is
  the circuit's demand (the pump enable), a separate output; `circuit_room` (20 °C) only when no zone has a target, or
  always without demand when `circuit_idle_keep` is off (the behaviour before 0.62.0);
  deficit: the largest (target − room temperature) of those zones;
  clamped to [`circuit_flow_min`, `circuit_flow_max`] – the floor circuit's maximum (36 °C in the reference house) is
  the water's flow limit, not the floor surface limit; that protection stays on the hydraulic / PLC side.
- no outdoor reading: no raw target; the given-out one stays (no guess from a lost sensor).
- the given-out target follows the raw one through core/setpoint_hold.py (deadband, confirmation, interval, rise limit).

Defaults per circuit type (all settable): radiator slope 1.2, 30–55 °C, kp 2, ΔT 10; floor slope 0.5, 22–36 °C, kp 1,
ΔT 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .setpoint_hold import HoldConfig, HoldResult, SetpointHold

DEFICIT_CAP = 3.0  # °C of room deficit that still raises the water

KINDS = ("radiator", "floor")
DEFAULTS = {
    "radiator": {"circuit_slope": 1.2, "circuit_flow_min": 30.0, "circuit_flow_max": 55.0, "circuit_kp": 2.0,
                 "circuit_dt": 10.0},
    "floor": {"circuit_slope": 0.5, "circuit_flow_min": 22.0, "circuit_flow_max": 36.0, "circuit_kp": 1.0,
              "circuit_dt": 5.0},
}


@dataclass
class CircuitConfig:
    circuit_kind: str = "radiator"
    circuit_slope: float = 1.2
    circuit_shift: float = 0.0
    circuit_room: float = 20.0
    circuit_flow_min: float = 30.0
    circuit_flow_max: float = 55.0
    circuit_kp: float = 2.0
    circuit_dt: float = 10.0  # the circuit's flow − return at design (for the usable heat of the tank)
    circuit_margin: float = 2.0  # the tank's top must be this much above the flow target
    circuit_hold_s: float = 1800.0  # a zone that asked within this counts as a lasting demand
    circuit_deadband: float = 1.5
    circuit_confirm_s: float = 600.0
    circuit_min_interval_s: float = 1500.0
    circuit_max_rise: float = 3.0
    circuit_urgent: float = 5.0
    circuit_idle_keep: bool = True  # 0.62.0: without demand the curve stays at the zones' targets

    @classmethod
    def from_conf(cls, conf: dict) -> "CircuitConfig":
        kind = conf.get("circuit_kind") if conf.get("circuit_kind") in KINDS else "radiator"
        known = cls.__dataclass_fields__
        values = {**DEFAULTS[kind], **{k: v for k, v in conf.items() if k in known and v is not None}}
        values["circuit_kind"] = kind
        return cls(**values)

    def hold(self) -> HoldConfig:
        return HoldConfig(self.circuit_deadband, self.circuit_confirm_s, self.circuit_min_interval_s,
                          self.circuit_max_rise, self.circuit_urgent)


@dataclass(frozen=True)
class ZoneReading:
    name: str
    asking: bool  # hvac_action heating now
    target: float | None = None
    indoor: float | None = None
    fault: bool = False


@dataclass(frozen=True)
class CircuitDecision:
    now: datetime
    target: float | None  # given out
    raw: float | None  # worked out, within the limits
    reason: str  # see HoldResult.reason
    demand: bool  # a lasting demand in the circuit
    lasting: tuple = ()  # zones with a lasting demand
    asking: tuple = ()  # zones asking now
    outdoor: float | None = None
    t_room: float | None = None
    deficit: float = 0.0
    details: dict = field(default_factory=dict)


class MixingCircuit:
    def __init__(self, cfg: CircuitConfig | None = None) -> None:
        self.cfg = cfg or CircuitConfig()
        self.hold = SetpointHold(self.cfg.hold())
        self.last_ask: dict[str, datetime] = {}

    def raw(self, outdoor: float | None, t_room: float, deficit: float) -> float | None:
        cfg = self.cfg
        if outdoor is None:
            return None
        flow = (t_room + cfg.circuit_slope * max(t_room - outdoor, 0.0) + cfg.circuit_shift
                + cfg.circuit_kp * min(max(deficit, 0.0), DEFICIT_CAP))
        return round(flow, 2)

    def step(self, now: datetime, zones: list[ZoneReading], outdoor: float | None) -> CircuitDecision:
        cfg = self.cfg
        names = {z.name for z in zones}
        for gone in [n for n in self.last_ask if n not in names]:
            self.last_ask.pop(gone)
        for z in zones:
            if z.asking and not z.fault:
                self.last_ask[z.name] = now
        lasting = [z for z in zones if not z.fault and z.name in self.last_ask
                   and (now - self.last_ask[z.name]).total_seconds() <= cfg.circuit_hold_s]
        targets = [z.target for z in lasting if z.target is not None]
        room_from = "demand" if targets else "default"
        if not targets and cfg.circuit_idle_keep:
            targets = [z.target for z in zones if not z.fault and z.target is not None]
            room_from = "zones" if targets else "default"
        t_room = max(targets) if targets else cfg.circuit_room
        deficits = [z.target - z.indoor for z in lasting if z.target is not None and z.indoor is not None]
        deficit = round(max([0.0, *deficits]), 2)
        raw = self.raw(outdoor, t_room, deficit)
        res: HoldResult = self.hold.step(now, raw, cfg.circuit_flow_min, cfg.circuit_flow_max)
        details = {"curve": None if outdoor is None else round(t_room + cfg.circuit_slope * max(t_room - outdoor, 0.0)
                                                                 + cfg.circuit_shift, 2),
                   "correction": round(cfg.circuit_kp * min(deficit, DEFICIT_CAP), 2),
                   "next_allowed": res.next_allowed.isoformat() if res.next_allowed else None,
                   "last_change": self.hold.last_change.isoformat() if self.hold.last_change else None,
                   "changed": res.changed, "room_from": room_from}
        if raw is None:
            details["no_outdoor"] = True
        return CircuitDecision(now, res.value, res.raw, res.reason, bool(lasting), tuple(z.name for z in lasting),
                               tuple(z.name for z in zones if z.asking and not z.fault), outdoor, t_room, deficit,
                               details)

    def state(self, now: datetime) -> dict:
        return {"hold": self.hold.state(now), "last_ask": {k: v.isoformat() for k, v in self.last_ask.items()}}

    def restore(self, data: dict, now: datetime) -> None:
        self.hold.restore(data.get("hold") or {}, now)
        for k, v in (data.get("last_ask") or {}).items():
            try:
                self.last_ask[k] = datetime.fromisoformat(v)
            except (TypeError, ValueError):
                continue

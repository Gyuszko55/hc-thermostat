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

0.64.0 – the tank cap (`circuit_tank_cap`, on; a linked buffer only): the mixer cannot give warmer water than the
tank's top holds, so the target given to it is min(demanded, top − `circuit_margin`) – the limit on a 0.5 °C grid (a
tank cooling by 0.1 °C does not rewrite the mixer). Three values: the demanded target (the hold's output – this one
goes to the heat pump coordination, which must see the real need), the one given to the mixer, and the shortfall.
- a cooling tank lowers it at once (no confirmation); when the tank warms up again it rises by at most
  `circuit_max_rise` every `circuit_confirm_s` until it reaches the demanded target;
- a limit below `circuit_flow_min`: the minimum is given out (the mixer is fully open anyway) and the state is
  `cold` (a warning);
- no fresh top reading: the last one is used for TANK_STALE_S (15 minutes, `stale`), then no cap (`no_data`, a
  warning) – the demanded target is given out.

Defaults per circuit type (all settable): radiator slope 1.2, 30–55 °C, kp 2, ΔT 10; floor slope 0.5, 22–36 °C, kp 1,
ΔT 5.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .setpoint_hold import HoldConfig, HoldResult, SetpointHold

import math

TANK_STALE_S = 900.0  # 0.64.0: the last tank top reading keeps capping this long
CAP_STATES = ("off", "ok", "limited", "cold", "stale", "no_data")
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
    circuit_tank_cap: bool = True  # 0.64.0: the target given to the mixer is at most the tank's top − margin

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
    demand_target: float | None = None  # 0.64.0: the demanded (uncapped) target – the heat pump's need
    cap: float | None = None  # 0.64.0: the tank's limit (top − margin, on a 0.5 °C grid; None: no cap)
    cap_state: str = "off"  # 0.64.0: see CAP_STATES
    shortfall: float = 0.0  # 0.64.0: demanded − given out


class MixingCircuit:
    def __init__(self, cfg: CircuitConfig | None = None) -> None:
        self.cfg = cfg or CircuitConfig()
        self.hold = SetpointHold(self.cfg.hold())
        self.last_ask: dict[str, datetime] = {}
        # 0.64.0: the tank cap
        self.out: float | None = None
        self.out_at: datetime | None = None
        self.limited = False
        self.top: float | None = None
        self.top_at: datetime | None = None

    def cap(self, now: datetime, given: float | None, top: float | None, linked: bool) -> tuple:
        """0.64.0: (target for the mixer, limit, state) from the demanded target and the tank's top."""
        cfg = self.cfg
        if not linked or not cfg.circuit_tank_cap:
            self.out, self.limited = given, False
            return given, None, "off"
        state = "ok"
        if top is not None:
            self.top, self.top_at = top, now
        elif self.top is not None and self.top_at is not None and (now - self.top_at).total_seconds() <= TANK_STALE_S:
            top, state = self.top, "stale"
        else:
            self.out, self.limited = given, False
            return given, None, "no_data"
        limit = math.floor((top - cfg.circuit_margin) * 2 + 1e-9) / 2
        cold = limit < cfg.circuit_flow_min
        if cold:
            limit = cfg.circuit_flow_min
        if given is None:
            self.out, self.limited = None, False
            return None, limit, state
        want = min(given, limit)
        prev = self.out
        if prev is None or want <= prev or not self.limited:
            out = want  # down at once; an uncapped target already went through the hold
        elif self.out_at is None or (now - self.out_at).total_seconds() >= cfg.circuit_confirm_s:
            out = min(want, prev + cfg.circuit_max_rise)  # back up after a cap: step by step
        else:
            out = prev
        if out != prev:
            self.out_at = now
        self.out = out
        self.limited = out < given - 1e-9
        if cold:
            state = "cold"  # the tank cannot give even the minimum
        elif self.limited and state == "ok":
            state = "limited"  # a stale reading stays "stale" (it may be limiting by an old value)
        return out, limit, state

    def raw(self, outdoor: float | None, t_room: float, deficit: float) -> float | None:
        cfg = self.cfg
        if outdoor is None:
            return None
        flow = (t_room + cfg.circuit_slope * max(t_room - outdoor, 0.0) + cfg.circuit_shift
                + cfg.circuit_kp * min(max(deficit, 0.0), DEFICIT_CAP))
        return round(flow, 2)

    def step(self, now: datetime, zones: list[ZoneReading], outdoor: float | None, tank_top: float | None = None,
             tank_linked: bool = False) -> CircuitDecision:
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
        out, limit, cap_state = self.cap(now, res.value, tank_top, tank_linked)
        shortfall = round(res.value - out, 1) if res.value is not None and out is not None else 0.0
        return CircuitDecision(now, out, res.raw, res.reason, bool(lasting), tuple(z.name for z in lasting),
                               tuple(z.name for z in zones if z.asking and not z.fault), outdoor, t_room, deficit,
                               details, res.value, limit, cap_state, shortfall)

    def state(self, now: datetime) -> dict:
        return {"hold": self.hold.state(now), "last_ask": {k: v.isoformat() for k, v in self.last_ask.items()},
                "cap": {"out": self.out, "out_at": self.out_at.isoformat() if self.out_at else None,
                        "limited": self.limited, "top": self.top,
                        "top_at": self.top_at.isoformat() if self.top_at else None}}

    def restore(self, data: dict, now: datetime) -> None:
        self.hold.restore(data.get("hold") or {}, now)
        cap = data.get("cap") or {}
        try:
            self.out = None if cap.get("out") is None else float(cap["out"])
            self.limited = bool(cap.get("limited"))
            self.top = None if cap.get("top") is None else float(cap["top"])
            self.out_at = datetime.fromisoformat(cap["out_at"]) if cap.get("out_at") else None
            self.top_at = datetime.fromisoformat(cap["top_at"]) if cap.get("top_at") else None
        except (TypeError, ValueError):
            self.out, self.limited, self.top, self.out_at, self.top_at = None, False, None, None, None
        for k, v in (data.get("last_ask") or {}).items():
            try:
                self.last_ask[k] = datetime.fromisoformat(v)
            except (TypeError, ValueError):
                continue

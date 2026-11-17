"""0.70.0 – watching a mixing circuit's chain (a tester's PLC house): HC asks for heat → the pump starts (the PLC may
wait some minutes on purpose) → the flow temperature moves. Watching only: it never writes, never touches the PLC.

States (one step every 30 s, from the circuit's lasting demand, the pump entity and the flow thermometer):
- idle: no demand;
- wait_pump: demand, the pump has not started yet – normal for `circuit_watch_pump_s` (10 minutes: the PLC's 5-minute
  start delay fits in);
- no_pump: demand for longer than that and the pump still stands – a problem;
- wait_flow: the pump runs, the flow has not moved yet – normal for `circuit_watch_flow_s` (15 minutes);
- no_flow: the pump has run for longer than that and the flow neither moved by `circuit_watch_flow_c` (1 °C) nor got
  near the given-out target (within NEAR_C) – a problem (a stuck mixer, a cold tank, a dead ESP);
- ok: the pump runs and the flow moved or is near the target (kept until the demand or the pump ends);
- pump_only: no flow thermometer – the pump started, the flow is not watched;
- not_watched: no pump entity and no flow thermometer, or the watch is off.

A pump reading that is not known (unavailable) keeps the timers running but never reports a problem by itself: the
state stays the waiting one and `pump_unknown` is set. A missing flow reading likewise.
"""

from __future__ import annotations

from datetime import datetime

NEAR_C = 2.0  # a flow this close to the given-out target is fine even when it did not move (it was warm already)
PROBLEMS = ("no_pump", "no_flow")
STATES = ("idle", "wait_pump", "no_pump", "wait_flow", "no_flow", "ok", "pump_only", "not_watched")


class CircuitWatch:
    def __init__(self, pump_s: float = 600.0, flow_s: float = 900.0, flow_c: float = 1.0, enabled: bool = True) -> None:
        self.pump_s, self.flow_s, self.flow_c, self.enabled = pump_s, flow_s, flow_c, enabled
        self.state = "idle"
        self.demand_at: datetime | None = None  # the demand started
        self.pump_at: datetime | None = None  # the pump was first seen running in this demand
        self.base: float | None = None  # the flow when the pump started
        self.moved = False
        self.problem_at: datetime | None = None
        self.pump_unknown = False

    def _reset(self) -> None:
        self.demand_at = self.pump_at = self.base = self.problem_at = None
        self.moved = False

    def step(self, now: datetime, demand: bool, pump: bool | None, flow: float | None, target: float | None,
             has_pump: bool, has_flow: bool) -> str:
        if not self.enabled or not (has_pump or has_flow):
            self._reset()
            self.state = "not_watched"
            return self.state
        self.pump_unknown = has_pump and pump is None
        if not demand:
            self._reset()
            return self._set(now, "idle")
        if self.demand_at is None:
            self.demand_at = now
        # without a pump entity the flow is watched from the demand's start
        runs = pump is True if has_pump else True
        if not runs:
            self.pump_at, self.base, self.moved = None, None, False
            late = (now - self.demand_at).total_seconds() >= self.pump_s
            return self._set(now, "no_pump" if late and pump is False else "wait_pump")
        if self.pump_at is None:
            self.pump_at = now if has_pump else self.demand_at
        if not has_flow:
            return self._set(now, "pump_only")
        if flow is not None:
            if self.base is None:
                self.base = flow
            if abs(flow - self.base) >= self.flow_c or (target is not None and abs(flow - target) <= NEAR_C):
                self.moved = True
        if self.moved:
            return self._set(now, "ok")
        late = (now - self.pump_at).total_seconds() >= self.flow_s
        return self._set(now, "no_flow" if late and flow is not None else "wait_flow")

    def _set(self, now: datetime, state: str) -> str:
        if state in PROBLEMS:
            if self.state != state or self.problem_at is None:
                self.problem_at = now
        else:
            self.problem_at = None
        self.state = state
        return state

    def info(self, now: datetime) -> dict:
        def mins(t):
            return None if t is None else round((now - t).total_seconds() / 60, 1)
        return {"state": self.state, "problem": self.state in PROBLEMS, "demand_min": mins(self.demand_at),
                "pump_min": mins(self.pump_at), "base": self.base, "problem_since": self.problem_at,
                "pump_unknown": self.pump_unknown, "pump_s": self.pump_s, "flow_s": self.flow_s, "flow_c": self.flow_c}

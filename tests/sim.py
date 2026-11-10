"""A simple house: room air + radiator lag, driven by a supervisor step by step."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from core.model import Decision, HcConfig, Inputs, Presence, Reading
from core.supervisor import Supervisor

START = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)
STEP_S = 30.0


@dataclass
class House:
    indoor: float = 20.0
    outdoor: float = 0.0
    radiator: float = 0.0  # 0..1 of full power, follows the burner with a lag
    loss_tau_s: float = 20 * 3600.0
    full_power_delta: float = 40.0  # steady indoor-outdoor difference at full power
    radiator_tau_s: float = 900.0
    window_open: bool = False
    burner_works: bool = True

    def advance(self, burner_on: bool, dt: float = STEP_S) -> None:
        heat = 1.0 if burner_on and self.burner_works else 0.0
        self.radiator += (heat - self.radiator) * dt / self.radiator_tau_s
        tau = self.loss_tau_s / (8 if self.window_open else 1)
        equilibrium = self.outdoor + self.radiator * self.full_power_delta
        self.indoor += (equilibrium - self.indoor) * dt / tau


@dataclass
class Run:
    cfg: HcConfig
    house: House = field(default_factory=House)
    now: datetime = START
    sup: Supervisor | None = None
    uptime_s: float = 1e9
    enabled: bool = True
    presence: Presence = Presence.HOME
    indoor_ok: bool = True
    indoor_age_s: float = 0.0
    outdoor_avg: float | None = None
    follow: bool = True  # the burner follows the decision (False: shadow, relay independent)
    decisions: list[Decision] = field(default_factory=list)
    changes: list[tuple[datetime, bool]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.sup = self.sup or Supervisor(self.cfg)

    def tick(self, actual: bool | None = None) -> Decision:
        house = self.house
        d = self.sup.step(Inputs(
            now=self.now,
            indoor=Reading(house.indoor if self.indoor_ok else None, self.indoor_age_s),
            outdoor=Reading(house.outdoor, 0.0),
            outdoor_avg=self.outdoor_avg,
            presence=self.presence,
            window_open=house.window_open,
            enabled=self.enabled,
            uptime_s=self.uptime_s,
            actual_heating=actual,
        ))
        if not self.changes or self.changes[-1][1] != d.output:
            self.changes.append((self.now, d.output))
        self.decisions.append(d)
        burner = actual if actual is not None else d.output
        house.advance(burner)
        self.now += timedelta(seconds=STEP_S)
        self.uptime_s += STEP_S
        return d

    def run(self, hours: float = 0, minutes: float = 0, **kw) -> Decision:
        d = None
        for _ in range(int((hours * 3600 + minutes * 60) / STEP_S)):
            d = self.tick(**kw)
        return d

    def on_off_durations(self):
        out = []
        for (t1, value), (t2, _) in zip(self.changes[1:], self.changes[2:]):
            out.append((value, (t2 - t1).total_seconds()))
        return out

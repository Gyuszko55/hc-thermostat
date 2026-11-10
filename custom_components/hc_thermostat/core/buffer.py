"""Buffer tank (0.33.0): a heat source (pellet boiler, heat pump, solid fuel, an electric element) charges a tank;
the heating circuits draw from it through their own HC zones.

The buffer instance switches the source by the tank temperatures:
- a charge starts when the top of the tank is at or below `buffer_on` (45 °C) – with zones given and
  `buffer_demand_led`, only while a zone asks for heat (no warm tank kept for nothing);
- it runs until the bottom (or, with one sensor, the top) reaches `buffer_off` (65 °C) – then it stops at once,
  even inside the minimum run (a full tank has nowhere to put the heat);
- a started charge always runs until the tank is full (a pellet boiler ignites and burns out slowly, short runs
  are its worst enemy), and a new charge waits `buffer_min_off_s` (20 min) after the last one;
- frost: a tank top at or below `buffer_frost` (8 °C) charges whatever the zones say;
- no top reading: no charge (the tank could be full) – reported as "no_sensor".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BufferConfig:
    buffer_on: float = 45.0
    buffer_off: float = 65.0
    buffer_min_off_s: float = 1200.0
    buffer_frost: float = 8.0
    buffer_demand_led: bool = True


@dataclass(frozen=True)
class BufferDecision:
    now: datetime
    output: bool
    reason: str  # charging | full | ready | waiting_demand | min_off | frost | no_sensor
    top: float | None = None
    bottom: float | None = None
    asking: tuple = ()
    details: dict = field(default_factory=dict)


class BufferCharger:
    def __init__(self, cfg: BufferConfig | None = None) -> None:
        self.cfg = cfg or BufferConfig()
        self.output = False
        self.last_change: datetime | None = None

    def _switch(self, now: datetime, on: bool) -> None:
        if on != self.output:
            self.output, self.last_change = on, now

    def step(self, now: datetime, top: float | None, bottom: float | None, asking: tuple = (),
             zones_given: bool = False) -> BufferDecision:
        cfg = self.cfg
        since = (now - self.last_change).total_seconds() if self.last_change else None
        done = lambda reason: BufferDecision(now, self.output, reason, top, bottom, tuple(asking),  # noqa: E731
                                             {"buffer_on": cfg.buffer_on, "buffer_off": cfg.buffer_off})
        if top is None:
            self._switch(now, False)
            return done("no_sensor")
        full = (bottom if bottom is not None else top) >= cfg.buffer_off
        if full:
            self._switch(now, False)  # nowhere to put the heat: at once
            return done("full")
        if top <= cfg.buffer_frost:
            self._switch(now, True)
            return done("frost")
        if self.output:
            return done("charging")  # until full
        if top > cfg.buffer_on:
            return done("ready")
        if cfg.buffer_demand_led and zones_given and not asking:
            return done("waiting_demand")
        if since is not None and since < cfg.buffer_min_off_s:
            return done("min_off")
        self._switch(now, True)
        return done("charging")

    def state(self) -> dict:
        return {"output": self.output, "last_change": self.last_change.isoformat() if self.last_change else None}

    def restore(self, data: dict) -> None:
        self.output = bool(data.get("output", False))
        self.last_change = datetime.fromisoformat(data["last_change"]) if data.get("last_change") else None

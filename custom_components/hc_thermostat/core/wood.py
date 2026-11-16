"""0.61.0 – wood firing told from the wood boiler's thermometer, with two thresholds (hysteresis) and a confirmation
time: active once the boiler is at `wood_on_above` (65 °C) or warmer for `wood_confirm_s` (5 min), inactive once it is
at `wood_off_below` (60 °C) or colder for as long. Between the two the last state holds. The first reading decides at
once (no waiting after a restart); a reading between the thresholds with no state yet, or no reading, is "not known"
(None) – then the coordination falls back to the tank's trend, as without a wood signal.

A direct wood signal (`wood_entity`: a flue / boiler running contact) stays the first choice; this one is used only
without it."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class WoodConfig:
    wood_on_above: float = 65.0
    wood_off_below: float = 60.0
    wood_confirm_s: float = 300.0

    @classmethod
    def from_conf(cls, conf: dict) -> "WoodConfig":
        known = cls.__dataclass_fields__
        return cls(**{k: float(v) for k, v in conf.items() if k in known and v is not None})


class WoodDetector:
    def __init__(self, cfg: WoodConfig | None = None) -> None:
        self.cfg = cfg or WoodConfig()
        self.state: bool | None = None
        self.pending: tuple[bool, datetime] | None = None

    def step(self, now: datetime, temp: float | None) -> bool | None:
        if temp is None:
            self.pending = None
            return None
        cfg = self.cfg
        want = True if temp >= cfg.wood_on_above else False if temp <= cfg.wood_off_below else self.state
        if want is None:
            return None
        if self.state is None:  # the first reading on one side decides at once
            self.state, self.pending = want, None
            return want
        if want == self.state:
            self.pending = None
            return self.state
        if self.pending is None or self.pending[0] != want:
            self.pending = (want, now)
        if (now - self.pending[1]).total_seconds() >= cfg.wood_confirm_s:
            self.state, self.pending = want, None
        return self.state

    def info(self, now: datetime) -> dict:
        return {"state": self.state,
                "pending": None if self.pending is None else {"to": self.pending[0],
                                                              "for_s": round((now - self.pending[1]).total_seconds())}}

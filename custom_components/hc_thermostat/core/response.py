"""0.69.0: how a room answers its heating, measured from the ordinary runs (no overshoot on purpose).

A tester's first night on a buffer house: hour-long PWM cycles give clean heating / pause stretches by themselves.
From each clean run (at least MIN_RUN_S, a steady target, regulating) this keeps a running average of:
- delay: minutes from the start until the room rises RISE_C above its lowest point (valve, pump, emitter warming);
- rise: °C/h while the run heats, from that first rise to the stop;
- after-heat: how much the room still rises after the stop, and in how many minutes;
- cooling: °C/h from that peak until the next start (at least MIN_COOL_S of it).
Only shown, nothing regulates by it yet.
"""

from __future__ import annotations

from datetime import datetime

RISE_C = 0.1
FALL_C = 0.1
MIN_RUN_S = 600.0
MIN_RISE_SPAN_S = 600.0
MIN_COOL_S = 1800.0
MAX_AFTER_S = 5400.0  # the after-heat peak is looked for this long after the stop
MAX_COOL_S = 4 * 3600.0
ALPHA = 0.3
KEYS = ("delay_min", "rise_c_h", "afterheat_c", "afterheat_min", "cool_c_h")


class ResponseMeter:
    def __init__(self) -> None:
        self.values: dict[str, float] = {}
        self.samples: dict[str, int] = {}
        self.last: dict[str, float] = {}
        self._phase = "idle"
        self._target: float | None = None
        self._p: dict = {}

    # --- measuring -------------------------------------------------------------------------------------------------
    def _record(self, key: str, value: float) -> None:
        value = round(value, 2)
        old = self.values.get(key)
        self.values[key] = value if old is None else round(old + ALPHA * (value - old), 2)
        self.samples[key] = self.samples.get(key, 0) + 1
        self.last[key] = value

    def _abort(self) -> None:
        self._phase, self._p = "idle", {}

    def step(self, now: datetime, output: bool, indoor: float | None, target: float | None, clean: bool) -> None:
        if not clean or indoor is None or target is None or (self._target is not None and target != self._target):
            self._target = target if clean else None
            self._abort()
            return
        self._target = target
        p = self._p
        if output:
            if self._phase in ("after", "cool"):
                self._finish_cool(now)
            if self._phase != "run":
                self._phase, self._p = "run", {"start": now, "low": indoor, "rise_at": None, "rise_temp": None}
                return
            p["low"] = min(p["low"], indoor)
            if p["rise_at"] is None and indoor >= p["low"] + RISE_C:
                p["rise_at"], p["rise_temp"] = now, indoor
            return
        if self._phase == "run":
            ran = (now - p["start"]).total_seconds()
            if ran < MIN_RUN_S:
                self._abort()
                return
            if p["rise_at"] is not None:
                self._record("delay_min", (p["rise_at"] - p["start"]).total_seconds() / 60)
                span = (now - p["rise_at"]).total_seconds()
                if span >= MIN_RISE_SPAN_S:
                    self._record("rise_c_h", (indoor - p["rise_temp"]) / (span / 3600))
            self._phase, self._p = "after", {"stop": now, "stop_temp": indoor, "peak": indoor, "peak_at": now}
            return
        if self._phase == "after":
            if indoor > p["peak"]:
                p["peak"], p["peak_at"] = indoor, now
            elif indoor <= p["peak"] - FALL_C or (now - p["stop"]).total_seconds() >= MAX_AFTER_S:
                self._record("afterheat_c", p["peak"] - p["stop_temp"])
                self._record("afterheat_min", (p["peak_at"] - p["stop"]).total_seconds() / 60)
                self._phase, self._p = "cool", {"from": p["peak_at"], "peak": p["peak"], "now": now, "temp": indoor}
            return
        if self._phase == "cool":
            p["now"], p["temp"] = now, indoor
            if (now - p["from"]).total_seconds() >= MAX_COOL_S:
                self._finish_cool(now)

    def _finish_cool(self, now: datetime) -> None:
        p = self._p
        if self._phase == "cool":
            span = (p["now"] - p["from"]).total_seconds()
            if span >= MIN_COOL_S and p["peak"] >= p["temp"]:
                self._record("cool_c_h", (p["peak"] - p["temp"]) / (span / 3600))
        self._abort()

    # --- shown and kept --------------------------------------------------------------------------------------------
    def info(self) -> dict:
        return {"values": dict(self.values), "samples": dict(self.samples), "last": dict(self.last),
                "phase": self._phase}

    def state(self) -> dict:
        return {"values": self.values, "samples": self.samples, "last": self.last}

    def restore(self, data: dict) -> None:
        def clean(d) -> dict:
            out = {}
            for k in KEYS:
                try:
                    if (d or {}).get(k) is not None:
                        out[k] = float(d[k])
                except (TypeError, ValueError):
                    continue
            return out
        self.values, self.last = clean(data.get("values")), clean(data.get("last"))
        self.samples = {k: int(v) for k, v in clean(data.get("samples")).items()}

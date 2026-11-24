"""0.76.0: the local guard – a small program next to the relay (guard/shelly/hc_guard.js on a Shelly Gen3 / Gen4, or
the same protocol from ESPHome or a PLC) that switches the relay only while HC renews a short lease.

HC sends {"cmd": "on" | "off", "ttl", "seq", "fb": fallback values} with every changed command and at least every
`guard_every_s`; the lease is written from HC's own decision step, so a Home Assistant that runs while HC is stuck
lets it run out just like a stopped one. Without a lease the guard keeps the last command for its grace time, then
runs its own thermostat (fallback, or nosensor without a thermometer) and hands control back only after a stable lease
(handback). This module is the HC side without I/O: when to send, what, and what the guard's answer means.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

MODES = ("normal", "grace", "fallback", "nosensor", "handback", "safety")  # 0.77.0 safety: the chain is open
TAKEN_OVER = ("fallback", "nosensor")  # the guard regulates on its own
UNREACHABLE_AFTER_S = 600.0  # no answer for this long: a problem (the lease surely ran out)


@dataclass(frozen=True)
class GuardSettings:
    every_s: float = 60.0
    ttl_s: float = 300.0
    sp: float = 20.5
    hyst: float = 0.6
    min_on_s: float = 300.0
    min_off_s: float = 300.0
    max_on_s: float = 0.0
    no_sensor: str = "off"  # "off" | "duty"
    duty_on_s: float = 1200.0
    duty_off_s: float = 2400.0
    push: str = ""


class GuardLink:
    def __init__(self, settings: GuardSettings, token: str = "") -> None:
        self.s = settings
        self.token = token
        self.seq = 0
        self.last_cmd: str | None = None
        self.last_sent: datetime | None = None
        self.last_ok: datetime | None = None
        self.fail_since: datetime | None = None
        self.error: str | None = None
        self.status: dict = {}

    @staticmethod
    def _cmd(on: bool, safety: bool = False) -> str:
        """0.78.2 (M1): "safety" – HC's life-safety stop: off at once on the guard, latched there until "on"/"off"."""
        return "safety" if safety else ("on" if on else "off")

    def due(self, now: datetime, on: bool, safety: bool = False) -> bool:
        """A changed command at once; else a renewal every `every_s`; after a failure every step."""
        cmd = self._cmd(on, safety)
        return (cmd != self.last_cmd or self.last_sent is None or self.fail_since is not None
                or (now - self.last_sent).total_seconds() >= self.s.every_s)

    def payload(self, on: bool, safety: bool = False) -> dict:
        self.seq += 1
        s = self.s
        out = {"cmd": self._cmd(on, safety), "ttl": int(s.ttl_s), "seq": self.seq,
               "fb": {"sp": s.sp, "hyst": s.hyst, "min_on": int(s.min_on_s), "min_off": int(s.min_off_s),
                      "max_on": int(s.max_on_s), "ns": "duty" if s.no_sensor == "duty" else "off",
                      "don": int(s.duty_on_s), "doff": int(s.duty_off_s), "push": s.push or ""}}
        if self.token:
            out["tok"] = self.token
        return out

    def sent(self, now: datetime, on: bool, status: dict | None, safety: bool = False) -> None:
        self.last_cmd, self.last_sent, self.last_ok = self._cmd(on, safety), now, now
        self.fail_since, self.error = None, None
        self.status = status if isinstance(status, dict) else {}

    def failed(self, now: datetime, error: str) -> None:
        self.last_sent = now
        if self.fail_since is None:
            self.fail_since = now
        self.error = error

    def mode(self) -> str | None:
        m = self.status.get("mode")
        return m if m in MODES else None

    def problem(self, now: datetime) -> str | None:
        """What Repairs shows: "unreachable" after UNREACHABLE_AFTER_S without an answer, "taken_over" while the guard
        regulates on its own although HC is running (it lost a lease and has not handed back yet)."""
        if self.fail_since is not None and (now - self.fail_since).total_seconds() >= UNREACHABLE_AFTER_S:
            return "unreachable"
        if self.mode() in TAKEN_OVER:
            return "taken_over"
        return None

    def info(self, now: datetime) -> dict:
        st = self.status
        return {"mode": "unreachable" if self.problem(now) == "unreachable" else self.mode(),
                "reason": st.get("reason"), "relay": st.get("relay"), "temp": st.get("temp"),
                "lease_left_s": st.get("lease_left"), "fallback_sp": st.get("sp"),
                "last_ok": self.last_ok.isoformat() if self.last_ok else None,
                "error": self.error, "problem": self.problem(now)}

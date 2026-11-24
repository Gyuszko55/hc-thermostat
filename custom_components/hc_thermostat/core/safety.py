"""0.77.0: the life-safety stop – smoke, fire, gas, CO, water. The real stop is wired: certified detectors with their own
sirens, their normally closed contacts in series (a safety chain) holding a latching relay that keeps the gas valve
open, the heating's contactor on and the water valve open. HC only reads that chain (and, as a second signal, other
detectors): any alarm latches a stop of every instance that watches it – above every other reason, frost protection
included – until someone acknowledges it with every input clear again. A latch survives a restart.

An input reads "on" = alarm (a binary_sensor with device_class safety / smoke / gas / carbon_monoxide / moisture, or
the chain's auxiliary contact mapped so that "on" means the chain is open). "unavailable" / "unknown" does not trip
(the wired chain is what stops; a lost reading must not shut the heating down on its own) but is reported.
"""

from __future__ import annotations

from datetime import datetime

ALARM_STATES = ("on", "open", "detected", "wet", "triggered")
UNKNOWN_STATES = ("unavailable", "unknown", None)
UNKNOWN_REPORT_S = 600.0  # 0.78.2: an input without a reading this long is a Repairs entry


class SafetyLatch:
    def __init__(self) -> None:
        self.tripped = False
        self.since: datetime | None = None
        self.by: list[str] = []  # the inputs that tripped it
        self.cleared_at: datetime | None = None
        self.cleared_by: str | None = None
        self.alarms: list[str] = []  # in alarm now
        self.unknown: list[str] = []  # no reading now
        self.unknown_since: dict[str, datetime] = {}  # 0.78.2: since when each has had no reading

    def check(self, now: datetime, states: dict[str, str | None]) -> bool:
        """Reads every watched input; trips (and stays tripped) on any alarm. Returns whether the stop holds."""
        self.alarms = sorted(e for e, s in states.items() if s in ALARM_STATES)
        self.unknown = sorted(e for e, s in states.items() if s in UNKNOWN_STATES)
        self.unknown_since = {e: self.unknown_since.get(e, now) for e in self.unknown}
        if self.alarms:
            if not self.tripped:
                self.tripped, self.since, self.by = True, now, list(self.alarms)
            else:
                self.by = sorted(set(self.by) | set(self.alarms))
        return self.tripped

    def lost(self, now: datetime) -> list[str]:
        """0.78.2 (security review): the inputs without a reading for UNKNOWN_REPORT_S – they would not trip."""
        return sorted(e for e, t in self.unknown_since.items() if (now - t).total_seconds() >= UNKNOWN_REPORT_S)

    def acknowledge(self, now: datetime, who: str | None = None) -> bool:
        """Lets go only with every input clear (and read); an alarm still on keeps the stop."""
        if not self.tripped:
            return True
        if self.alarms or self.unknown:
            return False
        self.tripped, self.cleared_at, self.cleared_by = False, now, who
        return True

    def info(self) -> dict:
        return {"tripped": self.tripped, "since": self.since.isoformat() if self.since else None, "by": list(self.by),
                "alarms": list(self.alarms), "unknown": list(self.unknown),
                "cleared_at": self.cleared_at.isoformat() if self.cleared_at else None, "cleared_by": self.cleared_by}

    def state(self) -> dict:
        return {"tripped": self.tripped, "since": self.since.isoformat() if self.since else None, "by": self.by,
                "cleared_at": self.cleared_at.isoformat() if self.cleared_at else None, "cleared_by": self.cleared_by}

    def restore(self, data: dict | None) -> None:
        if not data:
            return
        try:
            self.tripped = bool(data.get("tripped"))
            self.since = datetime.fromisoformat(data["since"]) if data.get("since") else None
            self.by = [str(x) for x in data.get("by") or []]
            self.cleared_at = datetime.fromisoformat(data["cleared_at"]) if data.get("cleared_at") else None
            self.cleared_by = data.get("cleared_by")
        except (TypeError, ValueError, KeyError):
            self.tripped = True  # a broken record: stay on the safe side until acknowledged

"""0.56.0 – writing a target out (a mixing circuit's flow target to the PLC, the heat pump's ON/OFF and flow target):
when HC writes, and when it does not.

One writer per target: HC writes only when the value there differs from what it wants (or a keep-alive is due). If
the value changes to something HC did not write – the PLC, a person, an automation – that is a **conflict**: HC stops
writing that target and says so, until the value there is HC's own again (the other writer gave way) or the instance
is reloaded. HC never fights another writer.

No write:
- in shadow mode, while writing is paused (the instance's switch), or after a supervised trial ended;
- in the first `GRACE_S` after a start (the inputs settle; no stale or half-restored value goes out);
- when the output is unavailable or HC has no value.

The trial (`trial` mode, `trial_hours`): writing for a limited time; then the instance goes back to shadow by itself
and a notification says so. Permanent writing is the `active` mode, chosen with a confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

GRACE_S = 120.0
FOREIGN_AFTER_S = 5.0  # a change this long after HC's own write is someone else's


@dataclass
class OutputGuard:
    tolerance: float = 0.25  # °C (0 for an on/off output)
    keepalive_s: float = 0.0  # re-send the same value this often (a PLC with a timeout); 0 = off
    last_value: float | None = None
    last_at: datetime | None = None
    conflict: bool = False
    conflict_value: float | None = None
    writes: int = 0

    def decide(self, now: datetime, want: float | None, current: float | None, current_changed: datetime | None,
               uptime_s: float) -> tuple[bool, str]:
        """(write?, status) – status: write | keepalive | in_sync | no_value | unavailable | grace | conflict."""
        if want is None:
            return False, "no_value"
        if current is None:
            return False, "unavailable"
        if uptime_s < GRACE_S:
            return False, "grace"
        tol = self.tolerance
        if self.last_value is not None and self.last_at is not None and not self.conflict:
            foreign = (abs(current - self.last_value) > tol and current_changed is not None
                       and (current_changed - self.last_at).total_seconds() > FOREIGN_AFTER_S)
            if foreign:
                self.conflict, self.conflict_value = True, current
        if self.conflict:
            if abs(current - self.last_value) <= tol or abs(current - want) <= tol:
                self.conflict, self.conflict_value = False, None  # the other writer gave way
            else:
                self.conflict_value = current
                return False, "conflict"
        if abs(current - want) > tol:
            return True, "write"
        if self.keepalive_s > 0 and (self.last_at is None or (now - self.last_at).total_seconds() >= self.keepalive_s):
            return True, "keepalive"
        return False, "in_sync"

    def wrote(self, now: datetime, value: float) -> None:
        self.last_value, self.last_at = value, now
        self.writes += 1

    def state(self) -> dict:
        return {"last_value": self.last_value, "last_at": self.last_at.isoformat() if self.last_at else None,
                "conflict": self.conflict, "conflict_value": self.conflict_value, "writes": self.writes}


MODES = ("shadow", "trial", "active")


def effective(mode: str, trial_start: datetime | None, trial_hours: float, now: datetime) -> tuple[bool, datetime | None]:
    """(writing?, trial end) for a mode; a trial with no start yet is not writing (the coordinator starts it)."""
    if mode == "active":
        return True, None
    if mode == "trial" and trial_start is not None:
        end = trial_start + timedelta(hours=trial_hours)
        return now < end, end
    return False, None

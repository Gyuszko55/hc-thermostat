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

0.56.1 – confirmation wait (`confirm_s`, 60 s by default): a slow device (a cloud device such as Tuya) may report the
written value late, or first echo the old one. Until the value there is HC's own or `confirm_s` passed, HC neither
writes again nor calls a change foreign ("confirming"). A value that never comes back as HC's (no echo, refused,
rounded) is written again – at most `max_retries` times in a row for the same value; then "not_accepted": HC stops
writing that value and says so, until the value HC wants changes. Once the device confirmed, a later change is
someone else's as before (after `FOREIGN_AFTER_S`).

0.57.1 – the device restarted: when the output was unavailable and comes back with another value (a PLC or heat pump
starting with its default), that is not a second writer: HC forgets the old confirmation and conflict and writes its
value again. A device that restarts without ever showing unavailable in Home Assistant cannot be told from another
writer – that stays a conflict.

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
    confirm_s: float = 60.0  # 0.56.1: wait this long for the device to confirm a write
    max_retries: int = 3  # 0.56.1: unconfirmed re-writes of the same value before "not_accepted"
    last_value: float | None = None
    last_at: datetime | None = None
    confirmed: bool = False  # the device reported HC's last written value
    unconfirmed: int = 0  # re-writes of the same value that the device did not confirm
    conflict: bool = False
    conflict_value: float | None = None
    writes: int = 0
    dropped: bool = False  # 0.57.1: the output was unavailable since the last decision with a value

    def decide(self, now: datetime, want: float | None, current: float | None, current_changed: datetime | None,
               uptime_s: float) -> tuple[bool, str]:
        """(write?, status) – status: write | keepalive | in_sync | confirming | not_accepted | no_value | unavailable |
        grace | conflict."""
        if want is None:
            return False, "no_value"
        if current is None:
            self.dropped = True
            return False, "unavailable"
        if uptime_s < GRACE_S:
            return False, "grace"
        tol = self.tolerance
        if self.dropped:
            self.dropped = False
            if self.last_value is not None and abs(current - self.last_value) > tol:
                # back after a restart with its own value: not someone else – write again, from a clean state
                self.conflict, self.conflict_value, self.confirmed, self.unconfirmed = False, None, False, 0
                self.last_at = None
                if abs(current - want) > tol:
                    return True, "write"
        wait = max(FOREIGN_AFTER_S, self.confirm_s)
        retry = False  # writing the same value again, unconfirmed
        if self.last_value is not None and self.last_at is not None and not self.conflict:
            since_change = (current_changed - self.last_at).total_seconds() if current_changed is not None else None
            if abs(current - self.last_value) <= tol:
                if not self.confirmed:
                    self.confirmed, self.unconfirmed = True, 0
            elif self.confirmed:
                # it was HC's value and then moved: someone else (as in 0.56.0)
                if since_change is not None and since_change > FOREIGN_AFTER_S:
                    self.conflict, self.conflict_value = True, current
            elif (now - self.last_at).total_seconds() < wait:
                return False, "confirming"  # the device has not reported HC's value yet
            elif since_change is not None and since_change > wait:
                self.conflict, self.conflict_value = True, current  # changed after the wait, never HC's: foreign
            else:
                retry = abs(want - self.last_value) <= tol  # no echo, refused or rounded: try again (counted)
        if self.conflict:
            if abs(current - self.last_value) <= tol or abs(current - want) <= tol:
                self.conflict, self.conflict_value = False, None  # the other writer gave way
            else:
                self.conflict_value = current
                return False, "conflict"
        if abs(current - want) > tol:
            if retry and self.unconfirmed >= self.max_retries:
                return False, "not_accepted"
            return True, "write"
        if self.keepalive_s > 0 and (self.last_at is None or (now - self.last_at).total_seconds() >= self.keepalive_s):
            return True, "keepalive"
        return False, "in_sync"

    def wrote(self, now: datetime, value: float) -> None:
        again = (self.last_value is not None and not self.confirmed
                 and abs(value - self.last_value) <= self.tolerance)
        self.unconfirmed = self.unconfirmed + 1 if again else 0
        self.last_value, self.last_at, self.confirmed = value, now, False
        self.writes += 1

    def state(self) -> dict:
        return {"last_value": self.last_value, "last_at": self.last_at.isoformat() if self.last_at else None,
                "confirmed": self.confirmed, "dropped": self.dropped, "unconfirmed": self.unconfirmed, "conflict": self.conflict, "conflict_value": self.conflict_value, "writes": self.writes}


MODES = ("shadow", "trial", "active")


def effective(mode: str, trial_start: datetime | None, trial_hours: float, now: datetime) -> tuple[bool, datetime | None]:
    """(writing?, trial end) for a mode; a trial with no start yet is not writing (the coordinator starts it)."""
    if mode == "active":
        return True, None
    if mode == "trial" and trial_start is not None:
        end = trial_start + timedelta(hours=trial_hours)
        return now < end, end
    return False, None

"""0.78.2 (security review M5): the minimum-time gates against a wall clock that jumps back.

A clock set back (NTP correcting a fake-hwclock boot, a restored backup, a hand change) puts a remembered switch time
in the future: the elapsed time goes negative, `since < min_on` holds a running relay ON until the clock has caught up
again – possibly hours. `rebase` puts such a time back to now: a running ON counts as having had its minimum run (it
may stop at once), an OFF starts its minimum pause again (it does not start at once either)."""

from __future__ import annotations

from datetime import datetime, timedelta

FUTURE_TOLERANCE_S = 60.0  # a reading this much "in the future" (the clock went back) has an unknown age
UNKNOWN_AGE_S = 10 * 365 * 86400.0  # ... and counts as very old (stale) – finite, so it stays plain JSON


def rebase(now: datetime, then: datetime | None, on: bool, min_on_s: float) -> datetime | None:
    if then is None or then <= now:
        return then
    return now - timedelta(seconds=max(0.0, float(min_on_s))) if on else now


def age_s(now: datetime, reported: datetime) -> float:
    """Seconds since a report; one from the future beyond the tolerance has an unknown age (stale)."""
    age = (now - reported).total_seconds()
    if age < -FUTURE_TOLERANCE_S:
        return UNKNOWN_AGE_S
    return max(age, 0.0)

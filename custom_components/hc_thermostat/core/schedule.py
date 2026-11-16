"""0.67.0 – the night window of the schedule, with an optional weekend night.

A night belongs to the morning it ends on: the nights ending on Saturday and Sunday morning (Friday and Saturday
evening's) use the weekend times when both are given, every other night the weekday times. Without weekend times
it is the one window for every day, as before. A window whose start equals its end is no night at all.

`windows(now, …)` gives the nights ending yesterday … the day after tomorrow, as (start, end) datetimes in `now`'s
time zone; the rest is read from them: whether `now` is night, the next start or end, the end of the night."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

WEEKEND_MORNINGS = (5, 6)  # Saturday, Sunday


def parse_time(text) -> time | None:
    if text is None or str(text).strip() == "":
        return None
    parts = [int(p) for p in str(text).split(":")]
    return time(parts[0], parts[1] if len(parts) > 1 else 0)


def _times(day: date, start, end, wk_start, wk_end) -> tuple[time, time] | None:
    s, e = parse_time(start), parse_time(end)
    ws, we = parse_time(wk_start), parse_time(wk_end)
    if day.weekday() in WEEKEND_MORNINGS and ws is not None and we is not None:
        s, e = ws, we
    if s is None or e is None or s == e:
        return None
    return s, e


def windows(now: datetime, start, end, wk_start=None, wk_end=None) -> list[tuple[datetime, datetime]]:
    out = []
    for k in range(-1, 3):
        day = now.date() + timedelta(days=k)
        t = _times(day, start, end, wk_start, wk_end)
        if t is None:
            continue
        s, e = t
        at_end = datetime.combine(day, e, tzinfo=now.tzinfo)
        at_start = datetime.combine(day if s < e else day - timedelta(days=1), s, tzinfo=now.tzinfo)
        out.append((at_start, at_end))
    return out


def is_night(now: datetime, start, end, wk_start=None, wk_end=None) -> bool:
    return any(s <= now < e for s, e in windows(now, start, end, wk_start, wk_end))


def next_boundary(now: datetime, start, end, wk_start=None, wk_end=None) -> datetime | None:
    points = [p for w in windows(now, start, end, wk_start, wk_end) for p in w if p > now]
    return min(points) if points else None


def night_end_at(now: datetime, start, end, wk_start=None, wk_end=None) -> datetime | None:
    ends = [e for _, e in windows(now, start, end, wk_start, wk_end) if e > now]
    return min(ends) if ends else None

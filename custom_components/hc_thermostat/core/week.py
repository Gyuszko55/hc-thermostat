"""0.72.0 – a weekly program: for every day of the week the times the level changes at.

A level is one of LEVELS (comfort / home / sleep / eco); its temperature comes from the instance's or the room's
targets, so changing a target moves every slot of that level. Presence (away, vacation), a preset or a manual
target still wins over the program, as over the night window before.

Stored form (options, JSON): {"0": [["06:00", "home"], ["22:00", "sleep"]], …, "6": […]} – day 0 is Monday. A level
holds from its time until the next change; before the day's first change the level of the day before carries on
(a day without changes is all the level of the day before). A program without any change is no program: the night
window is used, as before.

Parsed form: a tuple of 7 tuples of (minute of the day, level), sorted, without repeats of the level before.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta

LEVELS = ("comfort", "home", "sleep", "eco")
STEP_MIN = 15  # the editor's grid; a stored time is rounded to it
DAY_MIN = 24 * 60

Program = tuple  # tuple[tuple[tuple[int, str], ...], ...] – 7 days


def _minute(text) -> int | None:
    try:
        h, m = (int(p) for p in str(text).strip().split(":")[:2])
    except (TypeError, ValueError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return int(round((h * 60 + m) / STEP_MIN) * STEP_MIN) % DAY_MIN


def parse(raw) -> Program | None:
    """The stored program; None when there is none (or nothing usable in it)."""
    if isinstance(raw, (list, tuple)) and len(raw) == 7:
        raw = {str(i): v for i, v in enumerate(raw)}
    if not isinstance(raw, dict):
        return None
    days = []
    for d in range(7):
        points: dict[int, str] = {}
        for item in raw.get(str(d)) or raw.get(d) or ():
            if not isinstance(item, (list, tuple)) or len(item) != 2 or item[1] not in LEVELS:
                continue
            m = _minute(item[0])
            if m is not None:
                points[m] = item[1]
        days.append(sorted(points.items()))
    if not any(days):
        return None
    # drop a change to the level that already holds (it changes nothing)
    level = _last_before(days, 0)
    out = []
    for day in days:
        kept = []
        for m, lv in day:
            if lv != level:
                kept.append((m, lv))
                level = lv
        out.append(tuple(kept))
    if not any(out):  # one level all week
        first = next(day for day in days if day)
        out[0] = ((0, first[0][1]),)
    return tuple(out)


def _last_before(days, day: int) -> str:
    """The level holding at the start of `day`: the last change of the days before (going round the week)."""
    for k in range(1, 8):
        prev = days[(day - k) % 7]
        if prev:
            return prev[-1][1]
    return LEVELS[1]


def to_raw(program: Program | None) -> dict | None:
    if not program:
        return None
    return {str(d): [[f"{m // 60:02d}:{m % 60:02d}", lv] for m, lv in day] for d, day in enumerate(program)}


def level_at(program: Program, now: datetime) -> str:
    day, minute = now.weekday(), now.hour * 60 + now.minute
    level = _last_before(program, day)
    for m, lv in program[day]:
        if m <= minute:
            level = lv
        else:
            break
    return level


def changes(program: Program, now: datetime, days: int = 8):
    """The changes from today on: (datetime in now's time zone, level), in order."""
    start = now.date()
    for k in range(days):
        date = start + timedelta(days=k)
        for m, lv in program[date.weekday()]:
            yield datetime.combine(date, time(m // 60, m % 60), tzinfo=now.tzinfo), lv


def next_change(program: Program, now: datetime) -> datetime | None:
    """When the level changes next (None: never – one level all week)."""
    level = level_at(program, now)
    for at, lv in changes(program, now):
        if at > now and lv != level:
            return at
    return None


def level_end(program: Program, now: datetime) -> datetime | None:
    """When the level holding now ends – the same as next_change, named for the night's end."""
    return next_change(program, now)


def level_after(program: Program, now: datetime) -> str | None:
    at = next_change(program, now)
    return level_at(program, at) if at is not None else None

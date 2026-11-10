"""Target from a source entity: the setpoint turned on a wall thermostat (or set on a number) becomes this instance's
manual target, so several zones can follow one knob. A manual target lasts until the next scheduled change, like a
target set on the HC itself.

What any HC instance wrote to a device itself is remembered for a while (WriteLog), so an instance that controls
the wall thermostat as its external thermostat does not echo its own schedule into the zones that follow it.
"""

from __future__ import annotations

from datetime import datetime

_SAME = 0.01


class WriteLog:
    """Setpoints written by HC instances (shared by every instance of one Home Assistant)."""

    def __init__(self) -> None:
        self._last: dict[str, tuple[float, datetime]] = {}

    def note(self, entity: str, value: float, now: datetime) -> None:
        self._last[entity] = (float(value), now)

    def recent(self, entity: str, value: float, now: datetime, within_s: float = 120.0) -> bool:
        rec = self._last.get(entity)
        return rec is not None and abs(rec[0] - value) < _SAME and (now - rec[1]).total_seconds() <= within_s


class TargetFollower:
    """Turns changes of the source's setpoint into a new manual target (or nothing)."""

    def __init__(self) -> None:
        self._last: float | None = None

    def changed(self, value: float | None, current_target: float | None, own_write: bool) -> float | None:
        if value is None:
            return None
        if self._last is None:  # first look (after a start): only remember it, the schedule stays in charge
            self._last = value
            return None
        if abs(value - self._last) < _SAME:
            return None
        self._last = value
        if own_write:  # an HC instance wrote it (its schedule): not a hand on the knob
            return None
        if current_target is not None and abs(value - current_target) < _SAME:
            return None
        return value


def source_value(domain: str, state: str | None, attributes: dict) -> float | None:
    """The setpoint of a source entity: a climate's target temperature, or a number's value."""
    if state in (None, "unknown", "unavailable"):
        return None
    raw = attributes.get("temperature") if domain == "climate" else state
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None

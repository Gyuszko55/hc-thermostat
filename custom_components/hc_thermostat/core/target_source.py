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
        self._modes: dict[str, tuple[str, datetime]] = {}

    def note_mode(self, entity: str, mode: str, now: datetime) -> None:
        """An hvac mode an HC instance wrote (0.42.0: a managed thermostat switched off by HC is not "by hand")."""
        self._modes[entity] = (str(mode), now)

    def recent_mode(self, entity: str, mode: str, now: datetime, within_s: float = 120.0, consume: bool = False) -> bool:
        """consume: the change this write caused has been seen – a later change to the same mode is someone else's."""
        rec = self._modes.get(entity)
        hit = rec is not None and rec[0] == mode and (now - rec[1]).total_seconds() <= within_s
        if hit and consume:
            del self._modes[entity]
        return hit

    def note(self, entity: str, value: float, now: datetime) -> None:
        self._last[entity] = (float(value), now)

    def stamp(self, entity: str) -> datetime | None:
        """When the last setpoint was written to this entity (a follower that has seen that write's echo once)."""
        rec = self._last.get(entity)
        return rec[1] if rec is not None else None

    def recent(self, entity: str, value: float, now: datetime, within_s: float = 120.0) -> bool:
        rec = self._last.get(entity)
        return rec is not None and abs(rec[0] - value) < _SAME and (now - rec[1]).total_seconds() <= within_s


class TargetFollower:
    """Turns changes of the source's setpoint into a new manual target (or nothing)."""

    def __init__(self) -> None:
        self._last: float | None = None

    @property
    def last(self) -> float | None:
        return self._last

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


class ModeWatch:
    """0.42.0: the managed thermostat's hvac mode. Switched off by someone else (not an HC write) means "leave it
    off" until someone switches it on again; HC's own switching never changes that."""

    _GONE = (None, "unknown", "unavailable")

    def __init__(self, off_by_hand: bool = False) -> None:
        self.off_by_hand = off_by_hand

    def changed(self, old: str | None, new: str | None, own_write: bool) -> bool | None:
        """The new flag when it changed, else None."""
        if old in self._GONE or new in self._GONE or old == new or own_write:
            return None
        if new == "off" and not self.off_by_hand:
            self.off_by_hand = True
            return True
        if old == "off" and new != "off" and self.off_by_hand:
            self.off_by_hand = False
            return False
        return None


def source_value(domain: str, state: str | None, attributes: dict) -> float | None:
    """The setpoint of a source entity: a climate's target temperature, or a number's value."""
    if state in (None, "unknown", "unavailable"):
        return None
    raw = attributes.get("temperature") if domain == "climate" else state
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None

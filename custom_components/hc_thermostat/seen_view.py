"""0.78.1: Home Assistant's states for the core, with the device's own "last seen" time where the device has one.

A Zigbee2MQTT device with `last_seen` turned on has a `sensor.<device>_last_seen` timestamp entity. Its time is when
the device itself last sent a message – unlike `last_reported`, which also moves when Home Assistant restores a state
at its start or when Zigbee2MQTT re-sends its cached states after Home Assistant comes back. A silent device then
reads as old (stale) instead of fresh, and a restored value does not count as a new report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

_RECHECK = timedelta(minutes=10)


@dataclass(frozen=True)
class SeenSample:
    entity_id: str
    state: str
    attributes: Mapping[str, Any]
    last_reported: datetime
    seen: datetime | None


def last_seen_entity(registry: Any, entity_id: str) -> str | None:
    """The `*_last_seen` timestamp entity on the same device as `entity_id` (None when there is none)."""
    entry = registry.async_get(entity_id) if registry is not None else None
    if entry is None or not entry.device_id:
        return None
    for other in er.async_entries_for_device(registry, entry.device_id, include_disabled_entities=False):
        if other.domain == "sensor" and other.entity_id.endswith("_last_seen"):
            return other.entity_id
    return None


def parse_seen(state: Any) -> datetime | None:
    """A timestamp entity's time (None when unknown or not a time)."""
    if state is None or state.state in ("unknown", "unavailable", ""):
        return None
    when = dt_util.parse_datetime(str(state.state))
    if when is None:
        return None
    return when if when.tzinfo is not None else when.replace(tzinfo=dt_util.UTC)


class SeenView:
    """`hass.states` for the core; a source with a "last seen" sibling also carries the device's own time."""

    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self._links: dict[str, tuple[str | None, datetime]] = {}

    def _link(self, entity_id: str) -> str | None:
        now = dt_util.utcnow()
        cached = self._links.get(entity_id)
        if cached is not None and now - cached[1] < _RECHECK:
            return cached[0]
        try:
            link = last_seen_entity(er.async_get(self.hass), entity_id)
        except Exception:  # no registry (tests with a bare hass): plain states
            link = None
        self._links[entity_id] = (link, now)
        return link

    def get(self, entity_id: str) -> Any:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        link = self._link(entity_id)
        if link is None:
            return state
        seen = parse_seen(self.hass.states.get(link))
        if seen is None:
            return state
        return SeenSample(state.entity_id, state.state, state.attributes, state.last_reported, seen)

"""0.78.0: turning raw sensor states into the supervisor's readings – without Home Assistant.

Both bodies of HC use this: the Home Assistant integration (whose `hass.states` already fits `StateView`, since a
Home Assistant `State` has `entity_id`, `state`, `attributes` and `last_reported`) and the standalone service, which
keeps its own table of samples from MQTT, HTTP pushes and polled devices.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import math
from typing import Any, Iterable, Mapping, Protocol

from .clock import age_s
from .model import Reading
from .room_model import group_mean

NO_STATE = ("unknown", "unavailable", "")

_TEMP_UNITS = {"°C": "C", "C": "C", "℃": "C", "°F": "F", "F": "F", "℉": "F", "K": "K"}


# --- one sample ----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Sample:
    """One source's latest state, as Home Assistant keeps it: the raw state text, its attributes, and when the source
    last reported (also when the value did not change)."""

    entity_id: str
    state: str
    last_reported: datetime
    attributes: Mapping[str, Any] = field(default_factory=dict)
    # 0.78.1: when the device itself last sent a message (Zigbee2MQTT's `last_seen`), if known. Better than
    # `last_reported`, which a restart's restore or a bridge's re-sending of cached states also moves.
    seen: datetime | None = None


class SampleLike(Protocol):
    entity_id: str
    state: str
    attributes: Mapping[str, Any]
    last_reported: datetime


class StateView(Protocol):
    """Where the samples come from: `get(source)` gives the latest one, or None when the source is not known."""

    def get(self, entity_id: str) -> SampleLike | None: ...


class SampleTable:
    """A plain `StateView` for the standalone service and for tests: the latest sample per source."""

    def __init__(self, samples: Iterable[Sample] = ()) -> None:
        self._samples: dict[str, Sample] = {s.entity_id: s for s in samples}

    def get(self, entity_id: str) -> Sample | None:
        return self._samples.get(entity_id)

    def put(self, entity_id: str, state: Any, at: datetime, attributes: Mapping[str, Any] | None = None,
            seen: datetime | None = None) -> Sample:
        """A source reported: the value (even an unchanged one), the time, and the device's own time if known."""
        sample = Sample(entity_id, str(state), at, dict(attributes or {}), seen)
        self._samples[entity_id] = sample
        return sample


# --- numbers and temperatures --------------------------------------------------------------------------------------
def finite(value: Any) -> float | None:
    """A state as a number – None when it is no number, or "nan" / "inf"."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def to_c(value: Any, unit: Any) -> float | None:
    """A number in `unit` as °C; a value without a temperature unit is returned as a float, unchanged."""
    v = finite(value)
    if v is None:
        return None
    u = _TEMP_UNITS.get(str(unit).strip()) if unit is not None else None
    if u == "F":
        return (v - 32.0) / 1.8
    if u == "K":
        return v - 273.15
    return v


def value_c(sample: SampleLike | None) -> float | None:
    """A sensor's (or input_number's) numeric state, a weather entity's temperature – in °C when it is a temperature."""
    if sample is None:
        return None
    attrs = getattr(sample, "attributes", None) or {}
    if str(getattr(sample, "entity_id", "")).startswith("weather."):
        return to_c(attrs.get("temperature"), attrs.get("temperature_unit"))
    return to_c(sample.state, attrs.get("unit_of_measurement"))


def reported_at(sample: SampleLike) -> datetime:
    """0.78.1: when the source really reported – the device's own `seen` time if known, else `last_reported`."""
    seen = getattr(sample, "seen", None)
    return seen if seen is not None else sample.last_reported


def reading(view: StateView, entity_id: str | None, now: datetime) -> Reading:
    """A source as a `Reading`: its value in °C and the seconds since it last reported."""
    sample = view.get(entity_id) if entity_id else None
    value = value_c(sample)
    if value is None:
        return Reading()
    return Reading(value, age_s(now, reported_at(sample)))  # 0.78.2 (M5): a report from the future is no fresh one


def switch_on(view: StateView, entity_id: str | None) -> bool | None:
    """An on/off source: True / False, None when it is unknown, unavailable or not there."""
    sample = view.get(entity_id) if entity_id else None
    if sample is None or sample.state not in ("on", "off"):
        return None
    return sample.state == "on"


def any_on(view: StateView, entity_ids: Iterable[str] | None) -> bool:
    """Any of the contacts is on (a missing or unreadable one counts as off)."""
    return any((s := view.get(e)) is not None and s.state == "on" for e in entity_ids or ())


def group_reading(view: StateView, entity_ids: Iterable[str], now: datetime, max_age_s: float) -> Reading | None:
    """0.43.0: the mean of the group's fresh thermometers, aged as the freshest of them; None when none is fresh."""
    fresh = [(r.value, r.age_s) for e in entity_ids if (r := reading(view, e, now)).fresh(max_age_s) is not None]
    if not fresh:
        return None
    return Reading(group_mean([v for v, _ in fresh]), min(a for _, a in fresh))


# --- after a restart -----------------------------------------------------------------------------------------------
class RestartConfirm:
    """0.77.3: after a restart a sleeping thermometer's value is often the one restored from before the restart,
    stamped with the start time – it looks fresh but is old. The room reading counts as confirmed once one of its
    thermometers really reported after the start, or once the wait is over.

    0.78.1: "really reported" – with the device's own `seen` time, a message after the start; without it, a report
    after the value first seen *and* at least `settle_s` after the start. The first minutes bring only writes that
    look like reports: the restore itself (written twice by some integrations, ms apart) and a bridge re-sending its
    cached states when Home Assistant comes back (Zigbee2MQTT ~1.5 minutes after the start)."""

    def __init__(self, started: datetime, wait_s: float, settle_s: float = 0.0) -> None:
        self.started, self.wait_s, self.settle_s = started, wait_s, settle_s
        self.first_seen: dict[str, datetime] = {}
        self.confirmed = False

    def check(self, view: StateView, entity_ids: Iterable[str | None], now: datetime) -> bool:
        if self.confirmed:
            return True
        if (now - self.started).total_seconds() >= self.wait_s:
            self.confirmed = True
            return True
        for entity_id in filter(None, entity_ids):
            sample = view.get(entity_id)
            if sample is None or value_c(sample) is None:
                continue
            seen = getattr(sample, "seen", None)
            if seen is not None:
                if seen > self.started:
                    self.confirmed = True
                    return True
                continue
            first = self.first_seen.setdefault(entity_id, sample.last_reported)
            if sample.last_reported > first and (sample.last_reported - self.started).total_seconds() >= self.settle_s:
                self.confirmed = True
                return True
        return False


# --- the outdoor day average ---------------------------------------------------------------------------------------
class OutdoorAverage:
    """The last 24 hours' outdoor mean from one fresh value every 10 minutes (at least 6 values, else None)."""

    EVERY = timedelta(minutes=10)

    def __init__(self, saved: Iterable[Iterable] = ()) -> None:
        self.samples: deque[tuple[str, float]] = deque(maxlen=144)
        self.samples.extend(tuple(x) for x in saved)

    def update(self, fresh: float | None, now: datetime) -> float | None:
        last = datetime.fromisoformat(self.samples[-1][0]) if self.samples else None
        if fresh is not None and (last is None or now - last >= self.EVERY):
            self.samples.append((now.isoformat(), fresh))
        limit = now - timedelta(hours=24)
        values = [v for t, v in self.samples if datetime.fromisoformat(t) >= limit]
        return sum(values) / len(values) if len(values) >= 6 else None

    def state(self) -> list:
        return list(self.samples)

"""0.77.0: one life-safety latch for every HC instance that watches safety inputs (core/safety.py). Kept in hass.data,
saved at once when it trips or clears, announced by an event, a persistent notification and a Repairs entry."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .core.safety import SafetyLatch

_LOGGER = logging.getLogger(__name__)
EVENT_STOP = f"{DOMAIN}_safety_stop"
EVENT_CLEAR = f"{DOMAIN}_safety_clear"
ISSUE_ID = "safety_stop"
LOST_ISSUE_ID = "safety_input_lost"  # 0.78.2
NOTE_ID = f"{DOMAIN}_safety_stop"


class SafetyHub:
    def __init__(self, hass) -> None:
        self.hass = hass
        self.latch = SafetyLatch()
        self.watched: dict[str, list[str]] = {}  # entry_id → its inputs
        self._store = Store(hass, 1, f"{DOMAIN}.safety")
        self._loaded = False
        self._announced = False
        self._lost_shown: tuple[str, ...] = ()

    async def async_load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self.latch.restore(await self._store.async_load() or {})
        self._announced = self.latch.tripped  # a stop from before the restart was announced then

    def watch(self, entry_id: str, entities: list[str]) -> None:
        if entities:
            self.watched[entry_id] = list(entities)
        else:
            self.watched.pop(entry_id, None)

    def inputs(self) -> list[str]:
        return sorted({e for es in self.watched.values() for e in es})

    def check(self, now: datetime) -> bool:
        states = {}
        for eid in self.inputs():
            st = self.hass.states.get(eid)
            states[eid] = None if st is None else st.state
        was = self.latch.tripped
        held = self.latch.check(now, states)
        if held and not was:
            self.hass.async_create_task(self._store.async_save(self.latch.state()))
        if held and not self._announced:
            self._announced = True
            self._announce_stop()
        self._sync_lost(now)
        return held

    def _sync_lost(self, now: datetime) -> None:
        """0.78.2 (security review): a safety input without a reading does not trip the stop (the wired chain is the
        real stop) – but after UNKNOWN_REPORT_S it is a Repairs entry, so nobody believes it is watched."""
        lost = tuple(self.latch.lost(now))
        if lost == self._lost_shown:
            return
        self._lost_shown = lost
        try:
            if not lost:
                ir.async_delete_issue(self.hass, DOMAIN, LOST_ISSUE_ID)
                return
            ir.async_create_issue(self.hass, DOMAIN, LOST_ISSUE_ID, is_fixable=False, is_persistent=False,
                                  severity=ir.IssueSeverity.ERROR, translation_key="safety_input_lost",
                                  translation_placeholders={"inputs": self._names(list(lost))})
        except Exception:
            _LOGGER.debug("The lost safety input's Repairs entry could not be updated", exc_info=True)

    def acknowledge(self, who: str | None = None) -> bool:
        now = dt_util.now()
        self.check(now)  # a fresh reading before letting go
        if not self.latch.tripped:
            return True
        if not self.latch.acknowledge(now, who):
            return False
        self._announced = False
        self.hass.async_create_task(self._store.async_save(self.latch.state()))
        self.hass.bus.async_fire(EVENT_CLEAR, {"by": who, "at": now.isoformat()})
        try:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_ID)
            from homeassistant.components import persistent_notification
            persistent_notification.async_dismiss(self.hass, NOTE_ID)
        except Exception:
            _LOGGER.debug("The safety notices could not be cleared", exc_info=True)
        return True

    def _names(self, entities: list[str]) -> str:
        out = []
        for eid in entities:
            st = self.hass.states.get(eid)
            out.append((st.attributes.get("friendly_name") if st is not None else None) or eid)
        return ", ".join(out)

    def _announce_stop(self) -> None:
        info = self.latch.info()
        self.hass.bus.async_fire(EVENT_STOP, {"by": info["by"], "since": info["since"]})
        hu = str(getattr(self.hass.config, "language", "") or "").startswith("hu")
        names = self._names(info["by"])
        _LOGGER.warning("Life-safety stop: %s", names)
        try:
            ir.async_create_issue(self.hass, DOMAIN, ISSUE_ID, is_fixable=False, is_persistent=True,
                                  severity=ir.IssueSeverity.CRITICAL, translation_key="safety_stop",
                                  translation_placeholders={"by": names})
            from homeassistant.components import persistent_notification
            persistent_notification.async_create(
                self.hass,
                (f"Életvédelmi leállítás: {names}. Minden HC-példány kikapcsolta a hőtermelőjét (a valódi leállítás a "
                 "bekötött biztonsági láncé). Újraindítás csak kézi nyugtázással "
                 "(Életvédelmi leállítás nyugtázása gomb), ha minden érzékelő újra nyugalmi állapotban van.") if hu else
                (f"Life-safety stop: {names}. Every HC instance switched its heat output off (the wired safety chain "
                 "does the real stop). It restarts only when acknowledged "
                 "(Acknowledge the life-safety stop button) with every detector clear again."),
                title="HC – ÉLETVÉDELMI LEÁLLÍTÁS" if hu else "HC – LIFE-SAFETY STOP", notification_id=NOTE_ID)
        except Exception:
            _LOGGER.debug("The safety notices could not be created", exc_info=True)


def stop_hub(hass, own: SafetyHub | None = None) -> SafetyHub | None:
    """0.78.2 (security review M3): the latch an instance has to honour – its own (it watches safety inputs), else the
    shared one whenever any HC instance watches inputs or the latch holds. A central boiler, a buffer, a circuit or a
    room without inputs of its own stops with the house all the same."""
    if own is not None:
        return own
    hub = hass.data.get(f"{DOMAIN}_safety") if hass is not None and hasattr(hass, "data") else None
    if hub is None or not (hub.watched or hub.latch.tripped):
        return None
    return hub


def stop_held(hass, now: datetime, own: SafetyHub | None = None) -> tuple[bool, list[str]]:
    """0.78.2: (the stop holds?, the inputs that tripped it); a check that fails counts as what the latch last knew –
    unknown as tripped."""
    hub = stop_hub(hass, own)
    if hub is None:
        return False, []
    try:
        held = bool(hub.check(now))
    except Exception:
        held = bool(getattr(hub.latch, "tripped", True))
    return held, list(getattr(hub.latch, "by", []) or [])


def hub_of(hass) -> SafetyHub:
    hub = hass.data.get(f"{DOMAIN}_safety")
    if hub is None:
        hub = hass.data[f"{DOMAIN}_safety"] = SafetyHub(hass)
    return hub

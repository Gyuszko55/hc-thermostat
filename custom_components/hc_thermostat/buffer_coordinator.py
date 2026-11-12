"""Buffer tank instance (0.33.0): charges the tank by its temperatures, optionally led by the zones' demand.

The zones are ordinary HC instances that switch their circuit pumps / valves from the tank; this instance only reads
whether any of them asks for heat (hvac_action "heating") and switches the heat source of the tank.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import CONF_BOILER, CONF_BUFFER_BOTTOM, CONF_BUFFER_TOP, CONF_MODE, CONF_ZONES, DOMAIN, MODE_ACTIVE, MODE_SHADOW
from .core.buffer import BufferCharger, BufferConfig, BufferDecision, fresh

from .units import state_value_c

_LOGGER = logging.getLogger(__name__)
_INTERVAL = timedelta(seconds=30)


def _temp(hass, entity_id: str | None, now: datetime, max_age_s: float) -> float | None:
    """A tank temperature; None when missing, not a number, or older than max_age_s (a dead sensor keeps its value)."""
    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
        return None  # no sensor (the bottom one is optional) or not loaded yet
    value = state_value_c(state)  # 0.45.0: a tank thermometer in °F is read in °C
    if value is None:
        return None
    reported = getattr(state, "last_reported", None) or state.last_updated
    return fresh(value, (now - reported).total_seconds(), max_age_s)


def asking_zones(hass, zone_ids: list[str]) -> tuple:
    out = []
    for entity_id in zone_ids:
        state = hass.states.get(entity_id)
        if state is not None and state.state != "off" and state.attributes.get("hvac_action") == "heating":
            out.append(entity_id)
    return tuple(out)


class BufferCoordinator(DataUpdateCoordinator[BufferDecision]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_buffer", update_interval=_INTERVAL)
        data = {**entry.data, **entry.options}
        self.conf = data
        self.mode = data.get(CONF_MODE, MODE_SHADOW)
        known = BufferConfig.__dataclass_fields__
        self.buffer = BufferCharger(BufferConfig(**{k: v for k, v in data.items() if k in known and v is not None}))
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    @property
    def is_shadow(self) -> bool:
        return self.mode == MODE_SHADOW

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        self.buffer.restore(data.get("buffer") or {})

    async def async_save(self) -> None:
        await self._store.async_save({"buffer": self.buffer.state()})

    async def _async_update_data(self) -> BufferDecision:
        now: datetime = dt_util.now()
        zones = list(self.conf.get(CONF_ZONES) or [])
        was = self.buffer.output
        max_age = self.buffer.cfg.buffer_sensor_max_age_s
        decision = self.buffer.step(now, _temp(self.hass, self.conf.get(CONF_BUFFER_TOP), now, max_age),
                                    _temp(self.hass, self.conf.get(CONF_BUFFER_BOTTOM), now, max_age),
                                    asking_zones(self.hass, zones), zones_given=bool(zones))
        if decision.output != was:
            await self.async_save()
        if self.mode == MODE_ACTIVE:
            await self._switch(decision.output)
        return decision

    async def _switch(self, on: bool) -> None:
        source = self.conf.get(CONF_BOILER)
        state = self.hass.states.get(source) if source else None
        if state is None or state.state not in ("on", "off"):
            return
        want = "on" if on else "off"
        if state.state != want:
            try:
                await self.hass.services.async_call("homeassistant", f"turn_{want}", {"entity_id": source}, blocking=True)
            except Exception:  # A failed call must not stop the next decision.
                _LOGGER.exception("Could not switch the buffer's heat source")

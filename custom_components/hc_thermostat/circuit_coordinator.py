"""Mixing circuit instance (0.54.0, shadow only): the flow target of a radiator or floor circuit fed from a buffer tank.

It reads its zones (ordinary HC zone instances – they keep switching their own valves) and the outdoor thermometer
every 30 seconds, works out the raw flow target, and gives out a target that changes only now and then
(core/circuit.py, core/setpoint_hold.py). With a buffer instance linked it also shows what the tank can still give
this circuit. It writes nothing: the PLC / mixer keeps its own control; writing the target comes later, after a
supervised trial.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import CONF_CIRCUIT_BUFFER, CONF_MODE, CONF_OUTDOOR, CONF_ZONES, DOMAIN, MODE_SHADOW
from .core.circuit import CircuitConfig, CircuitDecision, MixingCircuit, ZoneReading
from .units import state_value_c

_LOGGER = logging.getLogger(__name__)
_INTERVAL = timedelta(seconds=30)
_SAVE_EVERY = timedelta(minutes=10)
OUTDOOR_MAX_AGE_S = 3 * 3600.0  # an outdoor reading older than this is lost (a dead sensor keeps its value)


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_circuit_zones(hass, zone_ids: list[str]) -> list[ZoneReading]:
    out = []
    for entity_id in zone_ids:
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            out.append(ZoneReading(entity_id, False, fault=True))
            continue
        a = state.attributes
        out.append(ZoneReading(entity_id, state.state != "off" and a.get("hvac_action") == "heating",
                               _num(a.get("temperature")), _num(a.get("current_temperature")), bool(a.get("fault"))))
    return out


def read_outdoor(hass, entity_id: str | None, now: datetime) -> float | None:
    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
        return None
    value = state_value_c(state)
    if value is None or not -50 <= value <= 60:
        return None
    reported = getattr(state, "last_reported", None) or state.last_updated
    if reported is not None and (now - reported).total_seconds() > OUTDOOR_MAX_AGE_S:
        return None
    return value


class CircuitCoordinator(DataUpdateCoordinator[CircuitDecision]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_circuit", update_interval=_INTERVAL)
        data = {**entry.data, **entry.options}
        self.conf = data
        self.mode = MODE_SHADOW  # 0.54.0: shadow only, whatever the entry says
        self.circuit = MixingCircuit(CircuitConfig.from_conf(data))
        self.zones: list[ZoneReading] = []
        self.usable: dict = {}
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._last_save = dt_util.now()

    @property
    def is_shadow(self) -> bool:
        return True

    async def async_load(self) -> None:
        self.circuit.restore(await self._store.async_load() or {}, dt_util.now())

    async def async_save(self) -> None:
        now = dt_util.now()
        self._last_save = now
        await self._store.async_save(self.circuit.state(now))

    def buffer_coordinator(self):
        """The linked buffer instance's coordinator, when it is loaded."""
        entry_id = self.conf.get(CONF_CIRCUIT_BUFFER)
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        c = getattr(entry, "runtime_data", None) if entry is not None else None
        return c if getattr(c, "stock", None) is not None else None

    async def _async_update_data(self) -> CircuitDecision:
        now = dt_util.now()
        self.zones = read_circuit_zones(self.hass, list(self.conf.get(CONF_ZONES) or []))
        decision = self.circuit.step(now, self.zones, read_outdoor(self.hass, self.conf.get(CONF_OUTDOOR), now))
        buf = self.buffer_coordinator()
        cfg = self.circuit.cfg
        self.usable = buf.stock.usable(decision.target, cfg.circuit_dt, cfg.circuit_margin) if buf is not None else {}
        if decision.details.get("changed") or now - self._last_save >= _SAVE_EVERY:
            await self.async_save()
        return decision

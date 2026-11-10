"""Central boiler instance: gathers the zone HC thermostats and switches the boiler (stage 3).

Each zone is an ordinary HC instance that only drives its own valve (a relay for a manifold actuator or a
zone valve) or its TRV (external thermostat). This instance reads their climate entities every 30 seconds:
a zone asks for heat when its hvac_action is "heating"; a TRV zone's valve counts as open at once, a relay
zone's after the configured opening time of a thermoelectric actuator – unless the zone names a valve
feedback entity (end switch or position): then that entity says whether the valve is open.

Modulating boiler (0.27.0): with a flow setpoint entity (number / input_number) the highest flow request of
the zones is written there while the boiler runs; when it stops, the entity's lowest value (the boiler relay
or OpenTherm heating-enable switch does the actual stop).
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import CONF_BOILER, CONF_FLOW, CONF_MODE, CONF_PUMP, CONF_ZONES, DOMAIN, MODE_ACTIVE, MODE_SHADOW
from .core.central import CentralBoiler, CentralConfig, CentralDecision, ZoneState, feedback_open
from .executor import KeepAlive

_LOGGER = logging.getLogger(__name__)
_INTERVAL = timedelta(seconds=30)


def read_zones(hass, zone_ids: list[str], valve_on: dict[str, datetime], now: datetime,
               valve_off: dict[str, datetime] | None = None) -> list[ZoneState]:
    """Zone states from the zone thermostats; remembers when each zone's valve was switched on and off."""
    valve_off = {} if valve_off is None else valve_off
    zones = []
    for entity_id in zone_ids:
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unavailable", "unknown"):
            valve_on.pop(entity_id, None)
            valve_off.pop(entity_id, None)
            zones.append(ZoneState(entity_id, False, fault=True))
            continue
        attrs = state.attributes
        wants = state.state != "off" and attrs.get("hvac_action") == "heating"
        if wants:
            valve_on.setdefault(entity_id, now)  # a valve that was still closing stays open for the pump
        elif valve_on.pop(entity_id, None) is not None:
            valve_off[entity_id] = now  # the valve starts closing now
        trv = attrs.get("control_type") == "external"
        feedback = None
        if fb_id := attrs.get("valve_feedback"):
            fb = hass.states.get(fb_id)
            feedback = feedback_open(fb.state, fb.attributes) if fb is not None else None
        demand = attrs.get("demand")
        request = attrs.get("flow_request")
        zones.append(ZoneState(
            name=entity_id,
            wants_heat=wants,
            demand=float(demand) / 100 if isinstance(demand, (int, float)) else (1.0 if wants else 0.0),
            valve_on_since=valve_on.get(entity_id),
            valve_open=feedback if feedback is not None else ((True if wants else None) if trv else None),
            fault=bool(attrs.get("fault")),
            valve_off_since=valve_off.get(entity_id),
            trv=trv,
            flow_request=float(request) if isinstance(request, (int, float)) else None,
        ))
    return zones


class CentralCoordinator(DataUpdateCoordinator[CentralDecision]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_central", update_interval=_INTERVAL)
        data = {**entry.data, **entry.options}
        self.conf = data
        self.mode = data.get(CONF_MODE, MODE_SHADOW)
        known = CentralConfig.__dataclass_fields__
        self.central = CentralBoiler(CentralConfig(**{k: v for k, v in data.items() if k in known and v is not None}))
        self._valve_on: dict[str, datetime] = {}
        self._valve_off: dict[str, datetime] = {}
        self.keep_alive = KeepAlive(self.central.cfg.central_keep_alive_s)
        self.zones: list[ZoneState] = []
        self._last_flow: float | None = None

    @property
    def is_shadow(self) -> bool:
        return self.mode == MODE_SHADOW

    async def _async_update_data(self) -> CentralDecision:
        now = dt_util.now()
        self.zones = read_zones(self.hass, list(self.conf.get(CONF_ZONES) or []), self._valve_on, now, self._valve_off)
        decision = self.central.step(now, self.zones)
        if self.mode == MODE_ACTIVE:
            await self._switch(decision.output, now)
            await self._switch_pump(decision.pump)
            await self._write_flow(decision.flow_setpoint)
        return decision

    async def _write_flow(self, value: float | None) -> None:
        """Modulating boiler: the flow setpoint (off: the entity's lowest value); tenths are not chased."""
        flow = self.conf.get(CONF_FLOW)
        state = self.hass.states.get(flow) if flow else None
        if state is None or state.state in ("unavailable", "unknown"):
            return
        if value is None:
            value = float(state.attributes.get("min", 0) or 0)
        if self._last_flow is not None and abs(value - self._last_flow) < 0.5:
            return
        try:
            await self.hass.services.async_call(flow.split(".", 1)[0], "set_value", {"entity_id": flow, "value": value}, blocking=True)
            self._last_flow = value
        except Exception:  # A failed call must not stop the next decision.
            _LOGGER.exception("Could not write the flow setpoint")

    async def _switch_pump(self, on: bool) -> None:
        pump = self.conf.get(CONF_PUMP)
        state = self.hass.states.get(pump) if pump else None
        if state is None or state.state not in ("on", "off"):
            return
        want = "on" if on else "off"
        if state.state != want:
            try:
                await self.hass.services.async_call("homeassistant", f"turn_{want}", {"entity_id": pump}, blocking=True)
            except Exception:  # A failed call must not stop the next decision.
                _LOGGER.exception("Could not switch the pump")

    async def _switch(self, on: bool, now: datetime) -> None:
        boiler = self.conf.get(CONF_BOILER)
        state = self.hass.states.get(boiler) if boiler else None
        if state is None or state.state not in ("on", "off"):
            return
        want = "on" if on else "off"
        if state.state != want or (on and self.keep_alive.due(now)):
            try:
                await self.hass.services.async_call("homeassistant", f"turn_{want}", {"entity_id": boiler}, blocking=True)
                if on:
                    self.keep_alive.sent(now)
            except Exception:  # A failed call must not stop the next decision.
                _LOGGER.exception("Could not switch the boiler")

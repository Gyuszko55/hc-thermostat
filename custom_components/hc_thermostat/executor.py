"""The only place that may touch real devices. In shadow mode it never does."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.util import dt as dt_util

from .const import DOMAIN, MODE_ACTIVE
from .core.fancoil import fan_at_level, fan_level
from .core.model import Decision
from .core.target_source import WriteLog

_LOGGER = logging.getLogger(__name__)
_SLACK_S = 2.0


def write_log(hass: Any) -> WriteLog:
    """Setpoints written by any HC instance – a target-source follower ignores these (no echo)."""
    return hass.data.setdefault(f"{DOMAIN}_writes", WriteLog())


class KeepAlive:
    """Some relays switch themselves off after a while (a Shelly auto-off as a safety net if Home Assistant
    stops): while the decision is "on", "on" is sent again every `every_s` seconds to restart that timer."""

    def __init__(self, every_s: float) -> None:
        self.every_s = float(every_s or 0)
        self._last: datetime | None = None

    def sent(self, now: datetime) -> None:
        self._last = now

    def due(self, now: datetime) -> bool:
        if self.every_s <= 0:
            return False
        # A little slack: the 30 s update steps drift by milliseconds, and a step just short of the interval
        # would otherwise push the resend a whole step later.
        return self._last is None or (now - self._last).total_seconds() >= self.every_s - _SLACK_S


class Executor:
    def __init__(self, hass: Any, mode: str, actuator: str | None, external: str | None,
                 flow: str | None = None, enable: str | None = None, keep_alive_s: float = 0.0,
                 exact_mode: bool = False, cool_mode: str | None = None, cool_flow: str | None = None,
                 discharge: str | None = None, fan: str | None = None, keep_script: str | None = None) -> None:
        self._hass = hass
        self.mode = mode
        self._actuator = actuator
        self._external = external
        self._flow = flow
        self._enable = enable
        self._last_flow: float | None = None
        self.keep_alive = KeepAlive(keep_alive_s)
        self._exact = exact_mode
        self._cool_mode = cool_mode  # floor cooling: the heat pump's cooling switch
        self._cool_flow = cool_flow  # floor cooling: its own flow setpoint (else the heating flow entity)
        self._discharge = discharge  # storage heater: discharge fan / damper
        self._keep_script = keep_script  # 0.41.0: re-arms a device-side off timer while the relay should stay on
        self._fan = fan  # fan coil: its fan, by percentage  # air conditioner: heat and cool are both real modes, set exactly

    async def apply(self, decision: Decision) -> None:
        if self.mode != MODE_ACTIVE:
            return
        try:
            await self._apply_cool_mode(decision)
            await self._apply_discharge(decision)
            await self._apply_fan(decision)
            if decision.external is not None:
                await self._apply_external(decision)
            elif self._flow:
                await self._apply_flow(decision)
            else:
                await self._apply_relay(decision)
        except Exception:  # A failed call must not stop the next decision.
            _LOGGER.exception("Could not apply the decision")

    async def _apply_relay(self, decision: Decision) -> None:
        if not self._actuator:
            return
        state = self._hass.states.get(self._actuator)
        if state is None or state.state not in ("on", "off"):
            return
        want = "on" if decision.output else "off"
        if state.state != want or (want == "on" and self.keep_alive.due(decision.now)):
            if state.state != want or not self._keep_script:
                await self._hass.services.async_call(
                    "homeassistant", f"turn_{want}", {"entity_id": self._actuator}, blocking=True
                )
            if want == "on":
                if self._keep_script:
                    # 0.41.0: e.g. a Shelly "turn on with a 15-minute timer" – re-armed at every keep-alive, so a
                    # long burn is never cut, while a dead Home Assistant leaves the relay on for 15 minutes at most.
                    await self._hass.services.async_call("script", "turn_on", {"entity_id": self._keep_script},
                                                         blocking=False)
                self.keep_alive.sent(decision.now)

    async def _apply_external(self, decision: Decision) -> None:
        if not self._external:
            return
        state = self._hass.states.get(self._external)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        command = decision.external
        if state.state != command.hvac and (self._exact or not (command.hvac == "heat" and state.state != "off")):
            await self._hass.services.async_call(
                "climate", "set_hvac_mode", {"entity_id": self._external, "hvac_mode": command.hvac}, blocking=True
            )
        if command.hvac in ("heat", "cool") and command.target is not None and state.attributes.get("temperature") != command.target:
            write_log(self._hass).note(self._external, command.target, dt_util.utcnow())
            await self._hass.services.async_call(
                "climate", "set_temperature", {"entity_id": self._external, "temperature": command.target}, blocking=True
            )

    async def _apply_fan(self, decision: Decision) -> None:
        """Fan coil: the fan speed follows the decision (0 % = off)."""
        details = decision.details or {}
        if not self._fan or "fan_pct" not in details:
            return
        state = self._hass.states.get(self._fan)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        pct = int(details["fan_pct"])
        if pct <= 0:
            if state.state != "off":
                await self._hass.services.async_call("fan", "turn_off", {"entity_id": self._fan}, blocking=True)
            return
        step = state.attributes.get("percentage_step")
        level, pct = fan_level(pct, step if isinstance(step, (int, float)) else None)
        if state.state != "on" or not fan_at_level(state.attributes.get("percentage"), level, step if isinstance(step, (int, float)) else None):
            await self._hass.services.async_call("fan", "set_percentage", {"entity_id": self._fan, "percentage": pct}, blocking=True)

    async def _apply_discharge(self, decision: Decision) -> None:
        """Storage heater: the discharge fan / damper follows the decision."""
        details = decision.details or {}
        if not self._discharge or "discharge" not in details:
            return
        state = self._hass.states.get(self._discharge)
        want = "on" if details["discharge"] else "off"
        if state is not None and state.state in ("on", "off") and state.state != want:
            await self._hass.services.async_call("homeassistant", f"turn_{want}", {"entity_id": self._discharge}, blocking=True)

    async def _apply_cool_mode(self, decision: Decision) -> None:
        """Floor cooling: the heat pump's cooling switch is on all summer while the instance cools (or may)."""
        if not self._cool_mode:
            return
        state = self._hass.states.get(self._cool_mode)
        want = "on" if (decision.details or {}).get("mode") == "cool" else "off"
        if state is not None and state.state in ("on", "off") and state.state != want:
            await self._hass.services.async_call("homeassistant", f"turn_{want}", {"entity_id": self._cool_mode}, blocking=True)

    async def _apply_flow(self, decision: Decision) -> None:
        """Heating curve (EXPERIMENTAL): write the flow setpoint; off = the enable switch off, or the lowest value."""
        if self._enable:
            state = self._hass.states.get(self._enable)
            want = "on" if decision.output else "off"
            if state is not None and state.state in ("on", "off") and state.state != want:
                await self._hass.services.async_call("homeassistant", f"turn_{want}", {"entity_id": self._enable}, blocking=True)
        cooling = (decision.details or {}).get("mode") == "cool"
        entity = self._cool_flow if cooling and self._cool_flow else self._flow
        state = self._hass.states.get(entity)
        if state is None or state.state in ("unavailable", "unknown"):
            return
        value = decision.flow_setpoint if decision.output and decision.flow_setpoint is not None else None
        if value is None:
            if self._enable:
                return  # switched off by the enable switch; leave the setpoint alone
            if cooling:  # no cold water: the highest setpoint means no cooling (the lowest would be the coldest)
                value = float(state.attributes.get("max", 30) or 30)
            else:
                value = float(state.attributes.get("min", 0) or 0)  # no enable switch: the lowest setpoint means off
        if self._last_flow is not None and abs(value - self._last_flow) < 0.5 and decision.output:
            return  # do not chase tenths
        domain = entity.split(".", 1)[0]
        await self._hass.services.async_call(domain, "set_value", {"entity_id": entity, "value": value}, blocking=True)
        self._last_flow = value

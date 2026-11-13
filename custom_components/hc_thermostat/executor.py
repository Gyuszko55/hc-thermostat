"""The only place that may touch real devices. In shadow mode it never does."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.util import dt as dt_util

from .const import DOMAIN, MODE_ACTIVE
from .core.adapters import GenericAdapter, adapter_for
from .core.fancoil import fan_at_level, fan_level
from .core.model import Decision
from .core.target_source import WriteLog
from .units import CELSIUS, from_c, system_unit, to_c

_LOGGER = logging.getLogger(__name__)
_SLACK_S = 2.0


def write_log(hass: Any) -> WriteLog:
    """Setpoints written by any HC instance – a target-source follower ignores these (no echo)."""
    return hass.data.setdefault(f"{DOMAIN}_writes", WriteLog())


def _same(current: Any, target: float) -> bool:
    try:
        return abs(float(current) - float(target)) < 0.01
    except (TypeError, ValueError):
        return False


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
        self.adapter: GenericAdapter = adapter_for(None)  # 0.42.0: the managed thermostat's integration (coordinator)
        self.paused = False  # 0.42.0: "HC supervision paused" – nothing is written to the managed thermostat
        self.failed: set[str] = set()  # 0.47.0: the parts whose last call failed (relay, flow, fan, ...)

    async def apply(self, decision: Decision) -> None:
        if self.mode != MODE_ACTIVE or self.paused:
            return
        # 0.47.0: every part on its own – a failing cooling switch, discharge fan or fan coil fan no longer takes the
        # relay / flow / managed thermostat write of the same step with it; what failed is kept for the fault sensor
        parts = [("cool_mode", self._apply_cool_mode), ("discharge", self._apply_discharge), ("fan", self._apply_fan)]
        if decision.external is not None:
            parts.append(("external", self._apply_external))
        elif self._flow:
            parts.append(("flow", self._apply_flow))
        else:
            parts.append(("relay", self._apply_relay))
        failed: set[str] = set()
        for name, part in parts:
            try:
                await part(decision)
            except Exception:  # A failed call must not stop the next decision, nor the other parts.
                failed.add(name)
                if name not in self.failed:  # once per failure streak, not every 30 s
                    _LOGGER.exception("Could not apply the decision (%s)", name)
        self.failed = failed

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
        attrs = state.attributes
        hvac, target = command.hvac, command.target
        # 0.45.0: a climate takes its temperatures in Home Assistant's unit system – a °C target goes in as °F there
        unit = system_unit(self._hass)
        if target is not None and unit != CELSIUS:
            target = from_c(target, unit)
        if not self._exact:
            # 0.42.0: external control – the mode that means heat for this entity, the target fitted to its own step
            # and range (a 1 °C-step unit refuses 22.5). The AC control already steps and clamps its setpoint.
            if hvac == "heat":
                hvac = self.adapter.heat_mode(attrs)
            if target is not None:
                target = self.adapter.fit_target(target, attrs)
        elif target is not None and unit != CELSIUS:
            # the AC control stepped it in °C by the unit's own step: back on that step in °F (no float noise)
            step = attrs.get("target_temp_step")
            step = float(step) if isinstance(step, (int, float)) and step > 0 else 1.0
            target = round(round(target / step) * step, 2)
        now = dt_util.utcnow()
        if state.state != hvac and (self._exact or not (command.hvac == "heat" and state.state != "off")):
            write_log(self._hass).note_mode(self._external, hvac, now)
            await self._hass.services.async_call(
                "climate", "set_hvac_mode", {"entity_id": self._external, "hvac_mode": hvac}, blocking=True
            )
        if command.hvac in ("heat", "cool") and target is not None and not _same(attrs.get("temperature"), target):
            write_log(self._hass).note(self._external, to_c(target, unit), now)  # the followers compare in °C
            await self._hass.services.async_call(
                "climate", "set_temperature", {"entity_id": self._external, "temperature": target}, blocking=True
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
        if value is not None:  # 0.45.0: a flow setpoint number in °F gets °F (its min / max below are its own)
            value = from_c(value, state.attributes.get("unit_of_measurement"))
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

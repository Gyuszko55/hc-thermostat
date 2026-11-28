"""Mixing circuit instance (0.54.0, shadow only): the flow target of a radiator or floor circuit fed from a buffer tank.

It reads its zones (ordinary HC zone instances – they keep switching their own valves) and the outdoor thermometer
every 30 seconds, works out the raw flow target, and gives out a target that changes only now and then
(core/circuit.py, core/setpoint_hold.py). With a buffer instance linked it also shows what the tank can still give
this circuit.

0.56.0: in a supervised trial or in active mode the given-out target is written to the output (a PLC number /
input_number, or a climate's target) – only the setpoint: the PLC keeps driving its mixer, pump and safety limits
(output_writer.py: one writer, conflict detection, grace after a start, keep-alive, pause switch).
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (CONF_CIRCUIT_BUFFER, CONF_CIRCUIT_FLOW, CONF_CIRCUIT_OUTPUT, CONF_CIRCUIT_PUMP, CONF_OUTDOOR, CONF_WRITE_CONFIRM, CONF_WRITE_KEEPALIVE, CONF_ZONES,
                    DOMAIN, WRITE_CONFIRM_DEFAULT)
from .core.circuit import CircuitConfig, CircuitDecision, MixingCircuit, ZoneReading
from .core.circuit_watch import CircuitWatch
from .failsafe import StepFailsafe
from .safety_hub import stop_held
from .output_writer import OutputWriter, WriteControl
from .units import state_value_c

_LOGGER = logging.getLogger(__name__)
_INTERVAL = timedelta(seconds=30)
_SAVE_EVERY = timedelta(minutes=10)
OUTDOOR_MAX_AGE_S = 3 * 3600.0  # an outdoor reading older than this is lost (a dead sensor keeps its value)
FLOW_MAX_AGE_S = 3600.0  # 0.70.0: the circuit's flow thermometer for the watch
WATCH_WORDS = {"hu": {"no_pump": "a szivattyú nem indult el a hőigényre",
                      "no_flow": "a szivattyú fut, de az előremenő hőmérséklet nem változik"},
               "en": {"no_pump": "the pump did not start on the heat demand",
                      "no_flow": "the pump runs but the flow temperature does not move"}}


def pump_state(hass, entity_id: str | None) -> bool | None:
    """0.70.0: the circuit's pump (PLC) runs – on / off, or a number above zero (power, speed); None: not known."""
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    if state.state in ("on", "true", "running", "heat", "heating", "open"):
        return True
    if state.state in ("off", "false", "idle", "standby", "closed"):
        return False
    try:
        return float(state.state) > 0
    except ValueError:
        return None


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
        self.write = WriteControl(hass, entry, data)  # 0.56.0
        self.mode = self.write.mode
        confirm = data.get(CONF_WRITE_CONFIRM)
        self.out = OutputWriter(hass, data.get(CONF_CIRCUIT_OUTPUT), keepalive_s=float(data.get(CONF_WRITE_KEEPALIVE) or 0),
                                confirm_s=float(WRITE_CONFIRM_DEFAULT if confirm is None else confirm))
        self._started = dt_util.now()
        self.circuit = MixingCircuit(CircuitConfig.from_conf(data))
        self.zones: list[ZoneReading] = []
        self.usable: dict = {}
        self._cap_state = "off"
        cfg = self.circuit.cfg
        self.watch = CircuitWatch(cfg.circuit_watch_pump_s, cfg.circuit_watch_flow_s, cfg.circuit_watch_flow_c,
                                  bool(cfg.circuit_watch))  # 0.70.0
        self._watch_shown: str | None = None
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._last_save = dt_util.now()
        self.failsafe = StepFailsafe(hass, entry)  # 0.78.2: security review H2

    def plain_summary(self, language: str | None = None) -> dict | None:
        """0.87.0: "why heating / why not" in a few plain lines (core/summary_roles.py)."""
        from .plain import role_plain
        return role_plain(self, "circuit", language)

    @property
    def is_shadow(self) -> bool:
        return not self.write.writing(dt_util.now())

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
        buf = self.buffer_coordinator()
        # 0.64.0: the tank's top (a fresh reading, else None) caps the target given to the mixer
        top = getattr(getattr(buf, "data", None), "top", None) if buf is not None else None
        cfg = self.circuit.cfg
        try:
            decision = self.circuit.step(now, self.zones, read_outdoor(self.hass, self.conf.get(CONF_OUTDOOR), now),
                                         tank_top=top, tank_linked=buf is not None)
        except Exception:
            # 0.78.2: a step that fails again and again must not leave the mixer at a high flow target – from the
            # FAILSAFE_AFTER-th failure in a row the circuit's lowest flow (circuit_flow_min) is given out
            if not self.failsafe.failed():
                raise
            decision = CircuitDecision(now, cfg.circuit_flow_min, None, "failsafe", False,
                                       details={"failsafe": self.failsafe.errors})
        else:
            self.failsafe.ok()
        stop, by = stop_held(self.hass, now)
        if stop:
            # 0.78.2 (security review M3): the house's life-safety stop – the lowest flow, forced (also in shadow)
            decision = CircuitDecision(now, cfg.circuit_flow_min, decision.raw, "safety_stop", False,
                                       details={**(decision.details or {}), "safety_stop": by})
        # what the tank can give the demanded (uncapped) target
        self.usable = buf.stock.usable(decision.demand_target, cfg.circuit_dt, cfg.circuit_margin) \
            if buf is not None and decision.demand_target is not None else {}
        if decision.details.get("changed") or decision.cap_state != self._cap_state or now - self._last_save >= _SAVE_EVERY:
            await self.async_save()
        self._cap_state = decision.cap_state
        self._step_watch(now, decision)
        await self.write.tick(now)
        await self.out.apply(now, decision.target, self.write.writing(now), (now - self._started).total_seconds(),
                             force=stop)
        self.write.note_conflict(self.out)
        return decision

    # --- 0.70.0: watching demand → pump → flow ---------------------------------------------------------------
    def _step_watch(self, now: datetime, decision: CircuitDecision) -> None:
        pump_id, flow_id = self.conf.get(CONF_CIRCUIT_PUMP), self.conf.get(CONF_CIRCUIT_FLOW)
        flow = read_outdoor(self.hass, flow_id, now) if flow_id else None  # the same plausibility (−50…60 °C)
        state = self.hass.states.get(flow_id) if flow_id else None
        if flow is not None and state is not None:
            reported = getattr(state, "last_reported", None) or state.last_updated
            if reported is not None and (now - reported).total_seconds() > FLOW_MAX_AGE_S:
                flow = None
        self.watch.step(now, bool(decision.demand), pump_state(self.hass, pump_id), flow, decision.target,
                        bool(pump_id), bool(flow_id))
        decision.details["watch"] = {**self.watch.info(now), "flow": flow}
        self._sync_watch_repair()

    def _sync_watch_repair(self) -> None:
        """A broken chain is also an entry in Repairs; it clears itself when the circuit works again."""
        show = self.watch.state if self.watch.state in WATCH_WORDS["en"] else None
        if show == self._watch_shown:
            return
        self._watch_shown = show
        issue_id = f"circuit_problem_{self.config_entry.entry_id}"
        try:
            if show is None:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                return
            hu = str(getattr(self.hass.config, "language", "") or "").startswith("hu")
            since = self.watch.problem_at
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id, is_fixable=False, is_persistent=False,
                severity=ir.IssueSeverity.WARNING, translation_key="circuit_problem",
                translation_placeholders={"name": self.config_entry.title,
                                          "problem": WATCH_WORDS["hu" if hu else "en"][show],
                                          "since": since.strftime("%H:%M") if since else ""})
        except Exception:  # the Repairs entry is a report – it must never stop the decision
            _LOGGER.debug("The Repairs entry could not be updated", exc_info=True)

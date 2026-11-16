"""Heat pump coordination instance (0.55.0, shadow only): what a heat pump charging a buffer tank should get – the
ON/OFF request, the heat demand and a rarely changing flow target with the manual offset (core/hp_coord.py).

It reads the linked buffer instance (its stratified stock and trend, its mixing circuits and their given-out targets),
the outdoor thermometer, and optionally whether the heat pump runs now and a wood boiler signal.

0.56.0: in a supervised trial or in active mode it writes – the flow target (number / input_number / climate), then the
ON/OFF request (switch / input_boolean / climate hvac mode), and an optional heat demand signal – each output
through output_writer.py (one writer, conflict detection, grace after a start, keep-alive, pause switch). The unit's
own frost protection and the PLC's safety stay in charge.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .buffer_coordinator import asking_zones
from .circuit_coordinator import read_outdoor
from .const import (CONF_HP_BUFFER, CONF_HP_DEMAND_OUT, CONF_HP_EXERCISE_OUT, CONF_HP_SUMMER_OUT, CONF_HP_RUNNING, CONF_HP_SWITCH, CONF_HP_TARGET_OUT, CONF_OUTDOOR,
                    CONF_WOOD, CONF_WRITE_CONFIRM, CONF_WRITE_KEEPALIVE, CONF_ZONES, DOMAIN, WRITE_CONFIRM_DEFAULT)
from .core.hp_coord import CircuitNeed, HeatPumpCoordinator, HpConfig, HpDecision, HpInputs
from .output_writer import OutputWriter, WriteControl

_LOGGER = logging.getLogger(__name__)
_INTERVAL = timedelta(seconds=30)
_ASK_FRESH_S = 90  # 0.57.0: a zone asked this recently = it asks now (the circuits run every 30 s)
_SAVE_EVERY = timedelta(minutes=10)
RUNNING_W = 100.0  # a power reading above this means the heat pump runs
# 0.57.1: a number means "runs" only with a unit HC understands; anything else is "not known" (None), so a kW, A or Hz
# reading is no longer taken as watts (which made the heat pump's own heat look like wood)
RUNNING_ABOVE = {"W": RUNNING_W, "kW": 0.1, "mW": RUNNING_W * 1000, "A": 0.5, "mA": 500.0, "Hz": 0.0, "rpm": 0.0,
                 "%": 0.0}
# 0.59.0: a measured number (power, current…) that says "runs" but has not been reported for this long is not trusted:
# a meter that stopped reporting at 1.5 kW must not keep the heat pump "running" (and wood looking impossible).
# A stale low reading stays "does not run" – a quiet meter at idle is normal.
RUNNING_MAX_AGE_S = 900.0


def reading_age_s(state, now: datetime | None = None) -> float | None:
    """Seconds since the entity last reported (None: not known)."""
    reported = getattr(state, "last_reported", None) or getattr(state, "last_updated", None)
    if reported is None:
        return None
    try:
        return max(0.0, ((now or dt_util.utcnow()) - reported).total_seconds())
    except TypeError:
        return None


def on_state(hass, entity_id: str | None, now: datetime | None = None) -> bool | None:
    """True / False from a binary_sensor, switch, input_boolean, a climate's hvac_action or a number with a unit
    (power W / kW, current A, compressor Hz / rpm, modulation %); None when not given or not known."""
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in ("unavailable", "unknown"):
        return None
    domain = entity_id.split(".", 1)[0]
    if domain == "climate":
        action = state.attributes.get("hvac_action")
        if action in (None, "unknown"):
            return None
        return action in ("heating", "preheating", "defrosting")
    if state.state in ("on", "heat", "heating", "running", "true"):
        return True
    if state.state in ("off", "idle", "standby", "false"):
        return False
    try:
        value = float(state.state)
    except ValueError:
        return None
    above = RUNNING_ABOVE.get(str(state.attributes.get("unit_of_measurement") or "").strip())
    if above is None:
        return None
    runs = value > above
    if runs:
        age = reading_age_s(state, now)
        if age is not None and age > RUNNING_MAX_AGE_S:
            return None  # 0.59.0: an old "runs" reading – not known
    return runs


class HpCoordCoordinator(DataUpdateCoordinator[HpDecision]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN}_hp_coord", update_interval=_INTERVAL)
        data = {**entry.data, **entry.options}
        self.conf = data
        self.write = WriteControl(hass, entry, data)  # 0.56.0
        self.mode = self.write.mode
        keep = float(data.get(CONF_WRITE_KEEPALIVE) or 0)
        confirm = data.get(CONF_WRITE_CONFIRM)
        confirm = float(WRITE_CONFIRM_DEFAULT if confirm is None else confirm)
        self.out_target = OutputWriter(hass, data.get(CONF_HP_TARGET_OUT), keepalive_s=keep, confirm_s=confirm)
        self.out_switch = OutputWriter(hass, data.get(CONF_HP_SWITCH), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self.out_demand = OutputWriter(hass, data.get(CONF_HP_DEMAND_OUT), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self.out_summer = OutputWriter(hass, data.get(CONF_HP_SUMMER_OUT), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self.out_exercise = OutputWriter(hass, data.get(CONF_HP_EXERCISE_OUT), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self._started = dt_util.now()
        self.hp = HeatPumpCoordinator(HpConfig.from_conf(data))
        self.offset: float | None = None  # the number entity's value (restored by it)
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._last_save = dt_util.now()

    @property
    def is_shadow(self) -> bool:
        return not self.write.writing(dt_util.now())

    def outputs(self) -> dict:
        return {"target": self.out_target.info(), "switch": self.out_switch.info(), "demand": self.out_demand.info(),
                "summer": self.out_summer.info(), "exercise": self.out_exercise.info()}

    async def async_load(self) -> None:
        self.hp.restore(await self._store.async_load() or {}, dt_util.now())

    async def async_save(self) -> None:
        now = dt_util.now()
        self._last_save = now
        await self._store.async_save(self.hp.state(now))

    def buffer_coordinator(self):
        entry_id = self.conf.get(CONF_HP_BUFFER)
        entry = self.hass.config_entries.async_get_entry(entry_id) if entry_id else None
        c = getattr(entry, "runtime_data", None) if entry is not None else None
        return c if hasattr(c, "stock") else None

    def inputs(self, now: datetime) -> HpInputs:
        buf = self.buffer_coordinator()
        stock = getattr(buf, "stock", None)
        trend = getattr(buf, "trend", {}) or {}
        circuits, zones_asking, frost = [], False, 8.0
        if buf is not None:
            frost = buf.buffer.cfg.buffer_frost
            for e, cc in buf.circuits():
                d = cc.data
                if d is not None:
                    asked = [t for t in cc.circuit.last_ask.values() if (now - t).total_seconds() <= _ASK_FRESH_S]
                    circuits.append(CircuitNeed(e.title, d.demand, d.target, cc.circuit.cfg.circuit_margin, bool(asked)))
            if not circuits:  # no circuit linked: the buffer's own zones say whether heat is wanted
                zones_asking = bool(asking_zones(self.hass, list(buf.conf.get(CONF_ZONES) or [])))
        return HpInputs(outdoor=read_outdoor(self.hass, self.conf.get(CONF_OUTDOOR), now),
                        top=stock.top if stock is not None else None,
                        charge=stock.charge if stock is not None else None,
                        trend_c_h=trend.get("c_per_h"), circuits=tuple(circuits), zones_asking=zones_asking,
                        frost_top=frost,
                        wood_signal=on_state(self.hass, self.conf.get(CONF_WOOD), now) if self.conf.get(CONF_WOOD) else None,
                        hp_running=on_state(self.hass, self.conf.get(CONF_HP_RUNNING), now),
                        hp_running_age_s=self._running_age(now),
                        offset=self.offset)

    def _running_age(self, now: datetime) -> float | None:
        """0.59.0: how old the "runs" reading is (shown next to it)."""
        eid = self.conf.get(CONF_HP_RUNNING)
        state = self.hass.states.get(eid) if eid else None
        if state is None:
            return None
        age = reading_age_s(state, now)
        return None if age is None else round(age)

    async def _async_update_data(self) -> HpDecision:
        now = dt_util.now()
        was = (self.hp.enable, self.hp.heating, self.hp.cold_latched, self.hp.summer)
        decision = self.hp.step(now, self.inputs(now))
        if was != (self.hp.enable, self.hp.heating, self.hp.cold_latched, self.hp.summer) or decision.details.get("target_changed") \
                or now - self._last_save >= _SAVE_EVERY:
            await self.async_save()
        await self.write.tick(now)
        writing, up = self.write.writing(now), (now - self._started).total_seconds()
        # the target first, so an ON finds the right water asked for; then ON / OFF, then the demand signal
        for out, value in ((self.out_target, decision.target), (self.out_switch, decision.enable),
                           (self.out_demand, decision.heat_demand), (self.out_summer, decision.summer),
                           (self.out_exercise, decision.exercise)):
            await out.apply(now, value, writing, up)
            self.write.note_conflict(out)
        return decision

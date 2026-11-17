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
from .const import (CONF_HP_TARGET_ROUND, CONF_HP_WATER_TEMP, CONF_HP_BUFFER, CONF_HP_DEMAND_OUT, CONF_HP_EXERCISE_OUT, CONF_HP_SUMMER_OUT, CONF_HP_RUNNING, CONF_HP_SWITCH, CONF_HP_TARGET_OUT, CONF_OUTDOOR,
                    CONF_WOOD, CONF_WOOD_TEMP, CONF_WRITE_CONFIRM, CONF_WRITE_KEEPALIVE, CONF_ZONES, DOMAIN, WRITE_CONFIRM_DEFAULT)
from .core.hp_coord import CircuitNeed, HeatPumpCoordinator, HpConfig, HpDecision, HpInputs
from .core.wood import WoodConfig, WoodDetector
from .units import state_value_c
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
TARGET_TOL_C = 0.4  # 0.70.0: the unit's reported target may differ this much from the sent one (its own rounding)
TARGET_MISMATCH_S = 600.0  # 0.70.0: a larger difference lasting this long is a mismatch
STANDBY_W = 10.0  # 0.70.0: a power reading above this (and below the compressor's threshold): switched on, standing


def reading_age_s(state, now: datetime | None = None) -> float | None:
    """Seconds since the entity last reported (None: not known)."""
    reported = getattr(state, "last_reported", None) or getattr(state, "last_updated", None)
    if reported is None:
        return None
    try:
        return max(0.0, ((now or dt_util.utcnow()) - reported).total_seconds())
    except TypeError:
        return None


def run_state(hass, entity_id: str | None, now: datetime | None = None, running_w: float | None = None,
              standby_w: float | None = None) -> tuple[str, float | None]:
    """0.70.0: what the heat pump does – ("heating" | "standby" | "stopped" | "unknown", the power reading in W or None).
    heating: the compressor runs (above `hp_running_w`); standby: switched on but the compressor stands – a power reading
    between `hp_standby_w` and `hp_running_w` (frost protection, circulation, electronics), a climate on but idle, or a
    "standby" state; stopped: off / at about zero; unknown: no reading, or a "runs" reading not reported for
    RUNNING_MAX_AGE_S (a meter that went quiet must not keep the compressor running). A quiet low reading stays what it
    was (as since 0.59.0: a meter at idle is often silent) – its age is shown next to it."""
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in ("unavailable", "unknown"):
        return "unknown", None
    domain = entity_id.split(".", 1)[0]
    if domain == "climate":
        action = state.attributes.get("hvac_action")
        if action in ("heating", "preheating", "defrosting"):
            return "heating", None
        if state.state == "off" or action == "off":
            return "stopped", None
        if action == "idle":
            return "standby", None
        return "unknown", None
    if state.state in ("on", "heat", "heating", "running", "true"):
        return "heating", None
    if state.state == "standby":
        return "standby", None
    if state.state in ("off", "idle", "false"):
        return "stopped", None
    try:
        value = float(state.state)
    except ValueError:
        return "unknown", None
    unit = str(state.attributes.get("unit_of_measurement") or "").strip()
    above = RUNNING_ABOVE.get(unit)
    to_w = {"W": 1.0, "kW": 1000.0, "mW": 0.001}.get(unit)
    if running_w is not None and to_w is not None:  # 0.69.0: the compressor's own power threshold
        above = running_w / to_w
    if above is None:
        return "unknown", None
    watts = None if to_w is None else round(value * to_w, 1)
    if value > above:
        result = "heating"
    elif to_w is not None and value * to_w > (STANDBY_W if standby_w is None else standby_w):
        result = "standby"
    else:
        result = "stopped"
    if result == "heating":
        age = reading_age_s(state, now)
        if age is not None and age > RUNNING_MAX_AGE_S:
            return "unknown", watts  # 0.59.0: an old "runs" reading – not known
    return result, watts


RUN_BOOL = {"heating": True, "standby": False, "stopped": False, "unknown": None}


def on_state(hass, entity_id: str | None, now: datetime | None = None, running_w: float | None = None) -> bool | None:
    """True / False from a binary_sensor, switch, input_boolean, a climate's hvac_action or a number with a unit
    (power W / kW, current A, compressor Hz / rpm, modulation %); None when not given or not known."""
    return RUN_BOOL[run_state(hass, entity_id, now, running_w)[0]]


def _layers(stock) -> tuple:
    """0.65.0: the tank's layers for the demand-based charging: (name, °C, litres, measured), top first."""
    if stock is None:
        return ()
    vol = getattr(stock, "volume_l", None) or 0
    return tuple((l.name, l.temp, round(l.share * vol, 1) if vol else None, bool(l.measured))
                 for l in getattr(stock, "layers", ()) or ())


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
        self.out_target = OutputWriter(hass, data.get(CONF_HP_TARGET_OUT), keepalive_s=keep, confirm_s=confirm,
                                       round_mode=str(data.get(CONF_HP_TARGET_ROUND) or "device"))  # 0.64.0
        self.out_switch = OutputWriter(hass, data.get(CONF_HP_SWITCH), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self.out_demand = OutputWriter(hass, data.get(CONF_HP_DEMAND_OUT), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self.out_summer = OutputWriter(hass, data.get(CONF_HP_SUMMER_OUT), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self.out_exercise = OutputWriter(hass, data.get(CONF_HP_EXERCISE_OUT), onoff=True, keepalive_s=keep, confirm_s=confirm)
        self._started = dt_util.now()
        self.hp = HeatPumpCoordinator(HpConfig.from_conf(data))
        self.wood = WoodDetector(WoodConfig.from_conf(data))  # 0.61.0: wood from the boiler's thermometer
        self.wood_temp: float | None = None
        self._mismatch_since: datetime | None = None  # 0.70.0
        self.offset: float | None = None  # the number entity's value (restored by it)
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._last_save = dt_util.now()

    @property
    def is_shadow(self) -> bool:
        return not self.write.writing(dt_util.now())

    def water_temp(self) -> float | None:
        """0.64.0: the heat pump's own water thermometer (shown on the chart next to the targets)."""
        eid = self.conf.get(CONF_HP_WATER_TEMP)
        state = self.hass.states.get(eid) if eid else None
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        value = state_value_c(state)
        return None if value is None else round(value, 2)

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
                    circuits.append(CircuitNeed(e.title, d.demand,
                                                    # 0.64.0: the demanded target, never the tank-capped one
                                                    d.demand_target if d.demand_target is not None else d.target,
                                                    cc.circuit.cfg.circuit_margin, bool(asked)))
            if not circuits:  # no circuit linked: the buffer's own zones say whether heat is wanted
                zones_asking = bool(asking_zones(self.hass, list(buf.conf.get(CONF_ZONES) or [])))
        run = run_state(self.hass, self.conf.get(CONF_HP_RUNNING), now, self.hp.cfg.hp_running_w,
                        self.hp.cfg.hp_standby_w)  # 0.70.0
        return HpInputs(outdoor=read_outdoor(self.hass, self.conf.get(CONF_OUTDOOR), now),
                        top=stock.top if stock is not None else None,
                        charge=stock.charge if stock is not None else None,
                        trend_c_h=trend.get("c_per_h"), circuits=tuple(circuits), zones_asking=zones_asking,
                        frost_top=frost,
                        wood_signal=self._wood_signal(now),
                        hp_running=RUN_BOOL[run[0]], hp_state=run[0] if self.conf.get(CONF_HP_RUNNING) else None,
                        hp_power_w=run[1],
                        hp_running_age_s=self._running_age(now),
                        offset=self.offset,
                        layers=_layers(stock))

    def _wood_signal(self, now: datetime) -> bool | None:
        """The wood signal: a direct contact first; else (0.61.0) the wood boiler's thermometer by two thresholds."""
        if self.conf.get(CONF_WOOD):
            return on_state(self.hass, self.conf.get(CONF_WOOD), now)
        eid = self.conf.get(CONF_WOOD_TEMP)
        if not eid:
            return None
        state = self.hass.states.get(eid)
        temp = state_value_c(state) if state is not None and state.state not in ("unavailable", "unknown") else None
        if temp is not None:
            age = reading_age_s(state, now)
            if age is not None and age > 3600:  # a dead thermometer keeps its value: not trusted after an hour
                temp = None
        self.wood_temp = temp
        return self.wood.step(now, temp)

    def wood_info(self, now: datetime) -> dict:
        """0.61.0: where the wood signal comes from, for the info panel."""
        by = "signal" if self.conf.get(CONF_WOOD) else "temp" if self.conf.get(CONF_WOOD_TEMP) else None
        out = {"by": by}
        if by == "temp":
            cfg = self.wood.cfg
            out.update(temp=self.wood_temp, on_above=cfg.wood_on_above, off_below=cfg.wood_off_below,
                       confirm_s=cfg.wood_confirm_s, **self.wood.info(now))
        return out

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
        self._target_check(now, decision, writing)
        return decision

    def _target_check(self, now: datetime, d: HpDecision, writing: bool) -> None:
        """0.70.0 (a tester's request): does the heat pump use the target HC asks for? The worked-out (raw), the
        given-out and the really sent target next to what the unit reports back. While HC writes, a difference above
        TARGET_TOL_C lasting TARGET_MISMATCH_S is a mismatch (shown in amber on the diagram); in shadow the unit's own
        target is only shown – HC asks nothing then."""
        if not self.conf.get(CONF_HP_TARGET_OUT):
            return
        rep, sent = self.out_target.reported(), self.out_target.sent
        ask = sent if writing and sent is not None else d.target
        diff = None if rep is None or ask is None else round(rep - ask, 2)
        off = writing and diff is not None and abs(diff) > TARGET_TOL_C
        if not off:
            self._mismatch_since = None
        elif self._mismatch_since is None:
            self._mismatch_since = now
        lasting = off and (now - self._mismatch_since).total_seconds() >= TARGET_MISMATCH_S
        d.details["target_check"] = {"raw": d.raw, "given": d.target, "sent": sent if writing else None, "reported": rep,
                                     "diff": diff, "writing": writing, "mismatch": lasting,
                                     "mismatch_min": round((now - self._mismatch_since).total_seconds() / 60)
                                     if self._mismatch_since else None}

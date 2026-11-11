"""Reads Home Assistant, asks the supervisor, logs the decision, runs the executor."""

from __future__ import annotations

from collections import deque
from datetime import datetime, time, timedelta
import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACTUATOR, CONF_KEEP_ALIVE_SCRIPT, CONF_BOILER_LIMIT, CONF_BOILER_PRICE, CONF_BOILER_PRICE_MANUAL, CONF_COP_HIGH, CONF_COP_LOW,
    CONF_BOILER_POWER, CONF_ENERGY_FACTOR, CONF_FLOW, CONF_HEAT_ENABLE, CONF_FLAME, CONF_WINDOW_DROP, CONF_OTHER_LIMIT, CONF_OTHER_PRICE, CONF_OTHER_PRICE_MANUAL, CONF_EXTERNAL, CONF_EXTRA_FACTOR, CONF_EXTRA_HEAT, CONF_HEAT_ENERGY, CONF_INDOOR, CONF_MODE, CONF_OUTDOOR, CONF_PRESENCE,
    CONF_REFERENCE, CONF_WINDOWS, CONF_ZONE_DIFF, CONF_ZONE_DOORS, CONF_ZONE_TEMP, DOMAIN, MODE_SHADOW,
    CONF_ASSIST, CONF_ROOMS, CONF_ROOM_TOL, CONF_ROOM_TRVS, CONF_ROOM_TRV_DEMAND, EVENT_ROOM_ADVICE, MODE_ACTIVE,
    CONF_HUMIDITY, CONF_COOL_MODE, CONF_COOL_FLOW, CONF_TRV_OFFSETS, CONF_POWER_AVAILABLE, CONF_DISCHARGE, CONF_FAN, CONF_COIL, CONF_RETURN,
    CONF_HEAT_SOURCE, CONF_ROLE, CONF_FLOOR, CONF_SYSTEM, CONF_TARGET_SOURCE, CONF_HP_DEFROST, CONF_HP_DHW,
    CONF_CONTROL, CONF_DEMAND,
)
from .core.boiler_health import BoilerHealth, health_kind
from .core.plausibility import Plausibility
from .core.matrix import ROOM_SOURCES, default_curve, floor_system, source_defaults
from .core.target_source import TargetFollower, source_value
from .core.model import Reason
from .core.rooms import RoomMonitor, room_text
from .core.trv import RoomDemand, TrvCalibration, TrvTargets
from .core.cost import CostAdvice, compare
from .core.messages import explain
from .core.model import Decision, HcConfig, Inputs, Presence, Reading
from .core.supervisor import Supervisor
from .core.zone import coupled
from .core.load import LoadClient, LoadManager
from .executor import Executor, write_log
from .rooms_ha import group_by_room, room_value

_LOGGER = logging.getLogger(__name__)
_INTERVAL = timedelta(seconds=30)
_SAVE_EVERY = timedelta(minutes=10)
_LOG_SIZE = 200
_AGREEMENT_SIZE = 2880  # 24 hours
_OUTDOOR_EVERY = timedelta(minutes=10)
_HOME = {"home", "on", "otthon"}
# a heat pump's defrost / hot-water signal: a binary sensor, a switch, or a mode sensor that names it
_BUSY_STATES = {"on", "true", "1", "defrost", "defrosting", "dhw", "hot_water", "domestic_hot_water", "leolvasztás", "hmv"}
_VACATION = {"vacation", "szabadság", "szabadsag"}


def load_manager(hass) -> LoadManager:
    """The one load manager of this Home Assistant (shared by every electric zone)."""
    return hass.data.setdefault(f"{DOMAIN}_load", LoadManager())


class HcCoordinator(DataUpdateCoordinator[Decision]):
    def __init__(self, hass: HomeAssistant, entry) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=_INTERVAL)
        data = {**entry.data, **entry.options}
        self.conf = data
        # safety defaults by heat source (electric: no blind fallback, floor limit); an explicit setting wins
        system, source = data.get(CONF_SYSTEM), data.get(CONF_HEAT_SOURCE)
        # a zone of a central modulating boiler asks for a flow by its own system's curve (floor: flat and low)
        curve = ({k: v for k, v in default_curve(system or "", source or "").items() if k != "heat_pump"}
                 if data.get(CONF_ROLE) == "zone" else {})
        contact = bool(data.get(CONF_DEMAND)) and data.get(CONF_CONTROL, "tpi") in ("tpi", "pid", "onoff")
        self.cfg = HcConfig.from_mapping({**source_defaults(system, source), **curve, **data,
                                          "floor_system": floor_system(system), "demand_contact": contact})
        self.mode = data.get(CONF_MODE, MODE_SHADOW)
        self.supervisor = Supervisor(self.cfg)
        if self.mode == MODE_ACTIVE and self.cfg.load_limit_kw > 0 and self.cfg.boiler_power_kw > 0:
            # electric zones sharing a power budget: only live relays count (a shadow instance switches nothing)
            self.supervisor.load = LoadClient(load_manager(hass), entry.title, self.cfg.boiler_power_kw, self.cfg.load_limit_kw)
        self.enabled = True
        self.log: deque[dict] = deque(maxlen=_LOG_SIZE)
        self._agreement: deque[bool] = deque(maxlen=_AGREEMENT_SIZE)
        self._outdoor: deque[tuple[str, float]] = deque(maxlen=144)
        self._executor = Executor(hass, self.mode, data.get(CONF_ACTUATOR), data.get(CONF_EXTERNAL),
                                  data.get(CONF_FLOW), data.get(CONF_HEAT_ENABLE), self.cfg.keep_alive_s,
                                  exact_mode=self.cfg.control == "ac",
                                  cool_mode=data.get(CONF_COOL_MODE), cool_flow=data.get(CONF_COOL_FLOW),
                                  discharge=data.get(CONF_DISCHARGE), fan=data.get(CONF_FAN),
                                  keep_script=data.get(CONF_KEEP_ALIVE_SCRIPT))
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self._started = dt_util.utcnow()
        self._last_save = self._started
        self._last_key: tuple | None = None
        self._extra_samples: deque[tuple[datetime, float]] = deque()
        self._counted_extra = 0.0  # kWh of the other source that reached the house
        self._last_extra: float | None = None
        self.zone: dict = {}
        self.extra_kw = 0.0
        self.cost = CostAdvice("unknown")
        self.actual: bool | None = None
        self.health = BoilerHealth(self.cfg, health_kind(data.get(CONF_HEAT_SOURCE)))
        cfg = self.cfg
        self._plaus_indoor = Plausibility(cfg.plaus_indoor_min, cfg.plaus_indoor_max, cfg.plaus_jump, cfg.plaus_confirm_s)
        self._plaus_outdoor = Plausibility(cfg.plaus_outdoor_min, cfg.plaus_outdoor_max)
        self._plaus_floor = Plausibility(0.0, 50.0, 6.0, cfg.plaus_confirm_s)  # a floor sensor inside the screed
        self._follower = TargetFollower()
        self._sensor_bad_since: dict[str, datetime] = {}
        self.sensor_problems: dict[str, str] = {}  # entity → lost | stale | out_of_range | jump (after a while)
        # one room (a heater, an AC unit, a zone): the texts say "the room" instead of "the house"
        self.room_wording = data.get(CONF_HEAT_SOURCE) in ROOM_SOURCES or data.get(CONF_ROLE) == "zone"
        self.rooms = RoomMonitor(float(data.get(CONF_ROOM_TOL, 0.5)))
        self.room_advice: list = []
        self._room_groups: dict[str, list[str]] | None = None
        self._trv_groups: dict[str, list[str]] | None = None
        self.trv_targets = TrvTargets()
        self.trv_cal = TrvCalibration()
        self.trv_info: dict[str, dict] = {}  # room -> {target, offset, heads: {head: {calibration, written}}}
        self.room_demand = RoomDemand()
        self.asking_rooms: list[str] = []

    # --- persistence -----------------------------------------------------------
    async def async_load(self) -> None:
        data = await self._store.async_load()
        if not data:
            return
        self.supervisor.restore(data.get("supervisor", {}))
        if data.get("mode") != self.mode:
            # Going live (or back to shadow): the cycle phase of the old mode would delay the first start.
            self.supervisor.new_cycle()
        if data.get("heat_basis") != self._heat_basis():
            self.supervisor.heat_need.samples.clear()  # Learned under other settings: not comparable.
        self.enabled = data.get("enabled", True)
        self.log.extend(data.get("log", []))
        self._outdoor.extend(tuple(x) for x in data.get("outdoor", []))
        self._counted_extra = float(data.get("counted_extra", 0.0))
        self._last_extra = data.get("last_extra")
        self.rooms.restore(data.get("rooms") or {})
        self.trv_targets.restore(data.get("trv") or {})
        self.trv_cal.restore(data.get("trv_cal") or {})

    async def async_backfill(self) -> None:
        """Seed the heat need from the statistics so it does not start empty."""
        conf, need = self.conf, self.supervisor.heat_need
        energy, indoor, outdoor = conf.get(CONF_HEAT_ENERGY), conf.get(CONF_INDOOR), conf.get(CONF_OUTDOOR)
        if need.samples or not (energy and indoor and outdoor):
            return
        # The statistics do not tell when a zone door was open, so its heat is left out here.
        extra = None if conf.get(CONF_ZONE_DOORS) else conf.get(CONF_EXTRA_HEAT)
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            today = dt_util.start_of_local_day()
            ids = {energy, indoor, outdoor} | ({extra} if extra else set())
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period, self.hass, today - timedelta(days=30), today, ids, "day", None,
                {"change", "mean"},
            )
        except Exception:  # Seeding is a convenience: the daily learning still runs.
            _LOGGER.debug("No statistics to seed the heat need from", exc_info=True)
            return
        window_start = dt_util.as_timestamp(today - timedelta(days=30))
        for day, kwh, degree_hours in seed_samples(
                stats, energy, indoor, outdoor, extra, float(conf.get(CONF_ENERGY_FACTOR, 1.0)),
                float(conf.get(CONF_EXTRA_FACTOR, 1.0)), window_start):
            need.add_sample(day, kwh, degree_hours)

    def _heat_basis(self) -> list:
        conf = self.conf
        return [conf.get(CONF_HEAT_ENERGY), conf.get(CONF_ENERGY_FACTOR), conf.get(CONF_EXTRA_HEAT),
                conf.get(CONF_EXTRA_FACTOR), sorted(conf.get(CONF_ZONE_DOORS) or []), conf.get(CONF_ZONE_DIFF)]

    async def async_save(self) -> None:
        await self._store.async_save({
            "supervisor": self.supervisor.state(),
            "mode": self.mode,
            "enabled": self.enabled,
            "log": list(self.log),
            "outdoor": list(self._outdoor),
            "heat_basis": self._heat_basis(),
            "counted_extra": self._counted_extra,
            "rooms": self.rooms.state(),
            "trv": self.trv_targets.state(),
            "trv_cal": self.trv_cal.state(),
            "last_extra": self._last_extra,
        })

    # --- reading Home Assistant ------------------------------------------------
    def _reading(self, entity_id: str | None, now: datetime) -> Reading:
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None:
            return Reading()
        raw = state.attributes.get("temperature") if entity_id.startswith("weather.") else state.state
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return Reading()
        return Reading(value, (now - state.last_reported).total_seconds())

    def _presence(self) -> Presence:
        states = [self.hass.states.get(e) for e in self.conf.get(CONF_PRESENCE) or []]
        values = [s.state.lower() for s in states if s and s.state not in ("unknown", "unavailable")]
        if not values or any(v in _HOME for v in values):
            return Presence.HOME
        return Presence.VACATION if any(v in _VACATION for v in values) else Presence.AWAY

    def _window_open(self) -> bool:
        return any(
            (s := self.hass.states.get(e)) is not None and s.state == "on"
            for e in self.conf.get(CONF_WINDOWS) or []
        )

    def _cumulative(self, entity_id: str | None) -> float | None:
        state = self.hass.states.get(entity_id) if entity_id else None
        try:
            return float(state.state) if state else None
        except ValueError:
            return None

    def _zone_state(self, indoor: Reading, now: datetime) -> tuple[bool, bool]:
        """Door open and coupled; without a zone the other source always counts."""
        conf = self.conf
        doors = conf.get(CONF_ZONE_DOORS) or []
        door_open = any((s := self.hass.states.get(e)) is not None and s.state == "on" for e in doors)
        temp = self._reading(conf.get(CONF_ZONE_TEMP), now).fresh(self.cfg.sensor_max_age_s)
        is_coupled = coupled(door_open, indoor.fresh(self.cfg.sensor_max_age_s), temp,
                             float(conf.get(CONF_ZONE_DIFF, 2.0)))
        self.zone = {"configured": bool(doors), "door_open": door_open, "temp": temp, "coupled": is_coupled}
        return door_open, is_coupled or not doors

    def _heat_energy(self, counts: bool) -> float | None:
        """Cumulative heat that reached the house."""
        conf = self.conf
        main = self._cumulative(conf.get(CONF_HEAT_ENERGY))
        extra = self._cumulative(conf.get(CONF_EXTRA_HEAT))
        if extra is not None:
            if counts and self._last_extra is not None and extra > self._last_extra:
                self._counted_extra += (extra - self._last_extra) * float(conf.get(CONF_EXTRA_FACTOR, 1.0))
            self._last_extra = extra
        if main is None and extra is None:
            return None
        return (main or 0.0) * float(conf.get(CONF_ENERGY_FACTOR, 1.0)) + self._counted_extra

    def _other_heat_kw(self, now: datetime) -> float:
        """Average heat of the other source over the last hour."""
        value = self._cumulative(self.conf.get(CONF_EXTRA_HEAT))
        if value is None:
            return 0.0
        samples = self._extra_samples
        samples.append((now, value))
        while now - samples[0][0] > timedelta(hours=1):
            samples.popleft()
        hours = (now - samples[0][0]).total_seconds() / 3600
        if hours < 0.25 or value < samples[0][1]:
            return 0.0
        return (value - samples[0][1]) * float(self.conf.get(CONF_EXTRA_FACTOR, 1.0)) / hours

    def _actual_heating(self) -> bool | None:
        conf = self.conf
        # A flame sensor shows the real burner; otherwise the reference thermostat or the relay itself.
        entity = conf.get(CONF_FLAME) or conf.get(CONF_REFERENCE) or conf.get(CONF_ACTUATOR) or conf.get(CONF_EXTERNAL)
        state = self.hass.states.get(entity) if entity else None
        if state is None or state.state in ("unknown", "unavailable"):
            return None
        if entity.startswith("climate."):
            return state.attributes.get("hvac_action") == "heating"
        return state.state == "on"

    def _outdoor_average(self, reading: Reading, now: datetime) -> float | None:
        fresh = reading.fresh(self.cfg.sensor_max_age_s)
        last = datetime.fromisoformat(self._outdoor[-1][0]) if self._outdoor else None
        if fresh is not None and (last is None or now - last >= _OUTDOOR_EVERY):
            self._outdoor.append((now.isoformat(), fresh))
        limit = now - timedelta(hours=24)
        values = [v for t, v in self._outdoor if datetime.fromisoformat(t) >= limit]
        return sum(values) / len(values) if len(values) >= 6 else None

    # --- one decision ----------------------------------------------------------
    def build_inputs(self, now: datetime) -> Inputs:
        conf = self.conf
        outdoor = self._plaus_outdoor.check(now, self._reading(conf.get(CONF_OUTDOOR), now))
        indoor = self._plaus_indoor.check(now, self._reading(conf.get(CONF_INDOOR), now))
        floor = self._plaus_floor.check(now, self._reading(conf.get(CONF_FLOOR), now)) if conf.get(CONF_FLOOR) else Reading()
        self._update_sensor_problems(now)
        door_open, counts = self._zone_state(indoor, now)
        self.extra_kw = self._other_heat_kw(now)
        self.actual = self._actual_heating()
        return Inputs(
            now=now,
            indoor=indoor,
            outdoor=outdoor,
            outdoor_avg=self._outdoor_average(outdoor, now),
            presence=self._presence(),
            window_open=self._window_open() or (door_open and not counts),
            enabled=self.enabled,
            uptime_s=(now - self._started).total_seconds(),
            actual_heating=self.actual,
            heat_energy_kwh=self._heat_energy(counts),
            other_heat_kw=self.extra_kw if counts else 0.0,
            drop_temps=tuple((e, self._reading(e, now)) for e in conf.get(CONF_WINDOW_DROP) or []),
            room_demand=tuple(self._room_demand(now)),
            yield_margin=self.cfg.yield_margin if self.cost.advice == "other" else 0.0,
            assist_target=self._assist_target(),
            floor=floor,
            hp_mode=self._hp_mode(),
            call=self._call(),
            humidity=self._humidity(now),
            power_available=self._power_available(),
            coil=self._reading(conf.get(CONF_COIL), now) if conf.get(CONF_COIL) else Reading(),
            return_temp=self._reading(conf.get(CONF_RETURN), now) if conf.get(CONF_RETURN) else Reading(),
            **self._unit_inputs(),
        )

    def _update_sensor_problems(self, now: datetime) -> None:
        """Which sensor is missing, silent or unbelievable – reported after `sensor_problem_after_s`."""
        conf, cfg = self.conf, self.cfg
        checks = [(conf.get(CONF_INDOOR), self._plaus_indoor), (conf.get(CONF_OUTDOOR), self._plaus_outdoor)]
        if conf.get(CONF_FLAME):
            checks.append((conf.get(CONF_FLAME), None))
        if conf.get(CONF_FLOOR):
            checks.append((conf.get(CONF_FLOOR), self._plaus_floor))
        if self.cfg.demand_contact:
            checks.append((conf.get(CONF_DEMAND), None))
        current: dict[str, str] = {}
        for entity, plaus in checks:
            if not entity:
                continue
            state = self.hass.states.get(entity)
            if state is None or state.state in ("unknown", "unavailable"):
                current[entity] = "lost"
            elif plaus is not None and plaus.problem:
                current[entity] = plaus.problem
            elif plaus is not None and (now - state.last_reported).total_seconds() > cfg.sensor_max_age_s:
                current[entity] = "stale"
        for entity in list(self._sensor_bad_since):
            if entity not in current:
                del self._sensor_bad_since[entity]
        for entity in current:
            self._sensor_bad_since.setdefault(entity, now)
        self.sensor_problems = {e: why for e, why in current.items()
                                if (now - self._sensor_bad_since[e]).total_seconds() >= cfg.sensor_problem_after_s}

    def _call(self) -> bool | None:
        """Wired wall thermostat (0.38.0): its contact on / off; None when unknown, unavailable or not configured."""
        if not self.cfg.demand_contact:
            return None
        state = self.hass.states.get(self.conf.get(CONF_DEMAND))
        if state is None or state.state not in ("on", "off"):
            return None
        return state.state == "on"

    def _power_available(self) -> bool | None:
        """Controlled (off-peak) power on? None without a signal or when it cannot be read (then it is assumed on)."""
        entity = self.conf.get(CONF_POWER_AVAILABLE)
        state = self.hass.states.get(entity) if entity else None
        if state is None or state.state not in ("on", "off"):
            return None
        return state.state == "on"

    def _humidity(self, now: datetime) -> Reading:
        """Room relative humidity (floor cooling); 0–100 % only."""
        reading = self._reading(self.conf.get(CONF_HUMIDITY), now) if self.conf.get(CONF_HUMIDITY) else Reading()
        return reading if reading.value is not None and 0 < reading.value <= 100 else Reading()

    def _hp_mode(self) -> str | None:
        """What the heat pump does besides heating the house, from its optional signals."""
        for key, mode in ((CONF_HP_DEFROST, "defrost"), (CONF_HP_DHW, "dhw")):
            state = self.hass.states.get(self.conf.get(key) or "")
            if state is not None and str(state.state).lower() in _BUSY_STATES:
                return mode
        return None

    @callback
    def async_track_target_source(self):
        """Follow the setpoint of a wall thermostat / number: a hand on its knob becomes the manual target here
        (until the next scheduled change); what an HC instance wrote there itself is ignored."""
        entity = self.conf.get(CONF_TARGET_SOURCE)
        if not entity:
            return lambda: None

        def value(state) -> float | None:
            return source_value(state.domain, state.state, dict(state.attributes)) if state is not None else None

        self._follower.changed(value(self.hass.states.get(entity)), None, False)  # remember the start value

        @callback
        def changed(event: Event) -> None:
            v = value(event.data.get("new_state"))
            own = v is not None and write_log(self.hass).recent(entity, v, dt_util.utcnow())
            current = self.data.target if self.data is not None else None
            new = self._follower.changed(v, current, own)
            if new is not None:
                self.supervisor.manual_target = new
                _LOGGER.debug("%s: target %s taken over from %s", self.config_entry.title, new, entity)
                self.hass.async_create_task(self.async_request_refresh())

        return async_track_state_change_event(self.hass, [entity], changed)

    def _assist_target(self) -> float | None:
        """Air conditioner: the house target, while the house says this source is cheaper and its door is open."""
        house = self.conf.get(CONF_ASSIST) if self.cfg.control == "ac" else None
        state = self.hass.states.get(house) if house else None
        if state is None or state.state in ("off", "unavailable", "unknown"):
            return None
        a = state.attributes
        if a.get("source_advice") in ("other", "other_zone_only") and a.get("zone_door_open") and isinstance(a.get("temperature"), (int, float)):
            return float(a["temperature"])
        return None

    def _unit_inputs(self) -> dict:
        """Air conditioner: its own reading, step and limits."""
        if self.cfg.control != "ac":
            return {}
        state = self.hass.states.get(self.conf.get(CONF_EXTERNAL) or "")
        if state is None:
            return {}
        a = state.attributes
        num = lambda k: float(a[k]) if isinstance(a.get(k), (int, float)) else None
        return {"unit_temp": num("current_temperature"), "unit_step": num("target_temp_step"),
                "unit_min": num("min_temp"), "unit_max": num("max_temp")}

    def _price(self, entity_key: str, manual_key: str) -> float | None:
        """A sensor (for example from Rezsikövető) wins; the manual price is the fallback."""
        value = self._cumulative(self.conf.get(entity_key))
        if value is None:
            value = self.conf.get(manual_key)
        return float(value) if value else None

    def _compare_cost(self, decision: Decision) -> CostAdvice:
        conf = self.conf
        return compare(
            self._price(CONF_BOILER_PRICE, CONF_BOILER_PRICE_MANUAL), float(conf.get(CONF_ENERGY_FACTOR, 1.0)),
            self._price(CONF_OTHER_PRICE, CONF_OTHER_PRICE_MANUAL), decision.outdoor,
            float(conf.get(CONF_COP_HIGH, 4.0)), float(conf.get(CONF_COP_LOW, 2.4)), decision.heat_need_kw,
            self.zone.get("coupled", False) or not self.zone.get("configured", False),
        )

    def allowance(self, key: str) -> tuple[float | None, str | None]:
        state = self.hass.states.get(self.conf.get(key)) if self.conf.get(key) else None
        return (self._cumulative(self.conf.get(key)), state.attributes.get("unit_of_measurement") if state else None)

    def _record(self, decision: Decision) -> None:
        if decision.external is None and self.actual is not None:
            self._agreement.append(decision.output == self.actual)
        key = (decision.reason, decision.output, decision.fault)
        if key == self._last_key:
            return
        self._last_key = key
        self.log.append({
            "time": decision.now.isoformat(),
            "reason": decision.reason.value,
            "text_hu": explain(decision, "hu", self.room_wording),
            "text_en": explain(decision, "en", self.room_wording),
            "target": decision.target,
            "indoor": decision.indoor,
            "outdoor": decision.outdoor,
            "demand": round(decision.demand * 100),
            "output": decision.output,
            "actual": self.actual,
            "fault": decision.fault,
        })

    async def _async_update_data(self) -> Decision:
        now = dt_util.now()
        inputs = self.build_inputs(now)
        self.last_inputs = inputs  # shown by the info panel
        decision = self.supervisor.step(inputs)
        self._record(decision)
        self.cost = self._compare_cost(decision)
        self._update_health(decision, now)
        self._update_rooms(decision, now)
        await self._executor.apply(decision)
        await self._apply_trvs(decision)
        if now - self._last_save >= _SAVE_EVERY:
            self._last_save = now
            await self.async_save()
        return decision

    def _groups(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        if self._room_groups is None:
            self._room_groups = group_by_room(self.hass, list(self.conf.get(CONF_ROOMS) or []))
        if self._trv_groups is None:
            self._trv_groups = group_by_room(self.hass, list(self.conf.get(CONF_ROOM_TRVS) or []))
        return self._room_groups, self._trv_groups

    def _trv_temp(self, head: str) -> float | None:
        state = self.hass.states.get(head)
        value = state.attributes.get("current_temperature") if state is not None else None
        return float(value) if isinstance(value, (int, float)) else None

    def _room_readings(self, now: datetime) -> dict[str, float | None]:
        """Room thermometers (median); a TRV room without one uses its heads' own sensors."""
        sensors, trvs = self._groups()
        out = {}
        for room, ids in sensors.items():
            values = [r.value for e in ids if (r := self._reading(e, now)).fresh(self.cfg.sensor_max_age_s) is not None]
            out[room] = room_value([v for v in values if v is not None])
        for room, heads in trvs.items():
            if room not in out:
                out[room] = room_value([t for h in heads if (t := self._trv_temp(h)) is not None])
        return out

    def _room_demand(self, now: datetime) -> list[str]:
        """Optional: TRV rooms far below the house target with an open head ask for heat."""
        _, trvs = self._groups()
        if not self.conf.get(CONF_ROOM_TRV_DEMAND) or not trvs or self.data is None:
            self.asking_rooms = []
            return []
        readings = self._room_readings(now)
        rooms = {}
        for room, heads in trvs.items():
            heating = any((s := self.hass.states.get(h)) is not None and s.attributes.get("hvac_action") == "heating"
                          for h in heads)
            rooms[room] = (readings.get(room), self.room_target(room, self.data.target), heating)
        self.asking_rooms = self.room_demand.update(now, rooms)
        return self.asking_rooms

    def room_target(self, room: str, house: float) -> float:
        """A TRV room's own target: the house target plus its offset (0.30.0)."""
        offsets = self.conf.get(CONF_TRV_OFFSETS) or {}
        try:
            return house + float(offsets.get(room, 0.0))
        except (TypeError, ValueError):
            return house

    def _room_sensor_temp(self, room: str, now: datetime) -> float | None:
        """The room's own thermometers only (not the heads) – the reference of the calibration."""
        sensors, _ = self._groups()
        values = [r.value for e in sensors.get(room, []) if (r := self._reading(e, now)).fresh(self.cfg.sensor_max_age_s) is not None]
        return room_value([v for v in values if v is not None])

    async def _apply_trvs(self, decision: Decision) -> None:
        """TRV heads get their room's target (house target + offset, + calibration) – only in active mode; a target
        set on the head by hand stays until the room's target changes."""
        _, trvs = self._groups()
        if not trvs or decision.target is None:
            return
        now = dt_util.now()
        info: dict[str, dict] = {}
        for room, heads in trvs.items():
            base = self.room_target(room, decision.target)
            room_temp = self._room_sensor_temp(room, now) if self.cfg.trv_calibration else None
            info[room] = {"target": round(base, 2), "offset": round(base - decision.target, 2), "room_temp": room_temp, "heads": {}}
            for head in heads:
                state = self.hass.states.get(head)
                attrs = state.attributes if state is not None else {}
                step = float(attrs.get("target_temp_step") or 0.5)
                cal = self.trv_cal.update(head, self._trv_temp(head), room_temp, now) if self.cfg.trv_calibration else 0.0
                room_base = round(base / step) * step
                want = round((base + cal) / step) * step
                info[room]["heads"][head] = {"calibration": cal, "want": want}
                if self.mode != MODE_ACTIVE:
                    continue
                plan = self.trv_targets.plan(head, room_base, state.state if state is not None else None,
                                             attrs.get("temperature"), attrs.get("min_temp"), attrs.get("max_temp"),
                                             want=want, now=now)
                info[room]["heads"][head]["plan"] = plan.reason
                if plan.target is None:
                    continue
                try:
                    write_log(self.hass).note(head, plan.target, dt_util.utcnow())
                    await self.hass.services.async_call("climate", "set_temperature",
                                                        {"entity_id": head, "temperature": plan.target}, blocking=True)
                    self.trv_targets.written(head, plan.target, room_base, now)
                except Exception:  # A head that does not answer must not stop the next decision.
                    _LOGGER.warning("Could not set the target of %s", head, exc_info=True)
        self.trv_info = info

    def _update_rooms(self, decision: Decision, now: datetime) -> None:
        """Single zone: the other rooms against the main thermometer; advice only, never the boiler."""
        if not self.conf.get(CONF_ROOMS) and not self.conf.get(CONF_ROOM_TRVS):
            return
        quiet = decision.reason in (Reason.REGULATING, Reason.AT_TARGET, Reason.THERMOSTAT_IDLE)
        readings = self._room_readings(now)
        self.rooms.update(now, decision.indoor, readings, quiet)
        trv_rooms = set(self._trv_groups or {})
        self.room_advice = self.rooms.advice(now, sorted(readings))
        for a in self.rooms.announcements(now, self.room_advice):
            self.hass.bus.async_fire(EVENT_ROOM_ADVICE, {
                "entry_id": self.config_entry.entry_id, "instance": self.config_entry.title, "room": a.room,
                "advice": a.advice, "deviation": a.deviation, "hours": a.hours,
                "trv": a.room in trv_rooms,
                "text_hu": room_text(a, "hu", a.room in trv_rooms), "text_en": room_text(a, "en", a.room in trv_rooms)})

    async def async_backfill_rooms(self) -> None:
        """Seed the room deviations from the hourly statistics (every hour counts here, not only quiet ones)."""
        ids = list(self.conf.get(CONF_ROOMS) or [])
        indoor = self.conf.get(CONF_INDOOR)
        if not ids or not indoor or self.rooms.hours:
            return
        try:
            from homeassistant.components.recorder import get_instance
            from homeassistant.components.recorder.statistics import statistics_during_period

            end = dt_util.now().replace(minute=0, second=0, microsecond=0)
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period, self.hass, end - timedelta(hours=72), end, set(ids) | {indoor}, "hour",
                None, {"mean"})
        except Exception:
            _LOGGER.debug("No statistics to seed the rooms from", exc_info=True)
            return
        self._room_groups = group_by_room(self.hass, ids)
        for hour_iso, room, deviation in seed_room_hours(stats, indoor, self._room_groups):
            self.rooms.add_hour(room, hour_iso, deviation)

    def _update_health(self, decision: Decision, now: datetime) -> None:
        """Boiler health from the relay and the power draw; only for a relay this supervisor knows."""
        conf = self.conf
        relay_state = self.hass.states.get(conf.get(CONF_ACTUATOR)) if conf.get(CONF_ACTUATOR) else None
        relay_on = None if relay_state is None or relay_state.state not in ("on", "off") else relay_state.state == "on"
        power = self._reading(conf.get(CONF_BOILER_POWER), now).fresh(self.cfg.sensor_max_age_s) if conf.get(CONF_BOILER_POWER) else None
        flame = self.actual if conf.get(CONF_FLAME) else None
        # a wall thermostat's own setpoint rules the room (0.38.0): the overheating check has no target to compare to
        target = None if self.cfg.demand_contact else decision.target
        self.health.update(now, relay_on, power, flame, decision.fault, decision.indoor, target,
                           busy=bool(decision.details.get("hp_mode")))

    @property
    def agreement_percent(self) -> float | None:
        if not self._agreement:
            return None
        return round(100 * sum(self._agreement) / len(self._agreement), 1)

    @property
    def is_shadow(self) -> bool:
        return self.mode == MODE_SHADOW


def seed_samples(stats: dict, energy: str, indoor: str, outdoor: str, extra: str | None,
                 energy_factor: float, extra_factor: float, window_start: float) -> list[tuple[str, float, float]]:
    """Daily heat-need samples from the daily statistics.

    A heat sensor whose statistics begin inside the window was created that day: its first day holds only
    the hours after it appeared, so it is left out (it would make the house look better insulated).
    """
    def _ts(value) -> float:
        return value.timestamp() if hasattr(value, "timestamp") else float(value) / (1000 if value > 1e11 else 1)

    by_day = {name: {_ts(row["start"]): row for row in rows} for name, rows in stats.items()}
    energy_days = sorted(by_day.get(energy, {}).items())
    if energy_days and energy_days[0][0] > window_start:
        energy_days = energy_days[1:]
    samples = []
    for start, row in energy_days:
        inside = by_day.get(indoor, {}).get(start, {}).get("mean")
        outside = by_day.get(outdoor, {}).get(start, {}).get("mean")
        if inside is None or outside is None or inside - outside < 5:
            continue
        kwh = (row.get("change") or 0.0) * energy_factor
        if extra:
            other = by_day.get(extra, {}).get(start, {}).get("change") or 0.0
            kwh += other * extra_factor
        if kwh > 0:
            day = dt_util.as_local(dt_util.utc_from_timestamp(start)).date().isoformat()
            samples.append((day, kwh, (inside - outside) * 24))
    return samples


def seed_room_hours(stats: dict, indoor: str, groups: dict[str, list[str]]) -> list[tuple[str, str, float]]:
    """Hourly (room − main) deviations from the hourly statistics; several sensors in a room by their median."""
    def _ts(value) -> float:
        return value.timestamp() if hasattr(value, "timestamp") else float(value) / (1000 if value > 1e11 else 1)

    means = {name: {_ts(r["start"]): r.get("mean") for r in rows} for name, rows in stats.items()}
    out = []
    for start, main in sorted(means.get(indoor, {}).items()):
        if main is None:
            continue
        hour_iso = dt_util.as_local(dt_util.utc_from_timestamp(start)).isoformat()
        for room, ids in groups.items():
            value = room_value([v for e in ids if (v := means.get(e, {}).get(start)) is not None])
            if value is not None:
                out.append((hour_iso, room, value - main))
    return out


"""Reads Home Assistant, asks the supervisor, logs the decision, runs the executor."""

from __future__ import annotations

from collections import deque
from datetime import datetime, time, timedelta
import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers import entity_registry as er
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
from .core.boiler_health import BoilerHealth, health_kind, power_levels_known
from .core.plausibility import Plausibility
from .core.matrix import ROOM_SOURCES, default_curve, floor_system, source_defaults
from .core.target_source import ModeWatch, TargetFollower
from .core.adapters import adapter_for
from .core.model import Reason
from .core.rooms import RoomMonitor, room_text
from .core.trv import RoomDemand, TrvCalibration, TrvTargets
from .core.room_model import (
    PRESENT, SETTLE_S, RoomControl, RoomSpec, general_windows, group_mean, presence_of,
)
from .core.cost import CostAdvice, compare
from .core.messages import explain
from .core.model import Decision, ExternalCommand, HcConfig, Inputs, Presence, Reading
from dataclasses import replace
from .core.supervisor import Supervisor
from .core.zone import coupled
from .core.load import LoadClient, LoadManager
from .executor import Executor, write_log
from .rooms_ha import area_name, group_by_room, room_specs_for, room_value
from .units import climate_attrs_c, climate_temp_c, source_value_c, state_value_c, to_system

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
HA_STARTED = f"{DOMAIN}_ha_started"
FAILSAFE_AFTER = 3  # 0.45.0: failed decisions in a row before the heat output is switched off
FAILSAFE_KEY = "hc_supervisor"  # its entry in sensor_problems (the fault binary sensor)
EXECUTOR_KEY = "hc_executor"  # 0.47.0: a part of the executor that failed (relay, flow, fan, ...)
SIDE_KEY = "hc_step"  # 0.47.0: a side step that failed (record, cost, health, rooms, trv)


def ha_started(hass) -> datetime | None:
    """When this Home Assistant started, as noted by async_setup (None: not known – the entry's load counts)."""
    data = getattr(hass, "data", None)
    return data.get(HA_STARTED) if isinstance(data, dict) else None


def note_ha_start(hass) -> None:
    """At the domain's setup: Home Assistant is starting now – or it already runs (the first instance is added
    later), then its start lies far enough back for the restart protection."""
    if HA_STARTED in hass.data:
        return
    now = dt_util.utcnow()
    running = getattr(hass, "is_running", False)
    hass.data[HA_STARTED] = now - timedelta(days=1) if running else now


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
        # 0.45.0: the restart protection counts from Home Assistant's start, not from this entry's load – an instance
        # added or reloaded (options saved) while Home Assistant runs has its sensors already and does not wait
        self._started = ha_started(hass) or dt_util.utcnow()
        self._last_save = dt_util.utcnow()
        self._last_key: tuple | None = None
        self._extra_samples: deque[tuple[datetime, float]] = deque()
        self._counted_extra = 0.0  # kWh of the other source that reached the house
        self._last_extra: float | None = None
        self.zone: dict = {}
        self.extra_kw = 0.0
        self.cost = CostAdvice("unknown")
        self.actual: bool | None = None
        # 0.45.0: the 20 W / 115 W defaults are one boiler's – only levels given in the options (or measured by the
        # wizard) judge "no response" / "no flame" by the power draw
        self.health = BoilerHealth(self.cfg, health_kind(data.get(CONF_HEAT_SOURCE)),
                                   levels_known=power_levels_known(data))
        cfg = self.cfg
        self._plaus_indoor = Plausibility(cfg.plaus_indoor_min, cfg.plaus_indoor_max, cfg.plaus_jump, cfg.plaus_confirm_s)
        self._plaus_outdoor = Plausibility(cfg.plaus_outdoor_min, cfg.plaus_outdoor_max)
        self._plaus_floor = Plausibility(0.0, 50.0, 6.0, cfg.plaus_confirm_s)  # a floor sensor inside the screed
        self._follower = TargetFollower()
        # 0.42.0: the managed thermostat (external / AC control): its integration, two-way following, pause
        self.managed = data.get(CONF_CONTROL, "tpi") in ("external", "ac") and bool(data.get(CONF_EXTERNAL))
        self.managed_platform: str | None = None
        self.adapter = adapter_for(None)
        self._managed_follower = TargetFollower()
        self._mode_watch = ModeWatch()
        self._own_seen = None  # the HC setpoint write whose echo the managed tracking has already seen
        self.adopted: dict | None = None  # {"target", "at", "how"}: the last target taken over from the thermostat
        self.paused = False
        self._paused_restored = False
        self._paused_unit: float | None = None  # AC: the unit's setpoint when the pause began
        if self.managed:
            self._detect_platform()
        self._sensor_bad_since: dict[str, datetime] = {}
        self.sensor_problems: dict[str, str] = {}  # entity → lost | stale | out_of_range | jump (after a while)
        self.step_errors = 0  # 0.45.0: failed decisions in a row (failsafe)
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
        # 0.43.0: rooms of one boiler (core/room_model.py)
        self._specs: tuple[list[RoomSpec], str | None] | None = None
        self.room_ctl: dict[str, RoomControl] = {}
        self.room_states: dict[str, dict] = {}  # room key -> what its climate and the info panel show

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
        self.trv_cal.restore(data.get("trv_cal") or {}, data.get("trv_cal_src"))
        for key, value in (data.get("room_ctl") or {}).items():
            self._ctl(key).restore(value)
        if self.managed:
            self._mode_watch.off_by_hand = bool(data.get("managed_off", False)) and self._two_way
            if "paused" in data:
                self.paused, self._paused_restored = bool(data["paused"]), True
                self._executor.paused = self.paused
            self._paused_unit = data.get("paused_unit")
            self.adopted = data.get("adopted")

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
            "trv_cal_src": dict(self.trv_cal.source),
            "room_ctl": {k: c.state() for k, c in self._ctls().items()},
            "last_extra": self._last_extra,
            **({"managed_off": self.managed_off, "paused": self.paused, "paused_unit": self._paused_unit,
                "adopted": self.adopted} if self.managed else {}),
        })

    # --- reading Home Assistant ------------------------------------------------
    def _reading(self, entity_id: str | None, now: datetime) -> Reading:
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None:
            return Reading()
        # 0.45.0: a temperature in °F (or K) is read in °C – by the sensor's unit, a weather entity's temperature_unit
        value = state_value_c(state)
        if value is None:
            return Reading()
        return Reading(value, (now - state.last_reported).total_seconds())

    def _presence(self) -> Presence:
        states = [self.hass.states.get(e) for e in self.conf.get(CONF_PRESENCE) or []]
        values = [s.state.lower() for s in states if s and s.state not in ("unknown", "unavailable")]
        if not values or any(v in _HOME for v in values):
            return Presence.HOME
        return Presence.VACATION if any(v in _VACATION for v in values) else Presence.AWAY

    def _window_ids(self) -> list[str]:
        """0.46.0: the contacts that stop the boiler – the instance's list plus the windows of the leading room and of
        the rooms without a TRV; a contact of a TRV room closes only that room's heads."""
        try:
            specs, leading = self.room_specs()
        except Exception:  # no rooms (central, tests without a hass)
            return list(self.conf.get(CONF_WINDOWS) or [])
        return general_windows(self.conf.get(CONF_WINDOWS), specs, leading)

    def _window_open(self) -> bool:
        return any(
            (s := self.hass.states.get(e)) is not None and s.state == "on"
            for e in self._window_ids()
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
        if self.managed and not conf.get(CONF_FLAME) and not conf.get(CONF_REFERENCE):
            # 0.42.0: no burner / heating signal of its own: the managed thermostat's hvac_action, read by its
            # adapter (None when the integration does not report it, e.g. Gree)
            state = self.hass.states.get(conf.get(CONF_EXTERNAL))
            if state is None or state.state in ("unknown", "unavailable"):
                return None
            return self.adapter.actual_heating(dict(state.attributes))
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
        indoor = self._plaus_indoor.check(now, self._indoor_reading(now))
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
            managed_off=self.managed_off,
            **self._unit_inputs(),
        )

    def _indoor_reading(self, now: datetime) -> Reading:
        """The house thermometer; 0.43.0: a leading room with a thermometer group gives the mean of its fresh ones."""
        main = self._reading(self.conf.get(CONF_INDOOR), now)
        lead = self.leading_spec()
        if lead is None or len(lead.sensors) < 2 or not self._explicit_rooms():
            return main
        fresh = [(r.value, r.age_s) for e in lead.sensors
                 if (r := self._reading(e, now)).fresh(self.cfg.sensor_max_age_s) is not None]
        if not fresh:
            return main
        return Reading(group_mean([v for v, _ in fresh]), min(a for _, a in fresh))

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
        # 0.44.5 (as Versatile Thermostat #2052): a window / door contact that is gone counts as closed – say so
        checks += [(e, None) for e in self._window_ids()]
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
        # 0.47.0: HC's own entries (failsafe, executor parts, side steps) are kept – each clears itself when it works
        own = {k: v for k, v in (getattr(self, "sensor_problems", None) or {}).items() if str(k).startswith("hc_")}
        self.sensor_problems = {**own, **{e: why for e, why in current.items()
                                          if (now - self._sensor_bad_since[e]).total_seconds() >= cfg.sensor_problem_after_s}}

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
            return source_value_c(self.hass, state) if state is not None else None

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

    # --- the managed thermostat (0.42.0) -------------------------------------------------------------------
    @property
    def _two_way(self) -> bool:
        """External control (not AC: there HC moves the setpoint all the time) with adopt_manual on."""
        return self.managed and self.cfg.control == "external" and self.cfg.adopt_manual

    @property
    def managed_off(self) -> bool:
        """Someone (not HC) switched the managed thermostat off: HC leaves it off (frost excepted)."""
        return self._two_way and self._mode_watch.off_by_hand

    def _detect_platform(self) -> None:
        """The integration behind the managed climate entity, from the entity registry; it picks the adapter."""
        entity = self.conf.get(CONF_EXTERNAL)
        try:
            entry = er.async_get(self.hass).async_get(entity) if entity else None
        except Exception:  # no registry (tests) – the generic adapter
            entry = None
        platform = entry.platform if entry is not None else None
        if platform is None and entity:
            platform = _platform_of_entity(self.hass, entity)  # a YAML entity without a unique_id
        self.managed_platform = platform
        self.adapter = adapter_for(self.managed_platform)
        self._executor.adapter = self.adapter

    def managed_info(self) -> dict | None:
        """For the climate attributes and the info panel."""
        if not self.managed:
            return None
        state = self.hass.states.get(self.conf.get(CONF_EXTERNAL))
        attrs = dict(state.attributes) if state is not None else {}
        sup = self.supervisor
        adopted = self.adopted if (self.adopted and sup.manual_target is not None
                                   and abs(float(self.adopted.get("target", 0)) - sup.manual_target) < 0.01) else None
        return {"entity_id": self.conf.get(CONF_EXTERNAL), "platform": self.managed_platform,
                "adapter": self.adapter.key, "adapter_name": self.adapter.name, "adapter_name_hu": self.adapter.name_hu,
                "state": state.state if state is not None else None, "target": attrs.get("temperature"),
                "hvac_action": attrs.get("hvac_action"), "adopt_manual": self._two_way,
                "paused": self.paused, "managed_off": self.managed_off, "adopted": adopted,
                "capabilities": self.adapter.describe(attrs)}

    def supervision_switch_id(self) -> str | None:
        """The entity_id of this instance's pause switch (the dial card switches it)."""
        if not self.managed:
            return None
        try:
            return er.async_get(self.hass).async_get_entity_id(
                "switch", DOMAIN, f"{self.config_entry.entry_id}_supervision_paused")
        except Exception:
            return None

    def _managed_details(self, decision: Decision) -> Decision:
        if not self.managed:
            return decision
        extra: dict = {}
        if self.paused:
            extra["paused"] = True
        a = self.adopted
        if (a and decision.manual and self.supervisor.manual_target is not None
                and abs(float(a.get("target", 0)) - self.supervisor.manual_target) < 0.01):
            extra["adopted"] = a["target"]
        return replace(decision, details={**decision.details, **extra}) if extra else decision

    def restore_paused(self, on: bool) -> None:
        """The pause switch's restored state – only when the coordinator's own store did not know it."""
        if not self._paused_restored:
            self.paused = self._executor.paused = bool(on)
            self._paused_restored = True

    async def async_set_paused(self, on: bool) -> None:
        """"HC supervision paused": nothing is written to the managed thermostat; switched off, HC takes over its
        current target as a manual target (no jump back)."""
        on = bool(on)
        if on == self.paused:
            return
        state = self.hass.states.get(self.conf.get(CONF_EXTERNAL))
        unit = climate_temp_c(self.hass, state.attributes, "temperature") if state is not None else None
        if on:
            self._paused_unit = unit
        else:
            self._adopt_on_resume(state, unit)
            self._paused_unit = None
        self.paused = self._executor.paused = on
        self._paused_restored = True
        await self.async_save()
        await self.async_request_refresh()

    def _adopt_on_resume(self, state, unit: float | None) -> None:
        if state is None or state.state in ("unknown", "unavailable") or unit is None or self.data is None:
            return
        now = dt_util.now()
        target = None
        if self.cfg.control == "ac":
            # the unit's setpoint is the room target plus the correction: a change made during the pause moves the
            # room target by as much
            if self._paused_unit is not None and abs(unit - self._paused_unit) >= 0.01:
                target = round((self.data.target + unit - self._paused_unit) * 2) / 2
        elif abs(unit - (self.adapter.fit_target(self.data.target, climate_attrs_c(self.hass, state.attributes))
                         or self.data.target)) >= 0.01:
            target = unit
        if target is not None:
            self.supervisor.manual_target = target
            self.adopted = {"target": target, "at": now.isoformat(), "how": "resume"}
        if (self._two_way and state.state == "off" and not self._mode_watch.off_by_hand
                and self.data.external is not None and self.data.external.hvac != "off"):
            self._mode_watch.off_by_hand = True  # switched off during the pause: stays off

    @callback
    def async_track_managed(self):
        """0.42.0, external control: a target or on/off set on the managed thermostat by someone else is adopted
        (target: manual until the next scheduled change; off: left off until someone switches it on). What any HC
        instance wrote there is recognised and not taken back."""
        entity = self.conf.get(CONF_EXTERNAL)
        if not self._two_way:
            return lambda: None
        follow_target = self.conf.get(CONF_TARGET_SOURCE) != entity  # else the target-source option does it
        start = self.hass.states.get(entity)
        if start is not None:
            self._managed_follower.changed(source_value_c(self.hass, start), None, False)

        @callback
        def changed(event: Event) -> None:
            old, new = event.data.get("old_state"), event.data.get("new_state")
            if new is None:
                return
            now, log = dt_util.utcnow(), write_log(self.hass)
            refresh = False
            flag = self._mode_watch.changed(old.state if old is not None else None, new.state,
                                            log.recent_mode(entity, new.state, now, consume=True))
            if flag is not None:
                refresh = True
                _LOGGER.debug("%s: %s switched %s by hand", self.config_entry.title, entity, new.state)
            if follow_target:
                v = source_value_c(self.hass, new)
                last = self._managed_follower.last
                moved = v is not None and (last is None or abs(v - last) >= 0.01)
                own = moved and log.recent(entity, v, now) and log.stamp(entity) != self._own_seen
                if own:
                    self._own_seen = log.stamp(entity)  # its echo is seen: the same value again is a hand
                current = self.data.target if self.data is not None else None
                if v is not None and current is not None and not own:
                    fitted = self.adapter.fit_target(current, climate_attrs_c(self.hass, new.attributes))
                    if fitted is not None and abs(fitted - v) < 0.01:
                        current = v  # HC's own (rounded) target, written earlier: not a hand on the knob
                target = self._managed_follower.changed(v, current, own)
                if target is not None:
                    self.supervisor.manual_target = target
                    self.adopted = {"target": target, "at": dt_util.now().isoformat(), "how": "thermostat"}
                    refresh = True
                    _LOGGER.debug("%s: target %s adopted from %s", self.config_entry.title, target, entity)
            if refresh:
                self.hass.async_create_task(self.async_request_refresh())

        return async_track_state_change_event(self.hass, [entity], changed)

    def _assist_target(self) -> float | None:
        """Air conditioner: the house target, while the house says this source is cheaper and its door is open."""
        house = self.conf.get(CONF_ASSIST) if self.cfg.control == "ac" else None
        state = self.hass.states.get(house) if house else None
        if state is None or state.state in ("off", "unavailable", "unknown"):
            return None
        a = state.attributes
        if a.get("source_advice") in ("other", "other_zone_only") and a.get("zone_door_open"):
            return climate_temp_c(self.hass, a, "temperature")  # 0.45.0: a climate shows the system unit
        return None

    def _unit_inputs(self) -> dict:
        """Air conditioner: its own reading, step and limits."""
        if self.cfg.control != "ac":
            return {}
        state = self.hass.states.get(self.conf.get(CONF_EXTERNAL) or "")
        if state is None:
            return {}
        a = climate_attrs_c(self.hass, state.attributes)  # 0.45.0: °F unit → °C (the executor writes it back in °F)
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
        key = (decision.reason, decision.output, decision.fault, bool(decision.details.get("paused")))
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
        if self.managed and self.managed_platform is None:
            self._detect_platform()  # the integration may load after HC
        try:
            # 0.47.0: reading the inputs is part of the decision – a failure there counts for the failsafe too
            inputs = self.build_inputs(now)
            self.last_inputs = inputs  # shown by the info panel
            decision = self._managed_details(self.supervisor.step(inputs))
        except Exception:
            # 0.45.0: a decision that fails again and again must not leave the heat on – the relay (or the managed
            # thermostat) is switched off after FAILSAFE_AFTER failed steps in a row, and the fault sensor says so
            decision = await self._failsafe(now)
        else:
            if self.step_errors:
                _LOGGER.warning("%s: the decision works again after %d failed step(s)", self.config_entry.title,
                                self.step_errors)
            self.step_errors = 0
            self.sensor_problems.pop(FAILSAFE_KEY, None)
        # 0.47.0: the side steps each on their own – none of them may keep the decision from the relay
        self._side("record", lambda: self._record(decision))
        self._side("cost", lambda: setattr(self, "cost", self._compare_cost(decision)))
        self._side("health", lambda: self._update_health(decision, now))
        self._side("rooms", lambda: self._update_rooms(decision, now))
        await self._executor.apply(decision)
        for part in ("cool_mode", "discharge", "fan", "external", "flow", "relay"):
            key = f"{EXECUTOR_KEY}:{part}"
            if part in getattr(self._executor, "failed", set()):
                self.sensor_problems[key] = "internal_error"
            else:
                self.sensor_problems.pop(key, None)
        try:
            await self._apply_trvs(decision)
            self.sensor_problems.pop(f"{SIDE_KEY}:trv", None)
        except Exception:
            self._side_failed("trv")
        # 0.47.0: saved at once when the output or a boost changes (a crash or a power cut lost up to 10 minutes of
        # burns – the boost resume and the flame log rely on it), else every 10 minutes
        mark = (bool(decision.output), bool(getattr(self.supervisor, "boosting", False)))
        if now - self._last_save >= _SAVE_EVERY or mark != getattr(self, "_save_mark", mark):
            self._last_save = now
            await self.async_save()
        self._save_mark = mark
        return decision

    def _side(self, name: str, fn) -> None:
        try:
            fn()
        except Exception:
            self._side_failed(name)
        else:
            self.sensor_problems.pop(f"{SIDE_KEY}:{name}", None)

    def _side_failed(self, name: str) -> None:
        key = f"{SIDE_KEY}:{name}"
        if key not in self.sensor_problems:  # once per failure streak
            _LOGGER.exception("%s: %s failed – the decision goes on", self.config_entry.title, name)
        self.sensor_problems[key] = "internal_error"

    async def _failsafe(self, now: datetime) -> Decision:
        """The supervisor raised: log it; from the FAILSAFE_AFTER-th failure in a row the heat goes off (active mode
        through the executor's usual path) until a step works again. Before that – or without a decision to base
        the off command on – the error is raised as before (the entities go unavailable for the step)."""
        self.step_errors = getattr(self, "step_errors", 0) + 1
        _LOGGER.exception("%s: the decision failed (%d in a row)", self.config_entry.title, self.step_errors)
        last = self.data
        if self.step_errors < FAILSAFE_AFTER or last is None:
            raise
        if self.step_errors == FAILSAFE_AFTER:
            _LOGGER.warning("%s: %d failed decisions in a row – the heat output is switched off for safety",
                            self.config_entry.title, self.step_errors)
        self.sensor_problems[FAILSAFE_KEY] = "internal_error"
        return replace(last, now=now, output=False, demand=0.0, fault=True, flow_setpoint=None,
                       external=ExternalCommand("off", last.target) if last.external is not None else None,
                       details={**(last.details or {}), "failsafe": self.step_errors},
                       shadow=None)

    def _groups(self) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
        if self._room_groups is None:
            self._room_groups = group_by_room(self.hass, list(self.conf.get(CONF_ROOMS) or []))
        if self._trv_groups is None:
            self._trv_groups = group_by_room(self.hass, list(self.conf.get(CONF_ROOM_TRVS) or []))
        return self._room_groups, self._trv_groups

    # --- rooms (0.43.0) --------------------------------------------------------------------------------------------
    def _explicit_rooms(self) -> bool:
        return isinstance(self.conf.get("rooms"), list) and bool(self.conf.get("rooms"))

    def room_specs(self) -> tuple[list[RoomSpec], str | None]:
        """(rooms, leading room key): the saved `rooms`, else derived from the legacy options (rooms_ha)."""
        cached = getattr(self, "_specs", None)
        if cached is None:
            if self._explicit_rooms():
                cached = room_specs_for(self.hass, self.conf)
            else:
                sensors, trvs = self._groups()
                cached = room_specs_for(self.hass, self.conf, sensors, trvs)
            self._specs = cached
        return cached

    def other_rooms(self) -> list[RoomSpec]:
        """Every room but the leading one (the host thermostat is the leading room's)."""
        specs, leading = self.room_specs()
        return [s for s in specs if s.key != leading]

    def leading_spec(self) -> RoomSpec | None:
        specs, leading = self.room_specs()
        return next((s for s in specs if s.key == leading), None)

    def all_heads(self) -> list[str]:
        return list(dict.fromkeys(h for s in self.room_specs()[0] for h in s.trvs))

    def _ctls(self) -> dict[str, RoomControl]:
        if "room_ctl" not in self.__dict__:
            self.room_ctl = {}
        return self.room_ctl

    def _ctl(self, key: str) -> RoomControl:
        return self._ctls().setdefault(key, RoomControl())

    def _spec(self, room: str) -> RoomSpec | None:
        return next((s for s in self.room_specs()[0] if room in (s.key, s.name)), None)

    def _household(self, now: datetime) -> str:
        """home | away | vacation: the host's active preset (household presence or a preset set by hand)."""
        sup = getattr(self, "supervisor", None)
        try:
            active = sup.active_preset(now) if sup is not None else "home"
        except Exception:
            active = "home"
        return active if active in ("away", "vacation") else "home"

    def _presence_obs(self, spec: RoomSpec) -> list[bool | None]:
        name = None
        if spec.area:
            try:
                name = area_name(self.hass, spec.area)
            except Exception:
                name = None
        out = []
        for entity in spec.presence:
            st = self.hass.states.get(entity)
            out.append(presence_of(st.state if st is not None else None, dict(st.attributes) if st is not None else {},
                                   entity.split(".")[0], spec.area or spec.key, name or spec.name))
        return out

    def _update_presence(self, now: datetime) -> None:
        started = getattr(self, "_started", None)
        settling = started is not None and (now - started).total_seconds() < SETTLE_S
        for spec in self.other_rooms():
            ctl = self._ctl(spec.key)
            # 0.46.0: a window of a TRV room closes the room's heads (after the window delay)
            ctl.update_window(now, bool(spec.trvs) and self._any_on(spec.windows), self.cfg.window_delay_s)
            if not spec.presence or not spec.trvs:
                ctl.presence_state = PRESENT
                continue
            ctl.presence_state = ctl.presence.update(now, self._presence_obs(spec), spec.absent_min * 60, settling)

    @callback
    def async_track_room_presence(self):
        """A presence source changes: decide at once (the 30 s step would follow anyway)."""
        ids = list(dict.fromkeys(e for s in self.other_rooms() if s.trvs for e in [*s.presence, *s.windows]))
        if not ids:
            return lambda: None

        @callback
        def changed(_event: Event) -> None:
            self.hass.async_create_task(self.async_request_refresh())

        return async_track_state_change_event(self.hass, ids, changed)

    def room_target(self, room: str, house: float) -> float:
        """A TRV room's own target (0.30.0: the house target plus its offset; 0.43.0: or its own schedule, presence,
        a manual target on its climate)."""
        spec = self._spec(room)
        if spec is None:
            offsets = self.conf.get(CONF_TRV_OFFSETS) or {}
            try:
                return house + float(offsets.get(room, 0.0))
            except (TypeError, ValueError):
                return house
        return self._room_target(spec, house, dt_util.now(), commit=False).target

    def _room_target(self, spec: RoomSpec, house: float, now: datetime, commit: bool = True):
        cfg = self.cfg
        ctl = self._ctl(spec.key)
        return ctl.target(spec, now, house, self._household(now), cfg.frost_temp, cfg.target_vacation, commit,
                          window=ctl.window_open)

    def _any_on(self, ids: list[str]) -> bool:
        return any((s := self.hass.states.get(e)) is not None and s.state == "on" for e in ids)

    # --- 0.46.0: a room's groups (its own sensor / binary sensors when it has more than one of a kind) ----------------
    def room_group_value(self, key: str, kind: str):
        """temperature: the mean of the room's fresh thermometers (the leading room: the house reading); presence:
        someone is in the room by any source (None: nothing known); window: any contact open."""
        spec = next((s for s in self.room_specs()[0] if s.key == key), None)
        if spec is None:
            return None
        now = dt_util.now()
        if kind == "temperature":
            return self._fresh_value(spec.sensors, now)
        if kind == "window":
            return self._any_on(spec.windows)
        obs = [o for o in self._presence_obs(spec) if o is not None]
        return any(obs) if obs else None

    def _trv_temp(self, head: str) -> float | None:
        state = self.hass.states.get(head)
        return climate_temp_c(self.hass, state.attributes, "current_temperature") if state is not None else None

    def trv_sources(self) -> dict[str, list[str]]:
        """Head -> the thermometers its calibration follows ([]: its own sensor)."""
        return {h: src for s in self.room_specs()[0] for h, src in s.head_sources().items()}

    def _fresh_value(self, ids: list[str], now: datetime) -> float | None:
        values = [r.value for e in ids if (r := self._reading(e, now)).fresh(self.cfg.sensor_max_age_s) is not None]
        return room_value([v for v in values if v is not None])

    def _room_reading(self, spec: RoomSpec, now: datetime) -> float | None:
        """A room's temperature: the mean of its fresh thermometers; a TRV room without one uses the thermometers
        chosen for its heads (0.42.0), else the heads' own sensors."""
        if spec.sensors:
            return self._fresh_value(spec.sensors, now)
        if not spec.trvs:
            return None
        chosen = [x for src in spec.head_sources().values() for x in src]
        value = self._fresh_value(chosen, now) if chosen else None
        return value if value is not None else room_value([t for h in spec.trvs if (t := self._trv_temp(h)) is not None])

    def _room_readings(self, now: datetime) -> dict[str, float | None]:
        """Every room but the leading one, by name."""
        return {s.name: self._room_reading(s, now) for s in self.other_rooms() if s.sensors or s.trvs}

    def _room_demand(self, now: datetime) -> list[str]:
        """Optional, per room: a TRV room far below its target with an open head asks for heat."""
        self._update_presence(now)
        rooms_allowed = [s for s in self.other_rooms() if s.trvs and s.demand]
        if not rooms_allowed or self.data is None:
            self.asking_rooms = []
            self.room_demand.update(now, {})
            return []
        rooms = {}
        for spec in rooms_allowed:
            heating = any((s := self.hass.states.get(h)) is not None and s.attributes.get("hvac_action") == "heating"
                          for h in spec.trvs)
            rt = self._room_target(spec, self.data.target, now, commit=False)
            rooms[spec.name] = (self._room_reading(spec, now), rt.target if rt.reason != "off" else None, heating)
        self.asking_rooms = self.room_demand.update(now, rooms)
        return self.asking_rooms

    def _room_sensor_temp(self, room: str, now: datetime) -> float | None:
        """The room's own thermometers only (not the heads) – the reference of the legacy calibration."""
        spec = self._spec(room)
        return self._fresh_value(spec.sensors, now) if spec is not None else None

    async def _apply_trvs(self, decision: Decision) -> None:
        """Every room: its target and state (for its climate); TRV heads get their room's target (+ calibration) –
        written only in active mode; a target set on the head by hand stays until the room's target changes."""
        specs, leading = self.room_specs()
        if decision.target is None:
            return
        if not specs:
            self.trv_info, self.room_states = {}, {}
            return
        now = dt_util.now()
        house = decision.target
        info: dict[str, dict] = {}
        states: dict[str, dict] = {}
        advice = {a.room: a for a in getattr(self, "room_advice", [])}
        asking = set(getattr(self, "asking_rooms", []))
        for spec in specs:
            is_lead = spec.key == leading
            temp = decision.indoor if is_lead else self._room_reading(spec, now)
            a = advice.get(spec.name)
            common = {"key": spec.key, "name": spec.name, "area": spec.area, "leading": is_lead, "trv": spec.has_trv,
                      "temperature": round(temp, 2) if temp is not None else None, "sensors": list(spec.sensors),
                      "house_target": house, "mode": spec.mode, "offset": spec.offset, "windows": list(spec.windows),
                      "advice": {"advice": a.advice, "deviation": a.deviation, "hours": a.hours} if a else None}
            if not spec.trvs:
                states[spec.key] = {**common, "target": house, "reason": "leading" if is_lead else "house",
                                    "heating": bool(decision.output), "presence": None}
                continue
            if is_lead:
                base, reason, presence = house, "leading", None
            else:
                rt = self._room_target(spec, house, now)
                base, reason = rt.target, rt.reason
                presence = self._ctl(spec.key).presence_state if spec.presence else None
            info[spec.name] = {"target": round(base, 2), "offset": round(base - house, 2), "room_temp": None,
                               "heads": {}, "key": spec.key, "reason": reason}
            heating = False
            for head in spec.trvs:
                state = self.hass.states.get(head)
                native = state.attributes if state is not None else {}
                attrs = climate_attrs_c(self.hass, native)  # 0.45.0: in °C (a °F system shows °F)
                heating = heating or attrs.get("hvac_action") == "heating"
                step = float(attrs.get("target_temp_step") or 0.5)
                ref_ids = spec.head_sources().get(head, [])  # [] : its own sensor, no calibration
                self.trv_cal.set_source(head, ref_ids)
                ref = self._fresh_value(ref_ids, now) if ref_ids else None
                if ref is not None and info[spec.name]["room_temp"] is None:
                    info[spec.name]["room_temp"] = ref
                cal = self.trv_cal.update(head, self._trv_temp(head), ref, now) if ref_ids else 0.0
                room_base = round(base / step) * step
                want = round((base + cal) / step) * step
                ref_st = self.hass.states.get(ref_ids[0]) if len(ref_ids) == 1 else None
                info[spec.name]["heads"][head] = {"sensor": ref_ids[0] if len(ref_ids) == 1 else (ref_ids or "head"),
                                                  **({"sensor_name": ref_st.attributes.get("friendly_name", ref_ids[0])}
                                                     if ref_st is not None else {}),
                                                  "sensor_temp": ref, "head_temp": self._trv_temp(head),
                                                  "calibration": cal, "want": want,
                                                  "state": state.state if state is not None else None,
                                                  "head_target": attrs.get("temperature")}
                if self.mode != MODE_ACTIVE:
                    continue
                plan = self.trv_targets.plan(head, room_base, state.state if state is not None else None,
                                             attrs.get("temperature"), attrs.get("min_temp"), attrs.get("max_temp"),
                                             want=want, now=now)
                info[spec.name]["heads"][head]["plan"] = plan.reason
                if plan.target is None:
                    continue
                try:
                    value = to_system(self.hass, plan.target, native.get("target_temp_step"))
                    write_log(self.hass).note(head, value, dt_util.utcnow())
                    await self.hass.services.async_call("climate", "set_temperature",
                                                        {"entity_id": head, "temperature": value}, blocking=True)
                    self.trv_targets.written(head, plan.target, room_base, now)
                except Exception:  # A head that does not answer must not stop the next decision.
                    _LOGGER.warning("Could not set the target of %s", head, exc_info=True)
            ctl = self._ctl(spec.key)
            states[spec.key] = {**common, "target": round(base, 2), "reason": reason, "heating": heating,
                                "presence": presence, "presence_sources": list(spec.presence), "window": ctl.window_open,
                                "absent_since": ctl.presence.absent_since.isoformat() if ctl.presence.absent_since else None,
                                "enabled": ctl.enabled, "manual": ctl.manual, "preset": ctl.preset,
                                "demand_allowed": spec.demand, "asking": spec.name in asking,
                                "heads": info[spec.name]["heads"]}
        self.trv_info = info
        self.room_states = states

    def _update_rooms(self, decision: Decision, now: datetime) -> None:
        """Single zone: the other rooms against the main thermometer; advice only, never the boiler."""
        others = [s for s in self.other_rooms() if s.sensors or s.trvs]
        if not others:
            return
        quiet = decision.reason in (Reason.REGULATING, Reason.AT_TARGET, Reason.THERMOSTAT_IDLE)
        readings = self._room_readings(now)
        self.rooms.update(now, decision.indoor, readings, quiet)
        trv_rooms = {s.name for s in others if s.trvs}
        self.room_advice = self.rooms.advice(now, sorted(readings))
        for a in self.rooms.announcements(now, self.room_advice):
            self.hass.bus.async_fire(EVENT_ROOM_ADVICE, {
                "entry_id": self.config_entry.entry_id, "instance": self.config_entry.title, "room": a.room,
                "advice": a.advice, "deviation": a.deviation, "hours": a.hours,
                "trv": a.room in trv_rooms,
                "text_hu": room_text(a, "hu", a.room in trv_rooms), "text_en": room_text(a, "en", a.room in trv_rooms)})

    async def async_backfill_rooms(self) -> None:
        """Seed the room deviations from the hourly statistics (every hour counts here, not only quiet ones)."""
        groups = {s.name: list(s.sensors) for s in self.other_rooms() if s.sensors}
        ids = sorted({e for v in groups.values() for e in v})
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
        for hour_iso, room, deviation in seed_room_hours(stats, indoor, groups):
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


def _platform_of_entity(hass, entity_id: str) -> str | None:
    """The integration of a climate entity that has no registry entry (YAML without a unique_id)."""
    try:
        from homeassistant.components.climate import DATA_COMPONENT
        component = hass.data.get(DATA_COMPONENT)
        ent = component.get_entity(entity_id) if component is not None else None
        platform = getattr(ent, "platform", None)
        return getattr(platform, "platform_name", None)
    except Exception:
        return None


def _float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    """Hourly (room − main) deviations from the hourly statistics; several sensors in a room by their mean (0.43.0)."""
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


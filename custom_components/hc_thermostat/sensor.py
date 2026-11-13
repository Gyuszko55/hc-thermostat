"""The decision with its reason, the demand and the shadow comparison."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE, UnitOfPower

from .const import CONF_BOILER_LIMIT, CONF_OTHER_LIMIT, CONF_ROLE, CONF_ROOM_TRVS, CONF_ROOMS
from .core.cost import ADVICE_TEXT
from .core.messages import explain
from .core.boiler_health import STATES as HEALTH_STATES
from .core.learning import band
from .core.model import Reason
from .entity import HcEntity
from .room_groups import RoomTemperatureGroup, groups_of, remove_old_groups


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    c = entry.runtime_data
    if entry.data.get(CONF_ROLE) == "central":
        async_add_entities([HcCentralDecision(c)])
        return
    if entry.data.get(CONF_ROLE) == "buffer":
        async_add_entities([HcBufferDecision(c)])
        return
    entities = [HcDecision(c), HcHeatNeed(c), HcHeatLoss(c), HcSourceAdvice(c)]
    if c.cfg.control not in ("external", "ac"):
        entities += [HcDemandPercent(c), HcAgreement(c), HcLearned(c)]
        if c.conf.get("heat_source") != "external_heat":  # 0.47.0: no burner of its own to watch
            entities.append(HcBoilerHealth(c))
        if c.cfg.control == "curve":
            entities.append(HcFlowSetpoint(c))
        if c.cfg.shadow_regulator:
            entities.append(HcShadowRegulator(c))
    if c.conf.get(CONF_ROOMS) or c.conf.get(CONF_ROOM_TRVS):
        entities.append(HcRooms(c))
    # 0.46.0: a room with two or more thermometers gets its group (the mean HC regulates by)
    groups = [RoomTemperatureGroup(c, s) for s, _ in groups_of(c, ("temperature",))]
    remove_old_groups(hass, entry, "sensor", {g.unique_id for g in groups})
    async_add_entities(entities + groups)


class HcDecision(HcEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [r.value for r in Reason]
    # 0.45.0: the last 20 decisions are in the state (cards read them there) – not again in the history every 30 s
    _unrecorded_attributes = frozenset({"log"})

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "decision")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.reason.value

    @property
    def extra_state_attributes(self) -> dict:
        c, d = self.coordinator, self.coordinator.data
        return {
            "explanation": explain(d, c.hass.config.language, c.room_wording),
            "mode": c.mode,
            "target": d.target,
            "indoor": d.indoor,
            "outdoor": d.outdoor,
            "limited_by": d.limited_by,
            "actual_heating": c.actual,
            "log": list(c.log)[-20:],
            **({"ac": {k: d.details.get(k) for k in ("ac_mode", "aim", "setpoint", "offset", "integral", "unit_temp", "assist")}}
               if d.details and "setpoint" in d.details else {}),
        }


class HcHeatNeed(HcEntity, SensorEntity):
    """What the house loses now at the target temperature: the heating has to replace this."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "heat_need")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.heat_need_kw

    @property
    def extra_state_attributes(self) -> dict:
        c, d = self.coordinator, self.coordinator.data
        return {
            "zone_configured": c.zone.get("configured", False),
            "zone_coupled": c.zone.get("coupled", False),
            "zone_door_open": c.zone.get("door_open", False),
            "zone_temp": c.zone.get("temp"),
            "extra_source_kw": round(c.extra_kw, 2),
            "other_sources_kw": round(d.other_heat_kw, 2),
            "boiler_share_kw": None if d.heat_need_kw is None else round(max(d.heat_need_kw - d.other_heat_kw, 0.0), 2),
        }


class HcHeatLoss(HcEntity, SensorEntity):
    """Learned loss factor of the house."""

    _attr_native_unit_of_measurement = "W/K"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "heat_loss")

    @property
    def native_value(self) -> float | None:
        loss = self.coordinator.data.loss_kw_per_k
        return None if loss is None else loss * 1000

    @property
    def extra_state_attributes(self) -> dict:
        return {"days_learned": len(self.coordinator.supervisor.heat_need.samples)}


class HcSourceAdvice(HcEntity, SensorEntity):
    """Which source gives the cheaper heat now. Advice only, it switches nothing."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = list(ADVICE_TEXT)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "source_advice")

    @property
    def native_value(self) -> str:
        return self.coordinator.cost.advice

    @property
    def extra_state_attributes(self) -> dict:
        c, a = self.coordinator, self.coordinator.cost
        lang = "hu" if c.hass.config.language.startswith("hu") else "en"
        boiler_left, boiler_unit = c.allowance(CONF_BOILER_LIMIT)
        other_left, other_unit = c.allowance(CONF_OTHER_LIMIT)
        return {
            "explanation": ADVICE_TEXT[a.advice][lang],
            "boiler_cost_per_kwh": a.boiler_cost,
            "other_cost_per_kwh": a.other_cost,
            "cop": a.cop,
            "breakeven_outdoor": a.breakeven_outdoor,
            "other_always_cheaper": a.other_always,
            "saving_per_hour": a.saving_per_hour,
            "boiler_allowance_left": boiler_left,
            "boiler_allowance_unit": boiler_unit,
            "other_allowance_left": other_left,
            "other_allowance_unit": other_unit,
        }


class HcDemandPercent(HcEntity, SensorEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "demand")

    @property
    def native_value(self) -> int:
        return round(self.coordinator.data.demand * 100)


class HcAgreement(HcEntity, SensorEntity):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "agreement")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.agreement_percent


class HcLearned(HcEntity, SensorEntity):
    """What the supervisor learned about this house; the state is the after-heat for today's outdoor band."""

    _attr_native_unit_of_measurement = "°C"
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "learned")

    @property
    def native_value(self) -> float:
        return self.coordinator.supervisor.learner.afterheat(self.coordinator.data.outdoor)

    @property
    def extra_state_attributes(self) -> dict:
        learner = self.coordinator.supervisor.learner
        learned = learner.learned
        return {
            "learning_enabled": bool(self.coordinator.cfg.learning_enabled),
            "outdoor_band": band(self.coordinator.data.outdoor),
            "afterheat": learned.afterheat,
            "minutes_per_degree": learned.minutes_per_degree,
            "trim": learner.trim,
            "tpi_coef_int": learner.tpi_coef_int,
            "tpi_offset_percent": round(learner.tpi_offset * 100, 1),
            "boosts_learned": learned.boosts,
            "days_learned": learned.days,
            "last_boost": learned.last_boost,
        }


class HcBoilerHealth(HcEntity, SensorEntity):
    """Boiler health from the relay and the power draw: ok, no_data, no_response, no_flame, heating_fault, short_cycling."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = HEALTH_STATES
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "boiler_health")

    @property
    def native_value(self) -> str:
        return self.coordinator.health.state

    @property
    def extra_state_attributes(self) -> dict:
        return self.coordinator.health.attributes()


class HcShadowRegulator(HcEntity, SensorEntity):
    """The other regulator (PID next to TPI): what it would ask for; it switches nothing."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:chart-bell-curve-cumulative"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "shadow_regulator")

    @property
    def native_value(self) -> float | None:
        shadow = self.coordinator.data.shadow
        return round(shadow["demand"] * 100) if shadow else None

    @property
    def extra_state_attributes(self) -> dict:
        shadow = self.coordinator.data.shadow or {}
        stats = self.coordinator.supervisor.shadow_stats
        return {
            "control": shadow.get("control"),
            "would_heat": shadow.get("output"),
            "integral": shadow.get("integral"),
            "today_shadow_min": round(stats["shadow_on_s"] / 60),
            "today_live_min": round(stats["live_on_s"] / 60),
            "yesterday": stats.get("yesterday"),
        }


class HcFlowSetpoint(HcEntity, SensorEntity):
    """Heating curve (EXPERIMENTAL): the flow temperature asked for; none while the heat source is off."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:thermometer-water"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "flow_setpoint")

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.flow_setpoint

    @property
    def extra_state_attributes(self) -> dict:
        sup = self.coordinator.supervisor
        d = self.coordinator.data
        return {"experimental": True, "curve_only": round(sup.curve.base(d.target, d.outdoor), 1) if d.outdoor is not None else None,
                "room_integral": round(sup.curve.integral, 2)}


class HcBufferDecision(HcEntity, SensorEntity):
    """Buffer tank (0.33.0): whether the heat source charges the tank, and why."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["charging", "full", "ready", "waiting_demand", "min_off", "frost", "no_sensor", "max_charge"]
    _attr_icon = "mdi:storage-tank"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "buffer_decision")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.reason

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"mode": self.coordinator.mode, "source": d.output, "top": d.top, "bottom": d.bottom,
                "asking": list(d.asking), **d.details}


class HcCentralDecision(HcEntity, SensorEntity):
    """Central boiler: why the boiler runs or not, which zones ask and whose valves are open."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["no_demand", "waiting_valves", "heating", "min_on", "min_off", "valves_closed"]
    _attr_icon = "mdi:water-boiler"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "central_decision")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.reason

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"mode": self.coordinator.mode, "asking": list(d.asking), "open": list(d.open_zones),
                "demand_sum": d.demand, "boiler": d.output, "faulty": [z.name for z in self.coordinator.zones if z.fault],
                "stuck": list(d.details.get("stuck", [])),
                "pump": d.pump, "pump_until": d.details.get("pump_until"),
                "flow_setpoint": d.flow_setpoint, "flow_by": d.details.get("flow_by"),
                "flow_capped_by": d.details.get("flow_capped_by"),
                "flow_requests": d.details.get("flow_requests", {}),
                **self._exercise()}

    def _exercise(self) -> dict:
        """Weekly pump exercise (0.39.0): running now and until when, the next one, when the pump last ran."""
        c, d = self.coordinator, self.coordinator.data
        if not c.central.has_pump:
            return {}
        ex = c.central.exercise
        nxt = ex.next_run(d.now)
        return {"pump_exercise": bool(d.details.get("pump_exercise")), "pump_exercise_until": d.details.get("pump_exercise_until"),
                "pump_exercise_next": nxt.isoformat() if nxt else None,
                "pump_last_run": ex.last_run.isoformat() if ex.last_run else None}


class HcRooms(HcEntity, SensorEntity):
    """Single zone: how many rooms need their radiator valve turned (down or up); details per room."""

    _attr_icon = "mdi:home-thermometer"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset({"trv_rooms"})  # 0.45.0: per-head live details, in the state only

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "rooms")

    @property
    def native_value(self) -> int:
        return sum(1 for a in self.coordinator.room_advice if a.advice in ("down", "up"))

    @property
    def extra_state_attributes(self) -> dict:
        c = self.coordinator
        trv_rooms = {r.name: list(r.trvs) for r in c.other_rooms() if r.trvs}
        lead = c.leading_spec()
        return {"tolerance": c.rooms.tolerance, "asking": list(c.asking_rooms), "trv_rooms": c.trv_info,
                "leading_room": lead.name if lead is not None else None,
                "rooms": {a.room: {"advice": a.advice, "deviation": a.deviation, "hours": a.hours,
                                   "trv": trv_rooms.get(a.room, [])}
                          for a in c.room_advice}}


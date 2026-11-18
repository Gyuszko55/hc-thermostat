"""Would it heat now, and is there a fault."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity

from .const import CONF_ROLE
from .entity import HcEntity
from .room_groups import RoomBinaryGroup, groups_of, remove_old_groups


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    c = entry.runtime_data
    if entry.data.get(CONF_ROLE) == "buffer":
        async_add_entities([HcCentralBoiler(c, "buffer_source")])
        return
    if entry.data.get(CONF_ROLE) == "central":
        async_add_entities([HcCentralBoiler(c), HcCentralPump(c)])
        return
    if entry.data.get(CONF_ROLE) == "circuit":  # 0.54.0
        async_add_entities([HcCircuitDemand(c)])
        return
    if entry.data.get(CONF_ROLE) == "hp_coord":  # 0.55.0
        async_add_entities([HcHpEnable(c), HcHpHeatDemand(c), HcHpSummer(c), HcHpExercise(c), HcHpWriteProblem(c)])
        return
    entities = [HcDemand(c), HcFault(c)]
    # 0.48.0: a measurement with a limit (pressure, fuel, a fault code, a radiator…) gets the problem sensor too
    if (c.cfg.control not in ("external", "ac") and c.conf.get("heat_source") != "external_heat") or c.measure_keys():
        entities.append(HcBoilerProblem(c))
    # 0.46.0: a room with two or more presence sources / window contacts gets its group
    groups = [RoomBinaryGroup(c, s, k) for s, k in groups_of(c, ("presence", "window"))]
    remove_old_groups(hass, entry, "binary_sensor", {g.unique_id for g in groups})
    async_add_entities(entities + groups)


class HcDemand(HcEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "heat_decision")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.output


class HcFault(HcEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "fault")

    @property
    def is_on(self) -> bool:
        # 0.23.0: also a missing, silent or unbelievable sensor (indoor, outdoor, flame)
        return self.coordinator.data.fault or bool(self.coordinator.sensor_problems)

    @property
    def extra_state_attributes(self) -> dict:
        since = getattr(self.coordinator, "degraded_since", None)
        return {"heating_fault": self.coordinator.data.fault, "sensors": dict(self.coordinator.sensor_problems),
                "degraded_since": since.isoformat() if since else None}  # 0.51.1


class HcBoilerProblem(HcEntity, BinarySensorEntity):
    """On when the boiler health is not ok (see the boiler health sensor for which problem)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "boiler_problem")

    @property
    def is_on(self) -> bool:
        return self.coordinator.health.problem or bool(self.coordinator.measure_problems)

    @property
    def extra_state_attributes(self) -> dict:
        return {"health": self.coordinator.health.state, "measurements": list(self.coordinator.measure_problems)}


class HcCentralBoiler(HcEntity, BinarySensorEntity):
    """Central boiler: on when the boiler should run (in shadow mode it is not switched)."""

    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator, key: str = "central_boiler") -> None:
        super().__init__(coordinator, key)

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.output


class HcCentralPump(HcEntity, BinarySensorEntity):
    """Central boiler: on when the pump should run – with the boiler and in its overrun."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:pump"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "central_pump")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.pump

    @property
    def extra_state_attributes(self) -> dict:
        return {"overrun_until": self.coordinator.data.details.get("pump_until")}


class HcCircuitDemand(HcEntity, BinarySensorEntity):
    """Mixing circuit (0.54.0): a lasting demand – a zone asked for heat within the hold time (not one TPI pulse)."""

    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "circuit_demand")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.demand

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"lasting": list(d.lasting), "asking_now": list(d.asking),
                "hold_s": self.coordinator.circuit.cfg.circuit_hold_s}


class HcHpEnable(HcEntity, BinarySensorEntity):
    """Heat pump coordination (0.55.0, shadow): the ON/OFF HC would ask of the unit – a request, not a sign that it runs."""

    _attr_icon = "mdi:power"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hp_enable")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.enable

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"mode": self.coordinator.write.status(d.now), "reason": d.reason, "cold_on": d.cold_on,
                "written": self.coordinator.out_switch.info()}


class HcHpHeatDemand(HcEntity, BinarySensorEntity):
    """Heat pump coordination (0.55.0): heat should be made now (for the circuits or the tank)."""

    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hp_heat_demand")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.heat_demand

    @property
    def extra_state_attributes(self) -> dict:
        d = self.coordinator.data
        return {"need": d.need, "wood": d.wood, "top": d.details.get("top"), "charge": d.details.get("charge")}


class HcHpSummer(HcEntity, BinarySensorEntity):
    """Heat pump coordination (0.57.0): automatic summer mode – the house has not asked for heat for a long time."""

    _attr_icon = "mdi:weather-sunny"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hp_summer")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.summer

    @property
    def extra_state_attributes(self) -> dict:
        d, cfg = self.coordinator.data, self.coordinator.hp.cfg
        return {"enabled": cfg.hp_auto_summer, "summer_since": d.details.get("summer_since"),
                "room_idle_hours": d.details.get("room_idle_hours"), "summer_after_h": cfg.hp_summer_after_h,
                "demand_held_s": d.details.get("demand_held_s"), "winter_after_s": cfg.hp_winter_after_s,
                "written": self.coordinator.out_summer.info()}


class HcHpExercise(HcEntity, BinarySensorEntity):
    """Heat pump coordination (0.57.0): pump / valve exercise due (summer mode, weekly) – the PLC runs it."""

    _attr_icon = "mdi:cog-refresh"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hp_exercise")

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.exercise

    @property
    def extra_state_attributes(self) -> dict:
        cfg = self.coordinator.hp.cfg
        return {"enabled": cfg.hp_exercise, "weekday": int(cfg.hp_exercise_weekday), "hour": int(cfg.hp_exercise_hour),
                "minutes": cfg.hp_exercise_min, "written": self.coordinator.out_exercise.info()}


class HcHpWriteProblem(HcEntity, BinarySensorEntity):
    """0.73.0: the heat pump does not take what HC asks for. With the supervised restore on: every restore failed;
    with it off: a conflict or a value the device did not accept (HC stopped writing it)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hp_write_problem")

    def _outs(self):
        c = self.coordinator
        return [o for o in (c.out_target, c.out_switch, c.out_demand, c.out_summer, c.out_exercise) if o.entity_id]

    @staticmethod
    def _bad(o) -> bool:
        if o.guard.restore_after_s > 0:
            return o.status == "failed"
        return o.status in ("conflict", "not_accepted")

    @property
    def is_on(self) -> bool:
        return any(self._bad(o) for o in self._outs())

    @property
    def extra_state_attributes(self) -> dict:
        return {"outputs": {o.entity_id: {"status": o.status, "restores": o.guard.restore_count,
                                           "value": o.read()[0], "asked": o.guard.failed_want if o.guard.failed else o.guard.last_value}
                            for o in self._outs()},
                "restore_min": round(self.coordinator.out_target.guard.restore_after_s / 60) or None,
                # 0.73.0: warning – a difference, a restore under way; error – every restore failed
                "level": "error" if self.is_on else "warning" if any(
                    o.status in ("conflict", "not_accepted", "restore") or o.guard.restore_count for o in self._outs()) else "ok"}

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
    entities = [HcDemand(c), HcFault(c)]
    if c.cfg.control not in ("external", "ac"):
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
        return {"heating_fault": self.coordinator.data.fault, "sensors": dict(self.coordinator.sensor_problems)}


class HcBoilerProblem(HcEntity, BinarySensorEntity):
    """On when the boiler health is not ok (see the boiler health sensor for which problem)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "boiler_problem")

    @property
    def is_on(self) -> bool:
        return self.coordinator.health.problem

    @property
    def extra_state_attributes(self) -> dict:
        return {"health": self.coordinator.health.state}


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

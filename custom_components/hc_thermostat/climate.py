"""The thermostat of the supervisor. In shadow mode it changes no device."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.util import dt as dt_util

from .const import CONF_ROLE, CONF_VALVE_FEEDBACK, PRESETS
from .core.curve import flow_request, zone_flow_limit
from .core.model import Reason
from .core.regulators import controller_attributes
from .entity import HcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([HcClimate(entry.runtime_data)])


class HcClimate(HcEntity, ClimateEntity):
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "thermostat")

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.indoor

    @property
    def target_temperature(self) -> float:
        return self.coordinator.data.target

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.coordinator.enabled else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if not self.coordinator.enabled:
            return HVACAction.OFF
        data = self.coordinator.data
        if data.reason == Reason.VALVE_EXERCISE:
            return HVACAction.IDLE  # the valve is only exercised: a central boiler must not start for it
        if data.external is not None and data.external.hvac == "cool":
            return HVACAction.COOLING
        if (data.details or {}).get("mode") == "cool":  # floor cooling (0.29.0)
            return HVACAction.COOLING if data.output else HVACAction.IDLE
        return HVACAction.HEATING if data.output else HVACAction.IDLE

    @property
    def preset_modes(self) -> list[str]:
        enabled = set(self.coordinator.cfg.presets_enabled)
        return [p for p in PRESETS if p == "auto" or p in enabled]

    @property
    def preset_mode(self) -> str:
        sup = self.coordinator.supervisor
        if sup.boosting:
            return "boost"
        return sup.preset or "auto"

    @property
    def extra_state_attributes(self) -> dict:
        data, sup = self.coordinator.data, self.coordinator.supervisor
        return {
            "hc_mode": self.coordinator.mode,
            "demand": round(data.demand * 100),  # read by a central boiler instance
            "fault": data.fault,
            "valve_feedback": self.coordinator.conf.get(CONF_VALVE_FEEDBACK),  # read by a central boiler
            "valve_exercising": data.reason == Reason.VALVE_EXERCISE,  # read by a central boiler (pump exercise)
            "valve_exercise_next": (n.isoformat() if (n := sup.exercise.next_run(dt_util.now())) else None),
            "control_type": self.coordinator.cfg.control,
            "flow_request": self._flow_request(),  # read by a central modulating boiler
            "flow_limit": zone_flow_limit(self.coordinator.conf, self.coordinator.cfg),  # ... its cap for this zone
            "heat_type": heat_type(self.coordinator.conf),  # icon hint for cards: boiler, floor, heat pump, AC
            "source_advice": self.coordinator.cost.advice,  # read by an air conditioner instance that may help
            "zone_door_open": self.coordinator.zone.get("door_open"),
            "zone_coupled": self.coordinator.zone.get("coupled"),
            "manual_target": data.target if data.manual else None,
            "manual_until": data.manual_until.isoformat() if data.manual_until else None,
            "preset_until": sup.preset_until.isoformat() if sup.preset_until else None,
            "preset_until_home": sup.preset_until_home,
            "preset_end_preview": sup.preset_end_preview(self.preset_modes, dt_util.now()),
            **controller_attributes(self.coordinator.cfg, sup, data.demand, dt_util.now()),
            **self._floor_attributes(),
        }

    def _floor_attributes(self) -> dict:
        """The floor limit in effect (0.37.0); floor tempering (0.35.0): whether it heats for the floor now, the floor
        target."""
        cfg, data = self.coordinator.cfg, self.coordinator.data
        out = {"floor_limit": cfg.floor_limit} if cfg.floor_system and cfg.floor_limit > 0 else {}  # 0.37.0: in effect
        if cfg.floor_temper:
            out.update(floor_tempering=data.reason == Reason.FLOOR_TEMPER,
                       floor_target=(data.details or {}).get("floor_target"))
        return out

    def _flow_request(self) -> float | None:
        """Zone of a central modulating boiler: the flow its own curve asks for while it wants heat."""
        data = self.coordinator.data
        if self.coordinator.conf.get(CONF_ROLE) != "zone" or not data.output:
            return None
        if data.flow_setpoint is not None:  # a zone on its own curve already knows it
            return data.flow_setpoint
        return flow_request(self.coordinator.cfg, data.target, data.indoor, data.outdoor)

    async def async_set_temperature(self, **kwargs) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self.coordinator.supervisor.manual_target = float(temperature)
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT and not self.coordinator.enabled:
            self.coordinator.supervisor.new_cycle()  # Switched on: start now, not at the old cycle phase.
        self.coordinator.enabled = hvac_mode == HVACMode.HEAT
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self.coordinator.supervisor.set_preset(preset_mode, dt_util.now())
        await self.coordinator.async_request_refresh()


def heat_type(conf: dict) -> str:
    """The kind of heat for cards (hc-dial-card heat_type): from the heat source and the system."""
    source, system = conf.get("heat_source"), conf.get("system") or ""
    if source == "air_conditioner":
        return "air_conditioner"
    if source == "heat_pump":
        return "heat_pump"
    if source in ("electric_boiler", "electric_heater", "storage_heater"):
        return "electric"
    if system.startswith("floor"):
        return "floor"
    return "gas_boiler"


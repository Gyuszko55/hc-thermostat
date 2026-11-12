"""Setup: heat source and hydraulics pick a matrix cell; a new entry always starts in shadow mode."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    BooleanSelector, EntitySelector, EntitySelectorConfig, NumberSelector, NumberSelectorConfig,
    NumberSelectorMode, SelectSelector, SelectSelectorConfig, SelectSelectorMode, TextSelector, TimeSelector,
)

from .const import (
    CONF_ACTUATOR, CONF_KEEP_ALIVE_SCRIPT, CONF_BOILER_LIMIT, CONF_BOILER_PRICE, CONF_BOILER_PRICE_MANUAL, CONF_COP_HIGH, CONF_COP_LOW,
    CONF_OTHER_LIMIT, CONF_OTHER_PRICE, CONF_OTHER_PRICE_MANUAL, CONF_CONFIRM, CONF_CONTROL, CONF_ENERGY_FACTOR, CONF_EXTERNAL, CONF_EXTRA_FACTOR, CONF_EXTRA_HEAT, CONF_HEAT_ENERGY, CONF_HEAT_SOURCE, CONF_INDOOR, CONF_MODE,
    CONF_OUTDOOR, CONF_PRESENCE, CONF_REFERENCE, CONF_SYSTEM, CONF_WINDOWS, CONF_FLAME, CONF_WINDOW_DROP, CONF_BOILER_POWER, CONF_FLOW, CONF_HEAT_ENABLE, CONF_ZONE_DIFF, CONF_ZONE_DOORS, CONF_ZONE_TEMP, CONF_ROLE, ROLES, CONF_ZONES, CONF_BOILER, CONF_PUMP, CONF_VALVE_FEEDBACK, CONF_HUMIDITY, CONF_COOL_MODE, CONF_COOL_FLOW, CONF_POWER_AVAILABLE, CONF_DISCHARGE, CONF_FAN, CONF_COIL, CONF_RETURN, CONF_BUFFER_TOP, CONF_BUFFER_BOTTOM, DOMAIN, EXPIRY, MODE_ACTIVE, MODE_SHADOW, PRESETS, TIMED_PRESETS,
    CONF_ROOMS, CONF_ROOM_TOL, CONF_ROOM_TRVS, CONF_ROOM_TRV_DEMAND, CONF_TRV_OFFSETS, CONF_TRV_SENSORS, TRV_HEAD, CONF_ASSIST, CONF_FLOOR, CONF_TARGET_SOURCE,
    CONF_HP_DEFROST, CONF_HP_DHW, CONF_DEMAND, CONF_HOME_NAME,
)
from .core.matrix import (
    ELECTRIC_SOURCES, SOURCES, SYSTEMS, Status, cell, controls, curve_supported, default_curve, default_timing, electric_floor,
    own_control_supported, source_defaults,
)
from .core.floor import COVERINGS, PROBES, covering_of
from .core.model import HcConfig
from .core.boiler_health import power_levels_known
from .core.buffer import BufferConfig
from .core.room_model import OWN, rooms_options
from . import room_form as rf
from .rooms_ha import (
    area_id_of, areas_of_other_instances, excluded_climates, heads_of_other_instances, room_specs_for, rooms_candidates,
)

# 0.46.0: what the rooms menu item saves – the settings path keeps these as they are
ROOM_OPTION_KEYS = ("rooms", "leading_room", "room_sensors", "room_trvs", "trv_sensors", "trv_offsets",
                    "room_trv_demand", CONF_INDOOR, CONF_HOME_NAME, CONF_ROOM_TOL)


def _select(options, key: str) -> SelectSelector:
    return SelectSelector(SelectSelectorConfig(
        options=list(options), translation_key=key, mode=SelectSelectorMode.DROPDOWN))


def _entity(*domains: str, multiple: bool = False) -> EntitySelector:
    return EntitySelector(EntitySelectorConfig(domain=list(domains), multiple=multiple))


# Entity pickers narrowed to what fits the field: (domain, device classes) pairs; None = any device class.
_T = ("sensor", ["temperature"])
_ENTITY_FILTERS: dict[str, list] = {
    CONF_INDOOR: [_T], CONF_ZONE_TEMP: [_T], CONF_FLOOR: [_T], CONF_COIL: [_T], CONF_RETURN: [_T],
    CONF_BUFFER_TOP: [_T], CONF_BUFFER_BOTTOM: [_T], CONF_WINDOW_DROP: [_T],
    CONF_OUTDOOR: [_T, ("weather", None)],
    CONF_HUMIDITY: [("sensor", ["humidity"])],
    CONF_BOILER_POWER: [("sensor", ["power"])],
    CONF_HEAT_ENERGY: [("sensor", ["gas", "energy", "volume"])],
    CONF_EXTRA_HEAT: [("sensor", ["energy", "power"])],
    CONF_FLAME: [("binary_sensor", ["heat", "running", "power"])],
    CONF_WINDOWS: [("binary_sensor", ["window", "door", "opening", "garage_door"])],
    CONF_ZONE_DOORS: [("binary_sensor", ["door", "opening", "window", "garage_door"])],
    CONF_PRESENCE: [("person", None), ("binary_sensor", ["presence", "occupancy"]), ("sensor", None), ("input_select", None)],
    CONF_DEMAND: [("binary_sensor", None), ("input_boolean", None), ("switch", None)],
}
_RELAY = ("tpi", "pid", "onoff")  # controls that switch a relay themselves
def _no_comment_end(text: str) -> str:
    """A placeholder that may sit inside an HTML comment of a translation must not end it."""
    return str(text).replace("-->", "->")


_STATUS_TEXT = {"recommended": ("Ajánlott", "Recommended"), "possible": ("Lehetséges", "Possible"),
                "not_recommended": ("Nem ajánlott", "Not recommended")}


def _ent(key: str, *domains: str, multiple: bool = False) -> EntitySelector:
    """The picker of a field: narrowed by _ENTITY_FILTERS when listed there, else by the given domains."""
    filters = _ENTITY_FILTERS.get(key)
    if not filters:
        return _entity(*domains, multiple=multiple)
    return EntitySelector(EntitySelectorConfig(
        filter=[{"domain": d, **({"device_class": dc} if dc else {})} for d, dc in filters], multiple=multiple))


def _rooms_ok(conf: dict, control: str | None) -> bool:
    """Rooms (0.43.0; TRV rooms before): a single zone with TPI / PID."""
    return conf.get(CONF_ROLE, "standalone") == "standalone" and control in ("tpi", "pid")


def _number(minimum: float, maximum: float, step: float, unit: str = "") -> NumberSelector:
    return NumberSelector(NumberSelectorConfig(
        min=minimum, max=maximum, step=step, unit_of_measurement=unit, mode=NumberSelectorMode.BOX))


_FEEDBACK_DOMAINS = ("binary_sensor", "sensor", "valve", "cover")


def _exercise_fields(cfg: HcConfig) -> dict:
    """Summer valve exercise of a zone's own actuator."""
    days = SelectSelector(SelectSelectorConfig(options=[str(d) for d in range(7)], translation_key="weekday",
                                               mode=SelectSelectorMode.DROPDOWN))
    return {
        vol.Required("valve_exercise", default=cfg.valve_exercise): BooleanSelector(),
        vol.Required("exercise_weekday", default=str(cfg.exercise_weekday)): days,
        vol.Required("exercise_time", default=cfg.exercise_time): TimeSelector(),
        vol.Required("exercise_s", default=cfg.exercise_s): _number(60, 1800, 60, "s"),
    }


def _buffer_fields(current: dict) -> dict:
    """Buffer tank (0.33.0): its thermometers, the heat source relay, the zones that draw from it, the limits."""
    zones = EntitySelector(EntitySelectorConfig(domain="climate", integration=DOMAIN, multiple=True))
    cfg = BufferConfig(**{k: v for k, v in current.items() if k in BufferConfig.__dataclass_fields__})
    return {
        vol.Required(CONF_BUFFER_TOP, default=current.get(CONF_BUFFER_TOP)) if current.get(CONF_BUFFER_TOP) else vol.Required(CONF_BUFFER_TOP): _ent(CONF_BUFFER_TOP, "sensor"),
        vol.Optional(CONF_BUFFER_BOTTOM, description={"suggested_value": current.get(CONF_BUFFER_BOTTOM)}): _ent(CONF_BUFFER_BOTTOM, "sensor"),
        vol.Required(CONF_BOILER, default=current.get(CONF_BOILER)) if current.get(CONF_BOILER) else vol.Required(CONF_BOILER): _entity("switch", "input_boolean"),
        vol.Optional(CONF_ZONES, description={"suggested_value": current.get(CONF_ZONES)}): zones,
        vol.Required("buffer_demand_led", default=cfg.buffer_demand_led): BooleanSelector(),
        vol.Required("buffer_on", default=cfg.buffer_on): _number(20, 80, 1, "°C"),
        vol.Required("buffer_off", default=cfg.buffer_off): _number(25, 90, 1, "°C"),
        vol.Required("buffer_min_off_s", default=cfg.buffer_min_off_s): _number(0, 7200, 60, "s"),
        vol.Required("buffer_max_charge_s", default=cfg.buffer_max_charge_s): _number(0, 86400, 600, "s"),
        vol.Required("buffer_frost", default=cfg.buffer_frost): _number(3, 15, 1, "°C"),
    }


def _central_fields(current: dict) -> dict:
    zones = EntitySelector(EntitySelectorConfig(domain="climate", integration=DOMAIN, multiple=True))
    return {
        vol.Required(CONF_ZONES, default=current.get(CONF_ZONES, [])): zones,
        vol.Required(CONF_BOILER, default=current.get(CONF_BOILER)) if current.get(CONF_BOILER) else vol.Required(CONF_BOILER): _entity("switch", "input_boolean"),
        vol.Required("central_valve_open_s", default=current.get("central_valve_open_s", 180)): _number(0, 900, 10, "s"),
        vol.Required("central_min_zones", default=current.get("central_min_zones", 1)): _number(1, 20, 1),
        vol.Required("central_min_demand", default=current.get("central_min_demand", 0.0)): _number(0, 10, 0.1),
        vol.Required("central_min_on_s", default=current.get("central_min_on_s", 300)): _number(0, 3600, 30, "s"),
        vol.Required("central_min_off_s", default=current.get("central_min_off_s", 300)): _number(0, 3600, 30, "s"),
        vol.Required("central_stuck_s", default=current.get("central_stuck_s", 600)): _number(60, 3600, 30, "s"),
        vol.Required("central_keep_alive_s", default=current.get("central_keep_alive_s", 0)): _number(0, 600, 10, "s"),
        vol.Optional(CONF_PUMP, description={"suggested_value": current.get(CONF_PUMP)}): _entity("switch", "input_boolean"),
        vol.Required("central_pump_overrun_s", default=current.get("central_pump_overrun_s", 180)): _number(0, 1800, 30, "s"),
        vol.Required("central_pump_bypass", default=current.get("central_pump_bypass", False)): BooleanSelector(),
        # weekly pump exercise (0.39.0): with a pump entity only
        vol.Required("central_pump_exercise_s", default=current.get("central_pump_exercise_s", 60)): _number(0, 600, 10, "s"),
        vol.Required("central_pump_exercise_weekday", default=str(current.get("central_pump_exercise_weekday", 0))): SelectSelector(
            SelectSelectorConfig(options=[str(d) for d in range(7)], translation_key="weekday", mode=SelectSelectorMode.DROPDOWN)),
        vol.Required("central_pump_exercise_time", default=current.get("central_pump_exercise_time", "10:00")): TimeSelector(),
        vol.Required("central_pump_exercise_idle_days", default=current.get("central_pump_exercise_idle_days", 7)): _number(1, 30, 1, "d"),
        # modulating boiler (0.27.0): the highest flow request of the zones
        vol.Optional(CONF_FLOW, description={"suggested_value": current.get(CONF_FLOW)}): _entity("number", "input_number"),
        vol.Required("central_flow_min", default=current.get("central_flow_min", 25.0)): _number(15, 60, 1, "°C"),
        vol.Required("central_flow_max", default=current.get("central_flow_max", 75.0)): _number(30, 90, 1, "°C"),
        vol.Required("central_flow_default", default=current.get("central_flow_default", 55.0)): _number(20, 90, 1, "°C"),
    }


def _hp_fields(source: str | None, control: str | None, current: dict, settings: bool) -> dict:
    """Heat pump: its defrost / hot-water signals (optional) and, in the options, the run times and the hysteresis."""
    if source != "heat_pump":
        return {}
    out = {
        vol.Optional(CONF_HP_DEFROST, description={"suggested_value": current.get(CONF_HP_DEFROST)}): _entity("binary_sensor", "sensor", "switch", "input_boolean"),
        vol.Optional(CONF_HP_DHW, description={"suggested_value": current.get(CONF_HP_DHW)}): _entity("binary_sensor", "sensor", "switch", "input_boolean"),
    }
    if settings and control in ("curve", "onoff"):
        cfg = HcConfig.from_mapping(current)
        out[vol.Required("hp_min_on_s", default=cfg.hp_min_on_s)] = _number(300, 7200, 60, "s")
        out[vol.Required("hp_min_off_s", default=cfg.hp_min_off_s)] = _number(120, 3600, 60, "s")
        if control == "onoff":
            out[vol.Required("onoff_hysteresis", default=cfg.onoff_hysteresis)] = _number(0.1, 2, 0.1, "°C")
    return out


def _floor_fields(system: str | None, source: str | None, control: str | None, current: dict) -> dict:
    """Floor heating with own control: the floor sensor and its limit (both required for an electric floor)."""
    if not str(system or "").startswith("floor") or control not in ("tpi", "pid", "onoff", "curve"):
        return {}
    cfg = HcConfig.from_mapping({**source_defaults(system, source), **current})
    electric = electric_floor(system, source)
    floor_key = vol.Required(CONF_FLOOR) if electric and not current.get(CONF_FLOOR) else \
        vol.Optional(CONF_FLOOR, description={"suggested_value": current.get(CONF_FLOOR)})
    return {
        floor_key: _ent(CONF_FLOOR, "sensor"),
        # 0.37.0: 0 = by the covering and the probe position (core/floor.py); a stored value stays as it is
        vol.Required("floor_max", default=float(current.get("floor_max", 0.0) or 0.0)): _number(0, 40, 0.5, "°C"),
        vol.Required("floor_covering", default=covering_of(cfg.floor_covering) or "none"): _select(("none",) + COVERINGS, "floor_covering"),
        vol.Required("floor_probe", default=cfg.floor_probe if cfg.floor_probe in PROBES else "surface"): _select(PROBES, "floor_probe"),
        vol.Required("floor_hysteresis", default=cfg.floor_hysteresis): _number(0.2, 5, 0.1, "°C"),
        **_temper_fields(control, cfg),
    }


def _temper_fields(control: str | None, cfg: HcConfig) -> dict:
    """Floor tempering (0.35.0) and the floor fallback of a lost room thermometer (0.36.0): relay controls only."""
    if control not in ("tpi", "pid", "onoff"):
        return {}
    return {
        vol.Required("floor_temper", default=cfg.floor_temper): BooleanSelector(),
        vol.Required("floor_temper_offset", default=cfg.floor_temper_offset): _number(0, 8, 0.5, "°C"),
        vol.Required("floor_temper_night", default=cfg.floor_temper_night): _number(0, 30, 0.5, "°C"),
        vol.Required("floor_temper_hysteresis", default=cfg.floor_temper_hysteresis): _number(0.1, 2, 0.1, "°C"),
        vol.Required("floor_temper_room_margin", default=cfg.floor_temper_room_margin): _number(0.2, 3, 0.1, "°C"),
        vol.Required("floor_fallback", default=cfg.floor_fallback): BooleanSelector(),  # 0.36.0
    }


def _power_fields(source: str | None, current: dict, settings: bool) -> dict:
    """Electric heat on controlled (off-peak) power, and the storage heater (0.31.0)."""
    if source not in ELECTRIC_SOURCES:
        return {}

    def opt(key, *domains):
        return {vol.Optional(key, description={"suggested_value": current.get(key)}): _ent(key, *domains)}

    out = opt(CONF_POWER_AVAILABLE, "binary_sensor", "switch", "input_boolean")
    if source == "storage_heater":
        out.update(opt(CONF_DISCHARGE, "switch", "input_boolean", "fan"))
        if settings:
            cfg = HcConfig.from_mapping(current)
            out.update({
                vol.Required("storage_window_start", default=cfg.storage_window_start): TimeSelector(),
                vol.Required("storage_window_end", default=cfg.storage_window_end): TimeSelector(),
                vol.Required("storage_charge_h", default=cfg.storage_charge_h): _number(1, 12, 0.5, "h"),
                vol.Required("storage_bias", default=cfg.storage_bias): _number(-0.5, 0.5, 0.05),
                vol.Required("storage_discharge_hyst", default=cfg.storage_discharge_hyst): _number(0.1, 2, 0.1, "°C"),
            })
    return out


def _water_fields(system: str | None, source: str | None, current: dict, settings: bool) -> dict:
    """Fan coil (its fan, coil sensor) and district heating (return limit) – 0.32.0."""
    out: dict = {}

    def opt(key, *domains):
        return {vol.Optional(key, description={"suggested_value": current.get(key)}): _ent(key, *domains)}

    cfg = HcConfig.from_mapping({**source_defaults(system, source), **current})
    if system == "fan_coil":
        out.update({**opt(CONF_FAN, "fan"), **opt(CONF_COIL, "sensor")})
        if settings:
            out.update({
                vol.Required("fan_min_pct", default=cfg.fan_min_pct): _number(0, 100, 5, "%"),
                vol.Required("fan_overrun_s", default=cfg.fan_overrun_s): _number(0, 900, 30, "s"),
                vol.Required("fan_min_coil", default=cfg.fan_min_coil): _number(15, 50, 1, "°C"),
            })
    if source == "district_heating":
        out.update(opt(CONF_RETURN, "sensor"))
        if settings:
            out.update({
                vol.Required("return_max", default=cfg.return_max): _number(0, 70, 1, "°C"),
                vol.Required("return_hysteresis", default=cfg.return_hysteresis): _number(1, 10, 0.5, "°C"),
            })
    return out


def _cool_fields(system: str | None, source: str | None, control: str | None, current: dict) -> dict:
    """Floor cooling with dew point protection (0.29.0): a reversible heat pump on a floor, curve or on/off."""
    if source != "heat_pump" or not str(system or "").startswith("floor") or control not in ("curve", "onoff"):
        return {}
    cfg = HcConfig.from_mapping(current)

    def opt(key, *domains):
        return {vol.Optional(key, description={"suggested_value": current.get(key)}): _ent(key, *domains)}

    out = {
        vol.Required("floor_cooling", default=cfg.floor_cooling): BooleanSelector(),
        **opt(CONF_HUMIDITY, "sensor"),
        **opt(CONF_COOL_MODE, "switch", "input_boolean"),
        vol.Required("target_cool", default=cfg.target_cool): _number(20, 30, 0.5, "°C"),
        vol.Required("dew_margin", default=cfg.dew_margin): _number(1, 5, 0.5, "°C"),
        vol.Required("floor_min_cool", default=cfg.floor_min_cool): _number(16, 24, 0.5, "°C"),
    }
    if control == "curve":
        out.update({
            **opt(CONF_COOL_FLOW, "number", "input_number"),
            vol.Required("cool_flow", default=cfg.cool_flow): _number(12, 24, 0.5, "°C"),
            vol.Required("cool_flow_max", default=cfg.cool_flow_max): _number(16, 26, 0.5, "°C"),
        })
    return out


class HcConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _name_taken(self, name: str) -> bool:
        name = str(name or "").strip().casefold()
        return any(str(e.title).strip().casefold() == name or str(e.data.get(CONF_NAME, "")).strip().casefold() == name
                   for e in self._async_current_entries(include_ignore=False))

    def _free_name(self, base: str = "HC Thermostat") -> str:
        """0.45.0: a default name no instance has yet (HC Thermostat, HC Thermostat 2, …)."""
        name, n = base, 1
        while self._name_taken(name):
            n += 1
            name = f"{base} {n}"
        return name

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None and self._name_taken(user_input[CONF_NAME]):
            errors[CONF_NAME] = "name_taken"  # 0.45.0: a field error; before, the flow aborted and the input was lost
        elif user_input is not None:
            user_input = {**user_input, CONF_NAME: str(user_input[CONF_NAME]).strip()}
            self._data.update(user_input)
            if user_input.get(CONF_ROLE) == "central":
                return await self.async_step_central()
            if user_input.get(CONF_ROLE) == "buffer":
                return await self.async_step_buffer()
            return await self.async_step_control()
        last = user_input or {}
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=last.get(CONF_NAME) or self._free_name()): TextSelector(),
            vol.Required(CONF_ROLE, default=last.get(CONF_ROLE, "standalone")): _select(ROLES, "role"),
            vol.Required(CONF_HEAT_SOURCE, default=last.get(CONF_HEAT_SOURCE, "onoff_boiler")): _select(SOURCES, "heat_source"),
            vol.Required(CONF_SYSTEM, default=last.get(CONF_SYSTEM, "radiator_single")): _select(SYSTEMS, "system"),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_wizard(self, data):
        """An instance put together in the setup wizard (already validated there); starts in shadow mode, or live
        when the user ticked "start live" on the wizard's summary (0.45.0)."""
        self._async_abort_entries_match({CONF_NAME: data[CONF_NAME]})
        mode = MODE_ACTIVE if data.get(CONF_MODE) == MODE_ACTIVE else MODE_SHADOW
        return self.async_create_entry(title=data[CONF_NAME], data={**data, CONF_MODE: mode})

    async def async_step_central(self, user_input=None):
        """Central boiler: the zone thermostats it gathers and the boiler relay it switches."""
        if user_input is not None:
            data = {**self._data, **user_input, CONF_MODE: MODE_SHADOW}  # Going live is a separate step.
            return self.async_create_entry(title=self._data[CONF_NAME], data=data)
        return self.async_show_form(step_id="central", data_schema=vol.Schema(_central_fields({})))

    async def async_step_buffer(self, user_input=None):
        """Buffer tank: charges the tank by its temperatures; starts in shadow mode."""
        errors = {}
        if user_input is not None:
            if user_input["buffer_off"] <= user_input["buffer_on"]:
                errors["buffer_off"] = "buffer_order"
            else:
                return self.async_create_entry(title=self._data[CONF_NAME], data={**self._data, **user_input, CONF_MODE: MODE_SHADOW})
        return self.async_show_form(step_id="buffer", data_schema=vol.Schema(_buffer_fields(user_input or {})), errors=errors)

    async def async_step_control(self, user_input=None):
        source, system = self._data[CONF_HEAT_SOURCE], self._data[CONF_SYSTEM]
        matrix = cell(system, source)
        risky = matrix.status == Status.NOT_RECOMMENDED
        errors = {}
        if user_input is not None:
            if risky and not user_input.get(CONF_CONFIRM):
                errors[CONF_CONFIRM] = "confirm_required"
            else:
                self._data[CONF_CONTROL] = user_input[CONF_CONTROL]
                return await self.async_step_entities()
        options = controls(source, system)  # fan coil: its own valve; curve = heating curve (EXPERIMENTAL); tpi/pid also as relay mode of a modulating boiler
        fields: dict = {vol.Required(CONF_CONTROL, default=options[0]): _select(options, "control")}
        if risky:
            fields[vol.Required(CONF_CONFIRM, default=False)] = BooleanSelector()
        # 0.45.0: the flow does not know the user's language – both languages go in, and each translation (hu.json,
        # en.json) uses its own; "status" / "advice" stay for a translation that still names them
        language = self.hass.config.language or "en"
        status_hu, status_en = _STATUS_TEXT[matrix.status.value]
        # each translation shows its own language and hides the other in an HTML comment (same placeholders in
        # every translation, as Home Assistant checks)
        return self.async_show_form(
            step_id="control", data_schema=vol.Schema(fields), errors=errors,
            description_placeholders={
                "status_hu": status_hu, "status_en": status_en, "advice_hu": matrix.text_hu, "advice_en": matrix.text_en,
                "status": status_hu if language.startswith("hu") else status_en,
                "advice": matrix.text_hu if language.startswith("hu") else matrix.text_en,
            },
        )

    async def async_step_entities(self, user_input=None):
        external = self._data[CONF_CONTROL] in ("external", "ac")
        curve = self._data[CONF_CONTROL] == "curve"
        relay = self._data[CONF_CONTROL] in _RELAY
        errors = {}
        if user_input is not None and not user_input.get(CONF_INDOOR) and not user_input.get(CONF_DEMAND):
            errors[CONF_INDOOR] = "indoor_required"  # a room thermometer, or a wall thermostat's contact (0.38.0)
        elif user_input is not None and user_input.get(CONF_EXTERNAL) in excluded_climates(self.hass):
            errors[CONF_EXTERNAL] = "climate_taken"  # 0.45.0: an HC thermostat or another instance's device
        elif user_input is not None:
            data = {
                **self._data, **user_input, **default_timing(self._data[CONF_SYSTEM], self._data[CONF_HEAT_SOURCE]),
                **(default_curve(self._data[CONF_SYSTEM], self._data[CONF_HEAT_SOURCE]) if curve else {}),
                CONF_MODE: MODE_SHADOW,  # Going live is always a separate, explicit step.
            }
            if data.get(CONF_ROLE) == "zone" and data[CONF_CONTROL] in ("tpi", "pid"):
                data["valve_exercise"] = True  # summer valve exercise of the zone's own actuator
            return self.async_create_entry(title=self._data[CONF_NAME], data=data)
        # a relay control may take its demand from a wired wall thermostat (0.38.0): then no room thermometer is needed
        fields: dict = {(vol.Optional(CONF_INDOOR) if relay else vol.Required(CONF_INDOOR)): _ent(CONF_INDOOR, "sensor")}
        if relay:
            fields[vol.Optional(CONF_DEMAND)] = _ent(CONF_DEMAND, "binary_sensor", "input_boolean", "switch")
        if external:
            # 0.45.0: not an HC thermostat, nor a climate another instance drives
            fields[vol.Required(CONF_EXTERNAL)] = EntitySelector(EntitySelectorConfig(
                domain="climate", exclude_entities=excluded_climates(self.hass)))
        elif curve:
            fields[vol.Required(CONF_FLOW)] = _entity("number", "input_number")
            fields[vol.Optional(CONF_HEAT_ENABLE)] = _entity("switch", "input_boolean")
        else:
            fields[vol.Required(CONF_ACTUATOR)] = _entity("switch", "input_boolean")
        if curve:
            fields[vol.Required(CONF_OUTDOOR)] = _ent(CONF_OUTDOOR, "sensor", "weather")  # the curve needs it
        else:
            fields[vol.Optional(CONF_OUTDOOR)] = _ent(CONF_OUTDOOR, "sensor", "weather")
        fields[vol.Optional(CONF_REFERENCE)] = _entity("binary_sensor", "switch", "climate", "input_boolean")
        fields[vol.Optional(CONF_HEAT_ENERGY)] = _ent(CONF_HEAT_ENERGY, "sensor")
        fields[vol.Optional(CONF_ENERGY_FACTOR, default=8.55)] = _number(0.01, 100, 0.01, "kWh")
        fields[vol.Optional(CONF_EXTRA_HEAT)] = _ent(CONF_EXTRA_HEAT, "sensor")
        fields[vol.Optional(CONF_EXTRA_FACTOR, default=3.0)] = _number(0.1, 10, 0.1, "×")
        fields[vol.Optional("boiler_power_kw", default=0.0)] = _number(0, 100, 0.1, "kW")
        fields[vol.Optional(CONF_WINDOWS)] = _ent(CONF_WINDOWS, "binary_sensor", multiple=True)
        fields[vol.Optional(CONF_PRESENCE)] = _ent(CONF_PRESENCE, "person", "sensor", "binary_sensor", "input_select", multiple=True)
        # 0.45.0: the adjoining room (a second heat source behind a door) is rare – it is set in the options
        if self._data.get(CONF_ROLE) == "zone":
            fields[vol.Optional(CONF_VALVE_FEEDBACK)] = _entity(*_FEEDBACK_DOMAINS)
        fields.update(_floor_fields(self._data[CONF_SYSTEM], self._data[CONF_HEAT_SOURCE], self._data[CONF_CONTROL], {}))
        fields.update(_hp_fields(self._data[CONF_HEAT_SOURCE], self._data[CONF_CONTROL], {}, settings=False))
        fields.update(_power_fields(self._data[CONF_HEAT_SOURCE], {}, settings=False))
        fields.update(_water_fields(self._data[CONF_SYSTEM], self._data[CONF_HEAT_SOURCE], {}, settings=False))
        fields[vol.Optional(CONF_TARGET_SOURCE)] = _entity("climate", "number", "input_number")
        return self.async_show_form(step_id="entities", data_schema=vol.Schema(fields), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "HcOptionsFlow":
        return HcOptionsFlow()


class HcOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        """0.45.0: a menu first – all settings, or only going live (back to shadow) with one confirmation."""
        current = {**self.config_entry.data, **self.config_entry.options}
        if current.get(CONF_ROLE) == "central":
            return await self.async_step_central(user_input)
        if current.get(CONF_ROLE) == "buffer":
            return await self.async_step_buffer(user_input)
        live = current.get(CONF_MODE, MODE_SHADOW) == MODE_ACTIVE
        menu = ["settings"]
        if _rooms_ok(current, current.get(CONF_CONTROL, "tpi")):
            menu.append("rooms")  # 0.46.0: straight to the rooms, saved on their own
        return self.async_show_menu(step_id="init", menu_options=[*menu, "go_shadow" if live else "go_live"])

    async def async_step_go_live(self, user_input=None):
        """Only the mode: shadow → active, with the usual confirmation; every other setting stays."""
        errors = {}
        if user_input is not None:
            if not user_input.get(CONF_CONFIRM):
                errors[CONF_CONFIRM] = "confirm_active"
            else:
                return self.async_create_entry(data={**self.config_entry.options, CONF_MODE: MODE_ACTIVE})
        return self.async_show_form(step_id="go_live", errors=errors, data_schema=vol.Schema({
            vol.Required(CONF_CONFIRM, default=False): BooleanSelector()}),
            description_placeholders={"name": self.config_entry.title})

    async def async_step_go_shadow(self, user_input=None):
        """Back to shadow mode: it calculates on, but switches nothing."""
        if user_input is not None:
            return self.async_create_entry(data={**self.config_entry.options, CONF_MODE: MODE_SHADOW})
        return self.async_show_form(step_id="go_shadow", data_schema=vol.Schema({}),
                                    description_placeholders={"name": self.config_entry.title})

    async def async_step_settings(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            if user_input[CONF_MODE] == MODE_ACTIVE and not user_input.get(CONF_CONFIRM):
                errors[CONF_CONFIRM] = "confirm_active"
            elif user_input.get("floor_cooling") and not user_input.get(CONF_HUMIDITY):
                errors[CONF_HUMIDITY] = "humidity_required"  # no dew point, no cooling
            elif (current.get(CONF_CONTROL) in _RELAY and not current.get(CONF_INDOOR)
                  and not user_input.get(CONF_DEMAND)):
                errors[CONF_DEMAND] = "demand_required"  # no room thermometer: the wall thermostat gives the demand
            else:
                self._settings = {k: v for k, v in user_input.items() if k != CONF_CONFIRM}
                # 0.45.0: the boiler's power levels count as given only when someone set them – the untouched
                # defaults (one boiler's values) are not saved, so the health check keeps learning
                base = HcConfig()
                if not power_levels_known(current) and user_input.get("power_idle_w") == base.power_idle_w \
                        and user_input.get("power_burn_w") == base.power_burn_w:
                    self._settings.pop("power_idle_w", None)
                    self._settings.pop("power_burn_w", None)
                return await self.async_step_presets()
        cfg = HcConfig.from_mapping(current)
        temp = _number(5, 30, 0.5, "°C")
        fields = {
            vol.Required(CONF_MODE, default=current.get(CONF_MODE, MODE_SHADOW)): _select([MODE_SHADOW, MODE_ACTIVE], "mode"),
            vol.Optional(CONF_CONFIRM, default=False): BooleanSelector(),
            vol.Required("target_home", default=cfg.target_home): temp,
            vol.Required("target_night", default=cfg.target_night): temp,
            vol.Required("target_away", default=cfg.target_away): temp,
            vol.Required("target_vacation", default=cfg.target_vacation): temp,
            vol.Required("frost_temp", default=cfg.frost_temp): _number(3, 12, 0.5, "°C"),
            vol.Required("night_start", default=cfg.night_start): TimeSelector(),
            vol.Required("night_end", default=cfg.night_end): TimeSelector(),
            vol.Required("cycle_s", default=cfg.cycle_s): _number(300, 7200, 60, "s"),
            vol.Required("min_on_s", default=cfg.min_on_s): _number(0, 3600, 30, "s"),
            vol.Required("min_off_s", default=cfg.min_off_s): _number(0, 3600, 30, "s"),
            vol.Required("keep_alive_s", default=cfg.keep_alive_s): _number(0, 600, 10, "s"),
            vol.Optional(CONF_KEEP_ALIVE_SCRIPT, description={"suggested_value": current.get(CONF_KEEP_ALIVE_SCRIPT)}): _entity("script"),
            **({vol.Required("frozen_after_h", default=cfg.frozen_after_h): _number(0, 24, 0.5, "h"),
                vol.Required("frozen_burn_min", default=cfg.frozen_burn_min): _number(0, 240, 5, "min")}
               if cfg.control in ("tpi", "pid", "onoff") else {}),
            vol.Required("season_enabled", default=cfg.season_enabled): BooleanSelector(),
            vol.Required("boost_enabled", default=cfg.boost_enabled): BooleanSelector(),
            vol.Required("learning_enabled", default=cfg.learning_enabled): BooleanSelector(),
            vol.Required("shadow_regulator", default=cfg.shadow_regulator): BooleanSelector(),
            **({vol.Required("target_cool", default=cfg.target_cool): _number(18, 32, 0.5, "°C"),
                vol.Required("ac_ki_per_hour", default=cfg.ac_ki_per_hour): _number(0, 3, 0.05),
                vol.Required("ac_min_change_s", default=cfg.ac_min_change_s): _number(120, 3600, 60, "s"),
                vol.Optional(CONF_ASSIST, description={"suggested_value": current.get(CONF_ASSIST)}): _entity("climate")}
               if cfg.control == "ac" else {}),
            **({vol.Required("yield_margin", default=cfg.yield_margin): _number(0, 2, 0.1, "°C")}
               if cfg.control in ("tpi", "pid") else {}),
            **({vol.Required(CONF_CONTROL, default=cfg.control): _select(["tpi", "pid"], "control")}
               if cfg.control in ("tpi", "pid") else {}),
            vol.Required("pid_kp", default=cfg.pid_kp): _number(0, 5, 0.05),
            vol.Required("pid_ki_per_hour", default=cfg.pid_ki_per_hour if cfg.pid_ki_per_hour is not None else round(cfg.pid_ki * 3600, 3)): _number(0, 5, 0.01),
            vol.Required("pid_kd", default=cfg.pid_kd): _number(0, 100000, 1),
            vol.Required("pid_d_filter_s", default=cfg.pid_d_filter_s): _number(0, 3600, 30, "s"),
            vol.Optional(CONF_FLAME, description={"suggested_value": current.get(CONF_FLAME)}): _ent(CONF_FLAME, "binary_sensor"),
            vol.Optional(CONF_BOILER_POWER, description={"suggested_value": current.get(CONF_BOILER_POWER)}): _ent(CONF_BOILER_POWER, "sensor"),
            vol.Required("power_idle_w", default=cfg.power_idle_w): _number(0, 500, 1, "W"),
            vol.Required("power_burn_w", default=cfg.power_burn_w): _number(0, 5000, 1, "W"),
            vol.Required("boiler_power_kw", default=cfg.boiler_power_kw): _number(0, 100, 0.1, "kW"),
            # electric zones sharing a power budget (0.28.0): the same limit on every zone, its own power above
            **({vol.Required("load_limit_kw", default=cfg.load_limit_kw): _number(0, 100, 0.1, "kW")}
               if current.get(CONF_HEAT_SOURCE) in ELECTRIC_SOURCES and cfg.control in ("tpi", "pid") else {}),
            vol.Optional(CONF_HEAT_ENERGY, description={"suggested_value": current.get(CONF_HEAT_ENERGY)}): _ent(CONF_HEAT_ENERGY, "sensor"),
            vol.Required(CONF_ENERGY_FACTOR, default=current.get(CONF_ENERGY_FACTOR, 8.55)): _number(0.01, 100, 0.01, "kWh"),
            vol.Required(CONF_EXTRA_FACTOR, default=current.get(CONF_EXTRA_FACTOR, 3.0)): _number(0.1, 10, 0.1, "×"),
            vol.Optional(CONF_WINDOWS, description={"suggested_value": current.get(CONF_WINDOWS)}): _ent(CONF_WINDOWS, "binary_sensor", multiple=True),
            vol.Optional(CONF_WINDOW_DROP, description={"suggested_value": current.get(CONF_WINDOW_DROP)}): _ent(CONF_WINDOW_DROP, "sensor", multiple=True),
            vol.Required("window_drop_rate", default=cfg.window_drop_rate): _number(0.5, 10, 0.1, "°C/h"),
            # 0.46.0: the rooms and their tolerance are in the "Rooms" menu item
            vol.Optional(CONF_ZONE_TEMP, description={"suggested_value": current.get(CONF_ZONE_TEMP)}): _ent(CONF_ZONE_TEMP, "sensor"),
            vol.Optional(CONF_ZONE_DOORS, description={"suggested_value": current.get(CONF_ZONE_DOORS)}): _ent(CONF_ZONE_DOORS, "binary_sensor", multiple=True),
            vol.Required(CONF_ZONE_DIFF, default=current.get(CONF_ZONE_DIFF, 2.0)): _number(0, 10, 0.5, "°C"),
            vol.Optional(CONF_BOILER_PRICE, description={"suggested_value": current.get(CONF_BOILER_PRICE)}): _entity("sensor", "input_number"),
            vol.Optional(CONF_OTHER_PRICE, description={"suggested_value": current.get(CONF_OTHER_PRICE)}): _entity("sensor", "input_number"),
            vol.Optional(CONF_BOILER_PRICE_MANUAL, description={"suggested_value": current.get(CONF_BOILER_PRICE_MANUAL)}): _number(0, 100000, 0.01),
            vol.Optional(CONF_OTHER_PRICE_MANUAL, description={"suggested_value": current.get(CONF_OTHER_PRICE_MANUAL)}): _number(0, 100000, 0.01),
            vol.Optional(CONF_BOILER_LIMIT, description={"suggested_value": current.get(CONF_BOILER_LIMIT)}): _entity("sensor"),
            vol.Optional(CONF_OTHER_LIMIT, description={"suggested_value": current.get(CONF_OTHER_LIMIT)}): _entity("sensor"),
            vol.Required(CONF_COP_HIGH, default=current.get(CONF_COP_HIGH, 4.0)): _number(1, 8, 0.1),
            vol.Required(CONF_COP_LOW, default=current.get(CONF_COP_LOW, 2.4)): _number(1, 8, 0.1),
        }
        fields.update(_floor_fields(current.get(CONF_SYSTEM), current.get(CONF_HEAT_SOURCE), cfg.control, current))
        fields.update(_hp_fields(current.get(CONF_HEAT_SOURCE), cfg.control, current, settings=True))
        fields.update(_cool_fields(current.get(CONF_SYSTEM), current.get(CONF_HEAT_SOURCE), cfg.control, current))
        fields.update(_power_fields(current.get(CONF_HEAT_SOURCE), current, settings=True))
        fields.update(_water_fields(current.get(CONF_SYSTEM), current.get(CONF_HEAT_SOURCE), current, settings=True))
        fields[vol.Optional(CONF_TARGET_SOURCE, description={"suggested_value": current.get(CONF_TARGET_SOURCE)})] = \
            _entity("climate", "number", "input_number")
        if cfg.control == "external":  # 0.42.0: take over a target / off set on the managed thermostat itself
            fields[vol.Required("adopt_manual", default=cfg.adopt_manual)] = BooleanSelector()
        if cfg.control in _RELAY:  # a wired wall thermostat's contact as the demand (0.38.0)
            fields[vol.Optional(CONF_DEMAND, description={"suggested_value": current.get(CONF_DEMAND)})] = \
                _ent(CONF_DEMAND, "binary_sensor", "input_boolean", "switch")
        if current.get(CONF_ROLE) == "zone":
            fields[vol.Optional(CONF_VALVE_FEEDBACK, description={"suggested_value": current.get(CONF_VALVE_FEEDBACK)})] = _entity(*_FEEDBACK_DOMAINS)
            if str(current.get(CONF_SYSTEM) or "").startswith("floor"):
                fields[vol.Required("zone_own_mixer", default=bool(current.get("zone_own_mixer", False)))] = BooleanSelector()
            if cfg.control in ("tpi", "pid"):
                fields.update(_exercise_fields(cfg))
        if cfg.control == "curve":
            fields[vol.Required("curve_slope", default=cfg.curve_slope)] = _number(0.1, 4, 0.05)
            fields[vol.Required("curve_shift", default=cfg.curve_shift)] = _number(-10, 10, 0.5, "°C")
            fields[vol.Required("flow_min", default=cfg.flow_min)] = _number(15, 50, 1, "°C")
            fields[vol.Required("flow_max", default=cfg.flow_max)] = _number(25, 90, 1, "°C")
            fields[vol.Required("room_kp", default=cfg.room_kp)] = _number(0, 20, 0.5)
            fields[vol.Required("room_ki_per_hour", default=cfg.room_ki_per_hour)] = _number(0, 10, 0.1)
        return self.async_show_form(step_id="settings", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_buffer(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            if user_input[CONF_MODE] == MODE_ACTIVE and not user_input.get(CONF_CONFIRM):
                errors[CONF_CONFIRM] = "confirm_active"
            elif user_input["buffer_off"] <= user_input["buffer_on"]:
                errors["buffer_off"] = "buffer_order"
            else:
                return self.async_create_entry(data={k: v for k, v in user_input.items() if k != CONF_CONFIRM})
        fields = {
            vol.Required(CONF_MODE, default=current.get(CONF_MODE, MODE_SHADOW)): _select([MODE_SHADOW, MODE_ACTIVE], "mode"),
            vol.Optional(CONF_CONFIRM, default=False): BooleanSelector(),
            **_buffer_fields(current),
        }
        return self.async_show_form(step_id="buffer", data_schema=vol.Schema(fields), errors=errors)

    async def async_step_central(self, user_input=None):
        current = {**self.config_entry.data, **self.config_entry.options}
        errors = {}
        if user_input is not None:
            if user_input[CONF_MODE] == MODE_ACTIVE and not user_input.get(CONF_CONFIRM):
                errors[CONF_CONFIRM] = "confirm_active"
            else:
                return self.async_create_entry(data={k: v for k, v in user_input.items() if k != CONF_CONFIRM})
        fields = {
            vol.Required(CONF_MODE, default=current.get(CONF_MODE, MODE_SHADOW)): _select([MODE_SHADOW, MODE_ACTIVE], "mode"),
            vol.Optional(CONF_CONFIRM, default=False): BooleanSelector(),
            **_central_fields(current),
        }
        return self.async_show_form(step_id="central", data_schema=vol.Schema(fields), errors=errors)

    # --- rooms (0.43.0; 0.46.0: areas ticked in a list, one fold-out section per room) ---------------------------
    def _load_rooms(self) -> None:
        """The rooms as they work now: saved, or derived from the legacy options (unchanged until saved here)."""
        if getattr(self, "_rooms", None) is not None:
            return
        current = {**self.config_entry.data, **self.config_entry.options}
        specs, leading = room_specs_for(self.hass, current)
        self._rooms = [s.as_dict() for s in specs]
        self._leading = leading
        self._cand = None

    def _lang(self) -> str:
        return rf.lang_of(self.hass)

    def _candidates(self) -> dict:
        if getattr(self, "_cand", None) is None:
            self._cand = rooms_candidates(self.hass)
        return self._cand

    def _hc_climates(self, ids: list[str]) -> list[str]:
        reg = er.async_get(self.hass)
        return [e for e in ids if (x := reg.async_get(e)) is not None and x.platform == DOMAIN]

    def _area_of(self, entity_id: str | None) -> str | None:
        try:
            return area_id_of(self.hass, entity_id) if entity_id else None
        except Exception:  # no registries
            return None

    def _name_of(self, entity_id: str) -> str:
        st = self.hass.states.get(entity_id)
        return str(st.attributes.get("friendly_name") or entity_id) if st is not None else entity_id

    def _placeholders(self, problem: str = "") -> dict:
        lang_rooms = {"rooms_hu": _no_comment_end(rf.summary("hu", self._rooms, self._leading)),
                      "rooms_en": _no_comment_end(rf.summary("en", self._rooms, self._leading))}
        return {**lang_rooms, "problem": problem}

    async def async_step_rooms(self, user_input=None):
        """Step 1: the home's name and the areas that are rooms of this boiler (a check list)."""
        self._load_rooms()
        current = {**self.config_entry.data, **self.config_entry.options}
        cand = self._candidates()
        taken = areas_of_other_instances(self.hass, self.config_entry.entry_id)
        lang = self._lang()
        errors, problem = {}, ""
        if user_input is not None:
            selected = list(user_input.get("areas") or [])
            self._home_name = str(user_input.get(CONF_HOME_NAME) or "").strip()
            clash = next((a for a in selected if a in taken and a not in {r.get("area") for r in self._rooms}), None)
            if clash is not None:
                name = next((a["name"] for a in cand["areas"] if a["area"] == clash), clash)
                errors["base"], problem = "room_problem", rf.problem_text(lang, "area_taken", name, taken[clash])
            else:
                rooms = rf.pick_rooms(selected, self._rooms, cand, user_input.get("custom_rooms"))
                if not rooms:
                    errors["base"], problem = "room_problem", rf.problem_text(lang, "no_rooms")
                else:
                    self._rooms = rooms
                    if self._leading not in {r["key"] for r in rooms}:
                        self._leading = None
                    if self._leading is None:  # the room of the house thermometer leads (it drives the boiler now)
                        self._leading = rf.leading_guess(rooms, current.get(CONF_INDOOR), self._area_of(current.get(CONF_INDOOR)))
                    return await self.async_step_room_details()
        fields = {
            vol.Optional(CONF_HOME_NAME, description={"suggested_value": current.get(CONF_HOME_NAME)}): TextSelector(),
            vol.Optional("areas", default=rf.chosen_values(self._rooms)): SelectSelector(SelectSelectorConfig(
                options=rf.area_options(lang, cand, self._rooms, taken), multiple=True, mode=SelectSelectorMode.LIST)),
            vol.Optional("custom_rooms"): TextSelector(),
        }
        return self.async_show_form(step_id="rooms", data_schema=vol.Schema(fields), errors=errors,
                                    description_placeholders=self._placeholders(_no_comment_end(problem)))

    def _sections(self) -> tuple[dict, dict]:
        """room key -> (its section name, its candidates); a section name is the room's name (made unique)."""
        cand = self._candidates()
        by_area = {a["area"]: a for a in cand.get("areas") or []}
        excluded = set(excluded_climates(self.hass, self.config_entry.entry_id))
        names, cands, used = {}, {}, {"leading_room", CONF_CONFIRM, CONF_ROOM_TOL}
        for r in self._rooms:
            others = {h for o in self._rooms if o is not r for h in o.get("trvs") or []}
            cands[r["key"]] = rf.room_candidates(r, by_area.get(r.get("area")), cand.get("tracking") or [],
                                                 excluded | others)
            name, n = r["name"] or r["key"], 2
            while name in used:
                name, n = f"{r['name']} ({n})", n + 1
            used.add(name)
            names[r["key"]] = name
        return names, cands

    async def async_step_room_details(self, user_input=None):
        """Step 2: the leading room and the tolerance, then one fold-out section per room with check boxes."""
        current = {**self.config_entry.data, **self.config_entry.options}
        lang = self._lang()
        names, cands = self._sections()
        errors, problem = {}, ""
        if user_input is not None:
            leading = user_input.get("leading_room")
            leading = leading if leading in names else None
            rooms = [rf.read_section(self.hass, lang, r, user_input.get(names[r["key"]]) or {}) for r in self._rooms]
            problem = rf.check_rooms(lang, rooms, leading, bool(user_input.get(CONF_CONFIRM)),
                                     set(self._hc_climates([h for r in rooms for h in r.get("trvs") or []])),
                                     heads_of_other_instances(self.hass, self.config_entry.entry_id), self._name_of)
            self._room_tol = float(user_input.get(CONF_ROOM_TOL, current.get(CONF_ROOM_TOL, 0.5)))
            if problem:
                errors["base"] = "room_problem"
                self._rooms = [{**r, "new": True} if old.get("new") else r for r, old in zip(rooms, self._rooms)]
                self._rooms = [{k: v for k, v in r.items() if k != "_position"} for r in self._rooms]
            else:
                self._rooms, self._leading = rf.order_rooms(rooms), leading
                if any(r.get("mode") == OWN and r.get("trvs") and r["key"] != leading for r in self._rooms):
                    return await self.async_step_room_own()
                return self._save_rooms()
        opts = [{"value": "-", "label": "–"}] + [{"value": r["key"], "label": r["name"]} for r in self._rooms]
        fields = {
            vol.Required("leading_room", default=self._leading or "-"): SelectSelector(SelectSelectorConfig(
                options=opts, mode=SelectSelectorMode.DROPDOWN)),
            vol.Optional(CONF_CONFIRM, default=False): BooleanSelector(),
            vol.Required(CONF_ROOM_TOL, default=float(getattr(self, "_room_tol", current.get(CONF_ROOM_TOL, 0.5)))):
                _number(0.2, 3, 0.1, "°C"),
        }
        total = len(self._rooms)
        for i, r in enumerate(self._rooms, 1):
            fields[vol.Required(names[r["key"]])] = rf.room_section(self.hass, lang, r, cands[r["key"]], self._leading,
                                                                    i, total)
        return self.async_show_form(step_id="room_details", data_schema=vol.Schema(fields), errors=errors,
                                    description_placeholders=self._placeholders(_no_comment_end(problem)))

    async def async_step_room_own(self, user_input=None):
        """Step 3: the own schedule of the rooms set to it."""
        lang = self._lang()
        own = [r for r in self._rooms if r.get("mode") == OWN and r.get("trvs") and r["key"] != self._leading]
        names = {r["key"]: r["name"] for r in own}
        if user_input is not None:
            self._rooms = [rf.read_own(lang, r, user_input.get(names[r["key"]]) or {}) if r["key"] in names else r
                           for r in self._rooms]
            return self._save_rooms()
        fields = {vol.Required(names[r["key"]]): rf.own_section(lang, r) for r in own}
        return self.async_show_form(step_id="room_own", data_schema=vol.Schema(fields),
                                    description_placeholders=self._placeholders())

    def _save_rooms(self):
        """Only the rooms (and the home's name, the tolerance) change; every other setting stays as it is."""
        current = {**self.config_entry.data, **self.config_entry.options}
        rooms = [{k: v for k, v in r.items() if k not in ("new", "_position")} for r in self._rooms]
        data = {**self.config_entry.options, **rooms_options(rooms, self._leading, current.get(CONF_INDOOR)),
                CONF_HOME_NAME: getattr(self, "_home_name", current.get(CONF_HOME_NAME, "")) or "",
                CONF_ROOM_TOL: float(getattr(self, "_room_tol", current.get(CONF_ROOM_TOL, 0.5)))}
        return self.async_create_entry(data=data)

    async def async_step_presets(self, user_input=None):
        """Which presets are offered, their targets, and when a preset chosen by hand ends."""
        if user_input is not None:
            self._settings = {**self._settings, **user_input}
            # 0.46.0: the rooms have their own menu item – what they saved stays as it is
            kept = {k: v for k, v in self.config_entry.options.items() if k in ROOM_OPTION_KEYS}
            return self.async_create_entry(data={**kept, **self._settings})
        current = {**self.config_entry.data, **self.config_entry.options}
        cfg = HcConfig.from_mapping(current)
        temp = _number(5, 30, 0.5, "°C")
        choices = [p for p in PRESETS if p != "auto"]
        fields = {
            vol.Required("presets_enabled", default=list(cfg.presets_enabled)): SelectSelector(SelectSelectorConfig(
                options=choices, translation_key="preset", multiple=True, mode=SelectSelectorMode.LIST)),
            vol.Required("target_comfort", default=cfg.target_comfort): temp,
            vol.Required("target_eco", default=cfg.target_eco): temp,
        }
        for preset in TIMED_PRESETS:
            fields[vol.Required(f"expiry_{preset}", default=getattr(cfg, f"expiry_{preset}"))] = _select(EXPIRY, "expiry")
            fields[vol.Required(f"hours_{preset}", default=getattr(cfg, f"hours_{preset}"))] = _number(0.5, 336, 0.5, "h")
        return self.async_show_form(step_id="presets", data_schema=vol.Schema(fields))


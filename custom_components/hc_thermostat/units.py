"""Temperatures of other entities, in °C (0.45.0).

HC works in °C inside. A Home Assistant with °F (or a single sensor in °F or K) is converted here:
- a sensor's state by its own `unit_of_measurement`;
- a weather entity's `temperature` attribute by its `temperature_unit`;
- a climate entity's attributes (current_temperature, temperature, min_temp, max_temp, target_temp_step) are in the
  unit system of Home Assistant – HA converts them for the state –, and a climate service takes a temperature in the
  same unit. So what HC writes to a climate entity goes back from °C to the system unit.
Anything that is not a temperature unit (%, W, kWh …) passes unchanged.
"""

from __future__ import annotations

from typing import Any, Mapping

from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter

CELSIUS = UnitOfTemperature.CELSIUS
_UNITS = {
    "°C": UnitOfTemperature.CELSIUS, "C": UnitOfTemperature.CELSIUS, "℃": UnitOfTemperature.CELSIUS,
    "°F": UnitOfTemperature.FAHRENHEIT, "F": UnitOfTemperature.FAHRENHEIT, "℉": UnitOfTemperature.FAHRENHEIT,
    "K": UnitOfTemperature.KELVIN,
}
CLIMATE_TEMPS = ("current_temperature", "temperature", "min_temp", "max_temp", "target_temp_low", "target_temp_high")


def temp_unit(unit: Any) -> str | None:
    """The temperature unit of a unit string; None when it is no temperature unit."""
    return _UNITS.get(str(unit).strip()) if unit is not None else None


def system_unit(hass: Any) -> str:
    """Home Assistant's temperature unit (°C when it cannot be read, e.g. a bare test object)."""
    units = getattr(getattr(hass, "config", None), "units", None)
    return temp_unit(getattr(units, "temperature_unit", None)) or CELSIUS


def to_c(value: Any, unit: Any) -> float | None:
    """A number in `unit` as °C; a value without a temperature unit is returned as a float, unchanged."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    u = temp_unit(unit)
    if u is None or u == CELSIUS:
        return v
    return TemperatureConverter.convert(v, u, CELSIUS)


def from_c(value: float | None, unit: Any) -> float | None:
    """°C to `unit` (°C when it is no temperature unit)."""
    if value is None:
        return None
    u = temp_unit(unit) or CELSIUS
    return float(value) if u == CELSIUS else TemperatureConverter.convert(float(value), CELSIUS, u)


def state_value_c(state: Any) -> float | None:
    """A sensor's (or input_number's) numeric state, a weather entity's temperature – in °C when it is a temperature."""
    if state is None:
        return None
    attrs = getattr(state, "attributes", None) or {}
    if str(getattr(state, "entity_id", "")).startswith("weather."):
        return to_c(attrs.get("temperature"), attrs.get("temperature_unit"))
    return to_c(state.state, attrs.get("unit_of_measurement"))


def climate_temp_c(hass: Any, attrs: Mapping, key: str) -> float | None:
    """A temperature attribute of a climate entity, from the system unit to °C (None when missing / no number)."""
    value = attrs.get(key) if attrs else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return to_c(value, system_unit(hass))


def climate_attrs_c(hass: Any, attrs: Mapping) -> dict:
    """A copy of a climate entity's attributes with its temperatures (and its step) in °C."""
    out = dict(attrs or {})
    unit = system_unit(hass)
    if unit == CELSIUS:
        return out
    for key in CLIMATE_TEMPS:
        if isinstance(out.get(key), (int, float)) and not isinstance(out.get(key), bool):
            out[key] = to_c(out[key], unit)
    step = out.get("target_temp_step")
    if isinstance(step, (int, float)) and not isinstance(step, bool):
        out["target_temp_step"] = step_c(step, unit)
    return out


def step_c(step: float, unit: Any) -> float:
    """A temperature difference (a step) in `unit` as °C degrees."""
    u = temp_unit(unit) or CELSIUS
    if u == UnitOfTemperature.FAHRENHEIT:
        return float(step) * 5.0 / 9.0
    return float(step)


def to_system(hass: Any, value_c: float | None, native_step: Any = None) -> float | None:
    """A °C target as the value a climate service takes (system unit); in °F rounded to the entity's own step
    (a whole degree when it has none), so 21.0 °C becomes 70 °F, not 69.8."""
    unit = system_unit(hass)
    if value_c is None or unit == CELSIUS:
        return value_c
    value = from_c(value_c, unit)
    try:
        step = float(native_step) if native_step else 1.0
    except (TypeError, ValueError):
        step = 1.0
    if step <= 0:
        step = 1.0
    return round(round(value / step) * step, 2)


def source_value_c(hass: Any, state: Any) -> float | None:
    """A target source's setpoint in °C: a climate's target (system unit) or a number's value (its own unit)."""
    from .core.target_source import source_value

    if state is None:
        return None
    domain = str(getattr(state, "domain", None) or str(getattr(state, "entity_id", "")).split(".", 1)[0])
    attrs = dict(getattr(state, "attributes", None) or {})
    value = source_value(domain, state.state, attrs)
    if value is None:
        return None
    if domain == "climate":
        return to_c(value, system_unit(hass))
    return to_c(value, attrs.get("unit_of_measurement"))

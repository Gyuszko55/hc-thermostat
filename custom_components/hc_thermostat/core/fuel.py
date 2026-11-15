"""0.49.0: the heat per metered unit (energy_factor) from a fuel and an efficiency, instead of a number to work out.

"auto" reads the heat meter's unit (m³ gas, kWh, MJ, GJ) and, without a meter, the heat source; "custom" keeps the
number typed in. The result is what HC always used: kWh of heat per one unit the meter (or the price) counts.
0.52.0: the natural gas's heating value is a setting (`gas_heating_value`, kWh/m³) – 9.61 is the Hungarian bills'
34.6 MJ/m³; another country's (or supplier's) gas differs.
"""

from __future__ import annotations

FUELS = ("auto", "gas_m3", "lpg_kg", "oil_l", "pellet_kg", "electric_kwh", "custom")
# kWh per unit (lower heating value); natural gas: the Hungarian bills' 34.6 MJ/m³
GAS_DEFAULT = 9.61  # kWh/m³ – the Hungarian bills' 34.6 MJ/m³
HEATING_VALUE = {"gas_m3": GAS_DEFAULT, "lpg_kg": 12.8, "oil_l": 10.0, "pellet_kg": 4.8, "electric_kwh": 1.0}
DEFAULT_EFFICIENCY = 90.0  # % – a burner's typical seasonal efficiency
DEFAULT_FACTOR = 8.55  # the factor every instance had before 0.49.0
_BURNERS = {"onoff_boiler": "gas_m3", "modulating_boiler": "gas_m3", "pellet_boiler": "pellet_kg"}
_NO_LOSS = ("electric_heater", "electric_boiler", "storage_heater", "district_heating")  # 1 kWh in = 1 kWh of heat


def gas_value(value) -> float:
    """The gas's heating value in kWh/m³ (0.52.0): the setting when it is believable (5–15), else the default."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return GAS_DEFAULT
    return v if 5.0 <= v <= 15.0 else GAS_DEFAULT


def _value(fuel: str, gas: float | None) -> float:
    return gas_value(gas) if fuel == "gas_m3" else HEATING_VALUE[fuel]


def _unit_factor(unit: str, source: str | None, eff: float, gas: float | None = None) -> float | None:
    """The factor of a meter by its unit; None when the unit tells nothing."""
    u = str(unit or "").strip().lower().replace("^3", "³").replace("3", "³") if unit else ""
    if u in ("m³",):
        return round(gas_value(gas) * eff, 3)
    loss = 1.0 if source in _NO_LOSS else eff  # a heat meter / an electric heater has no burner
    per_kwh = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0, "mj": 1 / 3.6, "gj": 1000 / 3.6}.get(u)
    return None if per_kwh is None else round(per_kwh * loss, 4)


def default_fuel(conf: dict) -> str:
    """An instance saved before 0.49.0 keeps its number ("custom"); a new one starts on "auto"."""
    if conf.get("heat_fuel") in FUELS:
        return conf["heat_fuel"]
    return "custom" if conf.get("energy_factor") is not None else "auto"


def energy_factor(fuel: str | None, efficiency_pct: float | None, unit: str | None, source: str | None,
                  typed: float | None, gas: float | None = None) -> float:
    """kWh of heat per metered unit. `typed`: the number in the field (kept for "custom" and when nothing is known);
    `gas`: the natural gas's heating value in kWh/m³ (0.52.0; None = 9.61)."""
    fallback = float(typed) if typed not in (None, "") else DEFAULT_FACTOR
    eff = max(0.1, min(1.2, float(efficiency_pct if efficiency_pct is not None else DEFAULT_EFFICIENCY) / 100.0))
    if fuel in HEATING_VALUE:
        return round(_value(fuel, gas) * (1.0 if fuel == "electric_kwh" else eff), 3)
    if fuel != "auto":
        return fallback
    if unit and (f := _unit_factor(unit, source, eff, gas)) is not None:
        return f
    if source in _BURNERS:
        return round(_value(_BURNERS[source], gas) * eff, 3)
    if source in _NO_LOSS:
        return 1.0
    return fallback  # a heat pump (its COP) or an unknown source: the typed number

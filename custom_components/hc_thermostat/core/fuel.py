"""0.49.0: the heat per metered unit (energy_factor) from a fuel and an efficiency, instead of a number to work out.

"auto" reads the heat meter's unit (m³ gas, kWh, MJ, GJ) and, without a meter, the heat source; "custom" keeps the
number typed in. The result is what HC always used: kWh of heat per one unit the meter (or the price) counts.
"""

from __future__ import annotations

FUELS = ("auto", "gas_m3", "lpg_kg", "oil_l", "pellet_kg", "electric_kwh", "custom")
# kWh per unit (lower heating value); natural gas: the Hungarian bills' 34.6 MJ/m³
HEATING_VALUE = {"gas_m3": 9.61, "lpg_kg": 12.8, "oil_l": 10.0, "pellet_kg": 4.8, "electric_kwh": 1.0}
DEFAULT_EFFICIENCY = 90.0  # % – a burner's typical seasonal efficiency
DEFAULT_FACTOR = 8.55  # the factor every instance had before 0.49.0
_BURNERS = {"onoff_boiler": "gas_m3", "modulating_boiler": "gas_m3", "pellet_boiler": "pellet_kg"}
_NO_LOSS = ("electric_heater", "electric_boiler", "storage_heater", "district_heating")  # 1 kWh in = 1 kWh of heat


def _unit_factor(unit: str, source: str | None, eff: float) -> float | None:
    """The factor of a meter by its unit; None when the unit tells nothing."""
    u = str(unit or "").strip().lower().replace("^3", "³").replace("3", "³") if unit else ""
    if u in ("m³",):
        return round(HEATING_VALUE["gas_m3"] * eff, 3)
    loss = 1.0 if source in _NO_LOSS else eff  # a heat meter / an electric heater has no burner
    per_kwh = {"wh": 0.001, "kwh": 1.0, "mwh": 1000.0, "mj": 1 / 3.6, "gj": 1000 / 3.6}.get(u)
    return None if per_kwh is None else round(per_kwh * loss, 4)


def default_fuel(conf: dict) -> str:
    """An instance saved before 0.49.0 keeps its number ("custom"); a new one starts on "auto"."""
    if conf.get("heat_fuel") in FUELS:
        return conf["heat_fuel"]
    return "custom" if conf.get("energy_factor") is not None else "auto"


def energy_factor(fuel: str | None, efficiency_pct: float | None, unit: str | None, source: str | None,
                  typed: float | None) -> float:
    """kWh of heat per metered unit. `typed`: the number in the field (kept for "custom" and when nothing is known)."""
    fallback = float(typed) if typed not in (None, "") else DEFAULT_FACTOR
    eff = max(0.1, min(1.2, float(efficiency_pct if efficiency_pct is not None else DEFAULT_EFFICIENCY) / 100.0))
    if fuel in HEATING_VALUE:
        return round(HEATING_VALUE[fuel] * (1.0 if fuel == "electric_kwh" else eff), 3)
    if fuel != "auto":
        return fallback
    if unit and (f := _unit_factor(unit, source, eff)) is not None:
        return f
    if source in _BURNERS:
        return round(HEATING_VALUE[_BURNERS[source]] * eff, 3)
    if source in _NO_LOSS:
        return 1.0
    return fallback  # a heat pump (its COP) or an unknown source: the typed number

"""0.51.0: an estimate of the building's energy rating by the Hungarian rules in force since 2024 (9/2023. (V. 25.)
ÉKM rendelet) – from the learned house model, not a certificate.

    heat (useful)  = Σ days 24 h × max(0, H × (20 °C − outdoor) − free heat)      the outdoor daily means of a year
    final energy   = heat ÷ efficiency (burner) | ÷ SCOP (heat pump, AC) | as is (electric, district heat)
                     + hot water (final, kWh/year) + auxiliary electricity (kWh/year)
    Ep             = Σ final × non-renewable primary factor ÷ floor area           kWh/m²·year

The scale (upper limits, kWh/m²·year; "A" = 76 = 100 %): A+++ 0 · A++ 38 · A+ 68 · A 76 · B 98.8 · C 122 · D 152 ·
E 190 · F 236 · G 296 · H 380 · I above (Magyar Épületgépészet 2024/11-12, Csoknyai: the ÉKM residential scale).
Primary factors (fnren): natural gas and other fossil fuels 1.1, electricity 2.3, district heat 1.38, solid biomass
0.6. Lighting does not count for a home. A certificate uses a standard climate, the layers of the walls and the
useful floor area – this is only a guide; the band is the loss factor ± 15 %.
"""

from __future__ import annotations

from datetime import date, timedelta

SCALE: tuple[tuple[float, str], ...] = (
    (0.0, "A+++"), (38.0, "A++"), (68.0, "A+"), (76.0, "A"), (98.8, "B"), (122.0, "C"), (152.0, "D"),
    (190.0, "E"), (236.0, "F"), (296.0, "G"), (380.0, "H"),
)
REFERENCE = 76.0  # kWh/m²·year = 100 %
FNREN = {"gas": 1.1, "electricity": 2.3, "district": 1.38, "biomass": 0.6}
BAND = 0.15
INDOOR = 20.0
MIN_DAYS = 300  # a measured year needs this many daily means, else the standard climate
# A standard Hungarian year (approximate monthly means, °C) when the outdoor sensor has no year of statistics
STANDARD_MONTHS = (-0.5, 1.5, 6.0, 11.5, 16.5, 20.0, 22.0, 21.5, 16.5, 11.0, 5.5, 1.0)
_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_BURNERS = ("onoff_boiler", "modulating_boiler", "pellet_boiler")
_ELECTRIC = ("electric_heater", "electric_boiler", "storage_heater")
_COP = ("heat_pump", "air_conditioner")


def standard_year() -> list[float]:
    return [t for t, n in zip(STANDARD_MONTHS, _DAYS) for _ in range(n)]


def grade(ep: float) -> str:
    for limit, name in SCALE:
        if ep <= limit:
            return name
    return "I"


def carrier(source: str | None, fuel: str | None) -> str | None:
    """The energy carrier of a heat source (None: unknown – a primary factor must be given)."""
    if source in _ELECTRIC or source in _COP or fuel == "electric_kwh":
        return "electricity"
    if source == "district_heating":
        return "district"
    if source == "pellet_boiler" or fuel == "pellet_kg":
        return "biomass"
    if source in _BURNERS or fuel in ("gas_m3", "lpg_kg", "oil_l"):
        return "gas"
    return None


def conversion(source: str | None, efficiency_pct: float | None, cop_high: float, cop_low: float) -> float:
    """Final energy per useful heat."""
    if source in _COP:
        return 1.0 / max(1.0, (cop_high + cop_low) / 2)
    if source in _BURNERS:
        return 100.0 / max(10.0, float(efficiency_pct or 90.0))
    return 1.0


def heat_kwh(loss_kw_per_k: float, gains_kw: float, outdoor_days: list[float]) -> float:
    return sum(24.0 * max(0.0, loss_kw_per_k * (INDOOR - t) - gains_kw) for t in outdoor_days)


def rating(loss_kw_per_k: float | None, gains_kw: float, area_m2: float, *, source: str | None,
           fuel: str | None = None, efficiency_pct: float | None = None, cop_high: float = 4.0, cop_low: float = 2.4,
           dhw_kwh: float = 0.0, aux_kwh: float = 0.0, primary_factor: float = 0.0,
           outdoor_days: list[float] | None = None, measured_days: int | None = None) -> dict | None:
    """The estimate, or None (no floor area, no loss factor, unknown carrier without a factor)."""
    if not area_m2 or area_m2 <= 0 or loss_kw_per_k is None or loss_kw_per_k <= 0:
        return None
    kind = carrier(source, fuel)
    fnren = primary_factor if primary_factor and primary_factor > 0 else FNREN.get(kind) if kind else None
    if fnren is None:
        return None
    if measured_days is not None and outdoor_days:
        # 0.51.2: a year of days filled by year_of() – the missing days are the standard climate's
        days = list(outdoor_days)[-365:]
        climate = "measured" if measured_days >= MIN_DAYS else "mixed" if measured_days > 0 else "standard"
    else:
        measured_days = len(outdoor_days) if outdoor_days is not None and len(outdoor_days) >= MIN_DAYS else 0
        days = list(outdoor_days)[-365:] if measured_days else standard_year()
        climate = "measured" if measured_days else "standard"
    per_heat = conversion(source, efficiency_pct, cop_high, cop_low)
    aux_factor = FNREN["electricity"]

    def ep_of(loss: float) -> float:
        final = heat_kwh(loss, max(gains_kw, 0.0), days) * per_heat + max(dhw_kwh, 0.0)
        return (final * fnren + max(aux_kwh, 0.0) * aux_factor) / area_m2

    ep = ep_of(loss_kw_per_k)
    low, high = ep_of(loss_kw_per_k * (1 - BAND)), ep_of(loss_kw_per_k * (1 + BAND))
    heat = heat_kwh(loss_kw_per_k, max(gains_kw, 0.0), days)
    return {"ep": round(ep, 1), "grade": grade(ep), "percent": round(100 * ep / REFERENCE),
            "ep_low": round(low, 1), "ep_high": round(high, 1), "grade_low": grade(low), "grade_high": grade(high),
            "heat_kwh": round(heat), "final_kwh": round(heat * per_heat + max(dhw_kwh, 0.0)),
            "primary_factor": fnren, "carrier": kind, "climate": climate, "measured_days": min(measured_days, len(days)),
            "days": len(days), "area_m2": area_m2}


def year_of(rows: list[tuple[date, float]], today: date) -> tuple[list[float], int]:
    """0.51.2: the 365 days before `today` – a measured daily mean where there is one, else the standard climate's
    monthly mean for that day; and how many days were measured."""
    seen = {d: float(v) for d, v in rows if v is not None}
    days, measured = [], 0
    for back in range(365, 0, -1):
        day = today - timedelta(days=back)
        if day in seen:
            days.append(seen[day])
            measured += 1
        else:
            days.append(STANDARD_MONTHS[day.month - 1])
    return days, measured


def daily_means(rows: list[tuple[date, float]]) -> list[float]:
    """Outdoor daily means in date order (one per day)."""
    seen: dict[date, float] = {}
    for d, v in rows:
        if v is not None:
            seen[d] = float(v)
    return [seen[d] for d in sorted(seen)]

"""Which heat source is cheaper now, in money per kWh of heat. It only advises."""

from __future__ import annotations

from dataclasses import dataclass

_MARGIN = 0.05
_T_HIGH, _T_LOW = 7.0, -7.0


def cop_at(outdoor: float, cop_high: float, cop_low: float) -> float:
    """Linear between the two rating points, flat outside them, never below direct electric heat."""
    t = max(_T_LOW, min(_T_HIGH, outdoor))
    return max(cop_low + (cop_high - cop_low) * (t - _T_LOW) / (_T_HIGH - _T_LOW), 1.0)


@dataclass(frozen=True)
class CostAdvice:
    advice: str  # boiler | other | other_zone_only | equal | unknown
    boiler_cost: float | None = None
    other_cost: float | None = None
    cop: float | None = None
    breakeven_outdoor: float | None = None
    other_always: bool | None = None  # True: cheaper even at -7 °C, False: dearer even at +7 °C
    saving_per_hour: float | None = None


def compare(boiler_price: float | None, energy_factor: float, other_price: float | None, outdoor: float | None,
            cop_high: float, cop_low: float, need_kw: float | None, reaches_house: bool) -> CostAdvice:
    if not boiler_price or not other_price or outdoor is None or energy_factor <= 0:
        return CostAdvice("unknown")
    boiler_cost = boiler_price / energy_factor
    cop = cop_at(outdoor, cop_high, cop_low)
    other_cost = other_price / cop
    breakeven, always = None, None
    needed = other_price / boiler_cost  # the COP at which both cost the same
    if needed <= min(cop_low, cop_high):
        always = True
    elif needed >= max(cop_low, cop_high):
        always = False
    elif cop_high > cop_low:
        breakeven = round(_T_LOW + (_T_HIGH - _T_LOW) * (needed - cop_low) / (cop_high - cop_low), 1)
    difference = abs(boiler_cost - other_cost)
    saving = None if need_kw is None else round(difference * need_kw, 1)
    if difference <= _MARGIN * min(boiler_cost, other_cost):
        advice = "equal"
    elif boiler_cost < other_cost:
        advice = "boiler"
    else:
        advice = "other" if reaches_house else "other_zone_only"
    return CostAdvice(advice, round(boiler_cost, 2), round(other_cost, 2), round(cop, 2), breakeven, always, saving)


ADVICE_TEXT = {
    "boiler": {"hu": "Most a kazán az olcsóbb hő.", "en": "The boiler gives the cheaper heat now."},
    "other": {"hu": "Most a másik hőforrás az olcsóbb, és eléri a házat.", "en": "The other source is cheaper now and reaches the house."},
    "other_zone_only": {"hu": "A másik hőforrás olcsóbb, de most csak a saját terét fűti.", "en": "The other source is cheaper, but it only heats its own room now."},
    "equal": {"hu": "A két hőforrás most kb. egyformán kerül.", "en": "The two sources cost about the same now."},
    "unknown": {"hu": "Nincs elég adat az összehasonlításhoz.", "en": "Not enough data to compare."},
}

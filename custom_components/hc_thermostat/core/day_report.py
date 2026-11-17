"""0.71.0 – the numbers of a day for the AI analysis of a house. Worked out by HC from the recorder, before any AI
sees them (the AI only explains them and suggests; it never sets anything).

Input everywhere: a list of (time, value) pairs sorted by time, the value holding until the next pair (a step
function); the day is [start, end). Values may be None (unavailable) – those stretches do not count.
"""

from __future__ import annotations

from datetime import datetime

UNDER_C = 0.3  # a room this far below its target counts as cold
OVER_C = 0.5  # and this far above as overheated


def _spans(points: list, start: datetime, end: datetime):
    """(value, seconds) for every stretch of the day, the value before `start` carried in."""
    if not points:
        return
    last = None
    for t, v in points:
        if t <= start:
            last = v
            continue
        break
    cur_t, cur_v = start, last
    for t, v in points:
        if t <= start:
            continue
        if t >= end:
            break
        if (t - cur_t).total_seconds() > 0:
            yield cur_v, (t - cur_t).total_seconds()
        cur_t, cur_v = t, v
    if (end - cur_t).total_seconds() > 0:
        yield cur_v, (end - cur_t).total_seconds()


def number_stats(points: list, start: datetime, end: datetime) -> dict | None:
    """Time-weighted mean, min and max of a numeric series; None without data."""
    total = weighted = 0.0
    lo = hi = None
    for v, s in _spans(points, start, end):
        if not isinstance(v, (int, float)):
            continue
        total += s
        weighted += v * s
        lo = v if lo is None else min(lo, v)
        hi = v if hi is None else max(hi, v)
    if total <= 0:
        return None
    return {"mean": round(weighted / total, 2), "min": round(lo, 2), "max": round(hi, 2),
            "hours": round(total / 3600, 2)}


def durations(points: list, start: datetime, end: datetime, top: int = 8) -> dict:
    """Hours spent in each state (the longest `top`), unavailable ones left out."""
    out: dict[str, float] = {}
    for v, s in _spans(points, start, end):
        if v in (None, "unavailable", "unknown"):
            continue
        out[str(v)] = out.get(str(v), 0.0) + s / 3600
    ranked = sorted(out.items(), key=lambda kv: -kv[1])[:top]
    return {k: round(h, 2) for k, h in ranked if h >= 0.01}


def on_stats(points: list, start: datetime, end: datetime) -> dict:
    """An on/off series: hours on and the number of starts (off → on) within the day."""
    hours, starts, prev = 0.0, 0, None
    for v, s in _spans(points, start, end):
        on = v is True or v == "on"
        if on:
            hours += s
        if on and prev is False:
            starts += 1
        if v is not None and v not in ("unavailable", "unknown"):
            prev = on
    return {"hours": round(hours / 3600, 2), "starts": starts}


def climate_stats(points: list, start: datetime, end: datetime) -> dict:
    """A HC thermostat's day from (time, (state, room temperature, target, hvac_action, preset)) pairs."""
    temps, targets, heating, presets = [], [], [], []
    for t, v in points:
        state, room, target, action, preset = v if isinstance(v, tuple) else (None,) * 5
        temps.append((t, room if state not in (None, "unavailable", "unknown") else None))
        targets.append((t, target if state not in (None, "unavailable", "unknown", "off") else None))
        heating.append((t, None if state in (None, "unavailable", "unknown") else action == "heating"))
        presets.append((t, preset or (state if state == "off" else None)))
    cold = hot = 0.0
    for (room, s), (tgt, _s) in zip(_spans(temps, start, end), _spans(targets, start, end)):
        if isinstance(room, (int, float)) and isinstance(tgt, (int, float)):
            if room < tgt - UNDER_C:
                cold += s
            elif room > tgt + OVER_C:
                hot += s
    return {"room": number_stats(temps, start, end), "target": number_stats(targets, start, end),
            "cold_h": round(cold / 3600, 2), "overheated_h": round(hot / 3600, 2),
            "heating": on_stats(heating, start, end), "presets": durations(presets, start, end)}


def energy_kwh_from_power(points: list, start: datetime, end: datetime, to_kw: float = 0.001) -> float | None:
    """A power reading (W by default) integrated over the day, kWh; None without data."""
    total, seen = 0.0, False
    for v, s in _spans(points, start, end):
        if isinstance(v, (int, float)):
            total += max(v, 0.0) * to_kw * s / 3600
            seen = True
    return round(total, 2) if seen else None


def meter_delta(points: list, start: datetime, end: datetime) -> float | None:
    """A cumulative meter's growth over the day: the sum of its rises (a reset to zero does not count as minus)."""
    before = [v for t, v in points if t <= start and isinstance(v, (int, float))]
    vals = before[-1:] + [v for t, v in points if start < t <= end and isinstance(v, (int, float))]
    if len(vals) < 2:
        return None
    rise = sum(b - a for a, b in zip(vals, vals[1:]) if b > a)
    return round(rise, 3)


def energy_and_cost(heating_h: float | None, power_kw: float, measured_fuel: float | None, energy_factor: float,
                    price: float | None, electric_kwh: float | None, electric: bool) -> dict:
    """The day's energy and cost from what is known, saying how (measured / estimated)."""
    out: dict = {}
    if electric:
        kwh = electric_kwh
        how = "measured" if kwh is not None else None
        if kwh is None and heating_h and power_kw > 0:
            kwh, how = round(heating_h * power_kw, 2), "estimated"
        if kwh is not None:
            out.update(electric_kwh=kwh, how=how)
            if price:
                out["cost"] = round(kwh * price, 0)
        return out
    fuel = measured_fuel
    how = "measured" if fuel is not None else None
    if fuel is None and heating_h and power_kw > 0 and energy_factor > 0:
        fuel, how = round(heating_h * power_kw / energy_factor, 3), "estimated"
    if fuel is not None:
        out.update(fuel=fuel, heat_kwh=round(fuel * energy_factor, 1) if energy_factor > 0 else None, how=how)
        if price:
            out["cost"] = round(fuel * price, 0)
    return out


def parse_lines(text) -> list[str]:
    """The AI's list fields come as text, one item a line, maybe with "•" / "-" / "1." in front."""
    if isinstance(text, list):
        items = [str(x) for x in text]
    else:
        items = str(text or "").splitlines()
    out = []
    for line in items:
        line = line.strip().lstrip("•-*–").strip()
        if len(line) > 2 and line[0].isdigit() and line[1] in ".)":
            line = line[2:].strip()
        if line and line.lower() not in ("nincs", "nincs teendő.", "nincs teendő", "none", "nothing to do."):
            out.append(line)
    return out

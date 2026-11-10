"""Floor cooling with dew point protection (0.29.0) – a reversible heat pump cools through the floor in summer.

Water colder than the dew point of the room air makes the floor wet (condensation, slippery tiles, mould), so:

- the dew point comes from the room temperature and relative humidity (Magnus formula); without a fresh
  humidity reading there is no cooling at all;
- the safe flow is dew point + `dew_margin` (2 °C). In curve control the flow setpoint is `cool_flow` (18 °C)
  raised to the safe flow; when even that is above `cool_flow_max` (22 °C, the floor would hardly cool) the
  cooling stops ("too humid");
- with a floor sensor: cooling stops when the floor reaches the safe flow or `floor_min_cool` (19 °C, comfort),
  and resumes 0.5 °C above it. On/off control does not know the heat pump's flow, so there the floor sensor is
  required;
- cooling starts above `target_cool` + 0.5 °C and keeps on until the room falls below `target_cool` − 0.5 °C.
"""

from __future__ import annotations

import math

_A, _B = 17.62, 243.12
RESUME = 0.5


def dew_point(temp: float, rh: float) -> float | None:
    """Dew point in °C of air at `temp` °C and `rh` % relative humidity (Magnus); None for nonsense input."""
    if rh is None or temp is None or not 0 < rh <= 100:
        return None
    gamma = math.log(rh / 100.0) + _A * temp / (_B + temp)
    return round(_B * gamma / (_A - gamma), 1)


class DewGuard:
    """Decides whether the floor may be cooled now, and with which flow."""

    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.cooling = False  # the room asks for cooling (with hysteresis)
        self.blocked = False  # stopped by the dew point / floor (with hysteresis)

    def wants(self, indoor: float) -> bool:
        cfg = self.cfg
        if indoor >= cfg.target_cool + RESUME:
            self.cooling = True
        elif indoor <= cfg.target_cool - RESUME:
            self.cooling = False
        return self.cooling

    def check(self, indoor: float | None, rh: float | None, floor: float | None, curve: bool) -> dict:
        """{"ok": bool, "why": None | lost | humid | floor | no_floor, "dew_point", "safe_flow", "flow"}."""
        cfg = self.cfg
        dew = dew_point(indoor, rh) if indoor is not None and rh is not None else None
        out: dict = {"dew_point": dew, "humidity": rh, "floor": floor}
        if dew is None:
            self.blocked = False
            return {**out, "ok": False, "why": "lost"}
        safe = round(dew + cfg.dew_margin, 1)
        out["safe_flow"] = safe
        if curve:
            flow = math.ceil(max(cfg.cool_flow, safe) * 2) / 2  # up to the next half degree
            out["flow"] = flow
            if flow > cfg.cool_flow_max:
                return {**out, "ok": False, "why": "humid"}
        elif floor is None:
            return {**out, "ok": False, "why": "no_floor"}
        if floor is not None:
            limit = max(safe, cfg.floor_min_cool)
            if floor <= limit:
                self.blocked = True
            elif floor >= limit + RESUME:
                self.blocked = False
            if self.blocked:
                return {**out, "ok": False, "why": "floor", "floor_limit": limit}
        else:
            self.blocked = False
        return {**out, "ok": True, "why": None}

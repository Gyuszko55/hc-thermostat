"""Fan coil (0.32.0): the water valve is switched by TPI / PID like any relay; the fan follows it.

- while the valve is open the fan runs at `fan_min_pct` + (100 − `fan_min_pct`) × demand (rounded to 5 %);
- after the valve closes the fan runs on for `fan_overrun_s` (the coil is still warm) at the lowest speed;
- with a coil (or supply) temperature sensor the fan waits until the coil is at least `fan_min_coil` warm, so it
  does not blow cold air into the room at the start;
- 0 % means off.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def fan_level(pct: int, step: float | None) -> tuple[int, int]:
    """0.39.3: (speed level, percentage to send) for a fan with speed steps – `percentage_step` is 33.3 for three
    speeds. A wanted 45 % is level 1 of 3; the fan reports 33 %, which must count as "already there", or the same
    command is sent again at every update. No (or a fine) step: the percentage as it is."""
    if pct <= 0:
        return 0, 0
    if not step or step <= 5:
        return pct, pct
    levels = max(1, round(100.0 / step))
    level = max(1, min(levels, round(pct / step)))
    return level, min(100, int(level * 100.0 / levels + 1e-6))  # 33, 66, 100: the floor, as Home Assistant maps it


def fan_at_level(current, level: int, step: float | None) -> bool:
    """Does the fan's reported percentage already mean this level?"""
    if not isinstance(current, (int, float)):
        return False
    if not step or step <= 5:
        return int(current) == level
    return round(current / step) == level


class FanCoil:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.overrun_until: datetime | None = None
        self._was_open = False

    def step(self, now: datetime, valve_open: bool, demand: float, coil: float | None) -> tuple[int, str]:
        """(fan %, why): why = heating | overrun | cold_coil | off."""
        cfg = self.cfg
        if valve_open:
            self._was_open, self.overrun_until = True, None
            if coil is not None and coil < cfg.fan_min_coil:
                return 0, "cold_coil"
            pct = cfg.fan_min_pct + (100.0 - cfg.fan_min_pct) * max(0.0, min(1.0, demand))
            return int(round(pct / 5.0) * 5), "heating"
        if self._was_open:
            self._was_open = False
            self.overrun_until = now + timedelta(seconds=cfg.fan_overrun_s) if cfg.fan_overrun_s > 0 else None
        if self.overrun_until is not None and now < self.overrun_until:
            return int(cfg.fan_min_pct), "overrun"
        self.overrun_until = None
        return 0, "off"

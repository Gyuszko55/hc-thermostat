"""Fan coil (0.32.0): the water valve is switched by TPI / PID like any relay; the fan follows it.

- while the valve is open the fan runs at `fan_min_pct` + (100 − `fan_min_pct`) × demand (rounded to 5 %);
- after the valve closes the fan runs on for `fan_overrun_s` (the coil is still warm) at the lowest speed;
- with a coil (or supply) temperature sensor the fan waits until the coil is at least `fan_min_coil` warm, so it
  does not blow cold air into the room at the start;
- 0 % means off.
"""

from __future__ import annotations

from datetime import datetime, timedelta


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

"""Storage heater on controlled (off-peak) power (0.31.0).

A storage heater charges its core while the cheap controlled power is on (typically at night) and gives the heat
off during the day – by itself, or through a fan / damper the HC switches (`discharge_entity`).

Charging:
- the charge window is `storage_window_start`–`storage_window_end` (22:00–06:00 by default); an optional
  `power_available_entity` (the provider's signal, or a relay of the controlled circuit) must also be on;
- how much: `fraction` = (target − outdoor) / (target − design outdoor), from the outdoor daily average, plus the
  user's `storage_bias`, clamped to 0..1 (no outdoor reading: full charge – the safe side). In the heating season
  only; frost charges full;
- when: the charge takes fraction × `storage_charge_h` hours and ends at the end of the window (the heat is fresh
  in the morning, less is lost overnight). The fraction is fixed once the charge has started, so the relay does not
  flap when the outdoor average moves;
- with a power signal (0.39.3): controlled power often comes in blocks, and a block that ends inside a charge timed
  to the end of the window would be lost. So the hours really charged are counted (relay on while the power is on),
  and the charge is on whenever the power is on inside the window until the hours are full – no waiting for the
  end of the window, the next block may not come.

Discharge (only with a discharge entity): on when the room is `storage_discharge_hyst` below the target, off at the
target; off with an open window, out of season and while switched off; frost always on.
"""

from __future__ import annotations

from datetime import datetime, timedelta


_MAX_STEP_S = 600.0


def _at(day: datetime, hhmm: str) -> datetime:
    h, m = (int(x) for x in str(hhmm).split(":")[:2])
    return day.replace(hour=h, minute=m, second=0, microsecond=0)


def window(now: datetime, start: str, end: str) -> tuple[datetime, datetime]:
    """The current (or the next) charge window as datetimes; it may run over midnight."""
    s, e = _at(now, start), _at(now, end)
    if e <= s:  # over midnight
        if now < e:
            s -= timedelta(days=1)
        else:
            e += timedelta(days=1)
    elif now >= e:
        s, e = s + timedelta(days=1), e + timedelta(days=1)
    return s, e


def charge_fraction(target: float, outdoor_avg: float | None, design_outdoor: float, bias: float = 0.0) -> float:
    if outdoor_avg is None:
        return 1.0
    span = max(target - design_outdoor, 1.0)
    return round(max(0.0, min(1.0, (target - outdoor_avg) / span + bias)), 2)


class StorageCharger:
    def __init__(self, cfg) -> None:
        self.cfg = cfg
        self.locked: float | None = None  # fraction fixed for the running charge
        self.locked_for: str | None = None  # window start of that charge
        self.charged_s = 0.0  # with a power signal: seconds really charged in this window
        self.charged_for: str | None = None
        self._last: datetime | None = None
        self._was_charging = False

    def _count(self, now: datetime, key: str, power: bool | None) -> None:
        """Add the time since the last step when the relay was on and the power is still there."""
        if self.charged_for != key:
            self.charged_s, self.charged_for = 0.0, key
        elif self._was_charging and power is True and self._last is not None:
            dt = (now - self._last).total_seconds()
            if 0 < dt <= _MAX_STEP_S:  # a long gap is a restart or an outage: not counted, rather charge more
                self.charged_s += dt
        self._last = now

    def step(self, now: datetime, fraction: float, power: bool | None) -> dict:
        """{"charge": bool, "fraction", "start", "end", "why"}; why: charging | waiting | done | no_power | none."""
        cfg = self.cfg
        s, e = window(now, cfg.storage_window_start, cfg.storage_window_end)
        key = s.isoformat()
        self._count(now, key, power)
        self._was_charging = False
        if self.locked_for == key and self.locked is not None:
            fraction = self.locked
        hours = fraction * cfg.storage_charge_h
        signal = power is not None
        # With a power signal the charge takes every block of power from the start of the window.
        start = s if signal else max(s, e - timedelta(hours=hours))
        out = {"fraction": fraction, "start": start, "end": e}
        if signal:
            out["charged_h"] = round(self.charged_s / 3600, 2)
        if fraction <= 0:
            return {**out, "charge": False, "why": "none"}
        if not s <= now < e or now < start:
            return {**out, "charge": False, "why": "waiting"}
        if signal and self.charged_s >= hours * 3600:
            return {**out, "charge": False, "why": "done"}
        if power is False:
            return {**out, "charge": False, "why": "no_power"}
        self.locked, self.locked_for = fraction, key
        self._was_charging = True
        return {**out, "charge": True, "why": "charging"}

    def state(self) -> dict:
        return {"locked": self.locked, "locked_for": self.locked_for, "charged_s": round(self.charged_s),
                "charged_for": self.charged_for}

    def restore(self, data: dict) -> None:
        self.locked = data.get("locked")
        self.locked_for = data.get("locked_for")
        self.charged_s = float(data.get("charged_s") or 0.0)
        self.charged_for = data.get("charged_for")


class Discharge:
    def __init__(self) -> None:
        self.on = False

    def step(self, indoor: float | None, target: float, hyst: float, allowed: bool, frost: bool) -> bool:
        if frost:
            self.on = True
        elif not allowed or indoor is None:
            self.on = False
        elif indoor <= target - hyst:
            self.on = True
        elif indoor >= target:
            self.on = False
        return self.on

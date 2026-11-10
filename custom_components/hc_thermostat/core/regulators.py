"""Heat demand regulators (0..1). PWM turns the demand into on/off, see pwm.py."""

from __future__ import annotations

from datetime import datetime

from .model import HcConfig


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class TpiRegulator:
    """Time proportional: indoor error plus outdoor compensation."""

    def __init__(self, cfg: HcConfig) -> None:
        self._cfg = cfg
        self.coef_int: float | None = None  # learned strength; None = the configured one
        self.offset = 0.0  # learned holding offset

    def update(self, target: float, indoor: float, outdoor: float | None, now: datetime,
               feedforward: float | None = None) -> float:
        ext = feedforward if feedforward is not None else (
            0.0 if outdoor is None else self._cfg.tpi_coef_ext * (target - outdoor))
        coef = self.coef_int if self.coef_int is not None else self._cfg.tpi_coef_int
        return _clamp(coef * (target - indoor) + ext + self.offset)

    def hold(self, now: datetime) -> None:
        """Nothing to freeze."""

    def state(self) -> dict:
        return {}

    def restore(self, data: dict) -> None:
        """Stateless."""


class PidRegulator:
    """PID with anti-windup and derivative on measurement."""

    def __init__(self, cfg: HcConfig) -> None:
        self._cfg = cfg
        self.integral = 0.0
        self._last: datetime | None = None
        self._last_indoor: float | None = None

    def update(self, target: float, indoor: float, outdoor: float | None, now: datetime,
               feedforward: float | None = None) -> float:
        cfg = self._cfg
        dt = 0.0 if self._last is None else max((now - self._last).total_seconds(), 0.0)
        error = target - indoor
        derivative = 0.0
        if dt > 0 and self._last_indoor is not None:
            derivative = -(indoor - self._last_indoor) / dt
        ext = feedforward if feedforward is not None else (
            0.0 if outdoor is None else cfg.pid_ke * (target - outdoor))
        base = cfg.pid_kp * error + cfg.pid_kd * derivative + ext
        ki = cfg.pid_ki_per_hour / 3600 if cfg.pid_ki_per_hour is not None else cfg.pid_ki
        candidate = self.integral + ki * error * dt
        # Anti-windup: the integral may only grow while the output has room for it.
        if 0.0 <= base + candidate <= 1.0:
            self.integral = candidate
        elif base + self.integral > 1.0:
            self.integral = min(self.integral, max(1.0 - base, 0.0))
        elif base + self.integral < 0.0:
            self.integral = max(self.integral, min(-base, 0.0))
        self._last, self._last_indoor = now, indoor
        return _clamp(base + self.integral)

    def hold(self, now: datetime) -> None:
        self._last, self._last_indoor = now, None

    def state(self) -> dict:
        return {"integral": self.integral}

    def restore(self, data: dict) -> None:
        self.integral = float(data.get("integral", 0.0))


def make_regulator(cfg: HcConfig, control: str | None = None):
    return PidRegulator(cfg) if (control or cfg.control) == "pid" else TpiRegulator(cfg)


def shadow_control(cfg: HcConfig) -> str:
    """The other algorithm, calculated next to the live one."""
    return "tpi" if cfg.control == "pid" else "pid"


def controller_attributes(cfg, sup, demand: float, now) -> dict:
    """The settings and the inner state of the controller, readable like the Smart Thermostat's (0.24.0):
    the target of each preset (<preset>_temp), the night of the schedule, the preset auto follows now, and
    kp / ki / kd / ke / pid_i for PID or the TPI coefficients – for templates, cards and the daily evaluation."""
    out = {
        "comfort_temp": cfg.target_comfort, "home_temp": cfg.target_home, "sleep_temp": cfg.target_night,
        "eco_temp": cfg.target_eco, "away_temp": cfg.target_away, "vacation_temp": cfg.target_vacation,
        "night_start": str(cfg.night_start)[:5], "night_end": str(cfg.night_end)[:5],  # HH:MM (the options store HH:MM:SS)
        "active_preset": sup.active_preset(now),
        "control_output": round(demand * 100, 1),  # %, the same as demand, under the Smart Thermostat's name
    }
    reg = sup.regulator
    if cfg.control == "pid":
        ki_h = cfg.pid_ki_per_hour if cfg.pid_ki_per_hour is not None else cfg.pid_ki * 3600
        out.update(kp=cfg.pid_kp, ki=round(ki_h, 4), ki_unit="1/h", kd=cfg.pid_kd, ke=cfg.pid_ke,
                   pid_i=round(getattr(reg, "integral", 0.0) * 100, 2))
    elif cfg.control == "tpi":
        coef = getattr(reg, "coef_int", None)
        out.update(tpi_coef_int=round(coef if coef is not None else cfg.tpi_coef_int, 3),
                   tpi_coef_ext=cfg.tpi_coef_ext, tpi_offset=round(getattr(reg, "offset", 0.0) * 100, 2))
    elif cfg.control == "onoff":
        out.update(onoff_hysteresis=cfg.onoff_hysteresis, overshoot_stop=cfg.overshoot_stop)
    if cfg.heat_pump and cfg.control in ("curve", "onoff"):
        out.update(hp_min_on_s=cfg.hp_min_on_s, hp_min_off_s=cfg.hp_min_off_s)
    return out

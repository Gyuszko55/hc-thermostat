"""House level decisions: what the heating should do now, and why.

Priority, highest first: device limits (in pwm.py) > frost > lost sensor > off >
open window > season > restart protection > boost > regulation.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, time, timedelta

from .cooling import DewGuard
from .fancoil import FanCoil
from .storage import Discharge, StorageCharger, charge_fraction
from .curve import CurveRegulator, RunGate
from .exercise import ValveExercise
from .flatline import FrozenSensor
from .heat_need import HeatNeedEstimator
from .learning import Learner
from .window_drop import DropDetector
from .model import Decision, ExternalCommand, HcConfig, Inputs, Presence, Reason
from .pwm import Pwm
from .regulators import make_regulator, shadow_control
from .ac import AcController

_REARM_OFF_S = 1800.0


def _parse_time(text: str) -> time:
    parts = [int(p) for p in str(text).split(":")]
    return time(parts[0], parts[1] if len(parts) > 1 else 0)


class Supervisor:
    def __init__(self, cfg: HcConfig) -> None:
        self.cfg = cfg
        self.regulator = make_regulator(cfg)
        self.shadow_kind = shadow_control(cfg)
        self.shadow_regulator = make_regulator(cfg, self.shadow_kind)
        self.ac = AcController(cfg.ac_ki_per_hour, cfg.ac_min_change_s)
        self.shadow_pwm = Pwm(cfg)
        self.shadow_stats: dict = {"day": None, "shadow_on_s": 0.0, "live_on_s": 0.0, "yesterday": None}
        self.pwm = Pwm(cfg)
        self.dew = DewGuard(cfg)
        self.storage = StorageCharger(cfg)  # storage heater (0.31.0)
        self.discharge = Discharge()
        self.fan = FanCoil(cfg)  # fan coil (0.32.0)
        self._return_hot = False  # district heating return limit (0.32.0)  # floor cooling with dew point protection (0.29.0)
        self.load = None  # LoadClient: shared load limit of electric zones (0.28.0), set by the coordinator
        self.learner = Learner(cfg)
        self.exercise = ValveExercise(cfg)
        self.frozen = FrozenSensor(cfg)  # 0.41.0: a room thermometer that repeats one value while heated
        self.curve = CurveRegulator(cfg)
        self._gate = RunGate()
        self._indoor_log: list[tuple[datetime, float]] = []  # 0.44.3: recent room readings (coasting)
        self._drops: dict[str, DropDetector] = {}
        self.drop_open: tuple[str, float] | None = None  # (entity, °C/h) while a drop counts as an open window
        self._window_active_flag = False
        self._boost_outdoor: float | None = None
        self._last_target: float | None = None
        self._target_since: datetime | None = None
        self.heat_need = HeatNeedEstimator()
        self.manual_target: float | None = None
        self.preset: str | None = None
        self.preset_until: datetime | None = None  # a preset chosen by hand ends here...
        self.preset_until_home = False  # ...or when someone arrives home
        self._last_presence: Presence | None = None
        self._boost_forced = False
        self.season_on = True
        self.fault = False
        self._base_target: float | None = None
        self._frost = False
        self._floor_hot = False  # the floor reached floor_max; cleared below floor_max - floor_hysteresis
        self._contact_backup = False  # the wall thermostat's contact is lost, the room thermometer regulates (0.39.3)
        self._temper_on = False  # floor tempering latch (0.35.0): on below floor target - hysteresis, off at it
        self._temper_run = False  # on/off control: the running gate was started by the tempering
        self._target_shown = 0.0
        self._pre_hold: dict | None = None  # 0.48.3: the scheduled lowering that holds a new start (see _pre_change)
        self._window_since: datetime | None = None
        self._boost_until: datetime | None = None  # safety limit of the running boost
        self._boost_armed = True
        self._boost_flame_s = 0.0
        self._boost_last: datetime | None = None
        self._boost_prior_min = 0.0  # 0.44.4: weighted burn minutes before this boost (after-heat still coming)
        self._boost_saved_at: datetime | None = None  # 0.44.4: a boost restored from storage, saved at this time
        self._flame_log: list[list] = []  # 0.44.4: recent burns [start, end or None]
        self._quiet_until: datetime | None = None
        self._quiet_cap: datetime | None = None
        self._quiet_peak: float | None = None
        self._quiet_rise: datetime | None = None
        self._quiet_target: float | None = None
        self._quiet_level = 0.0
        self._fault_temp: float | None = None
        self._fail_accum_s = 0.0
        self._fail_start_temp: float | None = None
        self._fail_off_s = 0.0
        self._fail_strikes = 0
        self._last_now: datetime | None = None

    # --- persistence -----------------------------------------------------------
    def state(self) -> dict:
        return {
            "pwm": self.pwm.state(),
            "storage": self.storage.state(),
            "regulator": self.regulator.state(),
            "ac": self.ac.state(),
            "shadow": {"regulator": self.shadow_regulator.state(), "pwm": self.shadow_pwm.state(),
                       "stats": self.shadow_stats},
            "heat_need": self.heat_need.state(),
            "learner": self.learner.state(),
            "curve": self.curve.state(),
            "exercise": self.exercise.state(),
            "manual_target": self.manual_target,
            "preset": self.preset,
            "preset_until": self.preset_until.isoformat() if self.preset_until else None,
            "preset_until_home": self.preset_until_home,
            "base_target": self._base_target,
            "season_on": self.season_on,
            "fault": self.fault,
            "fault_temp": self._fault_temp,
            "boost": self._boost_state(),
        }

    def _boost_state(self) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"until": iso(self._boost_until), "flame_s": self._boost_flame_s, "prior_min": self._boost_prior_min,
                "outdoor": self._boost_outdoor, "armed": self._boost_armed, "saved_at": iso(self._last_now),
                "quiet": [iso(self._quiet_until), iso(self._quiet_cap), self._quiet_peak, iso(self._quiet_rise),
                          self._quiet_target, self._quiet_level],
                "flames": [[iso(s), iso(e)] for s, e in self._flame_log]}

    def _restore_boost(self, data: dict) -> None:
        """0.44.4: before, a restart forgot a running boost – the next one started from zero burn minutes, with a
        fresh time limit, and the heat already in the radiators overshot the house (11-12: 22.9 °C for 22.5)."""
        when = lambda v: datetime.fromisoformat(v) if v else None  # noqa: E731
        saved = when(data.get("saved_at"))
        if saved is None:
            return
        self._boost_armed = bool(data.get("armed", True))
        if data.get("until"):
            self._boost_until, self._boost_saved_at = when(data["until"]), saved
            self._boost_flame_s = float(data.get("flame_s") or 0.0)
            self._boost_prior_min = float(data.get("prior_min") or 0.0)
            self._boost_outdoor, self._boost_last = data.get("outdoor"), None  # the downtime is not burn time
        q = data.get("quiet") or []
        if len(q) == 6 and q[0]:
            self._quiet_until, self._quiet_cap, self._quiet_peak = when(q[0]), when(q[1]), q[2]
            self._quiet_rise, self._quiet_target, self._quiet_level = when(q[3]), q[4], q[5]
        # A burn still open at the save ended then at the latest: the boiler is off during a restart.
        self._flame_log = [[when(s), when(e) or saved] for s, e in data.get("flames") or [] if s]

    def _note_flame(self, now: datetime, on: bool) -> None:
        log = self._flame_log
        if on and (not log or log[-1][1] is not None):
            log.append([now, None])
        elif not on and log and log[-1][1] is None:
            log[-1][1] = now
        cut = now - timedelta(seconds=self.cfg.boost_prior_window_s)
        self._flame_log = [b for b in log if b[1] is None or b[1] > cut]

    def _prior_flame_min(self, now: datetime) -> float:
        """Burn minutes of the last `boost_prior_window_s`, a burn's weight falling linearly with its age."""
        window = self.cfg.boost_prior_window_s
        total = 0.0
        for start, end in self._flame_log:
            end = end or now
            start = max(start, now - timedelta(seconds=window))
            if end <= start:
                continue
            age = (now - end).total_seconds()
            total += (end - start).total_seconds() / 60 * max(0.0, 1.0 - age / window)
        return total

    def restore(self, data: dict) -> None:
        self.pwm.restore(data.get("pwm", {}))
        self.storage.restore(data.get("storage", {}))
        self.regulator.restore(data.get("regulator", {}))
        self.ac.restore(data.get("ac", {}))
        shadow = data.get("shadow") or {}
        self.shadow_regulator.restore(shadow.get("regulator", {}))
        self.shadow_pwm.restore(shadow.get("pwm", {}))
        self.shadow_stats.update(shadow.get("stats") or {})
        self.heat_need.restore(data.get("heat_need", {}))
        self.learner.restore(data.get("learner", {}))
        self.curve.restore(data.get("curve", {}))
        self.exercise.restore(data.get("exercise") or {})
        self.manual_target = data.get("manual_target")
        self.preset = {"night": "sleep"}.get(data.get("preset"), data.get("preset"))  # 0.6.0 renamed night
        self.preset_until = datetime.fromisoformat(data["preset_until"]) if data.get("preset_until") else None
        self.preset_until_home = bool(data.get("preset_until_home", False))
        self._base_target = data.get("base_target")
        self._restore_boost(data.get("boost") or {})
        self.season_on = data.get("season_on", True)
        self.fault = data.get("fault", False)
        self._fault_temp = data.get("fault_temp")

    def set_preset(self, preset: str | None, now: datetime) -> None:
        """A preset chosen by hand; it ends as set for that preset (see HcConfig.expiry_*)."""
        if preset == "boost":
            self._boost_forced = True  # One boost to the current target, the preset itself stays.
            return
        self.manual_target = None
        self.preset_until, self.preset_until_home = None, False
        if preset in (None, "auto"):
            self.preset = None
            return
        self.preset = preset
        self.preset_until, self.preset_until_home = self._preset_end(preset, now)

    def _preset_end(self, preset: str, now: datetime) -> tuple[datetime | None, bool]:
        expiry = getattr(self.cfg, f"expiry_{preset}", "revoke")
        if expiry == "hours":
            return now + timedelta(hours=float(getattr(self.cfg, f"hours_{preset}", 3.0))), False
        if expiry == "next_change":
            return self._next_boundary(now), False
        return None, expiry == "home"

    def preset_end_preview(self, presets: list[str], now: datetime) -> dict:
        """For a preset menu: how each preset would end if chosen now.

        An ISO time (next night start/end), an ISO duration ("PT3H": the menu adds it to the clock, so the
        attribute does not change every update), "home", "once" (boost) or None (until changed).
        """
        out: dict = {}
        for preset in presets:
            if preset == "auto":
                continue
            if preset == "boost":
                out[preset] = "once"
                continue
            if getattr(self.cfg, f"expiry_{preset}", "revoke") == "hours":
                minutes = round(float(getattr(self.cfg, f"hours_{preset}", 3.0)) * 60)
                out[preset] = f"PT{minutes // 60}H" if minutes % 60 == 0 else f"PT{minutes}M"
                continue
            until, home = self._preset_end(preset, now)
            out[preset] = until.isoformat() if until else "home" if home else None
        return out

    @property
    def boosting(self) -> bool:
        return self._boost_until is not None

    def _expire_preset(self, inputs: Inputs) -> None:
        arrived = inputs.presence == Presence.HOME and self._last_presence not in (None, Presence.HOME)
        self._last_presence = inputs.presence
        if self.preset is None:
            return
        if (self.preset_until is not None and inputs.now >= self.preset_until) or (self.preset_until_home and arrived):
            self.preset, self.preset_until, self.preset_until_home = None, None, False

    def _coasting(self, now: datetime, target: float, indoor: float | None) -> dict | None:
        """0.44.3: after a burn the radiators keep heating for a while. While the room is just under (or at) the target
        and still rising (at least `coast_rise` over `coast_lookback_s`), within `coast_window_s` of the burn's end, a
        new start would only add to the overshoot. Returns what it saw, or None (a normal start)."""
        cfg = self.cfg
        if indoor is None:
            return None
        log = self._indoor_log
        if cfg.coast_window_s <= 0 or self.pwm.output or self.pwm.last_change is None:
            return None
        since_off = (now - self.pwm.last_change).total_seconds()
        if since_off > cfg.coast_window_s or indoor < target - cfg.coast_band:  # at / over the target: also wait
            return None
        ago = now - timedelta(seconds=cfg.coast_lookback_s)
        past = [v for t, v in log if t <= ago]
        if not past:
            return None  # not enough history (just started): a normal start
        rise = indoor - past[-1]
        if rise < cfg.coast_rise - 1e-9:
            return None
        return {"rise": round(rise, 2), "since_off_min": round(since_off / 60, 1)}

    def _pre_change(self, inputs: Inputs, target: float, indoor: float | None) -> dict | None:
        """0.48.3: the target goes down soon (night start, a preset or manual target running out) and the room is
        already at or above the coming target – a burn started now would give its heat after the change. Returns
        the change (time, coming target, minutes left) or None (start as usual)."""
        cfg = self.cfg
        if cfg.pre_change_s <= 0 or indoor is None:
            return None
        at = self._next_change(inputs)
        if at is None:
            return None
        left = (at - inputs.now).total_seconds()
        if left <= 0 or left > cfg.pre_change_s:
            return None
        after = self._target_after(inputs, at) - (target - self._target_shown)
        if after >= target - 1e-9 or indoor < after:
            return None
        return {"at": at, "target": round(after, 2), "min_left": round(left / 60, 1)}

    def _target_after(self, inputs: Inputs, at: datetime) -> float:
        """The target right after the change at `at`: the schedule's (a preset ends there, so does a manual target
        unless the schedule's value stays the same)."""
        preset, self.preset = self.preset, None
        try:
            base = self._schedule_target(replace(inputs, now=at + timedelta(seconds=1)))
        finally:
            self.preset = preset
        if self.manual_target is not None and base == self._base_target:
            return self.manual_target
        return base

    def new_cycle(self) -> None:
        """Start a fresh PWM cycle at the next step (after going live or switching on)."""
        self.pwm.cycle_start = None

    # --- helpers ---------------------------------------------------------------
    def _next_change(self, inputs: Inputs) -> datetime | None:
        """When the scheduled target changes next; None when it depends on presence or has no end."""
        if self.preset is not None:
            return self.preset_until
        if inputs.presence != Presence.HOME:
            return None
        return self._next_boundary(inputs.now)

    def _next_boundary(self, now: datetime) -> datetime | None:
        """The next night start or end."""
        cfg = self.cfg
        candidates = []
        for text in (cfg.night_start, cfg.night_end):
            at = now.replace(hour=_parse_time(text).hour, minute=_parse_time(text).minute, second=0, microsecond=0)
            if at <= now:
                at += timedelta(days=1)
            candidates.append(at)
        return min(candidates) if cfg.night_start != cfg.night_end else None

    def _is_night(self, now: datetime) -> bool:
        start, end, current = _parse_time(self.cfg.night_start), _parse_time(self.cfg.night_end), now.time()
        if start <= end:
            return start <= current < end
        return current >= start or current < end

    def active_preset(self, now: datetime) -> str:
        """The preset the target comes from now (0.24.0): a set preset, or for auto the presence and the schedule."""
        if self.preset and self.preset != "boost":
            return self.preset
        if self._last_presence == Presence.VACATION:
            return "vacation"
        if self._last_presence == Presence.AWAY:
            return "away"
        return "sleep" if self._is_night(now) else "home"

    def _schedule_target(self, inputs: Inputs) -> float:
        cfg = self.cfg
        preset = self.preset
        if preset == "comfort":
            return cfg.target_comfort
        if preset == "home":
            return cfg.target_home
        if preset == "sleep":
            return cfg.target_night
        if preset == "eco":
            return cfg.target_eco
        if preset == "away":
            return cfg.target_away
        if preset == "vacation":
            return cfg.target_vacation
        if inputs.presence == Presence.VACATION:
            return cfg.target_vacation
        if inputs.presence == Presence.AWAY:
            return cfg.target_away
        return cfg.target_night if self._is_night(inputs.now) else cfg.target_home

    def _target(self, inputs: Inputs) -> float:
        base = self._schedule_target(inputs)
        if self._base_target is not None and base != self._base_target:
            self.manual_target = None  # A manual setting lasts until the next change.
        self._base_target = base
        return self.manual_target if self.manual_target is not None else base

    def _update_season(self, outdoor_avg: float | None) -> None:
        cfg = self.cfg
        if not cfg.season_enabled:
            self.season_on = True
        elif outdoor_avg is None:
            return
        elif self.season_on and outdoor_avg > cfg.season_off_above:
            self.season_on = False
        elif not self.season_on and outdoor_avg < cfg.season_on_below:
            self.season_on = True

    def _update_drops(self, inputs: Inputs) -> bool:
        self.drop_open = None
        for entity, reading in inputs.drop_temps:
            detector = self._drops.setdefault(entity, DropDetector(self.cfg))
            if detector.update(inputs.now, reading.fresh(self.cfg.sensor_max_age_s)) and self.drop_open is None:
                self.drop_open = (entity, detector.rate)
        return self.drop_open is not None

    def _window_active(self, inputs: Inputs) -> bool:
        if not inputs.window_open:
            self._window_since = None
            return False
        if self._window_since is None:
            self._window_since = inputs.now
            if inputs.uptime_s < self.cfg.restart_grace_s:
                # 0.44.5 (as Versatile Thermostat #2147): open already when Home Assistant started – no new delay
                self._window_since = inputs.now - timedelta(seconds=self.cfg.window_delay_s)
        return (inputs.now - self._window_since).total_seconds() >= self.cfg.window_delay_s

    def _update_fault(self, inputs: Inputs, indoor: float | None, target: float, dt: float) -> None:
        """Long heating below target while the house still cools down means a fault.

        A flat temperature is not enough: a house in balance heats without rising.
        An open window is not a fault either.
        """
        cfg = self.cfg
        if indoor is None:
            return
        if self.fault and self._fault_temp is not None:
            self._fault_temp = min(self._fault_temp, indoor)  # Recovery counts from the lowest point.
            if indoor - self._fault_temp >= cfg.failure_min_drop:
                self.fault, self._fault_temp = False, None
        heating = inputs.actual_heating if inputs.actual_heating is not None else self.pwm.output
        if inputs.window_open or self.drop_open:
            self._fail_accum_s, self._fail_start_temp, self._fail_off_s, self._fail_strikes = 0.0, None, 0.0, 0
            return
        if inputs.hp_mode:
            return  # the heat pump defrosts or makes hot water: the house is not heated now, this is no fault
        if not heating:
            self._fail_off_s += dt
            if self._fail_off_s >= _REARM_OFF_S:
                self._fail_accum_s, self._fail_start_temp, self._fail_strikes = 0.0, None, 0
            return
        self._fail_off_s = 0.0
        if self._fail_start_temp is None:
            self._fail_start_temp = indoor
        self._fail_accum_s += dt
        if self._fail_accum_s >= cfg.failure_minutes * 60:
            cooling = self._fail_start_temp - indoor >= cfg.failure_min_drop
            # Two windows in a row: in the first one a cold radiator still has to warm up.
            self._fail_strikes = self._fail_strikes + 1 if cooling and target - indoor >= cfg.failure_deficit else 0
            if self._fail_strikes >= 2 and not self.fault:
                self.fault, self._fault_temp = True, indoor
            self._fail_accum_s, self._fail_start_temp = 0.0, indoor

    def _update_frost(self, indoor: float | None) -> None:
        cfg = self.cfg
        if indoor is None:
            self._frost = False
        elif indoor < cfg.frost_temp:
            self._frost = True
        elif indoor >= cfg.frost_temp + cfg.frost_hysteresis:
            self._frost = False

    def boost_forecast(self, indoor: float) -> float:
        """Indoor temperature expected once the after-heat of the burn so far has arrived."""
        cfg = self.cfg
        minutes = self._boost_flame_s / 60 + self._boost_prior_min
        if minutes <= 0:
            return indoor
        return indoor + self.learner.afterheat(self._boost_outdoor) * minutes / (minutes + cfg.boost_afterheat_ref_min)

    def _boost(self, inputs: Inputs, target: float, indoor: float) -> bool:
        cfg = self.cfg
        now = inputs.now
        deficit = target - indoor
        forced, self._boost_forced = self._boost_forced, False
        if not cfg.boost_enabled and self._boost_until is None and not forced:
            return False
        if self._boost_until is None and forced and deficit > 0.2:
            self._start_boost(inputs, target, indoor, minimum=cfg.min_on_s / 60)
            return True
        if not cfg.boost_enabled and self._boost_until is None:
            return False
        if self._boost_until is not None and self._boost_saved_at is not None:
            saved, self._boost_saved_at = self._boost_saved_at, None
            if (now - saved).total_seconds() > cfg.boost_resume_max_s:
                self._boost_until = None  # too old to resume; a new boost below still counts the recent burns
        if self._boost_until is not None:
            dt = (now - self._boost_last).total_seconds() if self._boost_last else 0.0
            self._boost_last = now
            flame = inputs.actual_heating if inputs.actual_heating is not None else self.pwm.output
            if flame:
                self._boost_flame_s += dt  # Burner minutes, not relay minutes: the boiler pauses on its own.
            if now < self._boost_until and indoor < target and self.boost_forecast(indoor) < target - self.learner.trim:
                return True
            self.learner.boost_stopped(indoor, self._boost_flame_s / 60)
            self._end_boost(now, indoor, target)
            return False
        if deficit < cfg.boost_min_deficit:
            self._boost_armed = True
            return False
        if self._boost_armed:
            self._start_boost(inputs, target, indoor)
            return True
        return False

    def _start_boost(self, inputs: Inputs, target: float, indoor: float, minimum: float = 0.0) -> None:
        cfg = self.cfg
        outdoor = inputs.outdoor.value
        per_degree = self.learner.minutes_per_degree(outdoor)
        limit = min((target - indoor) * per_degree * cfg.boost_max_factor, cfg.boost_max_minutes)
        self._boost_armed = False
        self._boost_until = inputs.now + timedelta(minutes=max(limit, minimum))
        self._boost_flame_s, self._boost_last, self._boost_outdoor = 0.0, inputs.now, outdoor
        self._boost_prior_min = self._prior_flame_min(inputs.now)
        self.learner.boost_started(inputs.now, target, indoor, outdoor)
        if self._boost_prior_min >= 1.0 and self.learner.boost is not None:
            self.learner.boost.disturbed = True  # earlier burns' after-heat mixes in: nothing to learn

    def _end_boost(self, now: datetime, indoor: float, target: float) -> None:
        cfg = self.cfg
        self._boost_until, self._boost_last = None, None
        self._quiet_until = now + timedelta(minutes=cfg.boost_quiet_minutes)
        self._quiet_cap = now + timedelta(minutes=cfg.boost_quiet_max_minutes)
        self._quiet_peak, self._quiet_rise, self._quiet_target = indoor, now, target
        self._quiet_level = indoor

    def _quiet(self, now: datetime, target: float, indoor: float) -> bool:
        """After a boost: hold off while the radiators still lift the house."""
        cfg = self.cfg
        if self._quiet_until is None:
            return False
        if indoor >= self._quiet_level + 0.05:
            self._quiet_level, self._quiet_rise = indoor, now  # a real rise, not a creep of hundredths
        self._quiet_peak = max(self._quiet_peak, indoor)
        rising = (now - self._quiet_rise).total_seconds() < cfg.boost_quiet_rise_minutes * 60
        dropped = indoor <= self._quiet_peak - cfg.boost_quiet_drop
        settled = now >= self._quiet_until and not rising
        if target != self._quiet_target or now >= self._quiet_cap or dropped or settled:
            self._quiet_until = None
            # At the cap the peak is all but reached; a changed target spoils the measurement.
            self.learner.boost_finished(peak_found=target == self._quiet_target)
            return False
        return True

    def _shadow(self, reason: Reason, target: float, indoor: float | None, outdoor: float | None, now: datetime,
                live_demand: float, live_output: bool, dt: float, inputs: Inputs) -> dict:
        """The other regulator calculates on the same inputs; only while regulating can it differ."""
        if reason == Reason.REGULATING and indoor is not None:
            loss = self.heat_need.loss_kw_per_k
            feedforward = None
            if loss is not None and outdoor is not None and self.cfg.boiler_power_kw > 0:
                need = max(loss * (target - outdoor), 0.0)
                feedforward = max(need - inputs.other_heat_kw, 0.0) / self.cfg.boiler_power_kw
            demand = self.shadow_regulator.update(target, indoor, outdoor, now, feedforward)
        else:
            self.shadow_regulator.hold(now)
            demand = live_demand
        output, _ = self.shadow_pwm.step(now, demand)
        stats = self.shadow_stats
        day = now.date().isoformat()
        if stats["day"] != day:
            if stats["day"] is not None:
                stats["yesterday"] = {"day": stats["day"], "shadow_min": round(stats["shadow_on_s"] / 60),
                                      "live_min": round(stats["live_on_s"] / 60)}
            stats.update(day=day, shadow_on_s=0.0, live_on_s=0.0)
        if 0 < dt <= 600:
            stats["shadow_on_s"] += dt if output else 0.0
            stats["live_on_s"] += dt if live_output else 0.0
        return {"control": self.shadow_kind, "demand": round(demand, 3), "output": output,
                "integral": round(getattr(self.shadow_regulator, "integral", 0.0), 4)}

    def _curve_decision(self, inputs: Inputs, reason: Reason, target: float, indoor: float | None,
                        outdoor: float | None, loss, need) -> Decision:
        """Heating curve (EXPERIMENTAL): a flow setpoint instead of on/off cycles."""
        cfg, now = self.cfg, inputs.now
        flow = None
        if reason == Reason.REGULATING and indoor is not None:
            flow = self.curve.update(target, indoor, outdoor, now)
        else:
            self.curve.hold(now)
            if reason in (Reason.BOOST, Reason.FROST):
                flow = cfg.flow_max if reason == Reason.BOOST else max(cfg.flow_min, cfg.frost_temp + 20)
            elif reason == Reason.SENSOR_LOST and outdoor is not None:
                flow = round(self.curve.base(target, outdoor), 1)  # the bare curve keeps the house safe
        min_on, min_off = (cfg.hp_min_on_s, cfg.hp_min_off_s) if cfg.heat_pump else (cfg.min_on_s, cfg.min_off_s)
        if reason == Reason.FLOOR_LIMIT:
            flow = None
            output, limited = self._gate.force_off(now), None  # a safety limit: no minimum run time
        else:
            output, limited = self._gate.step(now, flow is not None, min_on, min_off)
        if output and flow is None:
            flow = cfg.flow_min  # kept running for the minimum run time: lowest flow
        demand = 0.0 if not output else max(0.0, min(1.0, (flow - cfg.flow_min) / max(cfg.flow_max - cfg.flow_min, 1)))
        return Decision(now, reason, target, indoor, outdoor, demand=demand, output=output, limited_by=limited,
                        fault=self.fault, loss_kw_per_k=loss, heat_need_kw=need, other_heat_kw=inputs.other_heat_kw,
                        flow_setpoint=flow if output else None, details={"flow": flow if output else None})

    def _return_block(self, inputs: Inputs) -> bool:
        """District heating: close the valve while the return water is too warm (with hysteresis)."""
        cfg = self.cfg
        value = inputs.return_temp.fresh(cfg.sensor_max_age_s)
        if cfg.return_max <= 0 or value is None:
            self._return_hot = False
        elif value >= cfg.return_max:
            self._return_hot = True
        elif value <= cfg.return_max - cfg.return_hysteresis:
            self._return_hot = False
        return self._return_hot

    def _storage_decision(self, inputs: Inputs, reason: Reason, target: float, indoor: float | None,
                          outdoor: float | None, loss, need) -> Decision:
        """Storage heater: night charge by the outdoor daily average, day discharge by the room (0.31.0)."""
        cfg, now = self.cfg, inputs.now
        frost = reason == Reason.FROST
        if frost:
            fraction = 1.0
        elif reason in (Reason.DISABLED, Reason.SEASON_OFF):
            fraction = 0.0
        else:
            fraction = charge_fraction(cfg.target_home, inputs.outdoor_avg, cfg.curve_design_outdoor, cfg.storage_bias)
        res = self.storage.step(now, fraction, inputs.power_available)
        charge = res["charge"] or (frost and inputs.power_available is not False)
        discharge = self.discharge.step(indoor, target, cfg.storage_discharge_hyst,
                                        reason not in (Reason.DISABLED, Reason.WINDOW, Reason.SEASON_OFF), frost)
        if not frost and reason in (Reason.REGULATING, Reason.AT_TARGET, Reason.BOOST, Reason.AFTERHEAT, Reason.RESTART_HOLD):
            reason = Reason.STORAGE_CHARGE if charge else Reason.STORAGE_WAIT
        details = {"charge_fraction": res["fraction"], "charge_start": res["start"].strftime("%H:%M"),
                   "charge_end": res["end"].strftime("%H:%M"), "charge_why": res["why"], "discharge": discharge}
        if inputs.power_available is not None:
            details["power_available"] = inputs.power_available
            details["charged_h"] = res.get("charged_h")
        return Decision(now, reason, target, indoor, outdoor, demand=res["fraction"], output=charge,
                        fault=self.fault, loss_kw_per_k=loss, heat_need_kw=need, other_heat_kw=inputs.other_heat_kw,
                        details=details)

    def _cool_decision(self, inputs: Inputs, indoor: float | None, outdoor: float | None, loss, need) -> Decision:
        """Summer: floor cooling by a reversible heat pump, never below the dew point (+ margin)."""
        cfg, now = self.cfg, inputs.now
        self.curve.hold(now)
        curve = cfg.control == "curve"
        want = indoor is not None and self.dew.wants(indoor)
        guard = self.dew.check(indoor, inputs.humidity.fresh(cfg.humidity_max_age_s),
                               inputs.floor.fresh(cfg.floor_max_age_s), curve)
        details = {"mode": "cool", **{k: v for k, v in guard.items() if k != "ok" and v is not None}}
        if not guard["ok"]:
            output, limited = self._gate.force_off(now), None  # condensation: no minimum run time
            reason = Reason.DEW_POINT if want else Reason.SEASON_OFF
        else:
            output, limited = self._gate.step(now, want, cfg.hp_min_on_s, cfg.hp_min_off_s)
            reason = Reason.FLOOR_COOL if want or output else Reason.SEASON_OFF
        flow = guard.get("flow") if curve and output else None
        return Decision(now, reason, cfg.target_cool, indoor, outdoor, demand=1.0 if output else 0.0, output=output,
                        limited_by=limited, fault=self.fault, loss_kw_per_k=loss, heat_need_kw=need,
                        other_heat_kw=inputs.other_heat_kw, flow_setpoint=flow, details=details)

    def _onoff_decision(self, inputs: Inputs, reason: Reason, demand: float, target: float, indoor: float | None,
                        outdoor: float | None, loss, need, floor_led: bool = False) -> Decision:
        """On/off with long runs (a heat pump on its thermostat input): on below target - onoff_hysteresis, off
        when the house reached the target (AT_TARGET); no PWM, the minimum run and pause times hold."""
        cfg, now = self.cfg, inputs.now
        details: dict = {}
        if reason == Reason.FLOOR_LIMIT:
            output, limited = self._gate.force_off(now), None
        else:
            if reason == Reason.REGULATING and indoor is not None:
                # a run the floor tempering started does not keep going as a regulating run
                want = (self._gate.output and not self._temper_run) or indoor <= target - cfg.onoff_hysteresis
                if want and not self._gate.output and self._pre_hold is not None:
                    want = False  # 0.48.3: the target goes down soon, the room is warm enough for it
                    details = {"pre_change": self._pre_hold}
            else:
                want = demand > 0  # boost, frost; at target, window, summer, off: no
            min_on, min_off = (cfg.hp_min_on_s, cfg.hp_min_off_s) if cfg.heat_pump else (cfg.min_on_s, cfg.min_off_s)
            if reason == Reason.SENSOR_LOST and demand > 0 and not floor_led:
                # 0.39.3: no room reading and no floor fallback (0.36.0, that one follows the floor reading) – the
                # blind demand is a share of the time, not "on": one minimum run, then a pause long enough to keep
                # that share (without PWM the source would heat without end).
                share = max(0.05, min(1.0, demand))
                pause = max(min_off, min_on * (1.0 - share) / share)
                last = self._gate.last_change
                since = None if last is None else (now - last).total_seconds()
                want = (since is not None and since < min_on) if self._gate.output else (since is None or since >= pause)
                details = {"fallback_run_s": round(min_on), "fallback_pause_s": round(pause)}
            output, limited = self._gate.step(now, want, min_on, min_off)
            if "pre_change" in details and not output:
                limited = limited or "pre_change"
        return Decision(now, reason, target, indoor, outdoor, demand=1.0 if output else 0.0, output=output,
                        limited_by=limited, fault=self.fault, loss_kw_per_k=loss, heat_need_kw=need,
                        other_heat_kw=inputs.other_heat_kw, details=details)

    # --- the decision ----------------------------------------------------------
    def _choose(self, inputs: Inputs, target: float, indoor: float | None, outdoor: float | None,
                window: bool) -> tuple[Reason, float]:
        cfg = self.cfg
        if self._frost:
            return Reason.FROST, 1.0
        self._contact_backup = False
        if cfg.demand_contact:
            if inputs.call is not None:
                return self._contact(inputs, window)
            # The wall thermostat's contact is lost. 0.39.3: with a room reading the instance regulates by it and
            # its own target until the contact is back; without one, the lost-sensor path (floor fallback or blind).
            self._contact_backup = indoor is not None
        if indoor is None and inputs.uptime_s < cfg.restart_grace_s:
            # Right after a restart the sensors are often not loaded yet: that is no reason to start.
            return Reason.RESTART_HOLD, 0.0
        if indoor is None and cfg.sensor_lost_demand <= 0:
            # Electric heat: no blind fallback. A floor sensor still guards against frost.
            floor = inputs.floor.fresh(cfg.floor_max_age_s)
            if inputs.enabled and floor is not None and floor <= cfg.frost_temp:
                return Reason.FROST, 1.0
            return (Reason.SENSOR_LOST if inputs.enabled else Reason.DISABLED), 0.0
        if indoor is None:
            cold = outdoor is not None and outdoor <= cfg.frost_temp
            warm = outdoor is not None and outdoor >= cfg.season_off_above
            if warm or not (inputs.enabled or cold):
                return (Reason.SENSOR_LOST if inputs.enabled else Reason.DISABLED), 0.0
            # Below the minimum run time the burner would never start at all.
            return Reason.SENSOR_LOST, max(cfg.sensor_lost_demand, cfg.min_on_s / cfg.cycle_s)
        if not inputs.enabled:
            return Reason.DISABLED, 0.0
        if window:
            return Reason.WINDOW, 0.0
        if not self.season_on:
            return Reason.SEASON_OFF, 0.0
        if inputs.uptime_s < cfg.restart_grace_s and indoor >= target - cfg.restart_margin:
            return Reason.RESTART_HOLD, 0.0
        if indoor >= target + cfg.overshoot_stop:
            # 0.48.2: the after-heat watch goes on above the target too – the boost's lesson used to wait until the
            # house fell back to regulating (and a restart in between lost it)
            self._quiet(inputs.now, target, indoor)
            return Reason.AT_TARGET, 0.0
        self._pre_hold = self._pre_change(inputs, target, indoor) if not self.boosting else None
        if self._pre_hold is None and self._boost(inputs, target, indoor):
            return Reason.BOOST, 1.0
        if self._quiet(inputs.now, target, indoor):
            return Reason.AFTERHEAT, 0.0
        return Reason.REGULATING, -1.0

    def _contact(self, inputs: Inputs, window: bool) -> tuple[Reason, float]:
        """A wired wall thermostat gives the demand (0.38.0): its contact on = heat, off = no heat. No boost, no
        after-heat, the regulator is held; restart, off, window and summer still come first."""
        if inputs.uptime_s < self.cfg.restart_grace_s:
            return Reason.RESTART_HOLD, 0.0
        if not inputs.enabled:
            return Reason.DISABLED, 0.0
        if window:
            return Reason.WINDOW, 0.0
        if not self.season_on:
            return Reason.SEASON_OFF, 0.0
        return (Reason.THERMOSTAT_CALL, 1.0) if inputs.call else (Reason.THERMOSTAT_IDLE, 0.0)

    def _floor_block(self, inputs: Inputs) -> dict | None:
        """Floor temperature limit: details when heating must stop (the floor is too warm, or – where the floor
        sensor is required – it has no fresh reading); None when the floor allows heat."""
        cfg = self.cfg
        limit = cfg.floor_limit  # floor_max, or by the covering and the probe position (0.37.0)
        if limit <= 0 and not cfg.floor_required:
            return None
        # Many sensors report only on a change: a cold, still floor may stay silent for an hour. While heating the
        # floor warms and reports, so a silent sensor is suspicious sooner.
        heating = self.pwm.output or self._gate.output
        floor = inputs.floor.fresh(cfg.floor_max_age_on_s if heating else cfg.floor_max_age_s)
        if floor is None:
            self._floor_hot = False
            return {"floor": None, "floor_max": limit or None, "floor_why": "lost"} if cfg.floor_required else None
        if limit > 0:
            if floor >= limit:
                self._floor_hot = True
            elif floor <= limit - cfg.floor_hysteresis:
                self._floor_hot = False
        return {"floor": floor, "floor_max": limit, "floor_why": "hot"} if self._floor_hot else None

    @property
    def temper_on(self) -> bool:
        """The floor tempering latch (for the info panel)."""
        return self._temper_on

    def _floor_target(self, now: datetime, shown: float) -> float:
        """The floor target of the tempering: the user's room target + the offset; at night / in the sleep preset
        the night value when it is set."""
        cfg = self.cfg
        if cfg.floor_temper_night > 0 and (self._is_night(now) or self.active_preset(now) == "sleep"):
            return cfg.floor_temper_night
        return round(shown + cfg.temper_offset, 2)

    def _floor_latch(self, inputs: Inputs, shown: float, use: bool) -> dict | None:
        """Floor tempering (0.35.0) and the floor fallback of a lost room thermometer (0.36.0): the latch on the floor
        reading, with hysteresis. None when it does not apply (not used now, not a floor system, not a relay control,
        no fresh floor reading)."""
        cfg = self.cfg
        if not (use and cfg.floor_system and cfg.control in ("tpi", "pid", "onoff")):
            self._temper_on = False
            return None
        heating = self.pwm.output or self._gate.output  # the same freshness as the floor limit
        floor = inputs.floor.fresh(cfg.floor_max_age_on_s if heating else cfg.floor_max_age_s)
        if floor is None:
            self._temper_on = False
            return None
        aim = self._floor_target(inputs.now, shown)
        if floor >= aim:
            self._temper_on = False
        elif floor <= aim - cfg.floor_temper_hysteresis:
            self._temper_on = True
        return {"on": self._temper_on, "floor": floor, "floor_target": aim}

    def _external(self, inputs: Inputs, reason: Reason, target: float, indoor: float | None) -> tuple[Reason, ExternalCommand]:
        cfg = self.cfg
        if reason == Reason.FLOOR_LIMIT:
            return reason, ExternalCommand("off", target)
        if reason == Reason.FROST:
            return reason, ExternalCommand("heat", cfg.frost_temp + 1.0)
        if reason in (Reason.DISABLED, Reason.WINDOW, Reason.SEASON_OFF):
            return reason, ExternalCommand("off", target)
        if inputs.managed_off and cfg.control == "external":
            # 0.42.0: switched off by hand on the thermostat itself – respected (only frost overrides it)
            return Reason.MANAGED_OFF, ExternalCommand("off", target)
        if (inputs.uptime_s < cfg.restart_burn_window_s and inputs.actual_heating and indoor is not None
                and indoor >= target + cfg.overshoot_stop):
            return Reason.RESTART_BURN, ExternalCommand("off", target)
        if reason == Reason.SENSOR_LOST:
            return reason, ExternalCommand("heat", target)
        return Reason.EXTERNAL, ExternalCommand("heat", target)

    def _ac(self, inputs: Inputs, reason: Reason, command: ExternalCommand, target: float,
            indoor: float | None) -> tuple[Reason, ExternalCommand, dict]:
        """Air conditioner: move its setpoint by the room thermometer (virtual i-Feel); cool in summer."""
        cfg, now = self.cfg, inputs.now
        step, lo, hi = inputs.unit_step or 1.0, inputs.unit_min or 16.0, inputs.unit_max or 30.0
        if reason == Reason.SEASON_OFF:
            cooling = indoor is not None and (indoor > cfg.target_cool + 0.5
                                               or (self.ac.mode == "cool" and indoor > cfg.target_cool - 1.0))
            if not cooling:
                self.ac.step(now, "off", cfg.target_cool, indoor, inputs.unit_temp, step, lo, hi)
                return reason, ExternalCommand("off", cfg.target_cool), {}
            mode, aim = "cool", cfg.target_cool
        elif reason in (Reason.EXTERNAL,):
            mode, aim = "heat", target
            if inputs.assist_target is not None and inputs.assist_target > target:
                aim = inputs.assist_target  # cheaper than the boiler and the door is open: help the house
        else:
            # Off (window, switched off), frost, lost sensor, restart: the plain command, nothing moved – but a
            # heat setpoint must fit the unit (frost asks for 8 °C, most units start at 16 °C and refuse less).
            if command.hvac == "heat":
                command = ExternalCommand("heat", min(max(command.target, lo), hi))
            self.ac.hold(now)  # 0.44.1: no integral jump when regulation resumes
            return reason, command, {}
        c = self.ac.step(now, mode, aim, indoor, inputs.unit_temp, step, lo, hi)
        details = {"ac_mode": mode, "setpoint": c.setpoint, "aim": aim, "assist": aim != target and mode == "heat",
                   "offset": round(self.ac.offset or 0.0, 2),
                   "integral": round(self.ac.integral, 2), "unit_temp": inputs.unit_temp}
        if c.paused:
            return Reason.AC_PAUSE, ExternalCommand("off", aim), details
        return (Reason.AC_COOL if mode == "cool" else Reason.AC_HEAT), ExternalCommand(mode, c.setpoint), details

    def step(self, inputs: Inputs) -> Decision:
        decision = self._step(inputs)
        if inputs.hp_mode:
            decision = replace(decision, details={**decision.details, "hp_mode": inputs.hp_mode})
        if self.cfg.control in ("tpi", "pid") and self.exercise.step(inputs.now, decision.reason, decision.output):
            decision = replace(decision, reason=Reason.VALVE_EXERCISE, output=True, demand=0.0, limited_by=None,
                               details={"exercise_until": self.exercise.running_since + timedelta(seconds=self.cfg.exercise_s)})
        if self.manual_target is None:
            return decision
        return replace(decision, manual=True, manual_until=self._next_change(inputs))

    def _step(self, inputs: Inputs) -> Decision:
        cfg, now = self.cfg, inputs.now
        dt = 0.0 if self._last_now is None else max((now - self._last_now).total_seconds(), 0.0)
        self._last_now = now
        indoor = inputs.indoor.fresh(cfg.sensor_max_age_s)
        frozen = None
        if cfg.control in ("tpi", "pid", "onoff"):
            heating = inputs.actual_heating if inputs.actual_heating is not None else (self.pwm.output or self._gate.output)
            self._note_flame(now, bool(heating))
            if self.frozen.step(now, indoor, bool(heating)):
                frozen, indoor = self.frozen.details(now), None  # looks fresh, measures nothing: the lost-sensor path
        outdoor = inputs.outdoor.fresh(cfg.sensor_max_age_s)
        self._update_season(inputs.outdoor_avg)
        self._expire_preset(inputs)
        target = self._target(inputs)
        shown = target  # what the user set; the regulation may run a little lower while a cheaper source leads
        self._target_shown, self._pre_hold = shown, None
        yielding = inputs.yield_margin > 0 and cfg.control in ("tpi", "pid")
        if yielding:
            target = target - inputs.yield_margin
        window = self._window_active_flag = self._window_active(inputs)
        if self._update_drops(inputs):
            window = True
        self.heat_need.update(now, indoor, outdoor, inputs.heat_energy_kwh)
        loss = self.heat_need.loss_kw_per_k
        need = None
        if loss is not None and outdoor is not None:
            need = max(loss * (shown - outdoor), 0.0)
        frost_temp = indoor
        if frost_temp is None and cfg.demand_contact:
            frost_temp = inputs.floor.fresh(cfg.floor_max_age_s)  # no room thermometer: the floor guards against frost
        self._update_frost(frost_temp)
        if indoor is None and frost_temp is not None and frost_temp <= cfg.frost_temp:
            self._frost = True  # the floor at the frost limit (wall thermostat without a room thermometer)
        self._update_fault(inputs, indoor, target, dt)
        reason, demand = self._choose(inputs, target, indoor, outdoor, window)
        blind = None
        if (reason == Reason.SENSOR_LOST and demand > 0 and cfg.sensor_lost_model and need is not None
                and cfg.boiler_power_kw > 0 and cfg.sensor_lost_demand > 0):
            # 0.40.0: the learned heat loss tells how much the house needs now – a fixed 35 % overheats it in mild
            # weather and may be short in a cold spell. Never below one minimum run per cycle.
            share = max(need - inputs.other_heat_kw, 0.0) / cfg.boiler_power_kw
            demand = round(min(1.0, max(share, cfg.min_on_s / cfg.cycle_s)), 3)
            blind = {"blind_from": "heat_need", "heat_need_kw": round(need, 2)}
        self._boost_forced = False  # A boost asked for by hand that could not start now is dropped.
        floor_block = self._floor_block(inputs)
        if floor_block is not None and reason not in (Reason.DISABLED, Reason.WINDOW, Reason.SEASON_OFF):
            reason, demand = Reason.FLOOR_LIMIT, 0.0
        # Floor tempering (0.35.0): the room is warm enough, the floor slab is kept warm; never above the room margin.
        # Lost room thermometer (0.36.0): the floor sensor keeps the floor at the same target instead of a blind demand.
        lost = reason == Reason.SENSOR_LOST and cfg.floor_fallback
        latch = self._floor_latch(inputs, shown, cfg.floor_temper or lost)
        fallback = None
        warm = outdoor is not None and outdoor >= cfg.season_off_above
        if lost and latch is not None and inputs.enabled and not warm:
            demand = 1.0 if latch["on"] and not window else 0.0  # with the floor known, an open window pauses it
            fallback = {"floor_fallback": True, "floor": latch["floor"], "floor_target": latch["floor_target"]}
        tempering = None
        # A wall thermostat that asks for nothing counts as at target. Without a room thermometer there is no margin
        # check and the instance's own room target means nothing (the wall thermostat has its own): 0.39.3 – then
        # only the absolute night value tempers, in its own hours; "room target + offset" would heat against it.
        absolute = cfg.floor_temper_night > 0 and (self._is_night(now) or self.active_preset(now) == "sleep")
        if (cfg.floor_temper and latch is not None and latch["on"]
                and reason in (Reason.AT_TARGET, Reason.AFTERHEAT, Reason.REGULATING, Reason.THERMOSTAT_IDLE)
                and (indoor is not None and indoor < shown + cfg.floor_temper_room_margin
                     or indoor is None and reason == Reason.THERMOSTAT_IDLE and absolute)):
            tempering = {"floor": latch["floor"], "floor_target": latch["floor_target"]}
            if reason != Reason.REGULATING:
                reason, demand = Reason.FLOOR_TEMPER, 1.0
        floor_details = floor_block or ({"floor": inputs.floor.value} if inputs.floor.value is not None else {})
        if self._contact_backup:
            floor_details = {**floor_details, "contact_lost": True}
        if fallback is not None:
            floor_details = {**floor_details, **fallback}
        elif reason == Reason.SENSOR_LOST and cfg.sensor_lost_demand <= 0:
            floor_details = {**floor_details, "no_blind": True}  # electric heat: no fallback demand
        elif blind is not None and reason == Reason.SENSOR_LOST:
            floor_details = {**floor_details, **blind}
        if frozen is not None:
            floor_details = {**floor_details, **frozen}

        if cfg.control == "storage":
            return self._storage_decision(inputs, reason, target, indoor, outdoor, loss, need)
        if cfg.floor_cooling and cfg.control in ("curve", "onoff") and reason == Reason.SEASON_OFF:
            return self._cool_decision(inputs, indoor, outdoor, loss, need)

        if cfg.control in ("external", "ac"):
            reason, command = self._external(inputs, reason, target, indoor)
            details: dict = dict(floor_details)
            if cfg.control == "ac":
                reason, command, details = self._ac(inputs, reason, command, target, indoor)
            return Decision(now, reason, target, indoor, outdoor, fault=self.fault, external=command,
                            output=command.hvac in ("heat", "cool"), loss_kw_per_k=loss, heat_need_kw=need,
                            other_heat_kw=inputs.other_heat_kw, details=details)

        if self.learner.boost is not None:
            self.learner.observe(indoor, target, window)
        if target != self._last_target:
            self._last_target, self._target_since = target, now
        settled = self._target_since is not None and (now - self._target_since).total_seconds() >= cfg.learning_settle_s
        if (reason in (Reason.REGULATING, Reason.AT_TARGET) and inputs.presence == Presence.HOME and settled
                and indoor is not None and self.learner.boost is None and not yielding and tempering is None):
            self.learner.regulating(now, dt, target, indoor)
        if cfg.control == "curve":
            return self._curve_decision(inputs, reason, target, indoor, outdoor, loss, need)
        if cfg.control == "onoff":
            self.regulator.hold(now)
            if reason == Reason.REGULATING and tempering is not None:
                regulating = indoor <= target - cfg.onoff_hysteresis or (self._gate.output and not self._temper_run)
                if regulating:
                    self._temper_run = False  # the room asks by itself: an ordinary run
                else:
                    reason, demand = Reason.FLOOR_TEMPER, 1.0
            decision = self._onoff_decision(inputs, reason, demand, target, indoor, outdoor, loss, need,
                                            floor_led=fallback is not None)
            self._temper_run = decision.output and (decision.reason == Reason.FLOOR_TEMPER or self._temper_run)
            if decision.reason == Reason.FLOOR_TEMPER:
                floor_details = {**floor_details, **tempering}
            return replace(decision, details={**decision.details, **floor_details}) if floor_details else decision
        if indoor is not None:  # 0.44.3: the recent room readings for coasting (every step, not only regulating)
            self._indoor_log.append((now, indoor))
            cut = now - timedelta(seconds=cfg.coast_lookback_s + 600)
            while len(self._indoor_log) > 2 and self._indoor_log[1][0] <= cut:
                self._indoor_log.pop(0)
        no_power = inputs.power_available is False  # controlled power off: no heat now, no integral wind-up
        if reason == Reason.REGULATING and not no_power:
            if hasattr(self.regulator, "offset"):
                self.regulator.coef_int = self.learner.tpi_coef_int
                self.regulator.offset = self.learner.tpi_offset
            feedforward = None
            if need is not None and cfg.boiler_power_kw > 0:
                # The boiler replaces what the house loses and other sources do not cover.
                feedforward = max(need - inputs.other_heat_kw, 0.0) / cfg.boiler_power_kw
            integral_before = getattr(self.regulator, "integral", None)
            demand = self.regulator.update(target, indoor, outdoor, now, feedforward)
            coast = self._coasting(now, target, indoor) if 0 < demand <= cfg.coast_max_demand else None
            if coast is not None:
                # 0.44.3: the room still rises towards a near target after a burn – wait for it instead of starting
                # again (11-12: a second 7-min burn at 22.4 / 22.5 took the room to 22.8), and keep the integral
                if integral_before is not None and self.regulator.integral > integral_before:
                    self.regulator.integral = integral_before
                demand, coasting = 0.0, coast
            else:
                coasting = None
            if inputs.room_demand and indoor is not None and indoor <= target:
                # A TRV room far below its target: short burns, but the main thermometer stays in charge.
                demand = max(demand, min(1.0, (cfg.min_on_s + 60) / cfg.cycle_s))
            if self._pre_hold is not None and demand > 0 and not self.pwm.output:
                # 0.48.3: the target goes down soon and the room is already warm enough for it – no new start
                if integral_before is not None and self.regulator.integral > integral_before:
                    self.regulator.integral = integral_before
                demand = 0.0
            else:
                self._pre_hold = None
            if tempering is not None and demand < 1.0:
                reason, demand = Reason.FLOOR_TEMPER, 1.0  # the floor asks for more than the room
        else:
            self.regulator.hold(now)
            coasting = None
        if reason == Reason.FLOOR_LIMIT:
            output, limited = self.pwm.force_off(now), None  # a safety limit: no minimum run time
        elif self._return_block(inputs) and demand > 0:
            output, limited = self.pwm.force_off(now), "return_limit"  # the network wants its water back cooler
        elif no_power and (demand > 0 or reason == Reason.REGULATING):
            demand = max(demand, 0.0)
            output, limited = self.pwm.force_off(now), "no_power"  # the relay would switch a dead circuit
        else:
            allow = (lambda renew: self.load.request(now, renew)) if self.load is not None else None
            output, limited = self.pwm.step(now, demand, allow)
        if self.load is not None:
            self.load.report(output, limited == "load_limit", now)
        shadow = self._shadow(reason, target, indoor, outdoor, now, demand, output, dt, inputs) if cfg.shadow_regulator else None
        details: dict = {}
        if reason == Reason.REGULATING and inputs.room_demand and indoor is not None and indoor <= target:
            details = {"room_demand": list(inputs.room_demand)}
        if reason == Reason.BOOST:
            details = {"until": self._boost_until, "forecast": round(self.boost_forecast(indoor), 2),
                       "flame_min": round(self._boost_flame_s / 60, 1),
                       "prior_min": round(self._boost_prior_min, 1), "afterheat": cfg.boost_afterheat}
        elif reason == Reason.AFTERHEAT:
            details = {"peak": self._quiet_peak}
        elif reason == Reason.WINDOW and self.drop_open and not self._window_active_flag:
            details = {"window_source": "drop", "drop_entity": self.drop_open[0], "drop_rate": self.drop_open[1]}
        if yielding and reason in (Reason.REGULATING, Reason.AT_TARGET, Reason.BOOST, Reason.AFTERHEAT):
            details = {**details, "yield": inputs.yield_margin}
        if floor_details:
            details = {**details, **floor_details}
        if reason == Reason.FLOOR_TEMPER:
            details = {**details, **tempering}
        if self.load is not None and limited == "load_limit":
            details = {**details, **self.load.details(now)}
        if limited == "return_limit":
            details = {**details, "return": inputs.return_temp.value, "return_max": cfg.return_max}
        if coasting is not None and not output:
            limited = limited or "coast"
            details = {**details, "coast": coasting}
        if self._pre_hold is not None and reason == Reason.REGULATING and not output:
            limited = limited or "pre_change"
            details = {**details, "pre_change": self._pre_hold}
        if cfg.fan_coil:
            pct, why = self.fan.step(now, output, demand, inputs.coil.fresh(cfg.sensor_max_age_s))
            details = {**details, "fan_pct": pct, "fan_why": why}
        return Decision(now, reason, shown, indoor, outdoor, demand=demand, output=output,
                        limited_by=limited, fault=self.fault, loss_kw_per_k=loss, heat_need_kw=need,
                        other_heat_kw=inputs.other_heat_kw, shadow=shadow, details=details)

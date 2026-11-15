"""0.55.0 – a heat pump charging a buffer tank (through its coil or directly), coordinated with the circuits fed from
the tank and with another source (a wood boiler) charging the same tank. Shadow only: HC works out and shows three
separate things and writes none of them yet (that comes in 0.56.0, after a supervised trial):

A) heat demand – should heat be made for the rooms / the tank now?
B) enable – should the heat pump be switched ON or OFF on its own controller? (ON is not a heating command: with no
   heat demand the target goes to its lowest, so the unit stands by.)
C) the flow target – how warm the water should be while it may heat.

Order of priority (the reference design's priority list):
1. Lost inputs: no outdoor reading – with the cold-weather ON enabled the request is ON (fail-safe for a water-filled
   monoblock), else the last request stays (no random switching); no tank reading – the last request stays.
2. Cold-weather ON (`hp_cold_on`, off by default – only for a water-filled monoblock): below `hp_cold_on_below`
   (+5 °C) the request is ON, also with no heat demand and while wood heats; it is released only after the outdoor
   temperature stayed above `hp_cold_release_above` (+7 °C) for `hp_cold_release_s` (1 h). It wins over the long
   no-demand stop. It does not replace the unit's own frost protection.
3. Heat demand by the circuits and the tank's usable heat, wood first: a tank warm enough for the circuits makes no
   demand; while another source is known to charge the tank (wood signal on, or the tank warming while the heat pump
   is known not to run) the heat pump does not heat – no new start, no low-charge start, and a running heating
   stops (`hp_wood_first`, 0.56.1); only the buffer frost limit goes before it.
4. Long no-demand stop (`hp_idle_off`, on): with `hp_standby` (keep ON with no demand) the request goes OFF after
   `hp_idle_hours` (24 h) with no circuit demand and no heat demand – unless the cold-weather ON holds. Without
   `hp_standby` the request is already OFF whenever there is no demand, so there is nothing for this stop to do.
   "No demand" means neither: no lasting circuit / zone demand and no heat demand of the tank (charging included).
5. Low water, rare changes: the target is the circuits' need plus the coil reserve and the manual offset, within the
   limits (after the offset), given out through the same hold as the circuits (core/setpoint_hold.py).

Heat demand in detail (all thresholds settable; percentages only when the tank has a charge value):
- need = the highest given-out target of the circuits with a lasting demand + their margin;
- starts when the tank top is below the need, or the charge is at or below `hp_charge_on` %, or the top is at the
  buffer's frost limit;
- runs on until the top is at least need + `hp_hyst` and, with `hp_charge_off` set, the charge reached it;
- `hp_min_on_s` / `hp_min_off_s` hold the enable request (not the cold-weather ON and not a fail-safe ON).

Wood first (`hp_wood_first`, on – 0.56.1): with wood `certain` or `likely` the heat pump does not heat, not even
for a low charge (`hp_charge_on`), and a heating that already runs stops. Only the buffer frost limit is above it;
the cold-weather ON and a fail-safe ON still keep the unit ON (its target at the lowest – no heating command).
Off: the 0.55.0 order (a low charge and a running heating go before wood; wood only holds back a new start).

Wood: `certain` with a wood signal entity on; `likely` when the tank mean warms by at least `hp_wood_rise` °C/h while
the heat pump is known not to run; `possible` when it warms but whether the heat pump runs is not known – shown only,
it changes nothing (HC does not claim what it cannot know).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .setpoint_hold import HoldConfig, SetpointHold


@dataclass
class HpConfig:
    hp_flow_min: float = 25.0
    hp_flow_max: float = 55.0
    hp_reserve: float = 5.0  # °C: tank / coil reserve above the circuits' need
    hp_offset: float = 0.0  # °C −8…+8: the manual correction (the number entity overrides it)
    hp_hyst: float = 3.0  # °C above the need before a heating stops
    hp_charge_on: float = 0.0  # % – start at or below (0 = not used)
    hp_charge_off: float = 0.0  # % – stop only at or above (0 = not used)
    hp_min_on_s: float = 1800.0
    hp_min_off_s: float = 900.0
    hp_standby: bool = False  # keep the unit ON with no demand (its target at the lowest)
    hp_idle_off: bool = True
    hp_idle_hours: float = 24.0
    hp_cold_on: bool = False
    hp_cold_on_below: float = 5.0
    hp_cold_release_above: float = 7.0
    hp_cold_release_s: float = 3600.0
    hp_wood_rise: float = 2.0  # °C/h of the tank mean
    hp_wood_first: bool = True  # 0.56.1: wood also stops a low-charge start and a running heating
    hp_deadband: float = 2.0
    hp_confirm_s: float = 600.0
    hp_min_interval_s: float = 2700.0
    hp_max_rise: float = 3.0
    hp_urgent: float = 6.0

    @classmethod
    def from_conf(cls, conf: dict) -> "HpConfig":
        known = cls.__dataclass_fields__
        return cls(**{k: v for k, v in conf.items() if k in known and v is not None})

    def hold(self) -> HoldConfig:
        return HoldConfig(self.hp_deadband, self.hp_confirm_s, self.hp_min_interval_s, self.hp_max_rise, self.hp_urgent)


@dataclass(frozen=True)
class CircuitNeed:
    name: str
    demand: bool  # a lasting demand
    target: float | None  # its given-out flow target
    margin: float = 2.0


@dataclass(frozen=True)
class HpInputs:
    outdoor: float | None
    top: float | None  # tank top
    charge: float | None = None  # %
    trend_c_h: float | None = None  # tank mean °C/h
    circuits: tuple = ()  # CircuitNeed
    zones_asking: bool = False  # the buffer's own zones (when no circuit is linked)
    frost_top: float = 8.0  # the buffer's frost limit
    wood_signal: bool | None = None  # a wood boiler / flue signal (None: none given)
    hp_running: bool | None = None  # the heat pump runs now (None: not known)
    offset: float | None = None  # the manual offset now (the number entity)


@dataclass(frozen=True)
class HpDecision:
    now: datetime
    enable: bool  # ON/OFF request for the unit (a request, not a confirmation)
    heat_demand: bool
    reason: str
    target: float | None  # given out
    raw: float | None
    hold_reason: str
    need: float | None = None
    wood: str = "none"  # none | possible | likely | certain
    cold_on: bool = False
    details: dict = field(default_factory=dict)


REASONS = ["fail_safe_on", "no_outdoor", "no_buffer", "cold_on", "frost", "low_charge", "heat_needed", "heating",
           "charging", "wood", "idle_off", "standby", "off", "min_on", "min_off"]


class HeatPumpCoordinator:
    def __init__(self, cfg: HpConfig | None = None) -> None:
        self.cfg = cfg or HpConfig()
        self.hold = SetpointHold(self.cfg.hold())
        self.enable = False
        self.heating = False  # the heat demand (A), with its own hysteresis
        self.last_change: datetime | None = None  # of the enable request
        self.cold_latched = False
        self.warm_since: datetime | None = None  # outdoor above the release limit since
        self.last_demand: datetime | None = None  # a circuit demand or a heat demand last seen

    # --- parts ------------------------------------------------------------------------------------------------
    def _cold(self, now: datetime, outdoor: float | None) -> bool:
        cfg = self.cfg
        if not cfg.hp_cold_on:
            self.cold_latched, self.warm_since = False, None
            return False
        if outdoor is None:
            return self.cold_latched
        if outdoor < cfg.hp_cold_on_below:
            self.cold_latched, self.warm_since = True, None
        elif self.cold_latched:
            if outdoor > cfg.hp_cold_release_above:
                self.warm_since = self.warm_since or now
                if (now - self.warm_since).total_seconds() >= cfg.hp_cold_release_s:
                    self.cold_latched, self.warm_since = False, None
            else:
                self.warm_since = None
        return self.cold_latched

    def _wood(self, i: HpInputs) -> str:
        if i.wood_signal:
            return "certain"
        rising = i.trend_c_h is not None and i.trend_c_h >= self.cfg.hp_wood_rise
        if not rising:
            return "none"
        if i.hp_running is False:
            return "likely"
        return "possible" if i.hp_running is None else "none"  # warming while the heat pump runs: its own heat

    def _need(self, i: HpInputs) -> float | None:
        needs = [c.target + c.margin for c in i.circuits if c.demand and c.target is not None]
        return round(max(needs), 1) if needs else None

    def _heat(self, i: HpInputs, need: float | None, wood: str) -> tuple[bool, str]:
        cfg = self.cfg
        frost = i.top is not None and i.top <= i.frost_top
        low = cfg.hp_charge_on > 0 and i.charge is not None and i.charge <= cfg.hp_charge_on
        if frost:
            return True, "frost"
        if cfg.hp_wood_first and wood in ("certain", "likely"):
            # 0.56.1: wood first – before a low charge and also over a heating that already runs; frost (above),
            # the cold-weather ON and a fail-safe ON (the enable request, in step) still stand
            return False, "wood"
        if low:
            return True, "low_charge"
        if self.heating:
            if need is not None and i.top < need + cfg.hp_hyst:
                return True, "heating"
            if cfg.hp_charge_off > 0 and i.charge is not None and i.charge < cfg.hp_charge_off:
                return True, "charging"
            return False, "off"
        if need is not None and i.top < need:
            if wood in ("certain", "likely"):
                return False, "wood"  # another source charges the tank: let it
            return True, "heat_needed"
        return False, "off"

    def _switch(self, now: datetime, want: bool, force: bool) -> str | None:
        """Min on / off of the enable request; `force` (cold ON, fail-safe) ignores them."""
        if want == self.enable:
            return None
        since = (now - self.last_change).total_seconds() if self.last_change else None
        if not force and since is not None:
            if self.enable and since < self.cfg.hp_min_on_s:
                return "min_on"
            if not self.enable and since < self.cfg.hp_min_off_s:
                return "min_off"
        self.enable, self.last_change = want, now
        return None

    # --- the step ---------------------------------------------------------------------------------------------
    def step(self, now: datetime, i: HpInputs) -> HpDecision:
        cfg = self.cfg
        offset = max(-8.0, min(8.0, cfg.hp_offset if i.offset is None else i.offset))
        cold = self._cold(now, i.outdoor)
        wood = self._wood(i)
        need = self._need(i)
        details: dict = {"offset": offset, "top": i.top, "charge": i.charge, "trend_c_h": i.trend_c_h,
                         "hp_running": i.hp_running}
        demand_now = any(c.demand for c in i.circuits) or i.zones_asking
        if i.top is None:
            heat, why = self.heating, "no_buffer"
        else:
            heat, why = self._heat(i, need, wood)
        self.heating = heat
        if demand_now or heat or self.last_demand is None:
            self.last_demand = now  # the idle time counts from the first run, not from never
        idle_h = (now - self.last_demand).total_seconds() / 3600 if self.last_demand else None
        details["idle_hours"] = None if idle_h is None else round(idle_h, 2)

        # the enable request, by priority
        force = False
        if i.outdoor is None and cfg.hp_cold_on:
            want, reason, force = True, "fail_safe_on", True
        elif i.outdoor is None:
            want, reason = self.enable, "no_outdoor"
        elif i.top is None:
            want, reason = (True, "cold_on") if cold else (self.enable, "no_buffer")
            force = cold
        elif cold:
            want, reason, force = True, "cold_on", True
            if heat:
                details["heat_reason"] = why
            idle = cfg.hp_standby and cfg.hp_idle_off and not heat and idle_h is not None and idle_h >= cfg.hp_idle_hours
            details["idle_overridden"] = idle  # the long no-demand stop would apply, the cold-weather ON wins
        elif heat:
            want, reason = True, why
        elif cfg.hp_standby:
            idle = cfg.hp_idle_off and idle_h is not None and idle_h >= cfg.hp_idle_hours
            want, reason = (False, "idle_off") if idle else (True, "standby")
            if why == "wood":
                reason = "wood" if not idle else reason
        else:
            want, reason = False, why if why in ("wood",) else "off"
        held = self._switch(now, want, force)
        if held:
            reason = held

        # the flow target: the need + reserve + offset while heating, else the lowest (stand by)
        if heat and need is not None:
            raw = need + cfg.hp_reserve + offset
        elif heat:  # frost / low charge with no circuit asking: a modest charge
            raw = cfg.hp_flow_min + cfg.hp_reserve + offset
        else:
            raw = cfg.hp_flow_min
        res = self.hold.step(now, raw, cfg.hp_flow_min, cfg.hp_flow_max)
        details.update(next_allowed=res.next_allowed.isoformat() if res.next_allowed else None,
                       last_change=self.last_change.isoformat() if self.last_change else None,
                       target_changed=res.changed, warm_since=self.warm_since.isoformat() if self.warm_since else None)
        return HpDecision(now, self.enable, heat, reason, res.value, res.raw, res.reason, need, wood, cold, details)

    # --- restart ----------------------------------------------------------------------------------------------
    def state(self, now: datetime) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"hold": self.hold.state(now), "enable": self.enable, "heating": self.heating,
                "last_change": iso(self.last_change), "cold_latched": self.cold_latched,
                "warm_since": iso(self.warm_since), "last_demand": iso(self.last_demand)}

    def restore(self, data: dict, now: datetime) -> None:
        def when(key):
            try:
                return datetime.fromisoformat(data[key]) if data.get(key) else None
            except (TypeError, ValueError):
                return None
        self.hold.restore(data.get("hold") or {}, now)
        self.enable = bool(data.get("enable", False))
        self.heating = bool(data.get("heating", False))
        self.cold_latched = bool(data.get("cold_latched", False)) and self.cfg.hp_cold_on
        self.last_change, self.warm_since, self.last_demand = when("last_change"), when("warm_since"), when("last_demand")

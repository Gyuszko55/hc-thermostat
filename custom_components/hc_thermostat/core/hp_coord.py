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
   With the automatic summer mode on (0.57.0, see below) summer mode takes its place.
5. Low water, rare changes: the target is the circuits' need plus the coil reserve and the manual offset, within the
   limits (after the offset), given out through the same hold as the circuits (core/setpoint_hold.py).

Heat demand in detail (all thresholds settable; percentages only when the tank has a charge value):
- need = the highest given-out target of the circuits with a lasting demand + their margin;
- starts when the tank top is below the need, or the charge is at or below `hp_charge_on` %, or the top is at the
  buffer's frost limit;
- runs on until the top is at least need + `hp_hyst` and, with `hp_charge_off` set, the charge reached it;
- 0.59.0 `hp_charge_needs_demand` (off): the two percentages count only while a circuit / zone has a lasting demand –
  a low charge alone then starts nothing, and with no demand a heating stops on the temperatures alone;
- `hp_min_on_s` / `hp_min_off_s` hold the enable request (not the cold-weather ON and not a fail-safe ON).

0.65.0 – demand-based charging (`hp_charge_mode` = `demand`; `classic`, the rules above, by default). The tester's
live system (1000 l stratified tank, 10 kW heat pump on the lower coil) showed the classic start too late: with the
top at 37 °C and the need at 34.5 °C nothing started, though the tank was nearly spent below and the coil's heat takes
long to reach the top. In demand mode the percentages are only information; the start and the stop go by the need:
- need (T_need) = the highest demanded (not tank-capped) target of the circuits with a lasting demand + their margin;
- reserve: in °C the top − T_need; in kWh Σ layer litres × 1.163 Wh/(l·K) × max(layer − T_need, 0) (with the volume);
- start when the top < T_need + `hp_start_margin` (3 °C), or the kWh reserve < `hp_start_kwh` (0 = not used);
- stop when the `hp_stop_layer` (the lower middle sensor by default; the nearest measured one above it when missing)
  is at least T_need + `hp_stop_margin` (3 °C) – a usable reserve in the upper part, not only a warm top; that stop
  temperature is never above the flow target asked of the heat pump − `hp_coil_dt` (3 °C), so HC never waits for a
  tank the coil cannot reach (and never below T_need);
- 0.68.0: it also starts when the tank cools steadily (the tank mean by at least 0.2 °C/h) and at that pace the top
  reaches T_need within `hp_lead_min` (60 minutes; 0 = off) – the time the coil's heat needs to reach the top;
- with no lasting demand a running charge stops and nothing starts (a low percentage alone starts nothing);
- frost, wood first, the cold-weather ON, the long no-demand stop, summer mode and the min on / off stay as they are;
- a tank with no circuit linked (its own zones only) keeps the classic rules.
Both are worked out every step, each with its own hysteresis, and both are shown (`classic`, `demand_charge`), so the
one not driving can be compared in shadow; the estimated hours until the top reaches T_need (from the tank's trend)
were shown only until 0.68.0; since then they time the start (above).

Automatic summer / winter mode (`hp_auto_summer`, off – 0.57.0): not a date and not only the outdoor temperature, but
the house's own demand. After `hp_summer_after_h` (24 h) with no circuit / zone demand at all, the coordination goes
into summer mode: no heating for the tank – no low-charge start, no standby ON, a running heating stops; the target
goes to the lowest. Only the buffer frost limit still heats, and the cold-weather ON (a separate thing) still keeps the
unit ON with no heating command. It goes back to winter mode – by itself – once the circuits' demand has lasted
`hp_winter_after_s` (30 min) without a break and a room still asks for heat at its end: one TPI pulse or a short dip
after airing does not end the summer. A "summer mode" binary sensor (and, if given, a switch / input_boolean output)
tells a PLC. Optional "exercise due" signal (`hp_exercise`): in summer mode, every week on `hp_exercise_weekday` from
`hp_exercise_hour` for `hp_exercise_min` minutes – HC only signals, the PLC runs its pumps and valves. With it on, it
replaces the 24 h no-demand stop below.

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

from .clock import rebase
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
    hp_charge_needs_demand: bool = False  # 0.59.0: the charge % starts / keeps a heating only with a room demand
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
    hp_auto_summer: bool = False  # 0.57.0: summer mode after a long time with no room demand
    hp_summer_after_h: float = 24.0
    hp_winter_after_s: float = 1800.0  # back to winter: the circuits' demand lasted this long (0 = at once)
    hp_exercise: bool = False  # 0.57.0: an "exercise due" signal in summer mode, for the PLC
    hp_exercise_weekday: int = 0  # 0 = Monday
    hp_exercise_hour: int = 10
    hp_exercise_min: float = 10.0
    hp_charge_mode: str = "classic"  # 0.65.0: classic | demand (which rule drives; both are shown)
    hp_start_margin: float = 3.0  # 0.65.0 demand: start when the top < need + this
    hp_start_kwh: float = 0.0  # 0.65.0 demand: start when the usable reserve above the need < this kWh (0 = not used)
    hp_stop_layer: str = "lower"  # 0.65.0 demand: the layer that must reach need + hp_stop_margin
    hp_stop_margin: float = 3.0  # 0.65.0 demand
    hp_coil_dt: float = 3.0  # 0.65.0 demand: the tank stays this much under the heat pump's flow target
    hp_lead_min: float = 60.0  # 0.68.0 demand: start when the reserve runs out within this (from the trend; 0 = off)
    hp_deadband: float = 2.0
    hp_confirm_s: float = 600.0
    hp_min_interval_s: float = 2700.0
    hp_max_rise: float = 3.0
    hp_urgent: float = 6.0
    # 0.69.0 (a tester: 44.5 °C worked out, 39 °C given, the unit stopped its compressor on its own target with the tank
    # not charged): a new charge gives the full target at once, and so does a running charge whose compressor stopped
    # below it – the hold's confirmation, interval and ramp then only smooth the changes within a charge
    hp_charge_jump: bool = True
    hp_running_w: float = 100.0  # 0.69.0: a power reading above this (W) means the compressor runs (was fixed 100 W)
    hp_standby_w: float = 10.0  # 0.70.0: between this and hp_running_w: switched on, the compressor stands (standby)

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
    asking: bool | None = None  # 0.57.0: a zone asks right now (None: as `demand`)


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
    hp_state: str | None = None  # 0.70.0: heating | standby | stopped | unknown (None: no signal given)
    hp_power_w: float | None = None  # 0.70.0: the power reading behind it (W)
    hp_running_age_s: float | None = None  # 0.59.0: seconds since that reading was reported
    offset: float | None = None  # the manual offset now (the number entity)
    layers: tuple = ()  # 0.65.0: (name, °C or None, litres or None, measured) top first


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
    summer: bool = False  # 0.57.0
    exercise: bool = False  # 0.57.0: exercise due (summer mode only)


ZONE_HOLD_S = 1800.0  # 0.57.1: as a circuit's `circuit_hold_s`

REASONS = ["fail_safe_on", "no_outdoor", "no_buffer", "cold_on", "frost", "low_charge", "heat_needed", "heating",
           "charging", "wood", "summer", "idle_off", "standby", "off", "min_on", "min_off",
           # 0.65.0 demand-based charging
           "reserve_low", "reserve_low_kwh", "charging_reserve", "reserve_ok", "reserve_full", "no_demand",
           "reserve_runs_out",  # 0.68.0
           "safety_stop",  # 0.77.0
           "failsafe"]  # 0.78.2: the step failed FAILSAFE_AFTER times in a row (security review H2)
CHARGE_MODES = ("classic", "demand")
TREND_MIN_C_H = 0.2  # 0.68.0: a slower cooling (°C/h of the tank mean) is no trend to time the start by
STOP_LAYERS = ("top", "upper", "lower", "bottom")
WH_PER_L_K = 1.163


class HeatPumpCoordinator:
    def __init__(self, cfg: HpConfig | None = None) -> None:
        self.cfg = cfg or HpConfig()
        self.hold = SetpointHold(self.cfg.hold())
        self.enable = False
        self.heating = False  # the heat demand (A), with its own hysteresis
        self.alt_heating = False  # 0.65.0: the latch of the rule not driving (shown for comparison)
        self.last_change: datetime | None = None  # of the enable request
        self.cold_latched = False
        self.warm_since: datetime | None = None  # outdoor above the release limit since
        self.last_demand: datetime | None = None  # a circuit demand or a heat demand last seen
        self.summer = False  # 0.57.0
        self.summer_since: datetime | None = None
        self.last_room: datetime | None = None  # a circuit / zone demand last seen (not the tank's)
        self.ask_since: datetime | None = None  # the circuits' demand without a break since
        self.zones_last_ask: datetime | None = None  # 0.57.1: the buffer's own zones last asked (no circuit linked)

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

    def _season(self, now: datetime, lasting: bool, asking: bool) -> str | None:
        """0.57.0: summer / winter from the house's own demand; returns what changed (or None)."""
        cfg = self.cfg
        if lasting or self.last_room is None:
            self.last_room = now
        self.ask_since = (self.ask_since or now) if lasting else None
        if not cfg.hp_auto_summer:
            changed = "winter" if self.summer else None
            self.summer, self.summer_since = False, None
            return changed
        if self.summer:
            held = (now - self.ask_since).total_seconds() if self.ask_since else None
            if held is not None and held >= cfg.hp_winter_after_s and asking:
                self.summer, self.summer_since = False, None
                return "winter"
            return None
        if (now - self.last_room).total_seconds() >= cfg.hp_summer_after_h * 3600:
            self.summer, self.summer_since = True, now
            return "summer"
        return None

    def _exercise(self, now: datetime) -> bool:
        cfg = self.cfg
        if not (cfg.hp_exercise and self.summer):
            return False
        start = now.replace(hour=int(cfg.hp_exercise_hour) % 24, minute=0, second=0, microsecond=0)
        return now.weekday() == int(cfg.hp_exercise_weekday) % 7 and 0 <= (now - start).total_seconds() < cfg.hp_exercise_min * 60

    def _need(self, i: HpInputs) -> float | None:
        needs = [c.target + c.margin for c in i.circuits if c.demand and c.target is not None]
        return round(max(needs), 1) if needs else None

    def _heat(self, i: HpInputs, need: float | None, wood: str, demand: bool = True,
              heating: bool | None = None) -> tuple[bool, str]:
        cfg = self.cfg
        heating = self.heating if heating is None else heating
        frost = i.top is not None and i.top <= i.frost_top
        # 0.59.0: with `hp_charge_needs_demand` the charge percentage only counts while a room / circuit asks for heat
        by_charge = demand or not cfg.hp_charge_needs_demand
        low = by_charge and cfg.hp_charge_on > 0 and i.charge is not None and i.charge <= cfg.hp_charge_on
        if frost:
            return True, "frost"
        if cfg.hp_wood_first and wood in ("certain", "likely"):
            # 0.56.1: wood first – before a low charge and also over a heating that already runs; frost (above),
            # the cold-weather ON and a fail-safe ON (the enable request, in step) still stand
            return False, "wood"
        if low:
            return True, "low_charge"
        if heating:
            if need is not None and i.top < need + cfg.hp_hyst:
                return True, "heating"
            if by_charge and cfg.hp_charge_off > 0 and i.charge is not None and i.charge < cfg.hp_charge_off:
                return True, "charging"
            return False, "off"
        if need is not None and i.top < need:
            if wood in ("certain", "likely"):
                return False, "wood"  # another source charges the tank: let it
            return True, "heat_needed"
        return False, "off"

    def reserve(self, i: HpInputs, need: float | None, flow: float | None) -> dict:
        """0.65.0: the tank's reserve over the need, and the demand rule's start / stop points (information too)."""
        cfg = self.cfg
        out: dict = {"need": need}
        if need is None or i.top is None:
            return out
        out["reserve_c"] = round(i.top - need, 1)
        layers = [lv for lv in i.layers if lv[1] is not None]
        if layers and all(lv[2] for lv in layers):
            out["reserve_kwh"] = round(sum(lv[2] * WH_PER_L_K * max(lv[1] - need, 0.0) for lv in layers) / 1000, 2)
        out["start_below"] = round(need + cfg.hp_start_margin, 1)
        stop = need + cfg.hp_stop_margin
        if flow is not None:
            stop = min(stop, flow - cfg.hp_coil_dt)  # (E) the coil cannot make the tank warmer than this
        out["stop_at"] = round(max(stop, need), 1)
        order = [n for n in STOP_LAYERS if any(lv[0] == n for lv in i.layers)]
        want = cfg.hp_stop_layer if cfg.hp_stop_layer in STOP_LAYERS else "lower"
        names = list(STOP_LAYERS)
        pick = None
        for n in reversed(names[:names.index(want) + 1]):  # the layer, else the nearest measured one above it
            lv = next((x for x in i.layers if x[0] == n and x[1] is not None and (len(x) < 4 or x[3])), None)
            if lv is not None:
                pick = lv
                break
        out["stop_layer"] = pick[0] if pick else "top"
        out["stop_layer_temp"] = round(pick[1], 1) if pick else round(i.top, 1)
        out["layers_seen"] = order
        if i.trend_c_h is not None and i.trend_c_h < -0.05:
            out["hours_left"] = round(max(i.top - need, 0.0) / -i.trend_c_h, 2)
        if self.cfg.hp_lead_min > 0:
            out["lead_min"] = self.cfg.hp_lead_min  # 0.68.0: the start by the trend
        return out

    def _heat_demand(self, i: HpInputs, need: float | None, wood: str, demand: bool, heating: bool,
                     res: dict) -> tuple[bool, str]:
        """0.65.0: the demand-based charging rule (see the module text)."""
        cfg = self.cfg
        if i.top is not None and i.top <= i.frost_top:
            return True, "frost"
        if cfg.hp_wood_first and wood in ("certain", "likely"):
            return False, "wood"
        if need is None or not demand:
            return False, "no_demand"
        if heating:
            if res["stop_layer_temp"] < res["stop_at"]:
                return True, "charging_reserve"
            return False, "reserve_full"
        if wood in ("certain", "likely"):
            return False, "wood"
        if i.top < res["start_below"]:
            return True, "reserve_low"
        if cfg.hp_start_kwh > 0 and res.get("reserve_kwh") is not None and res["reserve_kwh"] < cfg.hp_start_kwh:
            return True, "reserve_low_kwh"
        # 0.68.0: the tank cools steadily (at least TREND_MIN_C_H) and at this pace the top reaches the need within the
        # heat pump's lead time – start now, so the coil's heat is up there in time
        if (cfg.hp_lead_min > 0 and i.trend_c_h is not None and i.trend_c_h <= -TREND_MIN_C_H
                and res.get("hours_left") is not None and res["hours_left"] * 60 <= cfg.hp_lead_min):
            return True, "reserve_runs_out"
        return False, "reserve_ok"

    def _switch(self, now: datetime, want: bool, force: bool) -> str | None:
        """Min on / off of the enable request; `force` (cold ON, fail-safe) ignores them."""
        if want == self.enable:
            return None
        self.last_change = rebase(now, self.last_change, self.enable, self.cfg.hp_min_on_s)  # 0.78.2 (M5)
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
        # 0.79.1: where the correction in use comes from – the settings form's value, or the number entity set apart
        # from it (it wins until the form is saved again); shown next to the offset so the two are never confused
        details: dict = {"offset": offset, "offset_form": cfg.hp_offset,
                         "offset_source": "entity" if i.offset is not None and i.offset != cfg.hp_offset else "form",
                         "top": i.top, "charge": i.charge, "trend_c_h": i.trend_c_h,
                         "hp_running": i.hp_running, "hp_running_age_s": i.hp_running_age_s,
                         "hp_state": i.hp_state, "hp_power_w": i.hp_power_w}
        # 0.57.1: the buffer's own zones (no circuit linked) get the circuits' hold too: a TPI pause does not end their
        # demand, so the summer mode can end on a lasting demand
        if i.zones_asking:
            self.zones_last_ask = now
        zones_lasting = self.zones_last_ask is not None and (now - self.zones_last_ask).total_seconds() <= ZONE_HOLD_S
        demand_now = any(c.demand for c in i.circuits) or zones_lasting
        asking = any(c.demand if c.asking is None else c.asking for c in i.circuits) or i.zones_asking
        season = self._season(now, demand_now, asking)
        # 0.65.0: both charging rules, each with its own latch; `hp_charge_mode` says which one drives
        mode = cfg.hp_charge_mode if cfg.hp_charge_mode in CHARGE_MODES else "classic"
        if mode == "demand" and not i.circuits:
            mode = "classic"  # a tank with only its own zones: no circuit need to charge by
            details["charge_mode_fallback"] = True
        flow = None if need is None else max(cfg.hp_flow_min, min(cfg.hp_flow_max, need + cfg.hp_reserve + offset))
        res = self.reserve(i, need, flow)
        details["charge_mode"] = mode
        if i.top is None:
            heat, why = self.heating, "no_buffer"
        else:
            latch_c = self.heating if mode == "classic" else self.alt_heating
            latch_d = self.heating if mode == "demand" else self.alt_heating
            c_heat, c_why = self._heat(i, need, wood, demand_now, latch_c)
            d_heat, d_why = self._heat_demand(i, need, wood, demand_now, latch_d, res) if "stop_at" in res \
                else (latch_d if need is not None else False, "no_demand" if need is None else "no_buffer")
            details["classic"] = {"heat": c_heat, "why": c_why}
            details["demand_charge"] = {"heat": d_heat, "why": d_why, **res}
            if mode == "demand":
                heat, why, self.alt_heating = d_heat, d_why, c_heat
            else:
                heat, why, self.alt_heating = c_heat, c_why, d_heat
            if (self.cfg.hp_charge_needs_demand and not demand_now and self.cfg.hp_charge_on > 0 and i.charge is not None
                    and i.charge <= self.cfg.hp_charge_on):
                details["low_charge_waits"] = True  # 0.59.0: a low charge, but no room asks – no start for it
        if self.summer and why != "frost":
            heat, why = False, "summer"  # 0.57.0: no heating for the tank in summer mode; the frost limit still heats
        was_heating, self.heating = self.heating, heat
        details.update(summer_since=self.summer_since.isoformat() if self.summer_since else None,
                       room_idle_hours=round((now - self.last_room).total_seconds() / 3600, 2) if self.last_room else None,
                       demand_held_s=round((now - self.ask_since).total_seconds()) if self.ask_since else None,
                       season_change=season)
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
            details["heat_reason"] = why  # 0.79.0: always there while it charges (not only under the cold-weather ON)
        elif self.summer:
            want, reason = False, "summer"  # 0.57.0: it replaces standby and the 24 h stop
        elif cfg.hp_standby:
            idle = cfg.hp_idle_off and idle_h is not None and idle_h >= cfg.hp_idle_hours
            want, reason = (False, "idle_off") if idle else (True, "standby")
            if why == "wood":
                reason = "wood" if not idle else reason
        else:
            want, reason = False, why if why in ("wood", "no_demand", "reserve_ok", "reserve_full") else "off"
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
        jump = None
        if cfg.hp_charge_jump and heat and self.hold.value is not None and raw - self.hold.value >= 0.5:
            if not was_heating:
                jump = "charge_start"
            elif i.hp_running is False and raw - self.hold.value >= 1.0:
                jump = "compressor_stopped"
        if jump is not None:
            res = self.hold.jump(now, raw, cfg.hp_flow_min, cfg.hp_flow_max, jump)
            details["jump"] = jump
        else:
            res = self.hold.step(now, raw, cfg.hp_flow_min, cfg.hp_flow_max)
        details.update(next_allowed=res.next_allowed.isoformat() if res.next_allowed else None,
                       last_change=self.last_change.isoformat() if self.last_change else None,
                       target_changed=res.changed, warm_since=self.warm_since.isoformat() if self.warm_since else None)
        return HpDecision(now, self.enable, heat, reason, res.value, res.raw, res.reason, need, wood, cold, details,
                          self.summer, self._exercise(now))

    # --- restart ----------------------------------------------------------------------------------------------
    def state(self, now: datetime) -> dict:
        iso = lambda d: d.isoformat() if d else None  # noqa: E731
        return {"hold": self.hold.state(now), "enable": self.enable, "heating": self.heating, "alt_heating": self.alt_heating,
                "last_change": iso(self.last_change), "cold_latched": self.cold_latched,
                "warm_since": iso(self.warm_since), "last_demand": iso(self.last_demand),
                "summer": self.summer, "summer_since": iso(self.summer_since), "last_room": iso(self.last_room),
                "ask_since": iso(self.ask_since), "zones_last_ask": iso(self.zones_last_ask)}

    def restore(self, data: dict, now: datetime) -> None:
        def when(key):
            try:
                return datetime.fromisoformat(data[key]) if data.get(key) else None
            except (TypeError, ValueError):
                return None
        self.hold.restore(data.get("hold") or {}, now)
        self.enable = bool(data.get("enable", False))
        self.heating = bool(data.get("heating", False))
        self.alt_heating = bool(data.get("alt_heating", False))
        self.cold_latched = bool(data.get("cold_latched", False)) and self.cfg.hp_cold_on
        self.last_change, self.warm_since, self.last_demand = when("last_change"), when("warm_since"), when("last_demand")
        self.summer = bool(data.get("summer", False)) and self.cfg.hp_auto_summer
        self.summer_since = when("summer_since") if self.summer else None
        self.last_room, self.ask_since = when("last_room"), when("ask_since")
        self.zones_last_ask = when("zones_last_ask")

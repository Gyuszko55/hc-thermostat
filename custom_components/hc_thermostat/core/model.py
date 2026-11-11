"""Inputs, configuration and decisions exchanged with the supervisor."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import StrEnum
from typing import Any, Mapping

from .floor import floor_limit, temper_offset


class Presence(StrEnum):
    HOME = "home"
    AWAY = "away"
    VACATION = "vacation"


class Reason(StrEnum):
    """Why the supervisor decided what it decided (one per decision)."""

    REGULATING = "regulating"
    AT_TARGET = "at_target"
    BOOST = "boost"
    AFTERHEAT = "afterheat"
    FROST = "frost"
    DISABLED = "disabled"
    SENSOR_LOST = "sensor_lost"
    WINDOW = "window"
    SEASON_OFF = "season_off"
    RESTART_HOLD = "restart_hold"
    RESTART_BURN = "restart_burn"
    EXTERNAL = "external"
    VALVE_EXERCISE = "valve_exercise"
    AC_HEAT = "ac_heat"
    AC_COOL = "ac_cool"
    AC_PAUSE = "ac_pause"
    FLOOR_LIMIT = "floor_limit"
    FLOOR_COOL = "floor_cool"
    DEW_POINT = "dew_point"
    STORAGE_CHARGE = "storage_charge"
    STORAGE_WAIT = "storage_wait"
    FLOOR_TEMPER = "floor_temper"
    THERMOSTAT_CALL = "thermostat_call"
    THERMOSTAT_IDLE = "thermostat_idle"


@dataclass(frozen=True)
class Reading:
    """A sensor value; ``value`` is None when unavailable."""

    value: float | None = None
    age_s: float = 0.0

    def fresh(self, max_age_s: float) -> float | None:
        return self.value if self.value is not None and self.age_s <= max_age_s else None


@dataclass(frozen=True)
class Inputs:
    now: datetime
    indoor: Reading = Reading()
    outdoor: Reading = Reading()
    outdoor_avg: float | None = None
    presence: Presence = Presence.HOME
    window_open: bool = False
    enabled: bool = True
    uptime_s: float = 1e9
    actual_heating: bool | None = None
    heat_energy_kwh: float | None = None  # cumulative heat delivered by every source
    other_heat_kw: float = 0.0  # current heat from sources other than this boiler
    drop_temps: tuple = ()  # (entity_id, Reading) pairs watched for a fast drop (open window)
    unit_temp: float | None = None  # air conditioner: the indoor unit's own reading
    unit_step: float | None = None
    unit_min: float | None = None
    unit_max: float | None = None
    yield_margin: float = 0.0  # house: the other (cheaper) source leads, regulate this much below the target
    assist_target: float | None = None  # air conditioner: help the house up to this target (cheaper and coupled)
    room_demand: tuple = ()  # TRV rooms asking for heat (single zone, optional); never above the main target
    floor: Reading = Reading()  # floor temperature (floor heating; limit and, for an electric floor, a safety input)
    humidity: Reading = Reading()
    coil: Reading = Reading()  # fan coil: coil / supply water temperature
    return_temp: Reading = Reading()  # district heating: return water temperature
    power_available: bool | None = None  # controlled power (off-peak circuit) on; None: no signal configured  # room relative humidity in % (floor cooling: dew point)
    hp_mode: str | None = None  # heat pump busy with something else: "defrost" | "dhw" (hot water); None: heating
    call: bool | None = None  # wired wall thermostat (0.38.0): its contact asks for heat; None: unknown / unavailable


@dataclass(frozen=True)
class HcConfig:
    """Every limit and default of one installation; values are user editable."""

    control: str = "tpi"  # tpi | pid | external | curve (heating curve, EXPERIMENTAL) | onoff (long runs, heat pump) | storage
    target_home: float = 21.0
    target_night: float = 19.0
    target_away: float = 17.0
    target_vacation: float = 15.0
    target_comfort: float = 22.0
    target_eco: float = 18.0
    # Presets: which ones are offered, and when a preset chosen by hand ends
    # (revoke = until changed, next_change = next night start/end, home = until someone arrives, hours = after N hours)
    presets_enabled: tuple = ("comfort", "home", "sleep", "eco", "away", "vacation", "boost")
    expiry_comfort: str = "hours"
    expiry_home: str = "next_change"
    expiry_sleep: str = "next_change"
    expiry_eco: str = "revoke"
    expiry_away: str = "home"
    expiry_vacation: str = "home"
    hours_comfort: float = 3.0
    hours_home: float = 3.0
    hours_sleep: float = 8.0
    hours_eco: float = 3.0
    hours_away: float = 8.0
    hours_vacation: float = 72.0
    night_start: str = "22:00"
    night_end: str = "06:00"
    frost_temp: float = 7.0
    frost_hysteresis: float = 0.5
    # TPI
    tpi_coef_int: float = 0.6
    tpi_coef_ext: float = 0.01
    yield_margin: float = 0.0  # house: °C below the target while a cheaper source heats the coupled zone; 0 = off
    target_cool: float = 26.0  # air conditioner: cooling target in summer (season off)
    ac_ki_per_hour: float = 0.5  # air conditioner: slow setpoint correction, °C per °C error per hour
    ac_min_change_s: float = 600.0  # air conditioner: at most one setpoint change per this many seconds
    # PID (demand 0..1 per degree / degree-second)
    pid_kp: float = 0.4
    pid_ki: float = 0.00005
    pid_kd: float = 0.0
    pid_d_filter_s: float = 300.0  # 0.40.0: low-pass time constant of the derivative (stepwise sensors); 0 = off
    pid_ke: float = 0.01
    pid_ki_per_hour: float | None = None  # when set, wins over pid_ki (demand per °C per hour; easier to read)
    # Heating curve (control "curve", EXPERIMENTAL – core/curve.py)
    curve_slope: float = 1.4
    curve_shift: float = 0.0
    curve_design_outdoor: float = -15.0
    flow_min: float = 25.0
    flow_max: float = 75.0
    flow_off_delta: float = 3.0
    room_kp: float = 3.0  # °C of flow per °C of room error
    room_ki_per_hour: float = 1.0  # °C of flow per °C of room error per hour
    room_integral_limit: float = 10.0
    heat_pump: bool = False  # longer runs, no short cycling
    hp_min_on_s: float = 1200.0  # heat pump (curve or on/off): shortest run
    hp_min_off_s: float = 600.0  # heat pump: shortest pause
    onoff_hysteresis: float = 0.3  # on/off control: starts this far below the target, stops at target + overshoot_stop
    # Shadow regulator: the other algorithm (PID next to TPI) calculates alongside and switches nothing
    shadow_regulator: bool = False
    # Device limits: no algorithm may override these
    cycle_s: float = 900.0
    min_on_s: float = 300.0
    min_off_s: float = 300.0
    keep_alive_s: float = 0.0  # resend "on" this often while heating (relay with its own auto-off timer); 0 = off
    # Safety
    sensor_max_age_s: float = 7200.0
    sensor_lost_demand: float = 0.35  # an electric heater gets 0 (matrix.source_defaults): no heat on a lost sensor
    # 0.40.0: with a learned heat loss and the source power known, the blind demand is the house's heat need now
    # (loss × (target − outdoor) − other sources) / boiler_power_kw instead of the fixed sensor_lost_demand
    sensor_lost_model: bool = True
    # 0.41.0: a room reading unchanged for this many hours while the source ran frozen_burn_min minutes is frozen
    frozen_after_h: float = 3.0  # 0 = off
    frozen_burn_min: float = 45.0
    # Floor temperature limit (floor heating): above floor_max no heat, whatever the regulator says; back below
    # floor_max - floor_hysteresis. floor_required: no fresh floor reading = no heat (electric floor heating).
    floor_max: float = 0.0  # 0 = by the covering and the probe position (core/floor.py; electric 27 °C, else none)
    floor_covering: str = ""  # "" (not given) | tiles | laminate | wood | vinyl | carpet (0.37.0)
    floor_probe: str = "surface"  # surface (under the covering) | screed (between the pipes) | above_pipe (0.37.0)
    floor_hysteresis: float = 1.0
    floor_required: bool = False
    floor_max_age_s: float = 7200.0  # relay off: a still floor sensor may report rarely
    floor_max_age_on_s: float = 1800.0  # while heating the floor changes and reports
    overshoot_stop: float = 0.3
    # Floor tempering (0.35.0, core/floor.py): keep the floor slab warm even when the room is warm enough (comfort);
    # floor heating with a floor sensor and a relay control (TPI, PID, on/off) only. Off by default.
    floor_temper: bool = False
    floor_temper_offset: float = 0.0  # °C above the room target; 0 = by the floor covering (tiles 2, others 3, none 2)
    floor_temper_night: float = 0.0  # absolute floor target at night / in the sleep preset; 0 = the day rule
    floor_temper_hysteresis: float = 0.3  # back on this far below the floor target
    floor_temper_room_margin: float = 0.5  # no tempering once the room is at target + this (0.39.2: 1.0 → 0.5, less swing)
    # Lost room thermometer (0.36.0): hold the floor at the tempering target by the floor sensor instead of the blind
    # demand (or, electric, of no heat). Floor heating with a floor sensor and a relay control only.
    floor_fallback: bool = True
    floor_system: bool = False  # floor heating (water or electric): set from the system, not an option
    demand_contact: bool = False  # a wired wall thermostat gives the demand (0.38.0): set from demand_entity, not an option
    # Restart behaviour
    restart_grace_s: float = 120.0
    restart_margin: float = 1.0
    restart_burn_window_s: float = 900.0
    # Season (daily average outdoor temperature, with hysteresis)
    season_enabled: bool = True
    season_off_above: float = 15.0
    season_on_below: float = 13.0
    # Window
    window_delay_s: float = 120.0
    # Open window from a fast temperature drop (core/window_drop.py); the sensors are chosen in the options
    window_drop_rate: float = 1.5  # °C per hour
    window_drop_min: float = 0.3
    window_drop_lookback_min: float = 30.0
    window_drop_min_span_min: float = 5.0
    window_drop_recover: float = 0.2
    window_drop_quiet_min: float = 15.0
    window_drop_max_min: float = 45.0
    window_drop_cooldown_min: float = 30.0
    # Failure detection
    failure_minutes: float = 30.0
    failure_min_drop: float = 0.1
    failure_deficit: float = 0.3
    # Boost: full demand after a large deficit, stopped early by a forecast of the after-heat
    boost_enabled: bool = False
    boost_min_deficit: float = 0.8
    boost_afterheat: float = 0.8  # degrees the radiators still add after a long burn
    boost_afterheat_ref_min: float = 10.0  # burn minutes at which half of that after-heat is expected
    boost_trim: float = 0.0  # stop this much earlier (+) or later (-); learned in a later release
    boost_minutes_per_degree: float = 17.0  # only for the safety limit below
    boost_max_factor: float = 1.5
    boost_max_minutes: float = 60.0
    # After a boost: no new burn while the after-heat still lifts the house
    boost_quiet_minutes: float = 20.0
    boost_quiet_rise_minutes: float = 10.0  # ...or while it rose within this many minutes
    boost_quiet_max_minutes: float = 60.0
    boost_quiet_drop: float = 0.2  # a fall this big below the peak ends the quiet time
    # Learning (core/learning.py): after-heat, minutes per degree, trim; TPI strength and holding offset
    learning_enabled: bool = True
    learning_settle_s: float = 7200.0
    # Boiler health (core/boiler_health.py)
    power_idle_w: float = 20.0  # below this the boiler stands by
    power_burn_w: float = 115.0  # at or above this the burner burns (between: only the pump)
    health_no_data_min: float = 10.0
    health_no_response_min: float = 3.0
    health_no_ignition_min: float = 5.0
    health_flame_lost_min: float = 15.0
    health_max_starts_per_hour: int = 8  # regulating hours count for the TPI only this long after a target change
    # 0.23.0: burning with the relay off (stuck relay, hand switch); a combi boiler also burns for hot water, so
    # only this many minutes of it in an hour count – an electric heater draws nothing with its relay off
    health_uncommanded_min: float = 45.0
    health_uncommanded_electric_min: float = 5.0
    # 0.23.0: overheating – this far above the target, still rising, and heating this many of the last 30 minutes
    health_overheat_margin: float = 2.0
    health_overheat_min: float = 20.0
    # 0.23.0: believable readings (core/plausibility.py) and when a sensor problem is reported
    plaus_indoor_min: float = 3.0
    plaus_indoor_max: float = 35.0
    plaus_outdoor_min: float = -45.0
    plaus_outdoor_max: float = 55.0
    plaus_jump: float = 4.0
    plaus_confirm_s: float = 600.0
    sensor_problem_after_s: float = 600.0
    # Summer valve exercise for zone instances (core/exercise.py)
    valve_exercise: bool = False
    exercise_weekday: int = 0  # 0 = Monday
    exercise_time: str = "10:00"
    exercise_s: float = 600.0
    exercise_idle_days: float = 7.0
    # Heat need: replaces the outdoor coefficient once the loss is learned (0 = not used)
    boiler_power_kw: float = 0.0
    # Electric zones sharing a power budget (0.28.0, core/load.py): 0 = no limit; the own power is boiler_power_kw
    load_limit_kw: float = 0.0
    # Floor cooling with dew point protection (0.29.0, core/cooling.py): heat pump on a floor, curve or on/off
    floor_cooling: bool = False
    dew_margin: float = 2.0  # the flow and the floor stay this far above the dew point
    cool_flow: float = 18.0  # curve: cooling flow setpoint (raised to dew point + margin)
    cool_flow_max: float = 22.0  # curve: a safe flow above this would hardly cool – stop instead
    floor_min_cool: float = 19.0  # floor sensor: no colder floor than this (comfort)
    humidity_max_age_s: float = 3600.0
    # TRV rooms (0.30.0, core/trv.py): calibration of the heads by the room thermometers (offsets: trv_offsets)
    trv_calibration: bool = False
    # Storage heater on controlled power (0.31.0, core/storage.py)
    storage_window_start: str = "22:00"
    storage_window_end: str = "06:00"
    storage_charge_h: float = 7.0  # a full charge takes this long
    storage_bias: float = 0.0  # added to the charge fraction (−0.5…+0.5): the user's correction
    storage_discharge_hyst: float = 0.3
    # Fan coil (0.32.0, core/fancoil.py): set by the system "fan_coil"
    fan_coil: bool = False
    fan_min_pct: float = 30.0
    fan_overrun_s: float = 120.0
    fan_min_coil: float = 30.0  # °C – with a coil sensor: no fan below this (no cold draught)
    # District heating return limit (0.32.0): 0 = off; the valve closes while the return is this warm
    return_max: float = 0.0
    return_hysteresis: float = 3.0  # many humidity sensors report only on a change

    @property
    def temper_offset(self) -> float:
        """The floor tempering offset in effect (°C above the room target)."""
        return temper_offset(self.floor_temper_offset, self.floor_covering)

    @property
    def floor_limit(self) -> float:
        """The floor limit in effect: floor_max, else by the covering and the probe (0.37.0), else 27 °C electric /
        29 °C water."""
        return floor_limit(self.floor_max, self.floor_covering, self.floor_probe, self.floor_required)[0]

    @property
    def floor_limit_from(self) -> str:
        """Where the floor limit comes from: manual | covering | electric | water."""
        return floor_limit(self.floor_max, self.floor_covering, self.floor_probe, self.floor_required)[1]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "HcConfig":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known and v is not None})


@dataclass(frozen=True)
class ExternalCommand:
    """What an external thermostat should be set to."""

    hvac: str  # heat | cool | off
    target: float


@dataclass(frozen=True)
class Decision:
    now: datetime
    reason: Reason
    target: float
    indoor: float | None
    outdoor: float | None
    demand: float = 0.0
    output: bool = False
    limited_by: str | None = None
    fault: bool = False
    loss_kw_per_k: float | None = None
    heat_need_kw: float | None = None
    other_heat_kw: float = 0.0
    external: ExternalCommand | None = None
    manual: bool = False  # the target was set by hand
    manual_until: datetime | None = None  # when a manual target ends (None: at the next preset or presence change)
    shadow: dict[str, Any] | None = None  # the shadow regulator: what it would ask for and switch
    flow_setpoint: float | None = None  # heating curve: the flow temperature asked for (None: off)
    details: dict[str, Any] = field(default_factory=dict)

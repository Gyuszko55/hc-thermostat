# <img src="images/icon.png" alt="HC Thermostat icon" width="44" align="absmiddle"> HC Thermostat (Heat Conductor Thermostat)

[Magyar leírás](README.hu.md)

> **Beta.** It runs a real home's heating, but every installation differs: a new instance always starts in
> **shadow mode** (it calculates and compares, switches nothing). Go live only after you have checked its decisions,
> and keep an independent backup thermostat (see Safety). The heating curve, cooling and the newer sources
> (storage heater, district heating, fan coil, pellet / buffer) are tested in a simulator and a test instance only.

HC Thermostat is a heating **supervisor** for Home Assistant, with a built-in regulator for simple systems. It does not try to replace good thermostat integrations. It sits above them and decides what the house should do, and says why.

## Quick start

**Requirements:** Home Assistant **2026.10** or newer; a room thermometer, and what HC switches or sets (a relay
`switch` / `input_boolean`, an existing `climate` thermostat or AC unit, or a flow setpoint `number`). °C and °F
both work (0.45.0): readings in °F are converted, and what HC writes to a thermostat is sent in your system's unit.

1. **Install:** HACS → ⋮ → Custom repositories → `https://github.com/Gyuszko55/hc-thermostat`, type *Integration* →
   download **HC Thermostat** → **restart** Home Assistant.
2. **Add:** Settings → Devices & services → Add integration → **HC Thermostat** → choose **the setup wizard
   (recommended)** – a link opens the **HC setup** panel (worked-out settings and rooms; for administrators) – or the
   manual setup: a name, the heat source and the system, the devices, then the targets and the timing.
3. **Watch it in shadow mode:** a new instance calculates and logs what it would do, switches nothing. The
   **HC info** panel and the decision sensor show why.
4. **Go live:** Settings → Devices & services → HC Thermostat → **Configure** → **Go live**, tick the confirmation.
   (The wizard's summary can also start a new instance live.) Back to shadow the same way.

**Presence** (`presence_entities`): home is any of `home`, `on`, `otthon` (a `person` / `device_tracker` at home, a
binary sensor on); vacation is `vacation`, `szabadság`, `szabadsag`; anything else (a zone name, `not_home`, `off`)
is away. With no presence entity the house is always home.

**Removing an instance:** HC writes nothing back – a TRV head or a managed thermostat keeps the last target HC sent,
and a relay stays as it is. Set them by hand if needed. When the last instance is deleted, the HC panels leave the
sidebar too (they come back with the next instance).

## Features

**Heat sources and systems**
- Gas boiler (on/off), modulating boiler with heating curve, electric heater, electric floor, heat pump, air conditioner, storage heater, district heating, pellet boiler.
- Radiators, water or electric floor (one room or zones), fan coil, room units; a central boiler with zones and a buffer tank role.

**Control**
- Own regulator: TPI or PID with PWM, on/off with long runs, weather-compensated heating curve, or an external thermostat / air conditioner driven by its setpoint.
- Minimum run and pause times that no algorithm may override; a shadow regulator runs the other algorithm side by side for comparison.
- Shadow mode (calculates, switches nothing) or active mode, per instance.

**Comfort and presence**
- Presets (comfort, home, sleep, eco, away, vacation, boost) with their own expiry; night schedule.
- Presence per instance: the house can follow the household, one room one person (see below).
- Boost that stops when the after-heat will reach the target; learning of after-heat, minutes per degree and holding.
- Target taken over from a wall thermostat or number entity; a wired wall thermostat contact as the demand.

**Floor heating**
- Floor limit by covering and sensor position, floor tempering (warm floor), floor fallback when the room thermometer is lost, floor cooling with dew point protection.

**Rooms and zones**
- Rooms of one boiler (0.43.0): a leading room drives the boiler, every other room has its own HC thermostat – TRV rooms with their own target, calibration against the room thermometer(s) and presence per room, rooms without a TRV follow the house; TRV rooms with their own offset and calibration; zone flow requests and flow cap for a central modulating boiler; load limit shared by electric zones; adjoining room (door open) and cheaper-source advice.

**Safety and supervision**
- Open window pause (sensor or a fast temperature drop), summer rest, frost protection, restart protection, implausible readings, lost sensor fallback.
- Boiler health from power and flame (no response, no ignition, short cycling, uncommanded burn, overheating) with a fault sensor.
- Weekly valve and pump exercise; controlled power signal; district heating return limit.

**Tools**
- Setup wizard in the sidebar, HC info panel (the system drawn with every value), decision log and texts in English and Hungarian, heat loss and heat need estimate, cost comparison.
- Companion round dial card: [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card).

## Basics

- **Shadow mode (default):** calculates everything, switches nothing, and compares itself with your real heating.
- **Own regulator:** TPI or PID with PWM for on/off relays, with minimum run and pause times that no algorithm may override.
- **External thermostat:** sets the target and mode of any `climate` entity.
- **Supervision:** presence and night schedule, open window pause, summer rest, frost protection, lost sensor fallback, restart protection, fault detection, optional boost.
- **Decision log** in English and Hungarian.
- **Control matrix:** heat source and hydraulics give a recommended control. These are engineering defaults, not an installation design.

## Presence per room

- Every instance has its own presence entities (`presence_entities`): a person, a binary sensor, an input boolean, or
  any entity that says home / on / Otthon, or vacation / Szabadság. With several, the instance is home while any of
  them is home, away when none is, and on vacation when one of them says so.
- So the whole house can follow the household, and one room can follow one person: when that person is away, only
  their room drops to the Away (later Vacation) target, the rest of the house heats as before; back home, the room
  returns to its own target. It works the same way as the house-level presence control.
- Examples: in a large family house the room of a grown-up child who is away stays on a setback; in a guesthouse or a
  hotel a room that is not let (an input boolean or a booking sensor per room) stays on a setback, while a let room
  heats normally.
- The away and vacation targets and how long a chosen preset lasts are set per instance.

## Setup wizard (0.21.0)

A sidebar panel, **HC setup** (admins only), walks through six steps: what to set up (a new instance or an
existing one) → heat source → system and control, with the recommendation matrix and its reason → the devices
(only the fields the chosen control needs, with first suggestions) → the settings worked out from them, each
with its reason and editable (cycle and minimum burn from the system, the AC unit's step and limits, heat per
cubic metre of gas, the boiler's idle and burning draw from two days of its power sensor, room thermometers) →
summary and save. A new instance always starts in shadow mode. The panel is there once the first HC instance
exists (add the first one under Settings → Devices & services).

## Electric floor heating, floor limit, target source (0.25.0)

- **Electric floor heating** (a heating mat or cable under the floor) is a recommended combination: TPI or PID with
  PWM on the relay, a 30 minute cycle and a 5 minute minimum by default.
- **Floor temperature limit:** a floor sensor and a maximum (27 °C by default for an electric floor). Above it the
  relay goes off at once, whatever the regulator says, and comes back 1 °C below. For an electric floor the floor
  sensor is required: without a fresh reading it does not heat. For a water floor the limit is optional.
- **Lost indoor sensor:** an electric heater (and electric floor) does not heat blind (0 % instead of the 35 %
  fallback of a boiler); a floor sensor still protects against frost.
- **Target source:** a wall thermostat (or a number) whose setpoint the instance takes over as a manual target
  until the next scheduled change – several zones can follow one knob. What an HC instance wrote there itself is
  not taken over.

## Heat pump (0.26.0)

- **On/off with long runs** (`onoff` control): the heat pump's thermostat input is switched on below the target
  and off when the house reached it – no pulses; the shortest run and pause are adjustable (20 / 10 minutes).
- **Defrost and hot water:** optional signals (a binary sensor, a switch or a mode sensor). While the heat pump
  defrosts or makes hot water, fault detection waits and the health check does not raise an alarm.

## Modulating boiler with zones (0.27.0)

- Every zone instance publishes the flow temperature its own curve asks for (`flow_request`: a floor zone flat and
  low, a radiator zone steeper, plus a correction while the room is short of its target).
- The central instance writes the **highest request of the open asking zones** to an optional flow setpoint entity
  (number / input_number) while the boiler runs; the other zones throttle with their valves. Without any request
  it uses `central_flow_default`; limits `central_flow_min` / `central_flow_max`.
- A floor circuit fed from the same water as radiators still needs its own mixing valve – the floor limit stays on.

## Load limit of electric zones (0.28.0)

- Several electric zones (relay or plug, TPI / PID) can share a power budget, e.g. the main fuse: give each zone its
  own heater power and the same `load_limit_kw`. A zone switches on only when its power fits under the limit.
- A refused zone waits (first come, first served) and its PWM cycle starts when it gets the room – it keeps its
  full on-time, and the zones end up staggered instead of all switching on together. A zone heating without a
  pause hands over to a waiting one at the start of its next cycle. Switching off is never held back; frost
  protection obeys the limit too (the fuse is physical).
- Counts live instances only; the decision text says when a zone waits for its turn.

## Floor cooling with dew point protection (0.29.0)

- A reversible heat pump on a floor (curve or on/off control) can cool in summer, while the heating season rests:
  above `target_cool` + 0.5 °C until the room is below `target_cool` − 0.5 °C.
- The dew point comes from the room temperature and humidity (a humidity sensor is required). The water and the
  floor always stay above the dew point + `dew_margin` (2 °C): in curve control the cooling flow (`cool_flow`,
  18 °C) is raised to it, and when even `cool_flow_max` (22 °C) would not be safe, cooling stops ("too humid").
  A floor sensor pauses the cooling at the safe limit or `floor_min_cool` (19 °C); on/off control requires it.
- Optional: a switch that puts the heat pump into cooling (on all summer, off in the heating season) and a separate
  cooling flow setpoint. A stopped cooling writes the warmest setpoint, never the coldest. Set in the options.

## TRV rooms: own target and calibration (0.30.0)

- Each TRV room of a single zone can have an offset to the house target (options, "TRV rooms" step: e.g. bedroom
  −2 °C, bathroom +1 °C) – it still follows the schedule (night, away).
- Calibration (optional): a head measures next to the hot radiator and closes too early. Where the room has its own
  thermometer, the difference head − room is followed slowly (30 minute smoothing, at most ±5 °C) and added to the
  target written to the head. A change that only comes from the calibration is written at most every 30 minutes.
- Per head thermometer (0.42.0): for every head the options ("TRV rooms" step) and the setup wizard ("TRV heads")
  offer "the head's own thermometer" (no calibration) or an external thermometer – the list shows the temperature
  sensors of the head's area (not the head's own entities; all of them when the area has none). Saved as
  `trv_sensors` (head → sensor). An instance saved before keeps working as before until it is saved again
  (`trv_calibration` on: the thermometers of the head's area). Another thermometer restarts what was learned.
  HC info and the dial card's "i" open the host instance from a TRV head too.
- A target turned on the head by hand still stays until the room's target changes. The rooms sensor shows
  `trv_rooms` (target, offset, calibration, plan per head).

## Storage heater and controlled power (0.31.0)

- New heat source **storage heater** (room unit, control `storage`): it charges in the controlled-power window
  (22:00–06:00 by default) as much as the outdoor daily average asks for ((target − outdoor) / (target − design
  outdoor), plus a user correction; no outdoor reading: full), and the charge is timed to the end of the window.
  The amount is fixed once charging started. Frost charges full whenever there is power.
- Optional discharge fan / damper: on when the room is 0.3 °C below the target, off at the target; off with an
  open window, out of season and when switched off.
- **Controlled power signal** (any electric heat, optional): while it is off nothing is switched, the regulator
  does not wind up, and the decision text says why.
- **With a power signal (0.39.2)** the storage heater counts the hours really charged and takes every block of
  power inside the window until the worked-out hours are full (controlled power comes in blocks; a charge timed to
  the end of the window would lose a block that drops out). Without a signal it is still timed to the end.

## Heat source with its own control, useful heat delay (0.47.0)

- **Heat source with its own control** (new heat source, "zone valve only"): a PLC, a heat pump's own controller or a
  boiler with its own logic makes the heat and starts the pumps; HC only switches the room's zone valve (TPI / PID +
  PWM, 30-minute cycle by default, long cycles on a floor). No burner, power draw or boiler health is asked or shown.
- **Useful heat delay** (`valve_delay_s`, setup and options, TPI / PID): a thermoelectric valve needs ~5 minutes to
  open, and a pump its own control starts e.g. 5 minutes after the demand – the first 10 minutes of every run give no
  heat. With the delay set, every run is lengthened by it, the minimum on time counts the useful part, and a demand too
  small for a useful run is **carried into the next cycles** until it is worth one (no demand clears it). In a
  simulation (15-minute cycle, 10-minute dead time, 24 h) a quarter to half of the runs ended before any heat arrived
  without it, none with it, and the room kept about twice as close to its target.
- **Setup:** "Add integration" first offers the wizard (its panel is served at once, before any instance) or the manual
  way; the manual way now ends with **basic settings** – targets, night, cycle, minimum on / off time, useful heat delay.

## Measurements (0.48.0)

Optional readings, in **Options → Settings → Measurements** (only those of the instance's heat source). They are
information: the HC info panel shows them (*Measurements*, and per room), and none of them changes a decision.
- **Heat source:** water pressure, real flow / return (ΔT), modulation or compressor %, fault code, hot water signal
  (combi boilers too), flue gas and fuel level (pellet), core temperature (storage heater), the state of a heat source
  with its own control.
- **COP** of a heat pump: give its heat meter (*heat given off*, kWh) next to its energy meter – today, 7 days and the
  season from the daily increase of both.
- **Starts and run time** of every relay / flame instance, per day, week and season.
- **Rooms** (rooms form): radiator thermometers – warm, or cold while the room needs heat – and humidity sensors – dew
  point and mould risk.
- **Alerts** on the boiler problem sensor: low / high pressure, little fuel, too many starts an hour, a fault code, a
  radiator cold too long (limits in the same part).
- **Sensors:** Starts today, Run time today, COP today, ΔT, Mould risk (per room).

## District heating and fan coil (0.32.0)

- **District heating** (new heat source): a zone valve per flat with TPI / PID and a long, calm cycle (30 minutes,
  10 minutes minimum open), or TRV heads in external thermostat mode. Optional **return limit**: with a return water
  sensor and `return_max` set, the valve stays closed while the return is that warm (3 °C hysteresis).
- **Fan coil** (new system, fed by any water source – also a heat pump): TPI / PID switches its water valve, the fan
  (a `fan` entity, by percentage) runs at `fan_min_pct` + the demand while the valve is open and runs on for 2
  minutes after it closes; with a coil sensor it waits until the coil is 30 °C warm (no cold draught).

## Pellet boiler and buffer tank (0.33.0)

- **Pellet boiler** (new heat source): on/off control with long runs – 45 minutes at least, 20 minutes pause – as
  it ignites and burns out slowly; the health check judges it by the power draw and allows its burn-out.
- **Buffer tank** (new role, like the central boiler): reads the tank's top (and optionally bottom) thermometer and
  switches the heat source: a charge starts when the top is at or below `buffer_on` (45 °C) and always runs until the
  bottom reaches `buffer_off` (65 °C); a new charge waits 20 minutes. With zones given it starts only while a zone
  asks for heat; frost (top ≤ 8 °C) charges anyway; no top reading – no charge. The circuits heat from the tank as
  ordinary HC zones. Decision sensor and a "heat source request" binary sensor.

## HC info panel (0.34.0)

A sidebar panel, **HC info** (admins only, read only), shows everything one instance knows: its heating system
drawn by its type (boiler, heat pump, district heating substation, pellet, electric, storage heater, air
conditioner; radiators, TRV heads, floor, fan coil; central boiler with its zones, buffer tank), with the data of
each part next to it, and beside the drawing the decision, presets and targets, input and output devices with their
live state, the inputs it decided on (with their age), every inner value, boiler health, rooms and TRVs, every
setting and the log. Which data shows at which part is set in one **data matrix** (`hc-info-panel.js`, `INFO`: part,
label, value, and the tags of the installations it applies to); the panel lists the matrix too. Open it from the
sidebar, or as `/hc-info?entity=climate.x` – the [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card) (1.14+)
opens it with its "i" icon.

**The house view (0.44.0).** A single-zone or zone instance is drawn as its house, a cutaway in the style of a
picture book: the heat source in the plant room (boiler with its flame, heat pump, district heating, pellet, electric,
air conditioner, storage heater) with flow / return pipes into every room, the rooms with their thermometer display
(reading → target, ≈ when the room follows the house target), radiators, floor heating or units, TRV heads (head
reading → head target), open windows, room presence, the leading room (★), the outdoor temperature and its 24 h
average, household presence, day / night by the sun, and today's gas (m³) or heat energy (kWh) of the
`heat_energy_entity` meter since local midnight (recorder statistics, else the state history; read every 5 minutes).
The rooms come from the host's room list (0.43.0) **in its order**: the bottom row first, next to the plant room, left
to right, then upwards; when Home Assistant floors are set on the areas, the floors give the storeys. Change the order
in the options (Rooms → the room's section → place in the house drawing) or with the ↑ ↓ buttons of the wizard's Rooms card. Other
rooms with a listed sensor (a window-drop thermometer, a separate zone) follow. A click on any part scrolls to its data
card (outdoor, HC controller, leading room, heat source / gas); a room or a TRV head opens the room's own card.
Light / dark follows the Home Assistant theme, it fits a phone, and it stays still with "reduce motion". Central and
buffer instances keep the line drawing.

## Floor tempering (0.35.0)

- Optional comfort for floor heating (water or electric, TPI / PID / on-off, with a floor sensor): while the room is
  warm enough the floor is held at the room target + 2 °C (`floor_temper_offset`), so it stays warm underfoot.
- An optional night value (`floor_temper_night`) is the floor target at night and in the sleep preset.
- On below the floor target − 0.3 °C, off at it; the minimum run and pause hold. It stops when the room is 0.5 °C
  above its target (`floor_temper_room_margin`; a larger value gives a warmer floor but a larger room swing and more
  energy), and never runs with an open window, switched off or in summer. The
  floor limit always wins, and the learning does not learn from these runs.

## Lost room thermometer: the floor stays warm (0.36.0)

- Floor heating with a floor sensor (TPI / PID / on-off): when the room thermometer is lost, the floor is held at
  the room target + the tempering offset (or the night value) by the floor sensor – instead of the blind 35 % of a
  boiler, or no heat at all on an electric floor. On by default (`floor_fallback`).
- Frost protection comes first, the floor limit always wins, an open window pauses it; without a floor reading
  everything works as before.

## Floor limit by covering and sensor position (0.37.0)

- Give the floor covering (tiles, laminate, wood / parquet, vinyl, carpet) and where the floor sensor sits (under
  the covering, in the screed between the pipes, above a supply pipe), and leave the floor limit at 0: the limit
  comes from a table – under the covering 29 °C for tiles and 27 °C for the others, in the screed 29 / 33 / 31 (vinyl)
  °C, above a pipe 36 °C (a deeper sensor reads warmer). An electric floor always uses the under-covering value; without a covering 27 °C for an
  electric floor, 29 °C for a water floor. These are starting points, and the deeper positions (screed, above a pipe)
  are estimates: they do not guarantee a surface below 27 °C. Under wood, parquet and laminate we recommend a sensor
  right under the covering. A limit typed in always wins.
- The covering also sets the tempering offset: 2 °C for tiles, 3 °C for the others.
- New forms start with 0 (by covering); a limit already saved stays as it is. The HC info panel shows the limit in
  effect and where it comes from.

## Wired wall thermostat as the demand (0.38.0)

- A relay instance (TPI / PID / on-off) can take its demand from a dry-contact wall thermostat, read through a binary
  sensor, an input boolean or a switch (`demand_entity`): contact on – heat, off – no heat. The room thermometer is
  then optional.
- Frost (by the room thermometer, or without one by the floor sensor), restart wait, switched off, open window and
  summer rest still come first; the floor limit and floor tempering apply on top (an idle wall thermostat counts as
  "at target"). No boost, no after-heat, the regulator waits. An unavailable contact: with a room thermometer the
  instance regulates by it and its own target until the contact is back (0.39.2); without one the lost-sensor
  fallback (the floor fallback with a floor sensor).
- Without a room thermometer the floor tempering only works with the absolute night value, in its hours (0.39.2):
  "room target + offset" would heat against the wall thermostat, which has its own setpoint.

## Weekly pump exercise (0.39.0)

- A central boiler with a circulation pump entity runs the pump alone once a week (Monday 10:00, 60 s by default)
  when it has stood still for 7 days, so it does not seize over the summer. Only while the boiler is off and no zone
  asks; the boiler never starts for it, and not in the first minutes after a restart. When the pump last ran is kept
  over restarts. `central_pump_exercise_s` (0 = off), `_weekday`, `_time`, `_idle_days`; the central decision shows
  `pump_exercise` and its end, the next run and the last run. (The buffer tank role drives no pump.)

## Managing existing thermostat integrations (0.42.0)

- With external control HC drives an existing climate entity – a Smart Thermostat, a Better Thermostat, a generic
  thermostat, an air conditioner – and that integration stays free to run on its own. HC finds the integration
  (`managed_platform`, `managed_adapter`) and fits its target to the entity's own step and range.
- A target set on the managed thermostat itself is taken over as a manual target until the next scheduled change;
  if someone switches it off, HC leaves it off (only frost protection heats) until someone switches it on again.
  Option `adopt_manual` (on). HC's own writes are never taken back. Not for the AC control.
- The switch "HC supervision paused" (external and AC control) stops every write to the managed thermostat; HC still
  decides and logs. Switched off, HC keeps the thermostat's current target as a manual target – no jump back.
  Relay controls (TPI, PID, on-off) have no such switch.
- Without a flame sensor the managed thermostat's `hvac_action` tells whether it really heats.
- The integration's presets are not used yet (HC sends a target); that comes in a later stage.

## Rooms of one boiler (0.43.0)

"One room, one thermometer (or a group), none or several TRV heads – but one boiler." A single zone instance (TPI / PID)
is the house: its boiler is driven by the **leading room** (a room without a regulating TRV head, usually the living
room; its thermometer is the house thermometer, `indoor_entity`). The house target is the schedule, the presets and
the household presence as before. Every other room gets **its own HC thermostat** (`climate.<room>_hc`, device
"<Room> HC" in the room's area, under the host's device):

- **Thermometers:** one or a group – the mean of the available ones, a dropped one is left out. A leading room with a
  group gives the mean to the boiler too.
- **TRV room:** regulates by its heads. All heads get the room's target, each calibrated against the room's
  thermometers (the 0.30.0 calibration); a head may instead follow another thermometer or its own one (no
  calibration); a room without a thermometer leaves its heads on their own sensors. Optional short burns (the
  existing room demand), **per room, off by default**, and only while the house is not above its own target.
- **Room without a TRV:** can only be reached through the boiler: its thermostat shows the house target, a target set
  on it is refused with a clear message, it gets the radiator valve advice, and it never drives the boiler.
- **Room target:** *follow* = house target + offset (night, away, presets and a manual house target follow), or *own*
  = its own home / night / away temperatures and night window (household vacation: the house's vacation target).
- **Presence per room (optional):** sources whose state is the room's area (phone room trackers such as Bermuda – the
  area name or `area_id`; an input_select) and motion / occupancy binary sensors (on = present); choosing the sources
  chooses whose presence counts. Present → the room's target; nobody for `absent_min` minutes (15) → target −
  `setback` (2 °C), never below the frost limit; while the household is away or on vacation the household target
  counts and no setback is added. Restart-safe: unknown sources hold the last state, the absence clock survives a
  restart, and for 5 minutes after a start "nobody here" does not start it.
- **Manual target / preset** (Automatic, Present, Away) on a room's thermostat holds until the room's automatic
  target changes (schedule, presence, the house target it follows), like the house. A room thermostat can be
  switched off (its heads get the frost limit).

**Where it is set (0.46.0):** the options' **Rooms** menu item – (1) tick the home's areas that are rooms (each shows
what it has), (2) one fold-out section per room with the area's thermometers, TRV heads, presence sources and window /
door contacts as check boxes (a new room comes ticked), the leading room on top, target / presence / boiler demand /
per head calibration only for a TRV room, (3) the own schedules; it saves only the rooms. The setup wizard's "Rooms" card
works the same way (one room or several, the areas as a check list – nothing ticked by itself). A room without a TRV is a
**watched room**.

- **Window / door per room (0.46.0):** in a TRV room its contacts close only the room's own heads (frost target after
  the window delay); in the leading room and in a watched room they stop the boiler like the instance's window list.
- **Room groups (0.46.0):** two or more thermometers / presence sources / contacts in a room give HC's own group entity
  (mean temperature, anyone present, any open), on the room's device; they follow the room. Saved as one `rooms` list and `leading_room` in the
instance's options; the old keys (`room_sensors`, `room_trvs`, `trv_sensors`, `trv_offsets`, `room_trv_demand`) are
written next to them, so the cards and a rollback keep working.

**Upgrade:** without `rooms` the list is derived from the old options, grouped by area, with exactly the old behaviour:
every room follows the house target with its offset, no presence, the heads keep their thermometers and what they
learned, the room demand stays as it was. Example: a house with the main thermometer in the living room, a kitchen
thermometer with a kitchen TRV head and a bedroom thermometer gets Living room (leading), Kitchen (TRV, calibrated)
and Bedroom (through the boiler) – two new thermostats, `climate.kitchen_hc` and `climate.bedroom_hc`.

HC info lists the rooms under their host; a room's thermostat (or a head) opens the host with a room section (temperature,
target and why, presence, heads, calibration, advice). The round [HC Dial Card](https://github.com/Gyuszko55/hc-dial-card)
is a separate HACS frontend repository: its released 1.14.0 opens HC info with the "i" button; the room features
(a room's thermostat opening HC info with its room, the radiator icon of a TRV room, a read-only room without a TRV)
come with its next release. A newer copy of the card is kept in this repository's `frontend/` folder for testing.

## Safety

This software does not replace the safety devices of your boiler. Keep an independent backup, for example a conventional room thermostat set low, wired in parallel. Use at your own risk (MIT, no warranty).

Going live is a separate, confirmed step (Configure → Go live). Nothing else may control the same output while active mode is on.
0.45.0: if the decision itself fails three times in a row (an internal error), HC switches its output off and the
fault sensor turns on, until a decision works again.

## Installation

**HACS (custom repository):** HACS → ⋮ → Custom repositories → `https://github.com/Gyuszko55/hc-thermostat`,
type *Integration* → download **HC Thermostat** → restart Home Assistant → Settings → Devices & services → Add
integration → **HC Thermostat** (the first step offers the **HC setup** wizard, 0.47.0).

**Manual:** copy `custom_components/hc_thermostat` to your configuration's `custom_components` folder and restart.

The round thermostat card is a separate project: [hc-dial-card](https://github.com/Gyuszko55/hc-dial-card).

## Tests

```sh
python -m pytest
```

The simulator in `tests/sim.py` runs the decision core without Home Assistant.

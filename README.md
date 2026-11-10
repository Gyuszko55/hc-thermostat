# <img src="images/icon.png" alt="HC Thermostat icon" width="44" align="absmiddle"> HC Thermostat (Heat Conductor Thermostat)

[Magyar leírás](README.hu.md)

> **Beta.** It runs a real home's heating, but every installation differs: a new instance always starts in
> **shadow mode** (it calculates and compares, switches nothing). Go live only after you have checked its decisions,
> and keep an independent backup thermostat (see Safety). The heating curve, cooling and the newer sources
> (storage heater, district heating, fan coil, pellet / buffer) are tested in a simulator and a test instance only.

HC Thermostat is a heating **supervisor** for Home Assistant, with a built-in regulator for simple systems. It does not try to replace good thermostat integrations. It sits above them and decides what the house should do, and says why.

## Basics

- **Shadow mode (default):** calculates everything, switches nothing, and compares itself with your real heating.
- **Own regulator:** TPI or PID with PWM for on/off relays, with minimum run and pause times that no algorithm may override.
- **External thermostat:** sets the target and mode of any `climate` entity.
- **Supervision:** presence and night schedule, open window pause, summer rest, frost protection, lost sensor fallback, restart protection, fault detection, optional boost.
- **Decision log** in English and Hungarian.
- **Control matrix:** heat source and hydraulics give a recommended control. These are engineering defaults, not an installation design.

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

## Safety

This software does not replace the safety devices of your boiler. Keep an independent backup, for example a conventional room thermostat set low, wired in parallel. Use at your own risk (MIT, no warranty).

Going live is a separate, confirmed step in the options. Nothing else may control the same output while active mode is on.

## Installation

**HACS (custom repository):** HACS → ⋮ → Custom repositories → `https://github.com/Gyuszko55/hc-thermostat`,
type *Integration* → download **HC Thermostat** → restart Home Assistant → Settings → Devices & services → Add
integration → **HC Thermostat** (or use the **HC setup** sidebar panel after the first instance).

**Manual:** copy `custom_components/hc_thermostat` to your configuration's `custom_components` folder and restart.

The round thermostat card is a separate project: [hc-dial-card](https://github.com/Gyuszko55/hc-dial-card).

## Tests

```sh
python -m pytest
```

The simulator in `tests/sim.py` runs the decision core without Home Assistant.

# Changelog

## 0.39.4 – 2026-11-11
- Hungarian texts: the on/off control is called "on-off" everywhere (options, wizard, HC info panel, control matrix, README) instead of "kétállású".
- README: a feature overview at the top, and a section on presence per room (a room can follow one person; guesthouse and family house examples).

## 0.39.3 – 2026-11-11
Fixes from the second outside review (0.33.0) and of 0.35.0–0.39.1:
- On/off control (heat pump, pellet boiler) with a lost room sensor: the fallback demand (35 %) meant "on" without end, as there is no PWM here. Now it is a share of the time: one minimum run, then a pause that keeps the share (never under the minimum pause); details `fallback_run_s`, `fallback_pause_s`.
- Central modulating boiler: a floor zone without its own mixing loop publishes `flow_limit` (its `flow_max`, 45 °C by default); while its circuit can get water (asking, open or still closing) the flow setpoint never goes above it, even below `central_flow_min` (`flow_capped_by` on the central decision). New zone option `zone_own_mixer` for floor zones that are protected by their own mixer.
- Storage heater with a power signal: the hours really charged are counted (`charged_h`, saved over restarts) and every block of power inside the window is used until the hours are full (`charge_why: done`); a block lost inside a charge timed to the end of the window was never made up. Without a signal nothing changes.
- Buffer tank: a tank reading older than `buffer_sensor_max_age_s` (1 hour) does not count (a dead sensor keeps its last value); a charge longer than `buffer_max_charge_s` (6 hours, 0 = no limit; in the options) stops as `max_charge` and waits the pause before it may try again.
- Wall thermostat contact lost (unknown / unavailable) while the room thermometer works: the instance regulates by the room thermometer and its own target until the contact is back (details `contact_lost`, text, HC info row) – before, the room reading was dropped and the blind 35 % demand ran even in a warm room. Without a room reading nothing changes.
- Floor tempering with a wall thermostat and no room thermometer: only the absolute night value (`floor_temper_night`) tempers, in its hours. "Room target + offset" had no room margin check there and heated against the wall thermostat's own setpoint.
- The on/off share above stays behind the floor fallback (0.36.0): with a fresh floor reading the floor is followed, as before.
- Fan coil: a fan with speed steps (`percentage_step`, for example three speeds) is set to the nearest step and not commanded again at every update because 45 % never equals the reported 33 %.
- A buffer tank without a bottom thermometer (it is optional) no longer fails at every update: a missing sensor is no reading, not an error (found when bringing these fixes in).

## 0.39.2 – 2026-11-11
- Floor tempering: the room margin (`floor_temper_room_margin`) defaults to 0.5 °C instead of 1.0 °C – the room swings less above its target and uses less energy. The description says so. Instances that already stored a value keep it.
- Floor limit table: the deeper sensor positions (screed, above a pipe) are marked as estimates in the forms, the wizard and the HC info panel; they do not guarantee a surface below 27 °C. Under wood, parquet and laminate a sensor right under the covering is recommended.

## 0.39.1 – 2026-11-11
- Pump exercise never runs against closed valves: it needs an open circuit – a bypass, a valve that is open, or a zone in its own weekly valve exercise (the zones now tell the central boiler, attribute `valve_exercising`; counted open after `central_valve_open_s`). From the set time it waits for such a circuit until the end of that day, then runs once; if the circuit closes during the run it stops and does not count.
- Floor limit: 0 with no covering now means 29 °C for a water floor (27 °C electric), never "no limit". An old instance that never stored a limit had 29 °C; saving its options stores 0, and that must not drop the limit.

## 0.39.0 – 2026-11-11
Weekly pump exercise:
- Central boiler with a pump entity: new options `central_pump_exercise_s` (60 s; 0 = off), `central_pump_exercise_weekday` (Monday), `central_pump_exercise_time` (10:00), `central_pump_exercise_idle_days` (7). The pump runs alone for the given time on that day from that time when it has not run for the idle days (the boiler, the overrun or anyone switching the pump counts as a run) – only while the boiler is off and no zone asks, never in the first 5 minutes after a restart; the boiler does not start. `core/exercise.py` `PumpExercise`.
- When the pump last ran is saved (the central instance now has its own store), so a restart does not repeat or skip it. A zone that starts asking ends the exercise at once.
- Central decision details `pump_exercise`, `pump_exercise_until`; attributes also `pump_exercise_next`, `pump_last_run`; the pump binary sensor is on meanwhile; HC info central card rows. Config flow, options and translations. The buffer tank role drives no pump, so it has nothing to exercise; the wizard sets up standalone instances only, so the options are in the central forms.

## 0.38.0 – 2026-11-11
Wired wall thermostat as the demand:
- New entity option `demand_entity` (binary sensor, input boolean or switch) for TPI / PID / on-off: contact on – new reason `thermostat_call`, demand 100 %; off – `thermostat_idle`, 0 % (counts as at target for floor tempering and the valve exercise). Texts.
- Before it, as before: frost (by the room thermometer; without one by a fresh floor reading at or below the frost limit), restart wait, switched off, open window, summer rest. No boost, no after-heat, the regulator is held; the floor limit and floor tempering apply on top (tempering without a room thermometer has no room margin check). Unknown / unavailable contact: the lost-sensor path (floor fallback or blind demand).
- With a contact the room thermometer is optional: config flow (error if neither is given), options (the contact is required when the instance has no room thermometer), wizard (the room thermometer stops being required once a contact is picked) and `wizard/apply`. The coordinator, sensors, attributes and the info panel work without an indoor entity; a lost contact is reported as a sensor problem; the boiler health overheating check is skipped in this mode.
- HC info: the contact's state; translations.

## 0.37.0 – 2026-11-11
Floor limit by covering and probe position:
- New options `floor_covering` ("" / tiles / laminate / wood / vinyl / carpet) and `floor_probe` (surface / screed / above_pipe) next to the floor limit. The limit in effect (`HcConfig.floor_limit`, `core/floor.py`): `floor_max` when above 0, else the table value of the covering, else 27 °C for an electric floor, else none. Table – surface: tiles 29, others 27; screed: tiles 29, laminate / wood / carpet 33, vinyl 31; above a pipe: 36 °C. An electric floor always uses the surface column. Starting points from EN 1264 and the makers' advice; `floor_max` overrides them.
- The supervisor, the decision details (`floor_max` is the limit in effect), the climate attribute `floor_limit` and the HC info panel (limit, where it comes from, covering / probe, tempering offset) use the effective limit.
- Floor tempering "0 = by covering" now works: tiles 2 °C, other coverings 3 °C, none 2 °C.
- Forms: the floor limit accepts 0 for every floor type ("0 = by covering and probe position"); new forms default to 0; saved values stay as they are (no migration). Config flow, options, wizard (choices with labels) and translations.

## 0.36.0 – 2026-11-11
Lost room thermometer – the floor stays warm:
- New option `floor_fallback` (on by default) for floor heating with a floor sensor and TPI / PID / on-off control. When the room thermometer is lost (after the restart wait) and a fresh floor reading exists, the floor is held at the tempering target (room target + offset, or the night value) with the same latch, instead of the blind `sensor_lost_demand` – and an electric floor no longer stays cold. The reason stays `sensor_lost`; details `floor_fallback`, `floor`, `floor_target`; texts.
- Frost first, the floor limit wins, an open window or a warm day gives no heat. Without a floor reading, or with the option off, everything is as before.
- Config flow, options, wizard, HC info row; translations.

## 0.35.0 – 2026-11-11
Floor tempering:
- New options for floor heating (water or electric) with a floor sensor and TPI / PID / on-off control: `floor_temper` (off by default), `floor_temper_offset` (°C above the room target; 0 = 2 °C), `floor_temper_night` (absolute floor target at night / in the sleep preset; 0 = as by day), `floor_temper_hysteresis` (0.3 °C), `floor_temper_room_margin` (1 °C).
- While the room is at target (or in the after-heat, or regulating with a smaller demand) and below target + margin, the floor is held at its target: on at floor target − hysteresis, off at the target, by a fresh floor reading only (the same age limits as the floor limit). New reason `floor_temper`, demand 100 %, details `floor`, `floor_target`; texts.
- Window, switched off, summer rest, frost and boost keep their priority; the floor limit always wins. The minimum run and pause hold. The learning skips these minutes. An on/off run started for the floor does not run on as a regulating run.
- Config flow, options, wizard (worked-out settings: switch, offset, night value – the wizard now shows switches and choices too), climate attributes `floor_tempering` / `floor_target`, HC info rows; translations.

## 0.34.3 – 2026-11-11
- Setup wizard and options: the entity pickers only list what fits the field – temperature sensors for thermometers, humidity / power / energy sensors, window and door contacts, presence (person, presence / occupancy sensor). The heat source relay and the other device fields stay as before.
- Setup wizard: under **Next** it says in red what is still missing (for example "Missing: Room thermometer, Boiler relay"); the required fields come from the same form that is drawn, so a field and the check can no longer drift apart. If the device of the chosen control is not in the form at all, an "Internal error" message names the field and the way round it.
- Tested end to end on a test Home Assistant: every options combination (410) and every wizard combination (165).

## 0.34.2 – 2026-11-11
- Setup wizard: a **storage heater** could not get past the devices step – the charge relay was required but its field was not shown (storage control was missing from the relay branch). Fixed; the step also offers the discharge fan, the controlled power signal (electric sources), the fan coil's fan and coil thermometer, and the district heating return thermometer, and the wizard saves them.

## 0.34.1 – 2026-11-10
HC info panel on a phone:
- Below 1000 px the drawing stands alone at full width and the data cards are listed under it in two columns – no card covers the drawing or another card. Larger labels in the drawing.
- Every card has a number, the same number sits on its part of the drawing (also on a wide screen), so data and part can be matched.
- On a wide screen too: the drawing alone on top (at most about half the screen height), the cards in a grid under it (four per row on a full-HD screen) – no card over the drawing any more; the instance picker stays in one row and scrolls.

## 0.34.0 – 2026-11-10
HC info panel:
- New sidebar panel **HC info** (`www/hc-info-panel.js`, admins, read only, refreshes every 5 s, own font – Home Assistant's Roboto under its own name). The instance's system is drawn by its source / system / control (no house outline): heat source, the HC controller with its signal line, flow / return pipes with moving water, radiators, TRV heads, floor (water or electric cable), fan coil, room units (electric heater, storage heater, AC indoor + outdoor unit), central boiler with its zones and valves, buffer tank with its fill.
- Data matrix `INFO` (part, label hu/en, value, format, tags such as relay, pid, curve, heat_pump, floor, trv, cooling, load…): decides which data shows at which part; listed in the panel ("Adat-mátrix") with the value and whether it applies.
- Side sections: decision with text and demand bar, presets and targets, input and output devices with live state, inputs decided on (with age), inner values (supervisor state, learning, load), boiler health, rooms / TRVs, zone, cost, settings grouped, log.
- Websocket `hc_thermostat/info_list`, `hc_thermostat/info` (by `entry_id` or by `entity_id`); `info.py` (`jsonable`). Opens as `/hc-info?entity=climate.x` (HC Dial Card 1.14 "i" icon).

## 0.33.0 – 2026-11-10
Pellet boiler and buffer tank:
- New heat source `pellet_boiler`: matrix (recommended; on a floor a buffer and a mixing loop are advised), controls `onoff` / `external`, default timing 3600 / 2700 / 1200 s; boiler health kind `pellet` (power-based, the long limit for a burn without command – its burn-out).
- New role `buffer` (`core/buffer.py`, `buffer_coordinator.py`): `buffer_top_entity` (required), `buffer_bottom_entity`, the heat source relay (`boiler_entity`), optional zones (HC climates), `buffer_demand_led`, `buffer_on` 45 °C, `buffer_off` 65 °C, `buffer_min_off_s` 1200 s, `buffer_frost` 8 °C. A charge runs until full (stops at once when full), no top reading means no charge, the state survives restarts. Sensor "Puffer döntés" (charging / full / ready / waiting_demand / min_off / frost / no_sensor) and binary sensor "Hőforrás kérés"; starts in shadow mode, live with confirmation.
- Config flow, options (validation: stop above start), wizard panel (pellet source, icon) and translations.

## 0.32.0 – 2026-11-10
District heating and fan coil:
- New heat source `district_heating`: matrix cells (radiators, TRVs, zones, floors recommended; mixed systems possible; room unit not), controls TPI / PID / external, default timing 1800 / 600 / 300 s (floors keep their long cycle). Optional `return_temp_entity` + `return_max` (0 = off) / `return_hysteresis` (3 °C): `limited_by: return_limit`, the valve closes at once and stays closed; text.
- New system `fan_coil` for any water source: `matrix.controls(source, system)` offers TPI / PID / external there; `source_defaults` sets `fan_coil` (and not the heat pump long runs – the valve is switched); default timing 900 / 180 / 180 s. `core/fancoil.py`: fan % = `fan_min_pct` (30) + rest × demand, rounded to 5 %, overrun `fan_overrun_s` (120 s) at the lowest speed, `fan_min_coil` (30 °C) with an optional `coil_temp_entity`. Executor drives a `fan` entity (`set_percentage` / `turn_off`). Decision details `fan_pct`, `fan_why`; texts.
- Config flow, options, wizard (controls per system, texts, icon, drawing) and translations.

## 0.31.0 – 2026-11-10
Storage heater and controlled power:
- New heat source `storage_heater` (room unit; matrix: recommended only as a room unit) with control `storage` (`core/storage.py`): charge window `storage_window_start` / `storage_window_end` (22:00–06:00), `storage_charge_h` (7 h full charge), `storage_bias` (−0.5…+0.5), charge fraction from the outdoor daily average and `curve_design_outdoor`, the charge ends at the window end, the fraction is locked for a running charge (saved over restarts). Frost: full charge whenever there is power.
- Discharge: optional `discharge_entity` (switch / input_boolean / fan), `storage_discharge_hyst` 0.3 °C.
- Controlled power: optional `power_available_entity` for electric heater, electric boiler and storage heater. Off: TPI/PID keeps the relay off (`limited_by: no_power`) without integral wind-up; the storage heater does not charge. Unknown state counts as available.
- New reasons `storage_charge`, `storage_wait`; decision details `charge_fraction`, `charge_start`, `charge_end`, `charge_why`, `discharge`, `power_available`; texts. Config flow, options, wizard panel (source, control, icon) and translations.

## 0.30.0 – 2026-11-10
TRV rooms – own target and calibration:
- New options step "TRV rooms" (when the instance has TRV heads): an offset per room to the house target (`trv_offsets`, −5…+5 °C) and `trv_calibration` (off by default). Without offsets and calibration everything works as before.
- Calibration (`TrvCalibration`): head temperature − room thermometer (only the room's own sensors, not the heads), first pair taken as is, then smoothed with a 30 minute time constant, bounded to ±5 °C, kept when a reading is missing, saved over restarts. The head gets round((room target + calibration) / step) × step.
- `TrvTargets.plan`: the room target (house + offset) is the reference of the hand-change detection; a calibration-only change is written at most every 30 minutes ("wait"); a new room target is written at once.
- TRV room demand compares against the room's own target. Rooms sensor attribute `trv_rooms`. Translations.

## 0.29.0 – 2026-11-10
Floor cooling with dew point protection:
- New options for a heat pump on a floor (curve or on/off): `floor_cooling`, `humidity_entity` (required), `cool_mode_entity`, `cool_flow_entity` (curve), `target_cool`, `dew_margin` (2 °C), `floor_min_cool` (19 °C), `cool_flow` (18 °C), `cool_flow_max` (22 °C); `humidity_max_age_s` 3600 s.
- In summer (season off) the instance cools: room hysteresis ±0.5 °C around `target_cool`, the heat pump minimum run/pause hold. Dew point by the Magnus formula (`core/cooling.py`); safe flow = dew point + margin; curve flow = `cool_flow` raised to the safe flow (next half degree); above `cool_flow_max` it stops ("humid"). Floor sensor: pause at max(safe flow, `floor_min_cool`), resume 0.5 °C above; on/off control needs it. No fresh humidity: no cooling. Stops for condensation ignore the minimum run time.
- New reasons `floor_cool`, `dew_point`; decision details `mode: cool`, `dew_point`, `humidity`, `safe_flow`, `flow`, `why`; climate shows cooling. Executor: cooling switch on all summer, separate cooling flow setpoint, a stopped cooling writes the entity's maximum (not the minimum).
- Options validation: floor cooling without a humidity sensor is refused. Translations.

## 0.28.0 – 2026-11-10
Load limit of electric zones:
- New option `load_limit_kw` (electric heater / boiler, TPI or PID; 0 = off) with the zone's own power in `boiler_power_kw`. One load manager per Home Assistant (`core/load.py`) grants room under the limit before a relay switches on.
- Refused: the relay stays off (`limited_by: load_limit`, details `load_used_kw`, `load_limit_kw`, `load_kw`, `load_waiting`), and the PWM cycle restarts when the room is granted – full on-time kept, zones staggered.
- First come, first served; a zone heating without a pause hands over at its next cycle when a waiting zone fits. Off is never delayed; floor limit stops as before; frost protection obeys the limit. Stale entries are forgotten (on 10 min, waiting 3 min); unloading an instance frees its room at once.
- Only live instances take part. Options field and translations; decision text "Terheléskorlát: …".

## 0.27.0 – 2026-11-10
Modulating boiler with zones:
- A zone instance publishes `flow_request`: the flow its own curve asks for while it wants heat (target + slope × (target − outdoor) + shift + room_kp × shortfall, clamped to its flow limits; no integral – the zone regulates its valve itself). Zones get the starting curve of their system (floor 0.5 / 22–45 °C, radiators 1.4 / 25–75 °C) unless set.
- The central instance takes the highest request of the open asking zones (all asking zones while valves are still opening), `central_flow_default` (55 °C) when none sends one, clamped to `central_flow_min` / `central_flow_max` (25 / 75 °C), and writes it to an optional flow setpoint entity (number / input_number) while the boiler runs; off: the entity's lowest value. Changes under 0.5 °C are not written.
- Central decision sensor: `flow_setpoint`, `flow_by`, `flow_requests`. Config flow, options and translations.

## 0.26.0 – 2026-11-10
Heat pump:
- New control `onoff` (heat pumps): switches the thermostat input with long runs, no PWM – on below target − `onoff_hysteresis` (0.3 °C), off when the house reached the target (+ `overshoot_stop`); the minimum run and pause times hold; the floor limit stops it at once.
- Minimum run / pause of a heat pump adjustable (`hp_min_on_s` 1200 s, `hp_min_off_s` 600 s), in curve and on/off control (was fixed).
- Defrost and hot water: optional signals `hp_defrost_entity`, `hp_dhw_entity` (binary sensor, switch, or a mode sensor naming it). While on, fault detection waits, the boiler health does not count it as running without command or as a start, and the decision says so.
- Boiler health: a heat pump is its own kind – running without command is reported after 45 minutes in an hour (it makes hot water by itself), not after 5 like an electric heater.
- Config flow, options, wizard and translations; climate attributes `onoff_hysteresis`, `hp_min_on_s`, `hp_min_off_s`; the floor limit fields also for on/off and curve control.

## 0.25.1 – 2026-11-10
Fixes from an outside review:
- AC: a heat setpoint outside the unit's range (frost protection asked for 8 °C, most units start at 16 °C) is clamped to the unit's limits instead of being refused.
- Floor sensor freshness: 2 hours with the relay off (many sensors report only on a change, a cold still floor stays silent), 30 minutes while heating (`floor_max_age_s`, `floor_max_age_on_s`); was 15 minutes, which could keep an electric floor from starting.
- Modulating boiler: relay mode (TPI / PID on the room-thermostat contacts) is offered next to the heating curve, as the matrix text promised (`matrix.controls`).
- Curve mode: the floor limit stops at once (`RunGate.force_off`), no longer after the minimum run time (20 minutes for a heat pump).
- Water floor: default floor limit 29 °C (acts only with a floor sensor).

## 0.25.0 – 2026-11-10
- Matrix: electric floor heating (electric heater × floor single/zones) is recommended; 30 minute cycle, 5 minute minimum.
- Floor temperature limit: `floor_entity`, `floor_max`, `floor_hysteresis`; reason `floor_limit`, the relay goes off at once (no minimum run time). An electric floor requires the floor sensor (config flow, wizard) and does not heat without a fresh floor reading; for a water floor the limit is optional; an external thermostat is switched off at the limit.
- Lost indoor sensor: an electric heater falls back to 0 % (was 35 %); a floor sensor still gives frost protection. Safety defaults by heat source (`matrix.source_defaults`), an explicit setting wins.
- Target source (`target_source_entity`, climate / number / input_number): a changed setpoint becomes the manual target until the next scheduled change; what any HC instance wrote there (external thermostat, TRV heads) is ignored for 2 minutes.

## 0.22.3 – 2026-11-09
- AC: with a whole-degree unit the setpoint is rounded towards what the room needs once it is 0.2 °C past the target, and such a step passes the hysteresis (live: terrace 19.5 °C at target 19 with the unit set to 20); integral limit ±2 °C; the decision sensor shows the AC setpoint, offset and integral.

## 0.22.2 – 2026-11-09
- Decision texts say "the room" instead of "the house" for room units (electric heater, AC) and zones.

## 0.22.1 – 2026-11-09
- Wizard: worked-out settings follow the heat source (no boiler output for a room heater, no relay resend, heater/boiler wording, no flame field for electric sources); a changed choice drops the values and devices of the earlier one; not recommended systems are not offered.

## 0.22.0 – 2026-11-09
- Matrix: electric boiler (water systems, contactor/relay, TPI/PID) and electric heater (room unit: relay or smart plug with a 10 minute cycle, or a Wi-Fi heater as external thermostat); heat_type "electric"; wizard cards, drawings and labels for both.

## 0.21.0 – 2026-11-09
- Setup wizard: sidebar panel "HC setup" (admin), websocket hc_thermostat/wizard/{start,derive,apply}; new instances in shadow mode.
## 0.20.2
- Climate publishes heat_type for cards.
## 0.20.1
- Fix: the shadow regulator crashed on the 0.20.0 code path.
## 0.20.0
- Boiler and heat pump coordinated by cost (assist_climate, yield_margin).

## 0.1.0 (development)

First stage: decision core, TPI/PID + PWM, external thermostat control, supervision, simulator and safety tests, bilingual setup, shadow mode.

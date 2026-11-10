# Changelog

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

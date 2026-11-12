# Changelog

## 0.45.0 – 2026-11-12
Fixes from a "boxed retail release" review: on a new Home Assistant HC can be taken into use in a few clicks.
- **°F and imperial systems:** thermometers are read in °C by their `unit_of_measurement` (a weather entity by its
  `temperature_unit`); a climate entity's attributes (TRV heads, the managed thermostat, an AC unit) are read from the
  system unit; what HC writes to a climate is sent in the system unit (on the entity's own step, e.g. 21 °C → 70 °F),
  a flow setpoint number in its own unit. HC's own climates stay °C inside (Home Assistant converts them). New
  `units.py`.
- **Relay failsafe:** a decision that raises three times in a row (`FAILSAFE_AFTER`) switches the output off
  through the executor's usual path (relay off, managed thermostat off, lowest flow); the fault sensor shows
  `hc_supervisor: internal_error`. The next good step clears it. In shadow mode nothing is switched.
- **Restart protection** counts from Home Assistant's start, not from the entry's load: an instance added, or
  reloaded by saving its options, while Home Assistant runs no longer shows "Waiting after restart". A real restart
  behaves as before.
- **Going live:** the options start with a menu – *Settings*, or *Go live* / *Back to shadow mode* (only the mode,
  with the confirmation). The wizard's summary can start a new instance live (a confirmed tick box).
- **Language:** config / options flow texts follow the user's language (both languages go into the placeholders,
  each translation uses its own: the matrix rating, its advice, the rooms list); the wizard sends the user's
  language for its reasons; the room climate's error is translated by Home Assistant; sidebar title by the system
  language ("HC setup" / "HC beállítás"); HC info and the dial card default to English.
- **Setup:** a taken name is a field error (the input stays) and the default name is free ("HC Thermostat 2");
  thermostat / AC unit / TRV head pickers do not offer HC's own climates nor climates another instance drives (and
  refuse them); the adjoining-room ("zone") fields moved to the options; the COP field has no "kWh" unit; plain
  descriptions for TPI / PWM / PID, virtual i-Feel, the power levels, Bermuda.
- **Wizard:** names and server texts escaped (XSS); no red message on the empty start screen; units on the summary;
  "BTHome" is no outdoor word any more.
- **HC info / house view:** decision keys translated, "Relé ki", "–" instead of "+null"; the house view draws when
  its data arrives before the element is defined or while its width is still 0.
- **Boiler health:** without power levels given in the options (or measured by the wizard) a burner judged by its
  power draw is `learning` (no problem) – no "no response" / "no flame" from the 20 W / 115 W defaults of another
  boiler. Untouched defaults are not saved by the options any more.
- **Texts:** house-specific Hungarian words removed ("teraszi hőmérő", "konyhaajtó").
- **Wording:** Hungarian texts consistently use „helyiség” for a HC room (was mixed „szoba”/„helyiség”); English
  „room”, „area” only for Home Assistant areas.
- **Packaging:** brand icon in `brand/` (Home Assistant 2026.10 serves it), manifest keys in hassfest order, the
  unused `frontend/hc-thermostat-card.js` removed, the decision log and the TRV room details are not recorded in the
  history (still in the state), the HC info commands are admin only (as the panel), the panels leave the sidebar
  with the last instance, "… HC HC supervision paused" → "… HC supervision paused" (entity ids unchanged).
- README: quick start, presence states, removing an instance, the Dial Card version.
- Tests: tests/test_retail_450.py (27), an upgrade from a 0.41.0 store (tests/data/upgrade_0410.json).
  tests/compare_regulators.py unchanged.

## 0.44.5 – 2026-11-12
Fixes found in the issues of Versatile Thermostat and SAT (review of 11-12).
- **TRV head: a late report is not a change by hand** (as VTherm #2141/#2175). A head that still showed its old
  target after our write counted as set by hand at the next step. Its target and calibration then stayed
  frozen until the house target changed. Now:
  - while the head shows its old target, the write is `pending` for up to 5 min (`ECHO_S`);
  - then it is written again (`rewrite`), at most twice, and left alone after that;
  - once the head took our write, any later change on it is by hand, as before.
- **Window contacts:** a contact that is unavailable is reported as a sensor problem (`lost`, after 10 min). It
  still counts as closed (as VTherm #2052). A window already open when Home Assistant starts pauses at once,
  without the 2-min delay (as VTherm #2147).
- **PWM:** a start delayed by the minimum off time keeps its full run; the cycle begins when the burner really
  starts (as VTherm #2194). At 40 %, 30-min cycle: 12 min instead of 8.
- **Window by temperature drop:** a thermometer that drops out no longer holds the pause beyond
  `window_drop_max_min`.
- **PID:** a gap over 300 s between two updates (`MAX_STEP_S`) is not integrated in one step, as in the AC
  since 0.44.1. This also covers the first regulating step after a long pause (at target, window).
- Simulation (tests/compare_regulators.py, Cirkó PID): unchanged, at −10 °C the largest overshoot fell from
  0.11 to 0.08 °C. Tests: tests/test_fixes_445.py.

## 0.44.4 – 2026-11-12
A boost survives a restart. On 11-12 a boost started at 10:49, at 21.6 °C, with target 22.5 and a time limit
of 11:14. A door pause and a Home Assistant restart at 11:05 (the 0.44.3 deploy) cut it. The restart forgot the
13 burn minutes. It started a fresh boost with a new limit (11:35) and burned 12.5 more minutes, about 25 minutes
in all instead of ~14. The heat already in the radiators took the house to 22.9 °C.
- The running boost is saved: its time limit, burn minutes, and the after-heat wait that follows it. After a
  restart it resumes where it was, if saved at most `boost_resume_max_s` (30 min) ago. The downtime does not
  count as burn time. A resumed boost teaches the learner nothing.
- A new boost counts the burns of the last `boost_prior_window_s` (45 min) in its after-heat forecast. A burn's
  weight falls linearly with its age. This also covers a lost save, or a boost right after normal burns. Such a
  boost is not learned from either. The info shows it as `prior_min`.
- Simulation (slow radiators, restart after 14 min of boost), burn minutes of the boost phase:
  - without a restart: 25.5;
  - before 0.44.4: 32.0, a lower but longer heat-up with a higher peak;
  - with 0.44.4: 19.0, because the original time limit holds.
  Replayed in tests/test_boost_444.py.

## 0.44.3 – 2026-11-12
Coasting after a burn (PID / TPI). On 11-12 morning a 12-min burn at 22.0 °C (target 22.5) was followed, 18 min
later, by a 7-min burn at the start of the next 30-min cycle. The room was at 22.4 and still rising from the
first burn, and it peaked at 22.8. The PID sees the error and its integral, not the heat still in the
radiators. Its integral also grew from 5.6 to 9.7 % while the room was rising.
- No new start while, at the same time:
  - the boiler stopped at most `coast_window_s` (45 min) ago;
  - the room is at most `coast_band` (0.2 °C) under the target, or at / over it;
  - the room rose at least `coast_rise` (0.1 °C) over `coast_lookback_s` (15 min);
  - the demand is at most `coast_max_demand` (30 %). A larger demand is a real need: no change.
- The integral does not grow while coasting. HC text: "Utánfűtés: a szoba még emelkedik …"
  (`limited_by: coast`).
- Ends when the rise stops or the window is over; then a normal start. Without enough history (just started)
  there is no coasting. `coast_window_s: 0` turns it off.
- Simulation (tests/compare_regulators.py, 15- and 30-min cycles, 15- and 40-min radiator lag): unchanged
  holding, warm-up and window results. The simulated house does not reproduce the live overshoot; the 11-12
  morning is replayed in tests/test_coast_443.py.

## 0.44.2 – 2026-11-12
Room suggestions and the PWM cycle, after the live findings of 11-12.
- PWM: a demand that only grows past the minimum run in the middle of a cycle now starts a new cycle at once,
  when this cycle has had no burn yet and the minimum off time is over. The cycle began below the minimum run,
  so it had no burn. Before, the demand waited for the next cycle. On 11-12 morning the Cirkó (30-min cycle,
  5-min minimum run) stayed off from 7:17 to 7:47 with the room 0.5 °C under its target (15 % → 38 %). With
  the fix it would have started at 7:24. A cycle that has burned is never restarted (one start per cycle at
  most, as before).
  Regulator comparison: in mild weather (+10 °C) the largest shortfall drops from 0.13 to 0.07 °C, with 72
  instead of 71 starts per day.
- Heads driven by another HC instance: no longer suggested by the wizard, dropped by `wizard/apply`, and refused
  in the options flow's room form (`trv_other_instance`). Two instances wrote one head: the HP fan-coil test
  instance and Cirkó HC both drove the real kitchen head through the night of 11-11.
- Only real valve heads are suggested: by id / name / device model, or a valve entity on the device. A plain
  thermostat of another integration (`climate.futes`, Smart Thermostat) was suggested as a head.
- Outdoor places are no rooms: outdoor areas (udvar, kert, outdoor, garden, yard, …) and every HC instance's
  outdoor thermometer and its area are left out of the room thermometer suggestion and the wizard's rooms. Udvar
  and Kert had become rooms with their own climate entities.
- A main thermometer without an area gets its own leading room in the wizard's suggestion ("main"). Before,
  there was none, and a leading room picked later replaced the main thermometer with its own.

## 0.44.1 – 2026-11-12
Integral fixes, after reviewing the Smart Thermostat 2026.11.0 PID fixes (its #305, #324, #326) against our own code.
- PID: when the total output (P + D + feed-forward + I) is saturated, the integral is frozen in the direction that
  would push it deeper, and never cut back. Before, it was clipped to max(1 − base, 0) / min(−base, 0). A target
  step of a few degrees (P alone over 100 %) wiped a learned positive integral. An overshoot (P + feed-forward
  below 0) wiped a negative one, the one that cancels a too generous feed-forward. The integral alone is bounded
  to ±100 %. It still unwinds at once when the error turns.
- Air conditioner (`control: ac`): a pause in regulation (window, switched off, frost, lost sensor) now restarts
  the step clock (`AcController.hold`). A gap over 5 minutes between two steps is no longer integrated. Before,
  the first step after an hour's pause integrated the whole hour: +1 °C on the unit's setpoint at a 2 K error.
- Weather curve (`control: curve`): no integration towards a flow limit it already sits at (`flow_max` while
  cold, `flow_min` while warm), and no further downwards while there is no demand. Before, it ran on to
  ±`room_integral_limit`.
- Already right, unchanged: the feed-forward counts in the PID anti-windup (Smart Thermostat #326). The 30 s fixed
  step keeps the kick of a target change negligible (#305, no trapezoid needed). OFF → HEAT keeps the integral.
- Regulator comparison (tests/compare_regulators.py): unchanged except a 30-minute open window. After it, the
  kept integral overshoots by at most 0.17 °C (Cirkó settings; before 0.07 °C, when the wiped integral had to be
  learned again).

## 0.44.0 – 2026-11-11
HC info: the house view.
- A standalone / zone instance is drawn as its house (`www/hc-house-view.js`, loaded by the panel with the
  integration's `?v=` version): plant room with the heat source, flow / return pipes, the rooms of the host's `rooms`
  list in their order (bottom row first next to the plant room, left to right, then upwards; HA floors give the
  storeys), thermometer displays, radiators / floor / fan coil / units, TRV heads, windows, room presence, the leading
  room, outdoor, sun, today's gas or heat energy. The old line drawing stays for central and buffer instances.
- Hotspots: a click scrolls to the matching data card (outdoor, HC controller, leading room → indoor, heat source / gas);
  a room or a TRV head selects the room and opens its 0.43.0 room card. The numbered markers are gone.
- Dark / light from the Home Assistant theme (`hass.themes.darkMode`), phone width, `prefers-reduced-motion`.
- Info data (read only, cheap): `entity_areas` (the area of every listed entity and of the rooms' thermometers, heads
  and presence sources: the entity's own area, else its device's), `areas`, `floors`, `sun`, `heat_today` (today's
  change of `heat_energy_entity` since local midnight: recorder statistics `change`, else the state history; read in
  the background at most every 5 minutes, the panel never waits), `pipes` (flow = `coil_temp_entity`, return =
  `return_temp_entity`, when set), and `area` on every `room_list` item.
- Room order: the options flow's room form has a "place in the list" field (the Rooms menu lists the rooms numbered);
  the wizard's Rooms card shows the rooms in their order with ↑ ↓ buttons (a first suggestion puts the leading room
  first). A list derived from the legacy options keeps leading room, then the room thermometers' rooms, then the heads'.

## 0.43.0 – 2026-11-11
Rooms of one boiler: "one room, one thermometer (or a group), none or several TRV heads – but one boiler".
- New room model (`core/room_model.py`): a single zone TPI / PID instance is the house, driven by its **leading room**
  (no regulating TRV; its thermometers are the house thermometer). Every other room is a `RoomSpec`: thermometers (the
  mean of the available ones; before: the median), TRV heads (per head: the room's thermometers by default, another
  thermometer, or its own – `head_sensors`), target `follow` (house target + `offset`) or `own` (home / night / away and
  its own night window; household vacation: the house's vacation target), presence sources, `absent_min` (15),
  `setback` (2 °C), boiler `demand` (per room, off by default).
- Every room but the leading one gets its own climate entity `climate.<room>_hc` (unique id `<entry_id>_room_<key>`,
  device "<Room> HC" in the room's area, linked to the host's device). TRV room: target, presets Automatic / Present /
  Away and on / off; a manual target or preset holds until the room's automatic target changes. Room without a TRV:
  shows the house target, `set_temperature` is refused with a clear message (`ServiceValidationError`), attribute
  `follows_house`. Attributes: reason, house target, presence, sources, calibration per head, advice, demand.
  A removed room's entity and device are removed too.
- Presence per room: a source whose state is the room's area name or id (Bermuda `area_id`, input_select) or an on/off
  sensor (motion / occupancy). Present → room target; nobody for `absent_min` → target − setback (never below frost);
  household away / vacation → the household target, no setback. Restart-safe (unknown sources hold the state, the
  absence clock is saved, no clock for 5 minutes after a start). Source changes trigger an immediate decision.
- Room demand is per room now (the old switch becomes the value of every TRV room on upgrade); still only while the
  house is not above its target. A leading room with a thermometer group gives its mean to the boiler.
- Storage: one `rooms` list and `leading_room` in the host's options (not config subentries: one atomic save of the
  rooms, the leading room, the house thermometer and the legacy keys; the wizard writes options anyway; a rollback to
  0.42.0 keeps working). The legacy keys are written next to it. Without `rooms` the list is derived from the legacy
  options grouped by area, behaviour unchanged (follow + old offset, no presence, the heads' thermometers and learned
  calibration kept, room advice history kept by room name).
- Options: the room thermometer / TRV pickers and the "TRV rooms" step are replaced by a **Rooms** menu after the
  presets: add, edit, remove a room, choose the leading room (a TRV room needs a confirmation), save. Errors: no name,
  name taken, no thermometer or head, an HC climate as a head, a head in two rooms.
- Setup wizard: the room thermometer list and the "TRV heads" card are replaced by a **Rooms** card (single zone TPI /
  PID): a suggested room per area with a thermometer or a head (a head's own thermometer is never the suggestion),
  thermometers, heads and their thermometer, leading room radio, target mode, presence (room trackers of the home and
  the area's motion / occupancy sensors) with delay and setback, demand; warnings when the leading room has a TRV or
  the house thermometer is in a TRV room; an existing instance is prefilled. New websocket `hc_thermostat/wizard/rooms`;
  `wizard/apply` takes `rooms` and `leading_room` (the old `trv` still works).
- HC info: `info_list` items carry `rooms`; the picker lists them under their host; `info` by a room climate (or a head)
  returns `via_room`; a room section (temperature, target and why, presence, heads, calibration, advice) and a rooms
  table. The host climate publishes `room_climates` and `leading_room`; the rooms sensor `leading_room`.
- HC Dial Card 1.16.0: a room without a TRV (`follows_house`) is read only; the "i" of a room climate opens its room.

## 0.42.0 – 2026-11-11
Managing existing thermostat integrations, stage 1. HC's external control (and the AC control) now treats the climate entity it drives as a partner that may also run on its own:
- Adapters (`core/adapters.py`) for Smart Thermostat (PID), Better Thermostat, Gree air conditioners and a generic one for any other climate entity. The integration is found from the entity registry (`managed_platform`, `managed_adapter` on the HC climate entity, and in HC info). Capabilities (hvac modes, range, step, presets) are always read from the entity's live attributes.
- External control: the target is rounded to the entity's own step and kept inside its range before it is written (a 1 °C-step unit refuses 22.5; the frost target is raised to the unit's minimum). The AC control already did this and is unchanged.
- External control, two-way (option `adopt_manual`, on): a target set on the managed thermostat itself becomes the manual target until the next scheduled change, like the target-source option; HC's own writes are recognised and not taken back. When someone switches the managed thermostat off, HC leaves it off (new decision `managed_off`) until someone switches it on again; only frost protection still heats. Not for the AC control: there HC moves the setpoint itself all the time. The separate target-source option works as before.
- "HC supervision paused": a new switch per instance with external or AC control (restored after a restart). While on, HC writes nothing to the managed thermostat; the decision is still computed and logged with `paused` and a note in the text. When switched off, HC takes over the thermostat's current target as a manual target instead of jumping back (AC: the change made on the unit during the pause moves the room target by as much). Relay controls get no such switch: a paused relay could stay on. Climate attributes `supervision_paused`, `supervision_switch` (the switch's entity id, for cards).
- Without a flame or reference sensor, actual heating for external and AC control comes from the managed thermostat's `hvac_action` through its adapter (unknown when the integration does not report it, as Gree does); a configured flame sensor still wins.
- HC info: managed thermostat (integration), supervision paused, switched off by hand, adopted manual target, actual heating.

TRV heads – a thermometer per head:
- New option `trv_sensors` (head → sensor): a head listed there is calibrated against that sensor (the 0.30.0 calibration: head − sensor, 30 minute smoothing, ±5 °C); a head not listed works by its own thermometer, calibration 0. A TRV room without a room thermometer reads its heads' chosen thermometers (else the heads' own) for the room advice and the room demand. Changing a head's thermometer (or setting it to its own) drops what was learned for it; an offset learned before 0.42.0 is kept when the same room thermometer is chosen.
- Backward compatible: without `trv_sensors` the old switch `trv_calibration` works as before (on: the room thermometers of the head's area). Saving the options or the wizard writes `trv_sensors` and leaves `trv_calibration` out.
- Options, "TRV rooms" step: the calibration switch is replaced by one choice per head – "the head's own thermometer" or one of the temperature sensors in the head's area (entity area, else device area; not the head's own device, no unavailable ones, by name; all temperature sensors when the area has none). A newly added head gets the first thermometer of its area as the suggestion.
- Setup wizard: a "TRV heads" part for single zone TPI / PID (shown on the worked-out settings step): add heads, choose per head the own or an external thermometer from the narrowed list, the room offset and the room demand switch; an existing instance is prefilled (a legacy instance shows the room thermometer it effectively follows). New websocket command `hc_thermostat/wizard/trv`; `wizard/apply` takes `trv`.
- `trv_info` (HC info, rooms sensor) shows per head `sensor` (an entity id or `head`), `sensor_temp`, `head_temp`.
- HC info: `hc_thermostat/info` with a TRV head's entity id returns its host instance (`via_trv`); `info_list` items carry `trvs`; the instance picker lists heads under their host ("Konyha TRV → Cirkó HC"), a row shows each head's thermometer. The climate entity publishes `trv_heads`.
- HC Dial Card 1.15.0: the "i" button is shown for a TRV head driven by an HC instance (found by `trv_heads`) and opens that instance's info.
- Options: a cleared room thermometer or TRV head picker is saved as an empty list; before, a list the wizard had written into the entry data came back.

## 0.41.0 – 2026-11-11
- Frozen room thermometer: a sensor that keeps reporting the same value looks fresh (its age counts from the last report) but measures nothing. When the room reading has not changed at all for `frozen_after_h` (3 h) while the heat source ran at least `frozen_burn_min` (45 min) in that time, it does not count: the lost-sensor path runs (floor fallback, heat-need demand or the blind share) until the value changes. Relay controls (TPI / PID / on-off); options with the other timing settings; details `indoor_frozen`, decision text. The measured house stayed at one value for at most 1.4 h with at most 17 burning minutes, so the defaults leave a wide margin.
- Relay watchdog script (`keep_alive_script`, options next to the keep-alive): at every keep-alive of a relay that should stay on, HC runs this script instead of switching the relay on again – for example a Shelly gen1 "turn on with a 15-minute flip-back timer" (`/relay/0?turn=on&timer=900`). Measured: a Shelly gen1 with an auto-off of 900 s cut long burns at 15 minutes although HC re-sent "on" every minute (an "on" to a relay that is already on does not restart its timer); HC switched it on again 30 s later – an extra ignition. With the script the timer restarts every minute: a long burn is never cut, and a dead Home Assistant still leaves the relay on for 15 minutes at most.
- Closed-loop regulator comparison: `tests/compare_regulators.py` runs TPI and PID on the same simulated house (0.1 °C sensor steps, boost and learning off) – holding at −10 / 0 / +10 °C outside, a 19 → 21 °C warm-up and an open window. PID holds within about 0.05 °C on average; plain TPI settles 0.4–0.6 °C below the target (no integral – in real use the learned holding offset closes it); both burn about the same. Regression tests pin these results.

## 0.40.0 – 2026-11-11
From a further outside review (sensor loss, PID, PWM, restart, relay, boiler protection):
- Lost room sensor with a boiler: the blind demand is the house's heat need now – learned heat loss × (target − outdoor), minus other sources, divided by `boiler_power_kw` – instead of the fixed 35 %; never below one minimum run per cycle. A fixed 35 % overheats the house in mild weather and may be short in a cold spell. Without a learned loss or without the power, the fixed share stays; option `sensor_lost_model` (on). Electric heat still does not run blind; the floor fallback (0.36.0) still comes first. Details `blind_from`, `heat_need_kw`, decision text.
- PID: the derivative is low-pass filtered (`pid_d_filter_s`, 300 s; 0 = off, in the options next to the derivative gain). Room sensors report in 0.1 °C steps only on a change, so the raw slope is a spike at a report and 0 between reports. Only matters with a derivative gain above 0.
- Checked, no change needed: the 2-hour sensor age (sensors report only on a change; shorter gives false losses), PWM minimum run and pause in every state (the safety stops – floor limit, return limit, no power – switch off at once by design, the minimum pause still holds), restart hold and restart burn, a single writer of the boiler relay, boiler protection (short cycling, no ignition, no response, uncommanded burn, overheating). New regression tests for the changes.

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

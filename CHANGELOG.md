# Changelog

## 0.81.1 – 2026-11-26

- **TRV heads only: the head's sensor select.** The SONOFF TRVZB on Zigbee2MQTT names the option
  `remote_temperature` (with `local_temperature` and `remote_source_offline`), not `external`: HC wrote the room
  temperature to the head but never switched the head to it, and took the offset calibration away – the head kept
  regulating by its own reading next to the hot radiator and closed early. HC now selects `remote_temperature`
  (`external` is kept for other heads), leaves `remote_source_offline` alone (the head goes back by itself on the
  next value) and keeps the offset calibration while the head is not on the input. The offset is no longer learned
  while the head is on the input (it reports the room's own value there): what it learned on its own sensor stays
  for when the input drops out.
  When the head changes thermometer (onto the input, or offline) the new target is written at once, not after the
  half-hour wait of a calibration drift.
- The heat type shown for district heating and for "TRV heads only" is a radiator (or a floor), not a gas boiler.
- Wizard, "TRV heads only": no "may ask the boiler for short burns" per room, the leading room's hint and the
  "start live" line speak of the heads, not of a boiler.

## 0.81.0 – 2026-11-26

- **"TRV heads only" – a flat on district heating.** A tester's panel flat (district heating, TRV heads on the
  radiators, a thermometer in each room, no zone valve, no boiler) could not be set up: every control the wizard
  offered for district heating asked for a relay, and with it for a flame, a boiler power and a gas meter. The new
  control has no device of its own: each room's heads get the room's target (the flat's schedule, the room's own
  offset or schedule, presence, windows), by the room's thermometer. It is offered for district heating on
  radiators, first on the "radiators with TRV heads" system; the wizard then asks for no relay, no burner fields and
  no return temperature, and needs at least one room with a head. No demand, run or switch counting.
- **A head's external sensor input.** Where a head can take the room temperature itself (SONOFF TRVZB on
  Zigbee2MQTT: `external_temperature_input` with `temperature_sensor_select` = external), HC writes the room's
  thermometer to it (on a 0.1 °C change, at least every 10 minutes, only live) and sets the head to use it – the
  head then regulates by the room, not by its own reading next to the hot radiator, and needs no offset
  calibration. Found on the head's own device; otherwise in its area by name. Heads without it keep the offset
  calibration.

## 0.80.0 – 2026-11-26

- **HC Lite: gas boiler or heat pump.** A new setting, the heat source (`src`). The web set-up starts with the
  choice, which loads the settings that suit it (a gas boiler: PI on a 45 min cycle, 5 / 5 min protection, an
  80 min longest burn, boost; a heat pump: hysteresis 0.5 °C, 20 min shortest run, 15 min shortest pause, no
  longest run, no boost, a longer preheat). Each can be changed afterwards.
- **HC Lite: cooling with a heat pump.** Heating or cooling (`{"hvac": "cool"}`, the web page's Heat / Cool
  buttons, HC's climate entity in Cool mode). Cooling has its own targets (day 25, night 26, away 28 °C), asks
  above the target, and has no preheat, boost or frost; without a reading it stays off. One relay switches the
  request only: the heat pump itself is set to cooling on its own controller.
- **HC Lite: dew point guard.** From the room's humidity (a BLU H&T's humidity, an add-on DHT22, or what a Wi-Fi
  H&T sends) the script works out the dew point. With an add-on probe on the cooled flow pipe, cooling stops at
  once while the pipe is below dew point + margin (2 °C by default), and starts again 1 °C above that; with a pipe
  probe but no humidity it does not cool. Without a pipe probe it only warns when the room nears its dew point.
- **HC Lite: buffer probes.** Up to 3 DS18B20 probes on a Shelly Plus Add-on, with names, shown on the relay's
  page and as HC sensors. They steer nothing.
- **Fix: the relay kept its settings only until a restart.** A KVS value holds less than 255 characters, and the
  settings had grown longer, so they were never saved; HC sent them again after a restart, but without HC a relay
  fell back to old settings. They are now kept in parts (`hc_lite_c1`…`c5`); `hc_lite_cfg` is still read last, so
  an upload tool's few settings win.
- **A compact script for the relay.** `guard/shelly/hc_lite.min.js` (made by `python3 guard/compact_js.py`, and
  what `upload_shelly.py --lite` sends) has no comments or indentation: about 20 kB instead of 29 kB, as the relay
  keeps the text of every function in its small memory. The tests run on both files.
- HC: new options (heat source, cooling targets, humidity id, flow pipe probe, dew point margin, buffer probes and
  names), the climate entity's Cool mode and humidity, sensors for the buffer probes, the dew point and the pipe.
  Needs the new script on the relay; the web page from this release.

## 0.79.9 – 2026-11-26

- **HC Lite: web set-up on the relay, without Home Assistant.** The relay's page (`…/script/<id>/lite?page=1`)
  loads a full set-up page: status (mode, ±, manual target, demand, boost, reading age, last switches), every
  setting in groups with its range, and first steps for a new relay – create the token, check the clock and time
  zone and that the script starts on power-up, pick the thermometer (BLU H&T and wired probes are listed; for a
  Wi-Fi H&T the webhook URL with the token is ready to copy), and shadow / live (going live takes a second click).
  A script holds only a few kB, so the page's program is fetched by the browser (from the public repository by
  default; another address can be set with `ui_src`) and talks to the relay only. Without the internet the small
  status page still works.
- **The first token from the web page.** `{"init_tok": ".."}` sets the token only while the relay has none.
- **HC takes over a change made on the relay.** The script counts a settings revision up on every real change. HC
  keeps the revision it last synced: a higher one on the relay means a change made there, and HC adopts those
  settings into its own options instead of sending its old ones back. A change made in HC still goes to the relay.
  Needs the new script on the device.

## 0.79.8 – 2026-11-26

- **HC Lite: boost.** With TPI or PI, a room at least *boost* °C below the target (1.0 by default; 0 turns it off)
  is heated without a break until it is *boost end* °C (0.3) from the target; then a new cycle starts and the
  demand rules again. The PI integral stands still during a boost (it would only wind up), and the longest burn
  still holds. The status shows the reason "boost" and `boost: true`. With preheat a cold morning starts as a boost.
  Needs the new script on the device.

## 0.79.7 – 2026-11-26

- **HC Lite: preheat.** The night ends early by the room's shortfall: the day target starts
  (day target − room) × *preheat* minutes before the day period (30 min per °C by default, at most *longest preheat*,
  120 min; 0 turns it off). Once begun it holds until the day starts, so a room that warms up quickly does not drop
  back to the night target; a manual target, "away" or "off" has no preheat. The status shows the period "preheat".
  When the target rises by 0.3 °C or more while the relay is off, a new cycle starts at once (before, the rest of the
  running cycle was waited out, up to a whole cycle late). Needs the new script on the device.

## 0.79.6 – 2026-11-25

- **HC Lite: a Wi-Fi H&T as the room thermometer.** A new sensor choice, *Wi-Fi H&T (pushes its reading)*: the
  thermometer's own webhook sends `GET http://<relay>/script/<id>/lite?tok=<token>&t=${ev.tC}` (the H&T's own URL syntax; the settings help names it without braces, as the frontend took them for a message argument) on each temperature
  change, straight to the relay, without Home Assistant. The token is the script's own; "?" and "&" both separate (the
  H&T appends "?hum=.."). The reading ages by the relay's uptime; older than the age limit (set it to 7200 s, as the
  H&T sends on a change only) or none since a script start means no reading, so the no-reading rule applies until the
  next push. A pushed reading is taken in any sensor mode but used only with *push*. Needs the new script on the device.

## 0.79.5 – 2026-11-25

- **"Starts today" counts heating runs.** With a relay (switch, input_boolean, light) a start is the relay switching
  on, counted on the state change itself, so a short run between two decisions is not missed. The flame signal used
  to be counted at the decisions only: it also lights for hot water and relights within a run, and short lights were
  missed, so the number was neither the runs nor all lights (a user counted 25 runs, it showed 32 of 42 flame lights).
  Without a relay the heating signal's starts are counted as before, but not while the hot-water entity is on. The
  run time still comes from the heating signal (the flame when one is given). The same holds for the 24-hour, week
  and season counts and the starts in the last hour (the short-cycling watch).

## 0.79.4 – 2026-11-25

- **HC Lite: a third control mode, PI** (the Shelly script's version 2): besides hysteresis and TPI the settings now
  offer *PI (TPI + integral)*. The demand is base + gain × (error + integral of the error / integral time), so a lasting
  gap closes by itself as the integral learns the house's steady need. The integral stands still while the demand is
  pinned at 0 or 100 % and the error pushes further (anti-windup), stays within ±1, goes to the device's KVS every 15
  minutes (a restart keeps it) and starts from zero when the mode is switched to PI. New setting: *PI integral time*
  (1800–86400 s, 14400 s by default). The status and the climate entity show the integral part of the demand; the HC
  dial card labels it *LITE·PID*. The new script has to be uploaded to the device (upload_shelly.py --lite); an older
  script ignores the PI choice and keeps its own mode.
- **HC Lite: the reason tells the present decision.** It used to change only when the relay switched, so after a
  script start it kept saying *boot* until the first switch; now it is the reason of the state it keeps (e.g. *target
  reached*, *demand 0 %*, *inside the band*). A switch held back by min on / min off keeps the reason of the last switch.

## 0.79.3 – 2026-11-25

- **Hydraulic diagram in two depths, an info-first part panel** (a tester's design idea, dev #7, variant 2 – tried in
  dev): a *User | Maintenance* switch above the diagram. The drawing and its data are the same; only how much it tells
  differs, and the choice is no permission (it is remembered per browser). A tap on a part no longer jumps away: a panel
  beside the drawing tells what the part is, what it does now and why, and lists its values each marked by kind –
  requested, given (HC's command), measured, feedback, worked out, estimated (an estimate is never shown as measured).
  The maintenance depth adds the demand, the reason code, limits, the heat need (estimated), the command against the
  feedback (with a note when they differ, a calm one in shadow), reading ages, starts and run hours today, the last
  switch, the heat source watch and the instance's entities; on the plain diagram each source gets a demand / command /
  feedback line. *Open* goes to the instance as before. No new control logic: everything comes from the HC info data.

## 0.79.2 – 2026-11-24

- **HC Lite, first version (Shelly script, shadow-ready):** `guard/shelly/hc_lite.js` – a complete small thermostat
  on a Shelly Gen3 / Gen4 relay with a BLU H&T: day / night program (weekday and weekend), away, off (frost), manual
  target until the next change or for a time, hysteresis or a simple TPI, min on / min off / max on, the dead-man
  timer, a safe duty without a reading, shadow mode and a small page of its own. It heats without Home Assistant.
  `upload_shelly.py --lite` installs it; desk tests run the unchanged script on a simulated Shelly
  (`node --test "guard/tests/*.test.mjs"`, also in CI). Tried on a real Shelly 1 Gen4 (firmware 2.2.0) in shadow: the
  program, the manual target, the token and the page work; peak memory 9 KB. A wired add-on probe can be the room
  thermometer instead of the BLU H&T.
- **HC Lite in Home Assistant:** a new role, *HC Lite on a Shelly*. The setup asks for the script's address, its token
  and the device password (checked live), then the settings (targets, day / night times, control, limits, what to do
  without a reading, shadow). The instance keeps the device's settings in line with its own, reads it every 30 s and
  offers a climate entity (target → a manual target until the next program change, off, away), the boiler state, the
  decision, today's starts and run time. The device heats by itself – Home Assistant can be off. A new instance starts
  in shadow. The HC panels leave a Lite instance out; its diagnostics carry the device's status.

- **hcd 0.1.4: in shadow it follows the integration's learned values** (`learned_from: <HC entry id>`,
  `learned_every_s`, 900 s by default): the house follows the integration's relay, not hcd's, so hcd's own learner drew
  lessons from decisions it never made and drifted (in the developer's house its demand ran 2–3 points higher and its
  burn minutes 22–38 % above the integration's within four days). hcd now takes the integration's learner state from
  the entry's diagnostics at start and every 15 minutes; `/api/status` shows when and whether it last did.
- **hcd 0.1.5: the regulator's integral is followed too.** With the learned values in line the burn minutes still ran
  ~30 % above the integration's: hcd asked 2–3 points more for the same room, with the same inputs, the same
  feed-forward and the same proportional part. The difference was the PID integral – it only adds up, so the gap from
  the days the two sides ran different core versions never closed. In shadow hcd now takes the integration's regulator
  state with the learned values; `/api/status` → `learned_from.regulator` shows whether it did.

## 0.79.1 – 2026-11-24

- **Heat pump: one correction, its source shown** (a tester's report, dev #10): the "Offset" number entity and the
  settings form's manual correction were two values – a restored entity value silently won over the form, so the form
  could show 0 °C while +4 °C was in use. Now the form opens on the correction in use, a form saved with a new value
  puts that value in force (the entity follows it after the reload), and moving the entity still works between saves.
  The info panel shows where the correction comes from ("from the Offset entity; form: 0 °C" or "from the settings");
  the decision details carry `offset_form` and `offset_source`. The value itself and the target formula are unchanged.
- **Mixing circuit: the weather-led reference beside the target (shadow only)** (a tester's proposal, dev #1): the
  circuit's details now carry `shadow_ref` – the outdoor-only curve at the circuit's reference room temperature, and
  how much the live room target (`room_lift`), the deficit correction and the trim each add on top of it. Nothing acts
  on it; it is the data to judge a target where a room asking for heat first gets more time, not warmer water.

## 0.79.0 – 2026-11-24 (live)

- **No short run just before the morning rise** (`preheat_hold_min`, 20 min by default, 0 = off): when the optimal
  start begins within this time and the room is at most 0.3 °C under its night target, no new regulating run starts
  before it. Seen in the developer's house on two mornings: a 6-minute run 1 and 14 minutes before the rise, then the
  rise waited out the 5-minute minimum pause – two burner starts minutes apart. The room's small fall only brings the
  optimal start a little earlier; a running burn is not cut. Shown as "Limited by: before the morning rise".
- **Switch log** (a tester's request): every change of the commanded output, in shadow mode too, with the indoor and
  target temperature, the demand, the reason, the PWM cycle (length, position, carried seconds) and the catch-up state –
  the last 200, kept across restarts; the last 100 in the HC info data and the downloaded diagnostics.
- **Starts in the last 24 hours:** the "Starts today" sensor gets `starts_24h` (rolling, not since midnight) and
  `commanded_on_24h` (from the switch log) – for comparing settings without reading graphs.
- **Heat pump: the charging reason on its own line.** Under the cold-weather ON the decision shows "ON: cold weather"
  and the charging reason was only in the details; now the info panel and the overview show "Why it charges" beside it,
  with the stop layer (e.g. lower middle 41 °C → 43 °C). The `heat_reason` detail is there whenever it charges.
- **AI analysis: only the live heating.** In a house whose leading instance controls (active), the daily AI report
  covers only the members that control too – shadow members (evaluation, simulations) are left out – and only their
  own open issues plus the house-wide ones (an issue of another house no longer shows up). A house still being
  evaluated in shadow mode keeps every member.
- **Heat meter: compressor Hz / 200 W gate (a tester's contribution):** produced heat counts only with confirmed
  compressor running; without any watt or Hz signal the water-side metering goes on, flagged `heat_confirmed: false`.
- **hcd: host names in `web_allow` right after a boot:** the first lookup waited until the uptime passed 300 s, so in
  the first five minutes after a host boot a named add-on got 403. The first lookup now happens at once (this also
  made the CI test fail on fresh runners since 0.1.3).

## 0.78.4 – 2026-11-21

- **A missed guard renewal is no relay fault while the lease holds:** after an instance reload the Shelly refused the
  first request (`HTTP 429`), and the fault sensor – with its notification – went on for a minute although the
  guard still held a valid lease and the next step renewed it. A failed renewal without an answer, a 429 or a 5xx is
  now logged once and tried again at the next step; the relay part counts as failed only from half the lease time
  (150 s by default) after the last renewal the guard took. A refused token or password (403 / 401) and the
  life-safety stop still count at once.

- **`guard/upload_shelly.py` on a protected device:** the tool used urllib, which knows no SHA-256 digest – the only
  one a Shelly Gen2+ offers – so `--password` and every run after `--set-password` failed. It now uses aiohttp
  (3.12 or later): one session and one digest middleware for the whole run, so the challenge comes once and every
  later call is signed in advance; a 429 is waited out (2, 4, 6 s) and tried again; a wrong password says so.

## 0.78.3 – 2026-11-21

- **Local guard with a device password:** a password-protected Shelly closes the connection on a script endpoint
  request that carries a body and no Authorization – it sends no 401, so the digest auth never started and every
  lease failed with `ClientOSError` (the guard fell back to its own program). HC now first GETs the guard's status
  (that 401 brings the challenge) and sends the lease signed in advance; a broken connection gets one fresh
  challenge and one retry. A wrong password shows as `HTTP 401 (device password)`.

## 0.78.2 – 2026-11-21 (security review)

- **Smaller security review items:**
  - diagnostics replace every room name by `room:<key>` (consistently, so hcd's import still matches the rooms up);
  - a relay entity that is gone is a failed relay part (the fault sensor, Repairs) instead of a silent skip; the
    central boiler and the buffer log a missing switch once;
  - with a relay watchdog script the relay goes **on only through the script**, run to its end – a failing script
    is a failed relay part, never a relay switched on without its timer. *Upgrading:* the script itself must
    switch the relay on (as a Shelly "turn on with timer" does);
  - a life-safety input without a reading for 10 minutes is a Repairs entry (it still never trips the stop);
  - the house drawing's and the overview's escape covers the apostrophe too.
- **Workflows hardened (security review):** the release job passes the tag through the environment instead of
  pasting it into the shell; `actions/checkout` and `actions/setup-python` are pinned to a commit like the others,
  without persisted credentials; pytest and build have fixed versions.
- **The setup wizard's commands check what they take (security review):** `wizard/apply`, `wizard/derive` and
  `wizard/system` accept each entity only in a domain its field allows (as the panel's pickers offer it – no
  `lock.*` as a relay), each setting only in its options-flow range (no string or NaN cycle), bounded lists and names;
  `wizard/system` takes an existing room only when it is an HC instance that can be a zone. A refused value is named
  in the error (`invalid_value`). New module `wizard_check.py`.
- **No real address in the examples (security review):** hcd's example settings and its test use a documentation address (192.0.2.10, RFC 5737) instead of a real LAN address.
- **The manual AI analysis is rate limited (security review):** the *Analyse now* button – which every user can
  press – and the panel's button make a report at most every 15 minutes and 6 times a day (each is a paid AI Task
  call and a day of history); a refused press says when the next one may come. The scheduled morning report is not
  counted.
- **A clock set back holds no relay ON (security review M5):** a remembered switch time in the future (NTP
  correcting a clock, a restored backup) no longer makes a negative elapsed time – the PWM, the on/off gate, the
  central boiler and the heat pump coordination put it back to now (`core/clock.py`): a running ON counts as having
  had its minimum run, an OFF starts its minimum pause again; a PWM cycle start in the future starts a new cycle. A
  reading reported more than a minute in the future has an unknown age and counts as stale.
- **TRV heads go to the frost level in a life-safety stop (security review M4):** every room with thermostatic heads
  gets the frost temperature (room reason `safety_stop`) – also in shadow and over a target turned up on the head
  by hand, so no open head keeps asking a central boiler or another source for heat. A head switched off stays off.
- **The life-safety latch is shared by every instance (security review M3):** an instance without safety inputs of
  its own stops with the house too – the central boiler (off, flow setpoint to its lowest; the pump keeps its
  overrun), the buffer (no charging), the mixing circuit (`circuit_flow_min`, forced), a room and the heat pump
  coordination – whenever any HC instance watches inputs and the latch holds; also in shadow. The decision sensors
  say `safety_stop`. The notification no longer claims more than HC does.
- **The guard's longest run in every mode (security review M2):** `max_on` now also cuts a run in the grace, the
  fallback and the handback (then `min_off`), not only while HC controls; electric heaters get `guard_max_on_s` 2 h
  by default. A Bluetooth reading of unknown age (no time sync, no timestamp) is no reading, and a pushed reading
  counts for 2 hours instead of 4.
- **Local guard secured (security review H3):** the token is required – the guard script (version 2) takes no
  lease and no pushed temperature without `hc_guard_token`, HC's settings refuse a guard address without a token. New
  setting *Device password*: every lease goes with the Shelly's digest auth (aiohttp `DigestAuthMiddleware`, user
  admin), which on a password-protected device also closes the whole Shelly RPC. `upload_shelly.py` makes a random
  token when none is given, reads secrets from `HC_GUARD_TOKEN` / `HC_GUARD_PASSWORD`, speaks digest auth and can
  protect the device (`--set-password`, `Shelly.SetAuth`); it warns about a device without a password. The token and
  the password never leave Home Assistant in the info panel; diagnostics also redact the guard's address.
- **The guard's safety command (M1):** HC's life-safety stop reaches the guard as `cmd: "safety"` – off at once
  (no `min_on`), latched on the device (KVS `hc_guard_stop`, kept over a restart, no fallback heating) until an
  ordinary lease after the acknowledgement; the status shows `hc_stop`.
- *Upgrading a guard:* upload the script again (`upload_shelly.py`), and enter its token (and the device password)
  in HC – a guard without a token now runs only its own program.
- **The life-safety stop cannot be bypassed (security review H1):** it now reaches the output on every path.
  The room thermostat's executor writes it also in shadow and with "HC supervision paused"; a decision step that
  raises while the latch holds gives the stop's own off decision at once (not only after the failsafe's third
  failure). The heat pump coordination reads the latch before its step, and its OFF, no demand, no exercise and
  lowest target go out forced – `OutputWriter.apply(force=True)` ignores shadow, an ended trial, paused writing,
  the grace after a start and a conflict / unaccepted / given-up value (status `safety`). A latch that cannot be
  read counts as tripped.
- **Failsafe in every instance that switches heat (security review H2):** the central boiler, the buffer, the mixing
  circuit and the heat pump coordination now do what the room thermostat has done since 0.45.0 – a step that fails
  `FAILSAFE_AFTER` (3) times in a row no longer leaves the output as it was: the boiler / the buffer's heat source is
  switched off (the modulating boiler's flow setpoint to its lowest, the pump keeps its last state), the mixing circuit
  gets `circuit_flow_min`, the heat pump no ON, no heat demand and no exercise with `hp_flow_min`. The decision sensor
  says `failsafe`, a Repairs entry (error) names the instance; both clear with the first step that works again. The first
  two failures raise as before (the entities go unavailable). New module `failsafe.py` (`StepFailsafe`).
- **System drawing, a boiler with its rooms:** the return pipe back to the source (blue) beside the flow; the measured
  flow and return temperatures (Settings → Measurements) in the source's box at the pipes' side; a room's
  thermostatic heads as a valve sign with the head's target (orange while the room asks for heat; the names, targets
  and head temperatures as a tooltip).

## hcd 0.1.3 – unreleased (security review)

- The page listens on `127.0.0.1` by default (`web_host`; it has no login); `web_allow` lets in only the named remote
  addresses. The add-on listens for its ingress and lets in only the Supervisor's proxy (172.30.32.2).
- The add-on runs the service as the unprivileged `hcd` user (`su-exec`), with a private 0600 copy of the settings in
  `/data`; `/share` is mapped read-only; the Python packages have fixed versions.
- The add-on's `web_allow` option: besides the ingress proxy, addresses or add-on host names (resolved, so a
  restarted container is still let in) that may read the page and the API.

## hcd 0.1.2 – 2026-11-20

- The steps where hcd and the integration differ (decision reason or output) are in the API: today's (at most 200,
  newest first) as `disagreements` in `/api/status`, any day's in `/api/disagreements?day=YYYY-MM-DD` (today by
  default).

## hcd 0.1.0 – 2026-11-19 (F2, shadow)

- **hcd**, HC without Home Assistant's core (`hcd/`): the same decision core (`hc_core`), its own feeds – Home
  Assistant states (REST, with a device "last seen" entity as `seen_from`), Zigbee2MQTT over MQTT (the payload's
  `last_seen` as the device time; contacts inverted, a power draw over a threshold as a burner signal), Shelly Gen2+
  RPC (the relay as it is) – a YAML settings file, a JSON state file and SQLite. It builds the inputs as the
  integration's coordinator does for a relay-driven boiler (rooms and the leading room, windows and the zone door,
  plausibility, the outdoor day average, presence, the restart confirmation, burner, heat delivered, the other
  source's heat). Settings it cannot handle yet are named (`unsupported`).
- **Shadow comparison:** every step the integration's decision, target, demand and relay are read from Home
  Assistant and kept beside hcd's own; a page (add-on ingress) shows the day's agreement and burn minutes. A preset or
  manual target set in Home Assistant is taken over.
- `python -m hcd.import_ha` makes the settings from an HC instance's diagnostics and, with `--state`, starts hcd from
  the integration's learned state. `tools/build_hcd_addon.sh` puts the local add-on together (Alpine 3.21 base,
  `services: mqtt:need`, ingress).
- 14 new tests (settings, feeds, engine, comparison, page, import); the test run also imports the core as `hc_core`.

## 0.78.1 – 2026-11-19

- The restart protection (0.77.3) now ignores reports in the first `restart_settle_s` (180 s) after Home
  Assistant's start: those minutes bring the restore and a bridge re-sending its cached states (Zigbee2MQTT
  ~1.5 minutes after the start), which look like new reports. A real report after that – or a device "last seen"
  time after the start – confirms the reading. A sleeping H&T (every ~5 minutes) costs at most one more cycle.
  (Correction to the first note on 21:11: the H&T really reported at 21:14:20; Home Assistant's REST API showed an
  old `last_reported`, as it caches a state whose value did not change.)
- **A device's own "last seen" time.** Where a thermometer's device has a `*_last_seen` timestamp entity (Zigbee2MQTT
  with `last_seen` turned on), HC ages the reading by it and a message after the start confirms at once. A Zigbee
  sensor that went silent no longer reads as fresh just because Zigbee2MQTT re-sent its last value; it shows as
  stale after `sensor_max_age_s`. Core: `Sample.seen`, `reported_at()`; integration: `seen_view.py`.
- The HC info panel shows the running version in its header.

## 0.78.0 – 2026-11-19

- The decision core is a package of its own: **`hc-core`** (import name `hc_core`, no dependencies, AGPL-3.0-only),
  built straight from `custom_components/hc_thermostat/core` by the new `pyproject.toml` – one source, no copy. The
  Home Assistant integration keeps using it as `.core`; the standalone service (`hcd`, next) will build on it.
- New `core/inputs.py`: turning raw states into readings without Home Assistant – °C conversion, a reading's age,
  on/off contacts, a thermometer group's fresh mean, the restart confirmation (0.77.3) and the outdoor day average.
  Home Assistant's `State` is already such a sample, so the coordinator passes `hass.states` as it is and only
  delegates. New `core/ports.py`: what a body provides (clock, state view, output, state store, notifier).
- No change in behaviour: the same readings, the same decisions; the saved outdoor samples load as before.
- Tests: the core imports nothing outside itself and the standard library, runs as `hc_core`, its °C conversion
  equals Home Assistant's; a new CI job builds the wheel and runs it without Home Assistant.

## 0.77.3 – 2026-11-19

- After a restart a sleeping thermometer's value (a battery Shelly H&T, a Zigbee sensor) is often the one restored
  from before the restart, stamped with the start time – it looked fresh. The room reading now counts as confirmed only
  once one of its thermometers reports again; until then (at most `restart_sensor_wait_s`, 15 minutes) a house no more
  than `restart_margin` below the target stays in *Waiting after restart*: no burn starts on the old value, and a
  running after-heat watch is not ended by it. A colder house still heats at once; frost protection is unchanged.
  (Seen live: a reading restored 0.7 °C low ended the after-heat watch and started a needless 6-minute burn.)

## 0.77.2 – 2026-11-19

- The local guard keeps `min_off` after its own start when the relay is off – after a power cut or a restart right
  after the dead man switched the relay off, the boiler no longer fires again at once. A relay found on may still
  switch off at once (no `min_on` to wait for).

## 0.77.1 – 2026-11-19

- The local guard's dead man: every "on" the Shelly script gives carries the relay's own flip-back timer
  (`toggle_after`, 180 s), re-armed every minute while the script runs. A stopped or crashed script – or a failed
  upload – lets the relay switch itself off within 3 minutes instead of keeping the boiler on; an "off" never carries
  a timer. `upload_shelly.py --deadman <s>` (KVS `hc_guard_deadman`, 60–3600 s, 0 = none); the status shows `dm`.
- Guard README: what other controllers taught – ESPHome's `reboot_timeout: 0s` (the default reboots every 15 minutes
  without Home Assistant), the relay off at boot, never full power as an emergency mode, and the guard is no safety
  device (the boiler's limits and the wired chain stay in series).

## 0.77.0 – 2026-11-18

- Life-safety stop (smoke, fire, gas, CO, water). The real stop belongs to a wired safety chain – certified detectors'
  normally closed contacts in series holding a latching relay that keeps the gas valve open, the heating's contactor
  on and the water valve open – and needs no Home Assistant. HC reads the chain's auxiliary contact (and detectors as
  a second signal): *Settings → Protection → Life-safety inputs* on a room / boiler instance, and on the heat pump
  coordination's first page. Any input on trips one shared latch: every instance watching it stops at once – above
  every other reason, frost protection and the valve exercise included; the relay off without its minimum run, a
  managed thermostat or air conditioner off, no flow asked for; the heat pump coordination gives no ON, no heat demand
  and the lowest target. The latch survives a restart and lets go only with the new *Acknowledge the life-safety
  stop* button once every input is clear and readable; an unreadable input does not trip on its own (the chain does)
  but blocks the acknowledgement.
- Announced once: the `hc_thermostat_safety_stop` event (for your own notifications), a persistent notification and a
  critical Repairs entry; `hc_thermostat_safety_clear` when acknowledged. New *Life-safety stop* binary sensor on
  each watching instance; the decision `safety_stop`; DECISION_CHAIN starts with it.
- The local guard: an input wired to the chain's auxiliary contact (`hc_guard_safety`, `upload_shelly.py --safety`)
  switches its relay off at once whatever the lease, as a second line, and announces it.

## 0.76.0 – 2026-11-18

- Local guard: a small program next to the relay that keeps the heating going when Home Assistant or HC fails.
  With *Settings → Local guard → address* given, HC no longer calls the relay's switch service: it sends the command
  as a **lease** to the guard (at once on every change, renewed every 60 s, valid 5 minutes), written from HC's own
  decision step – a Home Assistant that runs while HC is stuck lets it run out like a stopped one. Without a lease the
  guard keeps the last command for 5 minutes (a usual restart changes nothing), then regulates by its own thermometer
  with the fallback target and band set in HC (sent with every lease, kept on the device); without a thermometer it
  switches off or runs a fixed duty cycle. It hands control back only after a stable lease (2 minutes, 2 renewals),
  starts in fallback after a power cut, keeps HC's minimum on / off times in every mode and can post a push (an ntfy
  topic) when it takes over – independently of Home Assistant. Without an address nothing changes.
- `guard/shelly/hc_guard.js`: the guard for Shelly Gen3 / Gen4 relays (plain ASCII; a BLU H&T over BTHome or an
  add-on probe as the thermometer; optional token), `guard/upload_shelly.py` puts it on a relay, `guard/README.md`
  describes the setup, a test procedure and the protocol for ESPHome or a PLC.
- The guard also takes a room temperature pushed by a Wi-Fi thermometer (`?t=` / the Gen1 H&T's `?temp=`, with the
  token; kept 4 hours, the Bluetooth sensor first) – for a house without a BLU H&T.
- New *Local guard* sensor (normal / grace / fallback / nosensor / handback / unreachable) with the guard's thermometer
  and lease; an info panel row; a Repairs entry when the guard cannot be reached for 10 minutes or regulates on its
  own while HC runs. The token and the push URL are redacted from the diagnostics.

## 0.75.0 – 2026-11-18

- Heat meter and COP for the heat pump coordination (a tester's request after the readings of a heat pump charging a
  1000 l tank through its lower coil: 44 / 41 °C at 48 l/min ≈ 10.05 kW). Optional – the new *Heat meter and COP*
  section takes the water flow (outlet) and return (inlet) temperature and the water flow (l/min; L/h and m³/h
  converted); with all three given HC works out the heat the water circuit carries off the heat pump:
  kW = l/min × ΔT × 0.06977 × factor (pure water 1.00, lower for a glycol mix). Without them nothing changes.
- New sensors on the coordination's device: *heat output* (kW, unavailable without valid readings), *heat produced*
  (kWh, total increasing, kept over restarts – for the Energy dashboard and long-term statistics), *heat today*
  (a part of the total), *current COP* and *COP today*.
- The energy is the trapezoid rule between two valid readings at most `hm_max_gap_s` (2 min) apart. A reading missing,
  stale (`hm_max_age_s`, 5 min), not a number or impossible pauses the counting; a restart or a gap adds nothing and
  nothing is filled in. No flow (below `hm_min_flow`) is 0 kW; a negative ΔT is 0 kW – the counter never goes down.
- The COP takes the electric power HC already reads (the "runs" signal when it is a W / kW reading) or an own power
  sensor (*Electric power for the COP*); a binary / Hz signal alone gives the heat but no COP. The current COP is the
  heat over the electricity of the last `hm_cop_window_s` (10 min) of active running – water flowing, ΔT above zero,
  a fresh power reading above `hp_running_w`, no defrost – shown after `hm_cop_min_s` (5 min) of a run, which starts
  its window afresh (no spike at a restart); otherwise unavailable (never 0, never infinite), above `hm_cop_max`
  implausible. *COP today* and the all-time COP divide energies of the same intervals (not a mean of COPs), with the
  coverage. What the power meter measures (the whole unit or the compressor) is shown with it.
- Whole-degree thermometers: ± resolution / ΔT is shown as the estimate's uncertainty (`hm_resolution`, 1 °C).
- Info panel: a *Heat meter and COP* card (flow / return, ΔT and its uncertainty, flow, heat and electric power,
  current and momentary COP and why there is none, today / total kWh and COP); the *Heat pump target – 24 h* chart
  draws the current COP on its own right axis, broken where it does not heat, switchable in the browser (*COP curve*).
  The COP's history comes with the chart's own query (`hc_thermostat/hp_history`).

## 0.74.0 – 2026-11-18

- Low-temperature catch-up (a tester's proposal after 24 h on a buffer house: radiator rooms stayed at 22.7–22.9 °C
  for 23.2 °C on a circuit asking ~32 °C – a shortfall under the 0.5 °C catch-up threshold, so the TPI paused every
  hour, and every pause moved the thermoelectric valves and could stop the pump). Off by default: *Low-temperature
  catch-up* in the Regulation section. When every mixing circuit that lists the room has asked for a flow strictly
  below 45.0 °C for 15 minutes, the catch-up starts at 0.3 °C, after 30 minutes on radiators or 2 hours when one of
  the room's circuits is a floor (or the room is a floor room), and ends within 0.1 °C (floor 0.2 °C). All of these
  can be set.
- The circuit's demanded target decides (the one before the tank cap) – not the measured flow, which a stopped pump,
  a cold pipe or a slow mixer would show low. A room in two circuits (a bathroom: radiator + floor) is low only when
  both are. The classification changes only after the new state lasts the confirmation time, so 44.9 ↔ 45.0 does not
  switch it; a circuit not loaded, failed or without a target: the room's own thresholds at once (after a restart the
  saved classification is kept while the circuits load).
- Unchanged: the minimum on/off times, the floor limit, the overshoot stop, sensor faults, window, season, presets, a
  changed target and the other safety rules come first; a catch-up switched off (*from this shortfall* 0) stays off.
- Info panel *Catch-up circuit* row and the decision details (`catchup_mode`): the circuit kind and demanded flow, the
  classification (and a pending change), the threshold, wait and release in use, the wait so far and the last exit
  (reached, new target, other source, paused).

## 0.73.0 – 2026-11-17

- Supervised restore for the heat pump coordination (a tester's request – a Tuya unit came back from off / auto with
  12 °C and HC, as designed, stopped writing it as a conflict). Off by default: *Restore a lasting difference after*
  (minutes) and *Restore tries* (3) on the writing page. A conflict or a value the unit did not take that lasts that
  long is written again – HC's value as it is now, so the safety bans, frost protection and the wood priority still
  come first –, at most that many times, as far apart; a restore that holds that long starts the count again. When
  none helped: the new *Heat pump does not follow* problem sensor, a Repairs entry and a notification, the diagram and
  the info panel in red; HC stops writing that value until it wants another one or the unit shows HC's value again.
  Nothing changes with it off (a conflict stays a conflict, as before).
- With the restore on, a climate ON/OFF output counts its mode too: a unit put into another mode than the heating one
  HC switches to (LocalTuya: *auto* instead of *heat*) is a difference to restore.
- The first lasting difference is a warning (a notification saying when the restore comes, the problem sensor's
  `level: warning`, amber on the diagram); every restore failed is an error (the sensor on, Repairs, red). Each
  restore writes what HC asks for at that moment (a wood fire started meanwhile: the new, lower target).

## 0.72.1 – 2026-11-17

- The rooms form saves a room without a thermometer or a TRV head (a hallway on the house drawing, heated through the
  boiler, nothing measured there). It was refused – "a room needs a thermometer or a TRV head" – so once such a room
  was in the list, no change to any room of the instance could be saved.

## 0.72.0 – 2026-11-17

- Weekly program for the instance and for each room with its own TRV heads: on the HC info panel a 7-day grid where
  the levels Comfort, Home, Night and Eco are painted in 15-minute steps (copy Monday to Tue–Fri, Saturday to Sunday,
  a template); the levels' temperatures can be changed in the same window. A program takes the place of the night
  window (optimal start aims at the level after the night); removing it brings the night window back. Presence, a
  preset and a manual target still win. Saved through a new admin websocket command `hc_thermostat/week_set`; the
  instance reloads with it. A room that followed the house becomes an own-schedule room, starting from the house's
  targets plus its offset; own rooms gain comfort and eco targets.

## 0.71.4 – 2026-11-17

- No deprecation warnings on Home Assistant 2026.11: the thermostats give their temperatures by the new native
  names (`native_current_temperature`, `native_target_temperature`, `native_temperature_unit`; the old ones stop in
  2027.11). Home Assistant 2026.10 keeps working with the old names.
- The room devices of the mould risk sensors and the room groups hang under the instance by `via_device_id` too
  (the old `via_device` stops in 2027.8), like the room thermostats already did.

## 0.71.3 – 2026-11-17

- Air conditioner helping the house: when the help starts or ends, the slow correction (integral) starts again from
  zero. Before, what was gathered while helping stayed after the door was closed and kept the unit above the room's
  own target for hours (a terrace unit stayed at 21 °C for an 18 °C target).

## 0.71.2 – 2026-11-17
- **Heat quantities in MJ too.** Wherever the panel, the overview, the hydraulic diagram and the AI analysis show a
  heat or energy quantity in kWh, its MJ (1 kWh = 3.6 MJ) is beside it – e.g. *14.5 kWh (52 MJ)* – so it compares
  easily with a gas bill, which counts in MJ. The AI analysis gets the MJ values as well. The energy rating
  (kWh/m²·year) and the heat capacity (kWh/K) stay as they are.

## 0.71.1 – 2026-11-17
- **License: AGPL-3.0** (AGPL-3.0-only) from this version on, instead of MIT – see LICENSE and NOTICE. Releases up
  to 0.71.0 keep the MIT License they were published under.
- **Co-author: Krissz55555** – in the manifest's code owners, the copyright notice and the README.
- No change in the code's behaviour.
- **Every release carries `hc_thermostat.zip`** (also attached to all earlier releases); HACS downloads that file
  (`zip_release`), so the release page counts the downloads. A workflow attaches it to each new release.

## 0.71.0 – 2026-11-17
- **AI analysis of the house** (`ai_task_entity`, `ai_report_time` 06:30; Settings → Functions of the house's
  leading instance). HC first works out yesterday's numbers for every member of the house from the recorder: room
  temperature mean / min / max against the target, hours more than 0.3 °C below and 0.5 °C above, heating hours and
  starts, hours per mode and per decision, the plant's states (tank charge, circuit flow, heat pump runs), the outdoor
  day, energy and cost (a fuel / energy meter or a power meter when given, else heating hours × the rated power –
  marked measured / estimated) and the open HC warnings. The user's own AI Task entity turns them into a score, a
  summary, observations and things to do – advice only, HC changes nothing by it. Without an AI Task entity the
  numbers alone are made on request.
- **On the house drawing an AI button** (score and the number of things to do, coloured) opens the report: summary,
  observations, things to do, HC's numbers per instance, *Analyse now*. Also the *AI analysis* sensor (the score; the
  texts in its attributes), the *AI analysis now* button and the `hc_thermostat_ai_report` event (for a notification).
  The report is kept over a restart.

## 0.70.1 – 2026-11-17
- **An AC helping the house waits for a lasting open door and stays under a limit** (`assist_delay_s` 10 min,
  `assist_max_setpoint` 22 °C; 0 = the earlier behaviour). A kitchen door left open for 40 minutes made the terrace AC
  aim at the house's 22.5 °C by the terrace thermometer and raise its own setpoint to 25 °C – the terrace reached
  21 °C against its 18 °C target. Now a quick walk through does not raise the unit at all, and while helping the
  setpoint written to it is at most 22 °C. The decision's details show the wait (`assist_wait_s`).

## 0.70.0 – 2026-11-17
A tester's list after the 0.69.0 night: more to see, nothing new that regulates.
- **The heat pump's own target on the diagram:** under the unit *set* (what it reports back), *HC asks* (the sent
  target; the given-out one in shadow) and *worked out*. While HC writes, a difference over 0.4 °C lasting 10 minutes
  is a mismatch: amber on the diagram, a warning on the overview, *Matches the asked one* on the panel.
- **Mixing circuit watch** (`circuit_watch`, on by default; watching only): the chain *demand → pump → flow*. The pump
  should start within `circuit_watch_pump_s` (10 min – a PLC's start delay fits in), the flow should move by
  `circuit_watch_flow_c` (1 °C) or get within 2 °C of the target within `circuit_watch_flow_s` (15 min) after the
  pump started. A missing step is an entry in Repairs (it clears itself), the circuit amber on the diagram, a warning
  on the overview; the panel shows the step and its minutes. A pump state that is not known never raises it.
- **Heat pump: heating, standby, stopped or not known** (`hp_standby_w`, 10 W): a power reading between it and
  `hp_running_w` is standby (switched on, the compressor stands) – the tester's 138 W at a 200 W threshold. The
  diagram, the overview, the panel (with the power, its age and both thresholds) and the coordination use the same
  state; for the coordination standby is "does not run", as before.

## 0.69.0 – 2026-11-17
After a tester's first real night on a buffer house (1000 l tank, two motorised mixing circuits, 5-minute
thermoelectric valves, a PLC that starts the pumps late): the rooms switched far more often than before and still
stayed 0.2–0.4 °C under their targets.
- **Fast catch-up of a room long behind** (`catchup_gap` 0.5 °C, `catchup_after_s` 30 min – 2 h on a floor,
  `catchup_release` 0.2 °C; 0 = off): such a room gets the whole cycle, without a PWM pause, until it is near its
  target. Before, the TPI's proportional share left a room 0.75 °C behind on 64 % with a pause every cycle. The info
  panel and the explanation say so. A partial cycle while a room settles back after it no longer counts as a heating
  fault.
- **The holding offset learns by the hour** (at most 0.02 an hour, within −0.2…0.3), not once a day by at most 0.05 –
  a steady shortfall is gone within a day instead of a week; not while the room already has the whole cycle. The
  TPI's daily strength step now counts the hours more than 0.2 °C behind (was 0.3).
- **The TPI's coefficients in the settings** (`tpi_coef_int`, `tpi_coef_ext`, Regulation section, Advanced mode).
- **Mixing circuit: the flow from the rooms' lasting shortfall** (`circuit_room_trim`, off by default; step 0.5 °C an
  hour, ±5 °C): when most zones of the circuit heated nearly all the hour and still stayed below, the water goes up;
  when all held their targets with less than half the time heating, it goes down – long, even runs on cooler water
  instead of frequent switching. A tank too cold to give more does not count. Kept over a restart; the panel shows the
  adjustment and the hour so far.
- **The measured answer of a room** (panel, shown only): from ordinary runs of at least 10 minutes – minutes until it
  warms, °C/h while heating, the after-heat and its minutes, °C/h cooling.
- **Timing suggestion:** with a valve delay, a cycle shorter than six delays (or a minimum run shorter than two) gets a
  suggestion on the panel – 30 minutes for radiators, 60 for a floor at least.
- **Heat pump: the full target at once for a new charge** (`hp_charge_jump`, on): when a charge starts, and when the
  compressor stops below the target during one, the given-out target goes straight to the worked-out value; the
  hold's confirmation, interval and ramp only smooth the changes within a charge. The tester's unit stopped its
  compressor at 39 °C given while 44.5 °C was worked out.
- **The compressor's power threshold** (`hp_running_w`, 100 W): a power reading above it means the heat pump runs.

## 0.68.0 – 2026-11-16
**Demand-based tank charging, second step: the start timed by the pace of use** (`hp_lead_min`, 60 minutes; 0 = off).
In the demand rule the heat pump also starts when the tank cools steadily – its mean by at least 0.2 °C/h – and at
that pace its top would fall under the need within the lead time: the heat of the lower coil takes that long to reach
the top, so waiting for the reserve margin alone can be too late with a large draw. New reason `reserve_runs_out`
("the reserve runs out soon – charging"); the info panel shows the estimated time left and the lead time. The classic
rule is unchanged; both are still shown side by side.

## 0.67.0 – 2026-11-16
Simpler to set up and change, after an outside review (no change in how HC regulates on weekdays).
- **Weekend night:** an optional start and end for the nights ending on Saturday and Sunday morning (Friday and
  Saturday evening's) – e.g. the night target from 23:30 until 08:00. Empty: as on weekdays. In *Targets and times*
  and in *Settings*; both or neither (the form says so). The schedule, the next change, the coasting before a lowering
  and the optimal start all follow it (`core/schedule.py`). A room's own schedule stays one window.
- **Fine-tuning only in Advanced mode:** the *Regulation*, *Energy*, *Adjoining space*, *House* and *Measurements*
  sections of the settings page appear only with Advanced mode switched on in the user's profile; without it the page
  says so, and saving keeps those values unchanged.
- **README rewritten as a manual:** by topic – getting started, everyday use, heat sources and systems, rooms, floor,
  buffer and heat pump, house model, watching and safety, settings – instead of by version; version numbers live in
  the CHANGELOG.

## 0.66.0 – 2026-11-16
Watching and simpler changes, after an outside review (no change in how HC regulates).
- **A heat source problem goes to Repairs:** no ignition, no response to the relay, short cycling, a heating fault,
  overheating, burning without command or a lost power / flame reading that lasts 5 minutes is an entry in Home
  Assistant's *Repairs* (an error for the serious ones), with the instance's name, the problem and since when; it
  clears itself when the source is fine. Until now only a binary sensor turned on.
- **Notification blueprint** (`blueprints/automation/hc_thermostat/hc_problem_notify.yaml`): a push to a phone when
  *Boiler problem* or *Heating fault* stays on for the given minutes, with the problem in words, and optionally when it
  clears.
- **Diagnostics download** (Devices & services → HC Thermostat → ⋮ → Download diagnostics): the settings and
  everything the info panel shows for the instance; the house name is redacted.
- **"Targets and times" menu item:** the home, night, away and vacation targets, the frost limit and the night's
  start and end on one short page, saved at once – no more Settings → save → Presets → save for the most common change.
- **The mode only in the menu:** *Mode* and the confirmation tick left the Settings page (going live and back to
  shadow have their own menu items); saving the settings keeps the mode as it is.
- **Diagnostic sensors:** *Learned values*, *Time constant*, *Heat loss factor*, *Agreement* and *Cheaper source* are
  in the diagnostic category; the cheaper source sensor starts switched off on a new instance without any price.

## 0.65.3 – 2026-11-16
- **Fix:** the *Boiler state*, *Flow setpoint* and *Shadow regulator* sensors were made only when the floor area was
  given – since 0.51.0 a slip of the indentation had put them under the energy rating's `house_area_m2 > 0`. They
  are back under the regulator's own conditions; only the energy rating needs the floor area. Found by an outside
  review.

## 0.65.2 – 2026-11-16
Settings forms easier to read (no change in what is controlled; the stored settings are the same).
- **Heat pump coordination rules page in fold-out sections:** the charging rule, the flow limits, the reserve and the
  offset stay on top; *Charging by demand*, *Classic charging*, *Running and standby*, *Summer / winter mode,
  exercise*, *Cold-weather ON (monoblock)*, *Wood* and *Hold of the target* fold out – the classic and the
  demand-based charging fields are no longer mixed. An error of a folded field is shown above the form.
- **Explanations** (Hungarian and English) for every field of the buffer, mixing circuit, circuit curve, heat pump
  coordination and rules forms, and for every field of the zone / thermostat settings page (about 150 new texts):
  what it does, when it matters, typical values.

## 0.65.1 – 2026-11-16
A user-friendliness pass (no change in what is controlled).
- **Info panel:** the mixing circuit's and the heat pump coordination's *Decision* and *Details* rows are in words
  (Hungarian / English labels, reasons, wood level, cap state, charging rule, stop layer) instead of raw keys; zones
  are shown by their names, not entity ids (the zones card, *lasting* / *asking*, the names in the circuit drawing);
  the header says the role ("Mixing circuit (from the tank)", "Heat pump coordination (tank charging)") instead of the
  raw role twice; the cards are wider and no longer break words; the heat pump target chart is open; a switched-off
  tank cap says "switched off", not "no tank".
- **Forms:** the circuit and heat pump coordination titles lost "(shadow)" (they can write), no version numbers in the
  texts, the offset label no longer says "later"; a **zone** can now set the **house name** too (in *Adjoining*), as
  it has no rooms step.
- **Learning sensors:** the heat need, heat loss factor and time constant have a `status` attribute (still learning /
  given by hand / learned), and the cheaper source sensor says "no data – give the prices" (`no_data`) instead of
  HA's plain "unknown".
- The heating curve's small texts are a little larger.

## 0.65.0 – 2026-11-16
**Demand-based tank charging** (`hp_charge_mode`), after the tester's live case: at 18:58 with 5 °C outside the top was
37.0 °C, the layers below 36.6 / 35.9 / 28.5 °C, the charge 9 %, both circuits asking, the need 34.5 °C – and the heat
pump stayed off, because the classic rule starts only when the top falls under the need (or the charge under
`hp_charge_on`). With the heat pump on the lower coil of a 1000 l stratified tank its heat reaches the top late, so
that start comes too late.
- **Two rules, both worked out every step, each with its own hysteresis;** `hp_charge_mode` picks the one that drives
  (`classic` – the rules so far – by default; `demand`). The info panel and the overview show both, so they can be
  compared in shadow first.
- **Demand rule:** the need is the circuits' demanded (not tank-capped) target + margin. The reserve is the top − need
  (°C) and Σ layer litres × 1.163 × max(layer − need, 0) (kWh, with the tank's volume). It **starts** when the top <
  need + `hp_start_margin` (3 °C) or the kWh reserve < `hp_start_kwh` (0 = not used), and **stops** only when
  `hp_stop_layer` (the lower middle sensor; the nearest measured one above when missing) reaches need +
  `hp_stop_margin` (3 °C) – a usable reserve in the upper part, not just a warm top. That stop point is never above the
  heat pump's flow target − `hp_coil_dt` (3 °C), so HC never waits for a tank the coil cannot reach, and never under
  the need. With no lasting demand nothing starts and a charge stops; the percentage is information only. Frost, wood
  first, the cold-weather ON, the no-demand stop, summer mode and the min on / off are unchanged. A tank with only its
  own zones (no circuit) keeps the classic rule.
- **Shown:** the driving rule, both rules' decision and reason, the reserve (°C, kWh), the start and stop points, the
  stop layer's temperature, and the estimated hours until the top reaches the need from the tank's trend (information
  only – timing the start by it is the next step).

## 0.64.1 – 2026-11-16
- **Update safety: the tank cap (`circuit_tank_cap`) is off by default.** In 0.64.0 it came on by itself for every
  circuit linked to a buffer, so for a circuit already writing to a PLC the update alone could change the live
  setpoint (a cooling tank, or the first half minute after a restart while the tank's reading is not in yet). Now it
  is switched on by hand in the circuit's settings; an instance where it was already ticked keeps it.

## 0.64.0 – 2026-11-16
The tester's third round, live on the buffer system: the heat pump's target writing works (slowly, by the
confirmation, the interval and the start-up wait – as meant); four requests.
- **The mixer's target is capped by the tank (`circuit_tank_cap`, for a circuit linked to a buffer; off by default since 0.64.1):** the mixer
  cannot give warmer water than the tank's top holds, so the target given to it is min(demanded, top −
  `circuit_margin`), the limit on a 0.5 °C grid. Three values: the **demanded** flow (it still goes to the heat pump
  coordination – the heat pump must see the real need, not the capped one), the one **given to the mixer**, and the
  **shortfall**. A cooling tank lowers it at once (no confirmation wait); a warming one lets it back up by at most
  `circuit_max_rise` every `circuit_confirm_s`. A limit below the circuit's minimum gives the minimum and says "tank too
  cold"; with no fresh tank reading the last good one caps for 15 minutes, then nothing caps ("no tank reading", a
  warning). The circuit sensor's attributes (`demand_target`, `tank_cap`, `cap_state`, `shortfall`), the info panel
  and the overview (a warning while it limits) show it. `circuit_margin` (2 °C by default, 0–10) is the margin.
- **The heat pump's written target can be rounded up (`hp_target_round`):** the device's own step to the nearest (as
  before), up to 0.5 °C, or up to whole °C (36.1 → 37, 41.5 → 42) for a unit that mishandles decimals. HC keeps its
  decimals inside; the read-back check compares with the rounded value, within the unit's min / max.
- **Heat pump target chart (info panel, heat pump coordination, 24 h):** HC's raw target, the given-out one, what was
  really sent (rounded), the unit's reported setpoint and – with the new optional `hp_water_temp_entity` – the water it
  measures; from the recorder (`hc_thermostat/hp_history`, admins only). The target sensor also has `sent`,
  `reported`, `round` and `water` attributes.
- **House name on the plant's instances:** `home_name` can now be set in a buffer's, a mixing circuit's and a heat
  pump coordination's settings too (it was only in a zone's rooms step), and the house drawing takes it from any of
  the house's instances – the host instance keeps its own name. The same house name joins instances into one house.

## 0.63.0 – 2026-11-16
The buffer system's hydraulic diagram redrawn after the tester's own plant room drawing, and the readings it was
missing.
- **Plant room diagram:** outdoors the air-to-water heat pump (running / standing, its power), in the plant room the
  wood boiler (fire, its thermometer), the tank with its layers as a cold-to-warm colour gradient and its thermometers
  named on its side ("Tank 1 (top)" … "Tank 4 (bottom)"), the heat pump's lower coil, separate flow (red) and return
  (blue) pipes with arrows (moving while they flow), and per mixing circuit its circulation pump and three-way mixing
  valve with the return through the valve's third port; the circuit boxes carry a radiator / floor icon, the target and
  the measured flow. The rooms have icons (bedroom, bathroom, laundry, living room, kitchen, study); a room on two
  circuits (the bathroom with radiator and floor) is drawn once, between its two circuits. A legend and a control box
  (the modes of the instances, coil, wood first) close it. Light and dark theme. A house without a tank keeps its
  simple drawing.
- **Hot water tank (optional, drawing and overview only):** `dhw_pump_entity` (the third pump that charges it from the
  tank), `dhw_temp_entity` and `dhw_heater_entity` (its electric heater, PV / grid) in the buffer's settings: hot water
  is drawn as a branch of its own from the middle of the tank, through the hot water pump to the hot water tank (with
  its temperature and heater), under the circuits, its return to the tank's bottom; the overview shows them too.
  Nothing is switched.
- **What the PLC reports (optional, display only):** `circuit_pump_entity` (the circuit's pump runs) and
  `circuit_flow_entity` (the measured flow) in a mixing circuit's settings: the diagram shows the pump as the PLC says
  (else HC's enable), the overview has *pump (PLC)* and *measured flow* rows.
- The buffer system setup (`hc_thermostat/wizard/system`) takes these too (`buffer.dhw_pump`, `dhw_temp`, `dhw_heater`,
  `circuits[].pump`, `flow`).

## 0.62.0 – 2026-11-16
The tester's second round on the buffer system (wood boiler, 1000 l stratified tank, heat pump on the lower coil,
radiator and floor mixing circuits under a PLC, five room zones, the bathroom on both circuits).
- **The mixing circuit's target no longer drops in a TPI / PWM pause:** with no zone asking within `circuit_hold_s`
  the curve used the 20 °C fallback room (`circuit_room`), so the floor circuit fell from 29–30 °C to 26 °C between
  two pulses and the next pulse waited for the confirmation. Now the curve stays at the highest target of the
  circuit's zones (only the room correction of a demand goes); `circuit_room` is used only when no zone has a target.
  The circulation is the separate value it already was: the circuit's demand (the *circuit demand* `binary_sensor`; new
  `pump_enable` and `room_from` attributes on the target sensor, and two new rows on the info page). The PLC should
  stop the circuit's pump on it and move the mixing valve only while the pump runs (a pipe warmed by gravity then moves
  nothing). The heat pump coordination still counts only circuits with demand, so a kept target asks no heat. The
  old behaviour: switch off `circuit_idle_keep` (*Keep the zones' target in a pause*).
- **The plant joins one house by its pipes:** a buffer tank without zones joins the house of the circuits / heat pump
  coordinations it feeds, and a circuit or heat pump coordination still alone joins its tank's house (house rule 6,
  why "plant"). So the overview and the hydraulic diagram show the wood boiler, the tank, the heat pump on its coil,
  both circuits and every room as one system, from whichever instance it is opened; nothing has to be made again. The
  house link field is now on the buffer, mixing circuit and heat pump coordination settings too.
- **Source watch: no false *no data*:** an instance with neither a power reading nor a flame sensor (a zone on a
  valve relay, a source known only by its relay) gave `no_data` after ten minutes. Now it is `unwatched` (a quiet
  state, no warning); `no_data` means a reading that was set and got lost. The overview says the warnings in words
  ("source watch: the source's power / flame reading gives no data").

## 0.61.0 – 2026-11-16
The tester's last two points (5.2 and 5.7), and a fix of the 0.60.0 hydraulic diagram.
- **Buffer system setup path (HC setup panel → *Buffer system*):** the real system is described once – home name,
  whether a heat pump heats the tank through its coil, wood (none / a direct signal / the boiler's thermometer), the
  radiator and / or floor mixing circuit; then the devices (outdoor thermometer, the tank's up to four thermometers,
  an existing charge %, volume, base temperature; the heat pump's running signal and – for later – its ON/OFF and
  target; the wood signal or thermometer with its thresholds; the PLC setpoints of the circuits, optional); then the
  rooms, as many as needed, each with its thermometer and zone valve relay (or an existing HC zone) and the circuits it
  is on. A room on both circuits (a bathroom with radiator and floor) is **one** zone with one thermostat. The summary
  lists what will be made; *Create* makes every instance in order and links them: the room zones (TPI on their valves,
  heat source with its own control), the buffer tank (its zones: every room; no relay of its own), one mixing circuit
  per type with its rooms and the tank, the heat pump coordination on the tank. All start in shadow mode with the same
  home name, so HC info shows them as one house. New websocket `hc_thermostat/wizard/system` (admin only); nothing
  is switched or written.
- **Wood told from the wood boiler's thermometer (heat pump coordination, option):** `wood_temp_entity` with
  `wood_on_above` (65 °C), `wood_off_below` (60 °C) and `wood_confirm_s` (5 min): active once the boiler is at the
  upper threshold or warmer for the confirmation time, inactive once at the lower one or colder for as long; between
  them the last state holds; the first reading decides at once; no reading, or one older than an hour, is "not known".
  A direct wood signal (`wood_entity`) stays the first choice. The overview shows the thresholds and a pending change;
  the drawings show the wood boiler for it too. No helper or automation is needed for it any more.
- **Hydraulic diagram of a house without a buffer system:** 0.60.0 drew only tanks, circuits and heat pump
  coordinations, so an ordinary house (a gas boiler with its rooms, an air conditioner, an oil heater) got empty
  boxes. Now the plant room shows each water heating source (its kind, burning / idle, flow target), outdoors the
  air conditioners' and heat pumps' outdoor units and the outdoor temperature, and a column of rooms per source (its
  room list; a room it does not heat marked), the room units (air conditioner, heater) in a column of their own.

## 0.60.0 – 2026-11-16
Diagnosis of a whole house in one place (the same tester's points A, B and 5.3). Information only – nothing switches
differently.
- **HC info: three views of the house** – *Drawing* (as before), *Overview* and *Hydraulic diagram* – above the
  picture when the house has several instances (or for a circuit, buffer or heat pump coordination). The choice is
  remembered; a click on any part opens that instance's details on the right.
- **Overview, one page:** the outdoor temperature; every instance's control mode (shadow / supervised trial / active
  writing); warnings (faults, measurement problems, outputs in conflict / not accepted / unavailable / error, a heat
  pump "runs" reading that is not known, with its age); **why heat is asked for or not** in plain words (the heat
  pump's reason with the circuits' need and the tank top, wood, each circuit's lasting demand and the zones asking now);
  the heat sources (wood active / inactive, heat pump runs / stands / not known, its power reading and age, HC's ON/OFF
  request, heat demand, flow target, reason); the tank (each layer, the existing charge % kept apart from the stored
  heat worked out from the layers, the trend in °C/h); each mixing circuit (given-out flow target, worked out, by the
  curve, the PLC's target now, writing status, lasting demand, usable heat of the tank, a small curve); and every room
  (measured, target, asking, HC's command, the real relay – a difference is marked, expected in shadow mode – and its
  mode).
- **Hydraulic diagram from the links already set:** outdoors the heat pump on the tank's lower coil; the plant room
  with the wood boiler (when the coordination has a wood signal), the tank with its layers, charge and kWh, each mixing
  circuit as a mixing valve and pump with its flow target; then one column of rooms per circuit (a room on two circuits
  is in both, marked *on 2 circuits*), zones on no circuit in a *direct* column. No new setting: it is built from
  `hp_buffer`, `circuit_buffer`, the circuits' `zone_entities` and `wood_entity`.
- **Heating curve of a mixing circuit:** a graph in the circuit's info (new *Heating curve* section) – the curve at the
  room target, the curve corrected by the current room deficit, the limits, the outdoor temperature now with the
  worked-out point, the given-out target and the PLC's target.
- **Curve preview in the settings form:** the circuit's settings page shows a table of the flow target at −15…+15 °C
  and now, at the room target and with 1 °C room deficit, within the limits. Tick *Preview only* and submit to
  recompute it with the values entered – nothing is saved until it is submitted without the tick.

## 0.59.0 – 2026-11-16
Findings of a tester on a buffer system (wood boiler and a monoblock heat pump on the tank's coil, 1000 l tank with four
thermometers, a radiator and a floor mixing circuit run by a PLC, five room zones – the bathroom on both circuits). The
drawing and the texts change; the decisions stay as they were unless the new option is turned on.
- **No phantom room from a mixing circuit:** a circuit, a buffer tank and a heat pump coordination in a house are parts
  of the plant room, not rooms. The extra "Room 33 °C" was a circuit's flow target; each circuit now shows in the plant
  room as a mixing valve with its name and flow target (radiator grey, floor purple), the tank as its layers with
  their temperatures, the charge % and the stored kWh.
- **Room zones are not heat sources:** a zone instance (role zone, or a heat source with its own control) no longer
  adds an *External heat source* box per room. The heat pump coordination brings the real ones: the heat pump's
  outdoor unit (with its power) piped to the tank's coil, and – when its wood signal is set – a **wood boiler** with
  its fire door and flame while it fires.
- **Rooms named by their instance:** a zone named "HC Mosókonyha" is the Mosókonyha, even when its thermometer's name
  contains "konyha" (an area named exactly like the instance wins; the area of the thermometer only when the title
  contains its name).
- **One bathroom, radiator and floor:** a zone listed in a radiator and a floor circuit is one room with both emitters
  (the floor loop on its own circuit), one thermometer and one thermostat.
- **The zone's water:** a zone in mixing circuits shows the circuits' given-out flow targets (*Mixing circuit flow
  target*, e.g. "Radiator circuit: 33 °C; Floor circuit: 29 °C") instead of its own flow request (48 °C), which is
  not what its water gets.
- **Low charge only with a room demand (option, off):** heat pump coordination → `hp_charge_needs_demand`. On: the
  charge percentages (`hp_charge_on` / `hp_charge_off`) start and keep a heating only while a circuit / zone has a
  lasting demand; with no demand a low charge starts nothing (`low_charge_waits` in the details) and a running heating
  stops on the temperatures alone. Frost protection and the cold-weather ON are unchanged. Off: as before.
- **A stale "runs" reading is not trusted:** a power / current / speed reading that says "runs" but has not been
  reported for 15 minutes is "not known" (a meter stuck at 1.5 kW no longer keeps the heat pump running and wood
  impossible); a stale low reading stays "does not run". The reading's age is in the details (`hp_running_age_s`).
- **Setup texts:** the relay field reads *Switched relay (the boiler, or for a zone its zone valve / room relay)*; the
  buffer tank's heat source relay is optional – empty, HC only watches the tank (no virtual switch needed for a shadow
  trial or a tank charged by a heat pump coordination).
- Tip from the same review, already possible: the house's title is the host's *Home name* (settings), not its instance
  name.

## 0.58.0 – 2026-11-16
Each heating system drawn the way it is built (house view; only the drawing changes, no decision does).
- **District heating is a flat in a block of flats:** no roof, garden, sun or ground – the flats above and below with
  their windows, a neighbour block in the gap, the title on a plate, the building's flow / return risers in the outer
  wall. New option `district_connection` (settings → devices, district heating only; only the drawing uses it):
  `station` (default) – a flat station with a plate heat exchanger and the heat meter on top, fed from the risers;
  `direct` – radiators straight on the risers: shut-off valves and the flat's heat meter (with today's kWh) in the
  hall with the entrance door, a heat cost allocator on every radiator, no pump or expansion tank.
- **Pellet boiler:** red body with its fire door (the flame inside), the pellet store beside it with its level
  (`fuel_level_entity`, %) and the feed screw.
- **Heat pump / any water system with floor loops:** the floor heating manifold (flow and return bars with their
  loop valves) in the plant room when there is room; the buffer tank as before.
- **Electric floor heating** (electric heater on a floor system): the rooms get heating cables laid in a spiral in the
  floor (new emitter `efloor`), fed from a small electrical room with the distribution board and the floor thermostat,
  one cable per room; the plant label reads *Electric floor heating*.
- **Storage heaters:** a storage heater cabinet (outlet grille, warm air rising) in every room of the instance, wired
  from the board and the meter of the controlled tariff (phase and neutral).
- The flow / return pills also use the measured `flow_temp_entity` / `return_temp_entity` when the decision has none.

## 0.57.1 – 2026-11-15
Fixes from an outside review of 0.57.0, in the parts that write to a device – before anything is written live.
- **Heat pump running signal by its unit:** a number counts as "runs" only with a unit HC understands – W > 100,
  kW > 0.1, A > 0.5, Hz / rpm / % > 0. Until now every number was taken as watts, so a kW, A or Hz sensor said
  "stands" while the unit heated, its own heat looked like wood, and wood first stopped it. A number with no or an
  unknown unit is now "not known": wood is then at most "possible", which changes nothing.
- **Climate target on its own step and limits:** a climate output (`circuit_output_entity`, `hp_target_entity`) gets
  its target rounded to the entity's `target_temp_step` (0.5 °C / 1 °F when it has none) and kept within `min_temp` /
  `max_temp`, and HC compares with that value. Before, it wrote half degrees unclamped: a device on whole degrees never
  confirmed it and the output ended *not accepted* after four writes.
- **A device restart is not a second writer:** when an output was unavailable and comes back with another value (a PLC
  or heat pump starting with its default), HC writes its value again instead of calling it a conflict for good. A
  device that restarts without ever being unavailable in Home Assistant still counts as another writer.
- **ON never switches to cooling:** an ON request to a climate picks heat, else heat_cool, else auto; a climate with
  none of them is not switched (an error is shown) – before, it took the first mode in the list, which could be cool.
- **Summer mode without a circuit:** the buffer's own zones (no circuit linked) keep their demand for 30 min like a
  circuit, so TPI pauses no longer restart the 30 minutes and the summer mode ends on a lasting demand.
- **House view: power above the outdoor unit:** a heat pump's and an air conditioner's outdoor unit shows the electrical
  power it draws now (`boiler_power_entity`, W or kW) above it; several ACs on one side add up. The heat pump's power
  left the plant room's label, where it stood until now.

## 0.57.0 – 2026-11-15
Automatic summer / winter mode for the heat pump coordination – from the house's own demand, not from a date
(suggested by the reference design's owner: there it is how the PLC already switches).
- **Summer mode** (`hp_auto_summer`, off by default; heat pump coordination → settings): after `hp_summer_after_h`
  (24 h) with no circuit / zone demand at all, the coordination goes into summer mode. Only the rooms count: a low
  tank does not keep winter. In summer mode the tank is not kept warm – no low-charge start, no standby ON, a running
  heating stops, the target goes to the lowest. The buffer frost limit still heats; the cold-weather ON stays
  separate and keeps the unit ON with no heating command; the unit's own frost protection stays first. With it on,
  summer mode replaces the 24 h no-demand stop.
- **Back to winter by itself** when the circuits' demand lasted `hp_winter_after_s` (30 min; 0 = at once) without a
  break **and** a room still asks at its end: one TPI pulse (which keeps a circuit's lasting demand for 30 min) or a
  short dip after airing does not end the summer.
- **Signals for a PLC:** binary sensors *Summer mode* (since when, hours without room demand, how long the demand has
  held) and *Exercise due*; both can also be written to a switch / input_boolean (`hp_summer_entity`,
  `hp_exercise_entity`, same writing modes and one-writer rule as the other outputs).
- **Exercise due** (`hp_exercise`, off): in summer mode, every week on `hp_exercise_weekday` (0 = Monday) from
  `hp_exercise_hour` for `hp_exercise_min` (10) minutes. HC only signals – the PLC runs its pumps, mixing valves and
  actuators.
- The info panel shows the summer / winter state, the hours without room demand, the return countdown and the
  exercise signal. The state survives a restart.

## 0.56.1 – 2026-11-15
Two fixes from the reference design's review, before the heat pump is written live.
- **Wood first, for real** (`hp_wood_first`, on by default, heat pump coordination → settings): with wood `certain`
  (the wood signal on) or `likely` (the tank warms fast while the heat pump is known to stand) the heat pump does not
  heat – not even for a low charge (`hp_charge_on`), and a heating that already runs stops. Until now a low charge and
  a running heating went before wood, and wood only held back a new start. Only the buffer frost limit goes before
  wood; the cold-weather ON and a fail-safe ON still keep the unit ON, with the target at the lowest (no heating
  command). Off: the 0.55.0 order.
- **Confirmation wait for a written target** (`write_confirm_s`, 60 s, both writing roles → first options page): a
  slow cloud device (e.g. Tuya) may report the written value late or first echo the old one. Until the value there is
  HC's own, or the wait is over, HC neither writes again nor calls it someone else's (*waiting for the device to
  confirm*). A value that never comes back as HC's (no echo, refused, rounded by the device) is written again at most
  3 times in a row; then *not accepted*: HC stops writing that value, a notification says so, and it writes again
  when the value it wants changes or the device shows HC's value after all. Once confirmed, a later change is someone
  else's after 5 s, as before. Until now an unconfirmed value was written again every 30 s with no limit.
- The 24 h no-demand stop is unchanged and now described exactly: it applies with *keep ON with no demand* (without
  it the request is already OFF whenever there is no demand), and "no demand" means neither a lasting circuit / zone
  demand nor a heat demand of the tank.

## 0.56.0 – 2026-11-15
Writing: a mixing circuit's flow target to the PLC, the heat pump's flow target, ON/OFF and heat demand – after a
supervised trial, with one writer per target.
- **Writing modes** for the *mixing circuit* and the *heat pump coordination* roles (options, first page): *shadow*
  (works out and shows, writes nothing – the default and where every new instance starts), *supervised trial* (writes
  for `trial_hours`, 4 h by default, then goes back to shadow by itself, with a notification) and *active* (writes
  permanently). Writing needs an output entity and a confirmation.
- **Outputs:** a circuit writes its given-out target to `circuit_output_entity` (a PLC number / input_number, or a
  climate's target); the heat pump coordination writes its target to `hp_target_entity` (number / input_number /
  climate), then the ON/OFF request to `hp_switch_entity` (switch / input_boolean / a climate's hvac mode), then an
  optional heat demand signal to `hp_demand_entity`. Only setpoints and ON/OFF: the PLC keeps its mixers, pumps and
  safety, the unit its own frost protection. Values are clamped to the output's own min / max and stepped; °F numbers
  get °F.
- **One writer per target** (`core/output_guard.py`, `output_writer.py`): HC writes only when the value there differs
  from what it wants. A value changed by someone else (the PLC, a person, an automation) more than 5 s after HC's write
  is a **conflict**: HC stops writing that target, a notification says so, and it writes again only once the value is
  HC's again. HC never fights another writer.
- **No write in the first 2 minutes after a start** (the inputs settle; no stale value goes out); a lost output or no
  value writes nothing; a failed write is logged and shown, the next decision goes on.
- **Keep-alive** (`write_keepalive_s`, 0 = off): an unchanged value is re-sent this often, for a PLC that drops a
  setpoint after a timeout.
- **Writing paused** switch on both roles (kept over restarts): HC keeps working out and showing, writes nothing.
- The writing state, the trial's end and each output's state (last value, conflict, error) are in the attributes and
  in HC info.
- Tests: tests/test_write_560.py (13).

## 0.55.0 – 2026-11-15
Heat pump coordination for a buffer tank – shadow only (nothing is switched or written).
- **New role `hp_coord`** (*Heat pump coordination for a buffer*, `core/hp_coord.py`): for a heat pump charging a
  buffer tank (through its coil or directly), beside another source such as a wood boiler. It reads the linked buffer
  instance (its stratified stock, trend and mixing circuits), the outdoor thermometer and optionally whether the heat
  pump runs now and a wood boiler signal, and works out three separate things:
  - **heat demand** – the highest given-out target of the circuits with a lasting demand + their margin is the need;
    heating starts when the tank top is below it (or the charge is at or below `hp_charge_on` %, or the top is at the
    buffer's frost limit) and runs until the top is `hp_hyst` (3 °C) above it and, when set, the charge reached
    `hp_charge_off` %;
  - **the ON/OFF request** – a request, not a confirmation; minimum ON / OFF times (30 / 15 min);
  - **the flow target** – need + coil reserve (`hp_reserve`, 5 °C) + the manual offset (−8…+8 °C, the new number entity
    *Heat pump offset*, kept over restarts), within `hp_flow_min`–`hp_flow_max` after the offset; the lowest with no
    heat demand (ON is not a heating command); given out through the same hold as the circuits (2 °C, 10 min, 45 min,
    a rise at most 3 °C at a time, urgent 6 °C).
- **Wood first:** with a wood signal on (`certain`), or the tank warming by `hp_wood_rise` (2 °C/h) while the heat pump
  is known not to run (`likely`), no new heating starts; a warming tank with no running signal is only shown
  (`possible`) – HC does not claim what it cannot know. A tank warm enough makes no demand anyway.
- **Cold-weather ON** (`hp_cold_on`, off by default – a water-filled monoblock only): below +5 °C the request is ON even
  with no demand and while wood heats; released only after a lasting +7 °C (1 h); a lost outdoor reading gives a
  fail-safe ON. It never replaces the unit's own frost protection.
- **Long no-demand stop:** with *keep ON with no demand* (`hp_standby`), the request goes OFF after `hp_idle_hours`
  (24 h) without circuit or heat demand – unless the cold-weather ON holds: it wins, and the decision says so
  (`idle_overridden`).
- **Lost inputs:** no outdoor or tank reading – the last request stays (no random switching).
- Entities: *Heat pump decision* (the reason), *Heat pump ON request*, *Heat pump heat demand*, *Heat pump flow target*
  (given out; raw, hold, need, reserve, offset as attributes), *Heat pump flow target (raw)*, *Heat pump offset*
  (number). HC info: a heat pump coordination drawing with the decision, the target parts, wood, the cold-weather ON
  and the inputs.
- Tests: tests/test_hp_coord_550.py (18), with the reference design's acceptance cases.

## 0.54.0 – 2026-11-15
A stratified buffer tank and mixing circuits fed from it – shadow only, information only (nothing new is switched or
written). The first step towards several heat sources on one buffer with separately controlled circuits.
- **Stratified buffer** (`core/stratified.py`): up to four tank thermometers – top, upper middle (new), lower middle
  (new), bottom – each with its share of the volume (`buffer_share_*`, 0 = even), the tank volume (`buffer_volume_l`)
  and a base temperature (`buffer_base_temp`, 25 °C). New entities on the buffer instance: *Buffer charge* (%) – an
  existing charge sensor of the tank (`buffer_charge_entity`) is taken over unchanged, else worked out from the
  layers, the `method` attribute says which –, *Buffer stored heat* (kWh above the base, with a volume; 1 m³ · 1 K ≈
  1.163 kWh) and *Buffer trend* (charging / emptying / steady over half an hour, °C/h and kWh/h). A thermometer with no
  fresh reading takes its neighbour's value, marked as estimated. The charging decision is unchanged (top and bottom).
- **Mixing circuit role** (new role `circuit`, shadow only): a radiator or floor circuit with its own pump and mixing
  valve, fed from a buffer. Its rooms stay ordinary HC zones on their valves; the circuit reads them and the outdoor
  thermometer and works out the flow target: the curve at the highest target of the zones with a *lasting* demand
  (asked within `circuit_hold_s`, 30 min – a TPI pause does not drop it) plus a room correction for the largest
  deficit, within its own limits (radiators 30–55 °C, slope 1.2; floor 22–36 °C, slope 0.5 – all settable; the floor's
  maximum is the water's limit, not the floor surface limit, which stays with the hydraulics / PLC).
- **The given-out target changes only now and then** (`core/setpoint_hold.py`): a new target only for a difference of
  at least `circuit_deadband` (1.5 °C) that lasted `circuit_confirm_s` (10 min), at least `circuit_min_interval_s`
  (25 min) after the last change, a rise at most `circuit_max_rise` (3 °C) at a time, lowering unlimited; a lowered
  limit applies at once; an urgent difference (`circuit_urgent`, 5 °C) that lasted 2 minutes skips the wait (not the
  rise limit). No outdoor reading: the target stays. Over a restart the given-out target and its time are kept (not
  after 6 hours down). Entities: *Circuit flow target* (given out; the raw target, the reason it is held, the next
  allowed change, the curve and the correction as attributes), *Circuit flow target (raw)*, *Circuit lasting demand*.
- **What the tank can give a circuit:** with a buffer instance linked (`circuit_buffer`), the circuit shows whether the
  top is warm enough (target + `circuit_margin`, 2 °C) and the usable heat (the layers warm enough, down to the
  circuit's return); the buffer lists its circuits. An estimate from four points, more so while the tank charges.
- **HC info:** the buffer drawing shows the layers, the stored heat, the charge with its method, the trend and the
  circuits; a new circuit drawing shows the given-out and the raw target, why a change is held back, the limits and the
  zones.
- Nothing is written: the circuit has no output entity yet (writing to a PLC number comes after a supervised trial).
  Tests: tests/test_circuit_540.py.

## 0.53.0 – 2026-11-15
One house, several heat sources.
- **One house in HC info** (`core/house.py`): instances of the same building show as one house – automatically a
  one-room instance (AC, heater) in the area of a room or the adjoining room of an instance with more rooms (not its
  leading room), instances with the same home name, a central boiler / buffer where most of its zones are; or by hand:
  the new setting `house_link` (*Adjoining room, shared house* → *Part of which house*: automatic, its own, or
  another instance's house). `info_list` / `info` give `house`, `house_area`, `house_room`, `house_members`.
- **The house drawing** takes the members in: their rooms, the AC / heater in the room it heats (with target, setpoint
  and the unit's reading), a member's device next to the host's own emitter, every water-heating source side by side
  in the plant room, outdoor units stacked; a click on a member's part opens it. The picker lists members under their
  house; a member's page shows the whole house; a *Heat sources in the house* section lists them all.
- **Measured-only rooms:** a room may be marked *No heater of this heat source – measured only* (options → Rooms, and
  the wizard): drawn with its reading, no target, no climate, no radiator valve advice, no TRV heads. The leading
  room is always heated.
- Narrow drawings: an AC's setpoint label moves under the thermostat when it would cover the room's name.
- Display only – no decision changes. Tests: tests/test_house_530.py (15) and one in test_rooms_430.py.

## 0.52.1 – 2026-11-15
The defaults checked on two more house types.
- **Simulator** (`tests/sim.py`): three house types – the radiator house HC was developed on, a heavy house on a
  floor slab (τ 100 h, the screed following in ~6 h, a heat pump) and a light, fast house (τ 12 h, convectors /
  fan coils) – and a thermometer resolution (`Run(resolution=0.1)`).
- **Fix – the frozen-thermometer check on floors:** on the slab a regulated room showed one 0.1 °C value for up to
  17 h while the source ran, and the check took a working thermometer for lost for a third of the time; warming up
  at full power in the cold, one value far below the target held up to 5.3 h. Floors now wait 8 h
  (`frozen_after_h`) and do not judge a value within 1 °C of the target (new `frozen_band`); a thermometer stuck
  further away is still found.
- **Floors hold 2 h before a lowering** (`pre_change_s` 7200, was 1800): the screed gives the last hours' heat after
  the change; in the simulator the last hour had no run any more and the room was only 0.11 °C cooler at the change.
- **The hold before a lowering never sags more than `pre_change_sag`** when τ is known, also within `pre_change_s`
  (from the target, or from the room when it is already below it): a light house lost ~0.8 °C in the 30 minutes.
- The floor defaults are source defaults (a value set by hand wins) and the settings form shows them.
- The radiator house (and so a radiator instance) behaves as in 0.52.0. Also seen: TPI's outdoor term
  (`tpi_coef_ext` 0.01) fits a high-power boiler; on the slab and the light house TPI stays 0.3–0.6 °C under the
  target, PID holds it – PID is the better choice there.
- Tests: tests/test_house_types_521.py (40).

## 0.52.0 – 2026-11-15
Fewer guesses that only fit one house.
- **Presence values to choose** (`core/states.py`): for an `input_select` / `sensor` presence source the settings
  (*Functions*) offer its own values – which mean home (`presence_home_states`) and which vacation
  (`presence_vacation_states`); they count besides the built-in words. Before, every value other than `home` / `on`
  / `otthon` / `vacation` / `szabadság` was silently away (an input_select with "Itthon" was always away). Until
  something is chosen, an unknown value is logged once as a warning.
- **Heat pump busy values** (`hp_busy_states`, *Devices*): the same for a defrost / hot-water mode sensor.
- **Heating season limits** on the settings (*Functions*): `season_off_above` (15 °C) and `season_on_below` (13 °C);
  the start must be below the end.
- **Lowest believable room temperature** on the settings (*Protection*, `plaus_indoor_min`, 3 °C), never above the
  frost target minus 2 °C (checked in the form and applied in the regulation), so a really cold room is believed.
- **Natural gas heating value** (`gas_heating_value`, *Energy* and the first setup, 9.61 kWh/m³): visible and
  changeable, used with the automatic fuel too (before, a fixed Hungarian value).
- The energy rating's description says it is the Hungarian scale (indicative elsewhere); README: a *What has been
  tested* table per heat source (live / test instance / simulator only) and a *Limits you can set* section.
- Nothing changes for an existing instance until the new fields are set (all defaults are the old behaviour).
- Tests: tests/test_choices_520.py (11).

## 0.51.2 – 2026-11-15
The energy rating's year.
- **Its own outdoor sensor** (`rating_outdoor_entity`, *House model*; empty = the outdoor sensor): the year of
  daily means can come from an outdoor sensor or group with a longer history than the one HC regulates on.
- **Missing days are filled** (`energy_rating.year_of`): the 365 days before today, measured where there is a daily
  mean, else the standard climate's monthly mean. `climate` is `measured` (≥ 300 measured days), `mixed` or
  `standard`; new attribute `measured_days`; the info panel says how many days were measured.
- Tests: tests/test_rating_climate_512.py (5).

## 0.51.1 – 2026-11-15
Lessons from Better Thermostat 2.0 and Smart Thermostat 2026.11.
- **A renamed entity is followed** (`rename.py`): when an entity in the settings (thermometer, window, head, relay,
  meter …) is renamed in the entity registry, its id is replaced in the entry's data and options and the instance
  reloads – before, the old id stayed and the sensor counted as lost.
- **`nan` / `inf` is no reading** (`units.finite`, also in `to_c`): such a state passed `float()` and every comparison
  with it was false.
- **Repairs entry for a lasting problem**: what the fault sensor lists (`sensor_problems`, after
  `sensor_problem_after_s`) is also a warning in Home Assistant's Repairs, which clears itself when the problem is
  gone (and with the instance). New attribute `degraded_since` on the fault and decision sensors.
- The PID integral over a short off (heat → off → heat, a window) was already kept (the regulator is only held); a
  test now pins it.
- The *Supervision paused* switch implements `async_entity_id_changed` (HA 2026.11): its own entity id is changed
  in place on a rename instead of the entity being removed and added again (nothing in it is keyed on the id).
- Tests: tests/test_fixes_511.py (8).

## 0.51.0 – 2026-11-14
An estimate of the energy rating.
- **Energy rating (estimate)** (`core/energy_rating.py`, new sensor and a row in the HC info panel's *House model*):
  the building's grade on the Hungarian 9/2023. (V. 25.) ÉKM scale (A+++ 0 · A++ 38 · A+ 68 · A 76 · B 98.8 · C 122 ·
  D 152 · E 190 · F 236 · G 296 · H 380 · I above, kWh/m²·year; "A" = 100 %), from the learned house model: the
  useful heat of a year at 20 °C (Σ days 24 h × max(0, H × (20 − outdoor) − free heat), the outdoor sensor's daily
  means of the last year from the statistics, or a standard Hungarian year when it has fewer than 300 days), ÷ the
  burner's efficiency / ÷ the mean COP of a heat pump or AC / as is for electric and district heat, + hot water and
  auxiliary electricity, × the non-renewable primary factor (natural gas and other fossil fuels 1.1, electricity 2.3,
  district heat 1.38, solid biomass 0.6), ÷ the floor area. The band is the loss factor ± 15 %. Not a certificate.
- New settings in *House model*: `house_area_m2` (0 = off), `dhw_kwh_year`, `aux_kwh_year`, `primary_factor`
  (0 = by the heat source). Sensor attributes: `ep_kwh_m2`, `percent_of_a`, `ep_low`, `ep_high`, `grade_low`,
  `grade_high`, `heat_kwh_year`, `final_kwh_year`, `primary_factor`, `climate`, `area_m2`.
- Tests: tests/test_energy_rating_510.py (6).

## 0.50.0 – 2026-11-14
The house model: loss factor, free heat and time constant, and what uses them.
- **Loss factor from a line** (`core/heat_need.py`): daily heat against the mean indoor − outdoor difference; slope =
  H, intercept = free heat; need = H × (target − outdoor) − free heat (the blind demand, the feed-forward, the shadow
  regulator, the cost advice). At least 10 days 4 K apart, r ≥ 0.7 and a free heat of 0 or more (a negative one is hot water in the meter or a poor line); else the plain ratio as before. Sensor
  attributes `source`, `free_heat_kw`, `balance_point`, `fit_w_k`, `fit_free_heat_kw`, `fit_r`, `ratio_w_k`,
  `manual_w_k`, `since`.
- **Time constant τ** (`core/thermal.py`, new sensor *Time constant (τ)*): learned from stretches of ≥ 3 h without a
  burn (from 60 min after the last one; window closed, no other source counted), τ = hours / ln(ΔT0 / ΔT1) against the
  equilibrium outdoor + free heat / H; median of the last 21. Attributes: source, stretches, capacity (τ × H).
- **Hand-given values** `house_loss_w_k`, `house_gains_kw`, `house_tau_h` (new settings section *House model*); the
  learned values are blended in (H: 14 days, τ: 5 stretches). New button **Learn the house model again**
  (`heat_need.since`: the statistics before it are not seeded again).
- **Optimal start** (`optimal_start`, `optimal_start_max_min` 120, `optimal_start_lag_min` 20; off by default): the
  day target starts before the night end so that the room reaches it in time; held until the night end, restored
  after a restart; details `optimal_start`, decision text.
- **Forecast hold before a lowering:** with τ, up to `pre_change_max_s` (7200 s) while the predicted room stays at or
  above the coming target and within `pre_change_sag` (0.5 °C) of the current one; details `pre_change.predicted`.
- **Mould risk at the coldest surface** (`core/measures.surface`): surface temperature = outdoor + `mould_frsi` ×
  (indoor − outdoor) (EN ISO 13788, default 0.7), the humidity the room's vapour gives there, and the highest room
  humidity that keeps it under 80 %. Risk: high after 6 hours of 80 % at the surface in the last day (or 90 % now),
  moderate after any such hour (or 70 % now), low otherwise; without an outdoor reading by the room's own humidity as
  before. Mould risk sensors: `surface_temp`, `surface_rh`, `rh_limit`, `frsi`.
- **Humidity sensors from the thermometers:** once per instance (`humidity_auto`) every room without one gets the
  humidity sensors on its thermometers' devices (the leading room: the house thermometer's too) – written into the
  settings like the rooms form does; an instance without rooms gets `humidity_entity`. The rooms form ticks them for a
  room without one.
- **HC info panel:** new *House model* section (loss factor and its source, free heat, balance point, fitted line, τ,
  heat stored per degree, optimal start, the hold before a lowering, fRsi); the humidity rows show the coldest surface
  and the mould-free limit.
- Numbers of a real gas-heated house: before a wall insulation 163 W/K and 0.7 kW free heat (the ratio
  said 125 W/K), after it about 100 W/K; τ about 90 h.
- Tests: tests/test_house_model_500.py (22); test_fixes_400 and test_setup_490 follow the new model and section.

## 0.49.0 – 2026-11-13
A simpler setup.
- **Devices step of the manual setup:** on top only what a first setup needs (room thermometer or wall thermostat
  contact, what HC switches or sets, outdoor thermometer, windows, presence); the rest folds out under *More
  (optional)*. A field still to be filled (an electric floor's sensor) stays on top.
- **Pre-filled pickers** in the manual setup (`rooms_ha.suggest_entities`): the outdoor thermometer (named or placed
  outside, else a weather entity), the living room's thermometer or the only plausible one, every person for
  presence, the only gas meter (gas boilers). Never a relay or a thermostat.
- **Settings in fold-out sections:** the mode, the targets and the night on top; *Control and timing*, *Features*,
  *Protections*, *Floor*, *Heat source signals and power*, *Energy and cost*, *Adjoining room* and *Measurements*
  fold out. Stored on one level as before; an error of a field inside a section is shown above the form.
- **Change the control** (new options menu item): another control (e.g. a relay instance to an external thermostat)
  without a new instance – the matrix's list, then what the new control drives (pre-filled with the current
  entities). Saved in shadow mode, every other setting stays; a curve gets its default curve; refused while rooms are
  set and the new control is not TPI / PID.
- **Energy factor from a fuel:** `heat_fuel` (auto, natural gas m³, LPG kg, heating oil l, pellet kg, electricity kWh,
  custom) and `heat_efficiency` (%, default 90) work `energy_factor` out (`core/fuel.py`); auto reads the meter's unit
  (m³, Wh/kWh/MWh, MJ, GJ; no efficiency for a heat meter or electric heat), without a meter the heat source; a heat
  pump keeps the typed number. An instance saved before keeps its number ("custom").
- Tests: tests/test_setup_490.py (11); four tests follow the new structure (sections, menu).

## 0.48.3 – 2026-11-13
- **Decision chain on GitHub:** `DECISION_CHAIN.md` (English) and `DECISION_CHAIN.hu.md` (Hungarian) – one heating step
  on three levels (heat source → execution → emitter and room) as Mermaid diagrams, the one-step decision order, a
  fold-out part per heat source (what HC reads and switches, the optional measurements, what it works out, the
  controls with the recommended one first, the starting timing per emitter) and per emitter, and the heat source ×
  emitter matrix. Generated from the code by `tools/decision_chain.py`; a test fails when they are out of date.
  Linked from both READMEs.
- **No new start before the target goes down** (TPI, PID, on-off): within `pre_change_s` (default 1800 s, 0 = off)
  of a scheduled lowering of the target – night start, a preset or a manual target running out – no new burn starts
  while the room is already at or above the coming target; its heat would only arrive after the change. A boost does
  not start either; a running burn is not cut; the integral does not grow meanwhile. Shown as `limited_by:
  pre_change` with the time and the coming target. (11-12: a burn at 21:59:41 at 22.4 °C for a 22:00 night of
  21 °C ran its 5-min minimum and took the room to 22.6 °C – one start more than needed.)
- Tests: tests/test_decision_chain_483.py (3), tests/test_pre_change_483.py (10).

## 0.48.2 – 2026-11-13
The boost by the outdoor temperature (a morning boost at 14 °C overshot 0.3 °C: the warm band had nothing learned).
- **Nearest learned band:** a band without its own lesson takes the nearest learned one (before: the defaults).
- **Outdoor correction:** every 10 °C warmer outside a boost needs 20 % less burning and its after-heat lifts the
  house 20 % more (bounded to 0.7–1.4), against the outdoor temperature each band was learned at (`outdoor_ref`; a
  band learned before takes its centre: −5 / 5 / 15 °C). A lesson is brought to its band's reference before it is
  kept. Simulation (four boosts at 5 °C, then one at 12 / 14 / 16 °C): overshoot 0.28 / 0.32 / 0.36 → −0.04 /
  −0.06 / −0.08 °C (it stops just below, the regulation takes over).
- **The lesson is no longer lost:** the after-heat watch also runs while the house is above the target (before it
  waited for the regulation to come back), and the boost record is saved – a restart in the after-heat kept nothing
  of it (this morning's restart at 07:09).
- Tests: tests/test_boost_482.py (6).

## 0.48.1 – 2026-11-13
From an outside review of 0.47.0–0.48.0 (with a measured PWM simulation).
- **Valve delay PWM:** a full cycle only when the useful demand itself reaches the cycle minus the minimum pause;
  below it the run is the useful time + the delay, capped at that limit, and the useful seconds the cap cut off are
  carried on. Before, the delay was added first: with a 15-minute cycle and a 10-minute delay only 17 % or 97 %
  existed, and with 30 / 5 minutes a 70 % demand ran without a break. Now (30 / 5): 20 / 30 / 40 / 60 / 70 % give the
  same share of useful heat. A relay still on at a new cycle does not wait for the delay again.
- **A cycle too short for the delay** is refused in the setup's basics and the options (at least delay + minimum on
  + minimum off); the wizard lengthens it to 1.5 × that, in whole 5 minutes.
- **Small demands without a delay** (`pwm_carry`, new option, off by default): demands below the minimum run add up
  to a real run. Off because the simulation showed more overshoot after a boost with it (the after-heat learning).
  With a valve delay they are always collected.
- **Failsafe right after a start:** when the decision fails from the first step (no earlier decision), the heat is
  switched off after three failures too (before: the error was only raised, the relay stayed as it was).
- **Cold radiator:** the minutes of heating are added up over the PWM pauses (before every pause started the count
  again, so the 20-minute limit was reached only in a boost); it starts again when the radiator got warm or the room
  needs no more heat. "Warm" follows the flow when it is measured; lower for a heat pump.
- **Fault codes:** all zeros after a letter prefix ("00", "F.00", "0x00") are no fault; own "no fault" values in the
  measurements (`fault_ok_values`). **Pressure** in hPa is converted.
- **CI:** the hassfest and HACS actions pinned to a commit.
- Tests: tests/test_review_481.py (15); 0.47.0 tests use a cycle that holds the delay.

## 0.48.0 – 2026-11-13
Measurements: optional readings of the heat source and the rooms, shown in the HC info panel (a new *Measurements*
part, and per room), a few worked-out values as sensors, and their limits on the boiler problem sensor. None of them
changes a heating decision.
- **Options → Settings → Measurements** (a fold-out part, only the fields of the instance's heat source): water
  pressure (bar; psi / kPa / mbar converted), real flow and return temperature (water sources; district heating keeps
  its return field), modulation / compressor %, fault code, heat given off (heat meter – the COP), flue gas
  temperature and fuel level (pellet), core temperature (storage heater), the heat source's state (heat source with
  its own control), the hot water signal for combi boilers too (it pauses the fault watch, as a heat pump's did), a
  humidity sensor (any instance; floor cooling keeps its own field), and the limits: low / high pressure (1.0 / 2.5
  bar), little fuel (15 %), too many starts an hour (6; 0 = not watched), cold radiator after minutes (20).
- **Worked out:** starts and run time per local day (from the real heating signal; the week and the season from
  1 September), COP from the daily increase of the heat meter and the energy meter (today, 7 days, season – a meter
  that resets is not counted), ΔT, per room radiator surface (warm, cold while the room is below its target and the
  heat source runs, or idle), dew point and a mould risk from the hours of high humidity of the last day.
- **Sensors:** Starts today, Run time today (relay / flame / reference instances), COP today (with a heat meter and
  an energy meter), ΔT (flow and return), Mould risk (the instance's humidity sensor; per room on the room's device).
  Passed-on readings (pressure, modulation…) get no entity of their own – they have one already.
- **Boiler problem sensor:** also on for low / high pressure, little fuel, too many starts, a fault code or a radiator
  cold for longer than the limit (`measurements` attribute); an instance with measurements gets it even without a
  burner of its own (external / AC control, heat source with its own control).
- **Rooms form:** per room *Radiator thermometer* and *Humidity* check boxes (the area's thermometers named radiator /
  fűtőtest first – they were never offered as room thermometers – then its other thermometers; its humidity sensors);
  a sensor cannot be the room's thermometer and its radiator thermometer at once.
- **Heat energy:** the wizard turns a heat meter in GJ / MJ / MWh / kWh on district heating into kWh without a boiler
  efficiency (before: kWh × 0.9, GJ unknown); GJ for other sources too.
- Tests: tests/test_measures_480.py (14).

## 0.47.0 – 2026-11-12
From an outside tester's first try on their own system (heat pump and pumps run by a PLC, rooms on thermoelectric
valves through relays; points 2–5 – point 6 came in 0.46.0).
- **Heat source with its own control** (`external_heat`, "zone valve only"): HC only switches the room's zone valve,
  TPI / PID + PWM, 30-minute cycle (floor: 60); no flame, boiler power, power levels, boiler output, boiler health or
  boiler problem entities. Before, such a system had to pretend to be district heating.
- **Useful heat delay** (`valve_delay_s`, 0 = off, as before): every run is lengthened by it (slow valve + late pump),
  `min_on_s` counts the useful part, and a demand too small for a useful run is carried into the next cycles
  (`carry_s` in the PWM state, survives a restart; cleared by a run or by no demand). Simulation (PID, 15-minute cycle,
  10-minute dead time, 24 h, 5 / 12 °C outside): runs that ended before any heat 25 / 37 → 0, mean deviation 0.10 /
  0.12 → 0.04 / 0.06 °C. In the wizard's derived settings with its reason, in the setup's basics and in the options.
- **Add integration:** a first menu – the setup wizard (recommended; its panel and commands are set up at once, so it
  works before the first instance, and the flow ends with a link to it) or the manual setup.
- **Basic settings at the first setup:** after the devices, the manual setup asks the targets (home, night, away), the
  night window and – for a relay – the cycle, the minimum on / off time and the useful heat delay (before only in the
  options or the wizard).
- Wizard, HC info, house drawing: the new heat source's name and icon; no boiler power picker for it.
- **Failsafe over the whole step** (a review of the same evening): reading the inputs now counts for the failsafe as
  the decision does (three failures in a row switch the heat off); the side steps (decision log, cost advice, boiler
  health, room advice, TRV heads) run each on their own – a failing one is logged once, shown on the fault sensor
  (`hc_step:<name>`) and no longer keeps the decision from the relay.
- **Executor parts on their own:** the cooling switch, the discharge fan, the fan coil's fan and the relay / flow /
  managed thermostat are applied separately – a failing fan no longer takes the relay write of the same step with it;
  the failed part is shown on the fault sensor (`hc_executor:<part>`) and logged once per streak. HC's own fault
  entries survive the sensor check of the next step and clear themselves when the part works again.
- **State saved at once** when the output switches or a boost starts / ends (before: every 10 minutes and at a clean
  stop – a crash or a power cut could lose up to 10 minutes of burns the boost resume and the flame log rely on).
- **Off by default (measured on one house only):** the coasting after a burn (0.44.3, `coast_window_s`, now 0) and
  the mid-cycle start (0.44.2, new `pwm_midcycle_start`, False) – both in the options (TPI / PID) with a suggested
  value; an instance keeps them on only where its options say so. The burner-start cycle fix of 0.44.5 stays (it is a
  correction, not a tuning).
- **CI:** `.github/workflows/validate.yml` – hassfest, the HACS check and the tests with Home Assistant 2026.10.0.
- Tests: tests/test_external_470.py (12); the E2E takes the manual way and the basics step.

## 0.46.0 – 2026-11-12
Rooms set up from the home's areas, in fewer and shorter steps (and point 6 of an outside tester's feedback: only the
ticked areas are rooms – no server room or control cabinet as a heating zone).
- **Options:** the menu has **Rooms** next to *Settings*; it saves only the rooms (the other settings stay as they
  are), and *Settings* no longer walks through the rooms (it ends after the presets and keeps the rooms).
  1. *Areas:* the home's name and every indoor area as a check box with what it has ("Kitchen – 2 thermometers ·
     1 TRV head · 1 presence · 1 window/door"); an area another HC instance uses is marked and refused; rooms without
     an area by name. Unticking removes the room (and its thermostat), never touches the heads.
  2. *Settings:* the leading room (by default the room of the house thermometer), the valve advice tolerance (moved
     here from *Settings*), then **one fold-out section per room** with the area's devices as check boxes – ticked
     already for a new room: thermometers (not a head's own one), real free TRV heads, motion / occupancy sensors,
     window / door contacts – and "Add another device" for one from another area (sorted in by its kind). Target,
     presence setback, boiler demand and **per head calibration** (before only in the wizard) appear only for a TRV
     room that is not the leading one. The place in the house drawing is a number in the section.
  3. *Own schedule:* only for the rooms set to it.
  Problems are told with the room's name (a thermometer or head ticked in two rooms, a room with nothing, a head of
  another instance, a leading room with a head without the confirmation).
- **Window / door per room:** in a TRV room its contacts close **only the room's own heads** (frost target after the
  window delay, back at once when closed – reason `window`); in the leading room and in a room without a TRV they stop
  the boiler as the instance's window list does. A contact of the instance's list that is ticked in a TRV room counts
  only there from then on.
- **Room groups (HC's own entities):** a room with two or more thermometers gets `sensor.<room>_homerseklet_hc` (their
  mean, as HC regulates), two or more presence sources `binary_sensor.<room>_jelenlet_hc` (anyone there), two or more
  contacts `binary_sensor.<room>_ablak_hc` (any open) (English: `_temperature_hc`, `_presence_hc`, `_window_hc`). They
  come and go with the room and follow its members; a legacy (pre-0.43) room list gets none.
- **Wizard:** the Rooms card starts with the home's name and "One room – this thermostat" / "Several rooms with this heat
  source"; the areas are a check list and **nothing is ticked by itself** (before: every area with a thermometer was
  suggested); a ticked area comes filled as above (all its thermometers, its windows); window / door per room.
- **Wording:** a room without a TRV is a **watched room** ("megfigyelt") in the wizard, the options summary and HC info;
  HC info shows each room's role and its windows (and what they do).
- **House drawing:** the home's name on the gable (else the instance's name).
- Tests: tests/test_rooms_460.py (14); tests/test_rooms_430.py etc. unchanged in substance.

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

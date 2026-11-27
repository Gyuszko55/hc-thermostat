# Local guard (0.76.0)

When Home Assistant stops, restarts for too long, loses the network, or HC itself stops deciding, the heating should
not depend on it. The **local guard** is a small program next to the relay. It switches the relay only while HC
renews a short **lease**; without one it keeps the last command for a grace time and then regulates on its own by a
local thermometer. The boiler's own safety devices (high limit, safety thermostat, floor limit thermostat, frost
protection) stay below it and are never bypassed.

```
NORMAL ──lease expired──▶ GRACE ──5 min──▶ FALLBACK ──lease again──▶ HANDBACK ──2 min, 2 renewals──▶ NORMAL
  ▲                         │                 │  ▲                       │
  └──────lease renewed──────┘     sensor lost ▼  │ sensor back           └──lease lost──▶ FALLBACK
                                           NOSENSOR (off, or a fixed duty cycle)
```

After a power cut the guard starts in FALLBACK and hands over only after a stable lease.

## Shelly Gen3 / Gen4 (`shelly/hc_guard.js`)

Needs a relay with scripting (Gen2 and later; a Gen1 Shelly 1 cannot run it). For a boiler's thermostat input use a
relay with a **dry (potential-free) contact**, e.g. Shelly 1 Gen3 or Shelly 1 Gen4. The local thermometer is a
Shelly BLU H&T paired to the relay as a BTHome device (read over Bluetooth by the relay itself, without Home
Assistant), or a wired probe on an add-on.

A Wi-Fi thermometer can push its readings to the guard instead (it then needs the router, not Home Assistant):
`GET http://<ip>/script/<id>/hc?tok=<token>&t=21.3`. On a Plus H&T: a webhook on `temperature.change` with the URL
`http://<ip>/script/<id>/hc?tok=<token>&t=${ev.tC}`; on a Gen1 H&T: *Actions → Sensors report URL*
`http://<ip>/script/<id>/hc?tok=<token>` (it appends `?hum=..&temp=..`). A pushed reading counts for 2 hours (these
wake only on a change); the Bluetooth sensor, when there is one, comes first.

1. Pair the BLU H&T in the relay's web UI (Components → BTHome). The uploader finds its temperature itself (a fresh
   pairing numbers the sensors by object id, 200 is often the battery); `--sensor bthomesensor:<id>` picks one.
2. Upload and start the script, protecting the device with a password at the same time (0.78.2, strongly
   recommended):

   ```sh
   HC_GUARD_PASSWORD='<device password>' python3 guard/upload_shelly.py <ip> --set-password
   ```

   The tool needs aiohttp 3.12 or later (`pip install aiohttp`; Python's own urllib knows no SHA-256 digest, the
   only one a Shelly offers). Without `HC_GUARD_TOKEN` the tool makes a random token, writes it to the device and prints it once. Secrets in
   the environment stay out of the shell history and the process list (`--token` / `--password` work too).
3. In HC: the instance's **Settings → Local guard**: the printed address (`http://<ip>/script/<id>/hc`), the token
   (required), the device password, an optional push URL (an ntfy topic) and the fallback values (target, band,
   without a thermometer). Give the device password to Home Assistant's Shelly integration as well (reconfigure the
   device there), or it loses the device.
4. Remove the relay from any other automation: with a guard, HC no longer calls the relay's switch service – it
   sends the command in the lease, and the guard switches.

Recommended for a gas boiler: keep the old mechanical room thermostat **in parallel** with the relay, set to about
17 °C – it keeps the house from cooling down even if the guard itself fails.

### Longest run (0.78.2)

`max_on` (HC: Settings → Local guard → Longest continuous on) holds in every mode – while HC controls, in the grace
after a lost lease, in the fallback and in the handback: after that long the relay goes off and keeps `min_off`, so a
stale or wrong reading gives a bounded duty, never endless heating. Electric heaters get 2 hours by default (they have
no limit thermostat of their own). A Bluetooth reading whose age cannot be told (no time sync) counts as no reading.

### Security (0.78.2)

- **The token is required.** A guard without `hc_guard_token` takes no lease and no pushed temperature – it only runs
  its own program; HC's settings refuse a guard address without a token.
- **Protect the device with a password** (`--set-password`, or the Shelly web UI → Settings → Authentication). Its
  digest auth (SHA-256, user `admin`) then covers the script's endpoint *and* the whole Shelly RPC: without it anyone
  on the network can call `Switch.Set`, stop the script or rewrite its KVS keys, whatever the token. HC signs every
  lease with it (Settings → Local guard → Device password). A pushing Wi-Fi thermometer cannot do digest auth – with
  a password set, use the Bluetooth sensor instead of the push.
- A protected Shelly answers a script endpoint request that carries a body and no Authorization by closing the
  connection (no 401). HC (0.78.3) therefore takes the digest challenge from a bodiless GET of the status first and
  signs the lease in advance; a client of your own has to do the same.
- The token travels in plain HTTP (the Shelly has no HTTPS endpoint): keep the relay on a trusted network or an IoT
  VLAN; the device password, unlike the token, never travels in the clear.

### Test before it matters

With the boiler supervised: stop the lease (set HC's instance to shadow, or block the address), wait 5 minutes and
check that the guard reports `fallback`, switches by its own thermometer and sends the push; then let HC renew and
check the handback after 2 minutes. `GET http://<ip>/script/<id>/hc` shows the guard's status at any time.

### The dead man (0.77.1)

The guard watches HC; this watches the guard. Every "on" the script gives carries the relay's own flip-back timer
(`toggle_after`, 180 s), and the running script re-arms it every minute while the relay is on. If the script stops –
stopped by hand, a crash, a failed upload – the relay switches itself off within 3 minutes instead of staying on
forever; an "off" never carries a timer (that would switch the boiler on later). Change it with
`upload_shelly.py --deadman <s>` (KVS `hc_guard_deadman`, 60–3600, `0` = none); the status shows it as `dm`.
After its own start the script keeps `min_off` when it finds the relay off (0.77.2), so a restart right
after the dead man cut in does not fire the boiler again at once. A dead guard therefore means no heating, not endless heating – the boiler's own frost protection and high limit
remain the last line.

### The life-safety chain (0.77.0)

When the wired life-safety chain (smoke, CO, gas, water detectors' normally closed contacts in series, holding a
latching relay) has an auxiliary contact, wire it to the guard's input and set `--safety input:0:on` (on = chain
closed, all clear). With the chain open – or the input unreadable – the guard switches the relay off at once, ignores
every lease and posts a push; when the chain closes again it starts in fallback and hands back as usual. This is a
second line: the chain itself stops the boiler (in series with the relay contact), the gas valve and the water valve.

HC's own life-safety stop (its safety inputs, 0.77.0) reaches the guard as the command `"safety"` (0.78.2): the relay
goes off at once (no `min_on`), the stop is latched on the device (KVS `hc_guard_stop`, kept over a restart) and the
guard's fallback does **not** heat while it holds – even when Home Assistant is gone. The first ordinary lease after
the stop was acknowledged in HC clears it; control comes back through the usual handback. The status shows `hc_stop`.

## HC Lite – a whole thermostat on the relay (`shelly/hc_lite.js`, since 0.79.2; script 0.82.5)

For a plain on-off boiler with one room thermometer: a Shelly 1 Mini Gen4 (or any Gen3 / Gen4 relay with scripting)
and a Shelly BLU H&T paired to it (BTHome). The script **heats on its own** – Home Assistant only sets it up and reads
it. It is not the guard: run one of the two on a relay, never both.

- **Targets:** day / night program (separate weekday and weekend times), `away`, `off` (frost only), and a manual
  target until the next program change (or for a time). Without a clock (no time sync) it keeps the day target.
- **Control:** hysteresis (`ctl: "hyst"`, `hyst` total band) or a simple time-proportional one (`ctl: "tpi"`:
  `demand = bias + kp × (target − room)`, 0…1, over `cycle` seconds; an on time under `min_on` is skipped or
  stretched to it).
- **Limits in every mode:** `min_on`, `min_off`, `max_on`; every "on" carries the relay's dead-man timer
  (`toggle_after` 180 s, re-armed every 60 s while the script runs).
- **No reading** (sensor lost or older than `sensor_max_age`): `ns: "off"` or a fixed duty (`don` / `doff`).
- **Shadow:** `shadow: true` decides and reports (`relay` is what it would do, `real_relay` the actual one) but never
  switches – for a first run beside the old thermostat.
- **Endpoint** `/script/<id>/lite`: `GET` status JSON; `GET ?page=1` the page (it loads the web set-up; offline it
  shows the reading, target, mode and boiler, read only);
  `POST {"tok": .., "set": {..}}` settings, `{"tok": .., "target": 21.5, "hold": "next" | seconds}`,
  `{"tok": .., "mode": "auto" | "away" | "off"}`. The page's own buttons work only when the device has a password
  (the browser then passes digest auth); without one the page is read only.
- **Kept on the device** (KVS): `hc_lite_cfg`, `hc_lite_token`, `hc_lite_mode`, `hc_lite_hold`.
- **Presets (0.82.0)** – every one with an end, so a lost Home Assistant never leaves the relay stuck:
  `{"preset": "comfort"}` (the program's target + `cf_delta` for `cf_time`; again: longer), `{"preset": "sleep"}`
  (the night target until the program changes), `{"preset": "home"}` (all back to the program),
  `{"mode": "away", "for": 43200}` (away that ends by itself), `{"vacation": <unixtime> | 0}` (away until then,
  preheated back), `{"window": true, "for": 3600}` / `{"window": false}`, `{"we_today": true}` (the weekend
  program today); `"src": "ha" | "web"` says who asked. Order: off > window > vacation > away > comfort / sleep /
  manual > the program. The status shows `preset`, `psrc` (ha / web / button), `puntil`.
- **A BLU button without Home Assistant (0.82.0):** set `btn` to the bthomedevice id of the BLU H&T (or a BLU
  Button) paired to the relay – the device itself sends its button's pushes (a button cannot be added as a sensor):
  one push comfort, two pushes away / back, a long push all back to the program.

Install: pair the BLU H&T in the Shelly's web page (Components → Add BTHome device, press the H&T's button). The
relay numbers the sensors itself by object id – on a Shelly 1 Gen4 a fresh pairing gave 200 battery, 201 humidity,
202 temperature – so the uploader finds the temperature (and the humidity) on its own (`--sensor auto`, the default),
and the script, if the id set is no temperature, uses the first BTHome temperature on the relay and says so
(`sensor_warn`, also on the page's *First steps*). Then

```
HC_GUARD_PASSWORD=... python guard/upload_shelly.py <ip> --lite --set-password --shadow
```

It prints a token once – keep it: the relay's page (*First steps* → *Token*) and Home Assistant ask for it. Leave out
`--shadow` when it may switch the boiler (or go live later on the page). In Home Assistant: add HC Thermostat →
manual → role *HC Lite* → the script's address, the token and the device password; the form starts from the relay's
own settings. Desk tests: `node --test "guard/tests/*.test.mjs"` (a simulated Shelly runs the unchanged script).

## The protocol (for ESPHome, a PLC or anything else)

HC sends, at least every `guard_every_s` (60 s) and at once on every change:

```json
POST <guard url>
{"cmd": "on", "ttl": 300, "seq": 18342, "tok": "<required>",
 "fb": {"sp": 20.5, "hyst": 0.6, "min_on": 300, "min_off": 300, "max_on": 0,
        "ns": "off", "don": 1200, "doff": 2400, "push": ""}}
```

and expects `200` with `{"mode": "normal|grace|fallback|nosensor|handback|safety", "relay": true, "temp": 21.2,
"lease_left": 287, "sp": 20.5, "hc_stop": false, ...}`. `cmd` is `on`, `off` or `safety` (0.78.2: off at once, latched
until the next `on` / `off`); a request without the right `tok` gets `403`. A guard of any kind should: honour `min_on` / `min_off` in every mode, keep
`fb` in non-volatile memory, start in fallback after power-up, and hand back only after a stable lease. A PLC
typically uses a watchdog register incremented by HC instead of HTTP; its fallback is its own heating curve.

Lessons from other controllers worth keeping:

- **ESPHome:** set `api: reboot_timeout: 0s` (and `wifi: reboot_timeout: 0s`). The default reboots the device every
  15 minutes without Home Assistant, which restarts the fallback again and again – the very case the guard is for.
  Use the relay's `restore_mode: ALWAYS_OFF` and let the guard decide after boot, and a `interval:` dead man (or the
  relay's own timer) like the Shelly script.
- **Never heat at full power as an emergency mode.** The fallback is a thermostat with a band and minimum times, or a
  bounded duty cycle without a thermometer – not "on" until someone comes. A guard that knows nothing switches off.
- **The guard is not a safety device.** The boiler's high limit, safety thermostat, floor limit thermostat and the
  wired life-safety chain stay in series with the relay contact, whatever the software does.

HC shows the guard's mode as the *Local guard* sensor and in the info panel, and raises a Repairs entry when the
guard cannot be reached for 10 minutes or regulates on its own while HC runs.

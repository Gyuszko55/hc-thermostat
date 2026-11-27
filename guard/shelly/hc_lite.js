// HC Thermostat Lite for Shelly Gen3 / Gen4 (relay with scripting) - version 2
// A complete small thermostat on the relay itself: a Shelly BLU H&T (BTHome) in the room (or a wired add-on probe, or
// a Wi-Fi H&T that pushes its reading here),
// an on-off boiler on the relay. It heats with or without Home Assistant; Home Assistant (the HC integration) only sets it up and reads it.
//   - targets: day / night program (weekdays and weekend), "away", "off" (frost only), a manual target until the
//     next program change; preheat: the day target starts early, (day target - room) * pre minutes (at most pre_max)
//   - control: hysteresis, a simple time-proportional one (TPI) on a fixed cycle, or PI ("pid": TPI plus an integral
//     that learns the house's steady need; anti-windup, kept in KVS over restarts)
//   - boost (TPI / PI): at least `boost` C below the target it heats without a break until `boost_end` C below it,
//     then the cycle takes over again (max on still holds)
//   - limits in every mode: min on, min off, max on; the relay's own dead-man timer on every "on"
//   - no reading (sensor lost or too old): "off" or a fixed safe duty cycle
//   - shadow: decides and reports, never switches (for a first run beside the old thermostat)
//   - heat source (src): "gas" or "hp" (heat pump). A heat pump may also cool ({"hvac":"cool"}): the relay then asks
//     for cooling above the cooling targets (sc_*), with no preheat, boost or frost, and stays off without a reading.
//     The heat pump itself is set to cooling on its own controller (one relay = the request only).
//   - dew point (cooling): from the room's humidity (hum_id: a BTHome humidity 200.., an add-on DHT22 humidity
//     100..; a pushing Wi-Fi H&T sends it itself). With a probe on the cooled flow pipe (dew_id) cooling stops while
//     the pipe is below dew point + dew_margin (and without a humidity then); without one it only warns.
//   - buffer: up to 3 add-on probes (buf, names bufn) shown in the status; they do not steer anything
// Endpoint: GET  http://<ip>/script/<id>/lite            -> status (JSON)
//           GET  http://<ip>/script/<id>/lite?page=1     -> a small page (read only without a device password)
//           GET  http://<ip>/script/<id>/lite?tok=..&t=21.3 -> a pushed room temperature (sensor "push": a Wi-Fi
//                H&T's webhook; "?" and "&" both separate, as the H&T appends "?hum=..")
//           POST http://<ip>/script/<id>/lite {"tok":"..","set":{..settings..}}           -> new settings
//           POST http://<ip>/script/<id>/lite {"tok":"..","target":21.5,"hold":"next"|seconds} -> manual target
//           POST http://<ip>/script/<id>/lite {"tok":"..","mode":"auto"|"away"|"off"}     -> mode
//                (0.82.0: "away" with "for": seconds ends by itself - Home Assistant's presence sends it so)
//           0.82.0 presets: {"preset":"comfort"} (the target + cf_delta for cf_time s; again: longer),
//                {"preset":"sleep"} (the night target until the program changes), {"preset":"home"} (all back to
//                the program), {"vacation":<unixtime>|0} (away until then, preheated back), {"window":true,"for":s}
//                / {"window":false} (frost while open, at most "for" s), {"we_today":true} (the weekend program
//                today); "src":"ha"|"web" tells who asked. A BLU button (btn: its bthomedevice id): one push
//                comfort, two pushes away / back, a long push all back to the program.
//                Order: off > window > vacation > away > comfort / sleep / manual > the program.
//           The page's own buttons send {"ui":1,...}: accepted only when the device has a password (digest auth).
//           POST {"init_tok":".."}  -> the first token, only while the device has none (a set-up without Home Assistant)
//           POST {"tok":"..","ui_src":"https://.."} -> where the web set-up page loads its program from
// The page (?page=1) is a small status page; it also loads the full web set-up (status, settings, first steps) from
// UI_SRC: the script's memory holds only a few kB, so the browser fetches that program and it talks to this endpoint.
// Without the internet the small page still works.
//           POST http://<ip>/script/<id>/lite {"tok":"..","hvac":"heat"|"cool"}         -> heating or cooling (hp only)
// KVS: hc_lite_c1..c5 (the settings, in parts: a KVS value holds less than 255 characters), hc_lite_cfg (settings
//      JSON taken last, so an upload tool's few settings win; emptied on a save), hc_lite_token, hc_lite_mode,
//      hc_lite_hvac, hc_lite_hold (manual target JSON), hc_lite_i (integral),
//      hc_lite_rev (settings revision, +1 on every change), hc_lite_ui (UI_SRC),
//      hc_lite_mx (0.82.0: {mu: away until, ms: who set the mode, vac: vacation until, vs: who set it, we: day})
// Keep this file plain ASCII (Script.PutCode refuses longer code with many non-ASCII characters).

// ---------------------------------------------------------------- settings
let C = {
  relay: 0, sensor: "bthomesensor", sensor_id: 200, sensor_max_age: 1800,
  sp_day: 21.0, sp_night: 19.0, sp_away: 16.0, frost: 7.0,
  day: "06:00", night: "22:00", day_we: "07:00", night_we: "23:00",
  ctl: "hyst", hyst: 0.4,                  // total band, C: on below sp - hyst/2, off above sp + hyst/2
  cycle: 1800, kp: 0.5, bias: 0.15,        // TPI: demand = bias + kp * (sp - t), 0..1, over one cycle
  ti: 14400,                               // pid: demand = bias + kp * (e + integral of e dt / ti), the integral in -1..1
  boost: 0, boost_end: 0.3,               // boost: on without a break from boost C below the target to boost_end (0: none)
  pre: 0, pre_max: 120,                    // preheat: minutes per C below the day target before the day starts (0: none), at most
  min_on: 300, min_off: 300, max_on: 7200, // s (max_on 0: no limit)
  ns: "duty", don: 600, doff: 2400,        // no reading: "off" or a duty of don / doff seconds
  deadman: 180, rearm: 60, tick: 10,
  shadow: false,
  src: "gas", sc_day: 25.0, sc_night: 26.0, sc_away: 28.0, // heat source; cooling targets (hp)
  hum_id: -1, dew_id: -1, dew_margin: 2.0,                  // humidity, flow pipe probe (-1: none), C above dew point
  buf: [], bufn: [],                                         // buffer probes (temperature ids) and their names
  cf_delta: 1.0, cf_time: 7200, btn: -1                      // 0.82.0: comfort +C for s; a BLU button (bthomedevice id)
};
let HVAC = "heat";          // heat | cool (cool only with src "hp")
let TOKEN = "";
let REV = 0;                // +1 on every settings change, so a second writer (HC, the web page) sees a change
let UI_SRC = "https://cdn.jsdelivr.net/gh/Gyuszko55/hc-thermostat@main/guard/shelly/hc_lite_ui.js";
let MODE = "auto";          // auto | away | off
let HOLD = null;            // {sp: 21.5, until: unixtime | -1 (next program change), at: "day"|"night", p: preset, s: who}
let MX = { mu: 0, ms: "", vac: 0, vs: "", we: -1 }; // 0.82.0: away until, vacation until, weekend program today
let WIN = -1;               // 0.82.0: the window is open until this uptime

// ---------------------------------------------------------------- state
let st = {
  relay: false, would: false, changed: -100000, armed: -100000,
  temp: null, temp_age: null, sp: null, period: null, reason: "boot", demand: null,
  cyc_start: -1, day: -1, starts: 0, on_s: 0, last_t: -1, log: [],
  i: 0, i_t: -1, i_saved: -100000,
  push_t: null, push_at: -1, pre: false, boost: false,
  push_h: null, hum: null, dp: null, pipe: null, dew: false, dw: false, bufv: [], btn: null
};

function up() {
  let s = Shelly.getComponentStatus("sys");
  return s && typeof s.uptime === "number" ? s.uptime : 0;
}

// ---------------------------------------------------------------- local time and the program
function hm(s) { let p = s.split(":"); return Number(p[0]) * 60 + Number(p[1]); }

// minutes of the local day and the weekday (0 = Sunday); null without a time sync
function localNow() {
  let s = Shelly.getComponentStatus("sys");
  if (!s || typeof s.unixtime !== "number" || s.unixtime <= 0 || typeof s.time !== "string" || s.time.length < 4) return null;
  let lm = hm(s.time);
  let um = Math.floor(s.unixtime / 60) % 1440;
  let off = lm - um;
  if (off > 720) off = off - 1440;
  if (off < -720) off = off + 1440;
  let days = Math.floor((Math.floor(s.unixtime / 60) + off) / 1440);
  return { min: lm, wd: (days + 4) % 7, day: days, unix: s.unixtime };
}

function weekend(wd) { return wd === 0 || wd === 6; }

// "day" or "night" now, and the unixtime of the next change
function period(L) {
  let we = weekend(L.wd) || L.day === MX.we;
  let d = hm(we ? C.day_we : C.day), n = hm(we ? C.night_we : C.night);
  let isDay = d <= n ? (L.min >= d && L.min < n) : (L.min >= d || L.min < n);
  return isDay ? "day" : "night";
}

// minutes until the next day period starts (today's, or tomorrow's with its own weekday / weekend time)
function toDay(L) {
  let d = hm(weekend(L.wd) || L.day === MX.we ? C.day_we : C.day);
  if (L.min < d) return d - L.min;
  let w = (L.wd + 1) % 7;
  return hm(weekend(w) ? C.day_we : C.day) + 1440 - L.min;
}

// the night ends early by the room's shortfall: (day target - room) * pre minutes, at most pre_max; once begun it
// holds until the day period (a warming room must not drop it back to night)
function preheat(L, v) {
  if (C.pre <= 0 || v === null || C.sp_day <= C.sp_night) { st.pre = false; return false; }
  if (st.pre) return true;
  let lead = (C.sp_day - v) * C.pre;
  if (lead > C.pre_max) lead = C.pre_max;
  if (lead > 0 && toDay(L) <= lead) st.pre = true;
  return st.pre;
}

// cooling: its own targets, no preheat, and "off" is off (null: no frost guard in cooling)
function target(L, v) {
  let k = HVAC === "cool";
  if (MODE === "off") { st.period = "off"; st.pre = false; return k ? null : C.frost; }
  if (WIN >= 0 && up() >= WIN) WIN = -1;
  if (WIN >= 0) { st.period = "window"; st.pre = false; return k ? null : C.frost; }
  if (MX.vac > 0 && L !== null && L.unix >= MX.vac) { MX.vac = 0; MX.vs = ""; saveMx(); }
  if (MX.vac > 0) { // away until the date; the day target early by the room's shortfall (as preheat), so it is warm on arrival
    let lead = C.pre > 0 && v !== null && !k ? (C.sp_day - v) * C.pre : 0;
    if (lead > C.pre_max) lead = C.pre_max;
    if (L !== null && lead > 0 && (MX.vac - L.unix) / 60 <= lead) { st.period = "vacation preheat"; return C.sp_day; }
    st.period = "vacation"; st.pre = false; return k ? C.sc_away : C.sp_away;
  }
  if (MODE === "away" && MX.mu > 0 && L !== null && L.unix >= MX.mu) { MODE = "auto"; save("hc_lite_mode", MODE); MX.mu = 0; MX.ms = ""; saveMx(); }
  if (MODE === "away") { st.period = "away"; st.pre = false; return k ? C.sc_away : C.sp_away; }
  if (L === null) { st.period = "no time"; return k ? C.sc_day : C.sp_day; } // no clock: comfort, never a cold house
  let p = period(L);
  if (HOLD !== null) {
    let over = HOLD.until > 0 ? L.unix >= HOLD.until : p !== HOLD.at;
    if (over) { HOLD = null; save("hc_lite_hold", ""); }
  }
  if (p !== "night" || HOLD !== null) st.pre = false;
  st.period = p;
  if (HOLD !== null) { st.period = p + " (" + (HOLD.p || "manual") + ")"; return HOLD.sp; }
  if (k) return p === "day" ? C.sc_day : C.sc_night;
  if (p === "night" && preheat(L, v)) { st.period = "preheat"; return C.sp_day; }
  return p === "day" ? C.sp_day : C.sp_night;
}

// ---------------------------------------------------------------- humidity, dew point, pipe and buffer probes
function probe(id) {
  if (id < 0) return null;
  let s = Shelly.getComponentStatus("temperature", id);
  return s && typeof s.tC === "number" ? s.tC : null;
}

function extra(v) {
  let h = null, s;
  if (C.hum_id >= 200) { s = Shelly.getComponentStatus("bthomesensor", C.hum_id); if (s) h = s.value; }
  else if (C.hum_id >= 100) { s = Shelly.getComponentStatus("humidity", C.hum_id); if (s) h = s.rh; }
  else if (C.sensor === "push") h = st.push_h;
  st.hum = typeof h === "number" && h > 0 && h <= 100 ? h : null;
  st.dp = null;
  if (st.hum !== null && v !== null) { // Magnus formula
    let g = Math.log(st.hum / 100) + 17.62 * v / (243.12 + v);
    st.dp = Math.round(2431.2 * g / (17.62 - g)) / 10;
  }
  st.pipe = probe(C.dew_id);
  st.bufv = [];
  for (let i = 0; i < C.buf.length; i++) st.bufv.push(probe(C.buf[i]));
  st.dw = st.dp !== null && v !== null && v < st.dp + C.dew_margin + 1; // the room itself is close to its dew point
}

// cooling with a pipe probe: off below dew point + margin (or with no humidity / no pipe reading), on again 1 C above
function dewStop() {
  if (C.dew_id < 0) { st.dew = false; return false; }
  if (st.dp === null || st.pipe === null || st.pipe < st.dp + C.dew_margin) st.dew = true;
  else if (st.pipe >= st.dp + C.dew_margin + 1) st.dew = false;
  return st.dew;
}

// ---------------------------------------------------------------- the thermometer
function readTemp() {
  st.temp = null; st.temp_age = null;
  if (!C.sensor) return null;
  if (C.sensor === "push") { // a pushed reading, aged by the uptime (no time sync needed)
    if (st.push_t === null || st.push_at < 0) return null;
    let pa = up() - st.push_at;
    if (pa < 0 || pa > C.sensor_max_age) return null;
    st.temp = st.push_t; st.temp_age = pa;
    return st.push_t;
  }
  let s = Shelly.getComponentStatus(C.sensor, C.sensor_id);
  if (!s) return null;
  let v = C.sensor === "temperature" ? s.tC : s.value;
  if (typeof v !== "number" || v < -30 || v > 60) return null;
  if (C.sensor === "temperature") { st.temp = v; st.temp_age = 0; return v; } // a wired add-on probe: read live
  let sys = Shelly.getComponentStatus("sys");
  if (typeof s.last_updated_ts !== "number" || !sys || typeof sys.unixtime !== "number" || sys.unixtime <= 0) return null;
  let age = sys.unixtime - s.last_updated_ts;
  if (age < 0 || age > C.sensor_max_age) return null;
  st.temp = v; st.temp_age = age;
  return v;
}

// ---------------------------------------------------------------- the relay with its limits
function readRelay() {
  let s = Shelly.getComponentStatus("switch", C.relay);
  if (s && typeof s.output === "boolean" && !C.shadow) st.relay = s.output;
  return C.shadow ? st.would : st.relay;
}

function relayOn(t) {
  let p = { id: C.relay, on: true };
  if (C.deadman > 0) p.toggle_after = C.deadman;
  Shelly.call("Switch.Set", p);
  st.armed = t;
}

function want(on, t, why, now) {
  let cur = readRelay();
  if (on === cur) { st.reason = why; return; }  // the reason of the state it keeps (not only of the last switch)
  let held = t - st.changed;
  if (cur && held < C.min_on && !now) return;    // now: the dew point stops cooling at once
  if (!cur && held < C.min_off) return;
  st.changed = t; st.reason = why;
  if (on) st.starts = st.starts + 1;
  st.log.push([t, on ? 1 : 0, st.temp, st.sp]);
  if (st.log.length > 20) st.log.splice(0, 1);
  if (C.shadow) { st.would = on; return; }
  if (on) relayOn(t); else Shelly.call("Switch.Set", { id: C.relay, on: false });
  st.relay = on;
}

// ---------------------------------------------------------------- one step
function tick() {
  let t = up();
  let L = localNow();
  let cur = readRelay();
  if (L !== null && L.day !== st.day) { st.day = L.day; st.starts = 0; st.on_s = 0; }
  if (st.last_t >= 0 && cur) st.on_s = st.on_s + (t - st.last_t);
  st.last_t = t;
  if (!C.shadow && cur && C.deadman > 0 && t - st.armed >= C.rearm) relayOn(t);
  let v = readTemp();
  extra(v);
  let k = HVAC === "cool";
  let sp = target(L, v);
  if (sp === null) { st.sp = null; st.demand = null; st.boost = false; want(false, t, "off"); return; }
  // a higher heating (lower cooling) target: a new cycle now, not at its end
  if (st.sp !== null && (k ? st.sp - sp : sp - st.sp) >= 0.3 && !cur) st.cyc_start = -1;
  st.sp = sp;
  if (C.max_on > 0 && cur && t - st.changed >= C.max_on) { want(false, t, "max on"); return; }
  if (v === null) {
    st.demand = null;
    if (C.ns === "duty" && !k) {
      let held = t - st.changed;
      if (cur && held >= C.don) want(false, t, "no reading: duty off");
      else if (!cur && held >= C.doff) want(true, t, "no reading: duty on");
    } else {
      want(false, t, "no reading");
    }
    return;
  }
  if (k && dewStop()) { st.demand = null; st.i_t = t; want(false, t, "dew point", true); return; }
  let e = k ? v - sp : sp - v; // > 0: it needs heating (cooling)
  if (C.ctl === "tpi" || C.ctl === "pid") {
    if (k || C.boost <= 0 || e <= C.boost_end) {
      if (st.boost) st.cyc_start = t; // the boost ends: a new cycle from here
      st.boost = false;
    } else if (e >= C.boost) st.boost = true;
    let d = C.bias + C.kp * e;
    if (st.boost) {             // on without a break; the integral stands still (it would only wind up)
      st.i_t = t; st.demand = 1;
      want(true, t, "boost");
      return;
    }
    if (C.ctl === "pid") d = d + integrate(e, d, t);
    d = d < 0 ? 0 : (d > 1 ? 1 : d);
    st.demand = Math.round(d * 100) / 100;
    if (st.cyc_start < 0 || t - st.cyc_start >= C.cycle) st.cyc_start = t;
    let pos = t - st.cyc_start;
    let onFor = d * C.cycle;
    if (onFor > 0 && onFor < C.min_on) onFor = d >= 0.5 * C.min_on / C.cycle ? C.min_on : 0; // too short: skip or min
    if (pos < onFor) want(true, t, "demand " + Math.round(d * 100) + " %");
    else want(false, t, "demand " + Math.round(d * 100) + " %");
  } else {
    st.demand = null; st.boost = false;
    if (e >= C.hyst / 2) want(true, t, k ? "above target" : "below target");
    else if (e <= -C.hyst / 2) want(false, t, "target reached");
    else if (st.reason === "boot") st.reason = "inside the band";
  }
}

// pid: the integral part of the demand (kp * I). It stands still while the demand is pinned at 0 or 1 and the error
// pushes further that way (anti-windup), and goes to KVS every 15 minutes so a restart does not forget the house.
function integrate(e, d, t) {
  let dt = st.i_t < 0 ? 0 : t - st.i_t;
  st.i_t = t;
  if (dt > 0 && dt <= 600) {
    let p = d + C.kp * st.i;
    if (!((p >= 1 && e > 0) || (p <= 0 && e < 0))) {
      st.i = st.i + e * dt / C.ti;
      if (st.i > 1) st.i = 1;
      if (st.i < -1) st.i = -1;
    }
  }
  if (t - st.i_saved >= 900) { st.i_saved = t; save("hc_lite_i", String(Math.round(st.i * 10000) / 10000)); }
  return C.kp * st.i;
}

// ---------------------------------------------------------------- settings in, status out
// one KVS write at a time (a script may have only a few calls in flight)
let SQ = [];
function save(k, v) { SQ.push([k, v]); if (SQ.length === 1) flush(); }
function flush() {
  if (!SQ.length) return;
  Shelly.call("KVS.Set", { key: SQ[0][0], value: SQ[0][1] }, function () { SQ.splice(0, 1); flush(); });
}

// the settings in parts of less than 255 characters, as the device counts them (hc_lite_c1..c5); hc_lite_cfg emptied (see the KVS note)
function saveCfg() {
  let o = cfgOut(), part = {}, n = 0, len = 2, ps = [];
  for (let key in o) {
    // the device counts the value as escaped JSON (a quote is two characters); room left for UTF-8 names
    let one = JSON.stringify(JSON.stringify(key) + ":" + JSON.stringify(o[key])).length - 1;
    if (len + one > 220 && n > 0) { ps.push(JSON.stringify(part)); part = {}; n = 0; len = 2; }
    part[key] = o[key]; n++; len = len + one;
  }
  ps.push(JSON.stringify(part));
  for (let i = 0; i < 5; i++) save("hc_lite_c" + (i + 1), i < ps.length ? ps[i] : "{}");
  save("hc_lite_cfg", "{}");
}
function num(v, lo, hi, d) { return typeof v === "number" && v >= lo && v <= hi ? v : d; }
function clock(v, d) {
  if (typeof v !== "string" || v.length !== 5 || v.charAt(2) !== ":") return d;
  let h = Number(v.substr(0, 2)), m = Number(v.substr(3, 2));
  return h >= 0 && h <= 23 && m >= 0 && m <= 59 ? v : d;
}

function takeCfg(n) {
  if (!n || typeof n !== "object") return;
  C.sp_day = num(n.sp_day, 5, 30, C.sp_day); C.sp_night = num(n.sp_night, 5, 30, C.sp_night);
  C.sp_away = num(n.sp_away, 5, 30, C.sp_away); C.frost = num(n.frost, 3, 12, C.frost);
  C.day = clock(n.day, C.day); C.night = clock(n.night, C.night);
  C.day_we = clock(n.day_we, C.day_we); C.night_we = clock(n.night_we, C.night_we);
  if ((n.ctl === "hyst" || n.ctl === "tpi" || n.ctl === "pid") && n.ctl !== C.ctl) {
    if (n.ctl === "pid") { st.i = 0; st.i_t = -1; }  // a fresh start in pid
    C.ctl = n.ctl;
  }
  C.hyst = num(n.hyst, 0.1, 3, C.hyst);
  C.cycle = num(n.cycle, 600, 7200, C.cycle); C.kp = num(n.kp, 0.05, 3, C.kp); C.bias = num(n.bias, 0, 0.8, C.bias);
  C.ti = num(n.ti, 1800, 86400, C.ti);
  C.boost = num(n.boost, 0, 5, C.boost); C.boost_end = num(n.boost_end, 0, 2, C.boost_end);
  C.pre = num(n.pre, 0, 120, C.pre); C.pre_max = num(n.pre_max, 0, 360, C.pre_max);
  C.min_on = num(n.min_on, 0, 3600, C.min_on); C.min_off = num(n.min_off, 0, 3600, C.min_off);
  C.max_on = num(n.max_on, 0, 86400, C.max_on);
  if (n.ns === "off" || n.ns === "duty") C.ns = n.ns;
  C.don = num(n.don, 60, 7200, C.don); C.doff = num(n.doff, 60, 14400, C.doff);
  if (n.sensor === "bthomesensor" || n.sensor === "temperature" || n.sensor === "push") C.sensor = n.sensor;
  C.sensor_id = num(n.sensor_id, 0, 299, C.sensor_id); C.sensor_max_age = num(n.sensor_max_age, 300, 7200, C.sensor_max_age);
  if (typeof n.shadow === "boolean") { if (C.shadow && !n.shadow) st.would = false; C.shadow = n.shadow; }
  if (n.src === "gas" || n.src === "hp") C.src = n.src;
  if (C.src !== "hp") setHvac("heat");
  C.sc_day = num(n.sc_day, 16, 30, C.sc_day); C.sc_night = num(n.sc_night, 16, 30, C.sc_night);
  C.sc_away = num(n.sc_away, 16, 30, C.sc_away);
  C.hum_id = num(n.hum_id, -1, 299, C.hum_id); C.dew_id = num(n.dew_id, -1, 199, C.dew_id);
  C.dew_margin = num(n.dew_margin, 0.5, 5, C.dew_margin);
  if (n.buf && n.buf.length !== undefined) {
    let b = [];
    for (let i = 0; i < n.buf.length && b.length < 3; i++) if (num(n.buf[i], 100, 199, -1) >= 0) b.push(n.buf[i]);
    C.buf = b;
  }
  C.cf_delta = num(n.cf_delta, 0.5, 3, C.cf_delta); C.cf_time = num(n.cf_time, 1800, 21600, C.cf_time);
  C.btn = num(n.btn, -1, 299, C.btn);
  if (n.bufn && n.bufn.length !== undefined) {
    let b = [];
    for (let i = 0; i < n.bufn.length && b.length < 3; i++) b.push(typeof n.bufn[i] === "string" ? n.bufn[i].substr(0, 16) : "");
    C.bufn = b;
  }
}

// heating or cooling; a change starts the control afresh (the integral, boost, the cycle, the dew point latch)
function setHvac(h) {
  if (h === HVAC || (h === "cool" && C.src !== "hp")) return false;
  HVAC = h; save("hc_lite_hvac", h);
  st.i = 0; st.i_t = -1; st.boost = false; st.dew = false; st.cyc_start = -1; st.pre = false;
  return true;
}

function cfgOut() {
  return { sp_day: C.sp_day, sp_night: C.sp_night, sp_away: C.sp_away, frost: C.frost, day: C.day, night: C.night,
    day_we: C.day_we, night_we: C.night_we, ctl: C.ctl, hyst: C.hyst, cycle: C.cycle, kp: C.kp, bias: C.bias, ti: C.ti,
    boost: C.boost, boost_end: C.boost_end, pre: C.pre, pre_max: C.pre_max,
    min_on: C.min_on, min_off: C.min_off, max_on: C.max_on, ns: C.ns, don: C.don, doff: C.doff,
    sensor: C.sensor, sensor_id: C.sensor_id, sensor_max_age: C.sensor_max_age, shadow: C.shadow,
    src: C.src, sc_day: C.sc_day, sc_night: C.sc_night, sc_away: C.sc_away, hum_id: C.hum_id, dew_id: C.dew_id,
    dew_margin: C.dew_margin, buf: C.buf, bufn: C.bufn, cf_delta: C.cf_delta, cf_time: C.cf_time, btn: C.btn };
}

function status() {
  return { v: 1, mode: MODE, period: st.period, sp: st.sp, temp: st.temp, temp_age: st.temp_age,
    relay: C.shadow ? st.would : st.relay, shadow: C.shadow, real_relay: C.shadow ? readRelayRaw() : st.relay,
    demand: st.demand, integral: C.ctl === "pid" ? Math.round(C.kp * st.i * 1000) / 1000 : null, reason: st.reason, boost: st.boost, hold: HOLD, since_s: up() - st.changed,
    starts_today: st.starts, on_min_today: Math.round(st.on_s / 60), log: st.log, cfg: cfgOut(),
    token: TOKEN ? true : false, rev: REV, sv: "0.82.0",
    preset: preset(), psrc: psrc(), puntil: puntil(), vac: MX.vac > 0 ? MX.vac : null,
    win_s: WIN >= 0 ? WIN - up() : null, we_today: st.period !== null && MX.we >= 0 && MX.we === st.day, btn_ev: st.btn,
    hvac: HVAC, hum: st.hum, dew: st.dp, pipe: st.pipe, dew_stop: HVAC === "cool" && st.dew, dew_warn: HVAC === "cool" && st.dw,
    buf: st.bufv };
}

// 0.82.0: which preset rules now, who asked for it, and until when (unixtime; null: open-ended or by the program)
function preset() {
  if (MODE === "off") return "off";
  if (WIN >= 0) return "window";
  if (MX.vac > 0) return "vacation";
  if (MODE === "away") return "away";
  if (HOLD !== null) return HOLD.p || "manual";
  return "schedule";
}
function psrc() {
  let p = preset();
  if (p === "vacation") return MX.vs || null;
  if (p === "away" || p === "off") return MX.ms || null;
  if (HOLD !== null && p !== "schedule" && p !== "window") return HOLD.s || null;
  return null;
}
function puntil() {
  let p = preset();
  if (p === "vacation") return MX.vac;
  if (p === "away") return MX.mu > 0 ? MX.mu : null;
  if (p === "window") { let L = localNow(); return L !== null ? L.unix + WIN - up() : null; }
  if (HOLD !== null && p !== "off" && HOLD.until > 0) return HOLD.until;
  return null;
}
function saveMx() { save("hc_lite_mx", JSON.stringify(MX)); }

// the program's own target now (no manual target), for comfort's "+ cf_delta"
function base(L) {
  let h = HOLD, w = WIN; HOLD = null; WIN = -1;
  let t = target(L, st.temp);
  HOLD = h; WIN = w;
  return t;
}

// the presets; who: "ha", "web" or "button"
function setMode(m, who, secs) {
  let L = localNow();
  MODE = m; save("hc_lite_mode", MODE);
  MX.ms = who; MX.mu = m === "away" && typeof secs === "number" && secs >= 600 && L !== null ? L.unix + secs : 0;
  if (MODE !== "auto") { HOLD = null; save("hc_lite_hold", ""); }
  saveMx();
}
function home(who) {
  HOLD = null; save("hc_lite_hold", "");
  MX.vac = 0; MX.vs = ""; WIN = -1;
  setMode("auto", who);
}
function comfort(who) {
  let L = localNow();
  if (MODE !== "auto" || MX.vac > 0) { MX.vac = 0; MX.vs = ""; setMode("auto", who); }
  if (HOLD !== null && HOLD.p === "comfort" && HOLD.until > 0 && L !== null) {
    HOLD.until = HOLD.until + C.cf_time;
    if (HOLD.until > L.unix + 3 * C.cf_time) HOLD.until = L.unix + 3 * C.cf_time;
  } else {
    let b = base(L);
    if (b === null) return;
    let k = HVAC === "cool";
    let sp = Math.round((k ? b - C.cf_delta : b + C.cf_delta) * 2) / 2;
    HOLD = { sp: sp, until: L !== null ? L.unix + C.cf_time : -1, at: L !== null ? period(L) : "day", p: "comfort", s: who };
  }
  save("hc_lite_hold", JSON.stringify(HOLD));
}
function sleep(who) {
  let L = localNow();
  if (MODE !== "auto") setMode("auto", who);
  HOLD = { sp: HVAC === "cool" ? C.sc_night : C.sp_night, until: -1, at: L !== null ? period(L) : "day", p: "sleep", s: who };
  save("hc_lite_hold", JSON.stringify(HOLD));
}

// a BLU button paired to the relay (BTHome): one push comfort, two pushes away / back, a long push all back
function button(ev) {
  if (C.btn < 0 || !ev || !ev.info) return;
  let c = ev.info.component; // the BLU device itself (bthomedevice:200) sends its button's pushes; a sensor id works too
  if (c !== "bthomedevice:" + C.btn && c !== "bthomesensor:" + C.btn) return;
  let e = ev.info.event;
  if (typeof e !== "string" || e.indexOf("push") < 0) return;
  st.btn = e;
  if (e === "single_push") comfort("button");
  else if (e === "double_push") { if (MODE === "away" || MX.vac > 0) home("button"); else setMode("away", "button"); }
  else if (e === "long_push") home("button");
  else return;
  tick();
}

function readRelayRaw() {
  let s = Shelly.getComponentStatus("switch", C.relay);
  return s && typeof s.output === "boolean" ? s.output : null;
}

function authOn() {
  let d = Shelly.getDeviceInfo();
  return d && d.auth_en === true;
}

function okTok(t) {
  for (let i = 0; i < t.length; i++) {
    let c = t.charAt(i);
    if (!((c >= "a" && c <= "z") || (c >= "A" && c <= "Z") || (c >= "0" && c <= "9") || c === "-" || c === "_")) return false;
  }
  return true;
}

function handle(body) {
  let r;
  try { r = JSON.parse(body); } catch (e) { return { code: 400, body: { error: "bad json" } }; }
  if (typeof r.init_tok === "string") { // the first token, from the web set-up; never over an existing one
    if (TOKEN) return { code: 403, body: { error: "a token is already set" } };
    if (r.init_tok.length < 8 || r.init_tok.length > 64 || !okTok(r.init_tok)) return { code: 400, body: { error: "token: 8-64 letters, digits, - or _" } };
    TOKEN = r.init_tok; save("hc_lite_token", TOKEN);
    return { code: 200, body: status() };
  }
  if (r.ui === 1) { if (!authOn()) return { code: 403, body: { error: "set a device password to change it here" } }; }
  else if (!TOKEN || r.tok !== TOKEN) return { code: 403, body: { error: "bad token" } };
  let who = r.ui === 1 ? "web" : (r.src === "web" ? "web" : "ha");
  if (r.set) {
    let was = JSON.stringify(cfgOut());
    takeCfg(r.set);
    let now = JSON.stringify(cfgOut());
    if (now !== was) { REV = REV + 1; save("hc_lite_rev", String(REV)); saveCfg(); }
  }
  if (r.hvac === "heat" || r.hvac === "cool") {
    if (r.hvac === "cool" && C.src !== "hp") return { code: 400, body: { error: "cooling needs a heat pump (src hp)" } };
    setHvac(r.hvac);
  }
  if (typeof r.ui_src === "string" && r.ui_src.length <= 200 && (r.ui_src.indexOf("https://") === 0 || r.ui_src.indexOf("http://") === 0)) {
    UI_SRC = r.ui_src; save("hc_lite_ui", UI_SRC);
  }
  if (r.mode === "auto" || r.mode === "away" || r.mode === "off") {
    if (r.mode === "auto") { MX.vac = 0; MX.vs = ""; }
    setMode(r.mode, who, r.for);
  }
  if (r.preset === "home") home(who);
  if (r.preset === "comfort") comfort(who);
  if (r.preset === "sleep") sleep(who);
  if (typeof r.vacation === "number") {
    let L = localNow();
    if (r.vacation > 0 && (L === null || r.vacation > L.unix)) { MX.vac = r.vacation; MX.vs = who; HOLD = null; save("hc_lite_hold", ""); }
    else { MX.vac = 0; MX.vs = ""; }
    saveMx();
  }
  if (r.window === true) WIN = up() + num(r.for, 60, 7200, 3600);
  if (r.window === false) WIN = -1;
  if (r.we_today === true) { let L = localNow(); if (L !== null) { MX.we = L.day; saveMx(); } }
  if (r.we_today === false) { MX.we = -1; saveMx(); }
  if (typeof r.target === "number" && r.target >= 5 && r.target <= 30) {
    let L = localNow();
    let until = typeof r.hold === "number" && r.hold >= 600 && L !== null ? L.unix + r.hold : -1;
    MODE = "auto"; save("hc_lite_mode", MODE);
    HOLD = { sp: Math.round(r.target * 2) / 2, until: until, at: L !== null ? period(L) : "day", p: "manual", s: who };
    save("hc_lite_hold", JSON.stringify(HOLD));
  }
  if (r.clear_hold === true) { HOLD = null; save("hc_lite_hold", ""); }
  tick();
  return { code: 200, body: status() };
}

// a page small enough for the script's memory: the numbers, +/- and the mode; it reads /lite every 30 s
let PAGE = "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>HC Lite</title>" +
  "<style>body{font:16px sans-serif;margin:16px;max-width:420px}b{font-size:44px}button{font-size:20px;margin:4px;padding:8px 16px}" +
  "small{color:#777}</style><div id=s>...</div><p><button onclick=t(-0.5)>-</button><button onclick=t(0.5)>+</button>" +
  "<button onclick=p({preset:'comfort'})>Comfort</button><button onclick=m('auto')>Auto</button><button onclick=m('away')>Away</button><button onclick=m('off')>Off</button></p>" +
  "<small id=n></small><script>var S;function g(){fetch('lite').then(r=>r.json()).then(j=>{S=j;var e=document.getElementById('s');if(!e)return;" +
  "e.innerHTML='<b>'+(j.temp===null?'--':j.temp.toFixed(1))+' C</b><br>target '+j.sp+' C, '+" +
  "j.mode+' / '+j.period+'<br>boiler '+(j.relay?'ON':'off')+(j.shadow?' (shadow)':'')+', '+j.reason+'<br>today '+" +
  "j.starts_today+' starts, '+j.on_min_today+' min'})}function p(b){b.ui=1;fetch('lite',{method:'POST',body:JSON.stringify(b)})" +
  ".then(r=>r.json()).then(j=>{if(j.error)document.getElementById('n').textContent=j.error;g()})}" +
  "function t(d){p({target:S.sp+d,hold:'next'})}function m(x){p({mode:x})}g();setInterval(g,30000)</script>";

// a pushed reading: "t=21.3" (or "temp=21.3"); "?" and "&" both separate (the H&T appends "?hum=..")
function query(q, key) {
  if (!q) return null;
  let parts = q.split("?").join("&").split("&");
  for (let i = 0; i < parts.length; i++) {
    let kv = parts[i].split("=");
    if (kv.length === 2 && kv[0] === key) return kv[1];
  }
  return null;
}

function pushTemp(q) {
  if (!TOKEN || query(q, "tok") !== TOKEN) return { code: 403, body: { error: "bad token" } };
  let raw = query(q, "t");
  if (raw === null) raw = query(q, "temp");
  let v = raw === null ? NaN : Number(raw);
  if (!(v >= -30 && v <= 60)) return { code: 400, body: { error: "temperature" } };
  st.push_t = v; st.push_at = up();
  let h = query(q, "hum");
  if (h === null) h = query(q, "h");
  if (h !== null) { h = Number(h); st.push_h = h > 0 && h <= 100 ? h : null; }
  tick();
  return { code: 200, body: { ok: true, temp: v, used: C.sensor === "push" } };
}

function endpoint(req, res) {
  let q = req.query || "";
  let r;
  if (req.method === "POST") r = handle(req.body);
  else if (query(q, "t") !== null || query(q, "temp") !== null) r = pushTemp(q);
  else if (q.indexOf("page=1") >= 0) {
    res.code = 200; res.headers = [["Content-Type", "text/html; charset=utf-8"]];
    res.body = PAGE + "<script src='" + UI_SRC + "' charset=utf-8></script>"; res.send(); return;
  } else r = { code: 200, body: status() };
  res.code = r.code;
  res.headers = [["Content-Type", "application/json"]];
  res.body = JSON.stringify(r.body);
  res.send();
}

// ---------------------------------------------------------------- start
function start() {
  // an "off" relay at start keeps min_off before heating again; an "on" one may switch off at once
  let s = Shelly.getComponentStatus("switch", C.relay);
  let on = s && s.output === true;
  st.relay = on;
  st.changed = on ? up() - 100000 : up();
  HTTPServer.registerEndpoint("lite", endpoint);
  Shelly.addEventHandler(button);
  Timer.set(C.tick * 1000, true, tick);
  tick();
}

Shelly.call("KVS.GetMany", { match: "hc_lite_*" }, function (res) {
  let items = res && res.items ? res.items : null;
  if (items) {
    let get = function (k) {
      if (items.length !== undefined) { for (let i = 0; i < items.length; i++) if (items[i].key === k) return items[i].value; return null; }
      return items[k] ? items[k].value : null;
    };
    for (let p = 1; p <= 6; p++) {
      let c = get(p < 6 ? "hc_lite_c" + p : "hc_lite_cfg");
      if (c) { try { takeCfg(JSON.parse(c)); } catch (e) {} }
    }
    if (get("hc_lite_hvac") === "cool" && C.src === "hp") HVAC = "cool";
    let tok = get("hc_lite_token");
    if (tok) TOKEN = tok;
    let rv = Number(get("hc_lite_rev"));
    if (rv === rv && rv > 0) REV = rv;
    let us = get("hc_lite_ui");
    if (us) UI_SRC = us;
    let m = get("hc_lite_mode");
    if (m === "auto" || m === "away" || m === "off") MODE = m;
    let x = get("hc_lite_mx");
    if (x) { try { let o = JSON.parse(x); if (o && typeof o === "object") { MX.mu = o.mu || 0; MX.ms = o.ms || ""; MX.vac = o.vac || 0; MX.vs = o.vs || ""; MX.we = typeof o.we === "number" ? o.we : -1; } } catch (e) {} }
    let h = get("hc_lite_hold");
    if (h) { try { HOLD = JSON.parse(h); } catch (e) { HOLD = null; } }
    let i = Number(get("hc_lite_i"));
    if (C.ctl === "pid" && i === i && i >= -1 && i <= 1) st.i = i;
  }
  start();
});

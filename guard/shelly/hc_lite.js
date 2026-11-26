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
// Endpoint: GET  http://<ip>/script/<id>/lite            -> status (JSON)
//           GET  http://<ip>/script/<id>/lite?page=1     -> a small page (read only without a device password)
//           GET  http://<ip>/script/<id>/lite?tok=..&t=21.3 -> a pushed room temperature (sensor "push": a Wi-Fi
//                H&T's webhook; "?" and "&" both separate, as the H&T appends "?hum=..")
//           POST http://<ip>/script/<id>/lite {"tok":"..","set":{..settings..}}           -> new settings
//           POST http://<ip>/script/<id>/lite {"tok":"..","target":21.5,"hold":"next"|seconds} -> manual target
//           POST http://<ip>/script/<id>/lite {"tok":"..","mode":"auto"|"away"|"off"}     -> mode
//           The page's own buttons send {"ui":1,...}: accepted only when the device has a password (digest auth).
//           POST {"init_tok":".."}  -> the first token, only while the device has none (a set-up without Home Assistant)
//           POST {"tok":"..","ui_src":"https://.."} -> where the web set-up page loads its program from
// The page (?page=1) is a small status page; it also loads the full web set-up (status, settings, first steps) from
// UI_SRC: the script's memory holds only a few kB, so the browser fetches that program and it talks to this endpoint.
// Without the internet the small page still works.
// KVS: hc_lite_cfg (settings JSON), hc_lite_token, hc_lite_mode, hc_lite_hold (manual target JSON), hc_lite_i (integral),
//      hc_lite_rev (settings revision, +1 on every change), hc_lite_ui (UI_SRC)
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
  shadow: false
};
let TOKEN = "";
let REV = 0;                // +1 on every settings change, so a second writer (HC, the web page) sees a change
let UI_SRC = "https://cdn.jsdelivr.net/gh/Gyuszko55/hc-thermostat@main/guard/shelly/hc_lite_ui.js";
let MODE = "auto";          // auto | away | off
let HOLD = null;            // {sp: 21.5, until: unixtime | -1 (next program change), at: "day"|"night"}

// ---------------------------------------------------------------- state
let st = {
  relay: false, would: false, changed: -100000, armed: -100000,
  temp: null, temp_age: null, sp: null, period: null, reason: "boot", demand: null,
  cyc_start: -1, day: -1, starts: 0, on_s: 0, last_t: -1, log: [],
  i: 0, i_t: -1, i_saved: -100000,
  push_t: null, push_at: -1, pre: false, boost: false
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
  let we = weekend(L.wd);
  let d = hm(we ? C.day_we : C.day), n = hm(we ? C.night_we : C.night);
  let isDay = d <= n ? (L.min >= d && L.min < n) : (L.min >= d || L.min < n);
  return isDay ? "day" : "night";
}

// minutes until the next day period starts (today's, or tomorrow's with its own weekday / weekend time)
function toDay(L) {
  let d = hm(weekend(L.wd) ? C.day_we : C.day);
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

function target(L, v) {
  if (MODE === "off") { st.period = "off"; st.pre = false; return C.frost; }
  if (MODE === "away") { st.period = "away"; st.pre = false; return C.sp_away; }
  if (L === null) { st.period = "no time"; return C.sp_day; } // no clock: comfort, never a cold house
  let p = period(L);
  if (HOLD !== null) {
    let over = HOLD.until > 0 ? L.unix >= HOLD.until : p !== HOLD.at;
    if (over) { HOLD = null; save("hc_lite_hold", ""); }
  }
  if (p !== "night" || HOLD !== null) st.pre = false;
  st.period = p;
  if (HOLD !== null) { st.period = p + " (manual)"; return HOLD.sp; }
  if (p === "night" && preheat(L, v)) { st.period = "preheat"; return C.sp_day; }
  return p === "day" ? C.sp_day : C.sp_night;
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

function want(on, t, why) {
  let cur = readRelay();
  if (on === cur) { st.reason = why; return; }  // the reason of the state it keeps (not only of the last switch)
  let held = t - st.changed;
  if (cur && held < C.min_on) return;
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
  let sp = target(L, v);
  if (st.sp !== null && sp - st.sp >= 0.3 && !cur) st.cyc_start = -1; // a higher target: a new cycle now, not at its end
  st.sp = sp;
  if (C.max_on > 0 && cur && t - st.changed >= C.max_on) { want(false, t, "max on"); return; }
  if (v === null) {
    st.demand = null;
    if (C.ns === "duty") {
      let held = t - st.changed;
      if (cur && held >= C.don) want(false, t, "no reading: duty off");
      else if (!cur && held >= C.doff) want(true, t, "no reading: duty on");
    } else {
      want(false, t, "no reading");
    }
    return;
  }
  if (C.ctl === "tpi" || C.ctl === "pid") {
    let e = sp - v;
    if (C.boost <= 0 || e <= C.boost_end) {
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
    if (v <= sp - C.hyst / 2) want(true, t, "below target");
    else if (v >= sp + C.hyst / 2) want(false, t, "target reached");
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
function save(k, v) { Shelly.call("KVS.Set", { key: k, value: v }, function () {}); }
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
}

function cfgOut() {
  return { sp_day: C.sp_day, sp_night: C.sp_night, sp_away: C.sp_away, frost: C.frost, day: C.day, night: C.night,
    day_we: C.day_we, night_we: C.night_we, ctl: C.ctl, hyst: C.hyst, cycle: C.cycle, kp: C.kp, bias: C.bias, ti: C.ti,
    boost: C.boost, boost_end: C.boost_end, pre: C.pre, pre_max: C.pre_max,
    min_on: C.min_on, min_off: C.min_off, max_on: C.max_on, ns: C.ns, don: C.don, doff: C.doff,
    sensor: C.sensor, sensor_id: C.sensor_id, sensor_max_age: C.sensor_max_age, shadow: C.shadow };
}

function status() {
  return { v: 1, mode: MODE, period: st.period, sp: st.sp, temp: st.temp, temp_age: st.temp_age,
    relay: C.shadow ? st.would : st.relay, shadow: C.shadow, real_relay: C.shadow ? readRelayRaw() : st.relay,
    demand: st.demand, integral: C.ctl === "pid" ? Math.round(C.kp * st.i * 1000) / 1000 : null, reason: st.reason, boost: st.boost, hold: HOLD, since_s: up() - st.changed,
    starts_today: st.starts, on_min_today: Math.round(st.on_s / 60), log: st.log, cfg: cfgOut(),
    token: TOKEN ? true : false, rev: REV, sv: "0.79.9" };
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
  if (r.set) {
    let was = JSON.stringify(cfgOut());
    takeCfg(r.set);
    let now = JSON.stringify(cfgOut());
    if (now !== was) { REV = REV + 1; save("hc_lite_rev", String(REV)); save("hc_lite_cfg", now); }
  }
  if (typeof r.ui_src === "string" && r.ui_src.length <= 200 && (r.ui_src.indexOf("https://") === 0 || r.ui_src.indexOf("http://") === 0)) {
    UI_SRC = r.ui_src; save("hc_lite_ui", UI_SRC);
  }
  if (r.mode === "auto" || r.mode === "away" || r.mode === "off") {
    MODE = r.mode; save("hc_lite_mode", MODE);
    if (MODE !== "auto") { HOLD = null; save("hc_lite_hold", ""); }
  }
  if (typeof r.target === "number" && r.target >= 5 && r.target <= 30) {
    let L = localNow();
    let until = typeof r.hold === "number" && r.hold >= 600 && L !== null ? L.unix + r.hold : -1;
    MODE = "auto"; save("hc_lite_mode", MODE);
    HOLD = { sp: Math.round(r.target * 2) / 2, until: until, at: L !== null ? period(L) : "day" };
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
  "<button onclick=m('auto')>Auto</button><button onclick=m('away')>Away</button><button onclick=m('off')>Off</button></p>" +
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
    let c = get("hc_lite_cfg");
    if (c) { try { takeCfg(JSON.parse(c)); } catch (e) {} }
    let tok = get("hc_lite_token");
    if (tok) TOKEN = tok;
    let rv = Number(get("hc_lite_rev"));
    if (rv === rv && rv > 0) REV = rv;
    let us = get("hc_lite_ui");
    if (us) UI_SRC = us;
    let m = get("hc_lite_mode");
    if (m === "auto" || m === "away" || m === "off") MODE = m;
    let h = get("hc_lite_hold");
    if (h) { try { HOLD = JSON.parse(h); } catch (e) { HOLD = null; } }
    let i = Number(get("hc_lite_i"));
    if (C.ctl === "pid" && i === i && i >= -1 && i <= 1) st.i = i;
  }
  start();
});

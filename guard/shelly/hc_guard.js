// HC Thermostat local guard for Shelly Gen3 / Gen4 (relay with scripting) - version 2
// Runs on the relay itself. Home Assistant (HC) controls the relay only while it renews a short lease.
// Without a lease the guard keeps the last command for a grace time, then runs a simple local thermostat
// (a Shelly BLU H&T over BTHome, or an add-on probe), and hands control back only after a stable lease.
// Modes: normal -> grace -> fallback (-> nosensor) -> handback -> normal. After power-up: fallback (after min_off).
// safety: the life-safety chain is open (KVS hc_guard_safety = "input:0:on") - relay off at once, whatever the lease.
// 0.77.1 dead man: every "on" carries the relay's own flip-back timer (toggle_after), re-armed while the script runs;
//   a stopped or crashed script lets the relay fall off by itself (KVS hc_guard_deadman = seconds, "0" = none).
// 0.78.2: token required (no lease without it); set a device password too (digest auth covers this endpoint).
//   cmd "safety": off at once, latched (KVS hc_guard_stop) until an ordinary lease.
// Endpoint: POST http://<ip>/script/<id>/hc  {"cmd":"on"|"off"|"safety","ttl":300,"seq":1,"tok":"..","fb":{..}}
//           GET  http://<ip>/script/<id>/hc  -> status only (does not renew the lease)
//           GET  http://<ip>/script/<id>/hc?tok=..&t=21.3 -> a pushed room temperature (a Wi-Fi H&T's action / webhook;
//                the Gen1 H&T's report URL appends ?hum=..&temp=..). Used when the Bluetooth sensor is missing or old.
// Keep this file plain ASCII (Script.PutCode refuses longer code with many non-ASCII characters).

// ---------------------------------------------------------------- settings (defaults; HC sends its own in "fb")
let CFG = {
  relay: 0,             // switch id
  sensor: "bthomesensor", // "bthomesensor" (BLU H&T over BTHome), "temperature" (add-on probe) or "" (none)
  sensor_id: 200,
  sensor_max_age: 900,  // s: an older reading is no reading
  push_max_age: 7200,   // s: a pushed reading (a Wi-Fi H&T wakes on a change) is kept this long (0.78.2: 2 h)
  grace: 300,           // s: keep the last command this long after the lease ran out
  handback: 120,        // s: a lease must hold this long (and be renewed twice) before HC gets control back
  tick: 10,             // s
  safety_id: -1,        // 0.77.0: input id wired to the life-safety chain's auxiliary contact (-1: none)
  safety_ok: true,      // the input state that means "chain closed, all clear"
  deadman: 180,         // 0.77.1: s, the relay's own off timer on every "on" (0: none); never on an "off"
  rearm: 60             // s, re-arm it this often while the relay is on
};
let FB = {
  sp: 20.5,       // fallback target, C
  hyst: 0.6,      // total band: on below sp - hyst/2, off above sp + hyst/2
  min_on: 300,    // s, every mode
  min_off: 300,   // s, every mode
  max_on: 0,      // s, longest continuous on in every mode (0: no limit); then min_off
  ns: "off",      // no sensor in fallback: "off" or "duty"
  don: 1200,      // s on  (ns = "duty")
  doff: 2400,     // s off (ns = "duty")
  push: ""        // URL for a push when the guard takes over (ntfy topic URL); "" = none
};
let TOKEN = "";   // KVS hc_guard_token; required (0.78.2) - every lease and pushed reading must carry it in "tok"

// ---------------------------------------------------------------- state
let st = {
  mode: "fallback", since: 0, lease_until: -1, cmd: "off", seq: 0,
  hb_since: 0, hb_renews: 0,
  relay: false, changed: -100000, // uptime of the last relay change (far past: no minimum time pending)
  temp: null, temp_age: null, temp_src: null, pushed: false, reason: "boot",
  push_t: null, push_at: -1, armed: -100000,
  hc_stop: false  // 0.78.2: HC's life-safety stop, latched (KVS hc_guard_stop)
};

function now() {
  let s = Shelly.getComponentStatus("sys");
  return s && typeof s.uptime === "number" ? s.uptime : 0;
}

function setMode(m, why) {
  if (st.mode === m) return;
  print("hc_guard: " + st.mode + " -> " + m + " (" + why + ")");
  st.mode = m; st.since = now(); st.reason = why;
  if (m === "safety") st.pushed = false; // a life-safety stop is always announced
  if (m === "fallback" || m === "nosensor" || m === "safety") notify();
  if (m === "normal") st.pushed = false;
}

function notify() {
  if (st.pushed || !FB.push) return;
  st.pushed = true;
  let t = st.temp === null ? "no sensor" : (Math.round(st.temp * 10) / 10) + " C";
  let what = st.mode === "safety" ? "LIFE-SAFETY STOP - heating off" : "HC guard took over the heating";
  Shelly.call("HTTP.POST", { url: FB.push, body: what + " (" + st.reason + "), room " + t,
    content_type: "text/plain", timeout: 10 }, function () {});
}

// ---------------------------------------------------------------- relay with its limits
function readRelay() {
  let s = Shelly.getComponentStatus("switch", CFG.relay);
  if (s && typeof s.output === "boolean") st.relay = s.output;
  return st.relay;
}

function want(on, t) {
  let cur = readRelay();
  let held = t - st.changed;
  if (on === cur) return;
  if (cur && held < FB.min_on) return;   // a burn runs at least min_on
  if (!cur && held < FB.min_off) return; // a pause lasts at least min_off
  if (on) relayOn(t); else Shelly.call("Switch.Set", { id: CFG.relay, on: false });
  st.relay = on; st.changed = t;
}

// "on" only with the dead-man timer: the relay switches itself off unless the script re-arms it in time
function relayOn(t) {
  let p = { id: CFG.relay, on: true };
  if (CFG.deadman > 0) p.toggle_after = CFG.deadman;
  Shelly.call("Switch.Set", p);
  st.armed = t;
}

// ---------------------------------------------------------------- local thermometer
function readLocal() {
  if (!CFG.sensor) return null;
  let s = Shelly.getComponentStatus(CFG.sensor, CFG.sensor_id);
  if (!s) return null;
  let v = CFG.sensor === "temperature" ? s.tC : s.value;
  if (typeof v !== "number" || v < -30 || v > 60) return null;
  // 0.78.2: an age that cannot be told (no time sync, no timestamp) is no reading
  let sys = Shelly.getComponentStatus("sys");
  if (typeof s.last_updated_ts !== "number" || !sys || typeof sys.unixtime !== "number" || sys.unixtime <= 0) return null;
  let age = sys.unixtime - s.last_updated_ts;
  if (age < 0 || age > CFG.sensor_max_age) return null;
  return { v: v, age: age };
}

function readTemp() {
  st.temp = null; st.temp_age = null; st.temp_src = null;
  let l = readLocal();
  if (l !== null) { st.temp = l.v; st.temp_age = l.age; st.temp_src = "local"; return l.v; }
  if (st.push_t !== null && st.push_at >= 0) {
    let age = now() - st.push_at;
    if (age <= CFG.push_max_age) { st.temp = st.push_t; st.temp_age = age; st.temp_src = "push"; return st.push_t; }
  }
  return null;
}

// a pushed reading: "t=21.3" or the Gen1 H&T's "temp=21.3"; "?" and "&" both separate (the H&T appends "?hum=..")
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
  if (!TOKEN) return { code: 403, body: { error: "no token set" } };
  if (query(q, "tok") !== TOKEN) return { code: 403, body: { error: "bad token" } };
  let raw = query(q, "t");
  if (raw === null) raw = query(q, "temp");
  let v = raw === null ? NaN : Number(raw);
  if (!(v >= -30 && v <= 60)) return { code: 400, body: { error: "temperature" } };
  st.push_t = v; st.push_at = now();
  tick();
  return { code: 200, body: status() };
}

// ---------------------------------------------------------------- the local program
function fallbackStep(t) {
  let v = readTemp();
  if (v === null) {
    if (st.mode === "fallback") setMode("nosensor", "sensor lost");
    if (FB.ns === "duty") {
      let held = t - st.changed;
      if (st.relay && held >= FB.don) want(false, t);
      else if (!st.relay && held >= FB.doff) want(true, t);
    } else {
      want(false, t);
    }
    return;
  }
  if (st.mode === "nosensor") setMode("fallback", "sensor back");
  if (v <= FB.sp - FB.hyst / 2) want(true, t);
  else if (v >= FB.sp + FB.hyst / 2) want(false, t);
}

// the life-safety chain: an unreadable input counts as open
function safetyOk() {
  if (CFG.safety_id < 0) return true;
  let s = Shelly.getComponentStatus("input", CFG.safety_id);
  if (!s || typeof s.state !== "boolean") return false;
  return s.state === CFG.safety_ok;
}

function tick() {
  let t = now();
  readRelay();
  let chain = safetyOk();
  if (!chain || st.hc_stop) {
    if (st.mode !== "safety") setMode("safety", chain ? "HC safety stop" : "safety chain open");
    if (st.relay) { Shelly.call("Switch.Set", { id: CFG.relay, on: false }); st.relay = false; st.changed = t; }
    return;
  }
  if (st.mode === "safety") setMode("fallback", "safety chain closed");
  if (st.relay && CFG.deadman > 0 && t - st.armed >= CFG.rearm) relayOn(t); // still alive: keep the relay on
  // 0.78.2: max_on in every mode (normal, grace, fallback, handback); min_off follows
  if (FB.max_on > 0 && st.relay && t - st.changed >= FB.max_on) want(false, t);
  let leased = t < st.lease_until;
  if (st.mode === "normal") {
    if (!leased) { setMode("grace", "lease expired"); }
    else {
      want(st.cmd === "on", t);
      return;
    }
  }
  if (st.mode === "grace") {
    if (leased) { setMode("normal", "lease renewed"); want(st.cmd === "on", t); return; }
    if (t - st.lease_until >= CFG.grace) { setMode("fallback", "no lease for " + (CFG.grace / 60) + " min"); }
    else { readTemp(); return; } // the last command stays
  }
  if (st.mode === "handback") {
    if (!leased) { setMode("fallback", "lease lost during handback"); }
    else if (t - st.hb_since >= CFG.handback && st.hb_renews >= 2) {
      setMode("normal", "handed back"); want(st.cmd === "on", t); return;
    }
  }
  fallbackStep(t);
}

// ---------------------------------------------------------------- lease endpoint
function num(v, lo, hi, d) { return typeof v === "number" && v >= lo && v <= hi ? v : d; }

function takeFb(fb) {
  if (!fb || typeof fb !== "object") return false;
  let n = {
    sp: num(fb.sp, 5, 30, FB.sp), hyst: num(fb.hyst, 0.1, 3, FB.hyst),
    min_on: num(fb.min_on, 0, 3600, FB.min_on), min_off: num(fb.min_off, 0, 3600, FB.min_off),
    max_on: num(fb.max_on, 0, 86400, FB.max_on), ns: fb.ns === "duty" ? "duty" : "off",
    don: num(fb.don, 60, 7200, FB.don), doff: num(fb.doff, 60, 14400, FB.doff),
    push: typeof fb.push === "string" ? fb.push : FB.push
  };
  if (JSON.stringify(n) === JSON.stringify(FB)) return false;
  FB = n;
  Shelly.call("KVS.Set", { key: "hc_guard_fb", value: JSON.stringify(FB) }, function () {});
  return true;
}

function status() {
  let t = now();
  return { mode: st.mode, safety: safetyOk(), since_s: t - st.since, reason: st.reason, relay: st.relay, cmd: st.cmd,
    lease_left: st.lease_until > t ? st.lease_until - t : 0, temp: st.temp, temp_age: st.temp_age, temp_src: st.temp_src,
    sp: FB.sp, seq: st.seq, dm: CFG.deadman, hc_stop: st.hc_stop, token: TOKEN ? true : false, v: 2 };
}

function lease(body) {
  let req;
  try { req = JSON.parse(body); } catch (e) { return { code: 400, body: { error: "bad json" } }; }
  if (!TOKEN) return { code: 403, body: { error: "no token set" } };
  if (req.tok !== TOKEN) return { code: 403, body: { error: "bad token" } };
  if (req.cmd !== "on" && req.cmd !== "off" && req.cmd !== "safety") return { code: 400, body: { error: "cmd" } };
  let t = now();
  let ttl = num(req.ttl, 30, 900, 300);
  takeFb(req.fb);
  st.seq = typeof req.seq === "number" ? req.seq : st.seq;
  st.lease_until = t + ttl;
  if (req.cmd === "safety") {
    // 0.78.2 (M1): off at once, whatever min_on; latched until an ordinary lease
    st.cmd = "off";
    if (!st.hc_stop) { st.hc_stop = true; Shelly.call("KVS.Set", { key: "hc_guard_stop", value: "1" }, function () {}); }
    tick();
    return { code: 200, body: status() };
  }
  st.cmd = req.cmd;
  if (st.hc_stop) {
    // HC's stop was acknowledged: the latch goes; control comes back through the usual handback
    st.hc_stop = false;
    Shelly.call("KVS.Set", { key: "hc_guard_stop", value: "0" }, function () {});
    if (st.mode === "safety" && safetyOk()) { st.mode = "fallback"; st.since = t; st.reason = "HC safety stop cleared"; }
  }
  if (st.mode === "fallback" || st.mode === "nosensor") {
    st.mode = "handback"; st.since = t; st.reason = "lease back"; st.hb_since = t; st.hb_renews = 0;
    print("hc_guard: handback started");
  } else if (st.mode === "handback") {
    st.hb_renews = st.hb_renews + 1;
  }
  tick();
  return { code: 200, body: status() };
}

function endpoint(request, response) {
  let q = request.query || "";
  let r = request.method === "POST" ? lease(request.body)
    : (query(q, "t") !== null || query(q, "temp") !== null) ? pushTemp(q) : { code: 200, body: status() };
  response.code = r.code;
  response.headers = [["Content-Type", "application/json"]];
  response.body = JSON.stringify(r.body);
  response.send();
}

// ---------------------------------------------------------------- start
function start() {
  st.since = now();
  // 0.77.2: an "off" relay at start (power-up, a restart after the dead man cut in) keeps min_off before heating again;
  // an "on" one may switch off at once
  st.changed = readRelay() ? now() - 100000 : now();
  HTTPServer.registerEndpoint("hc", endpoint);
  Shelly.addStatusHandler(function (ev) { if (ev.name === "input" && ev.id === CFG.safety_id) tick(); });
  Timer.set(CFG.tick * 1000, true, tick);
  tick();
}

Shelly.call("KVS.GetMany", { match: "hc_guard_*" }, function (res) {
  let items = res && res.items ? res.items : null;
  if (items) {
    // GetMany returns an array of {key, value} (newer firmware) or an object by key (older)
    let get = function (k) {
      if (items.length !== undefined) { for (let i = 0; i < items.length; i++) if (items[i].key === k) return items[i].value; return null; }
      return items[k] ? items[k].value : null;
    };
    let fb = get("hc_guard_fb");
    if (fb) { try { takeFb(JSON.parse(fb)); } catch (e) {} }
    let tok = get("hc_guard_token");
    if (tok) TOKEN = tok;
    if (get("hc_guard_stop") === "1") st.hc_stop = true; // 0.78.2: a stop from before the restart holds
    let saf = get("hc_guard_safety");
    if (saf) { let q = saf.split(":"); if (q.length === 3 && q[0] === "input") { CFG.safety_id = JSON.parse(q[1]); CFG.safety_ok = q[2] === "on"; } }
    let dm = get("hc_guard_deadman");
    if (dm !== null) { let d = Number(dm); if (d === 0 || (d >= 60 && d <= 3600)) CFG.deadman = d; }
    let sens = get("hc_guard_sensor");
    if (sens) { let p = sens.split(":"); CFG.sensor = p[0] === "none" ? "" : p[0]; if (p.length > 1) CFG.sensor_id = JSON.parse(p[1]); }
  }
  start();
});

// Desk tests of the HC Lite Shelly script: node --test guard/tests
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { ShellySim } from "./shelly_sim.mjs";

const SCRIPT = fileURLToPath(new URL("../shelly/hc_lite.js", import.meta.url));
const TOK = "t0ken";
// Tuesday 2026-11-24, 13:00 local (UTC+1)
const TUE_13 = Date.UTC(2026, 10, 24, 12, 0, 0) / 1000;
const sim = (o = {}) => new ShellySim({ script: SCRIPT, kvs: { hc_lite_token: TOK, ...(o.kvs || {}) }, ...o });
const post = (s, b) => s.http("POST", { body: { tok: TOK, ...b } });

test("the file is plain ASCII (Script.PutCode)", () => {
  const src = readFileSync(SCRIPT);
  assert.ok([...src].every((b) => b < 128), "non-ASCII byte in hc_lite.js");
});

test("hysteresis: on below the band, off above it, min off after a power-up", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.0);
  s.run(60);
  assert.equal(s.relay, false, "an off relay at start keeps min_off (300 s)");
  s.run(300);
  assert.equal(s.relay, true);
  assert.equal(s.state().sp, 21.0);
  s.setTemp(21.1); s.run(400);
  assert.equal(s.relay, true, "inside the band nothing changes");
  s.setTemp(21.25); s.run(20);
  assert.equal(s.relay, false);
  assert.equal(s.state().starts_today, 1);
});

test("min on: a burn is not cut short", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.0); s.run(320);
  assert.equal(s.relay, true);
  s.setTemp(22.0); s.run(100);
  assert.equal(s.relay, true, "on for 100 s only");
  s.run(250);
  assert.equal(s.relay, false);
});

test("program: night target after 22:00 on a weekday, day target after 07:00 at the weekend", () => {
  const s = sim({ unix: TUE_13 + 9 * 3600 + 60 }); // 22:01 local
  s.setTemp(20.0); s.run(20);
  assert.equal(s.state().sp, 19.0);
  assert.equal(s.state().period, "night");
  const sat = sim({ unix: Date.UTC(2026, 10, 28, 5, 30) / 1000 }); // Saturday 06:30 local
  sat.setTemp(20.0); sat.run(20);
  assert.equal(sat.state().sp, 19.0, "weekend day starts at 07:00");
  sat.run(1800);
  assert.equal(sat.state().sp, 21.0);
});

test("no reading: the safe duty cycle", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(null);
  s.run(2400 + 20);
  assert.equal(s.relay, true, "on after doff");
  s.run(600 + 20);
  assert.equal(s.relay, false, "off after don");
  const old = sim({ unix: TUE_13 });
  old.setTemp(19.0, 4000); old.run(20, { keepFresh: false });
  assert.equal(old.state().temp, null, "an old reading is no reading");
});

test("max on, then min off", () => {
  const s = sim({ unix: TUE_13 });
  post(s, { set: { max_on: 1800 } });
  s.setTemp(15.0); s.run(320);
  assert.equal(s.relay, true);
  s.run(1800);
  assert.equal(s.relay, false);
  assert.match(s.state().reason, /max on/);
});

test("dead man: the relay falls off when the script stops", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(18.0); s.run(320);
  assert.equal(s.relay, true);
  s.run(600);
  assert.equal(s.relay, true, "re-armed while running");
  s.stopped = true; s.run(200);
  assert.equal(s.relay, false);
});

test("settings, mode and a manual target need the token", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  assert.equal(s.http("POST", { body: { tok: "wrong", target: 23 } }).code, 403);
  assert.equal(s.http("POST", { body: { ui: 1, target: 23 } }).code, 403, "the page needs a device password");
  assert.equal(post(s, { set: { sp_day: 22, hyst: 0.6 } }).code, 200);
  assert.equal(s.state().sp, 22);
  assert.equal(JSON.parse(s.kvs.hc_lite_cfg).sp_day, 22);
  post(s, { mode: "away" });
  assert.equal(s.state().sp, 16.0);
  post(s, { mode: "off" });
  assert.equal(s.state().sp, 7.0);
  const a = sim({ unix: TUE_13, auth: true });
  a.setTemp(20.5); a.run(20);
  assert.equal(a.http("POST", { body: { ui: 1, target: 22.5 } }).code, 200, "with a device password the page may");
});

test("manual target holds until the next program change", () => {
  const s = sim({ unix: TUE_13 + 8 * 3600 }); // 21:00 local
  s.setTemp(20.5); s.run(20);
  post(s, { target: 23.2, hold: "next" });
  assert.equal(s.state().sp, 23.0, "rounded to 0.5");
  assert.match(s.state().period, /manual/);
  s.run(3600 + 60); // past 22:00
  assert.equal(s.state().sp, 19.0);
  assert.equal(s.state().hold, null);
  assert.equal(s.kvs.hc_lite_hold, "");
});

test("manual target for a time", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { target: 18, hold: 1800 });
  s.run(1700); assert.equal(s.state().sp, 18);
  s.run(200); assert.equal(s.state().sp, 21);
});

test("shadow: decides, never switches", () => {
  const s = sim({ unix: TUE_13, kvs: { hc_lite_cfg: JSON.stringify({ shadow: true }) } });
  s.setTemp(19.0); s.run(400);
  const st = s.state();
  assert.equal(st.shadow, true);
  assert.equal(st.relay, true, "it would heat");
  assert.equal(s.relay, false);
  assert.ok(!s.calls.some(([m]) => m === "Switch.Set"));
});

test("TPI: the on time follows the demand over the cycle", () => {
  const s = sim({ unix: TUE_13 });
  post(s, { set: { ctl: "tpi", cycle: 1800, kp: 0.5, bias: 0.15, min_off: 0 } });
  s.setTemp(20.5); // demand 0.15 + 0.5 * 0.5 = 0.40 -> 720 s of 1800
  s.run(400); // past the start-up min_off
  let on = 0;
  for (let i = 0; i < 3 * 1800; i += 10) { s.run(10); if (s.relay) on += 10; }
  assert.equal(s.state().demand, 0.4);
  assert.ok(Math.abs(on / (3 * 1800) - 0.4) < 0.06, `duty ${on / 5400}`);
});

test("restarts keep settings, mode and the manual target", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { set: { sp_day: 21.5 }, mode: "auto" });
  post(s, { target: 22.0, hold: "next" });
  const again = new ShellySim({ script: SCRIPT, kvs: s.kvs, unix: s.unix });
  again.setTemp(20.5); again.run(20);
  assert.equal(again.state().sp, 22.0);
  assert.equal(again.state().cfg.sp_day, 21.5);
});

test("no clock: the day target, never a cold house", () => {
  const s = sim({ unix: TUE_13 });
  s.timeSynced = false;
  s.setTemp(20.0); s.run(20, { keepFresh: false });
  assert.equal(s.state().period, "no time");
  assert.equal(s.state().sp, 21.0);
});

test("the page is served", () => {
  const s = sim({ unix: TUE_13 });
  const r = s.http("GET", { query: "page=1" });
  assert.equal(r.code, 200);
  assert.match(r.body, /HC Lite/);
});

test("a wired add-on probe instead of the BLU H&T", () => {
  const s = sim({ unix: TUE_13, kvs: { hc_lite_cfg: JSON.stringify({ sensor: "temperature", sensor_id: 100 }) } });
  s.probe = 19.5; s.run(320, { keepFresh: false });
  assert.equal(s.state().temp, 19.5);
  assert.equal(s.relay, true);
  assert.equal(s.state().cfg.sensor, "temperature");
});

test("pid: the integral closes a steady gap and stops at saturation (0.79.4)", () => {
  const s = sim({ unix: TUE_13 });
  post(s, { set: { ctl: "pid", cycle: 1800, kp: 0.5, bias: 0.15, ti: 3600, min_off: 0 } });
  s.setTemp(20.5); // e = 0.5: P part 0.40, the integral grows 0.5 * 0.5 per hour
  s.run(20);
  const d0 = s.state().demand;
  assert.ok(Math.abs(d0 - 0.4) < 0.02, `start ${d0}`);
  s.run(3600);
  const st = s.state();
  assert.ok(Math.abs(st.integral - 0.25) < 0.02, `integral ${st.integral}`);
  assert.ok(Math.abs(st.demand - 0.65) < 0.02, `demand ${st.demand}`);
  assert.equal(s.kvs.hc_lite_i !== undefined, true, "kept in KVS");
  s.setTemp(15.0); s.run(4 * 3600); // pinned at 100 %: no windup
  assert.equal(s.state().demand, 1);
  assert.ok(s.state().integral <= 0.5 + 1e-9 && s.state().integral > 0.2, `windup ${s.state().integral}`);
  s.setTemp(22.0); s.run(600); // above target: the integral comes back down, the relay follows
  assert.ok(s.state().integral < 0.5);
});

test("pid: the integral survives a restart, a switch to pid starts it from zero", () => {
  const s = sim({ unix: TUE_13 });
  post(s, { set: { ctl: "pid", ti: 3600 } });
  s.setTemp(20.5); s.run(1900);
  const kept = Number(s.kvs.hc_lite_i);
  assert.ok(kept > 0.1, `kvs ${kept}`);
  const again = new ShellySim({ script: SCRIPT, kvs: s.kvs, unix: s.unix });
  again.setTemp(20.5); again.run(20);
  assert.ok(Math.abs(again.state().integral - 0.5 * kept) < 0.02, `restored ${again.state().integral}`);
  assert.equal(again.state().cfg.ti, 3600);
  post(again, { set: { ctl: "tpi" } });
  assert.equal(again.state().integral, null);
  post(again, { set: { ctl: "pid" } });
  assert.ok(Math.abs(again.state().integral) < 0.01, "fresh start");
});

test("the reason tells the present decision, not 'boot' (0.79.4)", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(27.0); s.run(20);
  assert.equal(s.state().reason, "target reached", "off and staying off");
  const t = sim({ unix: TUE_13 });
  post(t, { set: { ctl: "tpi" } });
  t.setTemp(27.0); t.run(20);
  assert.equal(t.state().reason, "demand 0 %");
  const b = sim({ unix: TUE_13 });
  b.setTemp(21.0); b.run(20);
  assert.equal(b.state().reason, "inside the band");
});

test("a Wi-Fi H&T pushes its reading (sensor push, 0.79.6)", () => {
  const s = sim({ unix: TUE_13, kvs: { hc_lite_token: TOK, hc_lite_cfg: JSON.stringify({ sensor: "push", sensor_max_age: 7200, min_off: 0 }) } });
  s.setTemp(null);
  assert.equal(s.http("GET", { query: "tok=nope&t=20.0" }).code, 403, "a wrong token is refused");
  assert.equal(s.http("GET", { query: "tok=" + TOK + "&t=99" }).code, 400);
  const r = s.http("GET", { query: "tok=" + TOK + "&t=20.0?hum=48" }); // the H&T appends ?hum=
  assert.equal(r.code, 200);
  assert.equal(r.body.used, true);
  s.run(20, { keepFresh: false });
  assert.equal(s.state().temp, 20.0);
  assert.equal(s.relay, true, "below the band: heats");
  assert.equal(s.state().cfg.sensor, "push");
  s.run(7200, { keepFresh: false });
  assert.equal(s.state().temp, null, "older than sensor_max_age: no reading");
});

test("preheat: the day target starts early by the room's shortfall, and holds until the day (0.79.7)", () => {
  const s = sim({ unix: TUE_13 + 15 * 3600 }); // Wednesday 04:00 local
  post(s, { set: { ctl: "pid", sp_day: 22.5, sp_night: 21, day: "05:30", night: "22:00", cycle: 2700, bias: 0.1,
    pre: 30, pre_max: 120, min_off: 0 } });
  s.setTemp(21.0); s.run(20);
  assert.equal(s.state().period, "night", "1.5 C short = 45 min: not yet at 04:00");
  assert.equal(s.state().sp, 21);
  s.run(43 * 60);
  assert.equal(s.state().period, "night", "04:43");
  s.run(3 * 60);
  assert.equal(s.state().period, "preheat", "from 04:45");
  assert.equal(s.state().sp, 22.5);
  s.run(60);
  assert.equal(s.relay, true, "a new cycle at once on the higher target");
  s.setTemp(22.4); s.run(20 * 60);
  assert.equal(s.state().period, "preheat", "a warming room does not drop it back to night");
  s.run(30 * 60);
  assert.equal(s.state().period, "day");
});

test("preheat: at most pre_max early, none with pre 0 (0.79.7)", () => {
  const s = sim({ unix: TUE_13 + 15 * 3600 }); // 04:00, the day at 05:30
  post(s, { set: { ctl: "pid", sp_day: 22.5, sp_night: 18, day: "05:30", pre: 60, pre_max: 60 } });
  s.setTemp(18.0); s.run(20);
  assert.equal(s.state().period, "night", "4.5 C short but at most 60 min");
  s.run(30 * 60);
  assert.equal(s.state().period, "preheat");
  const z = sim({ unix: TUE_13 + 16 * 3600 + 25 * 60 }); // 05:25
  post(z, { set: { sp_day: 22.5, sp_night: 18, day: "05:30", pre: 0 } });
  z.setTemp(18.0); z.run(20);
  assert.equal(z.state().period, "night");
});

test("boost: far below the target it heats without a break, then the cycle (0.79.8)", () => {
  const s = sim({ unix: TUE_13 }); // 13:00, day
  post(s, { set: { ctl: "pid", sp_day: 22.5, cycle: 2700, bias: 0.1, kp: 0.5, boost: 1.0, boost_end: 0.3, min_off: 0 } });
  s.setTemp(21.0); s.run(60);
  assert.equal(s.state().reason, "boost");
  assert.equal(s.state().boost, true);
  let on = 0;
  for (let i = 0; i < 3600; i += 10) { s.run(10); if (s.relay) on += 10; }
  assert.equal(on, 3600, "no break while 1.5 C short");
  s.setTemp(22.0); s.run(60);
  assert.equal(s.state().boost, true, "0.5 C short: still on");
  s.setTemp(22.3); s.run(20);
  assert.equal(s.state().boost, false, "0.2 C short: the boost ends");
  assert.notEqual(s.state().reason, "boost");
});

test("boost: a small gap is no boost; boost 0 turns it off (0.79.8)", () => {
  const s = sim({ unix: TUE_13 });
  post(s, { set: { ctl: "pid", sp_day: 22.5, boost: 1.0 } });
  s.setTemp(21.8); s.run(60);
  assert.equal(s.state().boost, false);
  const z = sim({ unix: TUE_13 });
  post(z, { set: { ctl: "pid", sp_day: 22.5, boost: 0 } });
  z.setTemp(19.0); z.run(60);
  assert.equal(z.state().boost, false);
});

test("web set-up: the first token only while there is none (0.79.9)", () => {
  const s = new ShellySim({ script: SCRIPT, unix: TUE_13 }); // a new relay: no token
  assert.equal(s.state().token, false);
  assert.equal(s.http("POST", { body: { set: { sp_day: 23 } } }).code, 403, "no token: no change");
  assert.equal(s.http("POST", { body: { init_tok: "short" } }).code, 400);
  assert.equal(s.http("POST", { body: { init_tok: "bad token!!" } }).code, 400);
  assert.equal(s.http("POST", { body: { init_tok: "Abc-12345_x" } }).code, 200);
  assert.equal(s.kvs.hc_lite_token, "Abc-12345_x");
  assert.equal(s.state().token, true);
  assert.equal(s.http("POST", { body: { init_tok: "Other-12345" } }).code, 403, "never over an existing token");
  assert.equal(s.http("POST", { body: { tok: "Abc-12345_x", set: { sp_day: 23 } } }).code, 200);
  assert.equal(s.state().cfg.sp_day, 23);
});

test("web set-up: the settings revision moves on a real change only, and survives a restart (0.79.9)", () => {
  const s = sim({ unix: TUE_13 });
  assert.equal(s.state().rev, 0);
  post(s, { set: { sp_day: 22 } });
  assert.equal(s.state().rev, 1);
  post(s, { set: { sp_day: 22 } });
  assert.equal(s.state().rev, 1, "the same value is no change");
  post(s, { set: { sp_day: 22.5, cycle: 2700 } });
  assert.equal(s.state().rev, 2);
  const r = sim({ unix: TUE_13, kvs: { ...s.kvs } });
  assert.equal(r.state().rev, 2);
});

test("web set-up: the page loads the set-up program from its address (0.79.9)", () => {
  const s = sim({ unix: TUE_13 });
  let r = s.http("GET", { query: "page=1" });
  assert.match(r.body, /<meta charset=utf-8>/);
  assert.match(r.body, /<script src='https:\/\/cdn\.jsdelivr\.net\/gh\/[^']+\/hc_lite_ui\.js' charset=utf-8><\/script>$/);
  assert.equal(post(s, { ui_src: "javascript:alert(1)" }).code, 200);
  assert.doesNotMatch(s.http("GET", { query: "page=1" }).body, /javascript:/, "only an http(s) address");
  post(s, { ui_src: "http://192.168.1.10:8123/local/hc_lite_ui.js" });
  r = s.http("GET", { query: "page=1" });
  assert.match(r.body, /src='http:\/\/192\.168\.1\.10:8123\/local\/hc_lite_ui\.js'/);
  assert.equal(s.kvs.hc_lite_ui, "http://192.168.1.10:8123/local/hc_lite_ui.js");
});

test("web set-up: the browser program parses and is plain JS (0.79.9)", () => {
  const src = readFileSync(new URL("../shelly/hc_lite_ui.js", import.meta.url), "utf8");
  assert.doesNotThrow(() => new Function(src));
  for (const k of ["init_tok", "Shelly.GetComponents", "Script.SetConfig", "sensor_max_age", "${ev.tC}"]) assert.ok(src.includes(k), k);
});

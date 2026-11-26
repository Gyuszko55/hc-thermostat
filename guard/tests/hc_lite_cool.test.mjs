// 0.80.0: HC Lite with a heat pump – cooling, the dew point, buffer probes, the settings kept in parts
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ShellySim } from "./shelly_sim.mjs";

// 0.80.0: HC_LITE_MIN=1 runs the same tests on the compact file that goes to the relay (hc_lite_min.test.mjs)
const SCRIPT = fileURLToPath(new URL(process.env.HC_LITE_MIN ? "../shelly/hc_lite.min.js" : "../shelly/hc_lite.js", import.meta.url));
const TOK = "t0ken";
const TUE_13 = Date.UTC(2026, 10, 24, 12, 0, 0) / 1000; // Tuesday 13:00 local
const sim = (o = {}) => new ShellySim({ script: SCRIPT, unix: TUE_13, ...o, kvs: { hc_lite_token: TOK, ...(o.kvs || {}) } });
const post = (s, b) => s.http("POST", { body: { tok: TOK, ...b } });
const hp = (s, set = {}) => { post(s, { set: { src: "hp", min_on: 600, min_off: 300, ...set } }); return post(s, { hvac: "cool" }); };

test("cooling needs a heat pump", () => {
  const s = sim();
  s.setTemp(27); s.run(20);
  assert.equal(post(s, { hvac: "cool" }).code, 400);
  assert.equal(s.state().hvac, "heat");
  assert.equal(hp(s).code, 200);
  assert.equal(s.state().hvac, "cool");
  post(s, { set: { src: "gas" } });
  assert.equal(s.state().hvac, "heat", "a gas boiler never cools");
});

test("cooling: on above the band, off below it, its own targets", () => {
  const s = sim();
  s.setTemp(26.0); s.run(20);
  hp(s); s.run(320);
  assert.equal(s.state().sp, 25.0, "the day cooling target");
  assert.equal(s.relay, true);
  assert.equal(s.state().reason, "above target");
  s.setTemp(25.1); s.run(700);
  assert.equal(s.relay, true, "inside the band nothing changes");
  s.setTemp(24.75); s.run(20);
  assert.equal(s.relay, false);
  assert.equal(s.state().reason, "target reached");
  post(s, { mode: "away" });
  assert.equal(s.state().sp, 28.0);
  const n = sim({ unix: TUE_13 + 9 * 3600 + 60 }); // 22:01
  n.setTemp(25.0); n.run(20); hp(n); n.run(20);
  assert.equal(n.state().sp, 26.0, "the night cooling target");
});

test("cooling: off is off, no reading is off (no duty, no frost), no boost, no preheat", () => {
  const s = sim();
  s.setTemp(27); s.run(20);
  hp(s, { boost: 1, ctl: "tpi", pre: 60 }); s.run(320);
  assert.equal(s.relay, true);
  assert.equal(s.state().boost, false, "no boost in cooling");
  s.run(700);
  post(s, { mode: "off" }); s.run(20);
  assert.equal(s.state().sp, null);
  assert.equal(s.relay, false);
  post(s, { mode: "auto" });
  s.setTemp(null); s.run(3600);
  assert.equal(s.relay, false, "no safe duty in cooling");
  assert.equal(s.state().reason, "no reading");
  const e = sim({ unix: TUE_13 - 8 * 3600 }); // 05:00, day at 06:00
  e.setTemp(27); e.run(20); hp(e, { pre: 60 }); e.run(20);
  assert.equal(e.state().period, "night", "no preheat in cooling");
});

test("cooling with TPI / PI: the demand grows with the room above the target", () => {
  const s = sim();
  s.setTemp(26.0); s.run(20);
  hp(s, { ctl: "pid", kp: 0.5, bias: 0.1 }); s.run(20);
  assert.ok(s.state().demand > 0.5, "1 C above: bias + kp");
  s.setTemp(24.0); s.run(20);
  assert.equal(s.state().demand, 0, "1 C below: none");
});

test("dew point: from the room's humidity (BTHome, add-on, the Wi-Fi H&T's push)", () => {
  const s = sim();
  s.bt[201] = 60;
  post(s, { set: { hum_id: 201 } });
  s.setTemp(25.0); s.run(20);
  assert.equal(s.state().hum, 60);
  assert.equal(s.state().dew, 16.7, "25 C, 60 %: 16.7 C");
  const a = sim();
  a.hums[100] = 50; post(a, { set: { hum_id: 100 } }); a.setTemp(20); a.run(20);
  assert.equal(a.state().dew, 9.3);
  const p = sim({ kvs: { hc_lite_cfg: JSON.stringify({ sensor: "push", sensor_max_age: 7200 }) } });
  p.http("GET", { query: `tok=${TOK}&t=25.0?hum=60` });
  assert.equal(p.state().hum, 60);
  assert.equal(p.state().dew, 16.7);
});

test("dew point: a cold flow pipe stops cooling at once (min on or not), 1 C above it cools again", () => {
  const s = sim();
  s.bt[201] = 60; s.probes[101] = 22;
  s.setTemp(27); s.run(20);
  hp(s, { hum_id: 201, dew_id: 101, dew_margin: 2 }); s.run(320);
  assert.equal(s.relay, true);
  s.probes[101] = 18.5; s.run(20); // dew point 18.8 at 27 C / 60 %: below 20.8
  assert.equal(s.relay, false, "off before min on");
  assert.equal(s.state().reason, "dew point");
  assert.equal(s.state().dew_stop, true);
  s.probes[101] = 21.0; s.run(400);
  assert.equal(s.relay, false, "inside the 1 C band it stays off");
  s.probes[101] = 22.0; s.run(20);
  assert.equal(s.relay, true);
  delete s.bt[201]; s.run(700);
  assert.equal(s.relay, false, "a pipe probe without a humidity: no cooling");
});

test("dew point without a pipe probe only warns", () => {
  const s = sim();
  s.bt[201] = 90; s.setTemp(27); s.run(20);
  hp(s, { hum_id: 201 }); s.run(320);
  assert.equal(s.relay, true);
  assert.equal(s.state().dew_warn, true);
  assert.equal(s.state().dew_stop, false);
});

test("buffer probes are shown, never steer", () => {
  const s = sim();
  s.probes[100] = 55.5; s.probes[102] = 38.0;
  s.setTemp(20); s.run(20);
  post(s, { set: { buf: [100, 101, 102, 103], bufn: ["teteje", "közepe", "alja"] } });
  assert.deepEqual(s.state().cfg.buf, [100, 101, 102], "at most 3");
  assert.deepEqual(s.state().buf, [55.5, null, 38.0]);
  assert.deepEqual(s.state().cfg.bufn, ["teteje", "közepe", "alja"]);
  s.run(320);
  assert.equal(s.relay, true, "it heats by the room only");
});

test("every setting survives a restart (parts under 255 characters), the cooling too", () => {
  const s = sim();
  s.setTemp(26); s.run(20);
  hp(s, { sc_day: 24.5, hum_id: 201, dew_id: 101, buf: [100, 102], bufn: ["puffer teteje", "puffer alja"], sp_day: 22 });
  assert.equal(s.kvsRefused || 0, 0, "no KVS value refused");
  assert.equal(s.kvs.hc_lite_cfg, "{}");
  const cfg = s.state().cfg;
  const again = new ShellySim({ script: SCRIPT, kvs: s.kvs, unix: TUE_13 });
  again.setTemp(26); again.run(20);
  assert.deepEqual(again.state().cfg, cfg);
  assert.equal(again.state().hvac, "cool");
});

test("an upload tool's hc_lite_cfg wins over the parts", () => {
  const s = sim();
  s.setTemp(20); s.run(20);
  post(s, { set: { sp_day: 22, shadow: false } });
  const kv = { ...s.kvs, hc_lite_cfg: JSON.stringify({ sensor: "temperature", sensor_id: 100, shadow: true }) };
  const again = new ShellySim({ script: SCRIPT, kvs: kv, unix: TUE_13 });
  again.run(20);
  assert.equal(again.state().cfg.sp_day, 22);
  assert.equal(again.state().cfg.shadow, true);
  assert.equal(again.state().cfg.sensor, "temperature");
});

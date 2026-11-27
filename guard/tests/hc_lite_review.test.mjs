// 0.82.2: the cases of an outside review of HC Lite 0.82.0, run on the desk Shelly
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ShellySim } from "./shelly_sim.mjs";

const SCRIPT = fileURLToPath(new URL(process.env.HC_LITE_MIN ? "../shelly/hc_lite.min.js" : "../shelly/hc_lite.js", import.meta.url));
const TOK = "t0ken";
const TUE_13 = Date.UTC(2026, 10, 24, 12, 0, 0) / 1000;
const sim = (o = {}) => new ShellySim({ script: SCRIPT, kvs: { hc_lite_token: TOK, ...(o.kvs || {}) }, unix: TUE_13, ...o });
const post = (s, b) => s.http("POST", { body: { tok: TOK, ...b } });

function heatMinutes(s, seconds) {
  let on = 0, starts = 0, prev = s.relay;
  for (let i = 0; i < seconds; i += 10) {
    s.run(10, { keepFresh: false });
    if (s.relay) on += 10;
    if (s.relay && !prev) starts++;
    prev = s.relay;
  }
  return { min: on / 60, starts };
}

test("a body that is valid JSON but not an object is refused, the script goes on", () => {
  const s = sim();
  s.setTemp(20.0); s.run(20);
  for (const b of ["null", "5", "\"x\"", "true", "[]"]) {
    const r = s.http("POST", { body: b });
    if (b === "[]") { assert.notEqual(r.code, 200, "an array is no command either"); continue; }
    assert.equal(r.code, 400, b);
  }
  s.run(400);
  assert.equal(s.relay, true, "it still heats");
});

test("no reading: off and an open window never run the safe duty", () => {
  for (const cmd of [{ mode: "off" }, { window: true, for: 7200 }]) {
    const s = sim();
    s.setTemp(20.0); s.run(20);
    post(s, cmd);
    s.setTemp(null);
    const h = heatMinutes(s, cmd.window ? 7000 : 6 * 3600); // the window ends by itself after 2 hours
    assert.equal(h.min, 0, JSON.stringify(cmd));
    assert.equal(s.state().reason, "no reading");
  }
});

test("no reading while away or on vacation: the safe duty stays (frost in winter)", () => {
  const s = sim();
  s.setTemp(20.0); s.run(20);
  post(s, { mode: "away" });
  s.setTemp(null);
  assert.ok(heatMinutes(s, 6 * 3600).min > 0);
});

test("no clock: a fresh BLU reading is used (its age by the uptime)", () => {
  const s = sim();
  s.timeSynced = false;
  s.setTemp(21.5); s.run(60);
  const st = s.state();
  assert.equal(st.temp, 21.5);
  assert.ok(st.temp_age <= 60);
  assert.notEqual(st.reason, "no reading: duty on");
});

test("no clock: a reading that stops changing goes stale after sensor_max_age", () => {
  const s = sim();
  s.timeSynced = false;
  s.setTemp(21.5); s.run(60);
  s.run(1900, { keepFresh: false });
  assert.equal(s.state().temp, null);
});

test("with a clock the first reading seen keeps its real age", () => {
  const s = sim();
  s.setTemp(21.5, 3000); s.run(5, { keepFresh: false });
  assert.equal(s.state().temp, null, "50 minutes old at start: too old");
});

test("switched off by hand while heating: min off counts from then", () => {
  const s = sim();
  s.setTemp(19.0); s.run(400);
  assert.equal(s.relay, true);
  s.run(200);
  s.relay = false; s.offAt = null; // by hand, in the Shelly app
  s.run(250);
  assert.equal(s.relay, false, "300 s min off from the hand switch");
  s.run(80);
  assert.equal(s.relay, true);
});

test("TPI: a noisy reading gives one start per cycle", () => {
  const s = sim();
  post(s, { set: { ctl: "tpi", cycle: 1800, kp: 0.5, bias: 0.15, min_on: 300, min_off: 300 } });
  let starts = 0, prev = s.relay, n = 0;
  for (let i = 0; i < 12 * 1800; i += 10) {
    s.setTemp(20.5 + (n++ % 2 ? 0.25 : -0.25));
    s.run(10);
    if (s.relay && !prev) starts++;
    prev = s.relay;
  }
  assert.ok(starts <= 13, `${starts} starts in 12 cycles`);
});

test("push: an empty t= is no reading", () => {
  const s = sim();
  post(s, { set: { sensor: "push" } });
  assert.equal(s.http("GET", { query: `tok=${TOK}&t=` }).code, 400);
  assert.equal(s.http("GET", { query: `tok=${TOK}&t=21.2` }).code, 200);
});

test("the integral goes to KVS only when it moved", () => {
  const s = sim();
  post(s, { set: { ctl: "pid" } });
  s.setTemp(21.0); s.run(20);
  const n = () => s.calls.filter((c) => c[0] === "KVS.Set" && c[1].key === "hc_lite_i").length;
  const n0 = n();
  s.run(6 * 3600);
  assert.ok(n() - n0 <= 1, `${n() - n0} writes at a steady integral`);
});

test("the web set-up comes from the script's own release, not from main", () => {
  const s = sim();
  const page = s.http("GET", { query: "page=1" }).body;
  assert.match(page, /hc-thermostat@v\d+\.\d+\.\d+\/guard\/shelly\/hc_lite_ui\.js/);
  assert.doesNotMatch(page, /@main\//);
  const old = sim({ kvs: { hc_lite_ui: "https://cdn.jsdelivr.net/gh/Gyuszko55/hc-thermostat@main/guard/shelly/hc_lite_ui.js" } });
  assert.doesNotMatch(old.http("GET", { query: "page=1" }).body, /@main\//, "the old default gives way");
  const own = sim({ kvs: { hc_lite_ui: "http://192.0.2.10/ui.js" } });
  assert.match(own.http("GET", { query: "page=1" }).body, /192\.0\.2\.10\/ui\.js/, "a chosen address stays");
  assert.equal(s.state().sv, page.match(/@v(\d+\.\d+\.\d+)\//)[1], "the same version as the script");
});

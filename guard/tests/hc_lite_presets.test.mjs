// 0.82.0: HC Lite presets - comfort, sleep, away with an end, vacation, window, the weekend program today, a BLU button
import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { ShellySim } from "./shelly_sim.mjs";

const SCRIPT = fileURLToPath(new URL(process.env.HC_LITE_MIN ? "../shelly/hc_lite.min.js" : "../shelly/hc_lite.js", import.meta.url));
const TOK = "t0ken";
// Tuesday 2026-11-24, 13:00 local (UTC+1)
const TUE_13 = Date.UTC(2026, 10, 24, 12, 0, 0) / 1000;
const sim = (o = {}) => new ShellySim({ script: SCRIPT, kvs: { hc_lite_token: TOK, ...(o.kvs || {}) }, ...o });
const post = (s, b) => s.http("POST", { body: { tok: TOK, ...b } });
const BTN = (s) => post(s, { set: { btn: 200 } });

test("comfort: the program's target + 1 C for 2 hours, then the program again", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  const r = post(s, { preset: "comfort" }).body;
  assert.equal(r.sp, 22.0);
  assert.equal(r.preset, "comfort");
  assert.equal(r.psrc, "ha");
  assert.equal(r.puntil, TUE_13 + 20 + 7200);
  s.run(7100);
  assert.equal(s.state().sp, 22.0);
  s.run(200);
  assert.equal(s.state().sp, 21.0);
  assert.equal(s.state().preset, "schedule");
});

test("comfort again: 2 more hours, at most 3 x cf_time from now", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { preset: "comfort" });
  const a = post(s, { preset: "comfort" }).body;
  assert.equal(a.puntil, TUE_13 + 20 + 14400);
  assert.equal(a.sp, 22.0, "the target stays (not +2)");
  post(s, { preset: "comfort" }); const c = post(s, { preset: "comfort" }).body;
  assert.equal(c.puntil, TUE_13 + 20 + 3 * 7200);
});

test("comfort settings: cf_delta and cf_time", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { set: { cf_delta: 2.0, cf_time: 3600 } });
  const r = post(s, { preset: "comfort" }).body;
  assert.equal(r.sp, 23.0);
  assert.equal(r.puntil, TUE_13 + 20 + 3600);
  assert.equal(r.cfg.cf_delta, 2.0);
});

test("sleep: the night target until the program changes", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  const r = post(s, { preset: "sleep" }).body;
  assert.equal(r.sp, 19.0);
  assert.equal(r.preset, "sleep");
  assert.match(r.period, /sleep/);
  s.run(9 * 3600); // 22:00: the night begins, the program takes over (also night)
  assert.equal(s.state().preset, "schedule");
  assert.equal(s.state().sp, 19.0);
});

test("away from presence: for 12 hours, then by itself back to the program", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  const r = post(s, { mode: "away", for: 43200 }).body;
  assert.equal(r.sp, 16.0);
  assert.equal(r.preset, "away");
  assert.equal(r.puntil, TUE_13 + 20 + 43200);
  s.run(43100);
  assert.equal(s.state().mode, "away");
  s.run(200);
  assert.equal(s.state().mode, "auto");
  assert.equal(s.state().preset, "schedule");
});

test("away by hand has no end", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  assert.equal(post(s, { mode: "away" }).body.puntil, null);
  s.run(2 * 86400);
  assert.equal(s.state().mode, "away");
});

test("vacation: away until the date, warm on arrival (preheat), then the program", () => {
  const s = sim({ unix: TUE_13 });
  post(s, { set: { pre: 30, pre_max: 120 } });
  s.setTemp(19.0); s.run(20);
  const until = TUE_13 + 2 * 86400; // Thursday 13:00
  const r = post(s, { vacation: until }).body;
  assert.equal(r.preset, "vacation");
  assert.equal(r.sp, 16.0);
  assert.equal(r.vac, until);
  s.run(2 * 86400 - 20 - 3700); // 61 minutes before the end: (21 - 19) * 30 = 60 min preheat not yet
  assert.equal(s.state().sp, 16.0);
  s.run(200);
  assert.equal(s.state().sp, 21.0, "the day target an hour early");
  assert.equal(s.state().period, "vacation preheat");
  s.run(3600);
  assert.equal(s.state().preset, "schedule");
  assert.equal(s.state().vac, null);
});

test("vacation 0 clears it; a date in the past is refused", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { vacation: TUE_13 + 86400 });
  assert.equal(post(s, { vacation: 0 }).body.preset, "schedule");
  assert.equal(post(s, { vacation: TUE_13 - 10 }).body.preset, "schedule");
});

test("window: frost while open, back at once on closing, by itself after `for`", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { preset: "comfort" });
  const r = post(s, { window: true, for: 3600 }).body;
  assert.equal(r.sp, 7.0);
  assert.equal(r.preset, "window");
  assert.equal(post(s, { window: false }).body.sp, 22.0, "the comfort it interrupted goes on");
  post(s, { window: true, for: 600 });
  s.run(620);
  assert.equal(s.state().preset, "comfort");
});

test("order: off > window > vacation > away > comfort", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { preset: "comfort" });
  post(s, { vacation: TUE_13 + 86400 });
  assert.equal(s.state().preset, "vacation");
  post(s, { window: true });
  assert.equal(s.state().preset, "window");
  post(s, { mode: "off" });
  assert.equal(s.state().preset, "off");
  assert.equal(s.state().sp, 7.0);
});

test("home: everything back to the program", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { vacation: TUE_13 + 86400 }); post(s, { window: true }); post(s, { mode: "away" });
  const r = post(s, { preset: "home" }).body;
  assert.equal(r.preset, "schedule");
  assert.equal(r.mode, "auto");
  assert.equal(r.sp, 21.0);
});

test("the weekend program today (a home-office day from the calendar)", () => {
  const s = sim({ unix: Date.UTC(2026, 10, 24, 5, 30) / 1000 }); // Tuesday 06:30 local: a weekday day already
  s.setTemp(20.0); s.run(20);
  assert.equal(s.state().sp, 21.0);
  const r = post(s, { we_today: true }).body;
  assert.equal(r.sp, 19.0, "the weekend day starts at 07:00");
  assert.equal(r.we_today, true);
  s.run(1800);
  assert.equal(s.state().sp, 21.0);
  assert.equal(post(s, { we_today: false }).body.we_today, false, "it can be taken back");
  post(s, { we_today: true });
  s.run(86400); // Wednesday: a weekday again
  assert.equal(s.state().we_today, false);
});

test("the BLU button: one push comfort, two away / back, long all back", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  BTN(s);
  s.emit("bthomedevice:200", "single_push");
  let st = s.state();
  assert.equal(st.preset, "comfort");
  assert.equal(st.psrc, "button");
  assert.equal(st.btn_ev, "single_push");
  s.emit("bthomedevice:200", "double_push");
  assert.equal(s.state().preset, "away");
  s.emit("bthomedevice:200", "double_push");
  assert.equal(s.state().preset, "schedule");
  post(s, { vacation: TUE_13 + 86400 });
  s.emit("bthomedevice:200", "long_push");
  assert.equal(s.state().preset, "schedule");
});

test("the button: only the configured one, and none by default", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  s.emit("bthomedevice:200", "single_push");
  assert.equal(s.state().preset, "schedule", "btn -1: no button");
  BTN(s);
  s.emit("bthomedevice:201", "single_push");
  s.emit("bthomesensor:200", "temperature");
  s.emit("switch:0", "single_push");
  assert.equal(s.state().preset, "schedule");
});

test("one push during away or vacation: someone is home - comfort, away and vacation end", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  BTN(s);
  post(s, { vacation: TUE_13 + 86400 });
  s.emit("bthomedevice:200", "single_push");
  const st = s.state();
  assert.equal(st.preset, "comfort");
  assert.equal(st.vac, null);
  assert.equal(st.sp, 22.0);
});

test("presets survive a restart (KVS)", () => {
  const s = sim({ unix: TUE_13 });
  s.setTemp(20.5); s.run(20);
  post(s, { vacation: TUE_13 + 86400 });
  post(s, { mode: "away", for: 43200 });
  const s2 = sim({ unix: TUE_13 + 60, kvs: s.kvs });
  s2.setTemp(20.5); s2.run(20);
  assert.equal(s2.state().preset, "vacation");
  assert.equal(s2.state().vac, TUE_13 + 86400);
  post(s2, { vacation: 0 });
  assert.equal(s2.state().preset, "away");
  assert.equal(s2.state().puntil, TUE_13 + 20 + 43200);
});

test("an old manual target (no preset field) still reads as manual", () => {
  const s = sim({ unix: TUE_13, kvs: { hc_lite_hold: JSON.stringify({ sp: 22.5, until: -1, at: "day" }) } });
  s.setTemp(20.5); s.run(20);
  assert.equal(s.state().preset, "manual");
  assert.equal(s.state().sp, 22.5);
});

test("cooling: comfort is 1 C cooler, the window stops it", () => {
  const s = sim({ unix: TUE_13 });
  post(s, { set: { src: "hp" } }); post(s, { hvac: "cool" });
  s.setTemp(27.0); s.run(20);
  assert.equal(post(s, { preset: "comfort" }).body.sp, 24.0);
  const r = post(s, { window: true }).body;
  assert.equal(r.sp, null);
  assert.equal(r.relay, false);
});

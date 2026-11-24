"""0.76.0: the local guard script for Shelly Gen3 / Gen4 (guard/shelly/hc_guard.js), run under node against a stub of
the Shelly scripting API (sys uptime, Switch.Set, KVS, HTTPServer, Timer, a BTHome sensor, HTTP.POST)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parents[1] / "guard" / "shelly" / "hc_guard.js"

HARNESS = r"""
const code = require("fs").readFileSync(process.argv[1], "utf8");
let clock = 0, relay = false, sets = [], posts = [], kvs = {}, timers = [], ep = null;
let nosync = false;
let sensor = { value: 19.8, last_updated_ts: 1e9 }, fresh = true, input0 = true, handlers = [], flip = null, dead = false;
const Shelly = {
  addStatusHandler(cb) { handlers.push(cb); },
  getComponentStatus(type, id) {
    if (type === "sys") return { uptime: clock, unixtime: nosync ? 0 : 1e9 + clock };
    if (type === "switch") return { output: relay };
    if (type === "bthomesensor") return sensor;
    if (type === "input") return input0 === null ? null : { id: 0, state: input0 };
    return null;
  },
  call(method, params, cb) {
    if (method === "Switch.Set") { relay = params.on; sets.push([clock, params.on, params.toggle_after]); flip = params.toggle_after ? clock + params.toggle_after : null; }
    else if (method === "HTTP.POST") posts.push(params);
    else if (method === "KVS.Set") kvs[params.key] = params.value;
    else if (method === "KVS.GetMany") { const items = Object.keys(kvs).map((k) => ({ key: k, value: kvs[k] })); cb && cb({ items }); return; }
    cb && cb({});
  },
};
const Timer = { set(ms, rep, cb) { timers.push(cb); return timers.length; }, clear() {} };
const HTTPServer = { registerEndpoint(name, cb) { ep = cb; } };
const print = () => {};
const api = {
  advance(s) { for (let i = 0; i < s; i += 10) { clock += 10; if (fresh) sensor.last_updated_ts = 1e9 + clock;
    if (flip !== null && clock >= flip) { relay = !relay; flip = null; }  // the relay's own flip-back timer
    if (!dead) timers.forEach((t) => t()); } },
  call(method, body) { let out = null; ep({ method, body: body === undefined ? "" : JSON.stringify(body) }, { send() { out = { code: this.code, body: JSON.parse(this.body) }; } }); return out; },
  get relay() { return relay; }, set relayRaw(v) { relay = v; },
  get clock() { return clock; }, sensor, posts, sets, kvs,
};
const preset = JSON.parse(process.argv[2] || "{}");
const DEFTOK = "t0k";  // 0.78.2: the token is required - every test runs with one unless it says otherwise
Object.assign(kvs, preset.kvs || {});
if (preset.relay) relay = true;
new Function("Shelly", "Timer", "HTTPServer", "print", code)(Shelly, Timer, HTTPServer, print);
const steps = JSON.parse(process.argv[3]);
const out = [];
const FB = { sp: 20.5, hyst: 0.6, min_on: 300, min_off: 300, push: "http://ntfy.local/topic" };
for (const s of steps) {
  if (s.dead) dead = true;  // the script stopped: no more ticks
  if (s.nosync !== undefined) nosync = s.nosync;  // 0.78.2: the device's clock not synced
  if (s.inp !== undefined) { input0 = s.inp; handlers.forEach((h) => h({ name: "input", id: 0, delta: { state: s.inp } })); }
  if (s.temp !== undefined) { if (s.temp === null) api.sensor.value = undefined; else api.sensor.value = s.temp; }
  if (s.stale) { fresh = false; api.sensor.last_updated_ts = 1e9 + api.clock - 5000; }
  if (s.adv) api.advance(s.adv);
  if (s.lease) out.push(api.call("POST", { cmd: s.lease, ttl: s.ttl || 300, seq: 1, fb: Object.assign({}, FB, s.fb || {}), tok: s.tok === undefined ? (kvs.hc_guard_token || "") : s.tok }));
  if (s.raw !== undefined) { let r = null; ep({ method: "POST", body: s.raw }, { send() { r = { code: this.code }; } }); out.push(r); }
  if (s.get) out.push(api.call("GET"));
  if (s.q !== undefined) { let r = null; const q = (s.q.indexOf("tok=") < 0 && kvs.hc_guard_token === DEFTOK) ? "tok=" + DEFTOK + "&" + s.q : s.q; ep({ method: "GET", query: q, body: "" }, { send() { r = { code: this.code, body: JSON.parse(this.body) }; } }); out.push(r); }
  if (s.snap) out.push({ snap: s.snap, relay: api.relay, mode: api.call("GET").body.mode, clock: api.clock, posts: api.posts.length,
                       sets: api.sets.slice(), kvs: Object.assign({}, api.kvs) });
}
console.log(JSON.stringify(out));
"""


def run(steps, preset=None, settle=True):
    """settle: start 5 minutes after the script's start, past the min_off it keeps at start (0.77.2)."""
    if settle:
        steps = [{"adv": 300}] + list(steps)
    preset = dict(preset or {})
    if not preset.pop("no_token", False):  # 0.78.2: the token is required – a default one unless the test sets its own
        preset["kvs"] = {"hc_guard_token": "t0k", **(preset.get("kvs") or {})}
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    res = subprocess.run([node, "-e", HARNESS, str(GUARD), json.dumps(preset or {}), json.dumps(steps)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def snaps(out):
    return {o["snap"]: o for o in out if "snap" in o}


def test_plain_ascii_and_small():
    raw = GUARD.read_bytes()
    assert all(b < 128 for b in raw), "Script.PutCode needs plain ASCII"
    assert len(raw) < 15000
    assert "=>" not in raw.decode() and "`" not in raw.decode()  # no arrow functions, no template strings


def test_boot_is_fallback_and_the_local_thermostat_heats():
    s = snaps(run([{"snap": "boot"}, {"adv": 30, "snap": "cold"}, {"temp": 21.0, "adv": 320, "snap": "warm"}]))
    assert s["boot"]["mode"] == "fallback" and s["boot"]["relay"]  # 19.8 <= 20.5 - 0.3: on at once
    assert s["warm"]["relay"] is False  # 21.0 >= 20.8 after min_on


def test_lease_handback_needs_two_minutes_and_two_renewals():
    s = snaps(run([{"lease": "off"}, {"snap": "hb"}, {"adv": 60, "lease": "off"}, {"adv": 60, "lease": "off"},
                   {"adv": 10, "snap": "normal"}, {"adv": 300, "snap": "off"}]))
    assert s["hb"]["mode"] == "handback" and s["hb"]["relay"]  # the guard still heats while it hands back
    assert s["normal"]["mode"] == "normal"
    assert s["off"]["relay"] is False  # HC said off (after the guard's min_on)


def to_normal():
    return [{"lease": "off"}, {"adv": 60, "lease": "off"}, {"adv": 70, "lease": "off"}, {"adv": 10}]


def test_lost_lease_grace_then_fallback_with_one_push():
    s = snaps(run(to_normal() + [{"adv": 60, "lease": "off"}] * 12 + [{"lease": "on"}, {"adv": 20, "snap": "on"},
                                 {"adv": 300, "snap": "grace"}, {"temp": 21.5, "adv": 200, "snap": "still_grace"},
                                 {"adv": 120, "snap": "fallback"}, {"adv": 600, "snap": "later"}]))
    assert s["on"]["mode"] == "normal" and s["on"]["relay"]
    assert s["grace"]["mode"] == "grace" and s["grace"]["relay"]  # the last command stays
    assert s["still_grace"]["mode"] == "grace" and s["still_grace"]["relay"]
    assert s["fallback"]["mode"] == "fallback" and s["fallback"]["relay"] is False  # 21.5: warm enough
    assert s["fallback"]["posts"] == 1 and s["later"]["posts"] == 1  # one push per takeover


def test_renewed_within_grace_goes_back_to_normal_without_handback():
    s = snaps(run(to_normal() + [{"adv": 400, "snap": "grace"}, {"lease": "on"}, {"snap": "back"}]))
    assert s["grace"]["mode"] == "grace" and s["back"]["mode"] == "normal"


def test_handback_interrupted_returns_to_fallback():
    s = snaps(run([{"lease": "off", "ttl": 60}, {"adv": 70, "snap": "lost"}]))
    assert s["lost"]["mode"] == "fallback"


def test_sensor_lost_off_or_duty():
    s = snaps(run([{"adv": 20}, {"temp": None, "adv": 320, "snap": "off"}]))
    assert s["off"]["mode"] == "nosensor" and s["off"]["relay"] is False
    duty = {"kvs": {"hc_guard_fb": json.dumps({"sp": 20.5, "hyst": 0.6, "min_on": 300, "min_off": 300, "max_on": 0,
                                               "ns": "duty", "don": 600, "doff": 1200, "push": ""})}}
    out = run([{"temp": None, "adv": 10, "snap": "a"}, {"adv": 600, "snap": "b"}, {"adv": 1200, "snap": "c"},
               {"temp": 19.0, "adv": 10, "snap": "d"}], duty)
    s = snaps(out)
    assert s["a"]["mode"] == "nosensor" and s["a"]["relay"]  # was on from boot: runs its don
    assert s["b"]["relay"] is False and s["c"]["relay"]
    assert s["d"]["mode"] == "fallback"


def test_stale_sensor_is_no_sensor():
    s = snaps(run([{"adv": 10, "stale": True, "snap": "x"}, {"adv": 10, "stale": True, "snap": "y"}]))
    assert s["y"]["mode"] == "nosensor"


def test_minimum_times_hold_in_normal_mode():
    out = run(to_normal() + [{"adv": 60, "lease": "off"}] * 12 + [{"lease": "on"}, {"adv": 10, "snap": "on"}, {"lease": "off"},
                             {"adv": 10, "snap": "too_soon"}, {"adv": 300, "lease": "off", "snap": "off"},
                             {"lease": "on"}, {"adv": 10, "snap": "pause"}, {"adv": 300, "lease": "on", "snap": "again"}])
    s = snaps(out)
    assert s["on"]["relay"] and s["too_soon"]["relay"]  # min_on 300 s
    assert s["off"]["relay"] is False and s["pause"]["relay"] is False  # min_off 300 s
    assert s["again"]["relay"]


def test_max_on_in_normal_mode():
    s = snaps(run(to_normal() + [{"adv": 60, "lease": "off"}] * 12 + [{"lease": "on", "fb": {"max_on": 600}}, {"adv": 10, "snap": "on"},
                                 {"adv": 60, "lease": "on", "fb": {"max_on": 600}}, {"adv": 540, "lease": "on", "fb": {"max_on": 600}},
                                 {"adv": 20, "snap": "cut"}]))
    assert s["on"]["relay"] and s["cut"]["relay"] is False


def test_token_bad_input_and_status_only_get():
    out = run([{"get": True}, {"raw": "{not json"}, {"lease": "maybe"}],
              {"kvs": {}})
    assert out[0]["code"] == 200 and out[0]["body"]["mode"] == "fallback" and out[0]["body"]["lease_left"] == 0
    assert out[1]["code"] == 400 and out[2]["code"] == 400
    out = run([{"lease": "on", "tok": "wrong"}, {"lease": "on", "tok": "s3cret"}], {"kvs": {"hc_guard_token": "s3cret"}})
    assert out[0]["code"] == 403 and out[1]["code"] == 200 and out[1]["body"]["mode"] == "handback"


def test_fallback_values_from_hc_are_kept_in_kvs():
    out = run([{"lease": "off", "fb": {"sp": 19.0}}, {"get": True}])
    assert out[1]["body"]["sp"] == 19.0


def test_a_pushed_temperature_from_a_wifi_ht():
    none = {"kvs": {"hc_guard_sensor": "none"}}
    out = run([{"adv": 10, "snap": "nosensor"}, {"q": "t=19.6"}, {"adv": 10, "snap": "heat"}], none)
    s = snaps(out)
    assert s["nosensor"]["mode"] == "nosensor" and s["nosensor"]["relay"] is False
    push = [o for o in out if o and o.get("code")][0]
    assert push["code"] == 200 and push["body"]["temp"] == 19.6 and push["body"]["temp_src"] == "push"
    assert s["heat"]["mode"] == "fallback" and s["heat"]["relay"]
    # the Gen1 H&T appends "?hum=..&temp=.." to a report URL that already has "?tok=.."
    tok = {"kvs": {"hc_guard_sensor": "none", "hc_guard_token": "k1"}}
    out = run([{"q": "tok=k1?hum=45&temp=21.5&id=shellyht-1"}, {"q": "t=21.5"}, {"q": "tok=k1&t=99"}], tok)
    assert out[0]["code"] == 200 and out[0]["body"]["temp"] == 21.5
    assert out[1]["code"] == 403 and out[2]["code"] == 400


def test_a_pushed_temperature_ages_out_after_2_hours():  # 0.78.2: was 4 hours
    s = snaps(run([{"q": "t=19.0"}, {"adv": 7190, "snap": "kept"}, {"adv": 30, "snap": "old"}],
                  {"kvs": {"hc_guard_sensor": "none"}}))
    assert s["kept"]["mode"] == "fallback" and s["old"]["mode"] == "nosensor"


def test_the_bluetooth_sensor_comes_first():
    out = run([{"q": "t=25.0"}, {"adv": 10}, {"get": True}])
    assert out[-1]["body"]["temp"] == 19.8 and out[-1]["body"]["temp_src"] == "local"


SAFE = {"kvs": {"hc_guard_safety": "input:0:on"}}


def test_the_safety_chain_input_switches_off_at_once_whatever_the_lease():
    steps = [{"lease": "off"}, {"adv": 60, "lease": "off"}, {"adv": 70, "lease": "off"}, {"adv": 10},
             {"adv": 60, "lease": "on"}, {"adv": 20, "snap": "on"},
             {"inp": False, "snap": "stop"},  # min_on not waited for
             {"adv": 60, "lease": "on"}, {"adv": 10, "snap": "still"},
             {"inp": True, "adv": 10, "snap": "closed"}]
    out = run(steps, SAFE)
    s = snaps(out)
    assert s["on"]["mode"] == "normal" and s["on"]["relay"]
    assert s["stop"]["mode"] == "safety" and s["stop"]["relay"] is False and s["stop"]["posts"] >= 0
    assert s["still"]["mode"] == "safety" and s["still"]["relay"] is False  # a lease changes nothing
    assert s["closed"]["mode"] in ("fallback", "handback")  # back through the usual handback


def test_an_unreadable_safety_input_counts_as_open():
    s = snaps(run([{"inp": None, "adv": 10, "snap": "x"}], SAFE))
    assert s["x"]["mode"] == "safety" and s["x"]["relay"] is False


def test_without_a_safety_input_nothing_changes():
    s = snaps(run([{"inp": False, "adv": 10, "snap": "x"}]))
    assert s["x"]["mode"] != "safety"


# 0.77.1: the dead man – every "on" carries the relay's own off timer, re-armed while the script runs


def test_every_on_carries_the_dead_man_timer_and_no_off_does():
    s = snaps(run([{"adv": 30}, {"temp": 21.0, "adv": 400, "snap": "x"}]))
    sets = s["x"]["sets"]
    ons = [x for x in sets if x[1] is True]
    offs = [x for x in sets if x[1] is False]
    assert ons and all(x[2] == 180 for x in ons)
    assert offs and all(x[2] is None for x in offs)  # an "off" with a flip-back would switch the boiler ON later


def test_a_running_script_keeps_a_long_burn_on():
    s = snaps(run([{"adv": 1800, "snap": "x"}]))  # 19.8 C, below the band: one long fallback burn
    assert s["x"]["relay"] is True
    rearms = [x for x in s["x"]["sets"] if x[1] is True]
    assert len(rearms) >= 1800 // 60 - 1  # re-armed every minute


def test_a_stopped_script_lets_the_relay_fall_off_by_itself():
    s = snaps(run([{"adv": 100, "snap": "on"}, {"dead": True, "adv": 120, "snap": "soon"},
                   {"adv": 120, "snap": "later"}]))
    assert s["on"]["relay"] is True
    assert s["soon"]["relay"] is True  # within 180 s of the last re-arm
    assert s["later"]["relay"] is False  # no script, no heat


def test_the_dead_man_from_kvs_or_off():
    s = snaps(run([{"adv": 30, "snap": "x"}], {"kvs": {"hc_guard_deadman": "600"}}))
    assert all(x[2] == 600 for x in s["x"]["sets"] if x[1] is True)
    s = snaps(run([{"adv": 30, "snap": "x"}, {"dead": True, "adv": 900, "snap": "y"}], {"kvs": {"hc_guard_deadman": "0"}}))
    assert all(x[2] is None for x in s["x"]["sets"]) and s["y"]["relay"] is True  # switched off on purpose: stays
    s = snaps(run([{"adv": 30, "snap": "x"}], {"kvs": {"hc_guard_deadman": "5"}}))  # nonsense: the default stays
    assert all(x[2] == 180 for x in s["x"]["sets"] if x[1] is True)
    assert run([{"get": True}])[0]["body"]["dm"] == 180


# 0.77.2: a start with the relay off (power-up, a restart after the dead man cut in) keeps min_off


def test_a_start_with_the_relay_off_keeps_min_off_before_heating():
    s = snaps(run([{"snap": "start"}, {"adv": 290, "snap": "wait"}, {"adv": 20, "snap": "heat"}], settle=False))
    assert s["start"]["mode"] == "fallback" and s["start"]["relay"] is False  # 19.8 C is cold, but min_off first
    assert s["wait"]["relay"] is False
    assert s["heat"]["relay"] is True


def test_a_start_with_the_relay_on_may_switch_off_at_once():
    out = run([{"temp": 22.0, "adv": 10, "snap": "x"}], {"relay": True}, settle=False)
    assert snaps(out)["x"]["relay"] is False  # too warm: no min_on to wait for after a restart

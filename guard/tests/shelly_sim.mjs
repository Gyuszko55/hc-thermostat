// A small Shelly Gen3/Gen4 script runtime for desk tests: clock, relay (with toggle_after), a BTHome sensor, KVS,
// the script's HTTP endpoint and its timers. The script runs unchanged in a node:vm context.
import { readFileSync } from "node:fs";
import vm from "node:vm";

export class ShellySim {
  constructor({ script, kvs = {}, unix = Date.UTC(2026, 10, 24, 12, 0, 0) / 1000, tzMin = 60, auth = false, relay = false } = {}) {
    this.uptime = 1000;
    this.unix = unix;           // UTC seconds
    this.tzMin = tzMin;         // local offset, minutes
    this.timeSynced = true;
    this.auth = auth;
    this.relay = relay;
    this.offAt = null;          // uptime of the toggle_after flip-back
    this.sensor = null;         // {value, ts}
    this.kvs = { ...kvs };
    this.calls = [];
    this.timers = [];
    this.endpoints = {};
    this.stopped = false;
    this.printed = [];
    this.probes = {};           // wired add-on probes by id: temperature:<id>.tC
    this.hums = {};             // add-on DHT22 humidity by id: humidity:<id>.rh
    this.bt = {};               // other BTHome objects by id (e.g. a humidity)
    const self = this;
    const Shelly = {
      getComponentStatus(name, id) { return self.status(name, id); },
      getDeviceInfo() { return { id: "shelly1minig4-sim", auth_en: self.auth }; },
      call(method, params, cb) { const r = self.rpc(method, params); if (cb) cb(r, 0, ""); },
      addStatusHandler() {},
    };
    const ctx = {
      Shelly,
      Timer: { set(ms, repeat, fn) { self.timers.push({ every: ms / 1000, next: self.uptime + ms / 1000, repeat, fn }); return self.timers.length; } },
      HTTPServer: { registerEndpoint(name, fn) { self.endpoints[name] = fn; } },
      print(s) { self.printed.push(String(s)); },
      JSON, Math, Number, String, Object,
    };
    vm.createContext(ctx);
    vm.runInContext(readFileSync(script, "utf8"), ctx, { filename: script });
  }

  localTime() {
    const m = Math.floor(this.unix / 60) + this.tzMin;
    const mm = ((m % 1440) + 1440) % 1440;
    return `${String(Math.floor(mm / 60)).padStart(2, "0")}:${String(mm % 60).padStart(2, "0")}`;
  }

  status(name, id) {
    if (name === "sys") {
      return this.timeSynced ? { uptime: this.uptime, unixtime: this.unix, time: this.localTime() } : { uptime: this.uptime, unixtime: null, time: null };
    }
    if (name === "switch" && id === 0) return { id: 0, output: this.relay };
    if (name === "temperature" && id === 100 && this.probe !== undefined) return { id: 100, tC: this.probe };
    if (name === "temperature" && this.probes[id] !== undefined) return { id, tC: this.probes[id] };
    if (name === "humidity" && this.hums[id] !== undefined) return { id, rh: this.hums[id] };
    if (name === "bthomesensor" && id === 200) {
      return this.sensor ? { id: 200, value: this.sensor.value, last_updated_ts: this.sensor.ts } : null;
    }
    if (name === "bthomesensor" && this.bt[id] !== undefined) return { id, value: this.bt[id], last_updated_ts: this.unix };
    return null;
  }

  rpc(method, p) {
    this.calls.push([method, p]);
    if (method === "Switch.Set") {
      this.relay = !!p.on;
      this.offAt = p.on && p.toggle_after ? this.uptime + p.toggle_after : null;
      return { was_on: !p.on };
    }
    if (method === "KVS.Set") { // a real device refuses a value of 255 characters or more
      if (JSON.stringify(String(p.value)).length - 2 >= 255 || Buffer.byteLength(String(p.value)) >= 255) { // counted escaped, as a real one does
        this.kvsRefused = (this.kvsRefused || 0) + 1; return null; }
      this.kvs[p.key] = p.value; return { etag: "x" };
    }
    if (method === "KVS.GetMany") {
      return { items: Object.entries(this.kvs).filter(([k]) => k.startsWith(p.match.replace("*", ""))).map(([key, value]) => ({ key, value })) };
    }
    return {};
  }

  setTemp(value, ageS = 0) { this.sensor = value === null ? null : { value, ts: this.unix - ageS }; }

  // advance the clock; a reading taken `keepFresh` keeps its age at 0 (a sensor that keeps reporting)
  run(seconds, { keepFresh = true } = {}) {
    const end = this.uptime + seconds;
    while (this.uptime < end) {
      this.uptime += 1; this.unix += 1;
      if (keepFresh && this.sensor) this.sensor.ts = this.unix;
      if (this.offAt !== null && this.uptime >= this.offAt) { this.relay = !this.relay; this.offAt = null; }
      if (this.stopped) continue;
      for (const t of this.timers) {
        if (this.uptime >= t.next) { t.next += t.every; t.fn(); }
      }
    }
  }

  http(method, { body = "", query = "" } = {}) {
    const res = { send() {} };
    this.endpoints.lite({ method, body: typeof body === "string" ? body : JSON.stringify(body), query }, res);
    return { code: res.code, body: res.headers?.[0]?.[1] === "application/json" ? JSON.parse(res.body) : res.body };
  }

  state() { return this.http("GET").body; }
}

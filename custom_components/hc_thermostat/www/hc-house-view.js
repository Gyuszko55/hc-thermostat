// hc-house-view.js — illustrated cutaway "live house" for the HC Thermostat info panel (0.44.0).
// Vanilla ES module, no build step, no external libraries or fonts. Served next to hc-info-panel.js.
// 0.44.0: fromInfo() reads the info JSON's own room list (`room_list`, in the order of the host's `rooms` option =
// the drawing order), `entity_areas`, `areas`, `floors`, `sun`, `heat_today` and `pipes`; extras still override.
//
// Usage
//   import { fromInfo, renderHouse } from "./hc-house-view.js";   // also defines <hc-house-view>
//   el.extras = { areas, floors, entityAreas, lang, sun, gasToday, ... };   // optional, set first
//   el.info = infoJson;          // websocket hc_thermostat/info result  -> fromInfo() -> model
//   el.model = viewModel;        // ...or hand over a ready view model
//   el.dark = true|false;        // or attribute dark / hass.themes.darkMode / auto from --card-background-color
//   el.addEventListener("hc-house-select", (e) => e.detail.key)   // "outdoor" | "hc" | "source" | "gas" | "room:<key>" | "trv:<entity_id>"
//
// ───────────────────────────── VIEW MODEL ─────────────────────────────
// {
//   lang: "hu" | "en",
//   title: "Boiler HC",                      // shown on the gable
//   subtitle: "Szabályoz: cél 22,5 °C …",  // optional, short status text
//   mode: "active" | "shadow" | "off",
//   target: 22.5, indoor: 22.6,            // HC (house / leading room) target and reading
//   demand: 0..1 | null,                   // controller output; drives flow animation speed
//   night: bool,                           // sky / lit rooms (sun below horizon)
//   outdoor: { temp, avg } | null,         // avg = 24 h average
//   presence: { state: "home"|"away"|"vacation"|"unknown", who: ["Anna", …] } | null,   // house level
//   doors: [{ name, open }],               // house-level openings that could not be placed in a room
//   source: {
//     kind: "gas_boiler" | "modulating_boiler" | "heat_pump" | "electric_boiler" | "pellet_boiler"
//         | "district_heating" | "buffer" | "air_conditioner" | "electric_heater" | "storage_heater",
//     name: "Boiler",                      // optional device label
//     running: bool,                       // burner lit / compressor / element on
//     flame: bool | null,                  // separate flame signal if known
//     modulation: 0..1 | null,             // modulating boilers (flame size)
//     pump: bool,                          // circulation pump -> water flows in the pipes
//     flow: °C | null, return: °C | null,  // measured pipe temperatures
//     flowTarget: °C | null,               // requested flow temperature (curve / OpenTherm)
//     buffer: bool, bufferTemp: °C | null, // buffer tank drawn in the plant room
//     mode: "heat" | "cool" | "off",
//     unitTarget: °C | null, unitTemp: °C | null,  // AC unit setpoint / own sensor
//     power: { value, unit } | null,       // electrical power of the device
//     gas: { now: m³/h | null, nowEstimated: bool, today: m³ | null, total: m³ | null } | null,
//     energy: { today: kWh | null, total: kWh | null } | null,
//     fault: bool, health: "ok" | …,
//   },
//   rooms: [{
//     key: "konyha", name: "Konyha", kind: "living"|"bed"|"kids"|"kitchen"|"dining"|"bath"|"wc"|"hall"|"office"|"storage"|"terrace"|"generic",
//     floor: level | null,                 // HA floor level; null -> automatic rows
//     temp, target,                        // room reading / room target (null = follows the house)
//     emitter: "radiator" | "floor" | "fan_coil" | "ac" | "electric" | "storage" | "none",
//     heating: bool,                       // this room's emitter receives heat now (branch animation, glow)
//     leading: bool,                       // this room drives the heat source (HC thermostat)
//     zone: bool,                          // separate zone (e.g. terrace coupled via a door)
//     trvs: [{ id, name, temp, target, state: "heating"|"idle"|"off"|"unknown", calibration }],
//     thermostat: { temp, target, hc: bool } | null,   // wall display; defaults to temp/target
//     presence: { state: "home"|"none"|"unknown", who: [] } | null,
//     window: true | false | null,          // open window
//     door: true | false | null,            // zone door
//     advice: "ok"|"up"|"down"|"learning"|null, deviation: K | null,
//     unit: { target, temp, running } | null     // AC / electric unit in this room
//   }]
// }
// ───────────────────────────────────────────────────────────────────────

const FONT = 'Roboto, "Segoe UI", "Helvetica Neue", Arial, sans-serif';

const TXT = {
  hu: {
    room: "Helyiség", flow: "előremenő", ret: "visszatérő", target: "cél", gas: "Gáz", total: "össz.", today: "ma", now: "most",
    burning: "ég", idle: "áll", running: "üzemel", off: "ki", outdoor: "Kint", avg: "24 h átl.", open: "nyitva",
    v_heating: "nyit", v_idle: "zárva", v_off: "ki", leading: "vezető", demand: "igény", home: "otthon", away: "távol",
    vacation: "szabadság", nobody: "senki", shadow: "árnyék", fault: "HIBA", zone: "zóna", buffer: "puffer", pump: "szivattyú",
    follows: "házat követi", door: "ajtó nyitva", unit: "egység", estimated: "becsült",
    kinds: { gas_boiler: "Gázkazán", modulating_boiler: "Moduláló kazán", heat_pump: "Hőszivattyú", electric_boiler: "Villanykazán",
      pellet_boiler: "Pelletkazán", district_heating: "Távhő", external_heat: "Külső hőtermelő", buffer: "Puffertartály", air_conditioner: "Klíma",
      electric_heater: "Villanyfűtő", storage_heater: "Hőtárolós kályha" },
  },
  en: {
    room: "Room", flow: "flow", ret: "return", target: "target", gas: "Gas", total: "total", today: "today", now: "now",
    burning: "burning", idle: "idle", running: "running", off: "off", outdoor: "Outdoor", avg: "24 h avg", open: "open",
    v_heating: "open", v_idle: "closed", v_off: "off", leading: "leading", demand: "demand", home: "home", away: "away",
    vacation: "vacation", nobody: "nobody", shadow: "shadow", fault: "FAULT", zone: "zone", buffer: "buffer", pump: "pump",
    follows: "follows house", door: "door open", unit: "unit", estimated: "estimated",
    kinds: { gas_boiler: "Gas boiler", modulating_boiler: "Modulating boiler", heat_pump: "Heat pump", electric_boiler: "Electric boiler",
      pellet_boiler: "Pellet boiler", district_heating: "District heating", external_heat: "External heat source", buffer: "Buffer tank", air_conditioner: "Air conditioner",
      electric_heater: "Electric heater", storage_heater: "Storage heater" },
  },
};

const ROOM_UNIT_KINDS = ["air_conditioner", "electric_heater", "storage_heater"];
const isHydronic = (vm) => !ROOM_UNIT_KINDS.includes(vm.source?.kind) || vm.rooms.some((r) => ["radiator", "floor", "fan_coil"].includes(r.emitter));

// ───────────── helpers ─────────────
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
const num = (s) => { if (isNum(s)) return s; const n = parseFloat(s); return isFinite(n) ? n : null; };
const norm = (s) => String(s || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const tokens = (s) => norm(s).split(/[^a-z0-9]+/).filter(Boolean);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const r1 = (v) => Math.round(v * 10) / 10;
const lerp = (a, b, t) => a + (b - a) * t;

function fmt(v, lang, d = 1) {
  if (!isNum(v)) return "–";
  let s = (Math.round(v * 10 ** d) / 10 ** d).toFixed(d);
  if (d > 0 && s.endsWith("0") && Math.abs(v) >= 10 && d === 1) s = s; // keep one decimal for temps
  return lang === "hu" ? s.replace(".", ",") : s;
}
const deg = (v, lang) => (isNum(v) ? `${fmt(v, lang)}°` : "–");
// trimmed number: 23.0 -> "23", 22.5 -> "22,5"
function tn(v, lang, d = 1) {
  if (!isNum(v)) return "–";
  const s = String(Math.round(v * 10 ** d) / 10 ** d);
  return lang === "hu" ? s.replace(".", ",") : s;
}

let _ctx = null;
function tw(s, size, weight = 400) {
  if (_ctx === null) { try { _ctx = document.createElement("canvas").getContext("2d"); } catch (e) { _ctx = undefined; } }
  if (_ctx) { _ctx.font = `${weight} ${size}px ${FONT}`; return _ctx.measureText(String(s)).width; }
  return String(s).length * size * 0.56;
}

// ───────────── room naming / kind guessing ─────────────
const ROOM_WORDS = [
  ["nappali", "Nappali"], ["konyha", "Konyha"], ["haloszoba", "Hálószoba"], ["halo", "Hálószoba"], ["gyerekszoba", "Gyerekszoba"],
  ["furdoszoba", "Fürdőszoba"], ["furdo", "Fürdőszoba"], ["wc", "WC"], ["eloszoba", "Előszoba"], ["folyoso", "Folyosó"],
  ["dolgozoszoba", "Dolgozószoba"], ["dolgozo", "Dolgozószoba"], ["iroda", "Iroda"], ["etkezo", "Étkező"], ["kamra", "Kamra"],
  ["terasz", "Terasz"], ["sufni", "Sufni"], ["garazs", "Garázs"], ["pince", "Pince"], ["padlas", "Padlás"], ["vendegszoba", "Vendégszoba"],
  ["living", "Living room"], ["kitchen", "Kitchen"], ["bedroom", "Bedroom"], ["bathroom", "Bathroom"], ["hallway", "Hallway"],
  ["office", "Office"], ["dining", "Dining room"], ["toilet", "Toilet"],
];
const OUTDOOR_RE = /^(udvar|kert|kint|kulso|szaletli|courtyard|garden|yard|outdoor|outside|backyard|porch)/;

function guessKind(name, icon) {
  const n = norm(name), ic = String(icon || "");
  const t = (re) => re.test(n);
  if (t(/gyerek|kid|child|nursery/)) return "kids";
  if (t(/halo|bed|vendeg|guest/) || ic.includes("bed")) return "bed";
  if (t(/nappali|living|lounge|sofa/) || ic.includes("sofa")) return "living";
  if (t(/konyha|kitchen/) || ic.includes("countertop") || ic.includes("stove")) return "kitchen";
  if (t(/etkezo|dining/) || ic.includes("table-chair")) return "dining";
  if (t(/furdo|bath|zuhany|shower/) || ic.includes("shower") || ic.includes("bath")) return "bath";
  if (t(/(^|[^a-z])wc|toilet|mosdo/) || ic.includes("paper-roll") || ic.includes("toilet")) return "wc";
  if (t(/eloszoba|folyoso|hall|entr|lepcso|stair/) || ic.includes("door")) return "hall";
  if (t(/dolgozo|iroda|office|study|work/) || ic.includes("desk")) return "office";
  if (t(/kamra|sufni|pantry|storage|tarolo|garazs|garage|pince|cellar/) || ic.includes("food")) return "storage";
  if (t(/terasz|terrace|veranda|balcony|erkely|teli ?kert|winter/) || ic.includes("roof")) return "terrace";
  return "generic";
}

// Match a free-text entity name (or entity id) against known areas; falls back to well-known room words.
function makeMatcher(areas) {
  const list = (areas || []).map((a) => ({ a, tk: tokens(a.name) })).filter((x) => x.tk.length);
  list.sort((p, q) => q.tk.join(" ").length - p.tk.join(" ").length);
  return (text) => {
    const tk = tokens(text);
    if (!tk.length) return null;
    for (const { a, tk: at } of list) {
      for (let i = 0; i + at.length <= tk.length; i++) {
        if (at.every((w, j) => (j === at.length - 1 ? tk[i + j].startsWith(w) : tk[i + j] === w))) return { name: a.name, area: a };
      }
    }
    for (const [w, label] of ROOM_WORDS) {
      if (tk.some((x) => x === w || (w.length > 3 && x.startsWith(w)))) return { name: label, area: null };
    }
    return null;
  };
}

// ───────────── adapter: info JSON -> view model ─────────────
// extras (all optional):
//   lang, areas [{area_id,name,floor_id,icon}], floors [{floor_id,name,level}], entityAreas {entity_id: area_id|area name},
//   allAreas: bool (add every indoor area as a room), excludeAreas: [area_id|name], mainRoom: name,
//   sun: "above_horizon"|"below_horizon", night: bool, gasToday: m³, energyToday: kWh, flow/return: °C, pump: bool,
//   roomPresence: { roomName: {state, who} }, rooms: [...] (override / upcoming per-room list, see fromRoomsList)
export function fromInfo(info, x = {}) {
  info = info || {};
  // 0.44.0: what the backend sends for the drawing; a caller's extras win
  const ht = info.heat_today;
  x = { ...x,
    areas: x.areas || info.areas || [], floors: x.floors || info.floors || [],
    entityAreas: { ...(info.entity_areas || {}), ...(x.entityAreas || {}) },
    sun: x.sun ?? info.sun?.state ?? null,
    gasToday: x.gasToday ?? (ht && /m³|m3/.test(ht.unit || "") ? num(ht.value) : null),
    energyToday: x.energyToday ?? (ht && /kwh/i.test(ht.unit || "") ? num(ht.value) : null),
    flow: x.flow ?? num(info.pipes?.flow) ?? null, return: x.return ?? num(info.pipes?.return) ?? null };
  const lang = x.lang || "hu";
  const ents = info.entities || {};
  const E = (k) => ents[k] || [];
  const E1 = (k) => E(k)[0] || null;
  const conf = info.conf || {};
  const dec = info.decision || {}, det = dec.details || {}, inp = info.inputs || {}, cl = info.climate?.attributes || {};
  const srcRaw = info.heat_source || "";
  const kind = srcRaw === "onoff_boiler" ? "gas_boiler" : srcRaw || "gas_boiler";
  const sys = info.system || "";
  const output = !!dec.output;
  const actual = info.actual ?? inp.actual_heating;
  const flameE = E1("flame_entity");
  const flame = flameE ? flameE.state === "on" : null;
  const relayE = E1("actuator_entity");
  const relay = relayE ? relayE.state === "on" : null;

  let running;
  if (["gas_boiler", "modulating_boiler", "pellet_boiler"].includes(kind)) running = flame ?? (actual ?? output);
  else if (kind === "air_conditioner") running = (cl.hvac_action === "heating" || cl.hvac_action === "cooling") || (output && (det.ac_mode || dec.external?.hvac) !== "off");
  else running = actual ?? relay ?? output;
  // electric devices: relay on but almost no power drawn = own thermostat idle
  const pE0 = E1("boiler_power_entity"), pw0 = pE0 ? num(pE0.state) : null;
  if (["electric_heater", "electric_boiler", "storage_heater"].includes(kind) && pw0 != null && /^w$/i.test(pE0.unit || "W") && pw0 < 30) running = false;
  running = !!running;

  // circulation: on-off boilers run the pump whenever the relay calls; modulating when CH enable + call
  const heatEnable = E1("heat_enable_entity");
  let pump = x.pump;
  if (pump == null) {
    if (ROOM_UNIT_KINDS.includes(kind)) pump = false;
    else pump = !!(running || output || relay || actual || (heatEnable && heatEnable.state === "on" && output));
  }

  const hE = E1("heat_energy_entity");
  let gas = null, energy = null;
  if (hE) {
    const v = num(hE.state);
    if (/m³|m3/.test(hE.unit || "")) gas = { total: v, today: x.gasToday ?? null, now: null, nowEstimated: false };
    else if (/kwh/i.test(hE.unit || "")) energy = { total: v, today: x.energyToday ?? null };
  }
  if (["gas_boiler", "modulating_boiler"].includes(kind)) {
    gas = gas || { total: null, today: x.gasToday ?? null, now: null, nowEstimated: false };
    const pkw = num(conf.boiler_power_kw ?? info.config?.boiler_power_kw), ef = num(conf.energy_factor);
    if (x.gasNow != null) gas.now = x.gasNow;
    else if (running && pkw && ef && kind === "gas_boiler") { gas.now = pkw / ef; gas.nowEstimated = true; }
    else if (!running) gas.now = 0;
  }
  const pE = E1("boiler_power_entity");
  const power = pE && num(pE.state) != null ? { value: num(pE.state), unit: pE.unit || "W" } : null;
  const fsE = E1("flow_setpoint_entity");

  const source = {
    kind, name: relayE?.name || null, running, flame, pump,
    modulation: kind === "modulating_boiler" && running ? clamp(num(dec.demand) ?? 0.5, 0.15, 1) : null,
    flow: x.flow ?? num(inp.flow?.value) ?? null,
    return: x.return ?? num(inp.return_temp?.value) ?? null,
    flowTarget: num(dec.flow_setpoint) ?? num(det.flow) ?? (fsE ? num(fsE.state) : null),
    buffer: info.role === "buffer" || !!x.buffer, bufferTemp: x.bufferTemp ?? null,
    mode: det.ac_mode || det.mode || (dec.external?.hvac) || "heat",
    unitTarget: num(det.setpoint) ?? num(info.state?.ac?.sent), unitTemp: num(det.unit_temp ?? inp.unit_temp),
    power, gas, energy,
    fault: !!(dec.fault || info.live?.fault), health: info.health?.state || null,
  };

  // presence (house level)
  const pres = E("presence_entities");
  let presence = null;
  if (pres.length || inp.presence) {
    const who = pres.filter((p) => p.entity_id?.startsWith("person.") && p.state === "home").map((p) => p.name);
    presence = { state: inp.presence || (who.length ? "home" : "unknown"), who };
  }

  // ---- rooms ----
  const areas = (x.areas || []).filter((a) => !(x.excludeAreas || []).includes(a.area_id) && !(x.excludeAreas || []).includes(a.name));
  const match = makeMatcher(areas);
  const areaById = Object.fromEntries((x.areas || []).map((a) => [a.area_id, a]));
  const floorLevel = Object.fromEntries((x.floors || []).map((f) => [f.floor_id, f.level ?? 0]));
  const rooms = new Map();
  const where = (eid, name) => {
    const ea = x.entityAreas?.[eid];
    if (ea) { const a = areaById[ea] || areas.find((q) => q.name === ea); return a ? { name: a.name, area: a } : { name: ea, area: null }; }
    return match(name) || match(eid);
  };
  const emitterFor = (rk) => {
    if (ROOM_UNIT_KINDS.includes(kind)) return "none";
    if (sys === "fan_coil") return "fan_coil";
    if (sys.startsWith("floor")) return "floor";
    if (sys.startsWith("mixed")) return ["bath", "hall", "kitchen", "wc"].includes(rk) ? "floor" : "radiator";
    return "radiator";
  };
  const room = (m, create = true) => {
    if (!m || (!m.key && OUTDOOR_RE.test(norm(m.name)))) return null;
    const aid = m.area?.area_id || null;
    const found = (m.key && rooms.get(m.key)) || (aid && [...rooms.values()].find((r) => r.area_id === aid))
      || [...rooms.values()].find((r) => norm(r.name) === norm(m.name));
    if (found) return found;
    const key = m.key || aid || norm(m.name).replace(/[^a-z0-9]+/g, "_");
    if (!rooms.has(key)) {
      if (!create) return null;
      const k = guessKind(m.name, m.area?.icon);
      rooms.set(key, { key, name: m.name, area_id: aid, kind: k,
        floor: m.area?.floor_id != null ? floorLevel[m.area.floor_id] ?? null : null,
        temp: null, target: null, emitter: emitterFor(k), heating: false, leading: false, zone: false, trvs: [],
        thermostat: null, presence: null, window: null, door: null, advice: null, deviation: null, unit: null, sensors: [] });
    }
    return rooms.get(key);
  };

  // 0.43.0+: the host's own rooms (in the order of its `rooms` option) come first, with their own data
  const roomList = Array.isArray(info.room_list) ? info.room_list : [];
  const heads = Object.fromEntries(E("room_trvs").map((t) => [t.entity_id, t]));
  const presMap = { present: "home", leaving: "home", absent: "none" };
  for (const it of roomList) {
    const r = room({ key: it.key, name: it.name, area: areaById[it.area] || areas.find((a) => a.name === it.name) || null });
    if (!r) continue;
    r.listed = true;
    r.temp = num(it.temperature);
    r.target = it.leading || !(it.trvs || []).length ? null : num(it.target);  // no TRV: it follows the house
    r.sensors.push(...(it.sensors || []));
    r.trvs = (it.trvs || []).map((h) => {
      const t = heads[h] || {}, v = (it.heads || {})[h] || {}, st = t.state ?? v.state;
      return { id: h, name: t.name || it.names?.[h] || h, temp: num(t.current_temperature ?? v.head_temp), target: num(t.temperature ?? v.head_target),
        state: st === "off" ? "off" : t.hvac_action === "heating" ? "heating" : t.hvac_action ? "idle" : st == null || st === "unavailable" ? "unknown" : "idle",
        calibration: num(v.calibration) };
    });
    if (r.trvs.length && (r.emitter === "none" || r.emitter === "floor")) r.emitter = "radiator";
    if (it.presence) r.presence = { state: presMap[it.presence] || "unknown", who: [] };
    if (it.advice) { r.advice = it.advice.advice ?? null; r.deviation = num(it.advice.deviation); }
    if (it.leading) r.leading = true;
  }
  const indoorE = E1("indoor_entity");
  let lead = [...rooms.values()].find((r) => r.leading) || room(indoorE ? where(indoorE.entity_id, indoorE.name) : null)
    || room(x.mainRoom ? { name: x.mainRoom, area: areas.find((a) => a.name === x.mainRoom) || null } : null);
  if (!lead) {
    const nm = indoorE?.name ? indoorE.name.replace(/\s*(hőmérséklet|temperature|temp)\s*$/i, "").trim() : TXT[lang].room;
    lead = room({ name: nm || TXT[lang].room, area: null });
  }
  lead.leading = true;
  lead.temp = num(inp.indoor?.value) ?? num(dec.indoor) ?? num(cl.current_temperature);
  lead.target = num(dec.target) ?? num(cl.temperature);
  lead.thermostat = { temp: lead.temp, target: lead.target, hc: true };
  if (ROOM_UNIT_KINDS.includes(kind)) {
    lead.emitter = kind === "air_conditioner" ? "ac" : kind === "storage_heater" ? "storage" : "electric";
    lead.unit = { target: source.unitTarget, temp: source.unitTemp, running, power };
  }

  const addTemp = (e) => {
    const r = room(where(e.entity_id, e.name)); if (!r) return;
    const v = num(e.state ?? e.value);
    r.sensors.push(e.entity_id);
    if (r.temp == null && v != null) r.temp = v;
  };
  E("room_sensors").forEach(addTemp);
  E("window_drop_entities").forEach(addTemp);

  // separate zone (e.g. terrace coupled through a door)
  const zE = E1("zone_temp_entity");
  if (zE) {
    const r = room(where(zE.entity_id, zE.name));
    if (r && !r.leading) {
      r.zone = true; r.temp = num(info.zone?.temp) ?? num(zE.state);
      const xh = E1("extra_heat_entity");
      r.emitter = xh && /kl[ií]ma|clima|\bac\b|air|split/i.test(xh.name || xh.entity_id) ? "ac" : "none";
      if (r.emitter === "ac") r.unit = { running: (num(inp.other_heat_kw) || 0) > 0, target: null, temp: null };
      r.heating = r.unit?.running || false;
    }
  }

  // TRV heads
  const trvRooms = info.rooms?.trv || {};
  const placed = new Set([...rooms.values()].flatMap((r) => r.trvs.map((t) => t.id)));
  for (const t of E("room_trvs")) {
    if (placed.has(t.entity_id)) continue;
    let rn = Object.keys(trvRooms).find((k) => trvRooms[k]?.heads && t.entity_id in trvRooms[k].heads);
    const r = rn ? room({ name: rn, area: areas.find((a) => a.name === rn) || null }) : room(where(t.entity_id, t.name));
    if (!r) continue;
    const info2 = rn ? trvRooms[rn] : null, head = info2?.heads?.[t.entity_id] || {};
    r.trvs.push({ id: t.entity_id, name: t.name, temp: num(t.current_temperature), target: num(t.temperature),
      state: t.state === "off" ? "off" : t.hvac_action === "heating" ? "heating" : t.hvac_action ? "idle" : "unknown",
      calibration: num(head.calibration) });
    if (r.emitter === "none" || r.emitter === "floor") r.emitter = "radiator";
    if (info2) { r.target = num(info2.target) ?? r.target; if (num(info2.room_temp) != null) r.temp = num(info2.room_temp); }
  }

  for (const a of info.rooms?.advice || []) {
    const r = room(where(null, a.room), false) || room({ name: a.room, area: areas.find((q) => q.name === a.room) || null });
    if (r && r.advice == null) { r.advice = a.advice; r.deviation = num(a.deviation); }
  }

  const doors = [];
  for (const w of E("window_entities")) {
    const r = room(where(w.entity_id, w.name), false);
    if (r) r.window = (r.window || false) || w.state === "on";
    else doors.push({ name: String(w.name || w.entity_id).replace(/\s+/g, " ").trim(), open: w.state === "on" });
  }
  for (const w of E("zone_door_entities")) {
    const r = room(where(w.entity_id, w.name), false);
    if (r) r.door = w.state === "on";
  }

  if (x.allAreas) for (const a of areas) room({ name: a.name, area: a });

  // upcoming per-room structure (0.43+) or caller-supplied list overrides/extends
  const list = x.rooms || info.rooms?.list || null;
  if (Array.isArray(list)) for (const it of list) mergeRoom(room({ name: it.name, area: areas.find((a) => a.name === it.name || a.area_id === it.area_id) || null }), it);

  for (const [n, p] of Object.entries(x.roomPresence || {})) { const r = room(where(null, n), false); if (r) r.presence = p; }

  // derive per-room heating
  const flowing = pump && !ROOM_UNIT_KINDS.includes(kind);
  for (const r of rooms.values()) {
    if (["radiator", "floor", "fan_coil"].includes(r.emitter)) {
      if (r._heatingSet) continue;
      r.heating = flowing && (r.trvs.length ? r.trvs.some((t) => t.state === "heating" || t.state === "unknown") : true);
    } else if (r.leading && ROOM_UNIT_KINDS.includes(kind)) r.heating = running;
    if (!r.thermostat && r.temp != null) r.thermostat = { temp: r.temp, target: r.target, hc: false };
  }

  const ordered = [...rooms.values()];
  const aidx = (r) => { const i = areas.findIndex((a) => a.name === r.name); return i < 0 ? 999 : i; };
  // extras.order: room names / area ids in the wanted order (bottom row first, left to right after the plant room);
  // unlisted rooms follow. Otherwise: leading room first, then HA area order.
  const ord = Array.isArray(x.order) ? x.order.map((n) => String(n).toLowerCase()) : null;
  const oidx = (r) => { if (!ord) return 0; const i = ord.findIndex((n) => n === String(r.name).toLowerCase() || n === String(r.key).toLowerCase() || n === String(r.area_id || "").toLowerCase()); return i < 0 ? 999 : i; };
  // 0.44.0: the host's room list gives the order (its rooms first, as listed); then the others: zone last, area order
  const lkeys = roomList.map((it) => it.key);
  const lidx = (r) => { const i = lkeys.indexOf(r.key); return i < 0 ? 999 : i; };
  if (lkeys.length) ordered.sort((p, q) => (oidx(p) - oidx(q)) || (lidx(p) - lidx(q)) || (p.zone - q.zone) || (aidx(p) - aidx(q)));
  else ordered.sort((p, q) => (oidx(p) - oidx(q)) || (q.leading - p.leading) || (p.zone - q.zone) || (aidx(p) - aidx(q)));

  let night = x.night;
  if (night == null && x.sun) night = x.sun === "below_horizon";
  if (night == null) { const h = new Date(dec.now || inp.now || Date.now()).getHours(); night = h < 7 || h >= 17; }

  const demand = num(dec.demand) ?? (num(cl.demand) != null ? num(cl.demand) / 100 : null);
  return {
    lang, title: conf.home_name || info.title || conf.name || "HC", subtitle: lang === "hu" ? info.text_hu : info.text_en,
    mode: info.mode || "active", target: num(dec.target), indoor: num(dec.indoor), demand,
    night: !!night, outdoor: (num(inp.outdoor?.value) ?? num(dec.outdoor)) != null ? { temp: num(inp.outdoor?.value) ?? num(dec.outdoor), avg: num(inp.outdoor_avg) } : null,
    presence, doors, source, rooms: ordered,
  };
}

// Generic per-room record (upcoming 0.43 "room thermostats"): tolerant of several spellings.
//   { name, area_id, temp|current|current_temperature, target|temperature, leading|is_leading,
//     trvs|heads: [{entity_id|id, name, current_temperature|temp, temperature|target, hvac_action|state, calibration}],
//     presence: {state, who} | "home"/"away", window_open|window, heating|demand>0, emitter, advice, deviation }
function mergeRoom(r, it) {
  if (!r || !it) return;
  const v = (...k) => { for (const q of k) if (it[q] != null) return it[q]; return undefined; };
  const t = num(v("temp", "current", "current_temperature", "indoor")); if (t != null) r.temp = t;
  const g = num(v("target", "temperature", "target_temp")); if (g != null) r.target = g;
  if (v("leading", "is_leading") != null) r.leading = !!v("leading", "is_leading");
  if (v("emitter") != null) r.emitter = v("emitter");
  if (v("kind") != null) r.kind = v("kind");
  if (v("floor") != null) r.floor = v("floor");
  const heads = v("trvs", "heads");
  if (Array.isArray(heads)) r.trvs = heads.map((h) => ({ id: h.entity_id || h.id, name: h.name || h.entity_id,
    temp: num(h.current_temperature ?? h.temp), target: num(h.temperature ?? h.target),
    state: h.state === "off" ? "off" : (h.hvac_action || h.state) === "heating" ? "heating" : (h.hvac_action || h.state) ? "idle" : "unknown",
    calibration: num(h.calibration) }));
  const p = v("presence");
  if (p != null) r.presence = typeof p === "string" ? { state: p === "on" || p === "home" ? "home" : p === "off" ? "none" : p, who: [] } : p;
  const w = v("window_open", "window"); if (w != null) r.window = !!w;
  const h = v("heating"); if (h != null) { r.heating = !!h; r._heatingSet = true; }
  else if (num(v("demand")) != null) { r.heating = num(v("demand")) > 0; r._heatingSet = true; }
  if (v("advice") != null) r.advice = v("advice");
  if (v("deviation") != null) r.deviation = num(v("deviation"));
  if (v("thermostat") != null) r.thermostat = v("thermostat");
  if (v("zone") != null) r.zone = !!v("zone");
}

// ───────────── renderer ─────────────
// opts: { width (px, host width), narrow?: bool, idPrefix }
export function renderHouse(vm, opts = {}) {
  const L = TXT[vm.lang] || TXT.hu, lang = vm.lang || "hu";
  const width = opts.width || 900;
  const narrow = opts.narrow ?? width < 560;
  const P = opts.idPrefix || "hv";
  const FS = narrow ? 1.22 : 1; // label scale on phones
  const src = vm.source || { kind: "gas_boiler" };
  const hyd = isHydronic(vm);
  const out = [], defs = [], over = []; // over = labels drawn on top of everything
  const pipesBase = [], pipesAnim = [];
  roomOverlays.length = 0;
  const rooms = vm.rooms || [];
  const flowing = hyd && !!src.pump;
  const spd = clamp(2.4 - 1.6 * (vm.demand ?? 0.5), 0.7, 2.4).toFixed(2);

  // ---- grid ----
  const Cmax = clamp(Math.floor(width / 185), 2, 5);
  const cells = rooms.map((r) => ({ room: r }));
  const util = hyd ? { util: true } : null;
  let rowsBU = []; // bottom-up
  if (rooms.some((r) => r.floor != null)) {
    const lv = [...new Set(rooms.map((r) => r.floor ?? 0))].sort((a, b) => a - b);
    lv.forEach((l, i) => {
      const list = cells.filter((c) => (c.room.floor ?? 0) === l);
      if (i === 0 && util) list.unshift(util);
      const nr = Math.ceil(list.length / Cmax), c = Math.ceil(list.length / nr);
      for (let k = 0; k < list.length; k += c) rowsBU.push(list.slice(k, k + c));
    });
  } else {
    const all = util ? [util, ...cells] : cells;
    const nr = Math.max(1, Math.ceil(all.length / Cmax)), c = Math.ceil(all.length / nr);
    for (let k = 0; k < all.length; k += c) rowsBU.push(all.slice(k, k + c));
  }
  if (!rowsBU.length) rowsBU = [[util || { room: { key: "x", name: L.room, kind: "generic", emitter: "none", trvs: [] } }]];
  const rows = rowsBU.slice().reverse();
  const C = Math.max(...rows.map((r) => r.length));
  // multi-storey: pad short rows with a staircase so every column keeps its width (risers stay in the walls)
  if (rows.length > 1) for (const row of rows) while (row.length < C) row.push({ filler: true });

  let R = narrow ? 176 : 222;
  if (C === 1) R = narrow ? 300 : 340;
  const H = narrow ? 184 : 190, T = 10, EW = 14, S = 16, SF = 24, CD = 10, FD = 20, I = 12;
  // which side gets the AC outdoor unit: the side nearest the (first) AC room
  let acSide = null;
  rows.forEach((row) => row.forEach((c, j) => { if (!acSide && c.room?.emitter === "ac") acSide = (row.length === 1 || j < row.length / 2) ? "L" : "R"; }));
  const hasHP = src.kind === "heat_pump";
  const hasGas = ["gas_boiler", "modulating_boiler"].includes(src.kind);
  if ((hasHP || (hasGas && hyd)) && acSide === "L") acSide = "R"; // left side is taken by the HP unit / gas meter
  const wideM = narrow ? 92 : 108;
  const OL = hasHP || acSide === "L" ? wideM : hasGas ? 40 : 22;
  const OR = acSide === "R" ? wideM : 22;
  const innerW = C * R + (C - 1) * T;
  const X0 = OL, X1 = X0 + EW + innerW + EW, houseW = X1 - X0;
  const RH = clamp(houseW * 0.2, 96, 128);
  const W = X1 + OR;
  const Xc = (X0 + X1) / 2;
  // top-right status stack: outdoor temperature, 24 h average, presence, open doors
  const stack = [];
  if (vm.outdoor && isNum(vm.outdoor.temp)) {
    stack.push({ t: `${L.outdoor} ${deg(vm.outdoor.temp, lang)}C`, cls: "po", size: 13, weight: 700, icon: "therm", key: "outdoor" });
    if (isNum(vm.outdoor.avg)) stack.push({ t: `${L.avg} ${deg(vm.outdoor.avg, lang)}`, cls: "po2", size: 11, key: "outdoor" });
  }
  if (vm.presence) {
    const st = vm.presence.state, who = (vm.presence.who || []).join(", ");
    const t = st === "home" ? (who || L.home) : st === "away" ? L.away : st === "vacation" ? L.vacation : (who || st);
    stack.push({ t, cls: st === "home" ? "pp1" : "pp0", size: 11, icon: "person", key: "hc" });
  }
  for (const d of vm.doors || []) if (d.open) stack.push({ t: `${d.name}: ${L.open}`, cls: "pwarn", size: 11, icon: "door", key: "hc" });
  const stackW = Math.max(0, ...stack.map((c) => tw(c.t, c.size * FS, c.weight || 600) + 12 + (c.icon ? 15 : 0)));
  const stackH = stack.reduce((a, c) => a + c.size * FS + 7 + 5, 0);
  const ov = 22;
  let apexY = 14;
  {
    const fr = Math.max(0, (W - 10 - stackW - Xc) / (X1 + ov - Xc));
    const need = 10 + stackH + 8;
    apexY = Math.max(apexY, need - fr * (RH + 12) + 4);
    const frl = Math.max(0, (Xc - 52) / (Xc - X0 + ov));
    apexY = Math.max(apexY, 56 - frl * (RH + 12) + 4);
  }
  const eaveY = apexY + RH;
  const rowY = (i) => eaveY + S + i * (H + S);
  const nR = rows.length;
  const yG = rowY(nR - 1) + H; // ground floor level (bottom row floor)
  const gs = src.gas || {};
  const parts = [];
  if (src.running && isNum(gs.now) && gs.now > 0) parts.push(`${L.now} ${gs.nowEstimated ? "≈" : ""}${fmt(gs.now, lang, 2)} m³/h`);
  else parts.push(src.running ? L.burning : L.idle);
  if (isNum(gs.today)) parts.push(`${L.today} ${fmt(gs.today, lang, 2)} m³`);
  if (isNum(gs.total)) parts.push(`${L.total} ${fmt(gs.total, lang, gs.total >= 100 ? 0 : 1)} m³`);
  const gasLine = `${L.gas}: ${parts.join(" · ")}`;
  const gas2 = hasGas && tw(gasLine, 12 * FS, 600) + 30 >= W - (X0 - 8) - 10;
  const Ht = yG + SF + (hasGas ? (gas2 ? 76 : 48) : 34);
  const night = !!vm.night;

  // per-row cell geometry
  const geo = [];
  rows.forEach((row, i) => {
    const k = row.length, cw = (innerW - (k - 1) * T) / k;
    row.forEach((cell, j) => geo.push({ cell, row: i, col: j, x0: X0 + EW + j * (cw + T), w: cw, y0: rowY(i), h: H }));
  });
  const ug = geo.find((g) => g.cell.util);
  const slabY = (i) => rowY(i) + H; // top of the slab under row i
  const yFl = (i) => slabY(i) + 5, yRt = (i) => slabY(i) + 11;

  // ---- defs ----
  defs.push(`
  <linearGradient id="${P}sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="sk1"/><stop offset="1" class="sk2"/></linearGradient>
  <linearGradient id="${P}roof" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="rf1"/><stop offset="1" class="rf2"/></linearGradient>
  <pattern id="${P}tiles" width="22" height="12" patternUnits="userSpaceOnUse"><path d="M0,12 Q5.5,4 11,12 Q16.5,4 22,12" class="tile"/></pattern>
  <linearGradient id="${P}boiler" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#ffffff"/><stop offset=".7" stop-color="#eef1f4"/><stop offset="1" stop-color="#cfd5db"/></linearGradient>
  <linearGradient id="${P}radc" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#d6dbe0"/></linearGradient>
  <linearGradient id="${P}radh" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff4ee"/><stop offset=".55" stop-color="#ffc2a6"/><stop offset="1" stop-color="#ff8a65"/></linearGradient>
  <linearGradient id="${P}oil" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffcc80"/><stop offset="1" stop-color="#ef6c00"/></linearGradient>
  <linearGradient id="${P}tank" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#b71c1c"/><stop offset=".35" stop-color="#ef5350"/><stop offset="1" stop-color="#8e1414"/></linearGradient>
  <linearGradient id="${P}steel" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#9aa3ab"/><stop offset=".35" stop-color="#e7ebee"/><stop offset="1" stop-color="#8a939b"/></linearGradient>
  <linearGradient id="${P}gl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" class="gl1"/><stop offset="1" class="gl2"/></linearGradient>
  <radialGradient id="${P}glow"><stop offset="0" stop-color="#ff9800" stop-opacity=".55"/><stop offset="1" stop-color="#ff9800" stop-opacity="0"/></radialGradient>
  <radialGradient id="${P}lamp" cx=".5" cy="0" r="1"><stop offset="0" stop-color="#ffd27a" stop-opacity=".5"/><stop offset=".6" stop-color="#ffd27a" stop-opacity=".08"/><stop offset="1" stop-color="#ffd27a" stop-opacity="0"/></radialGradient>
  <radialGradient id="${P}sun"><stop offset="0" stop-color="#fff6c4"/><stop offset=".5" stop-color="#ffd54f"/><stop offset="1" stop-color="#ffd54f" stop-opacity="0"/></radialGradient>
  <filter id="${P}sh" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="1.2" stdDeviation="1.2" flood-opacity=".28"/></filter>
  <filter id="${P}blur"><feGaussianBlur stdDeviation="3"/></filter>`);

  // ---- sky, sun/moon, ground ----
  out.push(`<rect x="0" y="0" width="${W}" height="${Ht}" fill="url(#${P}sky)"/>`);
  if (night) {
    let s = 7;
    const rnd = () => ((s = (s * 9301 + 49297) % 233280) / 233280);
    for (let i = 0; i < 26; i++) {
      const x = rnd() * W, y = rnd() * (eaveY + 10), r = 0.5 + rnd() * 1.1;
      out.push(`<circle class="star a-tw" style="animation-delay:${(-rnd() * 4).toFixed(2)}s" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r.toFixed(2)}"/>`);
    }
    out.push(`<g transform="translate(${34},${34})"><circle r="15" fill="#f4f1de"/><circle cx="7" cy="-5" r="13" class="moonbite"/></g>`);
  } else {
    out.push(`<circle cx="36" cy="36" r="34" fill="url(#${P}sun)"/><circle cx="36" cy="36" r="12" fill="#ffd54f"/>`);
  }
  // ground
  out.push(`<rect x="0" y="${yG - 2}" width="${W}" height="${Ht - yG + 2}" class="soil"/>
    <path d="M0,${yG - 4} Q${W * 0.25},${yG - 9} ${W * 0.5},${yG - 4} T${W},${yG - 4} V${yG + 8} H0Z" class="grass"/>`);
  // bushes
  const bush = (x, y, s) => `<g transform="translate(${x},${y}) scale(${s})"><ellipse cx="0" cy="-8" rx="16" ry="11" class="bush2"/><ellipse cx="-9" cy="-5" rx="10" ry="8" class="bush"/><ellipse cx="9" cy="-6" rx="11" ry="9" class="bush"/></g>`;
  if (OR < 60) out.push(bush(X1 + 6, yG + 1, 0.9));
  if (OL < 60) out.push(bush(X0 - 4, yG + 1, 0.8));

  // ---- house body ----
  out.push(`<rect x="${X0}" y="${eaveY}" width="${houseW}" height="${yG + SF - eaveY}" class="wallx" filter="url(#${P}sh)"/>`);
  // attic / gable
  const gI = 16;
  out.push(`<path d="M${X0 + gI},${eaveY} L${Xc},${apexY + 16} L${X1 - gI},${eaveY} Z" class="attic"/>`);
  // slabs
  for (let i = -1; i < nR; i++) {
    const y = i < 0 ? eaveY : slabY(i);
    const h = i === nR - 1 ? SF : S;
    out.push(`<rect x="${X0}" y="${y}" width="${houseW}" height="${h}" class="slab"/><line x1="${X0}" y1="${y + 0.5}" x2="${X1}" y2="${y + 0.5}" class="slabEdge"/>`);
  }
  // roof
  const th = 13;
  out.push(`<path d="M${X0 - ov},${eaveY + 8} L${Xc},${apexY - 4} L${X1 + ov},${eaveY + 8} L${X1 + ov - 6},${eaveY + 8 + th} L${Xc},${apexY - 4 + th + 3} L${X0 - ov + 6},${eaveY + 8 + th} Z" fill="url(#${P}roof)"/>`);
  out.push(`<path d="M${X0 - ov},${eaveY + 8} L${Xc},${apexY - 4} L${X1 + ov},${eaveY + 8} L${X1 + ov - 6},${eaveY + 8 + th} L${Xc},${apexY - 4 + th + 3} L${X0 - ov + 6},${eaveY + 8 + th} Z" fill="url(#${P}tiles)" opacity=".5"/>`);
  out.push(`<path d="M${X0 - ov + 6},${eaveY + 8 + th} L${Xc},${apexY - 4 + th + 3} L${X1 + ov - 6},${eaveY + 8 + th}" class="fascia"/>`);

  // ---- rooms & plant room ----
  for (const g of geo) {
    if (g.cell.util) drawUtility(g);
    else if (g.cell.filler) drawStairs(g);
    else drawRoom(g);
  }

  // ---- hydronic distribution ----
  if (hyd && ug) {
    const rfx = ug.x0 + ug.w - 26, rrx = ug.x0 + ug.w - 14;
    // branches: collect per row
    const byRow = new Map();
    for (const g of geo) {
      if (!g.branch) continue;
      if (!byRow.has(g.row)) byRow.set(g.row, []);
      byRow.get(g.row).push(g);
    }
    const topRow = Math.min(...byRow.keys(), ug.row), botRow = Math.max(...byRow.keys(), ug.row);
    // risers
    const uR = ug.row;
    pipe(`M${rfx},${ug.yFH} V${yFl(botRow)}`, "f", flowing);
    if (topRow < uR) pipe(`M${rfx},${ug.yFH} V${yFl(topRow)}`, "f", flowing);
    pipe(`M${rrx},${yRt(botRow)} V${ug.yRH}`, "r", flowing);
    if (topRow < uR) pipe(`M${rrx},${yRt(topRow)} V${ug.yRH}`, "r", flowing);
    for (const [ri, list] of byRow) {
      const fx = list.flatMap((g) => g.branch.map((b) => b.fx)), rx = list.flatMap((g) => g.branch.map((b) => b.rx));
      const minF = Math.min(...fx), maxF = Math.max(...fx), minR = Math.min(...rx), maxR = Math.max(...rx);
      if (maxF > rfx) pipe(`M${rfx},${yFl(ri)} H${maxF}`, "f", flowing);
      if (minF < rfx) pipe(`M${rfx},${yFl(ri)} H${minF}`, "f", flowing);
      if (maxR > rrx) pipe(`M${maxR},${yRt(ri)} H${rrx}`, "r", flowing);
      if (minR < rrx) pipe(`M${minR},${yRt(ri)} H${rrx}`, "r", flowing);
      for (const g of list) for (const b of g.branch) {
        pipe(b.fpath, "f", flowing && g.cell.room.heating);
        pipe(b.rpath, "r", flowing && g.cell.room.heating);
      }
    }
    // pipe temperature pills on the risers / mains
    const fy = ug.yFH, ry = ug.yRH;
    const fl = src.flow, rt = src.return, ft = src.flowTarget;
    const plx = ug.x0 + ug.w / 2 + 6;
    if (fl != null || ft != null) {
      const t = fl != null ? `▲ ${deg(fl, lang)}` + (ft != null && !narrow ? `  (${L.target} ${deg(ft, lang)})` : "") : `▲ ${L.target} ${deg(ft, lang)}`;
      over.push(pill(plx, fy - 13, t, { cls: "pf", anchor: "middle", key: "source", size: narrow ? 11 : 11.5, dashed: fl == null }));
    }
    if (rt != null) over.push(pill(plx, ry + 14, `▼ ${deg(rt, lang)}`, { cls: "pr", anchor: "middle", key: "source", size: narrow ? 11 : 11.5 }));
  }
  function pipe(d, kind, anim) {
    pipesBase.push(`<path d="${d}" class="pp pp-${kind}"/>`);
    pipesBase.push(`<path d="${d}" class="ph"/>`);
    if (anim) pipesAnim.push(`<path d="${d}" class="fl fl-${kind} a-fl"/>`);
  }

  // ---- outdoor units (heat pump / AC) ----
  const outUnits = [];
  if (src.kind === "heat_pump" && ug) {
    const ux = 10, uw = OL - 22, uh = 66, uy = yG - uh + 2;
    outUnits.push(outdoorUnit(ux, uy, uw, uh, src.running, "source"));
    const by = ug.box.y, bx = ug.box.x;
    const hp1 = `M${ux + uw * 0.35},${uy} V${by + 22} H${bx}`, hp2 = `M${bx},${by + 40} H${ux + uw * 0.65} V${uy}`;
    pipe(hp1, "f", src.running || flowing); pipe(hp2, "r", src.running || flowing);
  }
  const acRooms = geo.filter((g) => g.ac);
  if (acRooms.length) {
    const uw = wideM - 20, uh = 56, uy = yG - uh + 2, ux = acSide === "R" ? W - 8 - uw : 8;
    const anyOn = acRooms.some((g) => g.cell.room.unit?.running ?? g.cell.room.heating);
    outUnits.push(outdoorUnit(ux, uy, uw, uh, anyOn, acRooms[0].cell.room.leading ? "source" : `room:${acRooms[0].cell.room.key}`, acSide === "R"));
    acRooms.forEach((g, i) => {
      const cy = g.y0 + CD + 4 + i * 3;
      const sx = acSide === "R" ? ux + uw * 0.25 - i * 4 : ux + uw * 0.75 + i * 4;
      const ex = acSide === "R" ? g.ac.x + g.ac.w - 8 : g.ac.x + 8;
      const d = `M${sx},${uy} V${cy} H${ex} V${g.ac.y}`;
      pipesBase.push(`<path d="${d}" class="ref2"/><path d="${d}" class="ref"/>`);
    });
  }

  // ---- gas line & meter ----
  if (hasGas && ug) {
    const yGas = ug.yGas, mx = X0 - 30, gx = ug.box.x + ug.box.w / 2;
    const gp = `M${mx + 11},${yG + SF + 14} V${yGas + 14} M${mx + 22},${yGas} H${gx} V${ug.box.y + ug.box.h}`;
    pipesBase.push(`<path d="${gp}" class="gas"/>`);
    if (src.running) pipesAnim.push(`<path d="M${mx + 11},${yG + SF + 14} V${yGas + 14} M${mx + 22},${yGas} H${gx} V${ug.box.y + ug.box.h}" class="fl fl-g a-fl"/>`);
    pipesBase.push(`<path d="M${mx + 11},${yG + SF + 14} H0" class="gas"/>`);
    pipesBase.push(`<g class="hs" data-key="gas"><rect x="${mx}" y="${yGas - 13}" width="22" height="27" rx="3" class="meter"/><rect x="${mx + 4}" y="${yGas - 8}" width="14" height="7" rx="1" class="lcd"/><circle cx="${gx - 16}" cy="${yGas}" r="3.2" class="gasv"/></g>`);
    const line1 = gasLine;
    const lx = mx + 22, ly = yG + SF + 14;
    if (!gas2) over.push(pill(lx, ly, line1, { cls: "pg", key: "gas", size: 12, icon: "flame" }));
    else {
      over.push(pill(lx, ly, `${L.gas}: ${parts[0]}`, { cls: "pg", key: "gas", size: 12, icon: "flame" }));
      if (parts.length > 1) over.push(pill(lx, ly + 24, parts.slice(1).join(" · "), { cls: "pg", key: "gas", size: 11.5 }));
    }
  }

  // ---- gable: title, status, presence ----
  {
    const g = [];
    const atticW = (y) => (y - (apexY + 16)) / (eaveY - apexY - 16) * (houseW - 2 * gI);
    const ty = apexY + RH * 0.6, maxW = atticW(ty - 8 * FS) - 4;
    g.push(`<text x="${Xc}" y="${ty}" class="ttl" text-anchor="middle">${esc(fit(vm.title, 15 * FS, maxW, 700))}</text>`);
    const bits = [];
    if (isNum(vm.target)) bits.push(`${L.target} ${tn(vm.target, lang)} °C`);
    if (isNum(vm.demand) && hyd) bits.push(`${L.demand} ${Math.round(vm.demand * 100)} %`);
    if (vm.mode === "shadow") bits.unshift(L.shadow);
    if (src.fault) bits.unshift(L.fault);
    const sub = bits.join(" · ");
    const y2 = apexY + RH * 0.6 + 18 * FS;
    if (sub) g.push(`<text x="${Xc}" y="${y2}" class="sub" text-anchor="middle">${esc(fit(sub, 12 * FS, atticW(y2 - 6 * FS) - 4))}</text>`);
    if (isNum(vm.demand) && hyd) {
      const bw = Math.min(110, houseW * 0.3), bx = Xc - bw / 2, by = y2 + 6;
      g.push(`<rect x="${bx}" y="${by}" width="${bw}" height="5" rx="2.5" class="bar0"/><rect x="${bx}" y="${by}" width="${(bw * clamp(vm.demand, 0, 1)).toFixed(1)}" height="5" rx="2.5" class="bar1"/>`);
    }
    const hw = Math.min((houseW - 2 * gI) * 0.6, 260);
    over.push(`<g class="hs" data-key="hc" role="button" tabindex="0" aria-label="${esc(vm.title)}"><title>${esc(vm.subtitle || vm.title)}</title><rect x="${Xc - hw / 2}" y="${ty - 18 * FS}" width="${hw}" height="${y2 + 14 - ty + 18 * FS}" rx="8" class="hit"/>${g.join("")}</g>`);
  }
  {
    let y = 10;
    const items = stack.map((c) => { const h = c.size * FS + 7; const cy = y + h / 2; y += h + 5;
      return pill(W - 10, cy, c.t, { cls: c.cls, anchor: "end", size: c.size, weight: c.weight, icon: c.icon, key: c.key }); });
    over.push(`<g class="stack">${items.join("")}</g>`);
  }

  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W.toFixed(0)} ${Ht.toFixed(0)}" class="hv ${night ? "night" : "day"} ${narrow ? "narrow" : ""}" style="--spd:${spd}s" role="img" aria-label="${esc(vm.title)}">
<defs>${defs.join("")}</defs>${out.join("")}<g>${pipesBase.join("")}</g><g>${pipesAnim.join("")}</g>${outUnits.join("")}${roomOverlays.join("")}${over.join("")}</svg>`;
  return { svg, width: W, height: Ht };

  // ═════════════ inner drawing functions ═════════════
  function fit(s, size, maxW, weight = 400) {
    s = String(s ?? "");
    if (tw(s, size, weight) <= maxW) return s;
    while (s.length > 1 && tw(s + "…", size, weight) > maxW) s = s.slice(0, -1);
    return s + "…";
  }

  // pill label; anchor: start|middle|end; y = vertical center
  function pill(x, y, text, o = {}) {
    const size = (o.size || 11.5) * FS, weight = o.weight || 600;
    const icon = o.icon ? 13 : 0;
    const w = tw(text, size, weight) + 12 + (icon ? icon + 2 : 0), h = size + 7;
    const x0 = o.anchor === "middle" ? x - w / 2 : o.anchor === "end" ? x - w : x;
    const ic = o.icon ? iconSvg(o.icon, x0 + 6 + 6, y) : "";
    const body = `<rect x="${x0.toFixed(1)}" y="${(y - h / 2).toFixed(1)}" width="${w.toFixed(1)}" height="${h}" rx="${h / 2}" class="pill ${o.cls || ""}${o.dashed ? " dash" : ""}"/>${ic}<text x="${(x0 + 6 + (icon ? icon + 2 : 0)).toFixed(1)}" y="${(y + size * 0.36).toFixed(1)}" class="pt ${o.cls || ""}" style="font-size:${size}px;font-weight:${weight}">${esc(text)}</text>`;
    return o.key && !o.nokey ? `<g class="hs" data-key="${esc(o.key)}">${body}</g>` : body;
  }

  function iconSvg(kind, cx, cy) {
    if (kind === "flame") return `<path transform="translate(${cx},${cy})" d="M0,-6 C3,-2 5,0 4,3 C3,6 -3,6 -4,3 C-5,0 -2,-1 -1,-4 C0,-2 1,-1 0,-6Z" fill="#ff6d00"/>`;
    if (kind === "therm") return `<g transform="translate(${cx},${cy})"><rect x="-1.8" y="-6.5" width="3.6" height="9" rx="1.8" class="ico-l"/><circle cx="0" cy="3.5" r="3.2" fill="#e53935"/><rect x="-0.8" y="-3" width="1.6" height="6" fill="#e53935"/></g>`;
    if (kind === "person") return `<g transform="translate(${cx},${cy})" class="ico"><circle cx="0" cy="-3" r="2.6"/><path d="M-4.5,5.5 C-4.5,0.5 4.5,0.5 4.5,5.5Z"/></g>`;
    if (kind === "door") return `<g transform="translate(${cx},${cy})" class="ico"><rect x="-3.5" y="-6" width="7" height="12" rx="1"/></g>`;
    if (kind === "drop") return `<path transform="translate(${cx},${cy})" d="M0,-6 C3,-1 4,1 4,2.5 A4,4 0 0 1 -4,2.5 C-4,1 -3,-1 0,-6Z" fill="#42a5f5"/>`;
    return "";
  }

  function roomBox(g, cls) {
    const { x0, y0, w, h } = g, x1 = x0 + w, y1 = y0 + h, yB = y1 - FD;
    out.push(`<g class="${cls}">
      <rect x="${x0}" y="${y0}" width="${w}" height="${h}" class="side"/>
      <path d="M${x0},${y0} H${x1} L${x1 - I},${y0 + CD} H${x0 + I} Z" class="ceil"/>
      <rect x="${x0 + I}" y="${y0 + CD}" width="${w - 2 * I}" height="${yB - y0 - CD}" class="back"/>
      <path d="M${x0 + I},${yB} H${x1 - I} L${x1},${y1} H${x0} Z" class="floor"/>
      <path d="M${x0 + I},${yB} H${x1 - I}" class="skirt"/>
      ${night ? `<rect x="${x0 + I}" y="${y0 + CD}" width="${w - 2 * I}" height="${yB - y0 - CD}" fill="url(#${P}lamp)"/><path d="M${x0 + w / 2 - 9},${y0 + CD} h18 l-3,4 h-12z" class="lampc"/>` : `<path d="M${x0 + w / 2 - 7},${y0 + CD} h14 l-2,3 h-10z" class="lampc off"/>`}
    </g>`);
    return { x0, y0, w, h, x1, y1, yB };
  }

  function drawStairs(g) {
    const b = roomBox(g, "stairs");
    const n = 7, sw = (b.w - 2 * I - 20) / n, sh = (b.yB - b.y0 - CD - 40) / n;
    let d = `M${b.x0 + I + 4},${b.yB}`;
    for (let i = 0; i < n; i++) d += ` V${b.yB - (i + 1) * sh} H${b.x0 + I + 4 + (i + 1) * sw}`;
    d += ` V${b.yB} Z`;
    out.push(`<path d="${d}" class="stair"/><path d="M${b.x0 + I + 4},${b.yB - sh - 26} L${b.x0 + I + 4 + n * sw},${b.yB - n * sh - 26}" class="rail"/>`);
    for (let i = 0; i <= n; i += 2) out.push(`<line x1="${b.x0 + I + 4 + i * sw}" y1="${b.yB - i * sh - 26}" x2="${b.x0 + I + 4 + i * sw}" y2="${b.yB - Math.max(i, 1) * sh}" class="rail2"/>`);
  }

  function drawUtility(g) {
    const b = roomBox(g, "util");
    const bw = narrow ? 50 : 56, bh = 74, bx = b.x0 + I + 8, by = b.y0 + CD + 16;
    g.box = { x: bx, y: by, w: bw, h: bh };
    g.yFH = by + bh + 16; g.yRH = by + bh + 30; g.yGas = b.yB - 14;
    const k = src.kind, on = !!src.running;
    const parts = [];
    const rx1 = bx + 10, gx = bx + bw / 2, fx1 = bx + bw - 10;
    const rfx = b.x0 + b.w - 26, rrx = b.x0 + b.w - 14;
    // boiler <-> riser connections (drawn as pipes so they animate)
    pipe(`M${fx1},${by + bh} V${g.yFH} H${rfx}`, "f", flowing);
    pipe(`M${rrx},${g.yRH} H${rx1} V${by + bh}`, "r", flowing);
    if (on) parts.push(`<ellipse cx="${bx + bw / 2}" cy="${by + bh * 0.6}" rx="${bw}" ry="${bh * 0.7}" fill="url(#${P}glow)" class="a-pulse"/>`);
    if (k === "heat_pump" || k === "electric_boiler" || k === "buffer" || k === "district_heating" || ["gas_boiler", "modulating_boiler", "pellet_boiler"].includes(k)) {
      // wall unit body
      const big = k === "pellet_boiler";
      parts.push(`<rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="6" fill="url(#${P}boiler)" class="unit" filter="url(#${P}sh)"/>
        <rect x="${bx + 8}" y="${by + 12}" width="${bw - 16}" height="15" rx="2.5" class="lcd"/>`);
      const disp = isNum(src.flow) ? deg(src.flow, lang) : isNum(src.flowTarget) && on ? deg(src.flowTarget, lang) : on ? "ON" : "– –";
      parts.push(`<text x="${bx + bw / 2}" y="${by + 23.5}" class="lcdt" text-anchor="middle">${esc(disp)}</text>`);
      if (["gas_boiler", "modulating_boiler", "pellet_boiler"].includes(k)) {
        const s = on ? 0.8 + 0.6 * (src.modulation ?? 1) : 0.9;
        parts.push(`<g transform="translate(${bx + bw / 2},${by + 50}) scale(${s.toFixed(2)})"><path d="M0,-12 C6,-5 10,-1 8,5 C6,11 -6,11 -8,5 C-10,-1 -4,-2 -2,-8 C0,-4 2,-3 0,-12Z" class="${on ? "flame a-flk" : "flame0"}"/>${on ? `<path d="M0,-3 C3,0 4,2 3,5 C2,7 -2,7 -3,5 C-4,2 -1,1 0,-3Z" fill="#fff59d" class="a-flk"/>` : ""}</g>`);
      } else if (k === "electric_boiler") {
        parts.push(`<path transform="translate(${bx + bw / 2},${by + 50})" d="M2,-11 L-6,2 H0 L-2,11 L6,-2 H0Z" class="${on ? "bolt on" : "bolt"}"/>`);
      } else if (k === "heat_pump") {
        parts.push(`<g transform="translate(${bx + bw / 2},${by + 50})"><circle r="9" class="hpico ${on ? "on" : ""}"/><path d="M-4,2 L0,-4 L4,2" class="hparr"/></g>`);
      } else if (k === "district_heating") {
        for (let i = 0; i < 6; i++) parts.push(`<rect x="${bx + 9 + i * ((bw - 18) / 6)}" y="${by + 36}" width="${(bw - 18) / 6 - 2}" height="30" class="hex ${on ? "on" : ""}"/>`);
      }
      if (big) parts.push(`<rect x="${bx + bw}" y="${by + 6}" width="14" height="30" rx="2" class="unit"/>`);
    }
    // flue
    if (["gas_boiler", "modulating_boiler"].includes(k)) {
      const fy = by + 7, ex = X0 - 12;
      parts.push(`<path d="M${bx + bw / 2},${by} V${fy - 8} Q${bx + bw / 2},${fy - 14} ${bx + bw / 2 - 6},${fy - 14} H${ex}" class="flue"/><rect x="${ex - 7}" y="${fy - 20}" width="9" height="12" rx="2" class="fluecap"/>`);
      if (on) for (let i = 0; i < 3; i++) parts.push(`<circle cx="${ex - 10}" cy="${fy - 16}" r="${4 + i}" class="puff a-puff" style="animation-delay:${(-i * 0.9).toFixed(1)}s"/>`);
    } else if (k === "pellet_boiler") {
      const ex = X0 - 16;
      parts.push(`<path d="M${bx + bw / 2},${by} V${by - 6} H${ex + 6}" class="flue"/><rect x="${ex - 6}" y="${apexY + RH * 0.45}" width="16" height="${by - apexY - RH * 0.45 + 6}" class="chim"/>`);
      if (on) for (let i = 0; i < 3; i++) parts.push(`<circle cx="${ex + 2}" cy="${apexY + RH * 0.45 - 4}" r="${4 + i}" class="puff a-puff" style="animation-delay:${(-i * 0.9).toFixed(1)}s"/>`);
    }
    // expansion tank (+ buffer tank)
    const tx = bx + bw + 12, ty = by + 26;
    parts.push(`<path d="M${tx + 8},${ty + 40} V${g.yRH}" class="pp pp-r" style="stroke-width:3"/><rect x="${tx}" y="${ty}" width="16" height="40" rx="8" fill="url(#${P}tank)" filter="url(#${P}sh)"/>`);
    if (src.buffer && b.w > 150) {
      const cx = tx + 26, cw = Math.min(30, rfx - cx - 10);
      if (cw > 18) parts.push(`<rect x="${cx}" y="${by - 4}" width="${cw}" height="${bh + 8}" rx="${cw / 2.6}" fill="url(#${P}steel)" filter="url(#${P}sh)"/>${isNum(src.bufferTemp) ? `<text x="${cx + cw / 2}" y="${by + bh / 2}" class="tiny" text-anchor="middle">${esc(deg(src.bufferTemp, lang))}</text>` : ""}`);
    }
    // pump on the return stub
    const py = by + bh + 14;
    roomOverlays.push(`<g transform="translate(${rx1},${py})"><circle r="8" class="pump" filter="url(#${P}sh)"/><g class="${flowing ? "a-spin" : ""}"><path d="M0,-5 L1.5,0 L0,5 L-1.5,0Z M-5,0 L0,1.5 L5,0 L0,-1.5Z" class="rotor"/></g></g>`);
    // status label
    const name = L.kinds[k] || k;
    const st = ROOM_UNIT_KINDS.includes(k) ? "" : ["gas_boiler", "modulating_boiler", "pellet_boiler"].includes(k) ? (on ? L.burning : L.idle) : (on ? L.running : L.idle);
    const lx = b.x1 - I - 4, ly = b.y0 + CD + 13;
    const maxW = b.w - 2 * I - 8;
    roomOverlays.push(pill(lx, ly, fit(src.name && !narrow ? `${name}` : name, 11.5, maxW - 20, 700), { cls: on ? "pon" : "poff", anchor: "end", size: 11.5, weight: 700 }));
    const st2 = [st];
    if (src.power && isNum(src.power.value)) st2.push(`${tn(src.power.value, lang, src.power.value < 10 ? 1 : 0)} ${src.power.unit}`);
    roomOverlays.push(pill(lx, ly + 20, st2.filter(Boolean).join(" · "), { cls: on ? "pon2" : "poff2", anchor: "end", size: 11 }));
    if (src.fault) roomOverlays.push(pill(lx, ly + 40, L.fault, { cls: "pwarn", anchor: "end", size: 11 }));
    out.push(`<g class="hs" data-key="source" role="button" tabindex="0" aria-label="${esc(name)}"><title>${esc(`${name}${src.name ? " – " + src.name : ""}: ${st}`)}</title><rect x="${b.x0}" y="${b.y0}" width="${b.w}" height="${b.h}" class="hit"/>${parts.join("")}</g>`);
  }

  function drawRoom(g) {
    const r = g.cell.room;
    const b = roomBox(g, `room k-${r.kind}${r.heating ? " warm" : ""}${r.zone ? " zone" : ""}`);
    const parts = [], labels = [];
    const usable = b.w - 2 * I;
    const em = r.emitter || "none";
    const right = b.x1 - I - 10; // right slot edge
    let slotL = right; // left edge of the right slot (emitter)
    g.branch = [];
    const rowI = g.row;
    // ---- emitter ----
    if (em === "radiator" || em === "fan_coil") {
      const heads = r.trvs.length ? r.trvs.slice(0, usable > 190 ? 2 : 1) : [null];
      const rw = narrow ? 44 : 50, rh = 32, gap = 26;
      let x = right - rw;
      heads.slice().reverse().forEach((t, idx) => {
        const ry = b.yB - 7 - rh;
        const hot = r.heating && (!t || t.state === "heating" || t.state === "unknown");
        if (hot) parts.push(`<ellipse cx="${x + rw / 2}" cy="${ry + rh / 2}" rx="${rw * 0.9}" ry="${rh}" fill="url(#${P}glow)" class="a-pulse"/>`);
        if (em === "fan_coil") {
          parts.push(`<rect x="${x}" y="${ry}" width="${rw}" height="${rh}" rx="4" fill="url(#${P}${hot ? "radh" : "radc"})" class="rad"/><circle cx="${x + rw / 2}" cy="${ry + rh / 2}" r="10" class="fan"/><g transform="translate(${x + rw / 2},${ry + rh / 2})"><g class="${hot ? "a-spin" : ""}"><path d="M0,0 L-2,-8 L2,-8Z M0,0 L8,-2 L8,2Z M0,0 L2,8 L-2,8Z M0,0 L-8,2 L-8,-2Z" class="rotor"/></g></g>`);
        } else {
          parts.push(`<rect x="${x}" y="${ry}" width="${rw}" height="${rh}" rx="3" fill="url(#${P}${hot ? "radh" : "radc"})" class="rad"/>`);
          for (let c = x + 5; c < x + rw - 3; c += 5) parts.push(`<line x1="${c}" y1="${ry + 3}" x2="${c}" y2="${ry + rh - 3}" class="radl"/>`);
          parts.push(`<rect x="${x + 2}" y="${b.yB - 7}" width="3" height="5" class="radl2"/><rect x="${x + rw - 5}" y="${b.yB - 7}" width="3" height="5" class="radl2"/>`);
        }
        if (hot) for (let s = 0; s < 3; s++) parts.push(`<path d="M${x + rw * (0.25 + s * 0.25)},${ry - 4} q-3,-5 0,-10 q3,-5 0,-10" class="shim a-rise" style="animation-delay:${(-s * 0.7).toFixed(1)}s"/>`);
        // valve + TRV head (left top)
        const vx = x - 5, vy = ry + 6;
        g.branch.push({ fx: vx, rx: x + rw + 5,
          fpath: `M${vx},${yFl(rowI)} V${vy} H${x}`, rpath: `M${x + rw},${ry + rh - 6} H${x + rw + 5} V${yRt(rowI)}` });
        if (t) {
          const stc = t.state === "heating" ? "trv-h" : t.state === "off" ? "trv-o" : "trv-i";
          parts.push(`<rect x="${vx - 4}" y="${vy - 17}" width="8" height="13" rx="3" class="trv ${stc}"/><rect x="${vx - 4}" y="${vy - 7}" width="8" height="3" class="trvr ${stc}"/>`);
          const hidden = idx === heads.length - 1 ? r.trvs.length - heads.length : 0;
          const txt = `${deg(t.temp, lang)}→${tn(t.target, lang)}°${hidden > 0 ? ` +${hidden}` : ""}`;
          labels.push(pill(x + rw / 2 - 3, ry - 30 - (idx % 2) * 0, txt, { cls: `ptrv ${stc}`, anchor: "middle", size: narrow ? 10.5 : 11, key: `trv:${t.id}`, icon: null }));
        }
        slotL = x - 8;
        x -= rw + gap;
      });
    } else if (em === "floor") {
      // underfloor loop on the floor plane (serpentine; flow red -> return blue)
      const lanes = [0.82, 0.55, 0.28];
      const P2 = (u, v) => [lerp(lerp(b.x0 + I, b.x0, v), lerp(b.x1 - I, b.x1, v), u), lerp(b.yB, b.y1, v)];
      const u0 = 0.06, u1 = 0.94;
      const pts = [];
      lanes.forEach((v, i) => { const a = i % 2 === 0 ? [u0, u1] : [u1, u0]; pts.push(P2(a[0], v), P2(a[1], v)); });
      const start = P2(u0, 1), end = P2(u1, 1);
      const segs = [];
      let prev = start;
      for (const p of pts) { segs.push([prev, p]); prev = p; }
      // back to the front-right along the right edge
      segs.push([prev, P2(u1 + 0.02, 0.18)]); segs.push([P2(u1 + 0.02, 0.18), P2(u1 + 0.02, 1)]);
      const cols = ["#e53935", "#ec407a", "#ab47bc", "#7e57c2", "#5c6bc0", "#1e88e5", "#1e88e5", "#1e88e5"];
      segs.forEach(([p, q], i) => parts.push(`<path d="M${p[0].toFixed(1)},${p[1].toFixed(1)} L${q[0].toFixed(1)},${q[1].toFixed(1)}" class="ufh" stroke="${cols[Math.min(i, cols.length - 1)]}"/>`));
      const dAll = `M${start[0].toFixed(1)},${start[1].toFixed(1)} ` + segs.map(([, q]) => `L${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" ");
      if (r.heating && flowing) parts.push(`<path d="${dAll}" class="fl fl-u a-fl"/>`);
      if (r.heating) parts.push(`<path d="M${b.x0 + I},${b.yB} H${b.x1 - I} L${b.x1},${b.y1} H${b.x0} Z" class="ufhglow a-pulse"/>`);
      g.branch.push({ fx: start[0], rx: P2(u1 + 0.02, 1)[0], fpath: `M${start[0]},${yFl(rowI)} V${b.y1}`, rpath: `M${P2(u1 + 0.02, 1)[0]},${b.y1} V${yRt(rowI)}` });
      slotL = b.x1 - I; // free
    } else if (em === "ac") {
      const uw = narrow ? 58 : 66, ux = b.x1 - I - 10 - uw, uy = b.y0 + CD + 30;
      const on = r.unit?.running ?? r.heating;
      g.ac = { x: ux, y: uy, w: uw };
      parts.push(`<rect x="${ux}" y="${uy}" width="${uw}" height="18" rx="6" class="acu" filter="url(#${P}sh)"/><path d="M${ux + 6},${uy + 13} H${ux + uw - 6}" class="acl"/><circle cx="${ux + uw - 8}" cy="${uy + 6}" r="1.6" fill="${on ? "#66bb6a" : "#9e9e9e"}"/>`);
      if (on) {
        const cool = src.mode === "cool";
        for (let s = 0; s < 3; s++) parts.push(`<path d="M${ux + 12 + s * (uw - 24) / 2},${uy + 22} q4,10 12,16 q6,6 10,16" class="air ${cool ? "cool" : ""} a-air" style="animation-delay:${(-s * 0.5).toFixed(1)}s"/>`);
      }
      if (r.unit && (isNum(r.unit.target) || isNum(r.unit.temp))) {
        const t = `${L.unit}: ${isNum(r.unit.temp) ? deg(r.unit.temp, lang) + " → " : ""}${tn(r.unit.target, lang)}°`;
        labels.push(pill(ux + uw, uy - 11, t, { cls: on ? "pon2" : "poff2", size: 10.5, anchor: "end" }));
      }
    } else if (em === "electric" || em === "storage") {
      const on = r.unit?.running ?? r.heating;
      const ew = narrow ? 46 : 54, eh = 40, ex = right - ew, ey = b.yB - 4 - eh;
      if (on) parts.push(`<ellipse cx="${ex + ew / 2}" cy="${ey + eh / 2}" rx="${ew}" ry="${eh}" fill="url(#${P}glow)" class="a-pulse"/>`);
      if (em === "electric") {
        const n = 6, fw = ew / n;
        for (let i = 0; i < n; i++) parts.push(`<rect x="${ex + i * fw + 0.6}" y="${ey}" width="${fw - 1.2}" height="${eh}" rx="${fw / 2.2}" ${on ? `fill="url(#${P}oil)"` : ""} class="oil ${on ? "on" : ""}"/>`);
        parts.push(`<rect x="${ex + 3}" y="${ey + eh - 2}" width="${ew - 6}" height="4" rx="2" class="oilb"/><circle cx="${ex + 6}" cy="${b.yB}" r="2.4" class="oilb"/><circle cx="${ex + ew - 6}" cy="${b.yB}" r="2.4" class="oilb"/>`);
      } else {
        parts.push(`<rect x="${ex}" y="${ey}" width="${ew}" height="${eh}" rx="4" class="stor ${on ? "on" : ""}"/>`);
        for (let i = 0; i < 4; i++) parts.push(`<line x1="${ex + 6}" y1="${ey + 8 + i * 8}" x2="${ex + ew - 6}" y2="${ey + 8 + i * 8}" class="radl"/>`);
      }
      // cord to the socket
      const sx = b.x1 - I - 3;
      parts.push(`<path d="M${ex + ew},${ey + eh - 8} q8,0 ${sx - ex - ew - 2},-12" class="cord"/><rect x="${sx - 5}" y="${ey + eh - 26}" width="7" height="10" rx="2" class="sock"/>`);
      if (on) for (let s = 0; s < 3; s++) parts.push(`<path d="M${ex + ew * (0.25 + s * 0.25)},${ey - 4} q-3,-5 0,-10 q3,-5 0,-10" class="shim a-rise" style="animation-delay:${(-s * 0.7).toFixed(1)}s"/>`);
      const p = r.unit?.power;
      if (p && isNum(p.value)) labels.push(pill(ex + ew / 2, ey - 30, `${tn(p.value, lang, p.value < 10 ? 1 : 0)} ${p.unit}`, { cls: on ? "pon2" : "poff2", anchor: "middle", size: 10.5 }));
      slotL = ex - 8;
    }

    // ---- window (above the emitter or centred) ----
    {
      let ww = narrow ? 38 : 44; const wh = 46;
      if (em === "ac" && g.ac) { const gap = g.ac.x - (b.x0 + I + 8 + (narrow ? 58 : 56)); if (gap < ww + 8) ww = Math.max(18, gap - 8); }
      const wx = em === "radiator" || em === "fan_coil" || em === "electric" || em === "storage" ? Math.min(b.x1 - I - 8 - ww, (slotL + right) / 2 - ww / 2 + 4) : em === "ac" && g.ac ? ((b.x0 + I + 8 + (narrow ? 58 : 56)) + g.ac.x) / 2 - ww / 2 : b.x0 + b.w * 0.6 - ww / 2;
      const wy = b.y0 + CD + 22;
      const open = r.window === true;
      parts.push(`<rect x="${wx - 3}" y="${wy - 3}" width="${ww + 6}" height="${wh + 6}" rx="2" class="wframe ${open ? "open" : ""}"/><rect x="${wx}" y="${wy}" width="${ww}" height="${wh}" fill="url(#${P}gl)"/>`);
      if (night) parts.push(`<circle cx="${wx + ww * 0.7}" cy="${wy + 10}" r="1" fill="#fff"/>`);
      if (open) {
        parts.push(`<path d="M${wx + ww / 2},${wy} L${wx + ww - 4},${wy + 6} L${wx + ww - 4},${wy + wh + 6} L${wx + ww / 2},${wy + wh}Z" class="sash"/><path d="M${wx},${wy} L${wx + ww / 2 - 6},${wy + 6} L${wx + ww / 2 - 6},${wy + wh + 6} L${wx},${wy + wh}Z" class="sash"/>`);
        for (let s = 0; s < 2; s++) parts.push(`<path d="M${wx + 8 + s * 16},${wy + wh + 8} q6,6 0,12 q-6,6 0,12" class="cold a-rise2" style="animation-delay:${(-s * 0.8).toFixed(1)}s"/>`);
        labels.push(pill(wx + ww / 2, wy + wh + 13, L.open, { cls: "pwarn", anchor: "middle", size: 10 }));
      } else {
        parts.push(`<line x1="${wx + ww / 2}" y1="${wy}" x2="${wx + ww / 2}" y2="${wy + wh}" class="mull"/><line x1="${wx}" y1="${wy + wh * 0.45}" x2="${wx + ww}" y2="${wy + wh * 0.45}" class="mull"/>`);
      }
      if (slotL === right || em === "floor" || em === "none" || em === "ac") slotL = Math.min(slotL, wx - 10);
    }

    // ---- furniture ----
    const fx0 = b.x0 + I + 6, fx1 = (em === "none" || em === "floor" || em === "ac") ? b.x1 - I - 6 : Math.min(slotL, b.x1 - I - 6) - 4;
    const fw = fx1 - fx0;
    if (fw > 30) {
      const s = clamp(fw / 100, 0.55, em === "none" || em === "floor" || em === "ac" ? 1.25 : 1);
      const fwid = 100 * s;
      const fx = em === "none" || em === "floor" || em === "ac" ? fx0 + (fw - fwid) * 0.15 : fx0 + Math.max(0, fw - fwid) * 0.5;
      parts.push(`<g transform="translate(${fx.toFixed(1)},${(b.yB - 60 * s).toFixed(1)}) scale(${s.toFixed(3)})" class="furn">${FURN[r.kind] ? FURN[r.kind]() : FURN.generic()}</g>`);
    }

    // ---- presence figure ----
    if (r.presence && r.presence.state === "home") {
      const px = b.x0 + I + 22 + (fw > 120 ? fw * 0.45 : fw * 0.2), py = b.yB + 2;
      parts.push(`<g transform="translate(${px},${py})" class="person"><circle cx="0" cy="-36" r="5.5"/><path d="M-7,-28 Q0,-31 7,-28 L6,-12 L4,0 H1 L0,-11 L-1,0 H-4 L-6,-12Z"/></g>`);
      const who = (r.presence.who || []).join(", ");
      if (who) labels.push(pill(px, b.yB + 10, who, { cls: "pp1", anchor: "middle", size: 10 }));
    }

    // ---- wall thermostat (left) ----
    const th = r.thermostat || (isNum(r.temp) ? { temp: r.temp, target: r.target } : null);
    const tx = b.x0 + I + 8, ty = b.y0 + CD + 30;
    if (th) {
      const tW = narrow ? 58 : 56, tH = narrow ? 40 : 34;
      const cold = isNum(th.target) && isNum(th.temp) && th.temp < th.target - 0.3;
      const hot = isNum(th.target) && isNum(th.temp) && th.temp > th.target + 0.5;
      parts.push(`<rect x="${tx}" y="${ty}" width="${tW}" height="${tH}" rx="6" class="tstat ${th.hc || r.leading ? "lead" : ""}" filter="url(#${P}sh)"/><rect x="${tx + 3}" y="${ty + 3}" width="${tW - 6}" height="${tH - 6}" rx="3.5" class="tscr"/>`);
      parts.push(`<text x="${tx + tW / 2}" y="${ty + (narrow ? 20 : 17.5)}" class="tsv ${cold ? "tcold" : hot ? "thot" : ""}" text-anchor="middle">${esc(deg(th.temp, lang))}</text>`);
      const tt = isNum(th.target) ? `→ ${tn(th.target, lang)}°` : (vm.target != null && ["radiator", "floor"].includes(em) ? `≈ ${tn(vm.target, lang)}°` : "");
      if (tt) parts.push(`<text x="${tx + tW / 2}" y="${ty + (narrow ? 33 : 28)}" class="tst ${r.heating ? "heat" : ""}" text-anchor="middle">${esc(tt)}</text>`);
      if (th.hc || r.leading) parts.push(`<g transform="translate(${tx + tW},${ty})"><circle r="7" class="leadb"/><path d="M0,-4.2 L1.2,-1.3 L4.2,-1.3 L1.8,0.6 L2.7,3.6 L0,1.8 L-2.7,3.6 L-1.8,0.6 L-4.2,-1.3 L-1.2,-1.3Z" fill="#fff"/></g>`);
    }

    // ---- room name ----
    const adv = r.advice === "up" ? " ▲" : r.advice === "down" ? " ▼" : "";
    const nm = fit(r.name, 12.5, usable - 10, 700) + adv;
    labels.unshift(pill(b.x0 + I + 4, b.y0 + CD + 11, nm, { cls: `pname${r.leading ? " lead" : ""}${r.zone ? " zone" : ""}`, size: 12.5, weight: 700 }));

    const tip = [r.name, isNum(r.temp) ? deg(r.temp, lang) + "C" : null, isNum(r.target) ? `${L.target} ${tn(r.target, lang)}°` : null,
      ...r.trvs.map((t) => `${t.name}: ${deg(t.temp, lang)} → ${tn(t.target, lang)}° (${t.state === "heating" ? L.v_heating : t.state === "off" ? L.v_off : L.v_idle})${isNum(t.calibration) ? ` cal ${t.calibration > 0 ? "+" : ""}${tn(t.calibration, lang, 2)}` : ""}`),
      r.window ? `${L.open}` : null, r.door ? L.door : null, r.leading ? L.leading : null, r.zone ? L.zone : null,
      r.advice && r.advice !== "ok" ? `${r.advice}${isNum(r.deviation) ? ` (${r.deviation > 0 ? "+" : ""}${tn(r.deviation, lang, 2)} K)` : ""}` : null].filter(Boolean).join(" · ");
    out.push(`<g class="hs" data-key="room:${esc(r.key)}" role="button" tabindex="0" aria-label="${esc(tip)}"><title>${esc(tip)}</title><rect x="${b.x0}" y="${b.y0}" width="${b.w}" height="${b.h}" class="hit"/>${parts.join("")}</g>`);
    roomOverlays.push(`<g class="hs" data-key="room:${esc(r.key)}">${labels.join("")}</g>`);
  }

  function outdoorUnit(x, y, w, h, on, key, mirror = false) {
    const fr = Math.min(w, h) * 0.34, cx = mirror ? x + w * 0.58 : x + w * 0.42, cy = y + h / 2;
    let blades = "";
    for (let i = 0; i < 4; i++) blades += `<path d="M0,0 C${fr * 0.5},${-fr * 0.2} ${fr * 0.9},${-fr * 0.15} ${fr * 0.95},${fr * 0.25} C${fr * 0.5},${fr * 0.3} ${fr * 0.2},${fr * 0.2} 0,0Z" transform="rotate(${i * 90})" class="blade"/>`;
    const ax = mirror ? x + w + 2 : x - 2, dq = mirror ? 6 : -6;
    const air = on ? [0, 1, 2].map((i) => `<path d="M${ax},${cy - 10 + i * 10} q${dq},-3 ${2 * dq},0" class="air a-air2" style="animation-delay:${(-i * 0.4).toFixed(1)}s"/>`).join("") : "";
    return `<g class="hs" data-key="${esc(key)}" role="button" tabindex="0"><rect x="${x + 4}" y="${y + h - 2}" width="${w - 8}" height="6" class="pad"/><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="5" class="odu" filter="url(#${P}sh)"/>
      <circle cx="${cx}" cy="${cy}" r="${fr + 3}" class="grill"/><g transform="translate(${cx},${cy})"><g class="${on ? "a-spin-f" : ""}">${blades}</g><circle r="3" class="hub"/></g>
      <rect x="${mirror ? x + w * 0.08 : x + w * 0.78}" y="${y + 8}" width="${w * 0.14}" height="${h - 16}" rx="2" class="oduside"/>${air}</g>`;
  }
}
const roomOverlays = []; // filled during render (reset per call below)

// furniture in a 100×60 box, baseline y=60
const FURN = {
  living: () => `<path d="M8,60 v-14 q0,-4 4,-4 h4 v18z" class="pot"/><path d="M12,42 q-8,-10 -2,-20 q2,8 2,20 M12,42 q6,-14 0,-26 q-4,10 0,26 M12,42 q10,-8 8,-18 q-6,6 -8,18" class="leaf"/>
    <rect x="24" y="28" width="68" height="18" rx="7" class="f2"/><rect x="22" y="42" width="72" height="14" rx="4" class="f1"/><rect x="18" y="36" width="10" height="20" rx="4" class="f2"/><rect x="88" y="36" width="10" height="20" rx="4" class="f2"/>
    <rect x="32" y="33" width="16" height="11" rx="4" class="f3"/><rect x="66" y="33" width="16" height="11" rx="4" class="f3"/><rect x="24" y="56" width="3" height="4" class="f2"/><rect x="89" y="56" width="3" height="4" class="f2"/>`,
  bed: () => `<rect x="4" y="22" width="8" height="38" rx="2" class="f2"/><rect x="8" y="42" width="66" height="12" rx="2" class="f2"/><rect x="10" y="36" width="64" height="9" rx="3" class="f4"/>
    <rect x="13" y="31" width="17" height="8" rx="3.5" class="f4"/><path d="M30,36 h44 v10 q-22,4 -44,0z" class="f3"/><rect x="10" y="54" width="3" height="6" class="f2"/><rect x="70" y="54" width="3" height="6" class="f2"/>
    <rect x="80" y="40" width="17" height="20" rx="1.5" class="f1"/><line x1="80" y1="50" x2="97" y2="50" class="fl1"/><rect x="87" y="32" width="2" height="8" class="f2"/><path d="M83,32 h10 l-2,-7 h-6z" class="shade"/>`,
  kids: () => `<rect x="4" y="30" width="6" height="30" rx="2" class="f2"/><rect x="6" y="44" width="50" height="10" rx="2" class="f2"/><rect x="8" y="39" width="48" height="8" rx="3" class="f4"/><path d="M22,39 h34 v9 q-17,3 -34,0z" class="f3"/>
    <circle cx="16" cy="34" r="4" class="toy1"/><circle cx="13" cy="30.5" r="1.6" class="toy1"/><circle cx="19" cy="30.5" r="1.6" class="toy1"/>
    <rect x="66" y="48" width="12" height="12" class="toy2"/><rect x="78" y="48" width="12" height="12" class="toy3"/><rect x="72" y="36" width="12" height="12" class="toy1"/>`,
  kitchen: () => `<rect x="0" y="34" width="100" height="26" rx="1" class="f1"/><rect x="-2" y="31" width="104" height="4" rx="1" class="ctop"/>
    <line x1="33" y1="36" x2="33" y2="60" class="fl1"/><line x1="66" y1="36" x2="66" y2="60" class="fl1"/><rect x="14" y="40" width="6" height="2" class="f2"/><rect x="46" y="40" width="6" height="2" class="f2"/><rect x="80" y="40" width="6" height="2" class="f2"/>
    <path d="M24,31 v-9 q0,-3 4,-3 h4" class="tap"/><rect x="70" y="28" width="22" height="3" rx="1" class="f2"/><circle cx="76" cy="27" r="3" class="pan"/>
    <rect x="0" y="0" width="58" height="16" rx="1" class="f1"/><line x1="29" y1="1" x2="29" y2="16" class="fl1"/><rect x="74" y="0" width="24" height="10" rx="1" class="hood"/><path d="M78,10 h16 l4,6 h-24z" class="hood"/>`,
  dining: () => `<rect x="22" y="34" width="56" height="4" rx="1" class="f2"/><rect x="26" y="38" width="3" height="22" class="f2"/><rect x="71" y="38" width="3" height="22" class="f2"/>
    <path d="M6,60 v-24 h3 v12 h10 v12 h-3 v-9 h-7 v9z" class="f1"/><path d="M94,60 v-24 h-3 v12 h-10 v12 h3 v-9 h7 v9z" class="f1"/><circle cx="50" cy="30" r="4" class="pan"/><path d="M50,0 v10 M42,18 q8,-10 16,0z" class="shade"/>`,
  bath: () => `<path d="M2,36 h64 v8 q0,14 -14,14 h-36 q-14,0 -14,-14z" class="tub"/><rect x="0" y="33" width="68" height="4" rx="2" class="tubr"/><path d="M8,33 v-26 q0,-5 6,-5 h4 v4" class="tap"/>
    <circle cx="18" cy="9" r="3" class="tap"/><rect x="76" y="14" width="18" height="2" class="tap"/><rect x="78" y="16" width="14" height="22" rx="1" class="f3"/><rect x="74" y="44" width="22" height="16" rx="2" class="f1"/>`,
  wc: () => `<rect x="26" y="18" width="20" height="16" rx="2" class="tub"/><path d="M24,36 h30 q0,12 -10,14 l-2,10 h-12 l-2,-10 q-4,-4 -4,-14z" class="tub"/><rect x="22" y="34" width="34" height="4" rx="2" class="tubr"/>
    <rect x="68" y="30" width="24" height="7" rx="3" class="tub"/><rect x="77" y="37" width="6" height="23" class="tub"/><path d="M80,30 v-5 h4" class="tap"/><circle cx="8" cy="36" r="4" class="f4"/><rect x="2" y="34" width="6" height="2" class="f2"/>`,
  hall: () => `<rect x="10" y="4" width="3" height="56" class="f2"/><rect x="2" y="58" width="19" height="2" class="f2"/><path d="M5,8 h14" class="fl1"/><path d="M8,9 q-4,10 -2,22 h8 q2,-12 -2,-22z" class="f3"/><path d="M15,9 q6,8 3,18 h-5z" class="f4"/>
    <rect x="34" y="40" width="58" height="20" rx="1.5" class="f1"/><line x1="63" y1="42" x2="63" y2="58" class="fl1"/><rect x="48" y="4" width="30" height="30" rx="15" class="mirror"/>`,
  office: () => `<rect x="6" y="32" width="70" height="4" rx="1" class="f2"/><rect x="9" y="36" width="3" height="24" class="f2"/><rect x="58" y="36" width="16" height="24" class="f1"/>
    <rect x="22" y="10" width="30" height="19" rx="2" class="mon"/><rect x="35" y="29" width="4" height="3" class="f2"/><rect x="80" y="30" width="14" height="16" rx="3" class="f3"/><rect x="82" y="46" width="10" height="4" class="f2"/><path d="M87,50 v8 M81,60 h12" class="fl1"/>`,
  storage: () => `<rect x="8" y="2" width="84" height="58" class="f1"/><path d="M8,20 h84 M8,40 h84" class="fl1"/>
    <rect x="14" y="8" width="10" height="12" rx="2" class="jar"/><rect x="28" y="10" width="10" height="10" rx="2" class="jar2"/><rect x="60" y="6" width="22" height="14" class="toy3"/>
    <rect x="16" y="28" width="22" height="12" class="toy2"/><rect x="50" y="26" width="10" height="14" rx="2" class="jar"/><rect x="66" y="48" width="18" height="12" class="toy1"/><rect x="18" y="46" width="26" height="14" class="toy3"/>`,
  terrace: () => `<path d="M8,60 v-14 q0,-4 4,-4 h4 v18z" class="pot"/><path d="M12,42 q-8,-10 -2,-20 q2,8 2,20 M12,42 q6,-14 0,-26 q-4,10 0,26 M12,42 q10,-8 8,-18 q-6,6 -8,18" class="leaf"/>
    <path d="M30,60 v-22 q0,-6 6,-6 h20 q6,0 6,6 v22 h-4 v-10 h-24 v10z" class="f3"/><rect x="34" y="42" width="24" height="8" rx="3" class="f4"/>
    <ellipse cx="80" cy="44" rx="14" ry="3" class="f2"/><rect x="79" y="44" width="2" height="16" class="f2"/><rect x="74" y="58" width="12" height="2" class="f2"/><circle cx="80" cy="39" r="4" class="pan"/>`,
  generic: () => `<rect x="20" y="36" width="64" height="24" rx="2" class="f1"/><line x1="52" y1="38" x2="52" y2="58" class="fl1"/><rect x="34" y="30" width="10" height="6" rx="1" class="f3"/>
    <path d="M90,60 v-12 q0,-3 3,-3 h3 v15z" class="pot"/><path d="M93,45 q-6,-8 -1,-16 q2,6 1,16 M93,45 q6,-10 1,-20" class="leaf"/>`,
};

// ───────────── CSS ─────────────
const CSS = `
:host { display:block; position:relative; font-family:${FONT};
  --hv-text: var(--primary-text-color, #1f2328); --hv-acc: var(--primary-color, #03a9f4);
  --sk1:#8ccaf5; --sk2:#e4f3ff; --wallx:#d6cfc4; --slab:#b6ada0; --slabE:#8f877b; --rf1:#d2633f; --rf2:#9f3c25; --fascia:#7a4a2c; --tile:#7d2e1c;
  --attic:#f1e6d3; --side:#e8dcc8; --ceil:#f3ebdd; --back:#fbf5ea; --floor:#d6b386; --floorE:#b48d5f; --util:#e7ebee; --utilSide:#d3d9de;
  --grass:#78b85a; --soil:#9b7a55; --bush:#5e9c45; --bush2:#4b8437;
  --pill: rgba(255,255,255,.94); --pillS: rgba(0,0,0,.14); --ptext:#1f2328; --psub:#5b6168;
  --f1:#e2d3bd; --f2:#a88a68; --f3:#8fb5c9; --f4:#f5efe6; --fl1:#a88a68; --gl1:#bfe3fa; --gl2:#e9f6ff; --wframe:#ffffff; --tub:#ffffff; --tubE:#b9c2ca;
  --flow:#e53935; --flowE:#9e1d1b; --ret:#1e88e5; --retE:#0d4f8f; --hl:rgba(255,255,255,.45);
  --pf:#c62828; --pr:#1565c0; --lcd:#1b2a33; --lcdt:#7fe0ff; --tsb:#ffffff; --tsE:#c9cfd4; --stars:#fff; --moonbite:#26375e;
}
:host([dark]) {
  --hv-text: var(--primary-text-color, #e8e8e8);
  --sk1:#18263f; --sk2:#2f4469; --wallx:#57514a; --slab:#4c463f; --slabE:#2f2b27; --rf1:#9a4632; --rf2:#6a2a1b; --fascia:#3f2717; --tile:#3d150b;
  --attic:#3a342e; --side:#2e2924; --ceil:#36302a; --back:#3d3630; --floor:#5d4733; --floorE:#43321f; --util:#30363b; --utilSide:#262b30;
  --grass:#2f5c2b; --soil:#3d2f22; --bush:#2a5223; --bush2:#20421b;
  --pill: rgba(32,34,37,.92); --pillS: rgba(255,255,255,.16); --ptext:#eceff1; --psub:#b0b7bd;
  --f1:#6b5b47; --f2:#4b3d2e; --f3:#4f6e80; --f4:#8d8274; --fl1:#4b3d2e; --gl1:#355575; --gl2:#557ba0; --wframe:#c9c4bc; --tub:#d9dde0; --tubE:#8a9298;
  --flow:#ef5350; --flowE:#7f1715; --ret:#42a5f5; --retE:#0b3f73; --hl:rgba(255,255,255,.28);
  --pf:#ff8a80; --pr:#82b1ff; --tsb:#e3e6e8; --tsE:#7d858c; --moonbite:#1b2a48;
}
.wrap { position:relative; width:100%; }
svg.hv { display:block; width:100%; height:auto; border-radius:14px; overflow:hidden; user-select:none; }
svg.night { --sk1:#08112a; --sk2:#22325a; --gl1:#0f1d3d; --gl2:#2a3f6e; }
:host([dark]) svg.night { --sk1:#070d20; --sk2:#1a2747; }
.sk1 { stop-color:var(--sk1); } .sk2 { stop-color:var(--sk2); } .rf1 { stop-color:var(--rf1); } .rf2 { stop-color:var(--rf2); }
.gl1 { stop-color:var(--gl1); } .gl2 { stop-color:var(--gl2); }
.tile { fill:none; stroke:var(--tile); stroke-width:1.2; }
.star { fill:var(--stars); opacity:.8; } .moonbite { fill:var(--moonbite); }
.soil { fill:var(--soil); } .grass { fill:var(--grass); } .bush { fill:var(--bush); } .bush2 { fill:var(--bush2); }
.wallx { fill:var(--wallx); } .slab { fill:var(--slab); } .slabEdge { stroke:var(--slabE); stroke-width:1; opacity:.6; }
.attic { fill:var(--attic); } .fascia { fill:none; stroke:var(--fascia); stroke-width:3; stroke-linejoin:round; }
.side { fill:var(--side); } .ceil { fill:var(--ceil); } .back { fill:var(--back); } .floor { fill:var(--floor); } .skirt { stroke:var(--floorE); stroke-width:1.5; }
.util .back { fill:var(--util); } .util .side { fill:var(--utilSide); } .util .floor { fill:#9ea7ae; }
:host([dark]) .util .floor { fill:#454c52; }
.lampc { fill:#ffe08a; } .lampc.off { fill:#cfc6b6; }
:host([dark]) .lampc.off { fill:#6d655b; }
.room.warm .back { fill: color-mix(in srgb, var(--back) 90%, #ff9a5a); }
.zone .back { fill: color-mix(in srgb, var(--back) 88%, #7fb2d9); }
.hit { fill:transparent; }
.stair { fill:var(--f1); stroke:var(--f2); stroke-width:1; } .rail { stroke:var(--f2); stroke-width:3; stroke-linecap:round; } .rail2 { stroke:var(--f2); stroke-width:1.4; }
.hs { cursor:pointer; outline:none; }
.hs:hover > .hit, .hs:focus-visible > .hit { fill: color-mix(in srgb, var(--hv-acc) 10%, transparent); stroke:var(--hv-acc); stroke-width:2; }
.hs.sel > .hit { stroke:var(--hv-acc); stroke-width:3; fill: color-mix(in srgb, var(--hv-acc) 8%, transparent); }
.pill { fill:var(--pill); stroke:var(--pillS); stroke-width:1; }
.pill.dash { stroke-dasharray:3 2; stroke:var(--pf); }
.pt { fill:var(--ptext); dominant-baseline:auto; }
.pt.pf { fill:var(--pf); } .pt.pr { fill:var(--pr); } .pill.pf { stroke: color-mix(in srgb, var(--pf) 55%, transparent); } .pill.pr { stroke: color-mix(in srgb, var(--pr) 55%, transparent); }
.pt.pg { fill: #8a5a00; } :host([dark]) .pt.pg { fill:#ffd54f; } .pill.pg { stroke: #e0b000; }
.pt.pon, .pt.pon2 { fill:#d84315; } :host([dark]) .pt.pon, :host([dark]) .pt.pon2 { fill:#ffab91; }
.pill.pon { stroke:#ff8a50; }
.pt.poff2, .pt.po2 { fill:var(--psub); font-weight:500 !important; }
.pt.pwarn { fill:#fff; } .pill.pwarn { fill:#e53935; stroke:none; }
.pt.pp1 { fill:#2e7d32; } :host([dark]) .pt.pp1 { fill:#a5d6a7; } .pt.pp0 { fill:var(--psub); }
.pill.pname.lead { stroke:var(--hv-acc); stroke-width:1.6; }
.pill.ptrv.trv-h { stroke:#ff7043; } .pt.ptrv.trv-h { fill:#d84315; } :host([dark]) .pt.ptrv.trv-h { fill:#ffab91; }
.pt.ptrv.trv-i, .pt.ptrv.trv-o { fill:var(--psub); }
.ico { fill:currentColor; color:var(--psub); } .ico-l { fill:#fff; stroke:#9e9e9e; stroke-width:.8; }
.pt.po { font-weight:700; }
.ttl { fill:var(--hv-text); font-size:15px; font-weight:700; } .sub { fill:var(--hv-text); opacity:.75; font-size:12px; }
.bar0 { fill: color-mix(in srgb, var(--hv-text) 15%, transparent); } .bar1 { fill:#ff7043; }
.pp { fill:none; stroke-width:5.5; stroke-linecap:round; stroke-linejoin:round; }
.pp-f { stroke:var(--flow); } .pp-r { stroke:var(--ret); }
.ph { fill:none; stroke:var(--hl); stroke-width:1.3; stroke-linecap:round; stroke-linejoin:round; transform: translate(-0.9px,-0.9px); }
.fl { fill:none; stroke-linecap:round; stroke-linejoin:round; stroke-width:3.2; stroke-dasharray:0.1 13.9; }
.fl-f { stroke:#ffe0d6; } .fl-r { stroke:#d6ecff; } .fl-g { stroke:#fff3b0; stroke-width:2.6; } .fl-u { stroke:#fff; stroke-width:2.4; opacity:.9; }
.gas { fill:none; stroke:#f9c400; stroke-width:5; stroke-linejoin:round; stroke-linecap:round; } .gasv { fill:#c79c00; stroke:#7a5f00; }
.meter { fill:#cfd6dc; stroke:#7b858d; } .lcd { fill:var(--lcd); } .lcdt { fill:var(--lcdt); font-size:10.5px; font-weight:700; font-family: ui-monospace, Menlo, Consolas, monospace; }
.ref { fill:none; stroke:#c27b45; stroke-width:2.4; } .ref2 { fill:none; stroke:#eceff1; stroke-width:3.4; }
.unit { stroke: #aeb6bd; stroke-width:1; }
.flame { fill:#ff6d00; } .flame0 { fill:none; stroke:#b0b7bd; stroke-width:1.6; }
.bolt { fill:#b0b7bd; } .bolt.on { fill:#ffb300; } .hpico { fill:none; stroke:#90a4ae; stroke-width:2; } .hpico.on { stroke:#26a69a; } .hparr { fill:none; stroke:#26a69a; stroke-width:2; }
.hex { fill:#cfd8dc; } .hex.on { fill:#ffab91; }
.flue { fill:none; stroke:#aab3ba; stroke-width:7; stroke-linecap:round; } .fluecap { fill:#8d969d; } .chim { fill:#9e5b45; }
.puff { fill:#e9edf0; opacity:0; }
.pump { fill:#263238; stroke:#90a4ae; stroke-width:1.2; } .rotor { fill:#cfd8dc; }
.rad { stroke:#aab3ba; stroke-width:1; } .radl { stroke:rgba(0,0,0,.14); stroke-width:1; } .radl2 { fill:#9aa3ab; }
.shim { fill:none; stroke:#ff8a65; stroke-width:1.6; stroke-linecap:round; opacity:0; }
.trv { fill:#fafafa; stroke:#9aa3ab; stroke-width:.8; } .trvr.trv-h { fill:#ff5722; } .trvr.trv-i { fill:#90a4ae; } .trvr.trv-o { fill:#455a64; }
.ufh { fill:none; stroke-width:3; stroke-linecap:round; opacity:.95; } .ufhglow { fill:#ff8a50; fill-opacity:.16; }
.acu { fill:#fbfbfb; stroke:#c5cbd0; } .acl { stroke:#9aa3ab; stroke-width:1.2; }
.air { fill:none; stroke:#ffab76; stroke-width:2; stroke-linecap:round; stroke-dasharray:6 6; opacity:.9; } .air.cool { stroke:#81d4fa; }
.oil { fill:#e3e7ea; stroke:#a5adb4; stroke-width:.7; } .oil.on { stroke:#e65100; } .oilb { fill:#78838b; }
.stor { fill:#d7ccc8; stroke:#8d6e63; } .stor.on { fill:#ffccbc; }
.cord { fill:none; stroke:#37474f; stroke-width:1.4; } .sock { fill:#fafafa; stroke:#9aa3ab; }
.wframe { fill:var(--wframe); stroke:rgba(0,0,0,.12); } .wframe.open { stroke:#e53935; stroke-width:1.5; }
.mull { stroke:var(--wframe); stroke-width:2; } .sash { fill: color-mix(in srgb, var(--gl1) 60%, #fff); stroke:var(--wframe); stroke-width:2; opacity:.9; }
.cold { fill:none; stroke:#4fc3f7; stroke-width:1.8; stroke-linecap:round; opacity:0; }
.tstat { fill:var(--tsb); stroke:var(--tsE); } .tstat.lead { stroke:var(--hv-acc); stroke-width:1.6; }
.tscr { fill:var(--lcd); } .tsv { fill:#e8f6ff; font-size:12.5px; font-weight:700; } .tsv.tcold { fill:#81d4fa; } .tsv.thot { fill:#ffcc80; }
.tst { fill:#9fb3bf; font-size:9.5px; font-weight:600; } .tst.heat { fill:#ffab76; }
svg.narrow .tsv { font-size:15px; } svg.narrow .tst { font-size:11.5px; } svg.narrow .ttl { font-size:17px; } svg.narrow .sub { font-size:13.5px; }
.leadb { fill:var(--hv-acc); stroke:#fff; stroke-width:1.2; }
.person { fill: color-mix(in srgb, var(--hv-acc) 75%, #333); opacity:.95; }
.furn .f1 { fill:var(--f1); } .furn .f2 { fill:var(--f2); } .furn .f3 { fill:var(--f3); } .furn .f4 { fill:var(--f4); }
.furn .fl1 { stroke:var(--fl1); stroke-width:1.2; fill:none; } .furn .pot { fill:#b5653a; } .furn .leaf { fill:none; stroke:#4c9a3f; stroke-width:3; stroke-linecap:round; }
.furn .shade { fill:#ffe0a3; stroke:#c9a46a; stroke-width:.6; } .furn .ctop { fill:#5d5348; } .furn .tap { fill:none; stroke:#9aa3ab; stroke-width:2; stroke-linecap:round; }
.furn .pan { fill:#455a64; } .furn .hood { fill:#b0bec5; } .furn .tub { fill:var(--tub); stroke:var(--tubE); stroke-width:1; } .furn .tubr { fill:var(--tubE); }
.furn .mirror { fill: color-mix(in srgb, var(--gl1) 70%, #fff); stroke:var(--f2); stroke-width:2; } .furn .mon { fill:#263238; stroke:#90a4ae; }
.furn .jar { fill:#ffcc80; } .furn .jar2 { fill:#a5d6a7; } .furn .toy1 { fill:#ef9a9a; } .furn .toy2 { fill:#90caf9; } .furn .toy3 { fill:#c5a37a; }
.odu { fill:#f3f4f5; stroke:#b7bec4; } .grill { fill:#37474f; } .blade { fill:#b0bec5; } .hub { fill:#eceff1; } .oduside { fill:#dfe3e6; } .pad { fill:#9e9e9e; }
.tiny { fill:#263238; font-size:9px; font-weight:700; }
/* animations (only when the motion preference allows) */
@keyframes hvfl { to { stroke-dashoffset:-14; } }
@keyframes hvspin { to { transform: rotate(360deg); } }
@keyframes hvrise { 0% { transform: translateY(6px); opacity:0; } 30% { opacity:.85; } 100% { transform: translateY(-10px); opacity:0; } }
@keyframes hvrise2 { 0% { transform: translateY(-4px); opacity:0; } 30% { opacity:.9; } 100% { transform: translateY(10px); opacity:0; } }
@keyframes hvpuff { 0% { transform: translate(0,0) scale(.6); opacity:.0; } 20% { opacity:.85; } 100% { transform: translate(-6px,-26px) scale(1.6); opacity:0; } }
@keyframes hvpulse { 0%,100% { opacity:.65; } 50% { opacity:1; } }
@keyframes hvflk { 0%,100% { transform: scale(1,1); } 50% { transform: scale(.92,1.08); } }
@keyframes hvtw { 0%,100% { opacity:.85; } 50% { opacity:.25; } }
@keyframes hvair { to { stroke-dashoffset:-24; } }
@media (prefers-reduced-motion: no-preference) {
  .a-fl { animation: hvfl var(--spd,1.4s) linear infinite; animation-delay: var(--hv-delay, 0s); }
  .a-spin, .a-spin-f { animation: hvspin .9s linear infinite; }
  .a-spin-f { animation-duration: .6s; }
  .a-rise { animation: hvrise 2.4s ease-in infinite; transform-box: fill-box; }
  .a-rise2 { animation: hvrise2 2.2s ease-in infinite; }
  .a-puff { animation: hvpuff 2.7s ease-out infinite; transform-box: fill-box; transform-origin:center; }
  .a-pulse { animation: hvpulse 2.6s ease-in-out infinite; }
  .a-flk { animation: hvflk .5s ease-in-out infinite; transform-box: fill-box; transform-origin: 50% 100%; }
  .a-tw { animation: hvtw 3.5s ease-in-out infinite; }
  .a-air, .a-air2 { animation: hvair 1.1s linear infinite; }
}
@media (prefers-reduced-motion: reduce) {
  .shim, .cold { opacity:.7; } .puff { opacity:.5; }
}
:host([reduced-motion]) .a-fl, :host([reduced-motion]) .a-spin, :host([reduced-motion]) .a-spin-f, :host([reduced-motion]) .a-rise,
:host([reduced-motion]) .a-rise2, :host([reduced-motion]) .a-puff, :host([reduced-motion]) .a-pulse, :host([reduced-motion]) .a-flk,
:host([reduced-motion]) .a-tw, :host([reduced-motion]) .a-air, :host([reduced-motion]) .a-air2 { animation:none !important; }
:host([reduced-motion]) .shim, :host([reduced-motion]) .cold { opacity:.7; } :host([reduced-motion]) .puff { opacity:.5; }
.a-spin, .a-spin-f { transform-box: fill-box; transform-origin: center; }
`;


// ───────────── custom element ─────────────
const _Base = typeof HTMLElement !== "undefined" ? HTMLElement : class {};
class HcHouseView extends _Base {
  static get observedAttributes() { return ["dark", "lang"]; }
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `<style>${CSS}</style><div class="wrap"></div>`;
    this._wrap = this.shadowRoot.querySelector(".wrap");
    this._w = 0; this._bucket = null; this._sig = null;
    this._wrap.addEventListener("click", (e) => this._pick(e));
    this._wrap.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this._pick(e); } });
    // the element may be created (and given its data) before this module defined it: such values sit on the instance as
    // plain properties and hide the setters below, so the view never got its data (blank after a reload). Re-apply them.
    for (const p of ["extras", "info", "model", "selected", "hass", "dark"]) {
      if (Object.prototype.hasOwnProperty.call(this, p)) { const v = this[p]; delete this[p]; this[p] = v; }
    }
  }
  connectedCallback() {
    if (!this._ro && "ResizeObserver" in window) {
      this._ro = new ResizeObserver((en) => {
        const w = en[0]?.contentRect?.width || 0;
        if (w > 0 && Math.abs(w - this._w) >= 1) { this._w = w; this._render(); }
      });
      this._ro.observe(this);
    }
    this._autoDark();
    this._render();
    // re-attached (the info panel moves the element on each refresh): animations restart, keep their phase
    const el = this._wrap.firstElementChild;
    if (el) el.style.setProperty("--hv-delay", `${-(performance.now() / 1000).toFixed(3)}s`);
  }
  disconnectedCallback() { this._ro?.disconnect(); this._ro = null; }
  attributeChangedCallback() { this._sig = null; this._render(); }
  set extras(x) { this._extras = x || {}; if (this._info) this._build(); this._render(); }
  get extras() { return this._extras; }
  set info(info) { this._info = info; this._build(); this._render(); }
  // the view model from the info data; a failure keeps the last good model (and says why) instead of blanking the view
  _build() {
    try { this._vm = fromInfo(this._info, { lang: this.lang, ...(this._extras || {}) }); }
    catch (e) { console.warn("HC house view: model", e); }
  }
  set model(vm) { this._vm = vm; this._render(); }
  get model() { return this._vm; }
  set hass(h) { this._hass = h; if (h?.themes && typeof h.themes.darkMode === "boolean" && !this.hasAttribute("theme-locked")) this.dark = h.themes.darkMode; }
  set dark(v) { this.toggleAttribute("dark", !!v); }
  get dark() { return this.hasAttribute("dark"); }
  get lang() { return this.getAttribute("lang") || this._extras?.lang || "en"; }
  set selected(key) { this._sel = key; this._mark(); }
  _autoDark() {
    if (this.hasAttribute("dark") || this.hasAttribute("light")) return;
    const c = getComputedStyle(this).getPropertyValue("--card-background-color").trim();
    let lum = null;
    const m = c.match(/^#([0-9a-f]{3,8})$/i);
    if (m) { let h = m[1]; if (h.length === 3) h = h.split("").map((q) => q + q).join(""); const n = parseInt(h.slice(0, 6), 16); lum = (0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255; }
    const r = c.match(/rgba?\(([^)]+)\)/); if (r) { const [a, b, d] = r[1].split(",").map(parseFloat); lum = (0.299 * a + 0.587 * b + 0.114 * d) / 255; }
    if (lum == null && window.matchMedia) lum = window.matchMedia("(prefers-color-scheme: dark)").matches ? 0 : 1;
    if (lum != null && lum < 0.5) this.setAttribute("dark", "");
  }
  _render() {
    if (!this._vm || !this.shadowRoot) return;
    const measured = this._w || this.getBoundingClientRect().width || 0;
    // not laid out yet (width 0): draw at a fallback width now, and measure again on the next frame (once)
    if (!measured && !this._rafPending && this.isConnected && typeof requestAnimationFrame === "function") {
      this._rafPending = true;
      requestAnimationFrame(() => {
        this._rafPending = false;
        const w2 = this.getBoundingClientRect().width;
        if (w2 > 0 && !this._w) { this._w = w2; this._render(); }
      });
    }
    const w = measured || 900;
    const narrow = w < 560, Cmax = clamp(Math.floor(w / 185), 2, 5);
    const bucket = `${narrow}|${Cmax}`;
    const sig = JSON.stringify(this._vm) + bucket;
    if (sig === this._sig && this._wrap.firstElementChild) return;
    let svg;
    try { ({ svg } = renderHouse(this._vm, { width: w, narrow, idPrefix: "hv" })); }
    catch (e) { console.warn("HC house view: render", e); this._sig = null; return; }  // the next data retries
    this._sig = sig;
    this._wrap.innerHTML = svg;
    // keep the flow animation phase continuous across re-renders
    const el = this._wrap.firstElementChild;
    if (el) el.style.setProperty("--hv-delay", `${-(performance.now() / 1000).toFixed(3)}s`);
    this._mark();
  }
  _mark() { this._wrap.querySelectorAll(".hs.sel").forEach((n) => n.classList.remove("sel")); if (this._sel) this._wrap.querySelectorAll(`[data-key="${CSS_ESC(this._sel)}"]`).forEach((n) => n.classList.add("sel")); }
  _pick(e) {
    const n = e.composedPath().find((q) => q?.dataset?.key);
    if (!n) return;
    this.dispatchEvent(new CustomEvent("hc-house-select", { detail: { key: n.dataset.key }, bubbles: true, composed: true }));
  }
}
const CSS_ESC = (s) => String(s).replace(/["\\]/g, "\\$&");
if (typeof customElements !== "undefined" && !customElements.get("hc-house-view")) customElements.define("hc-house-view", HcHouseView);
export { HcHouseView, TXT };

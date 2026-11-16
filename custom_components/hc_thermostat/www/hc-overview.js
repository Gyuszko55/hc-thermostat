// hc-overview.js — 0.60.0: the house at a glance, the hydraulic diagram and the mixing circuit's heating curve.
// Pure functions from the HC info data (websocket hc_thermostat/info of the house's instances) to HTML / SVG strings;
// the HC info panel shows them. No state, no Home Assistant calls, nothing is switched.
//
//   renderOverview(all, { lang })   all = [host info, ...member infos]  -> HTML (cards)
//   renderSchematic(all, { lang })  -> SVG: outdoor | plant room (sources, tank, mixing circuits) | the rooms per circuit
//   curveSvg(cfg, st, { lang })     cfg = a circuit's config, st = its decision -> SVG of the curve
//   curveTable(cfg, outdoor, lang)  -> rows for a text preview
//
// Everything clickable carries data-key="member:<entry id>" (the panel opens that instance).

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const isNum = (v) => typeof v === "number" && isFinite(v);
const num = (v) => { if (isNum(v)) return v; const n = parseFloat(v); return isFinite(n) ? n : null; };
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

export const OV_TXT = {
  hu: {
    system: "Rendszer", why: "Miért kér vagy nem kér hőt?", sources: "Hőforrások", tank: "Puffer", circuits: "Keverőkörök",
    rooms: "Helyiségek", warnings: "Figyelmeztetések", none: "nincs", outdoor: "Kint", mode: "Vezérlés",
    shadow: "árnyék", trial: "felügyelt próba", active: "aktív", permanent: "aktív (írás)", off: "ki",
    wood: "Fatüzelés", hp: "Hőszivattyú", active_: "aktív", inactive: "inaktív", runs: "fut", stands: "áll", unknown: "nem ismert",
    request: "HC kérés", on: "ON", offv: "OFF", demand: "hőigény", yes: "igen", no: "nem", reason: "ok", power: "teljesítmény",
    age: "mérés kora", target: "cél", flowTarget: "előremenő cél", raw: "számított", curve: "görbe szerint", plc: "PLC célja most",
    written: "kiírás", lasting: "tartós igény", asking: "kér most", usable: "a pufferből", charge: "töltöttség (meglévő érzékelő)",
    stored: "becsült tárolt hő (rétegekből)", trend: "trend", charging: "töltődik", emptying: "merül", steady: "állandó",
    top: "teteje", bottom: "alja", meas: "mért", tgt: "cél", ask: "kér", cmd: "HC parancs", relay: "valódi relé",
    differs: "eltér (árnyékban rendben)", room: "Helyiség", stale: "elavult", min: "perc", s: "mp", need: "a körök igénye",
    whyNoHeat: "Most nincs hőigény.", kinds: { onoff_boiler: "Gázkazán", modulating_boiler: "Moduláló kazán", heat_pump: "Hőszivattyú", electric_boiler: "Villanykazán", air_conditioner: "Klíma", electric_heater: "Elektromos fűtő", storage_heater: "Hőtárolós kályha", district_heating: "Távhő", pellet_boiler: "Pelletkazán", external_heat: "Külső hőtermelő" },
    burning: "ég", idle: "áll", unitsCol: "Helyiségi egységek", unheated: "nem fűti", sharedRoom: "2 körön", woodBy: "a kazán hőmérője szerint", woodPending: "vált:", woodLv: { certain: "biztos", likely: "valószínű", possible: "lehetséges", none: "nincs" },
    wst: { shadow: "nem ír (árnyék)", none: "nincs kimenet", in_sync: "egyezik", write: "ír", confirming: "visszaigazolásra vár", grace: "indulási türelem", keepalive: "frissítés", conflict: "ütközés", not_accepted: "nem fogadja el", unavailable: "nem elérhető", no_value: "nincs érték", error: "hiba" },
    hst: { no_data: "a hőforrás teljesítménymérője / lángjele nem ad adatot", uncommanded_burn: "parancs nélkül ég", overheating: "túlfűt", no_response: "a kazán nem reagál a relére", no_flame: "nem gyújt be", heating_fault: "fűtési hiba (sokáig fűt, a ház mégis hűl)", short_cycling: "taktol" }, hstLbl: "hőforrás-figyelés", plant: "KAZÁNHÁZ", demanded: "igényelt (a hőszivattyúnak)", capSt: { off: "nincs korlát", ok: "a puffer elég meleg", limited: "a puffer korlátozza a keverő célját", cold: "hideg a puffer – a minimum sem jön ki", stale: "az utolsó jó pufferérték szerint", no_data: "nincs pufferadat – nem korlátoz" }, outside: "KÜLTÉR", house: "HELYISÉGEK",
    coil: "csőkígyó", mixer: "keverő + szivattyú", layer: "Puffer", hpLong: "Levegő–víz hőszivattyú", coilCharge: "csőkígyós töltés", woodBoiler: "Fatüzelésű kazán",
    dhw: "HMV", dhwPump: "HMV-szivattyú", dhwHeater: "villanyfűtés", dhwTank: "HMV (bojler)", dhwFrom: "melegvíz a pufferből", mixerPump: "keverőszelep + szivattyú", pumpLbl: "Keringető szivattyú", pumpPlc: "szivattyú (PLC)", flowMeas: "mért előremenő", pumpEnable: "HC szerint engedély:", radS: "radiátor", floorS: "padlófűtés",
    legend: "Jelmagyarázat", legFlow: "Előremenő (meleg víz)", legReturn: "Visszatérő (hűlt víz)", legPump: "Keringető szivattyú", legValve: "Keverőszelep (háromjáratú)", legSensor: "Hőmérséklet-érzékelő",
    control: "Vezérlés", coilNote: "A hőszivattyú a puffert csőkígyón keresztül fűti", woodNote: "A fatüzelés közvetlenül a puffert tölti, elsőbbséggel", direct: "közvetlenül", normal: "normál görbe", corrected: "helyiséghiánnyal",
    limits: "korlátok", now: "most", given: "kiadott cél", outdoorAxis: "kinti hőmérséklet (°C)", flowAxis: "előremenő (°C)",
    deficit: "helyiséghiány", lowWaits: "alacsony töltöttség, de nincs helyiségi igény: nem indít",
    hpWhy: { fail_safe_on: "nincs kinti mérés – biztonsági ON", no_outdoor: "nincs kinti mérés – változatlan", no_buffer: "nincs pufferhőfok – változatlan",
      cold_on: "hideg idő miatt ON", frost: "puffer fagyvédelem", low_charge: "alacsony puffer-töltöttség", heat_needed: "a puffer teteje a körök igénye alatt",
      heating: "fűt, amíg a puffer teteje el nem éri az igény + hiszterézist", charging: "tölt a kikapcsolási töltöttségig",
      wood: "a fa tölti a puffert – a hőszivattyú vár", summer: "nyári üzem", idle_off: "régóta nincs igény – OFF", standby: "készenlét (ON, nem fűt)",
      off: "nincs igény", min_on: "minimális futásidő tartja", min_off: "minimális szünet tartja",
      reserve_low: "kevés a tartalék az igény fölött – tölt", reserve_low_kwh: "kevés a hő-tartalék (kWh) – tölt", charging_reserve: "tartalékot tölt a leállítási rétegig",
      reserve_ok: "van elég tartalék az igény fölött", reserve_full: "feltöltve – a tartalék megvan", no_demand: "nincs tartós hőigény", reserve_runs_out: "a fogyás üteme szerint hamarosan elfogy a tartalék – tölt" },
    chMode: { classic: "klasszikus", demand: "igény szerinti" }, reserve: "tartalék", other: "a másik szabály",
  },
  en: {
    system: "System", why: "Why is heat asked for, or not?", sources: "Heat sources", tank: "Buffer tank", circuits: "Mixing circuits",
    rooms: "Rooms", warnings: "Warnings", none: "none", outdoor: "Outdoor", mode: "Control",
    shadow: "shadow", trial: "supervised trial", active: "active", permanent: "active (writing)", off: "off",
    wood: "Wood", hp: "Heat pump", active_: "active", inactive: "inactive", runs: "runs", stands: "stands", unknown: "not known",
    request: "HC request", on: "ON", offv: "OFF", demand: "heat demand", yes: "yes", no: "no", reason: "reason", power: "power",
    age: "reading age", target: "target", flowTarget: "flow target", raw: "worked out", curve: "by the curve", plc: "PLC target now",
    written: "writing", lasting: "lasting demand", asking: "asking now", usable: "from the tank", charge: "charge (existing sensor)",
    stored: "estimated stored heat (layers)", trend: "trend", charging: "charging", emptying: "emptying", steady: "steady",
    top: "top", bottom: "bottom", meas: "measured", tgt: "target", ask: "asks", cmd: "HC command", relay: "real relay",
    differs: "differs (fine in shadow)", room: "Room", stale: "stale", min: "min", s: "s", need: "the circuits' need",
    whyNoHeat: "No heat demand now.", kinds: { onoff_boiler: "Gas boiler", modulating_boiler: "Modulating boiler", heat_pump: "Heat pump", electric_boiler: "Electric boiler", air_conditioner: "Air conditioner", electric_heater: "Electric heater", storage_heater: "Storage heater", district_heating: "District heating", pellet_boiler: "Pellet boiler", external_heat: "External heat source" },
    burning: "burning", idle: "idle", unitsCol: "Room units", unheated: "not heated", sharedRoom: "on 2 circuits", woodBy: "by the boiler's thermometer", woodPending: "changing:", woodLv: { certain: "certain", likely: "likely", possible: "possible", none: "none" },
    wst: { shadow: "not writing (shadow)", none: "no output", in_sync: "in sync", write: "writing", confirming: "awaiting confirmation", grace: "start grace", keepalive: "keep-alive", conflict: "conflict", not_accepted: "not accepted", unavailable: "unavailable", no_value: "no value", error: "error" },
    hst: { no_data: "the source's power / flame reading gives no data", uncommanded_burn: "burns without command", overheating: "overheating", no_response: "the boiler does not answer the relay", no_flame: "no ignition", heating_fault: "heating fault (long heating, the house still cools)", short_cycling: "short cycling" }, hstLbl: "source watch", plant: "PLANT ROOM", demanded: "demanded (for the heat pump)", capSt: { off: "no cap", ok: "the tank is warm enough", limited: "the tank caps the mixer's target", cold: "tank too cold – not even the minimum", stale: "by the last good tank reading", no_data: "no tank reading – not capping" }, outside: "OUTDOORS", house: "ROOMS",
    coil: "coil", mixer: "mixer + pump", layer: "Tank", hpLong: "Air-to-water heat pump", coilCharge: "coil charging", woodBoiler: "Wood boiler",
    dhw: "DHW", dhwPump: "DHW pump", dhwHeater: "electric heater", dhwTank: "Hot water (DHW tank)", dhwFrom: "hot water from the tank", mixerPump: "mixing valve + pump", pumpLbl: "Circulation pump", pumpPlc: "pump (PLC)", flowMeas: "measured flow", pumpEnable: "HC enable:", radS: "radiators", floorS: "floor heating",
    legend: "Legend", legFlow: "Flow (hot water)", legReturn: "Return (cooled water)", legPump: "Circulation pump", legValve: "Mixing valve (three-way)", legSensor: "Temperature sensor",
    control: "Control", coilNote: "The heat pump heats the tank through a coil", woodNote: "Wood charges the tank directly, first", direct: "direct", normal: "normal curve", corrected: "with room deficit",
    limits: "limits", now: "now", given: "given-out target", outdoorAxis: "outdoor temperature (°C)", flowAxis: "flow (°C)",
    deficit: "room deficit", lowWaits: "low charge, but no room asks: no start",
    hpWhy: { fail_safe_on: "no outdoor reading – fail-safe ON", no_outdoor: "no outdoor reading – unchanged", no_buffer: "no tank reading – unchanged",
      cold_on: "ON for cold weather", frost: "tank frost protection", low_charge: "low tank charge", heat_needed: "the tank top is below the circuits' need",
      heating: "heats until the tank top reaches the need + hysteresis", charging: "charges up to the stop charge",
      wood: "wood charges the tank – the heat pump waits", summer: "summer mode", idle_off: "no demand for long – OFF", standby: "standby (ON, not heating)",
      off: "no demand", min_on: "held by the minimum run", min_off: "held by the minimum pause",
      reserve_low: "low reserve above the need – charging", reserve_low_kwh: "low heat reserve (kWh) – charging", charging_reserve: "charging the reserve up to the stop layer",
      reserve_ok: "enough reserve above the need", reserve_full: "charged – the reserve is there", no_demand: "no lasting heat demand", reserve_runs_out: "at this pace the reserve runs out soon – charging" },
    chMode: { classic: "classic", demand: "by demand" }, reserve: "reserve", other: "the other rule",
  },
};

const short = (t) => String(t || "").replace(/^\s*hc(?=[\s:\-–]|$)[\s:\-–]*/i, "").trim() || String(t || "");
const deg = (v, lang, d = 1) => (isNum(v) ? `${(Math.round(v * 10 ** d) / 10 ** d).toFixed(d).replace(".", lang === "hu" ? "," : ".")} °C` : "–");
const fx = (v, lang, d = 1) => (isNum(v) ? (Math.round(v * 10 ** d) / 10 ** d).toFixed(d).replace(".", lang === "hu" ? "," : ".") : "–");
const ent = (i, k) => ((i?.entities || {})[k] || [])[0] || null;

// ---------------------------------------------------------------- the model of the house
export function collect(all) {
  const list = (all || []).filter((i) => i && i.entry_id);
  const by = (r) => list.filter((i) => (i.role || "standalone") === r);
  const zones = list.filter((i) => ["standalone", "zone"].includes(i.role || "standalone"));
  const circuits = by("circuit"), tanks = by("buffer"), hps = by("hp_coord"), centrals = by("central");
  const zoneOf = (eid) => zones.find((z) => z.climate?.entity_id === eid) || null;
  const circuitZones = (c) => ((c.conf || {}).zone_entities || []).map((e) => ({ eid: e, info: zoneOf(e) }));
  const outdoor = [...hps.map((h) => num(h.inputs?.outdoor)), ...circuits.map((c) => num(c.decision?.outdoor)), ...zones.map((z) => num(z.decision?.outdoor))].find(isNum) ?? null;
  return { list, zones, circuits, tanks, hps, centrals, zoneOf, circuitZones, outdoor };
}

function modeTxt(i, T) {
  const w = i.write?.write_mode || i.mode || "shadow";
  if (w === "trial") return T.trial;
  if (w === "permanent") return T.permanent;
  return T[w] || w;
}

function warnings(m, T, lang) {
  const out = [];
  for (const i of m.list) {
    const n = short(i.title);
    if (i.decision?.fault || i.live?.fault) out.push(`${n}: ${lang === "hu" ? "hiba" : "fault"}`);
    for (const p of i.measure_problems || []) out.push(`${n}: ${p}`);
    for (const [k, o] of Object.entries(i.outputs || {})) {
      if (o && o.entity && ["conflict", "not_accepted", "unavailable", "error"].includes(o.status)) out.push(`${n} → ${k}: ${o.status}${o.error ? ` (${o.error})` : ""}`);
    }
    // 0.62.0: the source watch (power / flame) in words; quiet states (nothing to watch, learning) are no warning
    const hs = i.health?.state;
    if (hs && !["ok", "good", "unknown", "learning", "unwatched"].includes(hs)) out.push(`${n} – ${T.hstLbl}: ${T.hst[hs] || hs}`);
  }
  for (const c of m.circuits) {  // 0.64.0: the tank cannot give the circuit what it needs
    const cs = c.decision?.cap_state;
    if (["limited", "cold", "no_data"].includes(cs)) out.push(`${short(c.title)}: ${T.capSt[cs]}${isNum(num(c.decision?.shortfall)) && num(c.decision.shortfall) > 0 ? ` (−${fx(num(c.decision.shortfall), lang)} °C)` : ""}`);
  }
  for (const h of m.hps) {
    const det = h.decision?.details || {};
    if (det.hp_running == null && ent(h, "hp_running_entity")) out.push(`${short(h.title)}: ${T.hp} ${T.unknown}${isNum(det.hp_running_age_s) ? ` (${T.age} ${Math.round(det.hp_running_age_s / 60)} ${T.min})` : ""}`);
  }
  return out;
}

function why(m, T, lang) {
  const lines = [];
  for (const h of m.hps) {
    const d = h.decision || {}, det = d.details || {};
    const r = T.hpWhy[d.reason] || d.reason || "";
    let s = `${T.hp}: ${d.enable ? T.on : T.offv} – ${r}`;
    if (isNum(d.need) || isNum(det.top)) s += ` (${T.need} ${deg(d.need, lang)}, ${T.tank.toLowerCase()} ${T.top} ${deg(det.top, lang)})`;
    lines.push(s);
    if (det.low_charge_waits) lines.push(`${T.hp}: ${T.lowWaits}`);
    if (d.wood && d.wood !== "none") lines.push(`${T.wood}: ${T.woodLv[d.wood] || d.wood}`);
  }
  for (const c of m.circuits) {
    const d = c.decision || {};
    const asking = (d.asking || []).map((e) => short(m.zoneOf(e)?.title || e)).filter(Boolean);
    const lasting = (d.lasting || []).map((e) => short(m.zoneOf(e)?.title || e)).filter(Boolean);
    lines.push(`${short(c.title)}: ${d.demand ? `${T.lasting} (${lasting.join(", ") || "–"})` : T.whyNoHeat}${asking.length ? ` · ${T.asking}: ${asking.join(", ")}` : ""} → ${T.flowTarget} ${deg(d.target, lang)}`);
  }
  if (!m.circuits.length) {
    const asking = m.zones.filter((z) => z.decision?.output).map((z) => short(z.title));
    lines.push(asking.length ? `${T.rooms}: ${asking.join(", ")} – ${T.ask}` : T.whyNoHeat);
  }
  return lines;
}

const row = (k, v, cls = "") => `<div class="r ${cls}"><span>${esc(k)}</span><b>${v}</b></div>`;
const card = (title, body, key = "") => `<div class="card ovc" ${key ? `data-key="${esc(key)}"` : ""}><div class="ct">${esc(title)}</div>${body}</div>`;

export function renderOverview(all, opts = {}) {
  const lang = opts.lang === "en" ? "en" : "hu", T = OV_TXT[lang];
  const m = collect(all);
  const cards = [];
  // system: outdoor, modes, warnings
  const modes = m.list.map((i) => `<span class="ovm ${esc(i.write?.write_mode || i.mode || "shadow")}" data-key="member:${esc(i.entry_id)}">${esc(short(i.title))}: ${esc(modeTxt(i, T))}</span>`).join("");
  const warn = warnings(m, T, lang);
  cards.push(card(T.system, row(T.outdoor, deg(m.outdoor, lang)) + `<div class="ovmodes"><span class="lbl">${esc(T.mode)}</span>${modes}</div>`
    + `<div class="grp">${esc(T.warnings)}</div>${warn.length ? `<ul class="ovw">${warn.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : `<div class="muted">${esc(T.none)}</div>`}`));
  cards.push(card(T.why, `<ul class="ovwhy">${why(m, T, lang).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>`));
  // heat sources
  const src = [];
  for (const h of m.hps) {
    const d = h.decision || {}, det = d.details || {}, conf = h.conf || {};
    if (conf.wood_entity || conf.wood_temp_entity) {
      const we = ent(h, "wood_entity") || ent(h, "wood_temp_entity"), wi = h.wood || {};
      const wood = d.wood === "certain" || d.wood === "likely" || h.inputs?.wood_signal === true;
      src.push(row(T.wood, `${wood ? `<span class="hot">${esc(T.active_)}</span>` : esc(T.inactive)}${we ? ` <small>(${esc(we.state)}${we.unit ? " " + esc(we.unit) : ""})</small>` : ""}`));
      if (wi.by === "temp") src.push(row(`· ${T.woodBy}`, esc(`≥ ${fx(wi.on_above, lang, 0)} °C ${T.on} · ≤ ${fx(wi.off_below, lang, 0)} °C ${T.offv}${wi.pending ? ` · ${T.woodPending} ${wi.pending.to ? T.on : T.offv} (${Math.round(wi.pending.for_s / 60)}/${Math.round(wi.confirm_s / 60)} ${T.min})` : ""}`)));
    }
    const run = det.hp_running === true ? T.runs : det.hp_running === false ? T.stands : T.unknown;
    const pe = ent(h, "hp_running_entity");
    src.push(row(T.hp, esc(run)));
    if (pe) src.push(row(`· ${T.power}`, `${esc(pe.state)} ${esc(pe.unit || "")}${isNum(det.hp_running_age_s) ? ` <small>(${esc(T.age)} ${det.hp_running_age_s < 120 ? `${Math.round(det.hp_running_age_s)} ${T.s}` : `${Math.round(det.hp_running_age_s / 60)} ${T.min}`}${det.hp_running_age_s > 900 ? `, ${esc(T.stale)}` : ""})</small>` : ""}`));
    src.push(row(`· ${T.request}`, `${d.enable ? T.on : T.offv} · ${T.demand}: ${d.heat_demand ? T.yes : T.no}`));
    src.push(row(`· ${T.flowTarget}`, deg(d.target, lang)));
    src.push(row(`· ${T.reason}`, esc(T.hpWhy[d.reason] || d.reason || "–")));
    // 0.65.0: the reserve over the need and what the rule not driving would do
    const dc = det.demand_charge || {}, mode = det.charge_mode || "classic";
    if (isNum(num(dc.reserve_c))) src.push(row(`· ${T.reserve}`, `${fx(num(dc.reserve_c), lang)} °C${isNum(num(dc.reserve_kwh)) ? ` · ${fx(num(dc.reserve_kwh), lang)} kWh` : ""}${isNum(num(dc.hours_left)) ? ` · ~${fx(num(dc.hours_left), lang)} h` : ""}`));
    const alt = mode === "demand" ? det.classic : det.demand_charge;
    if (alt && alt.why) src.push(row(`· ${T.other} (${T.chMode[mode === "demand" ? "classic" : "demand"]})`, `${alt.heat ? T.on : T.offv} – ${esc(T.hpWhy[alt.why] || alt.why)}`));
  }
  for (const c of m.centrals) src.push(row(short(c.title), `${c.decision?.output ? T.on : T.offv} · ${esc(c.decision?.reason || "")}`));
  if (src.length) cards.push(card(T.sources, src.join(""), m.hps[0] ? `member:${m.hps[0].entry_id}` : ""));
  // tank
  for (const b of m.tanks) {
    const st = b.stock || {}, tr = b.trend || {}, d = b.decision || {};
    const layers = (st.layers || []).map((l) => row(`${l.name}${l.measured === false ? "*" : ""}`, deg(num(l.temp), lang))).join("");
    cards.push(card(`${T.tank}: ${short(b.title)}`, layers
      + row(T.charge, isNum(num(st.charge)) && st.charge_method === "external" ? `${fx(num(st.charge), lang, 0)} %` : "–")
      + row(T.stored, isNum(num(st.stored_kwh)) ? `${fx(num(st.stored_kwh), lang)} kWh${isNum(num(st.charge_layers)) ? ` (${fx(num(st.charge_layers), lang, 0)} %)` : ""}` : "–")
      + row(T.trend, tr.state ? `${esc(T[tr.state] || tr.state)} · ${fx(num(tr.c_per_h), lang)} °C/h` : "–")
      + row(T.request, d.output ? T.on : T.offv)
      // 0.63.0: the hot water tank charged from it (shown when its entities are set)
      + (ent(b, "dhw_temp_entity") || ent(b, "dhw_pump_entity") || ent(b, "dhw_heater_entity") ? row(T.dhw, `${deg(num(ent(b, "dhw_temp_entity")?.state), lang)}${ent(b, "dhw_pump_entity") ? ` · ${T.dhwPump}: ${isOn(ent(b, "dhw_pump_entity")) ? T.runs : isOn(ent(b, "dhw_pump_entity")) === false ? T.stands : T.unknown}` : ""}${ent(b, "dhw_heater_entity") ? ` · ${T.dhwHeater}: ${isOn(ent(b, "dhw_heater_entity")) ? T.on : isOn(ent(b, "dhw_heater_entity")) === false ? T.offv : T.unknown}` : ""}`) : ""), `member:${b.entry_id}`));
  }
  // circuits
  for (const c of m.circuits) {
    const d = c.decision || {}, det = d.details || {}, oe = ent(c, "circuit_output_entity"), w = c.outputs?.target || {};
    cards.push(card(short(c.title), row(T.flowTarget, `<b class="big">${deg(d.target, lang)}</b>`)
      // 0.64.0: the tank cap – what the circuit demands (the heat pump's need) when the mixer gets less
      + (isNum(num(d.demand_target)) && num(d.demand_target) !== num(d.target) ? row(T.demanded, `${deg(num(d.demand_target), lang)} · ${T.capSt[d.cap_state] || d.cap_state || ""}`) : "")
      + row(T.raw, deg(num(d.raw), lang)) + row(T.curve, deg(num(det.curve), lang))
      + row(T.plc, oe ? `${esc(oe.state)} ${esc(oe.unit || "")}` : "–")
      + row(T.written, esc(`${modeTxt(c, T)}${w.status && w.status !== "shadow" ? ` · ${T.wst[w.status] || w.status}` : ""}`))
      + row(T.lasting, d.demand ? T.yes : T.no)
      // 0.63.0: what the PLC reports, when given: the pump and the measured flow
      + (ent(c, "circuit_pump_entity") ? row(T.pumpPlc, isOn(ent(c, "circuit_pump_entity")) ? T.runs : isOn(ent(c, "circuit_pump_entity")) === false ? T.stands : T.unknown) : "")
      + (ent(c, "circuit_flow_entity") ? row(T.flowMeas, deg(num(ent(c, "circuit_flow_entity").state), lang)) : "")
      + row(T.usable, isNum(num(c.buffer?.usable_kwh)) ? `${fx(num(c.buffer.usable_kwh), lang)} kWh` : "–")
      + `<div class="ovcurve">${curveSvg(c.config || {}, { ...d, plc: oe ? num(oe.state) : null }, { lang, small: true })}</div>`, `member:${c.entry_id}`));
  }
  // rooms
  const rows = m.zones.map((z) => {
    const d = z.decision || {}, rel = ent(z, "actuator_entity");
    const cmd = !!d.output, real = rel ? rel.state === "on" : null;
    const diff = real !== null && real !== cmd;
    const circs = (z.circuits || []).map((q) => short(q.title)).join(" + ");
    return `<tr data-key="member:${esc(z.entry_id)}" class="${diff ? "diff" : ""}"><td><b>${esc(short(z.title))}</b>${circs ? `<small>${esc(circs)}</small>` : ""}</td>
      <td>${deg(num(d.indoor), lang)}</td><td>${deg(num(d.target), lang)}</td><td>${d.output ? `<span class="hot">${T.yes}</span>` : T.no}</td>
      <td>${cmd ? T.on : T.offv}</td><td>${real === null ? "–" : real ? T.on : T.offv}${diff ? ` <small>${esc(T.differs)}</small>` : ""}</td><td><small>${esc(modeTxt(z, T))}</small></td></tr>`;
  }).join("");
  if (rows) cards.push(`<div class="card ovc wide"><div class="ct">${esc(T.rooms)}</div><table class="ovt"><tr><th>${esc(T.room)}</th><th>${esc(T.meas)}</th><th>${esc(T.tgt)}</th><th>${esc(T.ask)}</th><th>${esc(T.cmd)}</th><th>${esc(T.relay)}</th><th>${esc(T.mode)}</th></tr>${rows}</table></div>`);
  return `<div class="ovgrid">${cards.join("")}</div>`;
}

// ---------------------------------------------------------------- the heating curve of a mixing circuit
export function curveAt(cfg, outdoor, tRoom, deficit = 0) {
  const c = { circuit_slope: 1.2, circuit_shift: 0, circuit_kp: 2, circuit_flow_min: 30, circuit_flow_max: 55, ...cfg };
  const raw = tRoom + c.circuit_slope * Math.max(tRoom - outdoor, 0) + c.circuit_shift + c.circuit_kp * Math.min(Math.max(deficit, 0), 3);
  return clamp(raw, c.circuit_flow_min, c.circuit_flow_max);
}

export function curveTable(cfg, outdoor = null, lang = "hu") {
  const tRoom = num(cfg.circuit_room) ?? 20;
  const pts = [-15, -10, -5, 0, 5, 10, 15];
  if (isNum(outdoor) && !pts.includes(Math.round(outdoor))) pts.push(Math.round(outdoor * 10) / 10);
  pts.sort((a, b) => a - b);
  return pts.map((o) => ({ outdoor: o, flow: curveAt(cfg, o, tRoom, 0), flow1: curveAt(cfg, o, tRoom, 1), now: isNum(outdoor) && Math.abs(o - outdoor) < 0.05 }));
}

export function curveSvg(cfg, st = {}, opts = {}) {
  const lang = opts.lang === "en" ? "en" : "hu", T = OV_TXT[lang];
  const c = { circuit_slope: 1.2, circuit_shift: 0, circuit_kp: 2, circuit_flow_min: 30, circuit_flow_max: 55, circuit_room: 20, ...cfg };
  const W = 420, H = opts.small ? 210 : 260, L = 38, R = 10, Tp = 12, B = 34;
  const x0 = -20, x1 = 20;
  const ymin = Math.floor((c.circuit_flow_min - 5) / 5) * 5, ymax = Math.ceil((c.circuit_flow_max + 5) / 5) * 5;
  const X = (o) => L + (o - x0) / (x1 - x0) * (W - L - R), Y = (f) => Tp + (1 - (f - ymin) / (ymax - ymin)) * (H - Tp - B);
  const tRoom = num(st.t_room) ?? num(c.circuit_room) ?? 20, deficit = num(st.deficit) ?? 0;
  const path = (dfc) => { let d = ""; for (let o = x0; o <= x1; o += 1) d += `${d ? "L" : "M"}${X(o).toFixed(1)},${Y(curveAt(c, o, tRoom, dfc)).toFixed(1)}`; return d; };
  const g = [];
  for (let o = x0; o <= x1; o += 5) g.push(`<line x1="${X(o)}" y1="${Tp}" x2="${X(o)}" y2="${H - B}" class="cg"/><text x="${X(o)}" y="${H - B + 13}" class="cx" text-anchor="middle">${o}</text>`);
  for (let f = ymin; f <= ymax; f += 5) g.push(`<line x1="${L}" y1="${Y(f)}" x2="${W - R}" y2="${Y(f)}" class="cg"/><text x="${L - 4}" y="${Y(f) + 3.5}" class="cx" text-anchor="end">${f}</text>`);
  g.push(`<line x1="${L}" y1="${Y(c.circuit_flow_min)}" x2="${W - R}" y2="${Y(c.circuit_flow_min)}" class="clim"/><line x1="${L}" y1="${Y(c.circuit_flow_max)}" x2="${W - R}" y2="${Y(c.circuit_flow_max)}" class="clim"/>`);
  g.push(`<path d="${path(0)}" class="cn"/>`);
  if (deficit > 0.05) g.push(`<path d="${path(deficit)}" class="cc"/>`);
  const out = num(st.outdoor);
  if (isNum(out) && out >= x0 && out <= x1) {
    g.push(`<line x1="${X(out)}" y1="${Tp}" x2="${X(out)}" y2="${H - B}" class="cnow"/>`);
    const raw = num(st.raw);
    if (isNum(raw)) g.push(`<circle cx="${X(out)}" cy="${Y(raw)}" r="4.5" class="craw"><title>${esc(`${T.raw}: ${deg(raw, lang)}`)}</title></circle>`);
    const tg = num(st.target);
    if (isNum(tg)) g.push(`<rect x="${X(out) - 5}" y="${Y(tg) - 5}" width="10" height="10" class="ctg"><title>${esc(`${T.given}: ${deg(tg, lang)}`)}</title></rect>`);
    const plc = num(st.plc);
    if (isNum(plc)) g.push(`<path d="M${X(out)},${Y(plc) - 6} l6,10 h-12z" class="cplc"><title>${esc(`${T.plc}: ${deg(plc, lang)}`)}</title></path>`);
  }
  g.push(`<text x="${(L + W - R) / 2}" y="${H - 4}" class="cx" text-anchor="middle">${esc(T.outdoorAxis)}</text>`);
  const leg = [[`cn`, T.normal], deficit > 0.05 ? [`cc`, `${T.corrected} (${fx(deficit, lang)} °C)`] : null, [`clim`, T.limits]].filter(Boolean);
  leg.forEach(([k, t], i) => g.push(`<line x1="${W - R - 150}" y1="${Tp + 8 + i * 13}" x2="${W - R - 132}" y2="${Tp + 8 + i * 13}" class="${k}"/><text x="${W - R - 128}" y="${Tp + 11.5 + i * 13}" class="cx">${esc(t)}</text>`));
  return `<svg class="hccurve" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(T.flowAxis)}">${g.join("")}</svg>`;
}

// 0.64.0: the heat pump's target over time – HC's raw target, the given-out one, what was really sent (rounded as
// set), what the unit reports back and, when given, the water it measures. hist = hc_thermostat/hp_history result.
const HPC = [["raw", "#9e9e9e", "4 3", { hu: "HC nyers cél", en: "HC raw target" }],
  ["target", "#43a047", "", { hu: "HC kiadott cél", en: "HC given-out target" }],
  ["sent", "#fb8c00", "", { hu: "kiküldve (kerekítve)", en: "sent (rounded)" }],
  ["reported", "#8e24aa", "2 2", { hu: "a hőszivattyú beállítása", en: "the unit's setpoint" }],
  ["water", "#1e88e5", "", { hu: "mért víz", en: "measured water" }]];
export function hpChartSvg(hist, opts = {}) {
  const lang = opts.lang === "en" ? "en" : "hu";
  const ser = (hist && hist.series) || {}, t0 = num(hist?.start), t1 = num(hist?.end);
  const vals = HPC.flatMap(([k]) => (ser[k] || []).map((p) => num(p[1])).filter(isNum));
  if (!isNum(t0) || !isNum(t1) || t1 <= t0 || !vals.length) {
    return `<div class="muted">${esc(lang === "hu" ? "Még nincs rögzített adat a grafikonhoz." : "No recorded data for the chart yet.")}</div>`;
  }
  const W = 420, H = 230, L = 34, R = 10, Tp = 10, B = 26;
  const lo = Math.floor((Math.min(...vals) - 1) / 5) * 5, hi = Math.ceil((Math.max(...vals) + 1) / 5) * 5;
  const X = (t) => L + (t - t0) / (t1 - t0) * (W - L - R), Y = (v) => Tp + (1 - (v - lo) / (hi - lo || 1)) * (H - Tp - B);
  const g = [];
  for (let v = lo; v <= hi; v += 5) g.push(`<line x1="${L}" y1="${Y(v).toFixed(1)}" x2="${W - R}" y2="${Y(v).toFixed(1)}" class="cg"/><text x="${L - 4}" y="${(Y(v) + 3.5).toFixed(1)}" class="cx" text-anchor="end">${v}</text>`);
  const span = t1 - t0, stepH = span > 36 * 3600e3 ? 12 : span > 12 * 3600e3 ? 6 : 2;
  const first = new Date(t0); first.setMinutes(0, 0, 0);
  for (let t = first.getTime() + 3600e3; t < t1; t += 3600e3) {
    const d = new Date(t); if (d.getHours() % stepH) continue;
    g.push(`<line x1="${X(t).toFixed(1)}" y1="${Tp}" x2="${X(t).toFixed(1)}" y2="${H - B}" class="cg"/><text x="${X(t).toFixed(1)}" y="${H - B + 13}" class="cx" text-anchor="middle">${String(d.getHours()).padStart(2, "0")}:00</text>`);
  }
  for (const [k, col, dash, name] of HPC) {
    const pts = (ser[k] || []).filter((p) => isNum(num(p[0])));
    if (!pts.length) continue;
    let d = "", last = null;
    for (const [tRaw, vRaw] of pts) {
      const t = Math.max(num(tRaw), t0), v = num(vRaw);
      if (!isNum(v)) { last = null; continue; }
      const x = X(t).toFixed(1), y = Y(v).toFixed(1);
      // targets are steps (they hold until changed); the water is a line
      d += last == null ? `M${x},${y}` : k === "water" ? `L${x},${y}` : `H${x}V${y}`;
      last = v;
    }
    if (last != null) d += k === "water" ? "" : `H${(W - R).toFixed(1)}`;
    if (d) g.push(`<path d="${d}" fill="none" stroke="${col}" stroke-width="${k === "target" ? 2.4 : 1.7}" ${dash ? `stroke-dasharray="${dash}"` : ""}><title>${esc(name[lang])}</title></path>`);
  }
  const shown = HPC.filter(([k]) => (ser[k] || []).length);
  const leg = shown.map(([k, col, dash, name]) => `<span class="hpl"><svg width="18" height="8"><line x1="0" y1="4" x2="18" y2="4" stroke="${col}" stroke-width="2.4" ${dash ? `stroke-dasharray="${dash}"` : ""}/></svg>${esc(name[lang])}</span>`).join("");
  return `<svg class="hccurve" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(lang === "hu" ? "Hőszivattyú célja" : "Heat pump target")}">${g.join("")}</svg><div class="hpleg">${leg}</div>`;
}

// ---------------------------------------------------------------- the hydraulic diagram
const ROOM_UNITS = ["air_conditioner", "electric_heater", "storage_heater"];

// 0.63.0: the buffer system drawn like a plant room overview – flow (red) and return (blue) pipes with arrows, the
// circulation pump and the three-way mixing valve of each circuit, the tank's layers with its thermometers named on
// the side, the heat pump's coil, the wood boiler, an optional hot water tank with its pump, the rooms with icons
// (a room on two circuits once, between them), a legend and how it is controlled.
const ICO = {
  bed: "M3 18V7 M3 14h18v4 M21 14v-2a3 3 0 0 0-3-3h-7v5 M5 11.5a1.5 1.5 0 1 0 3 0a1.5 1.5 0 1 0-3 0",
  washer: "M5 3h14v18H5z M5 7h14 M8 14a4 4 0 1 0 8 0a4 4 0 1 0-8 0 M8 5h1",
  bath: "M3 12h18v2a5 5 0 0 1-5 5H8a5 5 0 0 1-5-5z M6 12V6a2 2 0 0 1 4 0 M7 19l-1 2 M17 19l1 2",
  sofa: "M4 11V8a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v3 M2 12a2 2 0 0 1 4 0v3h12v-3a2 2 0 0 1 4 0v5H2z M4 17v2 M20 17v2",
  pot: "M4 10h16v6a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z M2 10h20 M9 6v2 M12 5v3 M15 6v2",
  desk: "M3 9h18 M5 9v11 M19 9v11 M14 9v6h5 M8 5h4v4H8z",
  home: "M3 11l9-7 9 7 M5 10v10h14V10 M10 20v-5h4v5",
  radiator: "M4 6v12 M8 6v12 M12 6v12 M16 6v12 M20 6v12 M2 8h20 M2 16h20",
  floor: "M3 6h15a3 3 0 0 1 0 6H6a3 3 0 0 0 0 6h15",
  tap: "M4 8h10a4 4 0 0 1 4 4v1 M8 5v3 M6 5h4 M18 16v.5 M17 19v.5 M19 21v.5",
};
const ROOM_ICONS = [[/fürd|bath|wc|zuhany|shower/i, "bath"], [/mos[óo]|laundry|wash/i, "washer"], [/nappali|living|lounge/i, "sofa"],
  [/konyha|kitchen/i, "pot"], [/h[áa]l[óo]|bed|gyerek|child|kid|vend[ée]g|guest/i, "bed"], [/dolgoz|iroda|office|study/i, "desk"]];
const roomIcon = (name) => (ROOM_ICONS.find(([re]) => re.test(name || "")) || [null, "home"])[1];
// cold blue → lavender → warm red, as on a plant room drawing (28 °C and below blue, 55 °C and above red)
const tempCol = (t) => { if (!isNum(t)) return "#9e9e9e"; const f = clamp((t - 28) / 27, 0, 1), a = [100, 170, 240], b = [236, 96, 96];
  return `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * f)).join(",")})`; };
const isOn = (st) => { if (!st || st.state == null) return null; const v = String(st.state).toLowerCase();
  if (["on", "true", "running", "heat", "heating", "open"].includes(v)) return true;
  if (["off", "false", "idle", "closed"].includes(v)) return false; const n = parseFloat(v); return isFinite(n) ? n > 5 : null; };

export function renderSchematic(all, opts = {}) {
  const m = collect(all);
  // 0.61.0: a house without a buffer tank (a boiler with its rooms, air conditioners, heaters) is drawn too
  if (!m.tanks.length && !m.circuits.length && !m.hps.length) return renderPlainSchematic(m, opts);
  const lang = opts.lang === "en" ? "en" : "hu", T = OV_TXT[lang];
  const g = [], defs = [];
  const hp = m.hps[0] || null, tank = m.tanks[0] || null;
  const hc = hp?.conf || {}, tc = tank?.conf || {};
  const wood = !!(hc.wood_entity || hc.wood_temp_entity);
  const woodOn = hp && (hp.decision?.wood === "certain" || hp.decision?.wood === "likely" || hp.inputs?.wood_signal === true);
  const hpOn = hp && hp.decision?.details?.hp_running === true;
  const uid = String(tank?.entry_id || hp?.entry_id || "x").replace(/[^a-z0-9]/gi, "").slice(-8);
  const key = (i) => (i ? `data-key="member:${esc(i.entry_id)}"` : "");
  const pipe = (d, hot, on) => `<path d="${d}" class="sp ${hot ? "sf" : "sr"} ${on ? "son" : ""}" marker-end="url(#${hot ? "af" : "ar"}${uid})"/>`;
  const line = (d, hot, on) => `<path d="${d}" class="sp ${hot ? "sf" : "sr"} ${on ? "son" : ""}"/>`;
  const box = (x, y, w, h, t) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" class="sbox"/><text x="${x + 14}" y="${y + 24}" class="shead">${esc(t)}</text>`;
  const icon = (name, x, y, s = 1) => `<path transform="translate(${x},${y}) scale(${s})" d="${ICO[name] || ICO.home}" class="sico"/>`;
  const pump = (x, y, on) => `<g class="spm ${on === true ? "on" : on === false ? "off" : ""}"><circle cx="${x}" cy="${y}" r="11"/><path d="M${x - 4},${y - 6} L${x + 6},${y} L${x - 4},${y + 6}Z"/></g>`;
  const valve = (x, y, cls = "") => `<g class="smix ${cls}"><path d="M${x - 12},${y - 8} L${x},${y} L${x - 12},${y + 8}Z M${x + 12},${y - 8} L${x},${y} L${x + 12},${y + 8}Z"/><path d="M${x},${y} V${y - 12} M${x - 5},${y - 17} h10 v5 h-10z" class="sstem"/><path d="M${x - 6},${y + 14} L${x},${y} L${x + 6},${y + 14}Z"/></g>`;
  const sensor = (x, y) => `<circle cx="${x}" cy="${y}" r="5.5" class="ssen"/>`;

  // the rows on the right: per circuit its own rooms; rooms on two circuits once, under the first of them
  const circs = m.circuits;
  const zoneCircs = (z) => circs.filter((c) => m.circuitZones(c).some((x) => x.info?.entry_id === z.entry_id));
  const shared = m.zones.filter((z) => zoneCircs(z).length > 1);
  const direct = m.zones.filter((z) => !zoneCircs(z).length);
  const own = (c) => m.circuitZones(c).map((x) => x.info).filter((z) => z && !shared.includes(z));
  const RH = 58, CH = 74;
  let y = 84;
  const rows = [];
  circs.forEach((c, k) => {
    const rs = own(c), bandH = Math.max(CH + 16, rs.length * RH + 6);
    rows.push({ c, y, h: bandH, rooms: rs });
    y += bandH + 10;
    if (k === 0 && shared.length && circs.length > 1) {
      rows.push({ shared: true, y, h: shared.length * (RH + 6) + 26, rooms: shared });
      y += shared.length * (RH + 6) + 36;
    }
  });
  if (direct.length && (tank || !circs.length)) { rows.push({ c: null, y, h: Math.max(CH, direct.length * RH), rooms: direct }); y += Math.max(CH, direct.length * RH) + 10; }
  // 0.63.0: hot water from the tank (the tester's drawing): its own branch with the hot water pump, under the circuits
  const dhw = !!(tank && (tc.dhw_pump_entity || tc.dhw_temp_entity || tc.dhw_heater_entity));
  if (dhw) { rows.push({ dhw: true, y, h: CH + 16, rooms: [] }); y += CH + 26; }
  const H = Math.max(y + 20, 430);
  // columns
  const OX = 10, OW = 200, PX = 230, TX = 450, TW = 130, XT = 720, XR = 736, XP = 770, XV = 818, CX = 850, CW = 250, PE = CX + CW + 30, RX = PE + 60, RW = 250;
  const W = RX + RW + 10;
  const ty = 80, th = H - 140, tb = ty + th;
  let sy0 = () => ty + 40, yOut = ty + 70, yIn = tb - 40, yMid = ty + th / 2;
  g.push(box(OX, 40, OW, H - 50, T.outside), box(PX, 40, PE - PX, H - 50, T.plant));
  if (isNum(m.outdoor)) g.push(`<text x="${OX + 14}" y="${96}" class="sval">${esc(`${T.outdoor} ${deg(m.outdoor, lang)}`)}</text>`);
  // the tank: layers as a gradient, thermometers on the side
  if (tank) {
    const ls = tank.stock?.layers || [];
    sy0 = (j) => ty + 40 + (ls.length > 1 ? ((th - 90) * j) / (ls.length - 1) : th / 2);
    if (ls.length > 1) { yOut = (sy0(0) + sy0(1)) / 2; yIn = (sy0(ls.length - 2) + sy0(ls.length - 1)) / 2; }
    if (ls.length > 2) yMid = (sy0(1) + sy0(2)) / 2;
    const stops = ls.map((l, j) => `<stop offset="${ls.length > 1 ? (0.1 + (0.8 * j) / (ls.length - 1)).toFixed(2) : 0.5}" stop-color="${tempCol(num(l.temp))}"/>`).join("");
    defs.push(`<linearGradient id="tg${uid}" x1="0" y1="0" x2="0" y2="1">${stops || `<stop offset="0" stop-color="#9e9e9e"/>`}</linearGradient>`);
    const vol = num(tank.stock?.volume_l) || num(tc.buffer_volume_l);
    g.push(`<g class="hs" ${key(tank)}><rect x="${TX}" y="${ty}" width="${TW}" height="${th}" rx="34" style="fill:url(#tg${uid})" class="stank"/>
      <text x="${TX + TW / 2}" y="${ty + 34}" class="stn" text-anchor="middle">${esc(short(tank.title))}</text>${vol ? `<text x="${TX + TW / 2}" y="${ty + 52}" class="stn" text-anchor="middle">${esc(`${fx(vol, lang, 0)} L`)}</text>` : ""}`);
    ls.forEach((l, j) => {
      const sy = sy0(j);
      const nm = `${T.layer} ${j + 1}${j === 0 ? ` (${T.top})` : j === ls.length - 1 && ls.length > 1 ? ` (${T.bottom})` : ""}`;
      g.push(`${sensor(TX + TW, sy)}<path d="M${TX + TW + 6},${sy} H${TX + TW + 16}" class="sld"/><rect x="${TX + TW + 16}" y="${sy - 17}" width="104" height="34" rx="6" class="slbl"/><text x="${TX + TW + 24}" y="${sy - 3}" class="ssm">${esc(nm)}</text><text x="${TX + TW + 24}" y="${sy + 12}" class="sval">${esc(deg(num(l.temp), lang))}</text>`);
    });
    const ch = num(tank.stock?.charge), kwh = num(tank.stock?.stored_kwh);
    g.push(`<text x="${TX + TW / 2}" y="${tb + 20}" class="ssm" text-anchor="middle">${esc([isNum(ch) ? `${fx(ch, lang, 0)} %` : null, isNum(kwh) ? `${fx(kwh, lang)} kWh` : null].filter(Boolean).join(" · "))}</text></g>`);
  }
  // the heat pump outdoors, on the tank's lower coil
  if (hp) {
    const cy = tb - 62, hy = cy - 50;
    const pw = num(ent(hp, "hp_running_entity")?.state);
    g.push(`<g class="hs" ${key(hp)}><rect x="${OX + 18}" y="${hy}" width="${OW - 36}" height="100" rx="8" class="sdev ${hpOn ? "on" : ""}"/>
      <circle cx="${OX + 62}" cy="${hy + 50}" r="30" class="sfan"/><circle cx="${OX + 62}" cy="${hy + 50}" r="6" class="sfanh"/>
      <path d="M${OX + 106},${hy + 22} h52 M${OX + 106},${hy + 34} h52 M${OX + 106},${hy + 46} h52 M${OX + 106},${hy + 58} h52 M${OX + 106},${hy + 70} h52" class="sgr"/>
      <text x="${OX + OW / 2}" y="${hy - 26}" class="sname" text-anchor="middle">${esc(T.hpLong)}</text>
      <text x="${OX + OW / 2}" y="${hy - 10}" class="ssm" text-anchor="middle">${esc(`${hpOn ? T.runs : hp.decision?.details?.hp_running === false ? T.stands : T.unknown}${isNum(pw) ? ` · ${fx(pw, lang, 0)} ${ent(hp, "hp_running_entity")?.unit || ""}` : ""}`)}</text></g>`);
    if (tank) {
      g.push(pipe(`M${OX + OW - 18},${cy - 8} H${TX + 18}`, true, hpOn), pipe(`M${TX + 18},${cy + 20} H${OX + OW - 18}`, false, hpOn));
      g.push(`<path d="${[0, 1, 2].map((r) => `M${TX + 16},${cy - 8 + r * 14} h${TW - 40} a6,6 0 0 1 0,12 h-${TW - 40}`).join(" ")}" class="scoil"/><text x="${TX - 12}" y="${cy - 18}" class="ssm" text-anchor="end">${esc(T.coilCharge)}</text>`);
    }
  }
  // the wood boiler straight on the tank
  if (wood && tank) {
    const bx = PX + 36, by = ty + 20, bw = 120, bh = 150;
    const kt = num(ent(hp, "wood_temp_entity")?.state);
    g.push(`<g class="hs" ${key(hp)}><text x="${bx + bw / 2}" y="${by - 8}" class="sname" text-anchor="middle">${esc(T.woodBoiler)}</text>
      <rect x="${bx}" y="${by}" width="${bw}" height="${bh}" rx="6" class="sdev wood ${woodOn ? "on" : ""}"/><rect x="${bx + 22}" y="${by + 22}" width="${bw - 44}" height="58" rx="4" class="sdoor"/>
      ${woodOn ? `<path transform="translate(${bx + bw / 2},${by + 58}) scale(1.6)" d="M0,-12 C6,-5 10,-1 8,5 C6,11 -6,11 -8,5 C-10,-1 -4,-2 -2,-8 C0,-4 2,-3 0,-12Z" class="sflame"/>` : ""}
      <rect x="${bx + 22}" y="${by + 96}" width="${bw - 44}" height="26" rx="4" class="sdoor"/>
      <text x="${bx + bw / 2}" y="${by + bh + 16}" class="ssm" text-anchor="middle">${esc(`${woodOn ? T.active_ : T.inactive}${isNum(kt) ? ` · ${deg(kt, lang)}` : ""}`)}</text></g>`);
    g.push(pipe(`M${bx + bw},${by + 22} H${TX}`, true, woodOn), pipe(`M${TX},${by + bh - 24} H${bx + bw}`, false, woodOn));
  }
  // the mixing circuits: pump → mixing valve → circuit; the return through the valve's third port back to the bottom
  if (tank && (circs.length || dhw)) {
    const ys = rows.filter((r) => r.c).map((r) => r.y + r.h / 2);
    const any = circs.some((c) => c.decision?.demand);
    const dr = rows.find((r) => r.dhw);
    if (dr) ys.push(dr.y + dr.h / 2);
    const cys = rows.filter((r) => r.c).map((r) => r.y + r.h / 2);
    if (cys.length) g.push(line(`M${TX + TW},${yOut} H${XT} M${XT},${Math.min(...cys, yOut)} V${Math.max(...cys, yOut)}`, true, any));
    g.push(line(`M${XR},${Math.min(Math.min(...ys) + 22, yIn)} V${Math.max(Math.max(...ys) + 22, yIn)}`, false, any), pipe(`M${XR},${yIn} H${TX + TW}`, false, any));
  }
  rows.forEach((r) => {
    if (r.dhw) {
      const cy = r.y + r.h / 2, dt = num(ent(tank, "dhw_temp_entity")?.state), don = isOn(ent(tank, "dhw_pump_entity"));
      const heat = isOn(ent(tank, "dhw_heater_entity")), XD = XT - 14;
      g.push(line(`M${TX + TW},${yMid} H${XD} V${cy} H${XP - 11}`, true, don), pipe(`M${XP + 11},${cy} H${CX}`, true, don),
        line(`M${CX},${cy + 22} H${XR}`, false, don));
      g.push(`<g class="hs" ${key(tank)}>${pump(XP, cy, don)}<text x="${XP + 6}" y="${cy - 17}" class="ssm" text-anchor="middle">${esc(T.dhwPump)}</text>
        <rect x="${CX}" y="${cy - CH / 2}" width="${CW}" height="${CH}" rx="10" class="scirc ${don ? "on" : ""}"/>${icon("tap", CX + 14, cy - 20, 1.4)}
        <text x="${CX + 58}" y="${cy - 14}" class="sname">${esc(T.dhwTank)}</text>
        <text x="${CX + 58}" y="${cy + 3}" class="ssh">${esc(T.dhwFrom)}</text>
        <text x="${CX + 58}" y="${cy + 22}" class="sval">${esc(`${deg(dt, lang)}${ent(tank, "dhw_heater_entity") ? ` · ${T.dhwHeater}: ${heat ? T.on : heat === false ? T.offv : T.unknown}` : ""}`)}</text>
        ${ent(tank, "dhw_heater_entity") ? `<path d="M${CX + CW - 64},${cy - 18} l7,-7 l7,7 l7,-7 l7,7 l7,-7 l7,7" class="sheat ${heat ? "on" : ""}"/>` : ""}</g>`);
      return;
    }
    if (r.shared) {
      r.rooms.forEach((z, j) => {
        const ry = r.y + 14 + j * (RH + 6), d2 = z.decision || {};
        g.push(`<g class="hs" ${key(z)}><rect x="${CX + 10}" y="${ry}" width="${CW - 20}" height="${RH}" rx="8" class="sroom ${d2.output ? "on" : ""}"/>${icon(roomIcon(short(z.title)), CX + 22, ry + 16, 1.15)}
          <text x="${CX + 60}" y="${ry + 18}" class="sname">${esc(short(z.title))}</text><text x="${CX + 60}" y="${ry + 34}" class="ssh">${esc(zoneCircs(z).map((c) => ((c.config?.circuit_kind || c.conf?.circuit_kind) === "floor" ? T.floorS : T.radS)).join(" + "))}</text>
          <text x="${CX + 60}" y="${ry + 50}" class="ssm">${esc(`${deg(num(d2.indoor), lang)} → ${deg(num(d2.target), lang)}`)}</text></g>`);
        // up to the circuit above, down to the one below
        const up = rows.find((x) => x.c && zoneCircs(z).includes(x.c) && x.y < r.y), dn = rows.find((x) => x.c && zoneCircs(z).includes(x.c) && x.y > r.y);
        const on = !!d2.output;
        if (up) { const cyU = up.y + up.h / 2 + CH / 2; g.push(pipe(`M${CX + 90},${cyU} V${ry}`, true, on), pipe(`M${CX + 160},${ry} V${cyU}`, false, on)); }
        if (dn) { const cyD = dn.y + dn.h / 2 - CH / 2; g.push(pipe(`M${CX + 90 + j * 4},${cyD} V${ry + RH}`, true, on), pipe(`M${CX + 160 + j * 4},${ry + RH} V${cyD}`, false, on)); }
      });
      return;
    }
    const c = r.c, cy = r.y + r.h / 2, d = c?.decision || {};
    const floor = c && (c.config?.circuit_kind || c.conf?.circuit_kind) === "floor";
    const pst = c ? isOn(ent(c, "circuit_pump_entity")) : null, pOn = pst ?? (c ? !!d.demand : false);
    const flow = c ? num(ent(c, "circuit_flow_entity")?.state) : null;
    if (c) {
      g.push(`<g class="hs" ${key(c)}>${tank ? pump(XP, cy, pst ?? (d.demand ? true : null)) + valve(XV, cy, floor ? "fl" : "") : ""}
        <rect x="${CX}" y="${cy - CH / 2}" width="${CW}" height="${CH}" rx="10" class="scirc ${pOn ? "on" : ""}"/>${icon(floor ? "floor" : "radiator", CX + 12, cy - 22, 1.5)}
        <text x="${CX + 58}" y="${cy - 14}" class="sname">${esc(short(c.title))}</text>
        <text x="${CX + 58}" y="${cy + 3}" class="ssh">${esc(T.mixerPump)}</text>
        <text x="${CX + 58}" y="${cy + 22}" class="sval">${esc(`${T.tgt} ${deg(num(d.target), lang)}${isNum(flow) ? ` · ${T.meas} ${deg(flow, lang)}` : ""}`)}</text>
        <title>${esc(`${T.pumpLbl}: ${pst === null ? `${T.pumpEnable} ${d.demand ? T.yes : T.no}` : pst ? T.runs : T.stands}`)}</title></g>`);
      if (tank) {
        g.push(line(`M${XT},${cy} H${XP - 11}`, true, pOn), line(`M${XP + 11},${cy} H${XV - 12}`, true, pOn), pipe(`M${XV + 12},${cy} H${CX}`, true, pOn));
        g.push(line(`M${CX},${cy + 22} H${XV + 14} `, false, pOn), pipe(`M${XV},${cy + 22} V${cy + 14}`, false, pOn), line(`M${XV - 1},${cy + 22} H${XR}`, false, pOn));
      }
    } else if (tank) {
      g.push(`<text x="${CX + CW / 2}" y="${cy}" class="ssm" text-anchor="middle">${esc(T.direct)}</text>`, pipe(`M${XT},${ty + 46} V${cy - 8} H${CX + CW + 20}`, true, false));
    }
    // its own rooms on the right
    if (r.rooms.length) {
      const top = cy - (r.rooms.length * RH - 6) / 2;
      const ys = r.rooms.map((_, j) => top + j * RH + (RH - 6) / 2);
      const on = r.rooms.some((z) => z.decision?.output);
      g.push(line(`M${CX + CW},${cy - 12} H${PE + 10} M${PE + 10},${Math.min(...ys, cy - 12) - 8} V${Math.max(...ys, cy - 4) - 8}`, true, on));
      g.push(line(`M${PE + 34},${Math.min(...ys, cy) + 8} V${Math.max(...ys, cy + 4) + 8} M${PE + 34},${cy + 12} H${CX + CW}`, false, on));
      r.rooms.forEach((z, j) => {
        const ry = top + j * RH, d2 = z.decision || {}, yy = ry + (RH - 6) / 2, zon = !!d2.output;
        g.push(pipe(`M${PE + 10},${yy - 8} H${RX}`, true, zon), pipe(`M${RX},${yy + 8} H${PE + 34}`, false, zon));
        g.push(`<g class="hs" ${key(z)}><rect x="${RX}" y="${ry}" width="${RW}" height="${RH - 6}" rx="8" class="sroom ${zon ? "on" : ""}"/>${icon(roomIcon(short(z.title)), RX + 12, ry + 13, 1.15)}
          <text x="${RX + 50}" y="${ry + 21}" class="sname">${esc(short(z.title))}</text><text x="${RX + 50}" y="${ry + 39}" class="ssm">${esc(`${deg(num(d2.indoor), lang)} → ${deg(num(d2.target), lang)}`)}</text></g>`);
      });
    }
  });
  // legend and how it is controlled
  const LY = H + 10;
  const modes = {}; m.list.forEach((i) => { const t = modeTxt(i, T); modes[t] = (modes[t] || 0) + 1; });
  const info = [`${T.control}: ${Object.entries(modes).map(([t, n]) => `${t} (${n})`).join(", ")}`,
    hp && tank ? T.coilNote : null, wood ? T.woodNote : null].filter(Boolean);
  g.push(`<rect x="${OX}" y="${LY}" width="${W * 0.56}" height="104" rx="10" class="sleg"/><text x="${OX + 16}" y="${LY + 24}" class="sname">${esc(T.legend)}</text>
    ${pipe(`M${OX + 18},${LY + 48} H${OX + 70}`, true, false)}<text x="${OX + 80}" y="${LY + 52}" class="ssm">${esc(T.legFlow)}</text>
    ${pipe(`M${OX + 18},${LY + 78} H${OX + 70}`, false, false)}<text x="${OX + 80}" y="${LY + 82}" class="ssm">${esc(T.legReturn)}</text>
    ${pump(W * 0.3, LY + 30, true)}<text x="${W * 0.3 + 20}" y="${LY + 34}" class="ssm">${esc(T.legPump)}</text>
    ${valve(W * 0.3, LY + 60)}<text x="${W * 0.3 + 20}" y="${LY + 64}" class="ssm">${esc(T.legValve)}</text>
    ${sensor(W * 0.3, LY + 88)}<text x="${W * 0.3 + 20}" y="${LY + 92}" class="ssm">${esc(T.legSensor)}</text>
    <rect x="${OX + W * 0.58}" y="${LY}" width="${W * 0.42 - 20}" height="104" rx="10" class="sinfo"/>
    ${info.map((t, j) => `<text x="${OX + W * 0.58 + 18}" y="${LY + 28 + j * 24}" class="ssm">• ${esc(t)}</text>`).join("")}`);
  defs.push(`<marker id="af${uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10z" fill="#e53935"/></marker><marker id="ar${uid}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10z" fill="#1e88e5"/></marker>`);
  return `<svg class="hcsch" viewBox="0 0 ${W} ${LY + 114}" role="img" aria-label="${esc(T.plant)}"><defs>${defs.join("")}</defs>${g.join("")}</svg>`;
}

function renderPlainSchematic(m, opts) {
  const lang = opts.lang === "en" ? "en" : "hu", T = OV_TXT[lang];
  const g = [];
  const key = (i) => (i ? `data-key="member:${esc(i.entry_id)}"` : "");
  const pipe = (d, hot, on) => `<path d="${d}" class="sp ${hot ? "sf" : "sr"} ${on ? "son" : ""}"/>`;
  const box = (x, y, w, h, t) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" class="sbox"/><text x="${x + 10}" y="${y + 18}" class="slab">${esc(t)}</text>`;
  const kindOf = (i) => i.heat_source || "onoff_boiler";
  const runs = (i) => !!(i.actual ?? i.decision?.output);
  const units = m.zones.filter((z) => ROOM_UNITS.includes(kindOf(z)));
  const sources = m.zones.filter((z) => !ROOM_UNITS.includes(kindOf(z)) && kindOf(z) !== "external_heat" && (z.role || "standalone") !== "zone");
  const zonesOnly = m.zones.filter((z) => !units.includes(z) && !sources.includes(z));
  const roomsOf = (i) => {
    const list = (i.room_list || []).length ? i.room_list : [{ name: short(i.title), leading: true }];
    return list.map((r) => {
      const lead = !!r.leading, heated = r.heated !== false;
      return { name: r.name, temp: lead ? num(i.decision?.indoor) ?? num(r.temperature) : num(r.temperature),
        target: heated ? (lead ? num(i.decision?.target) : num(r.target) ?? num(i.decision?.target)) : null,
        on: heated && runs(i), sub: heated ? "" : T.unheated, key: i };
    });
  };
  const cols = [
    ...sources.map((i) => ({ title: short(i.title), src: i, rooms: roomsOf(i) })),
    ...(units.length ? [{ title: T.unitsCol, rooms: units.map((u) => ({ ...roomsOf(u)[0], sub: T.kinds[kindOf(u)] || kindOf(u), tip: short(u.title), on: runs(u), key: u })) }] : []),
    ...(zonesOnly.length ? [{ title: T.direct, rooms: zonesOnly.map((z) => ({ ...roomsOf(z)[0], key: z })) }] : []),
  ];
  const acs = units.filter((u) => kindOf(u) === "air_conditioner"), hpsOut = sources.filter((i) => kindOf(i) === "heat_pump");
  const outN = acs.length + hpsOut.length;
  const px = 200, pw = sources.length ? 230 : 0, rx0 = (pw ? px + pw : 190) + 24, colW = 200;
  const W = Math.max(760, rx0 + cols.length * colW + 10);
  const maxRooms = Math.max(1, ...cols.map((c) => c.rooms.length));
  const H = Math.max(260, 110 + Math.max(maxRooms * 46, sources.length * 96, outN * 70) + 30);
  // outdoors: the outdoor temperature, AC outdoor units, a heat pump's outdoor unit
  g.push(box(10, 40, 170, Math.max(150, 70 + outN * 70), T.outside));
  if (isNum(m.outdoor)) g.push(`<text x="20" y="${40 + 40}" class="sval">${esc(`${T.outdoor} ${deg(m.outdoor, lang)}`)}</text>`);
  [...hpsOut, ...acs].forEach((u, j) => {
    const y = 95 + j * 70, on = runs(u);
    g.push(`<g class="hs" ${key(u)}><rect x="30" y="${y}" width="130" height="56" rx="6" class="sdev ${on ? "on" : ""}"/><circle cx="52" cy="${y + 28}" r="15" class="sfan"/><text x="112" y="${y + 24}" class="ssm" text-anchor="middle">${esc(T.kinds[kindOf(u)] || "")}</text><text x="112" y="${y + 41}" class="ssm" text-anchor="middle">${esc(on ? T.runs : T.stands)}</text></g>`);
  });
  // plant room: each water heating source
  if (pw) {
    g.push(box(px, 40, pw, H - 60, T.plant));
    sources.forEach((i, j) => {
      const y = 70 + j * 96, on = runs(i), k = kindOf(i), d = i.decision || {};
      const burner = ["onoff_boiler", "modulating_boiler", "pellet_boiler"].includes(k);
      g.push(`<g class="hs" ${key(i)}><rect x="${px + 20}" y="${y}" width="${pw - 40}" height="80" rx="8" class="sdev ${on ? "on" : ""}"/>
        <text x="${px + 32}" y="${y + 20}" class="sname">${esc(T.kinds[k] || k)}</text><text x="${px + 32}" y="${y + 37}" class="ssm">${esc(short(i.title))}</text>
        <text x="${px + 32}" y="${y + 56}" class="sval">${esc(`${on ? (burner ? T.burning : T.runs) : (burner ? T.idle : T.stands)}${isNum(num(d.flow_setpoint)) ? ` · ${T.flowTarget} ${deg(num(d.flow_setpoint), lang)}` : ""}`)}</text>
        ${on && burner ? `<path transform="translate(${px + pw - 44},${y + 46}) scale(1.4)" d="M0,-12 C6,-5 10,-1 8,5 C6,11 -6,11 -8,5 C-10,-1 -4,-2 -2,-8 C0,-4 2,-3 0,-12Z" class="sflame"/>` : ""}</g>`);
    });
  }
  // the rooms per source
  cols.forEach((col, k) => {
    const cx = rx0 + k * colW, cw = colW - 14;
    g.push(`<text x="${cx + cw / 2}" y="62" class="slab" text-anchor="middle">${esc(col.title)}</text>`);
    if (col.src) {
      const j = sources.indexOf(col.src), on = runs(col.src), sy = 70 + j * 96;
      g.push(pipe(`M${px + pw - 20},${sy + 30} H${px + pw + 6 + k * 4} V${84 + k * 4} H${cx + 6} V110`, true, on));
    }
    col.rooms.forEach((r, j) => {
      const y = 110 + j * 46;
      g.push(`<g class="hs" ${key(r.key)}><title>${esc(r.tip || short(r.key?.title || ""))}</title><rect x="${cx}" y="${y}" width="${cw}" height="38" rx="8" class="sroom ${r.on ? "on" : ""}"/><text x="${cx + 10}" y="${y + 16}" class="sname">${esc(r.name)}${r.sub ? `<tspan class="ssh"> · ${esc(r.sub)}</tspan>` : ""}</text><text x="${cx + 10}" y="${y + 31}" class="ssm">${esc(`${deg(r.temp, lang)}${isNum(r.target) ? ` → ${deg(r.target, lang)}` : ""}`)}</text></g>`);
    });
  });
  return `<svg class="hcsch" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(T.plant)}">${g.join("")}</svg>`;
}

export const OV_CSS = `
.hpleg { display:flex; flex-wrap:wrap; gap:4px 12px; font-size:12px; margin:2px 0 4px; }
.hpl { display:inline-flex; align-items:center; gap:4px; }
.ovtabs { display:flex; gap:6px; margin:0 0 8px; flex-wrap:wrap; }
.ovtabs button { border:1px solid var(--divider-color); background:var(--card-background-color); color:var(--primary-text-color); border-radius:16px; padding:4px 12px; cursor:pointer; font:inherit; }
.ovtabs button.sel { background:var(--primary-color); color:var(--text-primary-color, #fff); border-color:var(--primary-color); }
.ovgrid { display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:10px; align-items:start; }
.ovc.wide { grid-column:1 / -1; }
.ovc[data-key], .ovt tr[data-key], .ovm[data-key] { cursor:pointer; }
.ovc .big { font-size:1.25em; color:var(--primary-color); }
.ovmodes { display:flex; flex-wrap:wrap; gap:4px; margin:6px 0; align-items:center; } .ovmodes .lbl { color:var(--secondary-text-color); margin-right:4px; }
.ovm { border-radius:8px; padding:1px 7px; font-size:12px; background:var(--secondary-background-color); }
.ovm.active, .ovm.permanent { background:#2e7d32; color:#fff; } .ovm.trial { background:#ef6c00; color:#fff; }
.ovw, .ovwhy { margin:4px 0 0; padding-left:18px; } .ovw li { color:#e65100; }
.ovt { width:100%; border-collapse:collapse; font-size:13px; } .ovt th { text-align:left; font-weight:500; color:var(--secondary-text-color); padding:3px 4px; border-bottom:2px solid var(--divider-color); }
.ovt td { padding:4px; border-bottom:1px solid var(--divider-color); } .ovt td small { display:block; color:var(--secondary-text-color); }
.ovt tr.diff td { background:color-mix(in srgb, #ff9800 10%, transparent); }
.hccurve { width:100%; height:auto; display:block; } .ovcurve { margin-top:6px; }
.hccurve .cg { stroke:var(--divider-color); stroke-width:.6; } .hccurve .cx { fill:var(--secondary-text-color); font-size:11px; }
.hccurve .cn { fill:none; stroke:var(--primary-color); stroke-width:2.2; } .hccurve .cc { fill:none; stroke:#ef6c00; stroke-width:2; stroke-dasharray:5 3; }
.hccurve .clim { stroke:#9e9e9e; stroke-width:1.2; stroke-dasharray:3 3; } .hccurve .cnow { stroke:var(--secondary-text-color); stroke-width:1; stroke-dasharray:2 3; }
.hccurve .craw { fill:var(--primary-color); } .hccurve .ctg { fill:#2e7d32; } .hccurve .cplc { fill:#8e24aa; }
.hcsch { width:100%; height:auto; display:block; }
.hcsch .sbox { fill:color-mix(in srgb, var(--primary-text-color) 3%, transparent); stroke:var(--divider-color); stroke-width:1.5; }
.hcsch .slab { fill:var(--secondary-text-color); font-size:13px; font-weight:600; letter-spacing:.04em; }
.hcsch .ssm { fill:var(--primary-text-color); font-size:12px; } .hcsch .sval { fill:var(--primary-color); font-size:12.5px; font-weight:600; }
.hcsch .sname { fill:var(--primary-text-color); font-size:13px; font-weight:600; } .hcsch .stt { fill:#fff; font-size:11px; font-weight:700; }
.hcsch .sdev { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:1.6; } .hcsch .sdev.on { stroke:#ef6c00; stroke-width:2.4; }
.hcsch .sdev.wood { fill:color-mix(in srgb, #c62828 14%, var(--card-background-color)); }
.hcsch .sfan { fill:none; stroke:var(--primary-text-color); stroke-width:2; stroke-dasharray:10 6; }
.hcsch .stank { fill:color-mix(in srgb, #90a4ae 30%, var(--card-background-color)); stroke:var(--primary-text-color); stroke-width:1.6; }
.hcsch .sp { fill:none; stroke-width:3.5; opacity:.8; } .hcsch .sp.sf { stroke:#e53935; } .hcsch .sp.sr { stroke:#1e88e5; }
.hcsch .sp.son { opacity:1; stroke-dasharray:8 6; animation:folyik 1s linear infinite; }
.hcsch .scoil { fill:none; stroke:#5c6bc0; stroke-width:3; } .hcsch .sflame { fill:#ff6d00; }
.hcsch .smix { fill:#78909c; stroke:var(--primary-text-color); stroke-width:1; } .hcsch .smix.fl { fill:#ab47bc; }
.hcsch .spump { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:1.6; } .hcsch .spump.on { stroke:#2e7d32; stroke-width:2.6; }
.hcsch .sroom { fill:var(--card-background-color); stroke:var(--divider-color); stroke-width:1.4; } .hcsch .sroom.on { stroke:#ef6c00; stroke-width:2.2; }
.hcsch .shead { fill:var(--primary-text-color); font-size:17px; font-weight:700; letter-spacing:.03em; }
.hcsch .stn { fill:#fff; font-size:15px; font-weight:700; paint-order:stroke; stroke:rgba(0,0,0,.25); stroke-width:2px; }
.hcsch .sico { fill:none; stroke:var(--primary-text-color); stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
.hcsch .spm circle { fill:var(--card-background-color); stroke:#9e9e9e; stroke-width:2.4; } .hcsch .spm path { fill:#9e9e9e; }
.hcsch .spm.on circle { stroke:#2e7d32; fill:color-mix(in srgb, #2e7d32 14%, var(--card-background-color)); } .hcsch .spm.on path { fill:#2e7d32; }
.hcsch .spm.off circle { stroke:var(--secondary-text-color); }
.hcsch .smix path { fill:#8e7cc3; stroke:var(--primary-text-color); stroke-width:1; } .hcsch .smix.fl path { fill:#ab47bc; }
.hcsch .smix .sstem { fill:none; } .hcsch .ssen { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:2; }
.hcsch .sld { stroke:var(--primary-text-color); stroke-width:1.2; } .hcsch .slbl { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:1.2; }
.hcsch .scirc { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:1.6; } .hcsch .scirc.on { stroke:#2e7d32; stroke-width:2.4; }
.hcsch .sfanh { fill:var(--primary-text-color); } .hcsch .sgr { stroke:var(--secondary-text-color); stroke-width:2; }
.hcsch .sdoor { fill:color-mix(in srgb, var(--primary-text-color) 18%, var(--card-background-color)); stroke:var(--primary-text-color); stroke-width:1.2; }
.hcsch .sleg { fill:var(--card-background-color); stroke:var(--divider-color); stroke-width:1.4; }
.hcsch .sinfo { fill:color-mix(in srgb, var(--primary-color) 10%, var(--card-background-color)); stroke:color-mix(in srgb, var(--primary-color) 45%, transparent); stroke-width:1.4; }
.hcsch .sheat { fill:none; stroke:#9e9e9e; stroke-width:2.4; } .hcsch .sheat.on { stroke:#ff6d00; }
.hcsch .hs { cursor:pointer; } .hcsch .ssh { font-weight:400; font-size:11px; fill:var(--secondary-text-color); }
@media (prefers-reduced-motion: reduce) { .hcsch .sp.son { animation:none; } }
`;

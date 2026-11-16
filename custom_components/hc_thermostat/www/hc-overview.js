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
    whyNoHeat: "Most nincs hőigény.", sharedRoom: "2 körön", woodLv: { certain: "biztos", likely: "valószínű", possible: "lehetséges", none: "nincs" },
    wst: { shadow: "nem ír (árnyék)", none: "nincs kimenet", in_sync: "egyezik", write: "ír", confirming: "visszaigazolásra vár", grace: "indulási türelem", keepalive: "frissítés", conflict: "ütközés", not_accepted: "nem fogadja el", unavailable: "nem elérhető", no_value: "nincs érték", error: "hiba" }, plant: "KAZÁNHÁZ", outside: "KÜLTÉR", house: "HELYISÉGEK",
    coil: "csőkígyó", mixer: "keverő + szivattyú", direct: "közvetlenül", normal: "normál görbe", corrected: "helyiséghiánnyal",
    limits: "korlátok", now: "most", given: "kiadott cél", outdoorAxis: "kinti hőmérséklet (°C)", flowAxis: "előremenő (°C)",
    deficit: "helyiséghiány", lowWaits: "alacsony töltöttség, de nincs helyiségi igény: nem indít",
    hpWhy: { fail_safe_on: "nincs kinti mérés – biztonsági ON", no_outdoor: "nincs kinti mérés – változatlan", no_buffer: "nincs pufferhőfok – változatlan",
      cold_on: "hideg idő miatt ON", frost: "puffer fagyvédelem", low_charge: "alacsony puffer-töltöttség", heat_needed: "a puffer teteje a körök igénye alatt",
      heating: "fűt, amíg a puffer teteje el nem éri az igény + hiszterézist", charging: "tölt a kikapcsolási töltöttségig",
      wood: "a fa tölti a puffert – a hőszivattyú vár", summer: "nyári üzem", idle_off: "régóta nincs igény – OFF", standby: "készenlét (ON, nem fűt)",
      off: "nincs igény", min_on: "minimális futásidő tartja", min_off: "minimális szünet tartja" },
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
    whyNoHeat: "No heat demand now.", sharedRoom: "on 2 circuits", woodLv: { certain: "certain", likely: "likely", possible: "possible", none: "none" },
    wst: { shadow: "not writing (shadow)", none: "no output", in_sync: "in sync", write: "writing", confirming: "awaiting confirmation", grace: "start grace", keepalive: "keep-alive", conflict: "conflict", not_accepted: "not accepted", unavailable: "unavailable", no_value: "no value", error: "error" }, plant: "PLANT ROOM", outside: "OUTDOORS", house: "ROOMS",
    coil: "coil", mixer: "mixer + pump", direct: "direct", normal: "normal curve", corrected: "with room deficit",
    limits: "limits", now: "now", given: "given-out target", outdoorAxis: "outdoor temperature (°C)", flowAxis: "flow (°C)",
    deficit: "room deficit", lowWaits: "low charge, but no room asks: no start",
    hpWhy: { fail_safe_on: "no outdoor reading – fail-safe ON", no_outdoor: "no outdoor reading – unchanged", no_buffer: "no tank reading – unchanged",
      cold_on: "ON for cold weather", frost: "tank frost protection", low_charge: "low tank charge", heat_needed: "the tank top is below the circuits' need",
      heating: "heats until the tank top reaches the need + hysteresis", charging: "charges up to the stop charge",
      wood: "wood charges the tank – the heat pump waits", summer: "summer mode", idle_off: "no demand for long – OFF", standby: "standby (ON, not heating)",
      off: "no demand", min_on: "held by the minimum run", min_off: "held by the minimum pause" },
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
    if (i.health?.state && !["ok", "good", "unknown"].includes(i.health.state)) out.push(`${n}: ${i.health.state}`);
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
    if (conf.wood_entity) {
      const we = ent(h, "wood_entity");
      const wood = d.wood === "certain" || d.wood === "likely" || h.inputs?.wood_signal === true;
      src.push(row(T.wood, `${wood ? `<span class="hot">${esc(T.active_)}</span>` : esc(T.inactive)}${we ? ` <small>(${esc(we.state)})</small>` : ""}`));
    }
    const run = det.hp_running === true ? T.runs : det.hp_running === false ? T.stands : T.unknown;
    const pe = ent(h, "hp_running_entity");
    src.push(row(T.hp, esc(run)));
    if (pe) src.push(row(`· ${T.power}`, `${esc(pe.state)} ${esc(pe.unit || "")}${isNum(det.hp_running_age_s) ? ` <small>(${esc(T.age)} ${det.hp_running_age_s < 120 ? `${Math.round(det.hp_running_age_s)} ${T.s}` : `${Math.round(det.hp_running_age_s / 60)} ${T.min}`}${det.hp_running_age_s > 900 ? `, ${esc(T.stale)}` : ""})</small>` : ""}`));
    src.push(row(`· ${T.request}`, `${d.enable ? T.on : T.offv} · ${T.demand}: ${d.heat_demand ? T.yes : T.no}`));
    src.push(row(`· ${T.flowTarget}`, deg(d.target, lang)));
    src.push(row(`· ${T.reason}`, esc(T.hpWhy[d.reason] || d.reason || "–")));
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
      + row(T.request, d.output ? T.on : T.offv), `member:${b.entry_id}`));
  }
  // circuits
  for (const c of m.circuits) {
    const d = c.decision || {}, det = d.details || {}, oe = ent(c, "circuit_output_entity"), w = c.outputs?.target || {};
    cards.push(card(short(c.title), row(T.flowTarget, `<b class="big">${deg(d.target, lang)}</b>`)
      + row(T.raw, deg(num(d.raw), lang)) + row(T.curve, deg(num(det.curve), lang))
      + row(T.plc, oe ? `${esc(oe.state)} ${esc(oe.unit || "")}` : "–")
      + row(T.written, esc(`${modeTxt(c, T)}${w.status && w.status !== "shadow" ? ` · ${T.wst[w.status] || w.status}` : ""}`))
      + row(T.lasting, d.demand ? T.yes : T.no)
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

// ---------------------------------------------------------------- the hydraulic diagram
export function renderSchematic(all, opts = {}) {
  const lang = opts.lang === "en" ? "en" : "hu", T = OV_TXT[lang];
  const m = collect(all);
  const g = [], W = 1000;
  const hp = m.hps[0] || null, tank = m.tanks[0] || null;
  const wood = hp && (hp.conf || {}).wood_entity;
  const woodOn = hp && (hp.decision?.wood === "certain" || hp.decision?.wood === "likely" || hp.inputs?.wood_signal === true);
  const hpOn = hp && hp.decision?.details?.hp_running === true;
  const box = (x, y, w, h, t, cls = "") => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" class="sbox ${cls}"/><text x="${x + 10}" y="${y + 18}" class="slab">${esc(t)}</text>`;
  const key = (i) => (i ? `data-key="member:${esc(i.entry_id)}"` : "");
  const pipe = (d, hot, on) => `<path d="${d}" class="sp ${hot ? "sf" : "sr"} ${on ? "son" : ""}"/>`;

  // circuits and their rooms decide the height
  const circs = m.circuits.length ? m.circuits : [];
  const others = m.zones.filter((z) => !circs.some((c) => m.circuitZones(c).some((x) => x.info?.entry_id === z.entry_id)));
  const cols = [...circs.map((c) => ({ c, rooms: m.circuitZones(c) })), ...(others.length && (tank || !circs.length) ? [{ c: null, rooms: others.map((z) => ({ eid: z.climate?.entity_id, info: z })) }] : [])];
  const maxRooms = Math.max(1, ...cols.map((x) => x.rooms.length));
  const H = Math.max(360, 120 + maxRooms * 46 + 40);
  // outdoors
  g.push(box(10, 40, 170, 150, T.outside));
  if (hp) {
    g.push(`<g class="hs" ${key(hp)}><rect x="30" y="80" width="130" height="80" rx="6" class="sdev ${hpOn ? "on" : ""}"/><circle cx="54" cy="120" r="18" class="sfan ${hpOn ? "spin" : ""}"/><text x="117" y="112" class="ssm" text-anchor="middle">${esc(T.hp)}</text><text x="117" y="130" class="ssm" text-anchor="middle">${esc(hpOn ? T.runs : hp.decision?.details?.hp_running === false ? T.stands : T.unknown)}</text></g>`);
  }
  // plant room
  const px = 200, pw = 480;
  g.push(box(px, 40, pw, H - 60, T.plant));
  const tx = px + 140, ty = 80, tw = 70, th = 180;
  if (tank) {
    const ls = (tank.stock?.layers || []);
    g.push(`<g class="hs" ${key(tank)}><rect x="${tx}" y="${ty}" width="${tw}" height="${th}" rx="26" class="stank"/>`);
    const lh = (th - 20) / Math.max(1, ls.length);
    ls.forEach((l, j) => {
      const t = num(l.temp), col = isNum(t) ? `hsl(${clamp(220 - (t - 25) * 5.5, 0, 220).toFixed(0)},70%,55%)` : "#9e9e9e";
      g.push(`<rect x="${tx + 8}" y="${ty + 10 + j * lh}" width="${tw - 16}" height="${lh - 2}" rx="4" fill="${col}" fill-opacity=".85"/><text x="${tx + tw / 2}" y="${ty + 10 + j * lh + lh / 2 + 4}" class="stt" text-anchor="middle">${esc(`${l.name ? l.name.slice(0, 1).toUpperCase() : "P"}${j + 1} ${fx(t, lang, 0)}°`)}</text>`);
    });
    const ch = num(tank.stock?.charge), kwh = num(tank.stock?.stored_kwh);
    g.push(`<text x="${tx + tw / 2}" y="${ty + th + 16}" class="ssm" text-anchor="middle">${esc(short(tank.title))}</text><text x="${tx + tw / 2}" y="${ty + th + 32}" class="ssm" text-anchor="middle">${esc([isNum(ch) ? `${fx(ch, lang, 0)} %` : null, isNum(kwh) ? `${fx(kwh, lang)} kWh` : null].filter(Boolean).join(" · "))}</text></g>`);
    // the heat pump on the tank's lower coil
    if (hp) {
      const cy = ty + th * 0.78;
      g.push(pipe(`M160,105 H${px + 20} V${cy - 6} H${tx + 8}`, true, hpOn), pipe(`M${tx + 8},${cy + 8} H${px + 12} V135 H160`, false, hpOn));
      g.push(`<path d="M${tx + 10},${cy - 4} q8,-6 16,0 t16,0 t16,0 M${tx + 10},${cy + 6} q8,-6 16,0 t16,0 t16,0" class="scoil"/><text x="${px + 30}" y="${cy + 26}" class="ssm">${esc(T.coil)}</text>`);
    }
    if (wood) {
      g.push(`<g class="hs" ${key(hp)}><rect x="${px + 30}" y="${ty}" width="90" height="110" rx="8" class="sdev wood ${woodOn ? "on" : ""}"/><text x="${px + 75}" y="${ty + 22}" class="ssm" text-anchor="middle">${esc(T.wood)}</text>${woodOn ? `<path transform="translate(${px + 75},${ty + 70}) scale(1.8)" d="M0,-12 C6,-5 10,-1 8,5 C6,11 -6,11 -8,5 C-10,-1 -4,-2 -2,-8 C0,-4 2,-3 0,-12Z" class="sflame"/>` : ""}<text x="${px + 75}" y="${ty + 102}" class="ssm" text-anchor="middle">${esc(woodOn ? T.active_ : T.inactive)}</text></g>`);
      g.push(pipe(`M${px + 120},${ty + 20} H${tx}`, true, woodOn), pipe(`M${tx},${ty + th - 30} H${px + 110} V${ty + 110}`, false, woodOn));
    }
  }
  // mixing circuits: valve + pump on the tank's top, out to the rooms
  const colW = (W - (px + pw) - 30) / Math.max(1, cols.length), rx0 = px + pw + 20;
  cols.forEach((col, k) => {
    const c = col.c, d = c?.decision || {}, on = !!d.demand;
    const my = 110 + k * 78, mx = px + pw - 70;
    const cx = rx0 + k * colW, cw = colW - 14;
    if (c) {
      const floor = (c.config?.circuit_kind || c.conf?.circuit_kind) === "floor";
      g.push(`<g class="hs" ${key(c)}><path d="M${mx - 9},${my - 6} L${mx},${my} L${mx - 9},${my + 6}Z M${mx + 9},${my - 6} L${mx},${my} L${mx + 9},${my + 6}Z M${mx - 6},${my + 11} L${mx},${my} L${mx + 6},${my + 11}Z" class="smix ${floor ? "fl" : ""}"/>
        <circle cx="${mx + 30}" cy="${my}" r="9" class="spump ${on ? "on" : ""}"/><text x="${mx + 10}" y="${my + 26}" class="ssm" text-anchor="end">${esc(short(c.title))}</text>
        <text x="${mx + 10}" y="${my + 41}" class="sval" text-anchor="end">${esc(`${T.flowTarget} ${deg(num(d.target), lang)}`)}</text></g>`);
      if (tank) g.push(pipe(`M${tx + tw},${ty + 12 + k * 6} H${tx + tw + 8 + k * 8} V${my} H${mx - 9}`, true, on));
      g.push(pipe(`M${mx + 39},${my} H${px + pw + 4 + k * 6} V${86 + k * 6} H${cx + 6 + k * 4} V110`, true, on));
    } else if (tank) {
      g.push(pipe(`M${tx + tw},${ty + 30} H${px + pw + 4} V${86 + k * 6} H${cx + 6} V110`, true, false));
    }
    // the rooms of this circuit
    g.push(`<text x="${cx + cw / 2}" y="${62}" class="slab" text-anchor="middle">${esc(c ? short(c.title) : T.direct)}</text>`);
    col.rooms.forEach((r, j) => {
      const z = r.info, d2 = z?.decision || {}, y = 110 + j * 46;
      const shared = z && (z.circuits || []).length > 1;
      g.push(`<g class="hs" ${key(z)}><rect x="${cx}" y="${y}" width="${cw}" height="38" rx="8" class="sroom ${d2.output ? "on" : ""}"/><text x="${cx + 10}" y="${y + 16}" class="sname">${esc(short(z?.title || r.eid))}${shared ? `<tspan class="ssh"> · ${esc(T.sharedRoom)}</tspan>` : ""}</text><text x="${cx + 10}" y="${y + 31}" class="ssm">${esc(`${deg(num(d2.indoor), lang)} → ${deg(num(d2.target), lang)}`)}</text></g>`);
    });
  });
  return `<svg class="hcsch" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(T.plant)}">${g.join("")}</svg>`;
}

export const OV_CSS = `
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
.hccurve .cg { stroke:var(--divider-color); stroke-width:.6; } .hccurve .cx { fill:var(--secondary-text-color); font-size:9.5px; }
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
.hcsch .sp { fill:none; stroke-width:3.5; opacity:.55; } .hcsch .sp.sf { stroke:#e53935; } .hcsch .sp.sr { stroke:#1e88e5; }
.hcsch .sp.son { opacity:1; stroke-dasharray:8 6; animation:folyik 1s linear infinite; }
.hcsch .scoil { fill:none; stroke:#e53935; stroke-width:2; } .hcsch .sflame { fill:#ff6d00; }
.hcsch .smix { fill:#78909c; stroke:var(--primary-text-color); stroke-width:1; } .hcsch .smix.fl { fill:#ab47bc; }
.hcsch .spump { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:1.6; } .hcsch .spump.on { stroke:#2e7d32; stroke-width:2.6; }
.hcsch .sroom { fill:var(--card-background-color); stroke:var(--divider-color); stroke-width:1.4; } .hcsch .sroom.on { stroke:#ef6c00; stroke-width:2.2; }
.hcsch .hs { cursor:pointer; } .hcsch .ssh { font-weight:400; font-size:11px; fill:var(--secondary-text-color); }
@media (prefers-reduced-motion: reduce) { .hcsch .sp.son { animation:none; } }
`;

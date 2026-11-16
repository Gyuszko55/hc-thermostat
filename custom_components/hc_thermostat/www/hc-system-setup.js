// hc-system-setup.js — 0.61.0: the "Buffer system" path of the HC setup panel. The real system is described once
// (tank, heat pump on its coil, wood, the radiator / floor mixing circuits, the rooms and the circuits each room is
// on); the backend (hc_thermostat/wizard/system) then creates every HC instance it needs, linked, in shadow mode.
// Mounted by hc-wizard-panel.js into a div of its own shadow root (it uses the panel's styles).

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const SYS_TXT = {
  hu: {
    title: "Pufferes rendszer", hint: "Puffertartály, keverőkörök, hőszivattyú a csőkígyón, fatüzelés – a rendszert egyszer kell leírni, a szükséges HC-példányokat (helyiségzónák, puffer, keverőkörök, hőszivattyú-koordináció) a HC hozza létre és köti össze. Mind árnyék módban indul: számol, nem kapcsol és nem ír.",
    steps: ["Felépítés", "Eszközök", "Helyiségek", "Összegzés"], back: "Vissza", next: "Tovább", create: "Létrehozás (árnyék módban)", exit: "Mégse",
    home: "Az otthon neve (a ház címe a HC infóban)", prefix: "A példányok nevének eleje", hp: "Hőszivattyú fűti a puffert (csőkígyón át)",
    wood: "Fatüzelésű kazán", woodNone: "nincs", woodSignal: "van közvetlen jele (füstgáz / üzem érintkező)", woodTemp: "a kazán hőmérője szerint (két küszöb)",
    rad: "Radiátoros keverőkör", floor: "Padlófűtési keverőkör", plc: "A keverőket, szivattyúkat a meglévő vezérlés (PLC) hajtja – a HC csak az előremenő célt számolja (és később kiírhatja).",
    rooms: "Helyiségek", addRoom: "+ Helyiség", remove: "Törlés", onRad: "radiátoros körön", onFloor: "padlófűtési körön", existing: "vagy meglévő HC-zóna",
    newRoom: "új helyiség", roomsHint: "Minden helyiség egy zóna a saját hőmérőjével és zónaszelepével (TPI). A radiátorral és padlófűtéssel is fűtött helyiség (pl. fürdő) egyetlen zóna – pipáld mindkét kört, egy termosztát marad.",
    summary: "Ezek jönnek létre", zone: "helyiségzóna", buffer: "puffer", circuit: "keverőkör", hp_coord: "hőszivattyú-koordináció", rooms_of: "helyiségei",
    creating: "Létrehozás…", done: "Kész – létrehozva, árnyék módban:", failed: "Megállt:", openInfo: "Megnyitás a HC infóban", again: "Új beállítás",
    need: { outdoor: "Kell a kinti hőmérő.", top: "Kell a puffer felső hőmérője.", rooms: "Legalább egy helyiség kell.", room: "Minden új helyiséghez név, hőmérő és zónaszelep-relé kell.", circ: "Legalább egy keverőkör kell, és minden helyiség legyen legalább egy körön.", wood: "A kikapcsolási küszöb legyen a bekapcsolási alatt.", woodEnt: "Add meg a fatüzelés jelét vagy a kazán hőmérőjét." },
    f: { outdoor: "Kinti hőmérő", top: "Puffer felső hőmérője (Puffer 1)", upper: "Felső-középső (Puffer 2)", lower: "Alsó-középső (Puffer 3)", bottom: "Alsó (Puffer 4)",
      charge: "Meglévő töltöttség-% (változatlanul átveszi)", volume_l: "Térfogat (l)", base_temp: "Alap: ennél hidegebb víz már nem fűt (°C)",
      hp_running: "A hőszivattyú fut-e (teljesítmény W / jel)", hp_switch: "A hőszivattyú ON/OFF-ja (később írható)", hp_target: "A hőszivattyú előremenő célja (később írható)",
      wood_signal: "Fatüzelés jele", wood_temp: "Fatüzelésű kazán hőmérője", wood_on_above: "Aktív, ha legalább (°C)", wood_off_below: "Inaktív, ha legfeljebb (°C)", wood_confirm_s: "Ennyi ideig tartson (s)",
      rad_output: "Radiátoros kör: a PLC célértéke (number, nem kötelező)", floor_output: "Padlófűtési kör: a PLC célértéke (number, nem kötelező)",
      name: "Név", indoor: "Hőmérő", actuator: "Zónaszelep / helyiségi relé" },
  },
  en: {
    title: "Buffer system", hint: "Buffer tank, mixing circuits, a heat pump on the coil, wood – describe the system once and HC creates and links the instances it needs (room zones, tank, mixing circuits, heat pump coordination). All start in shadow mode: they calculate, switch and write nothing.",
    steps: ["Layout", "Devices", "Rooms", "Summary"], back: "Back", next: "Next", create: "Create (shadow mode)", exit: "Cancel",
    home: "Home name (the house title in HC info)", prefix: "Instance names start with", hp: "A heat pump heats the tank (through its coil)",
    wood: "Wood boiler", woodNone: "none", woodSignal: "with a direct signal (flue / running contact)", woodTemp: "by the boiler's thermometer (two thresholds)",
    rad: "Radiator mixing circuit", floor: "Floor mixing circuit", plc: "The mixers and pumps stay with the existing control (PLC) – HC works out the flow target (and may write it later).",
    rooms: "Rooms", addRoom: "+ Room", remove: "Remove", onRad: "on the radiator circuit", onFloor: "on the floor circuit", existing: "or an existing HC zone",
    newRoom: "new room", roomsHint: "Each room is a zone with its own thermometer and zone valve (TPI). A room with a radiator and floor heating (a bathroom) is ONE zone – tick both circuits, it keeps one thermostat.",
    summary: "To be created", zone: "room zone", buffer: "tank", circuit: "mixing circuit", hp_coord: "heat pump coordination", rooms_of: "its rooms",
    creating: "Creating…", done: "Done – created, in shadow mode:", failed: "Stopped:", openInfo: "Open in HC info", again: "New setup",
    need: { outdoor: "An outdoor thermometer is needed.", top: "The tank's top thermometer is needed.", rooms: "At least one room is needed.", room: "Every new room needs a name, a thermometer and a zone valve relay.", circ: "At least one mixing circuit is needed, and every room must be on one.", wood: "The off threshold must be below the on threshold.", woodEnt: "Give the wood signal or the boiler's thermometer." },
    f: { outdoor: "Outdoor thermometer", top: "Tank top thermometer", upper: "Upper middle", lower: "Lower middle", bottom: "Bottom",
      charge: "Existing charge % (taken over unchanged)", volume_l: "Volume (l)", base_temp: "Base: colder water no longer heats (°C)",
      hp_running: "Whether the heat pump runs (power W / signal)", hp_switch: "Heat pump ON/OFF (may be written later)", hp_target: "Heat pump flow target (may be written later)",
      wood_signal: "Wood signal", wood_temp: "Wood boiler thermometer", wood_on_above: "Active at or above (°C)", wood_off_below: "Inactive at or below (°C)", wood_confirm_s: "Lasting (s)",
      rad_output: "Radiator circuit: the PLC's setpoint (number, optional)", floor_output: "Floor circuit: the PLC's setpoint (number, optional)",
      name: "Name", indoor: "Thermometer", actuator: "Zone valve / room relay" },
  },
};

const TEMP = { domain: "sensor", device_class: "temperature" };
const ent = (name, filter, required = false) => ({ name, required, selector: { entity: { filter: [].concat(filter) } } });
const numSel = (name, min, max, step, unit) => ({ name, selector: { number: { min, max, step, mode: "box", unit_of_measurement: unit } } });

export function emptySystem() {
  return { step: 0, home_name: "", prefix: "HC", hp: true, wood: "temp", radiator: true, floor: true,
    dev: { volume_l: 1000, base_temp: 30, wood_on_above: 65, wood_off_below: 60, wood_confirm_s: 300 },
    rooms: [{ name: "", rad: true, floor: false }], result: null, busy: false };
}

export function devSchema(s) {
  const sc = [ent("outdoor", [TEMP, { domain: "weather" }], true), ent("top", TEMP, true), ent("upper", TEMP), ent("lower", TEMP), ent("bottom", TEMP),
    ent("charge", { domain: "sensor" }), numSel("volume_l", 0, 20000, 10, "l"), numSel("base_temp", 10, 50, 1, "°C")];
  if (s.hp) sc.push(ent("hp_running", [{ domain: "sensor" }, { domain: "binary_sensor" }, { domain: "climate" }, { domain: "switch" }]),
    ent("hp_switch", [{ domain: "switch" }, { domain: "input_boolean" }, { domain: "climate" }]), ent("hp_target", [{ domain: "number" }, { domain: "input_number" }, { domain: "climate" }]));
  if (s.hp && s.wood === "signal") sc.push(ent("wood_signal", [{ domain: "binary_sensor" }, { domain: "switch" }, { domain: "input_boolean" }, { domain: "sensor" }], true));
  if (s.hp && s.wood === "temp") sc.push(ent("wood_temp", TEMP, true), numSel("wood_on_above", 30, 95, 1, "°C"), numSel("wood_off_below", 25, 90, 1, "°C"), numSel("wood_confirm_s", 0, 3600, 60, "s"));
  if (s.radiator) sc.push(ent("rad_output", [{ domain: "number" }, { domain: "input_number" }, { domain: "climate" }]));
  if (s.floor) sc.push(ent("floor_output", [{ domain: "number" }, { domain: "input_number" }, { domain: "climate" }]));
  return sc;
}

// what is missing (null: the step may go on)
export function missing(s, step, T) {
  const d = s.dev;
  if (step >= 1) {
    if (!s.radiator && !s.floor) return T.need.circ;
    if (!d.outdoor) return T.need.outdoor;
    if (!d.top) return T.need.top;
    if (s.hp && s.wood === "signal" && !d.wood_signal) return T.need.woodEnt;
    if (s.hp && s.wood === "temp") {
      if (!d.wood_temp) return T.need.woodEnt;
      if (Number(d.wood_off_below) >= Number(d.wood_on_above)) return T.need.wood;
    }
  }
  if (step >= 2) {
    if (!s.rooms.length) return T.need.rooms;
    for (const r of s.rooms) {
      if (!r.entry_id && (!String(r.name || "").trim() || !r.indoor || !r.actuator)) return T.need.room;
      if (!((r.rad && s.radiator) || (r.floor && s.floor))) return T.need.circ;
    }
  }
  return null;
}

// the websocket request
export function request(s) {
  const d = s.dev;
  const circuits = [s.radiator ? { kind: "radiator", output: d.rad_output || null } : null, s.floor ? { kind: "floor", output: d.floor_output || null } : null].filter(Boolean);
  return {
    type: "hc_thermostat/wizard/system", home_name: s.home_name || null, prefix: s.prefix, outdoor: d.outdoor,
    buffer: { top: d.top, upper: d.upper || null, lower: d.lower || null, bottom: d.bottom || null, charge: d.charge || null, volume_l: d.volume_l, base_temp: d.base_temp },
    heat_pump: s.hp ? { enabled: true, running: d.hp_running || null, switch: d.hp_switch || null, target: d.hp_target || null } : { enabled: false },
    wood: s.hp && s.wood === "signal" ? { signal: d.wood_signal } : s.hp && s.wood === "temp" ? { temp: d.wood_temp, wood_on_above: d.wood_on_above, wood_off_below: d.wood_off_below, wood_confirm_s: d.wood_confirm_s } : null,
    circuits,
    rooms: s.rooms.map((r) => ({ entry_id: r.entry_id || null, name: r.name, indoor: r.indoor, actuator: r.actuator,
      circuits: [r.rad && s.radiator ? "radiator" : null, r.floor && s.floor ? "floor" : null].filter(Boolean) })),
  };
}

export class SystemSetup {
  constructor(panel) { this.p = panel; this.s = emptySystem(); }
  get T() { return SYS_TXT[String(this.p._lang || "").startsWith("hu") ? "hu" : "en"]; }

  html() {
    const T = this.T, s = this.s;
    const bar = `<div class="steps">${T.steps.map((n, i) => `<span class="${i === s.step ? "on" : i < s.step ? "done" : ""}">${i + 1}. ${esc(n)}</span>`).join("")}</div><h1>${esc(T.title)} – ${esc(T.steps[s.step])}</h1>`;
    if (s.result) {
      const r = s.result;
      return `<div class="card"><h1>${esc(r.error ? T.failed + " " + r.error : T.done)}</h1><ul>${(r.created || []).map((c) => `<li>${esc(c.title)} <span class="muted">(${esc(T[c.role] || c.role)})</span></li>`).join("")}</ul>
        <div class="nav"><a class="btn ghost" href="/hc-info">${esc(T.openInfo)}</a><button class="btn" id="sys_again">${esc(T.again)}</button></div></div>`;
    }
    let body = "";
    if (s.step === 0) {
      body = `<p class="hint">${esc(T.hint)}</p><div class="card">
        <label class="chk">${esc(T.home)} <input id="sys_home" style="width:auto;flex:1" value="${esc(s.home_name)}"></label>
        <label class="chk">${esc(T.prefix)} <input id="sys_prefix" value="${esc(s.prefix)}"></label>
        <label class="chk"><input type="checkbox" id="sys_hp" ${s.hp ? "checked" : ""}> ${esc(T.hp)}</label>
        ${s.hp ? `<div class="val"><span>${esc(T.wood)}</span><select id="sys_wood">${[["none", T.woodNone], ["signal", T.woodSignal], ["temp", T.woodTemp]].map(([v, l]) => `<option value="${v}" ${s.wood === v ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>` : ""}
        <label class="chk"><input type="checkbox" id="sys_rad" ${s.radiator ? "checked" : ""}> ${esc(T.rad)}</label>
        <label class="chk"><input type="checkbox" id="sys_floor" ${s.floor ? "checked" : ""}> ${esc(T.floor)}</label>
        <p class="muted small">${esc(T.plc)}</p></div>`;
    } else if (s.step === 1) {
      body = `<div class="card" id="sys_devform"></div>`;
    } else if (s.step === 2) {
      const zones = (this.p._start?.entries || []).filter((e) => e.role === "zone" || e.heat_source === "external_heat");
      body = `<p class="hint">${esc(T.roomsHint)}</p>` + s.rooms.map((r, i) => `<div class="room" data-room="${i}">
        <div class="val"><b>${esc(r.name || T.newRoom)}</b><button class="btn ghost small" data-rm="${i}" style="margin-left:auto">${esc(T.remove)}</button></div>
        ${zones.length ? `<div class="val"><span>${esc(T.existing)}</span><select data-ex="${i}"><option value="">–</option>${zones.map((z) => `<option value="${esc(z.entry_id)}" ${r.entry_id === z.entry_id ? "selected" : ""}>${esc(z.title)}</option>`).join("")}</select></div>` : ""}
        ${r.entry_id ? "" : `<div class="sysroomform" data-form="${i}"></div>`}
        ${s.radiator ? `<label class="chk"><input type="checkbox" data-rad="${i}" ${r.rad ? "checked" : ""}> ${esc(T.onRad)}</label>` : ""}
        ${s.floor ? `<label class="chk"><input type="checkbox" data-floor="${i}" ${r.floor ? "checked" : ""}> ${esc(T.onFloor)}</label>` : ""}
      </div>`).join("") + `<button class="btn ghost" id="sys_add">${esc(T.addRoom)}</button>`;
    } else {
      const pre = (n) => `${s.prefix ? s.prefix + " " : ""}${n}`;
      const roomName = (r) => r.entry_id ? ((this.p._start?.entries || []).find((e) => e.entry_id === r.entry_id)?.title || r.entry_id) : pre(r.name);
      const radRooms = s.rooms.filter((r) => r.rad && s.radiator).map(roomName), flRooms = s.rooms.filter((r) => r.floor && s.floor).map(roomName);
      const hu = this.T === SYS_TXT.hu, N = hu ? { b: "Puffer", r: "Radiátoros kör", f: "Padlófűtési kör", h: "Hőszivattyú koordináció" } : { b: "Buffer tank", r: "Radiator circuit", f: "Floor circuit", h: "Heat pump coordination" };
      body = `<div class="card sum"><b>${esc(T.summary)}</b>
        ${s.rooms.filter((r) => !r.entry_id).map((r) => `<div><span>${esc(pre(r.name))}</span><span>${esc(T.zone)}${r.rad && r.floor && s.radiator && s.floor ? " · radiátor + padló" : ""}</span></div>`).join("")}
        <div><span>${esc(pre(N.b))}</span><span>${esc(T.buffer)} · ${esc(s.dev.volume_l)} l</span></div>
        ${s.radiator ? `<div><span>${esc(pre(N.r))}</span><span>${esc(T.circuit)} · ${esc(T.rooms_of)}: ${esc(radRooms.join(", "))}</span></div>` : ""}
        ${s.floor ? `<div><span>${esc(pre(N.f))}</span><span>${esc(T.circuit)} · ${esc(T.rooms_of)}: ${esc(flRooms.join(", "))}</span></div>` : ""}
        ${s.hp ? `<div><span>${esc(pre(N.h))}</span><span>${esc(T.hp_coord)}${s.wood !== "none" ? " · " + esc(s.wood === "temp" ? T.woodTemp : T.woodSignal) : ""}</span></div>` : ""}
        ${this.err ? `<p class="err">${esc(this.err)}</p>` : ""}</div>`;
    }
    const miss = missing(s, s.step, T);
    const last = s.step === 3;
    const nav = `<div class="nav"><button class="btn ghost" id="sys_back">${esc(s.step === 0 ? T.exit : T.back)}</button>
      ${last ? `<button class="btn" id="sys_create" ${s.busy || miss ? "disabled" : ""}>${esc(s.busy ? T.creating : T.create)}</button>` : `<button class="btn" id="sys_next" ${miss && s.step > 0 ? "disabled" : ""}>${esc(T.next)}</button>`}</div>
      <p class="need">${esc(s.step > 0 ? miss || "" : "")}</p>`;
    return bar + body + nav;
  }

  bind(root) {
    const s = this.s, T = this.T, hass = this.p._hass, re = () => this.p._render();
    const on = (id, ev, fn) => root.getElementById(id)?.addEventListener(ev, fn);
    on("sys_back", "click", () => { if (s.step === 0) { this.p._sysMode = false; re(); } else { s.step -= 1; re(); } });
    on("sys_next", "click", () => { s.step += 1; re(); });
    on("sys_again", "click", () => { this.s = emptySystem(); re(); });
    on("sys_home", "change", (e) => { s.home_name = e.target.value; });
    on("sys_prefix", "change", (e) => { s.prefix = e.target.value; });
    on("sys_hp", "change", (e) => { s.hp = e.target.checked; re(); });
    on("sys_wood", "change", (e) => { s.wood = e.target.value; re(); });
    on("sys_rad", "change", (e) => { s.radiator = e.target.checked; re(); });
    on("sys_floor", "change", (e) => { s.floor = e.target.checked; re(); });
    on("sys_add", "click", () => { s.rooms.push({ name: "", rad: s.radiator, floor: !s.radiator }); re(); });
    root.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => { s.rooms.splice(+b.dataset.rm, 1); re(); }));
    root.querySelectorAll("[data-rad]").forEach((b) => b.addEventListener("change", () => { s.rooms[+b.dataset.rad].rad = b.checked; re(); }));
    root.querySelectorAll("[data-floor]").forEach((b) => b.addEventListener("change", () => { s.rooms[+b.dataset.floor].floor = b.checked; re(); }));
    root.querySelectorAll("[data-ex]").forEach((b) => b.addEventListener("change", () => { s.rooms[+b.dataset.ex].entry_id = b.value || null; re(); }));
    const upd = () => { const btn = root.getElementById("sys_next"), need = root.querySelector(".need"), m = missing(s, s.step, T); if (btn) btn.disabled = !!m; if (need) need.textContent = m || ""; };
    const form = (host, schema, data, label, onChange) => {
      const f = document.createElement("ha-form");
      f.hass = hass; f.schema = schema; f.data = data;
      f.computeLabel = (sch) => label[sch.name] || sch.name;
      f.addEventListener("value-changed", (e) => { onChange(e.detail.value || {}); f.data = e.detail.value || {}; upd(); });
      host.appendChild(f);
    };
    const dv = root.getElementById("sys_devform");
    if (dv) form(dv, devSchema(s), s.dev, T.f, (v) => { s.dev = { ...s.dev, ...v }; });
    root.querySelectorAll("[data-form]").forEach((host) => {
      const i = +host.dataset.form, r = s.rooms[i];
      form(host, [{ name: "name", required: true, selector: { text: {} } }, ent("indoor", TEMP, true), ent("actuator", [{ domain: "switch" }, { domain: "input_boolean" }], true)],
        { name: r.name, indoor: r.indoor, actuator: r.actuator }, T.f, (v) => { Object.assign(r, v); });
    });
    on("sys_create", "click", async () => {
      s.busy = true; this.err = null; re();
      try {
        s.result = await hass.callWS(request(s));
      } catch (e) { this.err = String(e?.message || e?.code || e); }
      s.busy = false; re();
    });
  }
}

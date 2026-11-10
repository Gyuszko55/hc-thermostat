// HC Thermostat card: shows what the supervisor reads, decides and would do. Read only, it has no controls.
// type: custom:hc-thermostat-card
// entity: climate.xxx            # the HC Thermostat climate entity; the rest is found from its device
// reference: binary_sensor.xxx   # optional: the real burner, for the timeline
// indoor: sensor.xxx             # optional: indoor sensor for the timeline
// outdoor: sensor.xxx            # optional: outdoor sensor for the timeline
// zone_name: Terrace             # optional: name of the adjoining room
// other_name: AC                 # optional: name of the other heat source
const TX = {
  hu: {
    shadow: "ÁRNYÉK", shadowHint: "számol, nem kapcsol", active: "ÉLES", activeHint: "valódi kazánt kapcsol",
    inputs: "Bemenetek", balance: "A ház hőmérlege", output: "Kimenet", indoor: "Bent", outdoor: "Kint", target: "Cél",
    presence: "Jelenlét", home: "Otthon", away: "Távol", vacation: "Szabadság", loss: "Hőveszteség", days: "nap adatból", learning: "még tanul",
    cost: "Melyik hő olcsóbb most", costHint: "csak javaslat, nem kapcsol", perKwh: "Ft/kWh hő", otherSrc: "Másik hőforrás", boilerName: "Kazán", breakeven: "e kinti hőfok felett olcsóbb", always: "-7 °C-on is olcsóbb", never: "+7 °C-on is drágább", allowance: "kedvezményes keret", saving: "különbség most", perHour: "Ft/óra", zone: "Csatlakozó tér", joined: "összenyitva", apart: "külön", openCold: "nyitva, hideg", zoneNote: "külön fűti, a házhoz most nem számít", need: "hőigény", boiler: "kazán", other: "klíma / egyéb", chain: "Döntési lánc", chainHint: "felülről lefelé az első érvényes szabály dönt",
    demand: "hőigény", wants: "HC kérne", real: "Valódi kazán", on: "ég", off: "áll", wantOn: "fűtést", wantOff: "semmit", unknown: "nincs adat",
    agree: "egyezés a valódi fűtéssel (legfeljebb 24 h)", timeline: "Elmúlt 24 óra", log: "Döntésnapló", noLog: "Még nincs bejegyzés.", fault: "Fűtési hiba gyanú", limited: "korlát", min_on: "minimális futás tart", min_off: "minimális szünet tart",
    r: { frost: "Fagyvédelem", sensor_lost: "Érzékelő", disabled: "Kikapcsolva", window: "Ablak", season_off: "Nyári pihenő", restart_hold: "Újraindítás", restart_burn: "Újraind. égés", at_target: "Cél elérve", boost: "Felfűtés", afterheat: "Utómeleg.", regulating: "Szabályoz", external: "Külső termosztát" },
  },
  en: {
    shadow: "SHADOW", shadowHint: "calculates, switches nothing", active: "ACTIVE", activeHint: "switches the real boiler",
    inputs: "Inputs", balance: "Heat balance of the house", output: "Output", indoor: "Indoor", outdoor: "Outdoor", target: "Target",
    presence: "Presence", home: "Home", away: "Away", vacation: "Vacation", loss: "Heat loss", days: "days of data", learning: "still learning",
    cost: "Which heat is cheaper now", costHint: "advice only, switches nothing", perKwh: "per kWh of heat", otherSrc: "Other source", boilerName: "Boiler", breakeven: "cheaper above this outdoor temperature", always: "cheaper even at -7 °C", never: "dearer even at +7 °C", allowance: "discounted allowance", saving: "difference now", perHour: "per hour", zone: "Adjoining room", joined: "open to house", apart: "separate", openCold: "open, cold", zoneNote: "heats it separately, not counted for the house now", need: "heat need", boiler: "boiler", other: "AC / other", chain: "Decision chain", chainHint: "top to bottom, the first valid rule decides",
    demand: "demand", wants: "HC would ask for", real: "Real boiler", on: "burning", off: "idle", wantOn: "heat", wantOff: "nothing", unknown: "no data",
    agree: "agreement with real heating (up to 24 h)", timeline: "Last 24 hours", log: "Decision log", noLog: "No entries yet.", fault: "Heating fault suspected", limited: "limit", min_on: "minimum run time", min_off: "minimum pause",
    r: { frost: "Frost", sensor_lost: "Sensor", disabled: "Off", window: "Window", season_off: "Summer rest", restart_hold: "Restart", restart_burn: "Restart burn", at_target: "At target", boost: "Boost", afterheat: "After-heat", regulating: "Regulating", external: "External" },
  },
};
const CHAIN = ["frost", "sensor_lost", "disabled", "window", "season_off", "restart_hold", "at_target", "boost", "afterheat", "regulating"];
const num = (v, d = 1) => (v == null || isNaN(v) ? "–" : Number(v).toLocaleString("hu-HU", { minimumFractionDigits: d, maximumFractionDigits: d }));
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const RING = 2 * Math.PI * 44;
const DAY = 864e5;

class HcThermostatCard extends HTMLElement {
  static getStubConfig() { return { entity: "" }; }
  setConfig(config) {
    if (!config.entity) throw new Error("Add meg a HC Thermostat climate entitását (entity).");
    this._config = config;
  }
  getCardSize() { return 12; }
  getGridOptions() { return { columns: "full", rows: "auto" }; }

  connectedCallback() {
    this._timer = setInterval(() => this._loadHistory(), 300000);
    this._loadHistory();
  }
  disconnectedCallback() { clearInterval(this._timer); }

  set hass(hass) {
    this._hass = hass;
    if (!this._ids) this._findEntities();
    if (!this.shadowRoot) this._build();
    this._update();
    if (!this._hist && this.isConnected) this._loadHistory();
  }

  _t() { return String(this._hass?.language || "en").startsWith("hu") ? TX.hu : TX.en; }

  // Entity ids depend on the language, the translation keys of the device do not.
  _findEntities() {
    const h = this._hass, own = h.entities?.[this._config.entity];
    if (!own?.device_id) return;
    const ids = {};
    for (const [id, e] of Object.entries(h.entities)) {
      if (e.device_id === own.device_id && e.translation_key) ids[e.translation_key] = id;
    }
    this._ids = ids;
  }
  _st(key) { return this._hass.states[this._ids?.[key]]; }
  _num(key) { const v = parseFloat(this._st(key)?.state); return isNaN(v) ? null : v; }

  _build() {
    const t = this._t();
    this.attachShadow({ mode: "open" }).innerHTML = `
      <style>
        :host { display: block; --meleg: #ff8a3d; --hideg: #4fb3ff; --jo: #4caf7d; --baj: #ef5350; --halk: var(--secondary-text-color); --keret: var(--divider-color, rgba(127,127,127,.25)); }
        ha-card { padding: 14px; overflow: hidden; container-type: inline-size; }
        .fej { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .nev { font-size: 17px; font-weight: 600; }
        .jel { font-size: 11px; font-weight: 700; letter-spacing: .08em; padding: 3px 8px; border-radius: 10px; background: rgba(127,127,127,.2); }
        .jel.eles { background: var(--meleg); color: #fff; }
        .tipp { font-size: 12px; color: var(--halk); }
        .mond { margin: 8px 0 12px; font-size: 14.5px; line-height: 1.35; }
        .baj { display: none; margin-bottom: 10px; padding: 7px 10px; border-radius: 8px; background: color-mix(in srgb, var(--baj) 18%, transparent); color: var(--baj); font-weight: 600; font-size: 13px; }
        .baj.van { display: block; }
        .fo { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr) minmax(0, 1fr); gap: 0; align-items: stretch; }
        .oszlop { min-width: 0; }
        .cim { font-size: 11px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--halk); margin-bottom: 6px; }
        .sor { display: flex; justify-content: space-between; gap: 8px; padding: 5px 0; border-bottom: 1px solid var(--keret); font-size: 13.5px; }
        .sor:last-child { border-bottom: 0; }
        .sor span { color: var(--halk); }
        .sor b { font-weight: 600; white-space: nowrap; }
        .haz { position: relative; display: flex; align-items: center; justify-content: center; }
        .haz svg { width: 100%; max-width: 300px; height: auto; display: block; }
        svg text { font-family: inherit; fill: var(--primary-text-color); }
        .vonal { fill: none; stroke: var(--primary-text-color); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; opacity: .85; }
        .ki { fill: none; stroke: var(--hideg); stroke-width: 2.2; stroke-linecap: round; stroke-dasharray: 3 7; animation: folyik var(--seb, 2s) linear infinite; }
        .be { fill: none; stroke: var(--meleg); stroke-width: 3; stroke-linecap: round; stroke-dasharray: 4 7; animation: folyik 1.1s linear infinite; opacity: .25; }
        .be.megy { opacity: 1; }
        .klimaag { stroke: #b48cff; }
        @keyframes folyik { to { stroke-dashoffset: -20; } }
        .gyuru { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
        .gyuru svg { width: 74px; height: 74px; flex: none; transform: rotate(-90deg); }
        .gyuru circle { fill: none; stroke-width: 9; }
        .gyuru .alap { stroke: var(--keret); }
        .gyuru .ertek { stroke: var(--meleg); stroke-linecap: round; transition: stroke-dashoffset .8s; }
        .gyuru b { font-size: 21px; font-weight: 600; display: block; line-height: 1.1; }
        .gyuru span { font-size: 12px; color: var(--halk); }
        .lamp { display: flex; align-items: center; gap: 8px; padding: 5px 0; font-size: 13.5px; }
        .lamp i { width: 11px; height: 11px; border-radius: 50%; background: var(--keret); flex: none; }
        .lamp i.eg { background: var(--meleg); box-shadow: 0 0 8px var(--meleg); animation: pul 1.6s ease-in-out infinite; }
        .lamp span { color: var(--halk); flex: 1; min-width: 0; }
        @keyframes pul { 50% { opacity: .55; } }
        .egyez { margin-top: 6px; font-size: 12px; color: var(--halk); }
        .egyez b { font-size: 17px; color: var(--primary-text-color); font-weight: 600; margin-right: 4px; }
        .blokk { margin-top: 14px; }
        .merleg { display: flex; height: 16px; border-radius: 8px; overflow: hidden; background: var(--keret); }
        .merleg div { transition: width .8s; }
        .m-kazan { background: var(--meleg); } .m-klima { background: #b48cff; }
        .jm { display: flex; flex-wrap: wrap; gap: 4px 14px; margin-top: 5px; font-size: 12.5px; color: var(--halk); }
        .jm i { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; }
        .jm b { color: var(--primary-text-color); font-weight: 600; }
        .kt { display: grid; grid-template-columns: 96px minmax(0, 1fr) 92px; gap: 8px; align-items: center; margin-bottom: 4px; font-size: 13px; color: var(--halk); }
        .kt .s { height: 12px; border-radius: 6px; background: var(--keret); overflow: hidden; }
        .kt .s div { height: 100%; border-radius: 6px; }
        .kt b { text-align: right; color: var(--primary-text-color); font-weight: 600; white-space: nowrap; }
        .kt.nyer { color: var(--primary-text-color); font-weight: 600; }
        .lanc { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
        .lsz { padding: 4px 9px; border-radius: 12px; font-size: 12px; border: 1px solid var(--keret); color: var(--halk); }
        .lsz.mult { color: var(--jo); border-color: color-mix(in srgb, var(--jo) 45%, transparent); }
        .lsz.most { background: var(--meleg); border-color: var(--meleg); color: #fff; font-weight: 600; }
        .lsz.utan { opacity: .5; }
        [hidden] { display: none !important; }
        .nyil { color: var(--halk); font-size: 11px; opacity: .6; }
        .tipp2 { font-size: 11.5px; color: var(--halk); margin-top: 5px; }
        .sav { display: grid; grid-template-columns: 74px minmax(0, 1fr) 46px; align-items: center; gap: 6px; margin-bottom: 3px; font-size: 12px; color: var(--halk); }
        .sav svg { width: 100%; display: block; }
        .sav b { color: var(--primary-text-color); font-weight: 600; text-align: right; }
        .tl-cimke { display: grid; grid-template-columns: 74px minmax(0, 1fr) 46px; gap: 6px; font-size: 11px; color: var(--halk); }
        .tl-cimke div:nth-child(2) { display: flex; justify-content: space-between; }
        .ln { display: grid; grid-template-columns: 44px 12px minmax(0, 1fr); gap: 6px; align-items: baseline; padding: 4px 0; border-bottom: 1px solid var(--keret); font-size: 13px; }
        .ln:last-child { border-bottom: 0; }
        .ln time { color: var(--halk); font-size: 12px; }
        .ln i { width: 8px; height: 8px; border-radius: 50%; background: var(--keret); align-self: center; }
        .ln i.eg { background: var(--meleg); }
        @container (max-width: 620px) {
          .fo { grid-template-columns: minmax(0, 1fr); gap: 12px; }
          .haz svg { max-width: 260px; }
        }
        @media (prefers-reduced-motion: reduce) { .ki, .be, .lamp i.eg { animation: none; } }
      </style>
      <ha-card>
        <div class="fej"><span class="nev" id="nev"></span><span class="jel" id="jel"></span><span class="tipp" id="tipp"></span></div>
        <div class="mond" id="mond"></div>
        <div class="baj" id="baj">${esc(t.fault)}</div>
        <div class="fo">
          <div class="oszlop"><div class="cim">${esc(t.inputs)}</div><div id="be"></div></div>
          <div class="oszlop haz">
            <svg viewBox="0 0 300 220" role="img" aria-label="${esc(t.balance)}">
              <path class="ki" style="--seb:var(--ks)" d="M62 92 C40 84 26 72 8 60"/>
              <path class="ki" style="--seb:var(--ks)" d="M238 92 C260 84 274 72 292 60"/>
              <path class="ki" style="--seb:var(--ks)" d="M56 150 H8"/>
              <path class="ki" style="--seb:var(--ks)" d="M244 150 H292"/>
              <path class="ki" style="--seb:var(--ks)" d="M150 28 V4"/>
              <path class="vonal" d="M38 104 L150 28 L262 104"/>
              <path class="vonal" d="M56 92 V192 H244 V92"/>
              <path class="be" id="kazanag" d="M86 216 V172"/>
              <path class="be klimaag" id="klimaag" d="M214 216 V172"/>
              <text x="86" y="166" text-anchor="middle" font-size="11" opacity=".75" id="tkazan"></text>
              <text x="214" y="166" text-anchor="middle" font-size="11" opacity=".75" id="tklima"></text>
              <text x="150" y="100" text-anchor="middle" font-size="32" font-weight="600" id="tbent"></text>
              <text x="150" y="122" text-anchor="middle" font-size="12.5" opacity=".7" id="tcel"></text>
              <text x="150" y="148" text-anchor="middle" font-size="17" font-weight="600" fill="var(--meleg)" style="fill:var(--meleg)" id="tigeny"></text>
              <text x="26" y="176" text-anchor="middle" font-size="14" font-weight="600" style="fill:var(--hideg)" id="tkint"></text>
            </svg>
          </div>
          <div class="oszlop"><div class="cim">${esc(t.output)}</div>
            <div class="gyuru"><svg viewBox="0 0 100 100"><circle class="alap" cx="50" cy="50" r="44"/><circle class="ertek" id="gy" cx="50" cy="50" r="44" stroke-dasharray="${RING}" stroke-dashoffset="${RING}"/></svg><div><b id="dem"></b><span>${esc(t.demand)}</span></div></div>
            <div class="lamp"><i id="l1"></i><span>${esc(t.wants)}</span><b id="l1t"></b></div>
            <div class="lamp"><i id="l2"></i><span>${esc(t.real)}</span><b id="l2t"></b></div>
            <div class="tipp2" id="kor"></div>
            <div class="egyez"><b id="egy"></b>${esc(t.agree)}</div>
          </div>
        </div>
        <div class="blokk"><div class="cim">${esc(t.balance)}</div><div class="merleg"><div class="m-kazan" id="mk"></div><div class="m-klima" id="ml"></div></div><div class="jm" id="jm"></div></div>
        <div class="blokk" id="ktg" hidden><div class="cim">${esc(t.cost)}</div><div id="ktgb"></div><div class="tipp2" id="ktgt"></div></div>
        <div class="blokk"><div class="cim">${esc(t.chain)}</div><div class="lanc" id="lanc"></div><div class="tipp2">${esc(t.chainHint)}</div></div>
        <div class="blokk"><div class="cim">${esc(t.timeline)}</div><div id="tl"></div></div>
        <div class="blokk"><div class="cim">${esc(t.log)}</div><div id="log"></div></div>
      </ha-card>`;
  }

  _set(id, text) { const el = this.shadowRoot.getElementById(id); if (el && el.textContent !== text) el.textContent = text; }

  _update() {
    const sr = this.shadowRoot, t = this._t(), h = this._hass;
    if (!sr || !this._ids) return;
    const dec = this._st("decision"), a = dec?.attributes || {}, cl = h.states[this._config.entity];
    if (!dec) return;
    const shadow = a.mode !== "active", heat = this._st("heat_need");
    this._set("nev", cl?.attributes?.friendly_name || "HC Thermostat");
    this._set("jel", shadow ? t.shadow : t.active);
    sr.getElementById("jel").classList.toggle("eles", !shadow);
    this._set("tipp", shadow ? t.shadowHint : t.activeHint);
    this._set("mond", a.explanation || "");
    sr.getElementById("baj").classList.toggle("van", this._st("fault")?.state === "on");

    // Inputs
    const pres = cl?.attributes?.preset_mode;
    const rows = [[t.indoor, `${num(a.indoor)} °C`], [t.outdoor, `${num(a.outdoor)} °C`], [t.target, `${num(a.target)} °C`]];
    const loss = this._num("heat_loss"), days = this._st("heat_loss")?.attributes?.days_learned;
    rows.push([t.loss, loss == null ? t.learning : `${Math.round(loss)} W/K`]);
    if (loss != null) rows.push(["", `${days} ${t.days}`]);
    if (pres && pres !== "auto") rows.push([t.presence, t[pres] || pres]);
    const z = this._st("heat_need")?.attributes || {};
    if (z.zone_configured) {
      const name = this._config.zone_name || t.zone;
      rows.push([name, `${num(z.zone_temp)} °C · ${z.zone_coupled ? t.joined : z.zone_door_open ? t.openCold : t.apart}`]);
    }
    const be = rows.map(([k, v]) => `<div class="sor"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join("");
    if (be !== this._beHtml) { this._beHtml = be; sr.getElementById("be").innerHTML = be; }

    // House
    const need = this._num("heat_need"), other = heat?.attributes?.other_sources_kw ?? 0, boiler = heat?.attributes?.boiler_share_kw ?? 0;
    this._set("tbent", `${num(a.indoor)}°`);
    this._set("tcel", `${t.target.toLowerCase()} ${num(a.target)}°`);
    this._set("tigeny", need == null ? "–" : `${num(need, 2)} kW`);
    this._set("tkint", `${num(a.outdoor)}°`);
    this._set("tkazan", t.boiler);
    this._set("tklima", other > 0 ? t.other.split(" ")[0] : "");
    // A bigger loss flows faster.
    sr.host.style.setProperty("--ks", `${Math.max(0.7, 3.5 - (need ?? 0) * 0.6)}s`);
    const realOn = a.actual_heating === true, wants = this._st("heat_decision")?.state === "on";
    sr.getElementById("kazanag").classList.toggle("megy", realOn);
    sr.getElementById("klimaag").classList.toggle("megy", other > 0.05);

    // Output
    const demand = this._num("demand");
    this._set("dem", demand == null ? "–" : `${demand} %`);
    sr.getElementById("gy").setAttribute("stroke-dashoffset", String(RING * (1 - Math.min(demand ?? 0, 100) / 100)));
    sr.getElementById("l1").classList.toggle("eg", wants);
    this._set("l1t", wants ? t.wantOn : t.wantOff);
    sr.getElementById("l2").classList.toggle("eg", realOn);
    this._set("l2t", a.actual_heating == null ? t.unknown : realOn ? t.on : t.off);
    this._set("kor", a.limited_by ? `${t.limited}: ${t[a.limited_by] || a.limited_by}` : "");
    const agree = this._num("agreement");
    this._set("egy", agree == null ? "–" : `${num(agree, 0)} %`);

    // Balance
    const total = Math.max(need ?? 0, 0.001), oShare = Math.min(other / total, 1) * 100, bShare = Math.min(boiler / total, 1) * 100;
    sr.getElementById("mk").style.width = `${bShare}%`;
    sr.getElementById("ml").style.width = `${oShare}%`;
    const jm = `<span><b>${num(need, 2)} kW</b> ${esc(t.need)}</span><span><i style="background:var(--meleg)"></i>${esc(t.boiler)} <b>${num(boiler, 2)} kW</b></span><span><i style="background:#b48cff"></i>${esc(t.other)} <b>${num(other, 2)} kW</b></span>`;
    const extra = heat?.attributes?.extra_source_kw ?? 0;
    const zoneNote = z.zone_configured && !z.zone_coupled && extra > 0.05
      ? `<span>${esc(this._config.zone_name || t.zone)}: <b>${num(extra, 2)} kW</b> ${esc(t.zoneNote)}</span>` : "";
    const jmAll = jm + zoneNote;
    if (jmAll !== this._jmHtml) { this._jmHtml = jmAll; sr.getElementById("jm").innerHTML = jmAll; }

    // Cost
    const adv = this._st("source_advice"), ca = adv?.attributes || {};
    const hasCost = adv && adv.state !== "unknown" && ca.boiler_cost_per_kwh != null;
    sr.getElementById("ktg").hidden = !hasCost;
    if (hasCost) {
      const oName = this._config.other_name || t.otherSrc, max = Math.max(ca.boiler_cost_per_kwh, ca.other_cost_per_kwh, 0.01);
      const bar = (name, value, color, win, note) => `<div class="kt${win ? " nyer" : ""}"><span>${esc(name)}${note ? ` <small>${esc(note)}</small>` : ""}</span><div class="s"><div style="width:${(value / max) * 100}%;background:${color}"></div></div><b>${num(value, 1)} Ft</b></div>`;
      const otherWins = ca.other_cost_per_kwh < ca.boiler_cost_per_kwh;
      const ktgb = bar(t.boilerName, ca.boiler_cost_per_kwh, "var(--meleg)", !otherWins) + bar(oName, ca.other_cost_per_kwh, "#b48cff", otherWins, ca.cop ? `COP ${num(ca.cop, 1)}` : "");
      if (ktgb !== this._ktgHtml) { this._ktgHtml = ktgb; sr.getElementById("ktgb").innerHTML = ktgb; }
      const parts = [ca.explanation, t.perKwh];
      if (ca.breakeven_outdoor != null) parts.push(`${oName}: ${num(ca.breakeven_outdoor)} °C ${t.breakeven}`);
      else if (ca.other_always_cheaper != null) parts.push(`${oName}: ${ca.other_always_cheaper ? t.always : t.never}`);
      if (ca.saving_per_hour != null) parts.push(`${t.saving}: ${num(ca.saving_per_hour, 1)} ${t.perHour}`);
      if (ca.other_allowance_left != null) parts.push(`${oName} ${t.allowance}: ${num(ca.other_allowance_left, 0)} ${ca.other_allowance_unit || ""}`);
      if (ca.boiler_allowance_left != null) parts.push(`${t.boilerName} ${t.allowance}: ${num(ca.boiler_allowance_left, 0)} ${ca.boiler_allowance_unit || ""}`);
      parts.push(t.costHint);
      this._set("ktgt", parts.join(" · "));
    }

    // Decision chain
    const reason = dec.state, shown = reason === "external" ? [...CHAIN.slice(0, 6), "restart_burn", "external"] : reason === "restart_burn" ? [...CHAIN.slice(0, 6), "restart_burn", "external"] : CHAIN;
    const at = shown.indexOf(reason);
    const lanc = shown.map((r, i) => `<span class="lsz ${i < at ? "mult" : i === at ? "most" : "utan"}">${esc(t.r[r] || r)}</span>`).join('<span class="nyil">›</span>');
    if (lanc !== this._lancHtml) { this._lancHtml = lanc; sr.getElementById("lanc").innerHTML = lanc; }

    // Log
    const lang = String(h.language || "en").startsWith("hu") ? "text_hu" : "text_en";
    const log = (a.log || []).slice(-6).reverse().map((e) => {
      const d = new Date(e.time);
      return `<div class="ln"><time>${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}</time><i class="${e.output ? "eg" : ""}"></i><div>${esc(e[lang])}</div></div>`;
    }).join("") || `<div class="tipp2">${esc(t.noLog)}</div>`;
    if (log !== this._logHtml) { this._logHtml = log; sr.getElementById("log").innerHTML = log; }
  }

  async _loadHistory() {
    if (!this._hass || !this._ids || this._loading) return;
    const c = this._config, ids = [this._ids.heat_decision, c.reference, c.indoor, c.outdoor].filter(Boolean);
    if (!ids.length) return;
    this._loading = true;
    try {
      const end = Date.now(), start = end - DAY;
      this._hist = await this._hass.callWS({
        type: "history/history_during_period", start_time: new Date(start).toISOString(), end_time: new Date(end).toISOString(),
        entity_ids: ids, minimal_response: true, no_attributes: true, significant_changes_only: false,
      });
      this._span = [start, end];
      this._drawTimeline();
    } catch (e) { /* the next round tries again */ }
    this._loading = false;
  }

  _points(id) { return (this._hist?.[id] || []).map((p) => [(p.lu ?? p.lc) * 1000, p.s]); }

  _strip(label, id, color) {
    const [start, end] = this._span, W = 1000, pts = this._points(id);
    let rects = "";
    pts.forEach(([ts, s], i) => {
      if (s !== "on") return;
      const x1 = Math.max(ts, start), x2 = i + 1 < pts.length ? pts[i + 1][0] : end;
      rects += `<rect x="${((x1 - start) / (end - start)) * W}" y="0" width="${Math.max(((x2 - x1) / (end - start)) * W, 2)}" height="14" fill="${color}"/>`;
    });
    const first = pts.length ? ((Math.max(pts[0][0], start) - start) / (end - start)) * W : W;
    const hatter = `<rect x="${first}" y="0" width="${W - first}" height="14" fill="var(--keret)"/>`;
    return `<div class="sav"><span>${esc(label)}</span><svg viewBox="0 0 ${W} 14" preserveAspectRatio="none" height="14">${hatter}${rects}</svg><b></b></div>`;
  }

  _line(label, id, color) {
    const [start, end] = this._span, W = 1000, H = 44;
    const pts = this._points(id).map(([ts, s]) => [ts, parseFloat(s)]).filter((p) => !isNaN(p[1]));
    if (!pts.length) return "";
    const vs = pts.map((p) => p[1]), lo = Math.min(...vs), hi = Math.max(...vs), rng = Math.max(hi - lo, 0.5);
    const d = pts.map(([ts, v], i) => `${i ? "L" : "M"}${(((Math.max(ts, start) - start) / (end - start)) * W).toFixed(1)} ${(H - 3 - ((v - lo) / rng) * (H - 6)).toFixed(1)}`).join("") + `L${W} ${(H - 3 - ((vs.at(-1) - lo) / rng) * (H - 6)).toFixed(1)}`;
    return `<div class="sav"><span>${esc(label)}<br>${num(lo)}–${num(hi)}°</span><svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" height="${H}"><path d="${d}" fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><b>${num(vs.at(-1))}°</b></div>`;
  }

  _drawTimeline() {
    const sr = this.shadowRoot, t = this._t(), c = this._config;
    if (!sr || !this._span) return;
    const stamp = (ms) => { const d = new Date(ms); return `${String(d.getHours()).padStart(2, "0")}:00`; };
    const [start, end] = this._span, mid = start + (end - start) / 2;
    sr.getElementById("tl").innerHTML =
      (c.indoor ? this._line(t.indoor, c.indoor, "var(--meleg)") : "") +
      (c.outdoor ? this._line(t.outdoor, c.outdoor, "var(--hideg)") : "") +
      this._strip(t.wants, this._ids.heat_decision, "var(--meleg)") +
      (c.reference ? this._strip(t.real, c.reference, "#d9534f") : "") +
      `<div class="tl-cimke"><div></div><div><span>${stamp(start)}</span><span>${stamp(mid)}</span><span>${stamp(end)}</span></div><div></div></div>`;
  }
}
if (!customElements.get("hc-thermostat-card")) customElements.define("hc-thermostat-card", HcThermostatCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "hc-thermostat-card", name: "HC Thermostat", description: "What the heating supervisor reads, decides and would do." });

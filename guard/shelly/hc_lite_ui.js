// HC Lite – the web set-up page (0.79.9). The relay serves a small page (/script/<id>/lite?page=1) that loads this
// program; it runs in the browser on the relay's own address and talks to the relay only (the script's endpoint and
// the device's own RPC), so it needs no Home Assistant. Status, every setting, and the first steps of a new relay:
// the token, the clock, the thermometer (BLU H&T, wired probe or a Wi-Fi H&T's webhook) and shadow / live.
(function () {
  "use strict";
  if (window.__hclUi) return;
  window.__hclUi = 1;
  window.g = function () {}; // the small page's own refresh: this page takes over

  const HU = (navigator.language || "").toLowerCase().indexOf("hu") === 0;
  const T = HU ? {
    title: "HC Lite", status: "Állapot", settings: "Beállítások", setup: "Első lépések",
    room: "Bent", target: "Cél", mode: "Mód", auto: "Auto", away: "Távol", off: "Ki",
    day: "nappali", night: "éjszakai", preheat: "előfűtés", manual: "kézi", frost: "fagyvédelem", notime: "nincs idő",
    heats: "fűt", would: "fűtene", rests: "pihen", shadow: "árnyék", live: "élesben", realRelay: "valódi relé",
    demand: "Igény", integral: "integrál", boost: "boost", today: "Ma", starts: "indítás", min: "perc",
    reading: "Mérés", ago: "ennyi ideje", noReading: "nincs mérés", since: "Ebben az állapotban",
    reason: "Döntés", holdUntilNext: "kézi cél a következő programváltásig", holdClear: "Kézi cél törlése",
    log: "Utolsó kapcsolások", on: "be", offW: "ki", save: "Mentés", saved: "Elmentve", nothing: "Nincs változás",
    login: "Token", loginHint: "A relé tokene (HC-ben is ez van). A böngésző megjegyzi ezen a gépen.",
    loginBtn: "Belépés", logout: "Kilépés", badTok: "Rossz token", needTok: "A változtatáshoz add meg a tokent (Első lépések).",
    newTok: "Ennek a relének még nincs tokene. Hozz létre egyet: ezzel lehet majd állítani (és a HC-t is ezzel kötheted be).",
    gen: "Új token", create: "Token beállítása", tokSaved: "Token beállítva",
    clock: "Óra és időzóna", clockOk: "Rendben", clockBad: "Nincs pontos idő: a program nem tud váltani. Állítsd be az időzónát és az NTP-t a Shelly beállításaiban (Settings → Time).",
    tz: "Időzóna", sensor: "Hőmérő", pick: "Ezt használja", found: "Talált hőmérők", none: "Nem találtam BTHome hőmérőt. BLU H&T-t a Shelly saját oldalán (Components → Add BTHome device) lehet felvenni.",
    pushTitle: "Wi-Fi H&T (küldi a mérést)", pushHow: "A Wi-Fi H&T saját oldalán: Actions → új Webhook, esemény: Temperature change, cím az alábbi (az ${ev.tC} részt hagyd így). A H&T akkor érhető el, amikor felébred (nyomd meg a gombját).",
    copy: "Másolás", copied: "Kimásolva", run: "Indulás bekapcsoláskor", runOk: "A szkript bekapcsoláskor magától indul.",
    runBad: "A szkript bekapcsoláskor nem indul el magától.", runFix: "Bekapcsolás", modeTitle: "Árnyék vagy élesben",
    shadowHow: "Árnyékban a HC Lite dönt és jelent, de nem kapcsolja a kazánt – így a régi termosztát mellett kipróbálható. Ha jól dönt, kapcsold élesre.",
    goLive: "Élesítés (kapcsolhatja a kazánt)", sure: "Biztosan? A HC Lite ezután kapcsolja a kazánt – kattints újra", probe: "vezetékes szonda", goShadow: "Vissza árnyékba", hcNote: "Ha Home Assistantból (HC) is kezeled, a HC a következő kiolvasáskor a saját beállításait küldi vissza – ott állítsd, vagy frissítsd a HC-t 0.79.9-re, ami átveszi az itt tett változtatást.",
    rev: "beállítás-változat", err: "Hiba", offline: "A relé nem válaszol", yes: "igen", no: "nem",
    secs: "mp", mins: "perc", hours: "óra",
  } : {
    title: "HC Lite", status: "Status", settings: "Settings", setup: "First steps",
    room: "Room", target: "Target", mode: "Mode", auto: "Auto", away: "Away", off: "Off",
    day: "day", night: "night", preheat: "preheat", manual: "manual", frost: "frost", notime: "no time",
    heats: "heating", would: "would heat", rests: "resting", shadow: "shadow", live: "live", realRelay: "real relay",
    demand: "Demand", integral: "integral", boost: "boost", today: "Today", starts: "starts", min: "min",
    reading: "Reading", ago: "age", noReading: "no reading", since: "In this state for",
    reason: "Decision", holdUntilNext: "manual target until the next program change", holdClear: "Clear the manual target",
    log: "Last switches", on: "on", offW: "off", save: "Save", saved: "Saved", nothing: "Nothing changed",
    login: "Token", loginHint: "The relay's token (the same as in HC). This browser keeps it on this computer.",
    loginBtn: "Log in", logout: "Log out", badTok: "Wrong token", needTok: "To change anything, give the token (First steps).",
    newTok: "This relay has no token yet. Create one: changes need it (and HC connects with it too).",
    gen: "New token", create: "Set the token", tokSaved: "Token set",
    clock: "Clock and time zone", clockOk: "OK", clockBad: "No exact time: the program cannot switch. Set the time zone and NTP in the Shelly settings (Settings → Time).",
    tz: "Time zone", sensor: "Thermometer", pick: "Use this", found: "Thermometers found", none: "No BTHome thermometer found. Add a BLU H&T on the Shelly's own page (Components → Add BTHome device).",
    pushTitle: "Wi-Fi H&T (pushes its reading)", pushHow: "On the Wi-Fi H&T's own page: Actions → new Webhook, event: Temperature change, the URL below (keep the ${ev.tC} part as it is). The H&T answers when it wakes (press its button).",
    copy: "Copy", copied: "Copied", run: "Start on power-up", runOk: "The script starts by itself on power-up.",
    runBad: "The script does not start by itself on power-up.", runFix: "Turn it on", modeTitle: "Shadow or live",
    shadowHow: "In shadow, HC Lite decides and reports but does not switch the boiler – try it beside the old thermostat. When it decides well, make it live.",
    goLive: "Go live (it may switch the boiler)", sure: "Sure? HC Lite will switch the boiler – click again", probe: "wired probe", goShadow: "Back to shadow", hcNote: "If Home Assistant (HC) manages it too, HC sends its own settings back at its next read – set it there, or update HC to 0.79.9, which takes over a change made here.",
    rev: "settings revision", err: "Error", offline: "The relay does not answer", yes: "yes", no: "no",
    secs: "s", mins: "min", hours: "h",
  };

  // label hu, label en, kind, min, max, step, unit
  const G = HU
    ? ["Célok és program", "Szabályozás", "Boost és előfűtés", "Kazánvédelem", "Hőmérő és mérés nélkül", "Működés"]
    : ["Targets and program", "Control", "Boost and preheat", "Boiler protection", "Thermometer and no reading", "Operation"];
  const F = [
    [0, "sp_day", "Nappali cél", "Day target", "n", 5, 30, 0.5, "°C"],
    [0, "sp_night", "Éjszakai cél", "Night target", "n", 5, 30, 0.5, "°C"],
    [0, "sp_away", "Távolléti cél", "Away target", "n", 5, 30, 0.5, "°C"],
    [0, "frost", "Fagyvédelem (Ki módban)", "Frost protection (Off)", "n", 3, 12, 0.5, "°C"],
    [0, "day", "Hétköznap nappal kezdete", "Weekday: day starts", "t"],
    [0, "night", "Hétköznap éjszaka kezdete", "Weekday: night starts", "t"],
    [0, "day_we", "Hétvégén nappal kezdete", "Weekend: day starts", "t"],
    [0, "night_we", "Hétvégén éjszaka kezdete", "Weekend: night starts", "t"],
    [1, "ctl", "Szabályozás", "Control", "c", ["hyst", "tpi", "pid"], HU ? ["hiszterézis", "TPI", "PI"] : ["hysteresis", "TPI", "PI"]],
    [1, "hyst", "Hiszterézis sáv (teljes)", "Hysteresis band (total)", "n", 0.1, 3, 0.1, "°C"],
    [1, "cycle", "Ciklusidő (TPI/PI)", "Cycle (TPI/PI)", "n", 600, 7200, 60, "s"],
    [1, "kp", "Erősítés (igény °C-onként)", "Gain (demand per °C)", "n", 0.05, 3, 0.05, ""],
    [1, "bias", "Alapigény", "Base demand", "n", 0, 0.8, 0.05, ""],
    [1, "ti", "PI integrálási idő", "PI integral time", "n", 1800, 86400, 300, "s"],
    [2, "boost", "Boost ennyi hiánytól (0: nincs)", "Boost from this gap (0: none)", "n", 0, 5, 0.1, "°C"],
    [2, "boost_end", "Boost vége ennyire a céltól", "Boost ends this close", "n", 0, 2, 0.1, "°C"],
    [2, "pre", "Előfűtés °C hiányonként (0: nincs)", "Preheat per °C short (0: none)", "n", 0, 120, 5, HU ? "perc" : "min"],
    [2, "pre_max", "Leghosszabb előfűtés", "Longest preheat", "n", 0, 360, 15, HU ? "perc" : "min"],
    [3, "min_on", "Legrövidebb égés", "Shortest burn", "n", 0, 3600, 30, "s"],
    [3, "min_off", "Legrövidebb szünet", "Shortest pause", "n", 0, 3600, 30, "s"],
    [3, "max_on", "Leghosszabb égés (0: nincs)", "Longest burn (0: none)", "n", 0, 86400, 300, "s"],
    [4, "sensor", "Hőmérő", "Thermometer", "c", ["bthomesensor", "temperature", "push"], HU ? ["BLU H&T (Bluetooth)", "vezetékes szonda", "Wi-Fi H&T (küldi)"] : ["BLU H&T (Bluetooth)", "wired probe", "Wi-Fi H&T (pushes)"]],
    [4, "sensor_id", "Hőmérő azonosító (komponens)", "Thermometer id (component)", "n", 0, 299, 1, ""],
    [4, "sensor_max_age", "Ennél régebbi mérés = nincs", "Older reading = none", "n", 300, 7200, 60, "s"],
    [4, "ns", "Mérés nélkül", "Without a reading", "c", ["duty", "off"], HU ? ["biztonsági ütem", "kikapcsol"] : ["safe duty cycle", "off"]],
    [4, "don", "Biztonsági ütem: be", "Duty: on", "n", 60, 7200, 60, "s"],
    [4, "doff", "Biztonsági ütem: ki", "Duty: off", "n", 60, 14400, 60, "s"],
    [5, "shadow", "Árnyék (dönt, de nem kapcsol)", "Shadow (decides, never switches)", "b"],
  ];

  const BASE = location.pathname.replace(/\/+$/, "");
  const TOKKEY = "hclite_tok_" + location.host + BASE;
  let tok = "";
  try { tok = localStorage.getItem(TOKKEY) || ""; } catch (e) { /* private window */ }
  let S = null, SYS = null, tab = "status", msg = "", timer = null;

  // ---------------------------------------------------------------- talking to the relay
  async function getStatus() {
    const r = await fetch(BASE, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }
  async function post(body, withTok) {
    const b = Object.assign({}, body);
    if (withTok !== false) b.tok = tok;
    const r = await fetch(BASE, { method: "POST", body: JSON.stringify(b) });
    const j = await r.json().catch(() => ({ error: String(r.status) }));
    if (!r.ok || j.error) throw new Error(j.error || r.status);
    return j;
  }
  async function rpc(method, params) {
    const q = params ? "?" + new URLSearchParams(params).toString() : "";
    const r = await fetch("/rpc/" + method + q, { cache: "no-store" });
    if (!r.ok) throw new Error(method + ": " + r.status);
    return r.json();
  }

  // ---------------------------------------------------------------- small helpers
  const $ = (s, el) => (el || document).querySelector(s);
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d) => (typeof v === "number" ? (d == null ? String(v) : v.toFixed(d)) : "–").replace(".", HU ? "," : ".");
  function dur(s) {
    if (typeof s !== "number" || s < 0) return "–";
    if (s < 90) return Math.round(s) + " " + T.secs;
    if (s < 5400) return Math.round(s / 60) + " " + T.mins;
    return (s / 3600).toFixed(1).replace(".", HU ? "," : ".") + " " + T.hours;
  }
  function periodText(p) {
    if (!p) return "–";
    const man = p.indexOf("(manual)") >= 0, base = p.replace(" (manual)", "");
    const w = { day: T.day, night: T.night, preheat: T.preheat, away: T.away.toLowerCase(), off: T.off.toLowerCase(), "no time": T.notime }[base] || base;
    return man ? w + " · " + T.manual : w;
  }
  function reasonText(r) {
    if (!r) return "–";
    if (r.indexOf("demand ") === 0) return T.demand.toLowerCase() + " " + r.slice(7);
    if (!HU) return r;
    return ({ boost: "boost (szünet nélkül)", "below target": "cél alatt", "target reached": "cél elérve", "inside the band": "a sávon belül",
      "no reading": "nincs mérés", "no reading: duty on": "nincs mérés: biztonsági ütem be", "no reading: duty off": "nincs mérés: biztonsági ütem ki",
      "max on": "leghosszabb égés letelt", boot: "indul" })[r] || r;
  }
  function randomTok() {
    const a = new Uint8Array(12);
    (window.crypto || {}).getRandomValues ? crypto.getRandomValues(a) : a.forEach((_, i) => { a[i] = Math.random() * 256; });
    return Array.from(a, (b) => "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"[b % 56]).join("");
  }
  function say(t, bad) { msg = (bad ? "! " : "") + t; render(); }
  async function act(fn) {
    try { await fn(); } catch (e) { say(T.err + ": " + (e.message === "bad token" ? T.badTok : e.message), true); }
  }

  // ---------------------------------------------------------------- look
  const css = `
  :root{--bg:#f4f6f7;--card:#fff;--fg:#1c2329;--mut:#62707c;--line:#dde3e8;--acc:#d2551f;--acc2:#fbeee6;--ok:#2d7d4e;--okb:#e5f3ea;--bad:#b3261e;--badb:#fbe9e7;--chip:#eef2f5}
  @media (prefers-color-scheme:dark){:root{--bg:#14181c;--card:#1c2228;--fg:#e7ecf0;--mut:#9aa7b2;--line:#303942;--acc:#f08a5d;--acc2:#3a261d;--ok:#6cc596;--okb:#1b3226;--bad:#ff8a80;--badb:#3b1d1b;--chip:#252d35;color-scheme:dark}}
  *{box-sizing:border-box}body{margin:0;max-width:none;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
  .w{max-width:640px;margin:0 auto;padding:14px 16px 40px}
  header{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}
  h1{font-size:20px;margin:0}h2{font-size:16px;margin:18px 0 8px}
  nav{display:flex;gap:6px;margin:6px 0 14px;flex-wrap:wrap}
  nav button,.btn{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:20px;padding:7px 14px;font:inherit;cursor:pointer}
  nav button.on{background:var(--acc);border-color:var(--acc);color:#fff}
  .btn.pri{background:var(--acc);border-color:var(--acc);color:#fff}.btn:disabled{opacity:.5}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}
  .big{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}.big b{font-size:46px;line-height:1;font-variant-numeric:tabular-nums}
  .mut{color:var(--mut);font-size:13.5px}
  .chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}.chip{background:var(--chip);border-radius:20px;padding:3px 10px;font-size:13px}
  .chip.hot{background:var(--acc2);color:var(--acc)}.chip.ok{background:var(--okb);color:var(--ok)}.chip.bad{background:var(--badb);color:var(--bad)}
  .row{display:flex;justify-content:space-between;gap:10px;padding:5px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}
  .row span:last-child{text-align:right;font-variant-numeric:tabular-nums}
  .btns{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
  label.f{display:grid;grid-template-columns:1fr 150px;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid var(--line)}
  label.f:last-child{border:0}label.f small{display:block;color:var(--mut);font-size:12px}
  input,select{font:inherit;color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:6px 8px;width:100%}
  input[type=checkbox]{width:22px;height:22px;justify-self:end}
  input.chg,select.chg{border-color:var(--acc)}
  .msg{padding:8px 12px;border-radius:8px;background:var(--okb);color:var(--ok);margin-bottom:10px}.msg.bad{background:var(--badb);color:var(--bad)}
  code{background:var(--chip);border-radius:6px;padding:6px 8px;display:block;overflow-wrap:anywhere;font-size:12.5px;margin:6px 0}
  table{width:100%;border-collapse:collapse;font-size:13.5px}td,th{text-align:left;padding:4px 6px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
  .bar{position:sticky;bottom:0;background:var(--bg);padding:10px 0;display:flex;gap:8px;align-items:center}
  @media (max-width:440px){label.f{grid-template-columns:1fr 120px}}`;
  document.head.insertAdjacentHTML("beforeend", "<style>" + css + "</style>");
  document.title = "HC Lite";
  document.body.innerHTML = '<div class="w" id="app"></div>';

  // ---------------------------------------------------------------- views
  function head() {
    const st = S ? (S.relay ? (S.shadow ? T.would : T.heats) : T.rests) : "…";
    return `<header><h1>${T.title}</h1><span class="chip ${S && S.relay ? "hot" : ""}">${esc(st)}</span>
      ${S ? `<span class="chip ${S.shadow ? "" : "ok"}">${S.shadow ? T.shadow : T.live}</span>` : ""}</header>
      <nav>${[["status", T.status], ["settings", T.settings], ["setup", T.setup]].map(([k, l]) =>
        `<button data-tab="${k}" class="${tab === k ? "on" : ""}">${l}</button>`).join("")}</nav>
      ${msg ? `<div class="msg ${msg[0] === "!" ? "bad" : ""}">${esc(msg.replace(/^! /, ""))}</div>` : ""}`;
  }

  function vStatus() {
    if (!S) return `<div class="card">${T.offline}</div>`;
    const age = typeof S.temp_age === "number" ? dur(S.temp_age) : "";
    const log = (S.log || []).slice().reverse().map((e) => {
      const ago = SYS && typeof SYS.uptime === "number" ? dur(SYS.uptime - e[0]) : "";
      return `<tr><td>${ago}</td><td>${e[1] ? T.on : T.offW}</td><td>${num(e[2], 1)} °C</td><td>${num(e[3], 1)} °C</td></tr>`;
    }).join("");
    return `<div class="card"><div class="big"><b>${num(S.temp, 1)}°</b>
        <div><div>${T.target}: <strong>${num(S.sp, 1)} °C</strong></div><div class="mut">${esc(periodText(S.period))}</div></div></div>
      <div class="chips">
        <span class="chip">${T.reason}: ${esc(reasonText(S.reason))}</span>
        ${typeof S.demand === "number" ? `<span class="chip">${T.demand} ${Math.round(S.demand * 100)} %</span>` : ""}
        ${typeof S.integral === "number" ? `<span class="chip">${T.integral} ${num(S.integral, 3)}</span>` : ""}
        ${S.boost ? `<span class="chip hot">${T.boost}</span>` : ""}
        ${S.shadow ? `<span class="chip">${T.realRelay}: ${S.real_relay ? T.on : T.offW}</span>` : ""}
      </div>
      <div class="btns">${["auto", "away", "off"].map((m) =>
        `<button class="btn ${S.mode === m ? "pri" : ""}" data-mode="${m}">${T[m]}</button>`).join("")}
        <button class="btn" data-adj="-0.5">−</button><button class="btn" data-adj="0.5">+</button>
        ${S.hold ? `<button class="btn" data-clear="1">${T.holdClear}</button>` : ""}</div>
      ${S.hold ? `<div class="mut" style="margin-top:6px">${T.holdUntilNext}: ${num(S.hold.sp, 1)} °C</div>` : ""}
    </div>
    <div class="card">
      <div class="row"><span>${T.reading}</span><span>${S.temp == null ? T.noReading : age}</span></div>
      <div class="row"><span>${T.since}</span><span>${dur(S.since_s)}</span></div>
      <div class="row"><span>${T.today}</span><span>${S.starts_today} ${T.starts} · ${S.on_min_today} ${T.min}</span></div>
      <div class="row"><span>${T.rev}</span><span>${S.rev == null ? "–" : S.rev} · ${esc(S.sv || "")}</span></div>
    </div>
    ${log ? `<div class="card"><h2 style="margin-top:0">${T.log}</h2><table><tr><th></th><th></th><th>${T.room}</th><th>${T.target}</th></tr>${log}</table></div>` : ""}`;
  }

  function field(f, cfg) {
    const [, k, hu, en, kind] = f, lab = HU ? hu : en, v = cfg[k];
    let inp;
    if (kind === "n") inp = `<input type="number" name="${k}" min="${f[5]}" max="${f[6]}" step="${f[7]}" value="${v == null ? "" : v}">`;
    else if (kind === "t") inp = `<input type="time" name="${k}" value="${esc(v)}">`;
    else if (kind === "c") inp = `<select name="${k}">${f[5].map((o, i) => `<option value="${o}" ${o === v ? "selected" : ""}>${esc(f[6][i])}</option>`).join("")}</select>`;
    else inp = `<input type="checkbox" name="${k}" ${v ? "checked" : ""}>`;
    const range = kind === "n" ? `<small>${num(f[5])}–${num(f[6])} ${f[8]}</small>` : "";
    return `<label class="f"><span>${lab}${range}</span>${inp}</label>`;
  }
  function vSettings() {
    if (!S || !S.cfg) return `<div class="card">${T.offline}</div>`;
    const groups = G.map((g, i) => `<div class="card"><h2 style="margin-top:0">${g}</h2>${F.filter((f) => f[0] === i).map((f) => field(f, S.cfg)).join("")}</div>`).join("");
    return `${tok ? "" : `<div class="msg bad">${T.needTok}</div>`}<form id="cf">${groups}
      <div class="mut" style="margin-bottom:8px">${T.hcNote}</div>
      <div class="bar"><button class="btn pri" type="submit" ${tok ? "" : "disabled"}>${T.save}</button></div></form>`;
  }
  function readForm() {
    const out = {}, fm = $("#cf");
    F.forEach((f) => {
      const k = f[1], el = fm.elements[k];
      if (!el) return;
      let v;
      if (f[4] === "n") { v = parseFloat(el.value); if (!(v >= f[5] && v <= f[6])) return; }
      else if (f[4] === "b") v = el.checked;
      else v = el.value;
      if (f[4] === "t" && !/^\d\d:\d\d$/.test(v)) return;
      if (v !== S.cfg[k]) out[k] = v;
    });
    return out;
  }

  let found = null, runCfg = null, armLive = false;
  function vSetup() {
    const host = location.host, hook = `http://${host}${BASE}?tok=${tok || "TOKEN"}&t=\${ev.tC}`;
    const clockOk = SYS && typeof SYS.unixtime === "number" && SYS.unixtime > 0 && SYS.time;
    const sens = found == null ? `<div class="mut">…</div>` : found.length ? found.map((c) =>
      `<div class="row"><span>${esc(c.name || c.key)} <span class="mut">${esc(c.key)}</span></span><span>${num(c.value, 1)} °C
        <button class="btn" data-sensor="${esc(c.key)}" ${tok ? "" : "disabled"}>${T.pick}</button></span></div>`).join("") : `<div class="mut">${T.none}</div>`;
    const cur = S && S.cfg ? `${esc(S.cfg.sensor)}${S.cfg.sensor !== "push" ? ":" + S.cfg.sensor_id : ""}` : "–";
    return `<div class="card"><h2 style="margin-top:0">1. ${T.login}</h2>
      ${S && S.token === false ? `<p>${T.newTok}</p><div class="btns"><input id="nt" value="${randomTok()}" style="max-width:260px">
        <button class="btn pri" data-init="1">${T.create}</button></div>`
      : tok ? `<div class="row"><span>${T.login}</span><span>•••••• <button class="btn" data-logout="1">${T.logout}</button></span></div>`
      : `<p class="mut">${T.loginHint}</p><div class="btns"><input id="lt" type="password" autocomplete="current-password" style="max-width:260px">
        <button class="btn pri" data-login="1">${T.loginBtn}</button></div>`}</div>
    <div class="card"><h2 style="margin-top:0">2. ${T.clock}</h2>
      <div class="row"><span>${T.clock}</span><span>${clockOk ? esc(SYS.time) + " · " + T.clockOk : "–"}</span></div>
      <div class="row"><span>${T.tz}</span><span>${esc((SYS && SYS.tz) || "–")}</span></div>
      ${clockOk ? "" : `<p class="msg bad">${T.clockBad}</p>`}
      <div class="row"><span>${T.run}</span><span>${runCfg == null ? "…" : runCfg ? T.runOk : `${T.runBad} <button class="btn" data-run="1">${T.runFix}</button>`}</span></div></div>
    <div class="card"><h2 style="margin-top:0">3. ${T.sensor}: <span class="mut">${cur}</span></h2>
      <div class="mut">${T.found}</div>${sens}
      <h2>${T.pushTitle}</h2><p class="mut">${T.pushHow}</p><code id="hook">${esc(hook)}</code>
      <div class="btns"><button class="btn" data-copy="1">${T.copy}</button>
        <button class="btn" data-push="1" ${tok ? "" : "disabled"}>${T.pick}</button></div></div>
    <div class="card"><h2 style="margin-top:0">4. ${T.modeTitle}</h2><p class="mut">${T.shadowHow}</p>
      ${S && S.cfg ? `<button class="btn" data-shadow="${S.cfg.shadow ? 0 : 1}" ${tok ? "" : "disabled"}>${S.cfg.shadow ? (armLive ? T.sure : T.goLive) : T.goShadow}</button>` : ""}</div>`;
  }

  function render() {
    const app = $("#app");
    const keep = tab === "settings" && $("#cf") ? readFormSafe() : null;
    app.innerHTML = head() + (tab === "status" ? vStatus() : tab === "settings" ? vSettings() : vSetup());
    if (keep) Object.keys(keep).forEach((k) => { const el = $("#cf").elements[k]; if (el) { if (el.type === "checkbox") el.checked = keep[k]; else el.value = keep[k]; el.classList.add("chg"); } });
  }
  function readFormSafe() { try { return readForm(); } catch (e) { return null; } }

  // ---------------------------------------------------------------- actions
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    const d = b.dataset;
    if (d.tab) { tab = d.tab; msg = ""; armLive = false; render(); if (tab === "setup") loadSetup(); return; }
    if (d.mode) return act(async () => { S = await post({ mode: d.mode }); say(T.saved); });
    if (d.adj) return act(async () => { S = await post({ target: Math.round((S.sp + parseFloat(d.adj)) * 2) / 2, hold: "next" }); say(T.saved); });
    if (d.clear) return act(async () => { S = await post({ clear_hold: true }); say(T.saved); });
    if (d.logout) { tok = ""; try { localStorage.removeItem(TOKKEY); } catch (e) { /* */ } render(); return; }
    if (d.login) return act(async () => {
      const v = $("#lt").value.trim();
      tok = v; S = await post({}); try { localStorage.setItem(TOKKEY, v); } catch (e) { /* */ } say(T.saved);
    }).then(() => { if (msg[0] === "!") { tok = ""; render(); } });
    if (d.init) return act(async () => {
      const v = $("#nt").value.trim();
      S = await post({ init_tok: v }, false); tok = v; try { localStorage.setItem(TOKKEY, v); } catch (e) { /* */ } say(T.tokSaved + ": " + v);
    });
    if (d.sensor) return act(async () => {
      const [kind, id] = d.sensor.split(":");
      S = await post({ set: { sensor: kind, sensor_id: Number(id), sensor_max_age: 1800 } }); say(T.saved);
    });
    if (d.push) return act(async () => { S = await post({ set: { sensor: "push", sensor_max_age: 7200 } }); say(T.saved); });
    if (d.shadow === "0" && !armLive) { armLive = true; render(); return; } // going live takes a second click
    if (d.shadow) return act(async () => { armLive = false; S = await post({ set: { shadow: d.shadow === "1" } }); say(T.saved); });
    if (d.run) return act(async () => { await rpc("Script.SetConfig", { id: scriptId(), config: JSON.stringify({ enable: true }) }); runCfg = true; say(T.saved); });
    if (d.copy) {
      const t = $("#hook").textContent;
      (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(() => say(T.copied)).catch(() => {
        const r = document.createRange(); r.selectNodeContents($("#hook")); const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      });
    }
  });
  document.addEventListener("submit", (ev) => {
    if (ev.target.id !== "cf") return;
    ev.preventDefault();
    const set = readForm();
    if (!Object.keys(set).length) return say(T.nothing);
    act(async () => { S = await post({ set }); say(T.saved + " (" + Object.keys(set).length + ")"); });
  });
  document.addEventListener("input", (ev) => { if (ev.target.form && ev.target.form.id === "cf") ev.target.classList.add("chg"); });

  function scriptId() { const m = BASE.match(/\/script\/(\d+)\//); return m ? Number(m[1]) : 1; }

  async function loadSetup() {
    try {
      const comps = await rpc("Shelly.GetComponents", { dynamic_only: "true" });
      found = (comps.components || []).filter((c) => /^bthomesensor:/.test(c.key) && c.config && c.config.obj_id === 69)
        .map((c) => ({ key: c.key, name: c.config.name, value: c.status && c.status.value }));
      const probes = await rpc("Shelly.GetStatus");
      Object.keys(probes).filter((k) => /^temperature:\d+$/.test(k)).forEach((k) => found.push({ key: k, name: T.probe, value: probes[k].tC }));
    } catch (e) { found = []; }
    try { runCfg = !!(await rpc("Script.GetConfig", { id: scriptId() })).enable; } catch (e) { runCfg = null; }
    if (tab === "setup") render();
  }

  async function refresh() {
    try {
      S = await getStatus();
      try {
        const sys = await rpc("Sys.GetStatus");
        const cfg = SYS && SYS.tz ? { location: { tz: SYS.tz } } : await rpc("Sys.GetConfig");
        SYS = Object.assign(sys, { tz: cfg.location && cfg.location.tz });
      } catch (e) { /* the device page asks for its password; the status still shows */ }
    } catch (e) { S = null; }
    if (!(tab === "settings" && document.activeElement && document.activeElement.form)) render();
  }
  refresh();
  timer = setInterval(refresh, 15000);
})();

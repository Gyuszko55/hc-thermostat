// HC info – everything one HC Thermostat instance knows, drawn as its heating system (0.34.0). Read only.
// Left: the system as a line drawing (heat source by type, the HC controller, flow / return pipes, emitters, sensors),
// every part with its own data. Right: decision, presets and targets, inputs, outputs, inner values, health, every
// setting, the log. Data: websocket hc_thermostat/info_list and hc_thermostat/info (refreshed every 5 s).
// 0.44.0: a standalone / zone instance is drawn as its house (hc-house-view.js: the rooms of its `rooms` list in their
// order, the heat source in the plant room, pipes, TRV heads, windows, outdoor, sun, today's gas / energy); a click on a
// part scrolls to its data card (rooms and TRV heads: the room's own card). Central / buffer roles keep the line drawing.

// the house view, loaded with this file's own ?v= (cache-busting with the integration's version)
const HOUSE = import(new URL(`./hc-house-view.js${new URL(import.meta.url).search}`, import.meta.url).href).catch((e) => {
  console.warn("HC info: house view not loaded", e); return null;
});

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
// a signed number ("+0.5", "-1"); a missing value is "–" (never "+null")
const sgn = (v) => (v == null || v === "" || Number.isNaN(Number(v)) ? "–" : `${Number(v) >= 0 ? "+" : ""}${v}`);

const T = {
  hu: {
    title: "HC info", pick: "Példány", live: "élő", shadow: "árnyék", refresh: "5 mp-enként frissül", none: "–",
    yes: "igen", no: "nem", on: "be", off: "ki", age: "kora", sec: "mp", min: "p",
    decision: "Döntés", presets: "Presetek és célok", inputs: "Bemenetek (amire döntött)", devices_in: "Bemeneti eszközök",
    devices_out: "Kimeneti eszközök", inner: "Belső értékek", health: "Kazán / hőforrás állapota", settings: "Beállítások",
    log: "Napló", rooms: "Helyiségek és szelepfejek", cost: "Költség-összevetés", zone: "Zóna", load: "Terheléskorlát",
    demand: "Igény", output: "Kimenet", limited: "Korlátozta", target: "Cél", indoor: "Bent", outdoor: "Kint",
    flow: "Előremenő", ret: "Visszatérő", source: "Hőforrás", emitter: "Hőleadó", controller: "HC vezérlő",
    current: "Most", manual: "Kézi cél", until: "Lejár", night: "Éjszaka", modes: "Választható",
    season: "Fűtési szezon", fault: "Hiba", reason: "Ok", text: "Magyarázat", actual: "Valós fűtés",
    zones: "Zónák", tank: "Puffertartály", top: "Teteje", bottom: "Alja", asking: "Igénylő", open: "Nyitott",
    pump: "Szivattyú", boiler: "Kazán", window: "Ablak", floor: "Padló", humidity: "Páratartalom", dew: "Harmatpont",
    fan: "Ventilátor", coil: "Hőcserélő", relay: "Relé", setpoint: "Alapjel", power: "Teljesítmény",
    charge: "Töltés", discharge: "Kisütés", trv: "Szelepfej", trvHead: "Szelepfej – a gazda példány adatai", unit: "Beltéri egység", outdoor_unit: "Kültéri egység",
    noinst: "Még nincs HC példány.", group_other: "Egyéb",
    room: "Helyiség", roomList: "Helyiségek (egy kazán)", roomTrv: "Helyiség – szelepfejes, saját céllal", roomBoiler: "Helyiség – csak a kazánon át",
    r_temp: "Hőmérséklet", r_target: "Cél", r_reason: "Miért ez a cél", r_house: "A ház célja", r_mode: "Cél módja", r_presence: "Jelenlét",
    r_sensors: "Hőmérők", r_heads: "Szelepfejek", r_advice: "Tanács", r_demand: "Égést kérhet", r_entity: "Termosztát", r_lead: "Vezető helyiség (a kazánt vezérli)",
    r_role: "Szerepe", role_lead: "vezető helyiség (a hőmérője vezérli a kazánt)", role_trv: "szelepfejes helyiség (saját célja van)",
    role_watch: "megfigyelt helyiség (csak a kazánon át fűthető, szelep-tanácsot kap)", r_windows: "Ablak / ajtó", open_now: "most nyitva",
    win_own: "csak a helyiség szelepfejeit zárja le", win_boiler: "nyitáskor a kazán leáll",
    follow: "a ház célját követi", own: "saját menetrend", asking_now: "most kér",
    pump_ex: "Szivattyú-átmozgatás", pump_next: "Következő átmozgatás", pump_last: "Szivattyú utoljára ment",
  },
  en: {
    title: "HC info", pick: "Instance", live: "live", shadow: "shadow", refresh: "refreshes every 5 s", none: "–",
    yes: "yes", no: "no", on: "on", off: "off", age: "age", sec: "s", min: "min",
    decision: "Decision", presets: "Presets and targets", inputs: "Inputs (decided on)", devices_in: "Input devices",
    devices_out: "Output devices", inner: "Inner values", health: "Boiler / source health", settings: "Settings",
    log: "Log", rooms: "Rooms and TRV heads", cost: "Cost comparison", zone: "Zone", load: "Load limit",
    demand: "Demand", output: "Output", limited: "Limited by", target: "Target", indoor: "Indoor", outdoor: "Outdoor",
    flow: "Flow", ret: "Return", source: "Heat source", emitter: "Emitter", controller: "HC controller",
    current: "Now", manual: "Manual target", until: "Until", night: "Night", modes: "Offered",
    season: "Heating season", fault: "Fault", reason: "Reason", text: "Explanation", actual: "Actual heating",
    zones: "Zones", tank: "Buffer tank", top: "Top", bottom: "Bottom", asking: "Asking", open: "Open",
    pump: "Pump", boiler: "Boiler", window: "Window", floor: "Floor", humidity: "Humidity", dew: "Dew point",
    fan: "Fan", coil: "Coil", relay: "Relay", setpoint: "Setpoint", power: "Power",
    charge: "Charge", discharge: "Discharge", trv: "TRV head", trvHead: "TRV head – its host instance", unit: "Indoor unit", outdoor_unit: "Outdoor unit",
    noinst: "No HC instance yet.", group_other: "Other",
    room: "Room", roomList: "Rooms (one boiler)", roomTrv: "Room – TRV heads, own target", roomBoiler: "Room – through the boiler only",
    r_temp: "Temperature", r_target: "Target", r_reason: "Why this target", r_house: "House target", r_mode: "Target mode", r_presence: "Presence",
    r_sensors: "Thermometers", r_heads: "TRV heads", r_advice: "Advice", r_demand: "May ask for burns", r_entity: "Thermostat", r_lead: "Leading room (runs the boiler)",
    r_role: "Role", role_lead: "leading room (its thermometer runs the boiler)", role_trv: "TRV room (its own target)",
    role_watch: "watched room (heated only through the boiler, gets valve advice)", r_windows: "Window / door", open_now: "open now",
    win_own: "closes only the room's TRV heads", win_boiler: "opened: the boiler stops",
    follow: "follows the house target", own: "own schedule", asking_now: "asking now",
    pump_ex: "Pump exercise", pump_next: "Next pump exercise", pump_last: "Pump last ran",
  },
};

const REASON = {
  hu: { regulating: "Szabályoz", at_target: "Célon", boost: "Felfűtés", afterheat: "Utómelegedés", frost: "Fagyvédelem",
    disabled: "Kikapcsolva", sensor_lost: "Nincs hőmérő", window: "Ablak nyitva", season_off: "Nyári pihenő",
    restart_hold: "Újraindítás után vár", restart_burn: "Újraindítás utáni égés", external: "Külső termosztát",
    valve_exercise: "Szelepmozgatás", ac_heat: "Klíma fűt", ac_cool: "Klíma hűt", ac_pause: "Klíma szünetel",
    floor_limit: "Padlóhőfok-limit", floor_cool: "Padlóhűtés", dew_point: "Harmatpont-védelem",
    storage_charge: "Hőtároló tölt", storage_wait: "Hőtároló vár", floor_temper: "Padlótemperálás", thermostat_call: "Fali termosztát kér", thermostat_idle: "Fali termosztát nem kér", managed_off: "Kézzel kikapcsolva",
    no_demand: "Nincs igény", waiting_valves: "Szelepekre vár", heating: "Fűt", min_on: "Minimális futás",
    min_off: "Minimális szünet", valves_closed: "Szelepek zárva", charging: "Tölt", full: "Tele", ready: "Elég meleg",
    waiting_demand: "Igényre vár", no_sensor: "Nincs hőmérő" },
  en: {},
};

const SOURCE = {
  hu: { onoff_boiler: "On-off gázkazán", modulating_boiler: "Moduláló kazán", heat_pump: "Hőszivattyú",
    electric_boiler: "Elektromos kazán", air_conditioner: "Klíma", electric_heater: "Elektromos fűtő",
    storage_heater: "Hőtárolós kályha", district_heating: "Távfűtés", pellet_boiler: "Pellet kazán" },
  en: { onoff_boiler: "On/off gas boiler", modulating_boiler: "Modulating boiler", heat_pump: "Heat pump",
    electric_boiler: "Electric boiler", air_conditioner: "Air conditioner", electric_heater: "Electric heater",
    storage_heater: "Storage heater", district_heating: "District heating", pellet_boiler: "Pellet boiler" },
};
const SYSTEM = {
  hu: { radiator_single: "Radiátoros, egy zóna", radiator_trv: "Radiátoros, szelepfejekkel", radiator_zones: "Radiátoros, zónák",
    floor_single: "Padlófűtés, egy zóna", floor_zones: "Padlófűtés, zónák", mixed_no_circuit: "Vegyes, keverőkör nélkül",
    mixed_rtl: "Vegyes, RTL-szeleppel", mixed_mixing: "Vegyes, keverőkörrel", room_unit: "Helyiség saját egységgel", fan_coil: "Fan-coil" },
  en: { radiator_single: "Radiators, one zone", radiator_trv: "Radiators with TRV heads", radiator_zones: "Radiators, zones",
    floor_single: "Floor heating, one zone", floor_zones: "Floor heating, zones", mixed_no_circuit: "Mixed, no circuit",
    mixed_rtl: "Mixed, RTL valve", mixed_mixing: "Mixed, mixing loop", room_unit: "Room unit", fan_coil: "Fan coil" },
};
const CONTROL = { tpi: "TPI + PWM", pid: "PID + PWM", external: "Külső termosztát / external", curve: "Fűtési görbe / curve",
  onoff: "On-off", ac: "Klíma (i-Feel)", storage: "Hőtároló / storage" };

// Entity keys: which ones are read (inputs) and which are switched / written (outputs)
const OUT_KEYS = ["actuator_entity", "external_climate", "external_entity", "flow_setpoint_entity", "heat_enable_entity",
  "cool_mode_entity", "cool_flow_entity", "discharge_entity", "fan_entity", "boiler_entity", "pump_entity", "room_trvs"];

const KEY_HU = {
  indoor_entity: "Benti hőmérő", outdoor_entity: "Kinti hőmérő", reference_entity: "Referencia", floor_entity: "Padlóhőmérő",
  humidity_entity: "Páratartalom", window_entities: "Ablakok / ajtók", window_drop_entities: "Hőesés-figyelt hőmérők",
  presence_entities: "Jelenlét", coil_temp_entity: "Hőcserélő hőmérő", return_temp_entity: "Visszatérő hőmérő",
  power_available_entity: "Vezérelt áram", flame_entity: "Láng / égés", boiler_power_entity: "Kazán áramfelvétel",
  heat_energy_entity: "Hőmennyiség / gáz", extra_heat_entity: "Más hőforrás", zone_temp_entity: "Zóna hőmérő",
  zone_door_entities: "Zóna ajtók", target_source_entity: "Célhő forrás", hp_defrost_entity: "Leolvasztás",
  hp_dhw_entity: "Melegvíz-készítés", valve_feedback_entity: "Szelep visszajelzés", room_sensors: "Helyiséghőmérők",
  actuator_entity: "Kapcsolt relé", external_climate: "Külső termosztát", external_entity: "Külső termosztát",
  flow_setpoint_entity: "Előremenő-alapjel", heat_enable_entity: "Fűtés engedélyezés", cool_mode_entity: "Hűtés üzemmód",
  cool_flow_entity: "Hűtési előremenő", discharge_entity: "Kisütő ventilátor", fan_entity: "Fan-coil ventilátor",
  boiler_entity: "Kazán / hőforrás relé", pump_entity: "Szivattyú", room_trvs: "Szelepfejek", zone_entities: "Zónák",
  buffer_top_entity: "Tartály teteje", buffer_bottom_entity: "Tartály alja", assist_entity: "Segítő klíma",
  boiler_price_entity: "Kazán ár", other_price_entity: "Másik forrás ár", boiler_allowance_entity: "Kazán keret",
  other_allowance_entity: "Másik keret", demand_entity: "Fali termosztát érintkező",
  // decision / inner values (the generic rows)
  output: "Kimenet", actual: "Valós fűtés", limited_by: "Korlátozta", fault: "Hiba", manual: "Kézi cél", manual_until: "Kézi cél eddig",
  target: "Cél", indoor: "Bent", outdoor: "Kint", flow_setpoint: "Előremenő cél", external: "Külső termosztát",
  loss_kw_per_k: "Hőveszteség (kW/K)", heat_need_kw: "Hőigény (kW)", other_heat_kw: "Más hőforrás (kW)",
  reason: "Ok", demand: "Igény", season_on: "Fűtési szezon", fault_temp: "Hiba hőmérséklete", base_target: "Alapcél",
  preset: "Preset", preset_until: "Preset lejár", preset_until_home: "Preset után: otthon", manual_target: "Kézi cél",
  boost: "Felfűtés", pwm: "PWM", regulator: "Szabályozó", learner: "Tanulás", learned: "Tanult értékek", heat_need: "Hőigény",
  curve: "Fűtési görbe", exercise: "Szivattyú-átmozgatás", storage: "Hőtároló", ac: "Klíma", shadow: "Árnyék",
  floor_temper_on: "Padlótemperálás", floor_limit: "Padlóhőfok-limit", load: "Terhelés", details: "Részletek",
  pump: "Szivattyú", valve_open: "Szelep nyitva", wants_heat: "Hőt kér",
};
// English labels of the same generic rows (entity keys stay as they are)
const KEY_EN = {
  output: "Output", actual: "Actual heating", limited_by: "Limited by", fault: "Fault", manual: "Manual target", manual_until: "Manual until",
  target: "Target", indoor: "Indoor", outdoor: "Outdoor", flow_setpoint: "Flow setpoint", external: "External thermostat",
  loss_kw_per_k: "Heat loss (kW/K)", heat_need_kw: "Heat need (kW)", other_heat_kw: "Other heat (kW)",
  reason: "Reason", demand: "Demand", season_on: "Heating season", fault_temp: "Fault temperature", base_target: "Base target",
  preset: "Preset", preset_until: "Preset until", preset_until_home: "After the preset: home", manual_target: "Manual target",
  boost: "Boost", pwm: "PWM", regulator: "Regulator", learner: "Learning", learned: "Learned values", heat_need: "Heat need",
  curve: "Heating curve", exercise: "Pump exercise", storage: "Storage heater", ac: "Air conditioner", shadow: "Shadow",
  floor_temper_on: "Floor tempering", floor_limit: "Floor limit", load: "Load", details: "Details",
  pump: "Pump", valve_open: "Valve open", wants_heat: "Wants heat",
};
// why the output was held (Decision.limited_by)
const LIMITED = {
  hu: { min_on: "minimális futás", min_off: "minimális szünet", load_limit: "terheléskorlát", return_limit: "visszatérő-korlát", no_power: "nincs vezérelt áram" },
  en: { min_on: "minimum run", min_off: "minimum pause", load_limit: "load limit", return_limit: "return limit", no_power: "no controlled power" },
};
// keys whose true / false is a switch state (on / off), not yes / no
const ONOFF_KEYS = new Set(["output", "actual", "season_on", "pump", "floor_temper_on"]);

const GROUPS = [
  ["Célok és ütemezés / targets", /^(target_|night_|presets_|expiry_|hours_|frost_temp)/],
  ["Ciklus és szabályozó / cycle", /^(control|cycle_s|min_on_s|min_off_s|keep_alive|pid_|tpi_|yield_|shadow_regulator|onoff_|overshoot)/],
  ["Fűtési görbe / curve", /^(curve_|flow_|room_k)/],
  ["Hőszivattyú / heat pump", /^(hp_|heat_pump)/],
  ["Padló és hűtés / floor, cooling", /^(floor_|dew_|cool_|humidity_)/],
  ["Biztonság / safety", /^(sensor_|plaus_|restart_|failure_|frost|health_)/],
  ["Ablak / window", /^window_/],
  ["Szezon / season", /^season_/],
  ["Felfűtés / boost", /^(boost_|afterheat)/],
  ["Tanulás / learning", /^learning_/],
  ["Energia és költség / energy", /^(power_|boiler_|energy|extra_|cop_|price)/],
  ["Hőtároló, fan-coil, puffer, terhelés", /^(storage_|fan_|return_|load_|buffer_|trv_|central_|valve_|exercise_|zone_)/],
  ["Klíma / AC", /^ac_/],
];


// ------------------------------------------------------------------------------------------------------------------
// DATA MATRIX – what the drawing shows, where, and for which installation. One row per data point:
//   [id, part, label hu, label en, value(d), format, when]
// part: the element of the drawing the row belongs to (hc, outdoor, indoor, source, emitter, floor, fan, unit, storage)
// when: a list of tags; the row shows if EVERY tag holds for the instance (empty list = always). Tags: see WHEN.
// A row whose value is empty is left out. The "Adat-mátrix" section of the panel lists every row with its tags.
const g = (o, path) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
const CA = (d, k) => d.climate?.attributes?.[k];
const ENT = (d, k) => d.entities?.[k]?.[0];
const ENTS = (d, k) => d.entities?.[k];
// 0.43.0: why a room has its target
const ROOM_REASON = {
  hu: { follow: "a ház célja + eltérés", home: "saját: otthon", night: "saját: éjszaka", household_away: "a háztartás távol", household_vacation: "a háztartás szabadságon",
    absent: "senki a helyiségben: csökkentve", manual: "kézi cél (a következő változásig)", preset_home: "preset: jelen van", preset_away: "preset: távol", off: "kikapcsolva (fagyvédelem)", window: "nyitva az ablak: a fejek fagyvédelmen",
    house: "a ház célja (csak a kazánon át fűthető)", leading: "vezető helyiség: a ház célja" },
  en: { follow: "house target + offset", home: "own: home", night: "own: night", household_away: "household away", household_vacation: "household on vacation",
    absent: "nobody in the room: set back", manual: "manual target (until the next change)", preset_home: "preset: present", preset_away: "preset: away", off: "off (frost protection)", window: "window open: the heads on frost protection",
    house: "house target (heated through the boiler only)", leading: "leading room: the house target" },
};
const PRESENCE = { hu: { present: "jelen van", leaving: "épp kiment (vár)", absent: "távol" }, en: { present: "present", leaving: "just left (waiting)", absent: "absent" } };
const WATER = (c) => !["air_conditioner", "electric_heater", "storage_heater"].includes(c.src) || (c.src === "electric_heater" && c.sys.startsWith("floor"));
const WHEN = {
  relay: (c) => ["tpi", "pid", "onoff", "storage"].includes(c.ctl),
  pid: (c) => c.ctl === "pid", tpi: (c) => c.ctl === "tpi", onoff: (c) => c.ctl === "onoff", curve: (c) => c.ctl === "curve",
  external: (c) => ["external", "ac"].includes(c.ctl), ac: (c) => c.src === "air_conditioner",
  burner: (c) => ["onoff_boiler", "modulating_boiler", "pellet_boiler"].includes(c.src),
  heat_pump: (c) => c.src === "heat_pump", electric: (c) => ["electric_heater", "electric_boiler", "storage_heater"].includes(c.src),
  storage: (c) => c.src === "storage_heater", district: (c) => c.src === "district_heating", pellet: (c) => c.src === "pellet_boiler",
  water: WATER, floor: (c) => c.sys.startsWith("floor") || c.sys.startsWith("mixed"), radiator: (c) => c.sys.startsWith("radiator") || c.sys.startsWith("mixed"),
  fan_coil: (c) => c.sys === "fan_coil", zone: (c) => c.role === "zone", standalone: (c) => c.role === "standalone",
  trv: (c) => !!ENTS(c.d, "room_trvs") || c.sys === "radiator_trv", cooling: (c) => !!c.d.config?.floor_cooling,
  load: (c) => !!c.d.config?.load_limit_kw, power_signal: (c) => !!ENT(c.d, "power_available_entity"),
  rooms: (c) => !!ENTS(c.d, "room_sensors") || !!ENTS(c.d, "room_trvs"),
};
const LIMIT_FROM = { manual: "kézi / manual", covering: "burkolat és szenzor (mélyebb szenzornál becslés) / covering and probe (estimate for a deeper probe)", electric: "elektromos alapérték 27 °C / electric default", water: "vizes padló alapértéke 29 °C / water floor default" };
const INFO = [
  // HC controller
  ["reason", "hc", "Döntés", "Decision", (d) => d.decision?.reason, "reason", []],
  ["demand", "hc", "Igény", "Demand", (d) => d.decision?.demand, "pct", []],
  ["output", "hc", "Kimenet", "Output", (d) => d.decision?.output, "onoff", []],
  ["limited", "hc", "Korlátozta", "Limited by", (d) => d.decision?.limited_by, "limited", []],
  ["target", "hc", "Cél", "Target", (d) => d.decision?.target, "deg", []],
  ["preset", "hc", "Preset", "Preset", (d) => d.presets?.current, "text", []],
  ["manual", "hc", "Kézi cél eddig", "Manual until", (d) => (d.decision?.manual ? d.decision?.manual_until : null), "time", []],
  ["mode", "hc", "Üzemmód", "Mode", (d) => d.mode, "mode", []],
  ["season", "hc", "Fűtési szezon", "Heating season", (d) => d.live?.season_on, "onoff", []],
  ["fault", "hc", "Hiba", "Fault", (d) => (d.decision?.fault ? true : null), "bool", []],
  ["actual", "hc", "Valós fűtés", "Actual heating", (d) => d.actual, "onoff", ["relay"]],
  ["pid_k", "hc", "PID kp / ki / kd", "PID kp / ki / kd", (d) => (CA(d, "kp") != null ? `${CA(d, "kp")} / ${CA(d, "ki")} / ${CA(d, "kd")}` : null), "text", ["pid"]],
  ["pid_i", "hc", "PID integrál", "PID integral", (d) => CA(d, "pid_i"), "num", ["pid"]],
  ["tpi", "hc", "TPI belső / külső", "TPI int / ext", (d) => (CA(d, "tpi_coef_int") != null ? `${CA(d, "tpi_coef_int")} / ${CA(d, "tpi_coef_ext")}` : null), "text", ["tpi"]],
  ["tpi_off", "hc", "TPI eltolás", "TPI offset", (d) => CA(d, "tpi_offset"), "num", ["tpi"]],
  ["cycle", "hc", "Ciklus kezdete", "Cycle start", (d) => g(d, "state.pwm.cycle_start"), "time", ["relay"]],
  ["hyst", "hc", "Hiszterézis", "Hysteresis", (d) => CA(d, "onoff_hysteresis"), "deg", ["onoff"]],
  ["curve_i", "hc", "Görbe integrál", "Curve integral", (d) => g(d, "state.curve.integral"), "num", ["curve"]],
  ["learn", "hc", "Tanult utómelegedés", "Learned after-heat", (d) => g(d, "live.learned.afterheat"), "deg", ["relay"]],
  ["load", "hc", "Terhelés (kW)", "Load (kW)", (d) => (d.live?.load ? `${d.live.load.load_used_kw} / ${d.live.load.load_limit_kw}` : null), "text", ["load"]],
  // outside
  ["out", "outdoor", "Kint", "Outdoor", (d) => d.inputs?.outdoor?.value, "deg", []],
  ["out_age", "outdoor", "Mérés kora", "Reading age", (d) => (d.inputs?.outdoor?.value != null ? d.inputs.outdoor.age_s : null), "age", []],
  ["out_avg", "outdoor", "24 órás átlag", "24 h average", (d) => d.inputs?.outdoor_avg, "deg", []],
  ["need", "outdoor", "Hőigény", "Heat need", (d) => d.decision?.heat_need_kw, "kw", []],
  ["loss", "outdoor", "Hőveszteség", "Heat loss", (d) => d.live?.loss_kw_per_k, "kwk", []],
  // inside
  ["in", "indoor", "Bent", "Indoor", (d) => d.inputs?.indoor?.value ?? d.decision?.indoor, "deg", []],
  ["in_age", "indoor", "Mérés kora", "Reading age", (d) => (d.inputs?.indoor?.value != null ? d.inputs.indoor.age_s : null), "age", []],
  ["in_target", "indoor", "Cél", "Target", (d) => d.decision?.target, "deg", []],
  ["presence", "indoor", "Jelenlét", "Presence", (d) => d.inputs?.presence, "text", []],
  ["window", "indoor", "Ablak", "Window", (d) => d.inputs?.window_open, "open", []],
  ["hum", "indoor", "Páratartalom", "Humidity", (d) => d.inputs?.humidity?.value, "pctv", []],
  ["dew", "indoor", "Harmatpont", "Dew point", (d) => d.decision?.details?.dew_point, "deg", ["cooling"]],
  ["zone_door", "indoor", "Zóna ajtó", "Zone door", (d) => CA(d, "zone_door_open"), "open", []],
  ["call", "indoor", "Fali termosztát kér", "Wall thermostat asks", (d) => (ENT(d, "demand_entity") ? ({ true: "be / on", false: "ki / off" }[d.inputs?.call] ?? "ismeretlen / unknown") : null), "text", ["relay"]],
  ["contact_lost", "indoor", "Érintkező elveszett: helyiséghőmérő szerint", "Contact lost: by the room thermometer", (d) => d.decision?.details?.contact_lost || null, "bool", ["relay"]],
  ["tsource", "indoor", "Célhő forrás", "Target source", (d) => ENT(d, "target_source_entity")?.temperature ?? ENT(d, "target_source_entity")?.state, "text", []],
  // heat source
  ["relay", "source", "Relé", "Relay", (d) => ENT(d, "actuator_entity")?.state, "state", ["relay"]],
  ["flow_set", "source", "Előremenő cél", "Flow setpoint", (d) => d.decision?.flow_setpoint, "deg", ["curve"]],
  ["flow_ent", "source", "Alapjel entitás", "Setpoint entity", (d) => ENT(d, "flow_setpoint_entity")?.state, "state", ["curve"]],
  ["enable", "source", "Fűtés engedély", "Heat enable", (d) => ENT(d, "heat_enable_entity")?.state, "state", ["curve"]],
  ["ext", "source", "Külső termosztát", "External thermostat", (d) => { const e = ENT(d, "external_climate"); return e ? `${e.state} → ${e.temperature ?? "?"} °C` : null; }, "text", ["external"]],
  // 0.42.0: the managed thermostat (external / AC control)
  ["managed", "source", "Kezelt termosztát (integráció)", "Managed thermostat (integration)", (d) => (d.managed ? `${d.managed.adapter_name} · ${d.managed.platform || "?"}` : null), "text", ["external"]],
  ["sup_paused", "source", "HC felügyelet szünetel", "HC supervision paused", (d) => d.managed?.paused, "onoff", ["external"]],
  ["managed_off", "source", "Kézzel kikapcsolva", "Switched off by hand", (d) => (d.managed?.managed_off ? true : null), "bool", ["external"]],
  ["adopted", "hc", "Átvett kézi cél", "Adopted manual target", (d) => d.managed?.adopted?.target, "deg", ["external"]],
  ["actual_ext", "source", "Valós fűtés (hvac_action)", "Actual heating (hvac_action)", (d) => d.actual, "onoff", ["external"]],
  ["flame", "source", "Láng", "Flame", (d) => ENT(d, "flame_entity")?.state, "state", []],
  ["power", "source", "Áramfelvétel", "Power draw", (d) => { const e = ENT(d, "boiler_power_entity"); return e ? `${e.state} ${e.unit || ""}` : null; }, "text", []],
  ["health", "source", "Állapot", "Health", (d) => d.health?.state, "text", ["relay"]],
  ["starts", "source", "Indítás / óra", "Starts / hour", (d) => d.health?.starts_last_hour, "num", ["relay"]],
  ["ign", "source", "Gyújtás ideje", "Ignition", (d) => d.health?.last_ignition_s, "sec", ["burner"]],
  ["burn", "source", "Átlagos futás", "Average run", (d) => d.health?.average_burn_min, "min", ["relay"]],
  ["uncmd", "source", "Futás parancs nélkül", "Run without command", (d) => d.health?.burn_without_relay_min || null, "min", ["relay"]],
  ["hp_mode", "source", "Leolvaszt / melegvíz", "Defrost / hot water", (d) => d.decision?.details?.hp_mode, "text", ["heat_pump"]],
  ["defrost", "source", "Leolvasztás jel", "Defrost signal", (d) => ENT(d, "hp_defrost_entity")?.state, "state", ["heat_pump"]],
  ["dhw", "source", "Melegvíz jel", "Hot water signal", (d) => ENT(d, "hp_dhw_entity")?.state, "state", ["heat_pump"]],
  ["ret", "source", "Visszatérő", "Return", (d) => d.inputs?.return_temp?.value, "deg", ["district"]],
  ["ret_max", "source", "Visszatérő-korlát", "Return limit", (d) => d.config?.return_max || null, "deg", ["district"]],
  ["pwr_av", "source", "Vezérelt áram", "Controlled power", (d) => d.inputs?.power_available, "onoff", ["power_signal"]],
  ["cool_mode", "source", "Hűtés üzemmód", "Cooling mode", (d) => ENT(d, "cool_mode_entity")?.state, "state", ["cooling"]],
  // storage heater (unit itself)
  ["ch_frac", "storage", "Töltés", "Charge", (d) => d.decision?.details?.charge_fraction, "pct", ["storage"]],
  ["ch_win", "storage", "Töltési ablak", "Charge window", (d) => (d.decision?.details?.charge_start ? `${d.decision.details.charge_start}–${d.decision.details.charge_end}` : null), "text", ["storage"]],
  ["ch_why", "storage", "Töltés állapota", "Charge state", (d) => d.decision?.details?.charge_why, "text", ["storage"]],
  ["disch", "storage", "Kisütés", "Discharge", (d) => d.decision?.details?.discharge, "onoff", ["storage"]],
  ["st_pwr", "storage", "Vezérelt áram", "Controlled power", (d) => d.inputs?.power_available, "onoff", ["storage", "power_signal"]],
  // AC / room unit
  ["ac_hvac", "unit", "Üzemmód", "HVAC", (d) => d.decision?.external?.hvac, "text", ["ac"]],
  ["ac_set", "unit", "Beállított cél", "Unit setpoint", (d) => d.decision?.external?.target, "deg", ["ac"]],
  ["ac_aim", "unit", "Valódi cél", "Aim", (d) => d.decision?.details?.aim, "deg", ["ac"]],
  ["ac_unit", "unit", "Beltéri mérés", "Unit reading", (d) => d.inputs?.unit_temp, "deg", ["ac"]],
  ["ac_off", "unit", "Eltolás", "Offset", (d) => d.decision?.details?.offset, "num", ["ac"]],
  ["ac_int", "unit", "Integrál", "Integral", (d) => d.decision?.details?.integral, "num", ["ac"]],
  ["ac_assist", "unit", "Segít a háznak", "Assists the house", (d) => d.decision?.details?.assist, "bool", ["ac"]],
  ["heater", "unit", "Relé", "Relay", (d) => ENT(d, "actuator_entity")?.state, "state", ["electric", "relay"]],
  ["heater_pw", "unit", "Áramfelvétel", "Power draw", (d) => { const e = ENT(d, "boiler_power_entity"); return e ? `${e.state} ${e.unit || ""}` : null; }, "text", ["electric"]],
  ["heater_load", "unit", "Terhelés (kW)", "Load (kW)", (d) => (d.live?.load ? `${d.live.load.load_used_kw} / ${d.live.load.load_limit_kw}` : null), "text", ["load"]],
  // emitters
  ["flow_req", "emitter", "Kért előremenő", "Flow request", (d) => CA(d, "flow_request"), "deg", ["zone"]],
  ["valve_fb", "emitter", "Szelep visszajelzés", "Valve feedback", (d) => ENT(d, "valve_feedback_entity")?.state, "state", ["zone"]],
  ["exercise", "emitter", "Következő szelepmozgatás", "Next valve exercise", (d) => CA(d, "valve_exercise_next"), "time", ["zone"]],
  ["trv_heads", "emitter", "Szelepfej", "TRV head", (d) => (ENTS(d, "room_trvs") || []).map((e) => `${e.name}: ${e.current_temperature ?? "?"} → ${e.temperature ?? "?"} °C`).join("; ") || null, "text", ["trv"]],
  ["trv_src", "emitter", "Fej hőmérője", "Head thermometer", (d) => trvSources(d).join("; ") || null, "text", ["trv"]],
  ["trv_rooms", "emitter", "Helyiségek célja", "Room targets", (d) => Object.entries(d.rooms?.trv || {}).map(([r, v]) => `${r} ${v.target} (${sgn(v.offset)})`).join("; ") || null, "text", ["trv"]],
  ["trv_cal", "emitter", "Kalibrálás", "Calibration", (d) => Object.values(d.rooms?.trv || {}).flatMap((r) => Object.entries(r.heads || {}).map(([h, v]) => `${h.split(".")[1]} ${sgn(v.calibration)}`)).join("; ") || null, "text", ["trv"]],
  ["advice", "emitter", "Helyiségek eltérése", "Room deviation", (d) => (d.rooms?.advice || []).map((a) => `${a.room} ${sgn(a.deviation)} (${a.advice})`).join("; ") || null, "text", ["rooms"]],
  ["asking", "emitter", "Igénylő helyiségek", "Rooms asking", (d) => (d.rooms?.asking || []).join(", ") || null, "text", ["trv"]],
  // floor
  ["floor_t", "floor", "Padló", "Floor", (d) => d.inputs?.floor?.value ?? d.decision?.details?.floor, "deg", ["floor"]],
  ["floor_age", "floor", "Mérés kora", "Reading age", (d) => (d.inputs?.floor?.value != null ? d.inputs.floor.age_s : null), "age", ["floor"]],
  ["floor_max", "floor", "Padlóhőfok-limit", "Floor limit", (d) => d.live?.floor_limit?.value || d.config?.floor_max || null, "deg", ["floor"]],
  ["floor_limit_from", "floor", "Limit forrása", "Limit from", (d) => LIMIT_FROM[d.live?.floor_limit?.from] ?? null, "text", ["floor"]],
  ["floor_cover", "floor", "Burkolat / szenzor helye", "Covering / probe", (d) => (d.config?.floor_covering && d.config.floor_covering !== "none" ? `${d.config.floor_covering} / ${d.config.floor_probe}` : null), "text", ["floor"]],
  ["floor_why", "floor", "Limit oka", "Limit reason", (d) => d.decision?.details?.floor_why, "text", ["floor"]],
  ["floor_temper", "floor", "Padlótemperálás", "Floor tempering", (d) => d.live?.floor_temper_on, "onoff", ["floor", "relay"]],
  ["floor_target", "floor", "Padló célja", "Floor target", (d) => d.decision?.details?.floor_target, "deg", ["floor"]],
  ["temper_offset", "floor", "Temperálás eltérése", "Tempering offset", (d) => (d.config?.floor_temper ? d.live?.floor_limit?.temper_offset : null), "deg", ["floor", "relay"]],
  ["floor_fallback", "floor", "Hőmérő nélkül a padló szerint", "No room thermometer: by the floor", (d) => d.decision?.details?.floor_fallback || null, "bool", ["floor", "relay"]],
  ["safe", "floor", "Biztonságos víz", "Safe water", (d) => d.decision?.details?.safe_flow, "deg", ["floor", "cooling"]],
  ["cool_why", "floor", "Hűtés leállás oka", "Cooling stop", (d) => d.decision?.details?.why, "text", ["floor", "cooling"]],
  // fan coil
  ["fan_pct", "fan", "Ventilátor", "Fan", (d) => d.decision?.details?.fan_pct, "pctv", ["fan_coil"]],
  ["fan_why", "fan", "Ventilátor állapota", "Fan state", (d) => d.decision?.details?.fan_why, "text", ["fan_coil"]],
  ["coil", "fan", "Hőcserélő", "Coil", (d) => d.inputs?.coil?.value, "deg", ["fan_coil"]],
  ["fan_ent", "fan", "Ventilátor entitás", "Fan entity", (d) => { const e = ENT(d, "fan_entity"); return e ? `${e.state}${e.percentage != null ? " " + e.percentage + " %" : ""}` : null; }, "text", ["fan_coil"]],
];

// 0.42.0: which thermometer each TRV head works by – its own one, or an external one (with its reading)
const TRV_HEAD_HU = { hu: "saját hőmérő (nincs kalibrálás)", en: "own thermometer (no calibration)" };
let PANEL_LANG = "en";  // set at every render (English until the viewer's language is known)
function trvSources(d, lang) {
  const hu = (lang || PANEL_LANG) === "hu";
  const names = Object.fromEntries((ENTS(d, "room_trvs") || []).map((e) => [e.entity_id, e.name]));
  return Object.values(d?.rooms?.trv || {}).flatMap((r) => Object.entries(r.heads || {}).map(([h, v]) => {
    const src = v.sensor;
    const own = !src || src === "head";
    const label = own ? TRV_HEAD_HU[hu ? "hu" : "en"] : (v.sensor_name || [].concat(src).join(", ")) + (v.sensor_temp != null ? ` (${v.sensor_temp} °C)` : "");
    return `${names[h] || h}: ${label}`;
  }));
}

// ------------------------------------------------------------------------------------------------------------------
class HcInfoPanel extends HTMLElement {
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (this._house) this._theme();
    if (first) this._start();
  }
  set narrow(v) { this._narrow = v; }
  // opened as /hc-info?entity=climate.x (the dial card's "i" button): show that thermostat's instance
  set route(r) { this._route = r; if (this._list) this._fromUrl(); }
  async _fromUrl() {
    const entity = new URLSearchParams(location.search).get("entity");
    if (!entity || entity === this._urlEntity || !this._hass) return false;
    this._urlEntity = entity;
    try {
      const d = await this._hass.callWS({ type: "hc_thermostat/info", entity_id: entity });
      this._sel = d.entry_id; this._trv = d.via_trv || null; this._room = d.via_room || null; this._d = d; this._scrollPick = true;
      this._selKey = this._trv ? `trv:${this._trv}` : this._room ? `room:${this._room}` : null;
      if (this._room) this._open.room = true;
      this._render();
      return true;
    } catch (e) { return false; }
  }
  set panel(v) { this._panel = v; }

  // the viewer's language (profile setting first); unknown -> English
  get _t() { return String(this._hass?.locale?.language || this._hass?.language || "en").startsWith("hu") ? T.hu : T.en; }
  get _hu() { return this._t === T.hu; }

  // own font: Home Assistant's bundled Roboto under a name of its own (a phone-wide font cannot swap it); @font-face
  // does not work inside a shadow root, hence the document head
  static _fonts() {
    if (document.getElementById("hc-info-fonts")) return;
    const st = document.createElement("style");
    st.id = "hc-info-fonts";
    st.textContent = [[300, "Light"], [400, "Regular"], [500, "Medium"], [700, "Bold"]].map(([w, n]) =>
      `@font-face{font-family:"HC Info Roboto";font-style:normal;font-weight:${w};font-display:swap;src:url("/static/fonts/roboto/Roboto-${n}.woff2") format("woff2");}`).join("");
    document.head.appendChild(st);
  }

  connectedCallback() {
    HcInfoPanel._fonts();
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    this._timer = setInterval(() => this._load(), 5000);
    if (this._hass) this._start();
  }
  disconnectedCallback() { clearInterval(this._timer); }

  async _start() {
    if (this._started) return;  // set hass and connectedCallback may both start it
    this._started = true;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    try {
      this._list = await this._hass.callWS({ type: "hc_thermostat/info_list" });
    } catch (e) { this._err = String(e?.message || e); this._list = []; }
    let saved = null;
    try { saved = localStorage.getItem("hc-info:entry"); } catch (e) { /* private mode */ }
    this._sel = (this._list.find((x) => x.entry_id === saved) || this._list[0])?.entry_id;
    this._open = this._open || { decision: true, presets: true, devices_in: true, devices_out: true };
    if (await this._fromUrl()) return;
    await this._load();
  }

  async _load() {
    if (!this._hass || !this._sel) { this._render(); return; }
    try {
      this._d = await this._hass.callWS({ type: "hc_thermostat/info", entry_id: this._sel });
      this._err = null;
    } catch (e) { this._err = String(e?.message || e); }
    this._render();
  }

  // ---------------------------------------------------------------- formatting
  _num(v, dig = 1) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return this._t.none;
    return Number(v).toLocaleString(this._hu ? "hu-HU" : "en-GB", { maximumFractionDigits: dig });
  }
  _deg(v) { return v == null ? this._t.none : `${this._num(v)} °C`; }
  _val(v) {
    const t = this._t;
    if (v === true) return t.yes;
    if (v === false) return t.no;
    if (v == null) return t.none;
    if (typeof v === "number") return this._num(v, 3);
    if (typeof v === "string" && /^\d{4}-\d\d-\d\dT\d\d:\d\d/.test(v)) {
      const d = new Date(v);
      const today = new Date().toDateString() === d.toDateString();
      return today ? d.toLocaleTimeString(this._hu ? "hu-HU" : "en-GB") : d.toLocaleString(this._hu ? "hu-HU" : "en-GB");
    }
    if (Array.isArray(v)) return v.length ? v.map((x) => (typeof x === "object" ? JSON.stringify(x) : this._val(x))).join(", ") : t.none;
    if (typeof v === "object") return JSON.stringify(v);
    return String(v);
  }
  _age(s) {
    if (s == null) return "";
    return s < 90 ? `${Math.round(s)} ${this._t.sec}` : `${Math.round(s / 60)} ${this._t.min}`;
  }
  _reason(r) {
    if (!r) return this._t.none;
    return (this._hu ? REASON.hu[r] : null) || (r.charAt(0).toUpperCase() + r.slice(1).replace(/_/g, " "));
  }
  _ent(key) { return this._d?.entities?.[key] || []; }
  // ---------------------------------------------------------------- rooms (0.43.0)
  _roomKey() {
    if (this._room) return this._room;
    if (this._trv) return (this._d?.room_list || []).find((r) => (r.trvs || []).includes(this._trv))?.key || null;
    return null;
  }
  _roomData() { const k = this._roomKey(); return k ? (this._d?.room_list || []).find((r) => r.key === k) || null : null; }
  _roomRows(r) {
    const t = this._t, L = this._hu ? "hu" : "en", n = (id) => r.names?.[id] || id;
    const rows = [];
    const add = (k, v) => { if (v !== null && v !== undefined && v !== "") rows.push(`<tr><td class="k">${esc(k)}</td><td class="v">${v}</td></tr>`); };
    // 0.46.0: the room's role – leading, TRV room, or watched (heated only through the boiler)
    add(t.r_role, esc(r.leading ? t.role_lead : r.trv ? t.role_trv : t.role_watch));
    add(t.r_temp, esc(this._deg(r.temperature)));
    add(t.r_target, `<b>${esc(this._deg(r.target))}</b>`);
    add(t.r_reason, esc(ROOM_REASON[L][r.reason] || r.reason || ""));
    if (!r.leading) add(t.r_house, esc(this._deg(r.house_target)));
    if (r.trv && !r.leading) add(t.r_mode, esc(r.mode === "own" ? `${t.own}: ${this._deg(r.own?.home)} / ${this._deg(r.own?.night)} (${r.own?.night_start}–${r.own?.night_end}) / ${this._deg(r.own?.away)}`
      : `${t.follow}${r.offset ? ` ${r.offset > 0 ? "+" : ""}${r.offset} °C` : ""}`));
    if ((r.presence_sources || []).length) add(t.r_presence, `${esc(PRESENCE[L][r.presence] || r.presence || "–")}${r.absent_since ? ` · ${esc(this._val(r.absent_since))}` : ""}
      <div class="eid">${esc(r.presence_sources.map(n).join(", "))} · ${esc(r.absent_min)} ${esc(t.min)} / −${esc(r.setback)} °C</div>`);
    add(t.r_sensors, esc((r.sensors || []).map(n).join(", ") || t.none));
    if ((r.windows || []).length) add(t.r_windows, `${esc(r.windows.map(n).join(", "))}${r.window ? ` · <b>${esc(t.open_now)}</b>` : ""}
      <div class="eid">${esc(r.trv && !r.leading ? t.win_own : t.win_boiler)}</div>`);
    if ((r.trvs || []).length) add(t.r_heads, r.trvs.map((h) => {
      const v = (r.heads || {})[h] || {};
      return `<div>${esc(n(h))}: ${esc(this._deg(v.head_temp))} → ${esc(this._deg(v.head_target))} · ${this._hu ? "kalibrálás" : "calibration"} ${esc(sgn(v.calibration))} (${esc(v.sensor === "head" ? (this._hu ? "saját" : "own") : Array.isArray(v.sensor) ? v.sensor.map(n).join(" + ") : (v.sensor_name || v.sensor || ""))})${v.plan ? ` · ${esc(v.plan)}` : ""}</div>`;
    }).join(""));
    if (r.advice) add(t.r_advice, esc(r.advice.deviation == null ? `${r.advice.advice} (${r.advice.hours} h)`
      : `${r.advice.advice} (${sgn(r.advice.deviation)} °C, ${r.advice.hours} h)`));
    if (r.trv && !r.leading) add(t.r_demand, esc((r.demand_allowed ? t.yes : t.no) + (r.asking ? ` · ${t.asking_now}` : "")));
    if (r.entity_id) add(t.r_entity, `<span class="eid">${esc(r.entity_id)}</span>`);
    return `<table>${rows.join("")}</table>`;
  }
  _roomTable() {
    const t = this._t, L = this._hu ? "hu" : "en";
    return `<table>${(this._d.room_list || []).map((r) => `<tr><td class="k">${esc(r.name)}${r.leading ? " ★" : ""}</td>
      <td class="v">${esc(this._deg(r.temperature))} → <b>${esc(this._deg(r.target))}</b> · ${esc(ROOM_REASON[L][r.reason] || r.reason || "")}
      ${r.presence ? ` · ${esc(PRESENCE[L][r.presence] || r.presence)}` : ""}${(r.trvs || []).length ? ` · ${r.trvs.length} ${esc(t.trv)}` : ""}</td></tr>`).join("")}</table>`;
  }
  _st(key) {
    const e = this._ent(key)[0];
    if (!e) return null;
    const n = parseFloat(e.state);
    return { ...e, num: Number.isFinite(n) ? n : null };
  }

  // ---------------------------------------------------------------- generic tables
  _rows(obj, skip = []) {
    if (!obj || typeof obj !== "object") return `<div class="muted">${this._t.none}</div>`;
    const keys = Object.keys(obj).filter((k) => !skip.includes(k));
    if (!keys.length) return `<div class="muted">${this._t.none}</div>`;
    return `<table>${keys.map((k) => {
      const v = obj[k];
      if (v && typeof v === "object" && !Array.isArray(v) && Object.keys(v).length && Object.keys(v).length <= 40)
        return `<tr><th colspan="2" class="sub">${esc(this._key(k))}</th></tr><tr><td colspan="2" class="nest">${this._rows(v)}</td></tr>`;
      return `<tr><td class="k">${esc(this._key(k))}</td><td class="v">${esc(this._rowVal(k, v))}</td></tr>`;
    }).join("")}</table>`;
  }
  // a row label in the viewer's language (raw key when there is none)
  _key(k) { return (this._hu ? KEY_HU[k] : KEY_EN[k]) || k; }
  _rowVal(k, v) {
    if (k === "limited_by" && typeof v === "string") return LIMITED[this._hu ? "hu" : "en"][v] || v;
    if (ONOFF_KEYS.has(k) && typeof v === "boolean") return v ? this._t.on : this._t.off;
    return this._val(v);
  }
  // an entity state: on / off in the viewer's language, anything else as it is
  _state(s) { return s === "on" ? this._t.on : s === "off" ? this._t.off : s; }

  _section(id, title, body, icon) {
    const open = this._open[id];
    return `<details class="sec" data-sec="${id}" ${open ? "open" : ""}><summary><ha-icon icon="${icon}"></ha-icon>${esc(title)}</summary><div class="body">${body}</div></details>`;
  }

  _devices(out) {
    const ents = this._d?.entities || {};
    const keys = Object.keys(ents).filter((k) => OUT_KEYS.includes(k) === out);
    if (!keys.length) return `<div class="muted">${this._t.none}</div>`;
    return `<table>${keys.map((k) => ents[k].map((e, i) => `<tr><td class="k">${i ? "" : esc(this._hu ? (KEY_HU[k] || k) : k)}</td>
      <td class="v"><b>${esc(this._state(e.state) ?? "?")}${e.unit ? " " + esc(e.unit) : ""}</b>
      ${e.current_temperature != null ? ` · ${esc(this._deg(e.current_temperature))}` : ""}${e.temperature != null ? ` → ${esc(this._deg(e.temperature))}` : ""}
      ${e.hvac_action ? ` · ${esc(e.hvac_action)}` : ""}${e.percentage != null ? ` · ${esc(e.percentage)} %` : ""}
      <div class="eid">${esc(e.name)} · ${esc(e.entity_id)}</div></td></tr>`).join("")).join("")}</table>`;
  }

  _inputs() {
    const i = this._d?.inputs;
    if (!i) return `<div class="muted">${this._t.none}</div>`;
    const rows = Object.entries(i).filter(([, v]) => v != null && !(Array.isArray(v) && !v.length)).map(([k, v]) => {
      if (v && typeof v === "object" && "value" in v && "age_s" in v)
        return `<tr><td class="k">${esc(this._key(k))}</td><td class="v"><b>${esc(this._val(v.value))}</b> <span class="muted">${v.value != null ? `(${this._t.age} ${this._age(v.age_s)})` : ""}</span></td></tr>`;
      return `<tr><td class="k">${esc(this._key(k))}</td><td class="v">${esc(this._val(v))}</td></tr>`;
    });
    return `<table>${rows.join("")}</table>`;
  }

  _settings() {
    const cfg = this._d?.config;
    if (!cfg) return "";
    const used = new Set();
    const parts = GROUPS.map(([title, re]) => {
      const keys = Object.keys(cfg).filter((k) => !used.has(k) && re.test(k));
      keys.forEach((k) => used.add(k));
      if (!keys.length) return "";
      return `<div class="grp">${esc(title)}</div><table>${keys.map((k) => `<tr><td class="k">${esc(k)}</td><td class="v">${esc(this._val(cfg[k]))}</td></tr>`).join("")}</table>`;
    });
    const rest = Object.keys(cfg).filter((k) => !used.has(k));
    if (rest.length) parts.push(`<div class="grp">${esc(this._t.group_other)}</div><table>${rest.map((k) => `<tr><td class="k">${esc(k)}</td><td class="v">${esc(this._val(cfg[k]))}</td></tr>`).join("")}</table>`);
    return parts.join("");
  }

  _presets() {
    const p = this._d?.presets;
    if (!p) return "";
    const t = this._t;
    const targets = Object.entries(p.targets || {}).map(([k, v]) => `<div class="chip ${(p.current === k.replace("target_", "") || (p.current === "auto" && k === "target_home")) ? "sel" : ""}"><span>${esc(k.replace("target_", ""))}</span><b>${esc(this._deg(v))}</b></div>`).join("");
    return `<div class="kv"><span>${t.current}</span><b>${esc(p.current)}${p.boosting ? " · boost" : ""}</b></div>
      <div class="kv"><span>${t.modes}</span><b>${esc((p.modes || []).join(", "))}</b></div>
      <div class="kv"><span>${t.manual}</span><b>${esc(p.manual_target != null ? this._deg(p.manual_target) : t.none)}</b></div>
      <div class="kv"><span>${t.until}</span><b>${esc(this._val(p.preset_until))}</b></div>
      <div class="kv"><span>${t.night}</span><b>${esc((p.night || []).join("–"))}</b></div>
      <div class="chips">${targets}</div>`;
  }

  _log() {
    const log = (this._d?.log || []).slice().reverse();
    if (!log.length) return `<div class="muted">${this._t.none}</div>`;
    return `<table class="log">${log.map((e) => `<tr><td class="k">${esc(this._val(e.time))}</td><td class="v"><b>${esc(this._reason(e.reason))}</b>
      · ${esc(e.demand)} % · ${e.output ? "▲" : "▽"}<div class="eid">${esc(this._hu ? e.text_hu : e.text_en)}</div></td></tr>`).join("")}</table>`;
  }

  // ---------------------------------------------------------------- the data matrix
  _ctx() {
    const d = this._d || {};
    return { d, src: d.heat_source || "", sys: d.system || "", ctl: d.control || "", role: d.role || "standalone" };
  }
  _applies(row, c) { return row[6].every((tag) => WHEN[tag]?.(c)); }
  _fmt(v, f) {
    const t = this._t;
    if (v == null || v === "") return null;
    switch (f) {
      case "deg": return this._deg(v);
      case "pct": return `${this._num(v * 100, 0)} %`;
      case "pctv": return `${this._num(v, 0)} %`;
      case "onoff": return v ? t.on : t.off;
      case "open": return v ? t.open : (this._hu ? "zárva" : "closed");
      case "bool": return v ? t.yes : t.no;
      case "reason": return this._reason(v);
      case "mode": return v === "active" ? t.live : t.shadow;
      case "time": return this._val(v);
      case "age": return this._age(v);
      case "sec": return `${this._num(v, 0)} ${t.sec}`;
      case "min": return `${this._num(v, 1)} ${t.min}`;
      case "kw": return `${this._num(v, 2)} kW`;
      case "kwk": return `${this._num(v, 3)} kW/K`;
      case "num": return this._num(v, 3);
      case "state": return String(this._state(v));
      case "limited": return LIMITED[this._hu ? "hu" : "en"][v] || String(v);
      default: return String(v);
    }
  }
  _partRows(part) {
    const c = this._ctx();
    return INFO.filter((r) => r[1] === part && this._applies(r, c)).map((r) => {
      let v = null;
      try { v = this._fmt(r[4](c.d), r[5]); } catch (e) { v = null; }
      const hot = ["reason", "output", "relay", "in", "out", "floor_t", "ch_frac", "fan_pct", "ac_set", "heater"].includes(r[0]);
      return [this._hu ? r[2] : r[3], v, hot && v != null];
    }).filter((r) => r[1] != null);
  }
  _part(x, y, title, part, mark) { return this._card(x, y, title, this._partRows(part), "", mark, part); }

  _matrix() {
    const c = this._ctx(), t = this._t;
    const parts = { hc: t.controller, outdoor: t.outdoor, indoor: t.indoor, source: t.source, storage: t.charge, unit: t.unit,
      emitter: t.emitter, floor: t.floor, fan: t.fan };
    return `<div class="muted" style="margin-bottom:6px">${this._hu ? "Minden adatpont: melyik rajzelemhez tartozik, mikor jelenik meg (címkék), és most mennyi. Halvány = ennél a példánynál nem érvényes." : "Every data point: its part of the drawing, when it shows (tags) and its value now. Faded = not for this instance."}</div>
      <table class="mx"><tr><th>${this._hu ? "Elem" : "Part"}</th><th>${this._hu ? "Adat" : "Data"}</th><th>${this._hu ? "Feltétel" : "When"}</th><th>${this._hu ? "Érték" : "Value"}</th></tr>
      ${INFO.map((r) => {
        const ok = this._applies(r, c);
        let v = null;
        try { v = ok ? this._fmt(r[4](c.d), r[5]) : null; } catch (e) { v = null; }
        return `<tr class="${ok ? "" : "off"}"><td>${esc(parts[r[1]] || r[1])}</td><td>${esc(this._hu ? r[2] : r[3])}<div class="eid">${esc(r[0])}</div></td>
          <td>${r[6].length ? r[6].map((x) => `<span class="tag">${esc(x)}</span>`).join("") : `<span class="tag all">${this._hu ? "mindig" : "always"}</span>`}</td><td>${esc(v ?? t.none)}</td></tr>`;
      }).join("")}</table>`;
  }

  // ---------------------------------------------------------------- the drawing
  // a data card: on a wide screen laid over the drawing at (x, y) in drawing units; on a phone listed under it.
  // Each card gets a number, also drawn at `mark` (the part it belongs to) so the two can be matched.
  _card(x, y, title, rows, cls = "", mark = null, part = null) {
    const body = rows.filter((r) => r && r[1] != null && r[1] !== "").map(([k, v, hot]) =>
      `<div class="r"><span>${esc(k)}</span><b class="${hot ? "hot" : ""}">${esc(v)}</b></div>`).join("");
    if (!body) return "";
    const attr = part ? ` data-part="${esc(part)}"` : "";
    if (this._houseMode) return `<div class="card ${cls}"${attr}><div class="ct">${esc(title)}</div>${body}</div>`;  // 0.44.0: no numbers
    const n = ++this._n;
    this._marks.push([n, mark || this._nextMark || [x + 12, y + 12]]);
    this._nextMark = null;
    return `<div class="card ${cls}"${attr}><div class="ct"><i class="no">${n}</i>${esc(title)}</div>${body}</div>`;
  }
  _markSvg() {
    return this._marks.map(([n, [x, y]]) => `<g class="num"><circle cx="${x}" cy="${y}" r="17"/><text x="${x}" y="${y + 6}">${n}</text></g>`).join("");
  }

  _drawing() {
    this._n = 0; this._marks = []; this._houseMode = false;
    // drawing units: viewBox 0 0 1000 700; the cards are placed in the same units (see _card)
    const d = this._d;
    if (!d) return { svg: "", cards: "" };
    if (d.role === "central") return this._drawCentral();
    if (d.role === "buffer") return this._drawBuffer();
    // 0.44.0: the house view draws it (see _houseView); the data cards stay, each one the target of a hotspot
    this._houseMode = true;
    const t = this._t, src = d.heat_source, sys = d.system || "", L = this._hu ? "hu" : "en";
    const efloor = src === "electric_heater" && sys.startsWith("floor");
    const roomUnit = !efloor && (sys === "room_unit" || ["air_conditioner", "electric_heater", "storage_heater"].includes(src));
    const floor = sys.startsWith("floor") || sys.startsWith("mixed");
    const fan = sys === "fan_coil";
    const cards = [this._part(0, 0, t.outdoor, "outdoor"), this._part(0, 0, t.controller, "hc"), this._part(0, 0, t.indoor, "indoor")];
    if (roomUnit) {
      if (src === "air_conditioner") cards.push(this._part(0, 0, t.outdoor_unit, "source"));
      if (src === "storage_heater") cards.push(this._part(0, 0, t.charge, "storage"));
      cards.push(this._part(0, 0, src === "air_conditioner" ? t.unit : (SOURCE[L][src] || src), "unit"));
    } else {
      cards.push(this._part(0, 0, `${t.source}: ${SOURCE[L][src] || src || ""}`, "source"));
      if (fan) cards.push(this._part(0, 0, t.fan, "fan"));
      else if (floor || efloor) cards.push(this._part(0, 0, `${t.floor}${efloor ? (this._hu ? " (elektromos)" : " (electric)") : ""}`, "floor"));
    }
    cards.push(this._part(0, 0, `${t.emitter}: ${SYSTEM[L][sys] || sys}`, "emitter"));
    return { house: true, svg: "", cards: cards.join("") };
  }

  // ---------------------------------------------------------------- the house view (0.44.0)
  _houseEl() {
    if (this._house) return this._house;
    const el = document.createElement("hc-house-view");
    el.addEventListener("hc-house-select", (e) => this._pickPart(e.detail?.key));
    this._house = el;
    this._theme();
    return el;
  }
  _theme() {
    const dark = this._hass?.themes?.darkMode;
    if (typeof dark !== "boolean" || !this._house) return;
    this._house.toggleAttribute("dark", dark);
    this._house.toggleAttribute("light", !dark);
  }
  // entity -> area: the backend's list, else the entity's own area or its device's (hass.entities / hass.devices)
  _entityAreas(d) {
    const out = { ...(d.entity_areas || {}) }, ents = this._hass?.entities || {}, devs = this._hass?.devices || {};
    const ids = [...Object.values(d.entities || {}).flat().map((e) => e.entity_id), ...(d.room_list || []).flatMap((r) => [...(r.sensors || []), ...(r.trvs || [])])];
    for (const id of ids) {
      if (!id || out[id]) continue;
      const e = ents[id], a = e?.area_id || (e?.device_id ? devs[e.device_id]?.area_id : null);
      if (a) out[id] = a;
    }
    return out;
  }
  _houseUpdate() {
    const el = this._house, d = this._d;
    if (!el || !d) return;
    const areas = (d.areas || []).length ? d.areas : Object.values(this._hass?.areas || {}).map((a) => ({ area_id: a.area_id, name: a.name, floor_id: a.floor_id ?? null, icon: a.icon ?? null }));
    const floors = (d.floors || []).length ? d.floors : Object.values(this._hass?.floors || {}).map((f) => ({ floor_id: f.floor_id, name: f.name, level: f.level ?? 0 }));
    const lang = this._hu ? "hu" : "en";
    el.setAttribute("lang", lang);
    el.extras = { areas, floors, entityAreas: this._entityAreas(d), sun: d.sun?.state ?? this._hass?.states?.["sun.sun"]?.state ?? null, lang };
    el.info = d;
    el.selected = this._selKey || null;
  }
  // a click on the drawing: the matching data card (a room or a head: the room's own card), scrolled into view
  _pickPart(key) {
    if (!key || !this._d) return;
    const d = this._d, list = d.room_list || [];
    let target = null;
    this._selKey = key;
    if (key.startsWith("trv:")) {
      const head = key.slice(4), room = list.find((r) => (r.trvs || []).includes(head));
      if (room) { this._trv = head; this._room = room.key; this._open.room = true; target = '[data-sec="room"]'; }
      else target = '[data-part="emitter"]';
    } else if (key.startsWith("room:")) {
      const k = key.slice(5), room = list.find((r) => r.key === k);
      const zoneRoom = !room && this._house?.model?.rooms?.find((r) => r.key === k)?.zone;
      if (room && room.leading) { this._room = null; this._trv = null; target = '[data-part="indoor"]'; }
      else if (room) { this._room = room.key; this._trv = null; this._open.room = true; target = '[data-sec="room"]'; }
      else if (zoneRoom && d.zone && Object.keys(d.zone).length) { this._open.zone = true; target = '[data-sec="zone"]'; }
      else if (!list.length && this._house?.model?.rooms?.find((r) => r.key === k)?.leading) target = '[data-part="indoor"]';
      else if (d.rooms && (d.rooms.advice?.length || Object.keys(d.rooms.trv || {}).length)) { this._open.rooms = true; target = '[data-sec="rooms"]'; }
      else target = '[data-part="emitter"]';
    } else {
      this._room = null; this._trv = null;
      target = { outdoor: '[data-part="outdoor"]', hc: '[data-part="hc"]', source: '[data-part="source"],[data-part="unit"],[data-part="storage"]',
        gas: '[data-part="source"],[data-part="unit"]' }[key] || null;
    }
    this._render();
    const el = target && this.shadowRoot.querySelector(target);
    if (el) {
      if (el.tagName === "DETAILS") el.open = true;
      const motion = !window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      el.scrollIntoView({ behavior: motion ? "smooth" : "auto", block: "nearest" });
      el.classList.add("flash");
      setTimeout(() => el.classList.remove("flash"), 1600);
    }
  }

  _drawCentral() {
    this._n = 0; this._marks = [];
    const d = this._d, t = this._t, dec = d.decision || {}, zones = d.zones || [];
    const svg = [], cards = [];
    svg.push(`<g class="dev ${dec.output ? "on" : ""}"><rect x="60" y="250" width="180" height="200" rx="10"/><path class="lang ${dec.output ? "eg" : ""}" d="M140,400 c-6,-18 18,-26 10,-46 c18,10 24,28 16,46 z"/></g>`);
    this._nextMark = [62, 252];
    cards.push(this._card(20, 20, t.boiler, [[t.reason, this._reason(dec.reason), true], [t.output, dec.output ? t.on : t.off, dec.output],
      [t.pump, dec.pump ? t.on : t.off], [t.pump_ex, dec.details?.pump_exercise ? `${t.on} → ${this._val(dec.details.pump_exercise_until)}` : null, true],
      [t.pump_next, d.state?.pump_exercise_next ? this._val(d.state.pump_exercise_next) : null], [t.pump_last, d.state?.pump_last_run ? this._val(d.state.pump_last_run) : null],
      [t.flow, dec.flow_setpoint != null ? this._deg(dec.flow_setpoint) : null],
      ["flow by", dec.details?.flow_by], [t.demand, this._num(dec.demand, 2)], ["stuck", (dec.details?.stuck || []).join(", ") || null, true]]));
    const n = Math.max(zones.length, 1);
    zones.forEach((z, i) => {
      const y = 120 + (i * 420) / n;
      svg.push(`<path class="cso" stroke="#e53935" d="M240,300 L420,300 L420,${y + 30} L640,${y + 30}"/><g class="dev ${z.wants_heat ? "on" : ""}"><rect x="640" y="${y}" width="140" height="60" rx="8"/></g>
        <circle cx="600" cy="${y + 30}" r="12" class="${z.valve_open ? "nyit" : "zar"}"/>`);
      this._nextMark = [782, y + 2];
      cards.push(this._card(800, Math.min(600, 20 + (i * 620) / n), z.name, [["asking", z.wants_heat ? t.yes : t.no, z.wants_heat],
        [t.demand, `${this._num((z.demand || 0) * 100, 0)} %`], ["valve", z.valve_open == null ? (z.valve_on_since ? "opening" : t.none) : (z.valve_open ? t.open : "zárva")],
        [t.flow, z.flow_request != null ? this._deg(z.flow_request) : null], ["fault", z.fault ? t.yes : null, true], ["TRV", z.trv ? t.yes : null]]));
    });
    return { svg: svg.join(""), cards: cards.join("") };
  }

  _drawBuffer() {
    this._n = 0; this._marks = [];
    const d = this._d, t = this._t, dec = d.decision || {}, cfg = d.config || {};
    const svg = [], cards = [];
    const top = dec.top, bot = dec.bottom, hi = cfg.buffer_off || 65, lo = cfg.buffer_on || 45;
    const fill = Math.max(0, Math.min(1, ((bot ?? top ?? 0) - 20) / (hi - 20)));
    svg.push(`<g class="dev ${dec.output ? "on" : ""}"><rect x="60" y="280" width="180" height="200" rx="10"/><path class="lang ${dec.output ? "eg" : ""}" d="M140,430 c-6,-18 18,-26 10,-46 c18,10 24,28 16,46 z"/></g>
      <path class="cso" stroke="#e53935" d="M240,320 H420"/><path class="cso" stroke="#1e88e5" d="M420,460 H240"/>
      <defs><linearGradient id="tank" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#1e88e5"/><stop offset="1" stop-color="#e53935"/></linearGradient></defs>
      <clipPath id="tankclip"><rect x="420" y="120" width="160" height="400" rx="70"/></clipPath>
      <rect x="420" y="${120 + 400 * (1 - fill)}" width="160" height="${400 * fill}" fill="url(#tank)" opacity=".35" clip-path="url(#tankclip)"/>
      <g class="dev"><rect x="420" y="120" width="160" height="400" rx="70"/></g>
      <path class="cso" stroke="#e53935" d="M580,170 H760"/><path class="cso" stroke="#1e88e5" d="M760,470 H580"/>
      <g class="dev"><rect x="760" y="150" width="160" height="340" rx="12"/></g>`);
    this._nextMark = [62, 282];
    cards.push(this._card(20, 20, t.source, [[t.reason, this._reason(dec.reason), true], [t.output, dec.output ? t.on : t.off, dec.output],
      ["entity", this._st("boiler_entity")?.entity_id], ["state", this._state(this._st("boiler_entity")?.state)]]));
    this._nextMark = [578, 128];
    cards.push(this._card(400, 545, t.tank, [[t.top, this._deg(top), true], [t.bottom, this._deg(bot)], ["start ≤", this._deg(lo)], ["stop ≥", this._deg(hi)],
      ["frost", this._deg(cfg.buffer_frost)], ["demand-led", cfg.buffer_demand_led ? t.yes : t.no]]));
    this._nextMark = [918, 152];
    cards.push(this._card(780, 20, t.zones, (this._ent("zone_entities")).map((z) => [z.name, `${z.hvac_action || z.state}${z.current_temperature != null ? " · " + this._deg(z.current_temperature) : ""}`, z.hvac_action === "heating"])));
    return { svg: svg.join(""), cards: cards.join("") };
  }

  // ---------------------------------------------------------------- page
  _render() {
    if (!this.shadowRoot) return;
    const t = this._t, d = this._d;
    PANEL_LANG = this._hu ? "hu" : "en";
    const list = this._list || [];
    const pick = list.map((e) => `<button class="pick ${e.entry_id === this._sel && !this._trv && !this._room ? "sel" : ""}" data-entry="${esc(e.entry_id)}">
      <b>${esc(e.title)}</b><small>${esc((SOURCE[this._hu ? "hu" : "en"][e.heat_source] || e.role || "") + (e.mode === "active" ? " · " + t.live : " · " + t.shadow))}</small></button>`
      + (e.trvs || []).map((h) => `<button class="pick trvpick ${e.entry_id === this._sel && this._trv === h.entity_id ? "sel" : ""}" data-entry="${esc(e.entry_id)}" data-trv="${esc(h.entity_id)}">
      <b>${esc(h.name)} → ${esc(e.title)}</b><small>${esc(t.trvHead)}</small></button>`).join("")
      + (e.rooms || []).map((r) => `<button class="pick roompick ${e.entry_id === this._sel && this._room === r.key && !this._trv ? "sel" : ""}" data-entry="${esc(e.entry_id)}" data-room="${esc(r.key)}">
      <b>${esc(r.name)} → ${esc(e.title)}</b><small>${esc(r.trv ? t.roomTrv : t.roomBoiler)}</small></button>`).join("")).join("");
    let main = "";
    if (!list.length) main = `<div class="empty">${esc(this._err || t.noinst)}</div>`;
    else if (d) {
      const dr = this._drawing();
      const dec = d.decision || {};
      const head = `<div class="head"><h2>${esc(d.title)}</h2><span>${esc(SOURCE[this._hu ? "hu" : "en"][d.heat_source] || d.role)} · ${esc(SYSTEM[this._hu ? "hu" : "en"][d.system] || d.system || "")} · ${esc(CONTROL[d.control] || d.control || d.role)}</span>
        <span class="badge ${d.mode === "active" ? "live" : ""}">${d.mode === "active" ? t.live : t.shadow}</span>
        ${this._roomKey() ? `<span class="badge room">${esc(t.room)}: ${esc(this._roomData()?.name || this._roomKey())}</span>` : ""}
        ${this._trv ? `<span class="badge">${esc(t.trv)}: ${esc(((list.find((x) => x.entry_id === d.entry_id) || {}).trvs || []).find((h) => h.entity_id === this._trv)?.name || this._trv)} · ${esc(trvSources(d).find((x) => x.startsWith((ENTS(d, "room_trvs") || []).find((e) => e.entity_id === this._trv)?.name + ":"))?.split(": ").slice(1).join(": ") || "")}</span>` : ""}</div>`;
      const decision = d.role === "standalone" || d.role === "zone"
        ? `<div class="reason">${esc(this._reason(dec.reason))}</div><div class="txt">${esc(this._hu ? d.text_hu : d.text_en)}</div>
          <div class="bar"><i style="width:${Math.round((dec.demand || 0) * 100)}%"></i></div>
          ${this._rows({ output: dec.output, actual: d.actual, limited_by: dec.limited_by, fault: dec.fault, manual: dec.manual, manual_until: dec.manual_until, target: dec.target, indoor: dec.indoor, outdoor: dec.outdoor, flow_setpoint: dec.flow_setpoint, external: dec.external, loss_kw_per_k: dec.loss_kw_per_k, heat_need_kw: dec.heat_need_kw, other_heat_kw: dec.other_heat_kw })}
          ${dec.details && Object.keys(dec.details).length ? `<div class="grp">${esc(this._key("details"))}</div>${this._rows(dec.details)}` : ""}
          ${dec.shadow ? `<div class="grp">${esc(this._key("shadow"))}</div>${this._rows(dec.shadow)}` : ""}`
        : this._rows(dec);
      const rd = this._roomData();
      const side = [
        rd ? this._section("room", `${t.room}: ${rd.name}`, this._roomRows(rd), "mdi:door-open") : "",
        this._section("decision", t.decision, decision, "mdi:head-cog-outline"),
        d.presets ? this._section("presets", t.presets, this._presets(), "mdi:calendar-clock") : "",
        this._section("devices_in", t.devices_in, this._devices(false), "mdi:thermometer-lines"),
        this._section("devices_out", t.devices_out, this._devices(true), "mdi:electric-switch"),
        d.inputs ? this._section("inputs", t.inputs, this._inputs(), "mdi:import") : "",
        this._section("inner", t.inner, d.state ? this._rows({ ...(d.live || {}), ...d.state }) : this._rows({ state: d.state, zones: d.zones }), "mdi:memory"),
        d.health ? this._section("health", t.health, this._rows(d.health), "mdi:heart-pulse") : "",
        (d.room_list || []).length ? this._section("room_list", t.roomList, this._roomTable(), "mdi:home-group") : "",
        d.rooms && (d.rooms.advice?.length || Object.keys(d.rooms.trv || {}).length) ? this._section("rooms", t.rooms, this._rows(d.rooms), "mdi:floor-plan") : "",
        d.zone && Object.keys(d.zone).length ? this._section("zone", t.zone, this._rows(d.zone), "mdi:texture-box") : "",
        d.cost ? this._section("cost", t.cost, this._rows(d.cost), "mdi:cash") : "",
        d.role === "standalone" || d.role === "zone" ? this._section("matrix", this._hu ? "Adat-mátrix" : "Data matrix", this._matrix(), "mdi:table") : "",
        this._section("settings", t.settings, d.role === "standalone" || d.role === "zone" ? this._settings() : this._rows(d.config), "mdi:tune"),
        d.log ? this._section("log", t.log, this._log(), "mdi:history") : "",
      ].join("");
      const pic = dr.house ? `<div class="houseslot"></div>` : `<svg viewBox="0 0 1000 700">${dr.svg}${this._markSvg()}</svg>`;
      main = `${head}<div class="grid"><div class="draw"><div class="stage">${pic}<div class="cards">${dr.cards}</div></div></div>
        <div class="side">${side}</div></div>`;
    } else main = `<div class="empty">${esc(this._err || "…")}</div>`;

    const scroll = this.shadowRoot.querySelector(".side")?.scrollTop || 0;
    const pickScroll = this.shadowRoot.querySelector(".picks")?.scrollLeft || 0;
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <div class="top"><ha-icon icon="mdi:information-outline"></ha-icon><h1>${t.title}</h1><div class="picks">${pick}</div><span class="muted">${t.refresh}</span></div>
      <div class="main">${main}</div>`;
    const slot = this.shadowRoot.querySelector(".houseslot");
    if (slot) { slot.appendChild(this._houseEl()); this._houseUpdate(); }  // one element kept across refreshes
    const side = this.shadowRoot.querySelector(".side");
    if (side) side.scrollTop = scroll;
    const picks = this.shadowRoot.querySelector(".picks"), selPick = this.shadowRoot.querySelector(".pick.sel");
    if (picks) picks.scrollLeft = pickScroll;  // the refresh keeps the picker where it was
    if (this._scrollPick && picks && selPick) {  // opened by a URL: show the chosen instance (or TRV head)
      this._scrollPick = false;
      picks.scrollLeft = selPick.offsetLeft - picks.offsetLeft - 8;
    }
    this.shadowRoot.querySelectorAll("[data-entry]").forEach((b) => b.addEventListener("click", () => {
      this._sel = b.dataset.entry; this._trv = b.dataset.trv || null; this._room = b.dataset.room || null; this._d = null;
      this._selKey = this._trv ? `trv:${this._trv}` : this._room ? `room:${this._room}` : null;
      if (this._room || this._trv) this._open.room = true;
      try { localStorage.setItem("hc-info:entry", this._sel); } catch (e) { /* private mode */ }
      this._load();
    }));
    this.shadowRoot.querySelectorAll("details[data-sec]").forEach((el) => el.addEventListener("toggle", () => { this._open[el.dataset.sec] = el.open; }));
  }
}

const CSS = `
:host { display:block; height:100%; background:var(--primary-background-color); color:var(--primary-text-color); font-family:"HC Info Roboto", Roboto, "Segoe UI", "Helvetica Neue", Arial, sans-serif; }
svg text { font-family:"HC Info Roboto", Roboto, Arial, sans-serif; }
table.mx td { font-size:12px; } table.mx th { text-align:left; font-weight:500; padding:3px 4px; border-bottom:2px solid var(--divider-color); }
table.mx tr.off td { opacity:.38; }
.tag { display:inline-block; border-radius:6px; padding:0 5px; margin:1px 2px 1px 0; font-size:11px; background:color-mix(in srgb, var(--primary-color) 15%, transparent); }
.tag.all { background:var(--secondary-background-color); }
.top { display:flex; align-items:center; gap:12px; padding:10px 16px; background:var(--app-header-background-color, var(--primary-color)); color:var(--app-header-text-color, #fff); flex-wrap:nowrap; }
.top h1 { font-size:20px; margin:0 8px 0 0; font-weight:500; }
.top .muted { color:inherit; opacity:.7; margin-left:auto; font-size:12px; }
.picks { display:flex; gap:6px; flex-wrap:nowrap; overflow-x:auto; min-width:0; flex:1; scrollbar-width:thin; }
.pick { flex:none; }
.top h1 { flex:none; } .top .muted { flex:none; }
.pick { border:1px solid rgba(255,255,255,.4); background:transparent; color:inherit; border-radius:10px; padding:4px 10px; cursor:pointer; text-align:left; }
.pick small { display:block; opacity:.75; font-size:11px; }
.pick.sel { background:rgba(255,255,255,.22); border-color:#fff; }
.pick.trvpick { border-style:dashed; }
.pick.roompick { border-style:dotted; }
.badge.room { background:color-mix(in srgb, var(--primary-color) 22%, transparent); }
.main { height:calc(100vh - 64px); box-sizing:border-box; padding:10px 14px; display:flex; flex-direction:column; }
.head { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-bottom:6px; }
.head h2 { margin:0; font-size:22px; font-weight:500; }
.head span { color:var(--secondary-text-color); }
.badge { border-radius:8px; padding:1px 8px; font-size:12px; background:var(--secondary-background-color); }
.badge.live { background:#2e7d32; color:#fff; }
.grid { flex:1; min-height:0; display:grid; grid-template-columns:minmax(0,2.3fr) minmax(360px,1fr); gap:14px; }
/* the drawing alone on top (numbered parts), the numbered data cards listed under it – nothing overlaps */
.draw { position:relative; min-height:0; background:var(--card-background-color); border-radius:16px; overflow:auto; padding:10px 12px; box-sizing:border-box; }
.stage { position:relative; }
.houseslot { display:block; width:100%; }
.houseslot hc-house-view { display:block; width:100%; }
.card.flash, details.sec.flash { outline:2px solid var(--primary-color); outline-offset:2px; transition:outline-color .3s; }
@media (prefers-reduced-motion: reduce) { .card.flash, details.sec.flash { transition:none; } }
.stage svg { display:block; width:100%; max-height:52vh; height:auto; margin:0 auto; overflow:visible; }
svg .jel { fill:none; stroke:var(--primary-color); stroke-width:2.5; stroke-dasharray:6 7; opacity:.6; }
svg .jel.akt { opacity:1; animation:folyik 1s linear infinite; }
svg .mid { text-anchor:middle; font-size:14px; fill:var(--secondary-text-color); font-weight:400; }
svg .ventil { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:2.2; }
svg .tolcser { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:3; }
.side { overflow:auto; min-height:0; padding-right:4px; }
svg .dev rect, svg .dev path:not(.vek):not(.bolt), svg .hc rect { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:3; opacity:.9; }
svg .dev.on rect { fill:color-mix(in srgb, #ff8100 12%, var(--card-background-color)); }
svg .vek { fill:none; stroke:var(--primary-text-color); stroke-width:2.2; opacity:.7; stroke-linecap:round; }
svg .hc rect { stroke:var(--primary-color); stroke-width:3.5; }
svg .hc text { fill:var(--primary-text-color); text-anchor:middle; }
svg .big { font-size:28px; font-weight:700; } svg .sm { font-size:14px; opacity:.75; }
svg .lab { font-size:16px; font-weight:600; }
svg .sens circle { fill:var(--card-background-color); stroke:var(--primary-text-color); stroke-width:2.5; }
svg .sens path { stroke:var(--primary-text-color); stroke-width:5; stroke-linecap:round; }
svg .sens .bulb { fill:#e53935; stroke:none; }
svg .cso { fill:none; stroke-width:7; stroke-linecap:round; stroke-linejoin:round; opacity:.45; }
svg .cso.viz { stroke-dasharray:8 14; opacity:1; animation:folyik 1s linear infinite; }
svg .cso.kabel { stroke-dasharray:none; stroke-width:4; opacity:.8; }
@keyframes folyik { to { stroke-dashoffset:-22; } }
svg .lang { fill:#ff8100; opacity:.15; }
svg .lang.eg { opacity:1; transform-box:fill-box; transform-origin:50% 100%; animation:lobog 1.1s ease-in-out infinite alternate; }
@keyframes lobog { from { transform:scaleY(.85); } to { transform:scaleY(1.12); } }
svg .bolt { fill:#f2a20c; stroke:none; }
svg .padlo { fill:color-mix(in srgb, var(--primary-text-color) 6%, transparent); stroke:var(--primary-text-color); stroke-width:2; opacity:.7; }
svg .forog { transform-box:fill-box; transform-origin:50% 50%; animation:forog 1.2s linear infinite; }
@keyframes forog { to { transform:rotate(360deg); } }
svg .nyit { fill:#43a047; } svg .zar { fill:#9e9e9e; }
.card { position:static !important; box-sizing:border-box; display:block; width:100%; break-inside:avoid; margin:0; background:var(--card-background-color); border:1px solid var(--divider-color); border-radius:10px; padding:7px 10px; font-size:13px; }
.card .ct { font-weight:600; font-size:1.08em; margin-bottom:3px; color:var(--primary-color); }
.card .r { display:flex; justify-content:space-between; gap:8px; line-height:1.45; }
.card .r span { color:var(--secondary-text-color); }
.card .r b { font-weight:500; text-align:right; word-break:break-word; }
.hot { color:#ff8100; }
details.sec { background:var(--card-background-color); border-radius:12px; margin-bottom:8px; }
details.sec summary { cursor:pointer; padding:10px 12px; font-weight:500; display:flex; gap:8px; align-items:center; }
details.sec .body { padding:0 12px 10px; font-size:13px; }
table { width:100%; border-collapse:collapse; }
td { padding:3px 4px; vertical-align:top; border-bottom:1px solid var(--divider-color); }
td.k { color:var(--secondary-text-color); width:42%; word-break:break-word; }
td.v { word-break:break-word; }
td.nest { padding-left:12px; }
th.sub { text-align:left; padding-top:6px; font-weight:500; color:var(--primary-color); }
.eid { color:var(--secondary-text-color); font-size:11px; }
.grp { margin:10px 0 4px; font-weight:600; color:var(--primary-color); }
.reason { font-size:20px; font-weight:600; }
.txt { margin:4px 0 8px; }
.bar { height:8px; border-radius:4px; background:var(--divider-color); overflow:hidden; margin-bottom:8px; }
.bar i { display:block; height:100%; background:#ff8100; }
.kv { display:flex; justify-content:space-between; padding:3px 0; border-bottom:1px solid var(--divider-color); }
.kv span { color:var(--secondary-text-color); }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.chip { border:1px solid var(--divider-color); border-radius:10px; padding:4px 8px; display:flex; flex-direction:column; min-width:70px; }
.chip span { font-size:11px; color:var(--secondary-text-color); }
.chip.sel { border-color:var(--primary-color); background:color-mix(in srgb, var(--primary-color) 12%, transparent); }
.muted { color:var(--secondary-text-color); }
.empty { padding:40px; text-align:center; color:var(--secondary-text-color); }
table.log td.k { width:28%; }
.cards { display:grid; grid-template-columns:repeat(auto-fill, minmax(215px, 1fr)); gap:10px; align-items:start; margin-top:12px; }
.card .no { display:inline-flex; align-items:center; justify-content:center; width:1.5em; height:1.5em; border-radius:50%;
  background:var(--primary-color); color:var(--text-primary-color, #fff); font-style:normal; font-size:.8em; margin-right:5px; vertical-align:1px; }
svg .num circle { fill:var(--primary-color); }
svg .num text { fill:var(--text-primary-color, #fff); font-size:19px; font-weight:700; text-anchor:middle; }
/* phone / narrow: the drawing alone at full width, the cards listed under it (no overlap) */
@media (max-width: 1000px) {
  .main { height:auto; padding:8px; }
  .grid { grid-template-columns:1fr; gap:10px; }
  .draw { padding:6px; overflow:visible; }
  .stage svg { max-height:none; }
  .cards { display:block; columns:2 165px; column-gap:8px; margin-top:8px; }
  .card { display:inline-block; margin:0 0 8px; }
  svg .lab { font-size:30px; } svg .mid { font-size:28px; } svg .sm { font-size:24px; } svg .big { font-size:40px; }
  svg .num circle { r:27px; } svg .num text { font-size:30px; }
  .side { overflow:visible; }
  .top { padding:8px 10px; }
  .picks { width:100%; overflow-x:auto; flex-wrap:nowrap; }
  .pick { flex:none; }
  .top .muted { display:none; }
}
`;

customElements.define("hc-info-panel", HcInfoPanel);

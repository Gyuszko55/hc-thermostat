/* HC Thermostat – setup wizard (sidebar panel "HC setup").
 * Six steps: what to set up → heat source → system and control (with the matrix) → devices → worked-out
 * settings (each with its reason, editable) → summary and save. New instances always start in shadow mode.
 * Talks to the integration through hc_thermostat/wizard/{start,derive,rooms,apply}. 0.43.0: the "Rooms" card (single zone
 * TPI / PID): per room thermometers, TRV heads, leading room, target, presence, boiler demand.
 */
const T = {
  hu: {
    title: "HC beállítás", steps: ["Mit állítunk be?", "Hőforrás", "Rendszer és szabályozás", "Eszközök", "Kiszámolt beállítások", "Összefoglaló"],
    new_inst: "Új HC-példány", new_hint: "Új termosztát felvétele. Árnyék módban indul: számol, de nem kapcsol, amíg élesre nem állítod.",
    existing: "Meglévő példány átállítása", mode: { shadow: "árnyék", active: "éles" },
    back: "Vissza", next: "Tovább", save: "Mentés", saving: "Mentés…", again: "Új beállítás",
    sources: {
      onoff_boiler: ["Be/ki kazán (relé)", "Gázkazán helyiségtermosztát-bemenettel; a HC a relén kapcsolja."],
      modulating_boiler: ["Moduláló kazán", "OpenTherm / eBUS: előremenő hőfok állítható (fűtési görbe)."],
      heat_pump: ["Hőszivattyú (levegő–víz)", "Hosszú, egyenletes futás, alacsony előremenő."],
      electric_boiler: ["Elektromos kazán", "Vizes rendszer, mágneskapcsolóval vagy relével; a HC kapcsolja."],
      air_conditioner: ["Klíma (levegő–levegő)", "Fűt és hűt; a HC a célját tolja a helyiséghőmérő szerint."],
      electric_heater: ["Elektromos fűtő", "Konvektor, olajradiátor, infrapanel: relén, okosdugaljon vagy wifis saját termosztáttal."],
      pellet_boiler: ["Pellet kazán", "Lassan gyújt és ég ki: hosszú futásokkal kapcsolja; puffertartállyal a puffer szerep tölti."],
      district_heating: ["Távfűtés", "Lakásonkénti zónaszeleppel vagy szelepfejekkel; nincs saját kazán."],
      storage_heater: ["Hőtárolós kályha", "Vezérelt (éjszakai) árammal tölt, nappal adja le a hőt; a töltést és a kisütő ventilátort kapcsolja."],
    },
    systems: {
      radiator_single: "Radiátorok, egy kör", radiator_trv: "Radiátorok termosztátfejjel", radiator_zones: "Radiátor-zónák szeleppel",
      floor_single: "Padlófűtés, egy kör", floor_zones: "Padlófűtés zónákkal", mixed_no_circuit: "Vegyes, közös kör",
      mixed_rtl: "Vegyes, RTL-szeleppel", mixed_mixing: "Vegyes, keverőkörrel", room_unit: "Helyiség saját egységgel (klíma, elektromos fűtő)", fan_coil: "Fan-coil (vizes ventilátoros hőleadó)",
    },
    status: { recommended: "Ajánlott", possible: "Lehetséges", not_recommended: "Nem ajánlott" },
    control_title: "Szabályozás",
    controls: {
      tpi: ["TPI + PWM", "Arányos impulzusok a hiba és a hőigény szerint; a legtöbb relés kazánhoz."],
      pid: ["PID + PWM", "Integráló taggal: nem marad tartósan a cél alatt."],
      external: ["Külső termosztát", "Egy meglévő termosztátot (TRV, BT) állít; a hőt az szabályozza."],
      curve: ["Fűtési görbe (kísérleti)", "Előremenő hőfok a kinti hőmérséklet szerint, helyiségkorrekcióval."],
      ac: ["Klíma – virtuális i-Feel", "A klíma célját tolja el a helyiséghőmérő szerint; nem kapcsolgat."],
      onoff: ["On-off, hosszú futással", "A hőszivattyú termosztát-bemenetét kapcsolja: a cél alatt indul, fölötte áll le; nincs szaggatás."],
      storage: ["Hőtároló", "Éjjel a kinti napi átlag szerint tölt, az ablak végére időzítve; nappal a helyiség szerint süt ki."],
    },
    fields: {
      name: "Név", indoor_entity: "Helyiség-hőmérő (a fő hőmérő)", outdoor_entity: "Kinti hőmérő",
      actuator_entity: "Kazán reléje", external_climate: "Termosztát / klíma", flame_entity: "Égés jelzője (ha van)",
      boiler_power_entity: "Kazán áramfelvétele (W, ha van)", heat_energy_entity: "Gáz- vagy hőmennyiség-mérő (ha van)",
      flow_setpoint_entity: "Előremenő cél (number)", heat_enable_entity: "Fűtés engedélyező kapcsoló",
      window_entities: "Ablak- és ajtóérzékelők", presence_entities: "Jelenlét (személyek)", assist_climate: "Ház termosztátja, amit a klíma segít",
      floor_entity: "Padlóhőmérő (padlószenzor)", target_source_entity: "Célhő forrása (fali termosztát tekerője, ha van)",
      hp_defrost_entity: "Leolvasztás jelzője (ha van)", hp_dhw_entity: "Melegvíz-készítés jelzője (ha van)",
      power_available_entity: "Vezérelt áram jelzése (ha van)", discharge_entity: "Kisütő ventilátor / csappantyú (ha van)",
      fan_entity: "Fan-coil ventilátora (ha van)", coil_temp_entity: "Hőcserélő hőmérője (ha van)",
      return_temp_entity: "Visszatérő víz hőmérője (ha van)",
      demand_entity: "Vezetékes fali termosztát érintkezője (ha van; ezzel a helyiséghőmérő elhagyható)",
    },
    derived_hint: "Ezeket a választott hőforrásból, rendszerből és eszközökből számoltam. Mindegyik mellett ott az indok; bármelyik átírható.",
    rm: { title: "Helyiségek", hint: "Egy helyiség = egy hőmérő vagy hőmérő-csoport (az elérhetők átlaga), nulla vagy több szelepfej, de egy kazán. A vezető helyiség (szelepfej nélkül, általában a nappali) hőmérője vezérli a kazánt; minden más helyiség saját HC termosztátot kap. Szelepfejes helyiség: a fejek a helyiség célját kapják, a helyiség hőmérőjéhez kalibrálva. Szelepfej nélküli helyiség: csak a kazánon át fűthető, a ház célját mutatja és radiátorszelep-tanácsot kap. A sorrend (↑ ↓) a HC info házrajzáé: alsó sor először, balról jobbra, aztán felfelé.",
      add: "Helyiség hozzáadása (terület)…", custom: "Egyéni helyiség (terület nélkül)", custom_name: "Új helyiség", empty: "Még nincs helyiség.", name: "Név", no_area: "nincs terület",
      leading: "Vezető helyiség", remove: "Levesz", up: "Előrébb", down: "Hátrébb", sensors: "Hőmérők", trvs: "Szelepfejek", add_sensor: "Másik hőmérő…", add_trv: "Másik szelepfej…",
      lead_hint: "Ennek a hőmérője vezérli a kazánt (a ház célja: menetrend, presetek, háztartás-jelenlét). A HC példány termosztátja ennek a helyiségnek a termosztátja.",
      trv_hint: "Saját HC termosztát: a fejek a helyiség célját kapják.", notrv_hint: "Saját HC termosztát, de csak a kazánon át fűthető: a ház célját követi, radiátorszelep-tanácsot kap.",
      head_hint: "Fejenként: mihez kalibrálja a HC.", head_room: "A helyiség hőmérő(i) – kalibrálás", head_room_none: "A helyiség hőmérője (nincs: a fej saját mérése)", head_own: "A fej saját hőmérője – nincs kalibrálás",
      target: "Cél", follow: "A ház célját követi", own: "Saját menetrend", offset: "Eltérés a ház céljától", target_home: "Otthon", target_night: "Éjszaka", target_away: "Háztartás távol", night: "Éjszaka",
      presence: "Jelenlét", presence_hint: "Helyiség-követő (állapota a helyiség területe, pl. Bermuda) vagy mozgásérzékelő. Senki: a megadott perc után a cél csökken (a fagyhatár alá soha); háztartás távol / szabadság: a háztartás célja.",
      tracker: "helyiség-követő", no_presence: "Nincs jelenlét-forrás.", absent_min: "Távollét ennyi perc után", setback: "Csökkentés", min: "perc",
      demand: "Kérhet rövid égést a kazántól, ha messze a célja alatt van (csak ha a ház nincs a célja fölött)", demand_short: "égést kérhet",
      follows_house: "a ház célját követi", n_sensors: "hőmérő", n_trvs: "fej", rooms_line: "Helyiségek",
      warn_no_leading: "Nincs vezető helyiség kiválasztva: a kazánt a fő hőmérő vezérli, de jelöld meg, melyik helyiségben van.",
      warn_leading_trv: "A vezető helyiségben ({room}) szelepfej van: a fej és a kazán egymás ellen dolgozhat. A fej a ház célját kapja.",
      warn_indoor_trv: "A ház fő hőmérője a(z) {room} szelepfejes helyiségben van: a fej lezár, a kazán pedig a fej szerint áll le – válassz más vezető hőmérőt." },
    keys: {
      cycle_s: "Ciklusidő", min_on_s: "Minimális égés", min_off_s: "Minimális szünet", keep_alive_s: "Bekapcsolt állapot újraküldése",
      power_idle_w: "Kazán alapjárata", power_burn_w: "Kazán égése", boiler_power_kw: "Kazán teljesítménye", energy_factor: "Hő egységnyi mért mennyiségre",
      target_home: "Nappali cél", target_night: "Éjszakai cél", target_away: "Távolléti cél", target_cool: "Hűtési cél",
      night_start: "Éjszaka kezdete", night_end: "Éjszaka vége", curve_slope: "Görbe meredeksége", flow_max: "Előremenő maximum",
      flow_min: "Előremenő minimum", unit_step: "Klíma lépésköze", unit_range: "Klíma határai", ac_min_change_s: "Legritkább célváltás",
      floor_max: "Padlóhőfok-limit", hp_min_on_s: "Legrövidebb futás", hp_min_off_s: "Legrövidebb szünet", onoff_hysteresis: "Bekapcsolási hiszterézis",
      floor_temper: "Padlótemperálás", floor_temper_offset: "Padló célja a helyiség célja fölött", floor_temper_night: "Padló célja éjjel", floor_fallback: "Padló tartása hőmérő nélkül", floor_covering: "Padlóburkolat", floor_probe: "Padlószenzor helye",
    },
    summary_new: "Új példány jön létre árnyék módban: számol és naplóz, de nem kapcsol. Ha a döntései rendben vannak, élesíthető: Beállítások → Eszközök és szolgáltatások → HC Thermostat → Konfigurálás → Élesítés.",
    start_active: "Élesen indul: a HC azonnal kapcsolja a fűtést (csak ha semmi más nem vezérli ugyanazt a kimenetet)",
    start_active_on: "Élesen indul – azonnal kapcsol.", name_taken: "Már van ilyen nevű példány.",
    summary_edit: "A meglévő példány beállításai frissülnek; az üzemmódja (éles/árnyék) nem változik. A példány újratöltődik.",
    done_new: "Elkészült az új példány.", done_edit: "A példány beállításai frissültek.", open_integration: "Megnyitás a beállításokban",
    load_error: "A varázsló nem tudott adatot kérni a HC Thermostattól.", missing: "Hiányzik:", pick_need: "Válaszd ki, mit állítunk be.", source_need: "Válassz hőforrást.",
    system_need: "Válassz rendszert és vezérlést.", name_need: "Adj nevet a példánynak.",
    field_bug: "Belső hiba: ennél a kombinációnál ({combo}) nincs beviteli mező ehhez: {field}. Kérlek jelezd – addig a Beállítások → Eszközök és szolgáltatások → HC Thermostat → Integráció hozzáadása úton vehető fel.",
  },
  en: {
    title: "HC setup", steps: ["What to set up", "Heat source", "System and control", "Devices", "Worked-out settings", "Summary"],
    new_inst: "New HC instance", new_hint: "Add a thermostat. It starts in shadow mode: it calculates but switches nothing until you make it live.",
    existing: "Change an existing instance", mode: { shadow: "shadow", active: "live" },
    back: "Back", next: "Next", save: "Save", saving: "Saving…", again: "Set up another",
    sources: {
      onoff_boiler: ["On/off boiler (relay)", "Gas boiler with a room thermostat input; the HC switches its relay."],
      modulating_boiler: ["Modulating boiler", "OpenTherm / eBUS: the flow temperature can be set (heating curve)."],
      heat_pump: ["Heat pump (air to water)", "Long, even runs, low flow temperature."],
      electric_boiler: ["Electric boiler", "Water system with a contactor or relay; the HC switches it."],
      air_conditioner: ["Air conditioner (air to air)", "Heats and cools; the HC moves its setpoint by the room thermometer."],
      electric_heater: ["Electric heater", "Convector, oil radiator, infrared panel: on a relay, a smart plug or Wi-Fi with its own thermostat."],
      pellet_boiler: ["Pellet boiler", "Ignites and burns out slowly: switched with long runs; with a buffer tank the buffer role charges it."],
      district_heating: ["District heating", "With a zone valve per flat or with TRV heads; no own boiler."],
      storage_heater: ["Storage heater", "Charges on controlled (night) power, gives the heat off by day; switches the charge and the discharge fan."],
    },
    systems: {
      radiator_single: "Radiators, one loop", radiator_trv: "Radiators with TRVs", radiator_zones: "Radiator zones with valves",
      floor_single: "Floor heating, one loop", floor_zones: "Floor heating with zones", mixed_no_circuit: "Mixed, shared loop",
      mixed_rtl: "Mixed, with an RTL valve", mixed_mixing: "Mixed, with a mixing loop", room_unit: "Room with its own unit (AC, electric heater)", fan_coil: "Fan coil (water fed fan unit)",
    },
    status: { recommended: "Recommended", possible: "Possible", not_recommended: "Not recommended" },
    control_title: "Control",
    controls: {
      tpi: ["TPI + PWM", "Proportional pulses by the error and the heat need; fits most relay boilers."],
      pid: ["PID + PWM", "With an integral: does not stay below the target."],
      external: ["External thermostat", "Sets an existing thermostat (TRV, BT); that one regulates the heat."],
      curve: ["Heating curve (experimental)", "Flow temperature by the outdoor temperature, with room correction."],
      ac: ["AC – virtual i-Feel", "Moves the unit's setpoint by the room thermometer; never switches it to regulate."],
      onoff: ["On/off, long runs", "Switches the heat pump's thermostat input: on below the target, off above it; no pulsing."],
      storage: ["Storage", "Charges at night by the outdoor daily average, timed to the end of the window; discharges by day by the room."],
    },
    fields: {
      name: "Name", indoor_entity: "Room thermometer (the main one)", outdoor_entity: "Outdoor thermometer",
      actuator_entity: "Boiler relay", external_climate: "Thermostat / AC", flame_entity: "Burner signal (if any)",
      boiler_power_entity: "Boiler power draw (W, if any)", heat_energy_entity: "Gas or heat meter (if any)",
      flow_setpoint_entity: "Flow setpoint (number)", heat_enable_entity: "Heating enable switch",
      window_entities: "Window and door sensors", presence_entities: "Presence (people)", assist_climate: "House thermostat the AC helps",
      floor_entity: "Floor thermometer (floor sensor)", target_source_entity: "Target source (a wall thermostat's knob, if any)",
      hp_defrost_entity: "Defrost signal (if any)", hp_dhw_entity: "Hot water signal (if any)",
      power_available_entity: "Controlled power signal (if any)", discharge_entity: "Discharge fan / damper (if any)",
      fan_entity: "Fan coil fan (if any)", coil_temp_entity: "Coil thermometer (if any)",
      return_temp_entity: "Return water thermometer (if any)",
      demand_entity: "Wired wall thermostat contact (if any; with it the room thermometer is optional)",
    },
    derived_hint: "Worked out from the chosen heat source, system and devices. Each shows its reason; any can be changed.",
    rm: { title: "Rooms", hint: "One room = one thermometer or a group (the mean of the available ones), none or several TRV heads, but one boiler. The leading room's thermometer (no TRV head, usually the living room) runs the boiler; every other room gets its own HC thermostat. A TRV room: its heads get the room's target, calibrated to the room's thermometer. A room without a TRV: heated only through the boiler, shows the house target and gets radiator valve advice. The order (↑ ↓) is the order in the HC info house drawing: bottom row first, left to right, then upwards.",
      add: "Add a room (area)…", custom: "Custom room (no area)", custom_name: "New room", empty: "No rooms yet.", name: "Name", no_area: "no area",
      leading: "Leading room", remove: "Remove", up: "Move up", down: "Move down", sensors: "Thermometers", trvs: "TRV heads", add_sensor: "Another thermometer…", add_trv: "Another TRV head…",
      lead_hint: "Its thermometer runs the boiler (the house target: schedule, presets, household presence). The HC instance's thermostat is this room's thermostat.",
      trv_hint: "Its own HC thermostat: the heads get the room's target.", notrv_hint: "Its own HC thermostat, but heated only through the boiler: follows the house target, gets radiator valve advice.",
      head_hint: "Per head: what HC calibrates it to.", head_room: "The room's thermometer(s) – calibrated", head_room_none: "The room's thermometer (none: the head's own reading)", head_own: "The head's own thermometer – no calibration",
      target: "Target", follow: "Follows the house target", own: "Own schedule", offset: "Offset to the house target", target_home: "Home", target_night: "Night", target_away: "Household away", night: "Night",
      presence: "Presence", presence_hint: "A room tracker (its state is the room's area, e.g. Bermuda) or a motion sensor. Nobody: after the given minutes the target is set back (never below the frost limit); household away / vacation: the household target.",
      tracker: "room tracker", no_presence: "No presence source.", absent_min: "Absent after", setback: "Setback", min: "min",
      demand: "May ask the boiler for short burns when far below its target (only while the house is not above its own)", demand_short: "may ask for burns",
      follows_house: "follows the house", n_sensors: "thermometer(s)", n_trvs: "head(s)", rooms_line: "Rooms",
      warn_no_leading: "No leading room chosen: the main thermometer runs the boiler, but mark which room it is in.",
      warn_leading_trv: "The leading room ({room}) has a TRV head: the head and the boiler may work against each other. The head gets the house target.",
      warn_indoor_trv: "The house's main thermometer is in the TRV room {room}: the head closes and the boiler stops by it – choose another leading thermometer." },
    keys: {
      cycle_s: "Cycle", min_on_s: "Minimum burn", min_off_s: "Minimum pause", keep_alive_s: "Resend on every",
      power_idle_w: "Boiler idle", power_burn_w: "Boiler burning", boiler_power_kw: "Boiler output", energy_factor: "Heat per metered unit",
      target_home: "Day target", target_night: "Night target", target_away: "Away target", target_cool: "Cooling target",
      night_start: "Night from", night_end: "Night until", curve_slope: "Curve slope", flow_max: "Flow maximum",
      flow_min: "Flow minimum", unit_step: "Unit step", unit_range: "Unit limits", ac_min_change_s: "Minimum time between changes",
      floor_max: "Floor limit", hp_min_on_s: "Shortest run", hp_min_off_s: "Shortest pause", onoff_hysteresis: "Switch-on hysteresis",
      floor_temper: "Floor tempering", floor_temper_offset: "Floor target above the room target", floor_temper_night: "Floor target at night", floor_fallback: "Keep the floor without a room thermometer", floor_covering: "Floor covering", floor_probe: "Floor sensor position",
    },
    summary_new: "A new instance is created in shadow mode: it calculates and logs, but switches nothing. When its decisions look right, make it live: Settings → Devices & services → HC Thermostat → Configure → Go live.",
    start_active: "Start live: HC switches the heating at once (only when nothing else controls the same output)",
    start_active_on: "Starts live – switches at once.", name_taken: "An instance with this name exists already.",
    summary_edit: "The instance's settings are updated; its mode (live/shadow) stays. The instance reloads.",
    done_new: "The new instance is ready.", done_edit: "The instance's settings are updated.", open_integration: "Open in settings",
    load_error: "The wizard could not get data from HC Thermostat.", missing: "Missing:", pick_need: "Choose what to set up.", source_need: "Choose a heat source.",
    system_need: "Choose a system and a control.", name_need: "Give the instance a name.",
    field_bug: "Internal error: this combination ({combo}) has no input field for {field}. Please report it – until then add it under Settings → Devices & services → HC Thermostat → Add integration.",
  },
};
// 0.45.0: every name, title or server text goes into the HTML through esc()
const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SOURCE_ICON = { onoff_boiler: "mdi:fire", modulating_boiler: "mdi:fire-circle", heat_pump: "mdi:heat-pump", electric_boiler: "mdi:water-boiler",
  air_conditioner: "mdi:air-conditioner", electric_heater: "mdi:radiator", storage_heater: "mdi:heat-wave", district_heating: "mdi:city", pellet_boiler: "mdi:fire" };
const SETTING_KEYS = ["cycle_s", "min_on_s", "min_off_s", "keep_alive_s", "power_idle_w", "power_burn_w", "boiler_power_kw", "energy_factor",
  "target_home", "target_night", "target_away", "target_cool", "night_start", "night_end", "curve_slope", "flow_max", "flow_min",
  "room_tolerance", "ac_min_change_s", "floor_max", "hp_min_on_s", "hp_min_off_s", "onoff_hysteresis",
  "floor_temper", "floor_temper_offset", "floor_temper_night", "floor_fallback", "floor_covering", "floor_probe"];
const CONTROL_DEVICE = { tpi: "actuator_entity", pid: "actuator_entity", onoff: "actuator_entity", storage: "actuator_entity", external: "external_climate", ac: "external_climate", curve: "flow_setpoint_entity" };

// Small line drawings of the systems (stroke = currentColor)
const rad = (x, y, w = 34, h = 26) => {
  let s = `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="3"/>`;
  for (let i = x + 6; i < x + w - 2; i += 6) s += `<line x1="${i}" y1="${y + 4}" x2="${i}" y2="${y + h - 4}"/>`;
  return s;
};
const coil = (x, y, w = 40, n = 4) => {
  let d = `M${x},${y}`;
  for (let i = 0; i < n; i++) d += ` h${w} a4,4 0 0 1 0,8 h-${w} a4,4 0 0 0 0,8`;
  return `<path d="${d}" fill="none"/>`;
};
const valve = (x, y) => `<path d="M${x - 5},${y - 4} L${x + 5},${y + 4} L${x + 5},${y - 4} L${x - 5},${y + 4} Z"/>`;
const DRAW = {
  radiator_single: () => rad(40, 22) + `<line x1="20" y1="58" x2="100" y2="58"/>`,
  radiator_trv: () => rad(36, 22) + `<circle cx="78" cy="30" r="5"/><line x1="20" y1="58" x2="100" y2="58"/>`,
  radiator_zones: () => rad(14, 20, 30, 24) + rad(70, 20, 30, 24) + valve(29, 54) + valve(85, 54) + `<line x1="8" y1="54" x2="112" y2="54"/>`,
  floor_single: () => coil(36, 16, 48, 3) + `<line x1="20" y1="62" x2="100" y2="62"/>`,
  floor_zones: () => coil(12, 16, 36, 3) + coil(68, 16, 36, 3),
  mixed_no_circuit: () => rad(14, 18, 30, 24) + coil(66, 16, 36, 3) + `<line x1="8" y1="58" x2="112" y2="58"/>`,
  mixed_rtl: () => rad(14, 18, 30, 24) + coil(66, 16, 36, 3) + `<rect x="52" y="50" width="16" height="12" rx="2"/>`,
  mixed_mixing: () => rad(14, 18, 30, 24) + coil(66, 16, 36, 3) + valve(60, 56) + `<circle cx="60" cy="56" r="9"/>`,
  heater_unit: () => `<rect x="24" y="16" width="72" height="40" rx="5"/><path d="M34,24 v24 M46,24 v24 M58,24 v24 M70,24 v24 M82,24 v24"/><line x1="30" y1="56" x2="30" y2="62"/><line x1="90" y1="56" x2="90" y2="62"/>`,
  fan_coil: () => `<rect x="20" y="16" width="80" height="34" rx="6"/><circle cx="45" cy="33" r="10" fill="none"/><path d="M45,23 v20 M35,33 h20" /><path d="M70,26 h22 M70,33 h22 M70,40 h22"/><path d="M40,56 q5,6 0,10 M60,56 q5,6 0,10 M80,56 q5,6 0,10" fill="none"/>`,
  room_unit: () => `<rect x="20" y="18" width="80" height="24" rx="8"/><line x1="30" y1="36" x2="90" y2="36"/><path d="M40,50 q5,6 0,12 M60,50 q5,6 0,12 M80,50 q5,6 0,12" fill="none"/>`,
};

class HcWizardPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._step = 0;
    this._s = { entry_id: null, name: "", heat_source: null, system: null, control: null, entities: {}, settings: {} };
    this._derived = null;
    this._done = null;
  }
  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (this._form) this._form.hass = h;
    if (first) this._load();
  }
  get hass() { return this._hass; }
  set narrow(n) { this._narrow = n; }
  get _lang() { return this._hass?.locale?.language || this._hass?.language || "en"; }
  get _t() { return T[this._lang.startsWith("hu") ? "hu" : "en"]; }

  async _load() {
    this._render();
    try {
      this._start = await this._hass.callWS({ type: "hc_thermostat/wizard/start" });
    } catch (e) {
      this._error = this._t.load_error + " " + (e.message || "");
    }
    await this._ensureForm();
    this._render();
  }
  async _ensureForm() {
    if (customElements.get("ha-form")) return;
    try {
      const helpers = await window.loadCardHelpers();
      const card = await helpers.createCardElement({ type: "entities", entities: [] });
      await card.constructor.getConfigElement();
    } catch (e) { /* the form below waits for it anyway */ }
    await Promise.race([customElements.whenDefined("ha-form"), new Promise((r) => setTimeout(r, 4000))]);
  }

  // ---------- navigation ----------
  // Why "next" is not allowed now (null: it is). Step 3: every required field of the form must be filled – the same
  // schema that draws the form decides, so a required device can never be missing from the form unnoticed; and the
  // device the chosen control drives must be in the form at all (otherwise an internal error is shown).
  _whyNot() {
    const s = this._s, t = this._t;
    switch (this._step) {
      case 0: return null;  // 0.45.0: nothing chosen yet is no error (Next stays disabled)
      case 1: return s.heat_source ? null : t.source_need;
      case 2: return s.system && s.control ? null : t.system_need;
      case 3: {
        const sc = this._schema();
        const need = CONTROL_DEVICE[s.control];
        if (!need || !sc.some((f) => f.name === need && f.required))
          return t.field_bug.replace("{combo}", `${s.heat_source} / ${s.system} / ${s.control}`).replace("{field}", need || s.control);
        const miss = sc.filter((f) => f.required && f.name !== "name" && !(Array.isArray(s.entities[f.name]) ? s.entities[f.name].length : s.entities[f.name]))
          .map((f) => this._label(f.name));
        if (!s.entry_id && !String(s.name || "").trim()) miss.unshift(t.fields.name);
        if (miss.length) return `${t.missing} ${miss.join(", ")}`;
        if (!s.entry_id && this._nameTaken(s.name)) return t.name_taken;  // 0.45.0: said here, not lost at the save
        return null;
      }
      default: return null;
    }
  }
  _nameTaken(name) {
    const n = String(name || "").trim().toLowerCase();
    return !!n && (this._start?.entries || []).some((e) => String(e.title || "").trim().toLowerCase() === n);
  }
  _updNext() {
    const r = this.shadowRoot, why = this._whyNot();
    const next = r?.getElementById("next");
    if (next) next.disabled = !!why || !this._canNext();
    const need = r?.getElementById("need");
    if (need) need.textContent = why || "";
  }
  _label(name) { return this._over?.[name] || this._t.fields[name] || name; }
  _canNext() {
    const s = this._s;
    switch (this._step) {
      case 0: return this._picked !== undefined;
      case 1: return !!s.heat_source;
      case 2: return !!s.system && !!s.control;
      case 3: return !this._whyNot();
      default: return true;
    }
  }
  async _go(d) {
    if (d > 0 && !this._canNext()) return;
    this._step = Math.max(0, Math.min(5, this._step + d));
    if (this._step === 4 && d > 0) await this._derive();
    this._render();
    this.shadowRoot.querySelector(".body")?.scrollTo?.({ top: 0 });
  }
  async _derive() {
    const s = this._s;
    // only the devices the chosen source and control use (a field left over from an earlier choice is dropped)
    const names = new Set(this._schema().map((x) => x.name));
    s.entities = Object.fromEntries(Object.entries(s.entities).filter(([k]) => names.has(k)));
    this._derived = await this._hass.callWS({ type: "hc_thermostat/wizard/derive", heat_source: s.heat_source, system: s.system,
      control: s.control, entities: s.entities, language: this._lang });
    // only what belongs to this choice; values the user already changed are kept
    const prev = s.settings;
    s.settings = {};
    for (const it of this._derived.items) if (it.editable) s.settings[it.key] = it.key in prev ? prev[it.key] : it.value;
    if (this._trvOk()) await this._loadRooms();
  }
  // ---------- rooms (0.43.0): single zone TPI / PID – one boiler, a leading room, every other room its own ----------
  _trvOk() { return ["tpi", "pid"].includes(this._s.control); }
  async _loadRooms() {
    const s = this._s;
    try {
      this._rc = await this._hass.callWS({ type: "hc_thermostat/wizard/rooms", indoor: s.entities.indoor_entity || null });
    } catch (e) { this._error = e.message || String(e); return; }
    if (!Array.isArray(s.roomList)) {
      const e = s.entry_id ? (this._start.entries || []).find((x) => x.entry_id === s.entry_id) : null;
      if (e && (e.rooms || []).length) { s.roomList = e.rooms.map((r) => ({ ...r })); s.leading = e.leading_room || null; }
      else {
        s.roomList = (this._rc.suggest || []).map((r) => ({ ...r })); s.leading = this._rc.suggest_leading || null;
        s.roomList.sort((x, y) => (y.key === s.leading) - (x.key === s.leading));  // a first suggestion: the leading room first
      }
    }
    if (s.leading && !s.roomList.some((r) => r.key === s.leading)) s.leading = null;
  }
  _area(key) { return (this._rc?.areas || []).find((a) => a.area === key) || null; }
  _room(key) { return (this._s.roomList || []).find((r) => r.key === key); }
  _newRoom(area) {
    const s = this._s, a = this._area(area), t = this._t.rm;
    let key = area || `room_${Date.now().toString(36)}`;
    while (s.roomList.some((r) => r.key === key)) key += "_2";
    s.roomList = [...s.roomList, { key, name: a ? a.name : t.custom_name, area: a ? a.area : null,
      sensors: a ? a.sensors.filter((x) => !x.head).slice(0, 1).map((x) => x.id) : [], trvs: a ? a.trvs.map((x) => x.id).filter((h) => !this._usedHead(h)) : [],
      mode: "follow", offset: 0, presence: [], absent_min: 15, setback: 2, demand: false }];
    this._render();
  }
  _usedHead(h, except) { return (this._s.roomList || []).some((r) => r.key !== except && (r.trvs || []).includes(h)); }
  _roomWarnings() {
    const s = this._s, t = this._t.rm, out = [];
    if (!s.roomList?.length) return out;
    const lead = this._room(s.leading);
    if (!lead) out.push(t.warn_no_leading);
    else if ((lead.trvs || []).length) out.push(t.warn_leading_trv.replace("{room}", lead.name));
    const indoor = s.entities.indoor_entity;
    const inTrv = indoor && s.roomList.find((r) => r.key !== s.leading && (r.trvs || []).length
      && ((r.sensors || []).includes(indoor) || (r.area && r.area === this._rc?.suggest_leading)));
    if (inTrv) out.push(t.warn_indoor_trv.replace("{room}", inTrv.name));
    return out;
  }
  _renderRooms() {
    const t = this._t.rm, s = this._s, rc = this._rc || { areas: [], tracking: [], temperature: [], climates: [] };
    const excl = new Set(this._excluded());  // 0.45.0: heads another instance drives are not offered
    const list = s.roomList || [];  // 0.44.0: in their order (= the HC info drawing: bottom row first, left to right, upwards)
    const item = (x) => `${esc(x.name)}${x.state != null && x.state !== "" ? ` <span class="muted">(${esc(x.state)}${x.unit ? " " + esc(x.unit) : ""})</span>` : ""}`;
    const checks = (room, field, cands, chosen) => {
      const ids = new Set(cands.map((c) => c.id));
      const extra = chosen.filter((id) => !ids.has(id)).map((id) => ({ id, name: this._name(id), state: this._hass.states[id]?.state }));
      return [...cands, ...extra].map((c) => `<label class="chk"><input type="checkbox" data-rm-list="${esc(room.key)}|${field}" value="${esc(c.id)}" ${chosen.includes(c.id) ? "checked" : ""}>${item(c)}</label>`).join("");
    };
    const adder = (room, field, cands, chosen, label) => {
      const rest = cands.filter((c) => !chosen.includes(c.id) && !(field === "trvs" && (this._usedHead(c.id, room.key) || c.id === s.entities.external_climate)));
      return rest.length ? `<select data-rm-add="${esc(room.key)}|${field}" aria-label="${esc(label)}"><option value="">${esc(label)}</option>${rest.map((c) => `<option value="${esc(c.id)}">${esc(c.name)}${c.area_name ? " · " + esc(c.area_name) : ""}</option>`).join("")}</select>` : "";
    };
    const num = (room, k, v, min, max, step, unit) => `<div class="val"><span>${t[k]}</span><input type="number" min="${min}" max="${max}" step="${step}" data-rm-num="${esc(room.key)}|${k}" value="${v}"><span>${unit}</span></div>`;
    const cards = list.map((r, i) => {
      const a = this._area(r.area) || { sensors: [], trvs: [], presence: [] };
      const lead = r.key === s.leading, trv = (r.trvs || []).length > 0;
      const headSel = (h) => {
        const cur = (r.head_sensors || {})[h] || "room";
        const opts = [["room", (r.sensors || []).length ? t.head_room : t.head_room_none], ["head", t.head_own],
          ...a.sensors.filter((x) => !(r.sensors || []).includes(x.id)).map((x) => [x.id, x.name])];
        if (!opts.some(([v]) => v === cur)) opts.push([cur, this._name(cur)]);
        return `<div class="val"><span>${esc(this._name(h))}</span><select data-rm-head="${esc(r.key)}|${esc(h)}">${opts.map(([v, l]) => `<option value="${esc(v)}" ${v === cur ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>`;
      };
      const presC = [...rc.tracking.map((x) => ({ ...x, name: `${x.name} (${t.tracker})` })), ...a.presence];
      const own = r.mode === "own";
      return `<div class="room ${lead ? "lead" : ""}" data-room-key="${esc(r.key)}">
        <div class="trvtop"><input class="rname" data-rm-name="${esc(r.key)}" value="${esc(r.name)}" aria-label="${t.name}">
          <span class="muted">${esc(r.area ? (this._area(r.area)?.name || r.area) : t.no_area)}</span>
          <label class="chk"><input type="radio" name="leading" data-rm-lead="${esc(r.key)}" ${lead ? "checked" : ""}>${t.leading}</label>
          <span class="order"><button class="btn ghost small" data-rm-move="${esc(r.key)}|-1" ${i ? "" : "disabled"} title="${esc(t.up)}" aria-label="${esc(t.up)}">↑</button><button class="btn ghost small" data-rm-move="${esc(r.key)}|1" ${i < list.length - 1 ? "" : "disabled"} title="${esc(t.down)}" aria-label="${esc(t.down)}">↓</button></span>
          <button class="btn ghost small" data-rm-remove="${esc(r.key)}">${t.remove}</button></div>
        <div class="muted small">${lead ? t.lead_hint : trv ? t.trv_hint : t.notrv_hint}</div>
        <div class="sub"><b>${t.sensors}</b>${checks(r, "sensors", a.sensors, r.sensors || [])}${adder(r, "sensors", rc.temperature, r.sensors || [], t.add_sensor)}</div>
        <div class="sub"><b>${t.trvs}</b>${checks(r, "trvs", a.trvs.filter((c) => !this._usedHead(c.id, r.key) && !excl.has(c.id)), r.trvs || [])}${adder(r, "trvs", rc.climates.filter((c) => !excl.has(c.id)), r.trvs || [], t.add_trv)}
          ${trv ? `<div class="muted small">${t.head_hint}</div>${r.trvs.map(headSel).join("")}` : ""}</div>
        ${trv && !lead ? `<div class="sub"><b>${t.target}</b>
          <select data-rm-mode="${esc(r.key)}"><option value="follow" ${own ? "" : "selected"}>${t.follow}</option><option value="own" ${own ? "selected" : ""}>${t.own}</option></select>
          ${own ? num(r, "target_home", r.target_home ?? 21, 5, 30, 0.5, "°C") + num(r, "target_night", r.target_night ?? 19, 5, 30, 0.5, "°C") + num(r, "target_away", r.target_away ?? 17, 5, 30, 0.5, "°C")
            + `<div class="val"><span>${t.night}</span><input type="time" data-rm-time="${esc(r.key)}|night_start" value="${esc(r.night_start || "22:00")}"><span>–</span><input type="time" data-rm-time="${esc(r.key)}|night_end" value="${esc(r.night_end || "06:00")}"></div>`
            : num(r, "offset", r.offset ?? 0, -5, 5, 0.5, "°C")}</div>
        <div class="sub"><b>${t.presence}</b><div class="muted small">${t.presence_hint}</div>${presC.length || (r.presence || []).length ? checks(r, "presence", presC, r.presence || []) : `<span class="muted small">${t.no_presence}</span>`}
          ${(r.presence || []).length ? num(r, "absent_min", r.absent_min ?? 15, 1, 720, 1, t.min) + num(r, "setback", r.setback ?? 2, 0, 10, 0.5, "°C") : ""}</div>
        <label class="chk"><input type="checkbox" data-rm-demand="${esc(r.key)}" ${r.demand ? "checked" : ""}>${t.demand}</label>` : ""}
      </div>`;
    }).join("");
    const used = new Set(list.map((r) => r.area).filter(Boolean));
    const free = (rc.areas || []).filter((a) => !used.has(a.area));
    const warn = this._roomWarnings().map((w) => `<div class="warn">⚠ ${esc(w)}</div>`).join("");
    return `<div class="card trv rooms2"><b>${t.title}</b><p class="hint">${t.hint}</p>${warn}${cards || `<p class="muted">${t.empty}</p>`}
      <select id="rmadd" aria-label="${t.add}"><option value="">${t.add}</option>${free.map((a) => `<option value="${esc(a.area)}">${esc(a.name)}${a.sensors.length || a.trvs.length ? ` (${a.sensors.length} ${t.n_sensors}, ${a.trvs.length} ${t.n_trvs})` : ""}</option>`).join("")}<option value="__custom">${t.custom}</option></select></div>`;
  }
  _bindRooms() {
    const r = this.shadowRoot, s = this._s;
    const room = (k) => this._room(k);
    const split = (v) => { const i = v.indexOf("|"); return [v.slice(0, i), v.slice(i + 1)]; };
    r.getElementById("rmadd")?.addEventListener("change", (e) => { if (e.target.value) this._newRoom(e.target.value === "__custom" ? null : e.target.value); });
    r.querySelectorAll("[data-rm-remove]").forEach((b) => b.addEventListener("click", () => {
      s.roomList = s.roomList.filter((x) => x.key !== b.dataset.rmRemove);
      if (s.leading === b.dataset.rmRemove) s.leading = null;
      this._render();
    }));
    r.querySelectorAll("[data-rm-move]").forEach((b) => b.addEventListener("click", () => {  // 0.44.0: the room order
      const [k, d] = split(b.dataset.rmMove), i = s.roomList.findIndex((x) => x.key === k), j = i + Number(d);
      if (i < 0 || j < 0 || j >= s.roomList.length) return;
      const l = [...s.roomList];
      [l[i], l[j]] = [l[j], l[i]];
      s.roomList = l;
      this._render();
    }));
    r.querySelectorAll("[data-rm-lead]").forEach((i) => i.addEventListener("change", () => { s.leading = i.dataset.rmLead; this._render(); }));
    r.querySelectorAll("[data-rm-name]").forEach((i) => i.addEventListener("change", () => { const x = room(i.dataset.rmName); if (x && i.value.trim()) x.name = i.value.trim(); }));
    r.querySelectorAll("[data-rm-list]").forEach((i) => i.addEventListener("change", () => {
      const [k, f] = split(i.dataset.rmList), x = room(k);
      if (!x) return;
      const cur = x[f] || [];
      x[f] = i.checked ? [...new Set([...cur, i.value])] : cur.filter((v) => v !== i.value);
      if (f === "trvs" && !i.checked && x.head_sensors) delete x.head_sensors[i.value];
      if (f === "trvs" && !x.trvs.length) x.demand = false;
      this._render();
    }));
    r.querySelectorAll("[data-rm-add]").forEach((i) => i.addEventListener("change", () => {
      const [k, f] = split(i.dataset.rmAdd), x = room(k);
      if (x && i.value) { x[f] = [...new Set([...(x[f] || []), i.value])]; this._render(); }
    }));
    r.querySelectorAll("[data-rm-head]").forEach((i) => i.addEventListener("change", () => {
      const [k, h] = split(i.dataset.rmHead), x = room(k);
      if (!x) return;
      const hs = { ...(x.head_sensors || {}) };
      if (i.value === "room") delete hs[h]; else hs[h] = i.value;
      x.head_sensors = hs;
    }));
    r.querySelectorAll("[data-rm-mode]").forEach((i) => i.addEventListener("change", () => { const x = room(i.dataset.rmMode); if (x) { x.mode = i.value; this._render(); } }));
    r.querySelectorAll("[data-rm-num]").forEach((i) => i.addEventListener("change", () => {
      const [k, f] = split(i.dataset.rmNum), x = room(k), v = parseFloat(i.value);
      if (x && Number.isFinite(v)) { x[f] = Math.max(+i.min, Math.min(+i.max, v)); if (f === "absent_min" || f === "setback") return; }
    }));
    r.querySelectorAll("[data-rm-time]").forEach((i) => i.addEventListener("change", () => { const [k, f] = split(i.dataset.rmTime), x = room(k); if (x && i.value) x[f] = i.value; }));
    r.querySelectorAll("[data-rm-demand]").forEach((i) => i.addEventListener("change", () => { const x = room(i.dataset.rmDemand); if (x) x.demand = i.checked; }));
  }
  _roomsSummary() {
    const t = this._t.rm, s = this._s;
    return (s.roomList || []).map((r) => {
      const bits = [];
      if (r.key === s.leading) bits.push(t.leading);
      bits.push(`${(r.sensors || []).length} ${t.n_sensors}`);
      if ((r.trvs || []).length) {
        bits.push(`${r.trvs.length} ${t.n_trvs}`);
        if (r.key !== s.leading) bits.push(r.mode === "own" ? t.own : `${t.follow}${r.offset ? ` ${r.offset > 0 ? "+" : ""}${r.offset} °C` : ""}`);
        if ((r.presence || []).length && r.key !== s.leading) bits.push(`${t.presence}: ${r.presence.length}`);
        if (r.demand && r.key !== s.leading) bits.push(t.demand_short);
      } else if (r.key !== s.leading) bits.push(t.follows_house);
      return `${r.name} (${bits.join(", ")})`;  // plain text: line() escapes it
    }).join("; ");
  }
  async _save() {
    const s = this._s;
    this._saving = true;
    this._render();
    try {
      const ents = { ...s.entities };
      // 0.43.0: the rooms (the backend writes the legacy keys next to them)
      const rooms = this._trvOk() && Array.isArray(s.roomList) ? { rooms: s.roomList, leading_room: s.leading || null } : {};
      const res = await this._hass.callWS({ type: "hc_thermostat/wizard/apply", entry_id: s.entry_id, name: s.name,
        heat_source: s.heat_source, system: s.system, control: s.control, entities: ents, settings: s.settings, ...rooms,
        ...(s.entry_id ? {} : { start_active: !!s.start_active }) });
      this._done = res;
    } catch (e) {
      if (e?.code === "name_taken") { this._step = 3; this._error = null; this._saving = false; this._render(); return; }
      this._error = e.message || String(e);
    }
    this._saving = false;
    this._render();
  }
  _pickEntry(id) {
    this._picked = id;
    const e = (this._start.entries || []).find((x) => x.entry_id === id);
    const keys = ["indoor_entity", "outdoor_entity", "actuator_entity", "external_climate", "flame_entity", "boiler_power_entity",
      "heat_energy_entity", "flow_setpoint_entity", "heat_enable_entity", "window_entities", "presence_entities", "assist_climate",
      "floor_entity", "target_source_entity", "hp_defrost_entity", "hp_dhw_entity", "demand_entity"];
    if (e) {
      const c = e.conf || {};
      this._s = { entry_id: id, name: e.title, heat_source: e.heat_source, system: e.system, control: e.control,
        entities: Object.fromEntries(keys.filter((k) => c[k]).map((k) => [k, c[k]])),
        settings: Object.fromEntries(SETTING_KEYS.filter((k) => c[k] !== undefined && c[k] !== null).map((k) => [k, c[k]])) };
    } else {
      const sug = this._start.suggest || {};
      this._s = { entry_id: null, name: this._start.default_name || "HC Thermostat", heat_source: null, system: null, control: null,
        entities: Object.fromEntries(Object.entries(sug).filter(([, v]) => v && (!Array.isArray(v) || v.length))), settings: {} };
    }
    this._render();
  }

  // ---------- rendering ----------
  _render() {
    const t = this._t;
    const css = `
      :host { display:block; background: var(--primary-background-color); color: var(--primary-text-color); min-height:100%; }
      .bar { display:flex; align-items:center; gap:8px; height:56px; padding: 0 max(12px, env(safe-area-inset-right,0px)) 0 max(4px, env(safe-area-inset-left,0px));
        background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); font-size:20px; }
      .wrap { max-width: 960px; margin: 0 auto; padding: 20px max(16px, env(safe-area-inset-right,0px)) 40px max(16px, env(safe-area-inset-left,0px)); display:grid; gap:18px; }
      .steps { display:flex; gap:6px; flex-wrap:wrap; }
      .steps span { font-size:12px; padding:4px 10px; border-radius:12px; background: var(--secondary-background-color); color: var(--secondary-text-color); }
      .steps span.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
      .steps span.done { color: var(--primary-color); }
      h1 { margin:0; font-size:24px; font-weight:500; }
      .hint { color: var(--secondary-text-color); margin:0; max-width:70ch; }
      .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap:12px; }
      .opt { position:relative; display:grid; gap:6px; align-content:start; text-align:left; padding:16px; border-radius: var(--ha-card-border-radius, 12px);
        background: var(--card-background-color); border: 2px solid var(--divider-color); cursor:pointer; color:inherit; font:inherit; }
      .opt:hover { border-color: var(--primary-color); }
      .opt:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
      .opt.sel { border-color: var(--primary-color); box-shadow: 0 0 0 1px var(--primary-color) inset; }
      .opt.dim { opacity:.55; }
      .opt ha-icon { --mdc-icon-size: 34px; color: var(--primary-color); }
      .opt b { font-size:15px; font-weight:500; }
      .opt small { color: var(--secondary-text-color); font-size:12.5px; line-height:1.4; }
      .opt svg { width:100%; height:64px; stroke: var(--primary-color); stroke-width:2; fill:none; stroke-linecap:round; stroke-linejoin:round; }
      .badge { justify-self:start; font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; padding:2px 8px; border-radius:10px; color:#fff; }
      .badge.recommended { background: var(--success-color, #43a047); } .badge.possible { background: var(--warning-color, #ffa000); }
      .badge.not_recommended { background: var(--error-color, #db4437); }
      .mode { position:absolute; top:12px; right:12px; font-size:11px; padding:2px 8px; border-radius:10px; background: var(--secondary-background-color); }
      .card { background: var(--card-background-color); border-radius: var(--ha-card-border-radius, 12px); padding:16px; border:1px solid var(--divider-color); display:grid; gap:12px; min-width:0; }
      table { width:100%; border-collapse:collapse; } td { padding:8px 6px; border-bottom:1px solid var(--divider-color); vertical-align:top; }
      td.k { width:34%; font-weight:500; } td.why { color: var(--secondary-text-color); font-size:12.5px; }
      .val { display:flex; align-items:center; gap:6px; }
      select { padding:6px 8px; border-radius:6px; border:1px solid var(--divider-color); background: var(--primary-background-color); color: var(--primary-text-color); font:inherit; max-width:100%; }
      input { width:110px; padding:6px 8px; border-radius:6px; border:1px solid var(--divider-color); background: var(--primary-background-color); color: var(--primary-text-color); font:inherit; }
      input:focus-visible { outline:2px solid var(--primary-color); }
      .rooms label { display:flex; gap:8px; align-items:center; padding:4px 0; }
      .trvh { display:grid; gap:6px; padding:10px 0; border-bottom:1px solid var(--divider-color); }
      .trvtop { display:flex; gap:8px; align-items:baseline; flex-wrap:wrap; }
      .trvtop .order { display:inline-flex; gap:2px; margin-left:auto; } .trvtop .order .btn, .trvtop .order + .btn { margin-left:0; } .trvtop .order button[disabled] { opacity:.35; cursor:default; }
      .trvtop .btn { margin-left:auto; }
      .trv label.radio { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
      .trv input[type=radio] { width:auto; }
      .trvsel { padding-left:26px; display:grid; gap:4px; }
      .trvsel select, #trvadd { width:100%; }
      .muted { color: var(--secondary-text-color); } .small { font-size:12.5px; }
      .room { display:grid; gap:8px; padding:12px; border:1px solid var(--divider-color); border-radius:10px; }
      .room.lead { border-color: var(--primary-color); box-shadow: 0 0 0 1px var(--primary-color) inset; }
      .room .sub { display:grid; gap:4px; padding-left:4px; }
      .room input.rname { width:auto; min-width:0; flex:1 1 140px; font-weight:500; }
      .room label.chk, .rooms2 label.chk { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
      .room input[type=checkbox], .room input[type=radio] { width:auto; }
      .room .val { flex-wrap:wrap; } .room .val > span:first-child { min-width:140px; }
      .room select, #rmadd { max-width:100%; }
      .warn { color: var(--warning-color, #b26a00); font-size:13.5px; }
      .btn.small { padding:4px 12px; font-size:13px; }
      .nav { display:flex; justify-content:space-between; gap:10px; }
      .btn { font:inherit; padding:10px 20px; border-radius:22px; border:none; cursor:pointer; background: var(--primary-color); color: var(--text-primary-color, #fff); }
      .btn.ghost { background:transparent; color: var(--primary-color); border:1px solid var(--primary-color); }
      .btn[disabled] { opacity:.45; cursor:default; }
      .btn:focus-visible { outline:2px solid var(--primary-color); outline-offset:2px; }
      .err { color: var(--error-color, #db4437); }
      .need { color: var(--error-color, #db4437); margin:8px 0 0; text-align:right; min-height:1.2em; font-size:14px; }
      .sum div { display:flex; gap:10px; padding:6px 0; border-bottom:1px solid var(--divider-color); flex-wrap:wrap; }
      .sum > div > span:first-child { min-width:200px; color: var(--secondary-text-color); }
      label.live { display:flex; gap:8px; align-items:center; } label.live input { width:auto; }
      @media (max-width: 520px) { td.k { width:auto; } .sum > div > span:first-child { min-width:0; width:100%; } }
      @media (prefers-reduced-motion: reduce) { * { transition:none !important; } }`;
    const head = `<div class="bar"><ha-menu-button></ha-menu-button><span>${t.title}</span></div>`;
    let body = "";
    if (this._error && !this._start) body = `<p class="err">${esc(this._error)}</p>`;
    else if (!this._start) body = `<p class="hint">…</p>`;
    else if (this._done) body = this._renderDone();
    else body = this._renderStep();
    this.shadowRoot.innerHTML = `<style>${css}</style>${head}<div class="wrap body">${body}</div>`;
    const mb = this.shadowRoot.querySelector("ha-menu-button");
    if (mb) { mb.hass = this._hass; mb.narrow = this._narrow; }
    this._bind();
  }
  _stepsBar() {
    return `<div class="steps">${this._t.steps.map((n, i) => `<span class="${i === this._step ? "on" : i < this._step ? "done" : ""}">${i + 1}. ${n}</span>`).join("")}</div>`;
  }
  _nav(last = false) {
    const t = this._t;
    return `<div class="nav"><button class="btn ghost" id="back" ${this._step === 0 ? "disabled" : ""}>${t.back}</button>
      ${last ? `<button class="btn" id="save" ${this._saving ? "disabled" : ""}>${this._saving ? t.saving : t.save}</button>`
        : `<button class="btn" id="next" ${this._canNext() ? "" : "disabled"}>${t.next}</button>`}</div>
      ${last ? "" : `<p class="need" id="need">${this._whyNot() || ""}</p>`}`;
  }
  _renderStep() {
    const t = this._t, s = this._s, st = this._start;
    const top = this._stepsBar() + `<h1>${t.steps[this._step]}</h1>`;
    if (this._step === 0) {
      const entries = (st.entries || []).filter((e) => e.role === "standalone");
      return top + `<div class="grid">
        <button class="opt ${this._picked === null ? "sel" : ""}" data-entry=""><ha-icon icon="mdi:plus-circle-outline"></ha-icon><b>${t.new_inst}</b><small>${t.new_hint}</small></button>
        ${entries.map((e) => `<button class="opt ${this._picked === e.entry_id ? "sel" : ""}" data-entry="${esc(e.entry_id)}">
          <span class="mode">${esc(t.mode[e.mode] || e.mode)}</span><ha-icon icon="${SOURCE_ICON[e.heat_source] || "mdi:thermostat"}"></ha-icon>
          <b>${esc(e.title)}</b><small>${t.existing} · ${esc((t.sources[e.heat_source] || [e.heat_source])[0])} · ${esc((t.controls[e.control] || [e.control])[0])}</small></button>`).join("")}
        </div>` + this._nav();
    }
    if (this._step === 1) {
      return top + `<div class="grid">${st.sources.map((k) => `<button class="opt ${s.heat_source === k ? "sel" : ""}" data-source="${k}">
        <ha-icon icon="${SOURCE_ICON[k]}"></ha-icon><b>${t.sources[k][0]}</b><small>${t.sources[k][1]}</small></button>`).join("")}</div>` + this._nav();
    }
    if (this._step === 2) {
      const lang = t === T.hu ? "hu" : "en";
      // only what fits: a not recommended system is shown only if an existing instance uses it now
      const sys = st.systems.filter((k) => (st.matrix[`${k}|${s.heat_source}`] || {}).status !== "not_recommended" || s.system === k).map((k) => {
        const m = st.matrix[`${k}|${s.heat_source}`] || { status: "possible", hu: "", en: "" };
        return `<button class="opt ${s.system === k ? "sel" : ""} ${m.status === "not_recommended" ? "dim" : ""}" data-system="${k}">
          <svg viewBox="0 0 120 72" aria-hidden="true">${(k === "room_unit" && ["electric_heater", "storage_heater"].includes(s.heat_source) ? DRAW.heater_unit : DRAW[k])?.() || ""}</svg><b>${t.systems[k] || k}</b>
          <span class="badge ${esc(m.status)}">${t.status[m.status]}</span><small>${esc(m[lang])}</small></button>`;
      }).join("");
      const ctl = s.system ? `<h1 style="font-size:18px">${t.control_title}</h1><div class="grid">${((s.system === "fan_coil" ? st.controls_fan_coil : st.controls)?.[s.heat_source] || []).map((k) =>
        `<button class="opt ${s.control === k ? "sel" : ""}" data-control="${k}"><b>${t.controls[k][0]}</b><small>${t.controls[k][1]}</small></button>`).join("")}</div>` : "";
      return top + `<div class="grid">${sys}</div>${ctl}` + this._nav();
    }
    if (this._step === 3) {
      return top + `<div class="card"><div id="form"></div></div>` + this._nav();
    }
    if (this._step === 4) {
      const d = this._derived || { items: [], rooms: [] };
      const rows = d.items.map((it) => {
        const v = it.editable ? s.settings[it.key] : it.value;
        const isTime = typeof v === "string" && /^\d\d:\d\d/.test(v);
        // a switch (boolean), a choice (options: [value, label hu, label en]), a time or a number
        const input = !it.editable ? `<span>${esc(v)}</span>` : typeof v === "boolean"
          ? `<input type="checkbox" data-set="${it.key}" ${v ? "checked" : ""} style="width:auto">`
          : it.options ? `<select data-set="${it.key}">${it.options.map((o) => `<option value="${o[0]}" ${o[0] === v ? "selected" : ""}>${t === T.hu ? o[1] : o[2]}</option>`).join("")}</select>`
          : isTime
          ? `<input type="time" data-set="${it.key}" value="${String(v).slice(0, 5)}">`
          : `<input type="number" step="any" data-set="${it.key}" value="${esc(v)}">`;
        return `<tr><td class="k">${esc(this._keyLabel(it.key))}</td><td><div class="val">${input}<span>${esc(it.unit || "")}</span></div></td><td class="why">${esc(it.why)}</td></tr>`;
      }).join("");
      return top + `<p class="hint">${t.derived_hint}</p><div class="card" style="overflow-x:auto"><table>${rows}</table></div>${this._trvOk() && this._rc ? this._renderRooms() : ""}` + this._nav();
    }
    const m = this._derived?.matrix;
    // a, b are plain texts (escaped here); raw: b is HTML built from escaped parts
    const line = (a, b, raw = false) => `<div><span>${esc(a)}</span><span>${raw ? b : esc(b)}</span></div>`;
    const ents = Object.entries(s.entities).filter(([, v]) => v && (!Array.isArray(v) || v.length))
      .map(([k, v]) => line(t.fields[k] || k, [].concat(v).map((x) => this._name(x)).join(", "))).join("");
    const yes = t === T.hu ? ["igen", "nem"] : ["yes", "no"];
    const shown = (k, v) => (typeof v === "boolean" ? yes[v ? 0 : 1] : ((this._derived?.items || []).find((x) => x.key === k)?.options || [])
      .map((o) => (o[0] === v ? (t === T.hu ? o[1] : o[2]) : null)).find((x) => x) ?? v);
    // 0.45.0: with its unit (s, min, °C, %, W …)
    const unitOf = (k) => (this._derived?.items || []).find((x) => x.key === k)?.unit || "";
    const sets = Object.entries(s.settings).map(([k, v]) => {
      const u = typeof v === "boolean" || typeof v === "string" ? "" : unitOf(k);
      return line(this._keyLabel(k), `${shown(k, v)}${u ? " " + u : ""}`);
    }).join("");
    const live = s.entry_id ? "" : `<label class="chk live"><input type="checkbox" id="start_active" ${s.start_active ? "checked" : ""}>${esc(t.start_active)}</label>`;
    return top + `<div class="card sum">
      ${line(t.fields.name, s.name || "–")}${line(t.steps[1], t.sources[s.heat_source][0])}${line(t.steps[2], `${t.systems[s.system]} · ${t.controls[s.control][0]}`)}
      ${m ? line("", `<span class="badge ${esc(m.status)}">${t.status[m.status]}</span> ${esc(m.text)}`, true) : ""}${ents}${sets}
      ${this._trvOk() && (s.roomList || []).length ? line(t.rm.rooms_line, this._roomsSummary()) : ""}
      </div><p class="hint">${s.entry_id ? t.summary_edit : t.summary_new}</p>${live}${s.start_active && !s.entry_id ? `<p class="warn">⚠ ${esc(t.start_active_on)}</p>` : ""}${this._error ? `<p class="err">${esc(this._error)}</p>` : ""}` + this._nav(true);
  }
  _renderDone() {
    const t = this._t;
    return `<div class="card"><ha-icon icon="mdi:check-circle" style="--mdc-icon-size:40px;color:var(--success-color,#43a047)"></ha-icon>
      <h1>${this._done.created ? t.done_new : t.done_edit}</h1>
      <div class="nav"><a class="btn ghost" href="/config/integrations/integration/hc_thermostat">${t.open_integration}</a>
      <button class="btn" id="again">${t.again}</button></div></div>`;
  }
  _keyLabel(k) {
    const hu = this._t === T.hu, src = this._s.heat_source;
    if (src === "electric_heater") {
      const o = { power_idle_w: hu ? "A fűtő készenléti fogyasztása" : "Heater standby draw", power_burn_w: hu ? "A fűtő fűtési fogyasztása" : "Heater heating draw" };
      if (o[k]) return o[k];
    }
    if (src === "electric_boiler") {
      const o = { power_idle_w: hu ? "Kazán készenléti fogyasztása" : "Boiler standby draw", power_burn_w: hu ? "Kazán fűtési fogyasztása" : "Boiler heating draw" };
      if (o[k]) return o[k];
    }
    if (k === "min_on_s" && String(src).startsWith("electric")) return hu ? "Minimális bekapcsolt idő" : "Minimum on time";
    return this._t.keys[k] || k;
  }
  _name(id) { return this._hass.states[id]?.attributes?.friendly_name || id; }
  // 0.45.0: climates no picker offers: HC's own, and those another instance drives
  _excluded() {
    const st = this._start || {};
    return [...new Set([...(st.hc_climates || []), ...((st.taken_climates || {})[this._s.entry_id || ""] || [])])];
  }

  // an electric heating mat / cable under the floor: the floor sensor is required (floor limit)
  _floorNeeded() {
    const s = this._s;
    return s.heat_source === "electric_heater" && String(s.system || "").startsWith("floor") && ["tpi", "pid"].includes(s.control);
  }
  _schema() {
    const s = this._s, c = s.control;
    // entity pickers narrowed to what fits: a list of {domain, device_class} filters per field
    const f = (domain, device_class) => (device_class ? { domain, device_class } : { domain });
    const ent = (name, filters, multiple = false) => ({ name, selector: { entity: { filter: [].concat(filters), ...(multiple ? { multiple: true } : {}) } } });
    const TEMP = f("sensor", "temperature");
    const sc = [];
    if (!s.entry_id) sc.push({ name: "name", required: true, selector: { text: {} } });
    // 0.38.0: a relay control may take its demand from a wired wall thermostat – then the room thermometer is optional
    const relay = ["tpi", "pid", "onoff"].includes(c);
    sc.push({ ...ent("indoor_entity", TEMP), required: !(relay && s.entities.demand_entity) });
    if (relay) sc.push(ent("demand_entity", [f("binary_sensor"), f("input_boolean"), f("switch")]));
    sc.push(ent("outdoor_entity", [TEMP, f("weather")]));
    if (c === "tpi" || c === "pid" || c === "onoff" || c === "storage") {
      sc.push({ ...ent("actuator_entity", [f("switch"), f("input_boolean")]), required: true });
      if (["onoff_boiler", "modulating_boiler", "pellet_boiler"].includes(s.heat_source))  // only a burner has a flame
        sc.push(ent("flame_entity", [f("binary_sensor", "heat"), f("binary_sensor", "running"), f("binary_sensor", "power"), f("binary_sensor")]));
      sc.push(ent("boiler_power_entity", f("sensor", "power")),
        ent("heat_energy_entity", [f("sensor", "gas"), f("sensor", "energy"), f("sensor", "volume")]));
      if (String(s.system || "").startsWith("floor"))
        sc.push({ ...ent("floor_entity", TEMP), required: this._floorNeeded() });
    } else if (c === "external" || c === "ac") {
      // 0.45.0: not an HC thermostat, nor a climate another instance drives
      sc.push({ name: "external_climate", required: true, selector: { entity: { filter: [f("climate")], exclude_entities: this._excluded() } } });
      if (c === "ac") sc.push(ent("assist_climate", f("climate")));
    } else if (c === "curve") {
      sc.push({ ...ent("flow_setpoint_entity", [f("number"), f("input_number")]), required: true },
        ent("heat_enable_entity", [f("switch"), f("input_boolean")]), ent("heat_energy_entity", [f("sensor", "gas"), f("sensor", "energy"), f("sensor", "volume")]));
      if (String(s.system || "").startsWith("floor")) sc.push(ent("floor_entity", TEMP));
    }
    // 0.31–0.32: the storage heater's discharge fan, controlled power, fan coil, district heating return
    if (c === "storage") sc.push(ent("discharge_entity", [f("switch"), f("input_boolean"), f("fan")]));
    if (["electric_heater", "electric_boiler", "storage_heater"].includes(s.heat_source) && c !== "external")
      sc.push(ent("power_available_entity", [f("binary_sensor"), f("switch"), f("input_boolean")]));
    if (s.system === "fan_coil" && c !== "external") sc.push(ent("fan_entity", f("fan")), ent("coil_temp_entity", TEMP));
    if (s.heat_source === "district_heating" && c !== "external") sc.push(ent("return_temp_entity", TEMP));
    if (s.heat_source === "heat_pump" && (c === "onoff" || c === "curve"))
      sc.push(ent("hp_defrost_entity", [f("binary_sensor"), f("sensor"), f("switch"), f("input_boolean")]),
        ent("hp_dhw_entity", [f("binary_sensor"), f("sensor"), f("switch"), f("input_boolean")]));
    if (c !== "ac") sc.push(ent("target_source_entity", [f("climate"), f("number"), f("input_number")]));
    sc.push(ent("window_entities", ["window", "door", "opening", "garage_door"].map((dc) => f("binary_sensor", dc)), true),
      ent("presence_entities", [f("person"), f("binary_sensor", "presence"), f("binary_sensor", "occupancy"), f("sensor"), f("input_select")], true));
    return sc;
  }
  _bind() {
    const r = this.shadowRoot, s = this._s;
    r.getElementById("back")?.addEventListener("click", () => this._go(-1));
    r.getElementById("next")?.addEventListener("click", () => this._go(1));
    r.getElementById("save")?.addEventListener("click", () => this._save());
    r.getElementById("start_active")?.addEventListener("change", (e) => { s.start_active = e.target.checked; this._render(); });
    r.getElementById("again")?.addEventListener("click", () => { this._done = null; this._step = 0; this._picked = undefined; this._load(); });
    r.querySelectorAll("[data-entry]").forEach((b) => b.addEventListener("click", () => this._pickEntry(b.dataset.entry || null)));
    r.querySelectorAll("[data-source]").forEach((b) => b.addEventListener("click", () => {
      if (s.heat_source !== b.dataset.source) { s.system = null; s.control = null; }
      s.heat_source = b.dataset.source;
      if (s.heat_source === "air_conditioner") { s.system = "room_unit"; s.control = "ac"; }
      if (s.heat_source === "electric_heater") { s.system = "room_unit"; s.control = "tpi"; }
      if (s.heat_source === "storage_heater") { s.system = "room_unit"; s.control = "storage"; }
      this._render();
    }));
    r.querySelectorAll("[data-system]").forEach((b) => b.addEventListener("click", () => {
      s.system = b.dataset.system;
      const ctl = (s.system === "fan_coil" ? this._start.controls_fan_coil : this._start.controls)?.[s.heat_source] || [];
      if (!ctl.includes(s.control)) s.control = ctl[0];
      this._render();
    }));
    r.querySelectorAll("[data-control]").forEach((b) => b.addEventListener("click", () => { s.control = b.dataset.control; this._render(); }));
    r.querySelectorAll("[data-set]").forEach((i) => i.addEventListener("change", () => {
      if (i.type === "checkbox") { s.settings[i.dataset.set] = i.checked; return; }
      if (i.tagName === "SELECT") { s.settings[i.dataset.set] = i.value; return; }
      const v = i.type === "time" ? `${i.value}:00` : parseFloat(i.value);
      if (i.type === "time" || Number.isFinite(v)) s.settings[i.dataset.set] = v;
    }));
    this._bindRooms();  // 0.43.0
    const host = r.getElementById("form");
    if (host) {
      const f = document.createElement("ha-form");
      f.hass = this._hass;
      f.data = { name: s.name, ...s.entities };
      f.schema = this._schema();
      const heater = s.heat_source === "electric_heater", eb = s.heat_source === "electric_boiler";
    const hu = this._t === T.hu;
    const over = heater ? { actuator_entity: hu ? "A fűtő kapcsolója (relé vagy okosdugalj)" : "Heater switch (relay or smart plug)",
        external_climate: hu ? "A fűtő termosztátja (wifis fűtő)" : "Heater thermostat (Wi-Fi heater)",
        boiler_power_entity: hu ? "A fűtő áramfelvétele (W, ha van)" : "Heater power draw (W, if any)",
        heat_energy_entity: hu ? "A fűtő fogyasztásmérője (kWh, ha van)" : "Heater energy meter (kWh, if any)", flame_entity: hu ? "Fűtés jelzője (ha van)" : "Heating signal (if any)" }
      : eb ? { actuator_entity: hu ? "A kazán mágneskapcsolója / reléje" : "Boiler contactor / relay", heat_energy_entity: hu ? "Fogyasztásmérő (kWh, ha van)" : "Energy meter (kWh, if any)" } : {};
    this._over = over;
    f.computeLabel = (sch) => over[sch.name] || this._t.fields[sch.name] || sch.name;
      f.addEventListener("value-changed", (e) => {
        const v = e.detail.value || {};
        s.name = v.name ?? s.name;
        const { name, ...rest } = v;
        const had = !!s.entities.demand_entity;
        s.entities = rest;
        f.data = v;
        if (had !== !!rest.demand_entity) f.schema = this._schema();  // the room thermometer becomes (not) required
        this._updNext();
      });
      host.appendChild(f);
      this._form = f;
    } else {
      this._form = null;
    }
    this._updNext();
  }
}
customElements.define("hc-wizard-panel", HcWizardPanel);

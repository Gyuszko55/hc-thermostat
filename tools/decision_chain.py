"""0.48.3: writes DECISION_CHAIN.md (English) and DECISION_CHAIN.hu.md (Hungarian) from the code – the decision chain
of one heating step: heat source → execution → emitter and room, the one-step decision order and the heat source ×
emitter matrix. Run it after a change of core/matrix.py, core/measures.py or the texts below:

    python tools/decision_chain.py          # writes both files
    python tools/decision_chain.py --check  # exit 1 when a file is out of date (the tests run this)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(PKG))
from core import measures as ms  # noqa: E402
from core.matrix import SOURCES, SYSTEMS, cell, controls, default_timing  # noqa: E402

LANGS = ("en", "hu")
OUT = {"en": REPO / "DECISION_CHAIN.md", "hu": REPO / "DECISION_CHAIN.hu.md"}


def T(en: str, hu: str) -> dict:
    return {"en": en, "hu": hu}


def _labels(lang: str) -> dict:
    sel = json.loads((PKG / "translations" / f"{lang}.json").read_text(encoding="utf-8"))["selector"]
    return {k: sel[k]["options"] for k in ("heat_source", "system", "control")}


REQ, OPT, MEAS = "req", "opt", "meas"
DONE, MEASURED = "done", "measured"

# --- 1. the heat source: what HC reads and switches ------------------------------------------------------------------
READS = {
    "onoff_boiler": [("actuator_entity", REQ, T("Boiler relay (the room thermostat input)", "Kazánt kapcsoló relé (a termosztát-bemenetre kötve)")),
                     ("flame_entity", OPT, T("Flame signal (real burning)", "Láng-érzékelő (valódi égés)")),
                     ("boiler_power_entity", OPT, T("Boiler power meter (W): standby / pump / burning", "Kazán fogyasztásmérője (W): készenlét / szivattyú / égés"))],
    "modulating_boiler": [("flow_setpoint_entity", REQ, T("Flow setpoint (OpenTherm, eBUS) – the curve writes it", "Előremenő-cél (OpenTherm, eBUS) – a görbe ide írja")),
                          ("heat_enable_entity", OPT, T("Heating enable switch", "Fűtés engedélyezése")),
                          ("flame_entity", OPT, T("Flame signal", "Láng-érzékelő")),
                          ("outdoor_entity", REQ, T("Outdoor thermometer (the curve needs it)", "Kinti hőmérő (a görbéhez kötelező)"))],
    "heat_pump": [("flow_setpoint_entity", REQ, T("Flow setpoint, or its thermostat input (on/off)", "Előremenő-cél, vagy termosztát-bemenet (on-off)")),
                  ("hp_defrost_entity", OPT, T("Defrost signal: no fault watch meanwhile", "Leolvasztás jelzője: közben nincs hibafigyelés")),
                  ("hp_dhw_entity", OPT, T("Hot water signal: the house waits, no fault", "Melegvíz-jelző: a ház vár, nem hiba")),
                  ("cool_mode_entity", OPT, T("Cooling switch (floor cooling)", "Hűtés-kapcsoló (padlóhűtés)"))],
    "electric_boiler": [("actuator_entity", REQ, T("Contactor (keep the boiler's own thermostat above)", "Mágneskapcsoló (a kazán saját termosztátja maradjon felül)")),
                        ("boiler_power_entity", OPT, T("Power meter (W)", "Fogyasztásmérő (W)")),
                        ("power_available_entity", OPT, T("Off-peak power available", "Vezérelt áram jelzése"))],
    "air_conditioner": [("external_climate", REQ, T("The AC's climate entity: HC writes its setpoint", "A klíma climate entitása: a HC a célját írja"))],
    "electric_heater": [("actuator_entity", REQ, T("Relay or smart plug", "Relé vagy okosdugalj")),
                        ("boiler_power_entity", OPT, T("Power meter (W): on but 0 W → problem", "Fogyasztásmérő (W): bekapcsolva, de 0 W → probléma")),
                        ("power_available_entity", OPT, T("Off-peak power available", "Vezérelt áram jelzése"))],
    "storage_heater": [("actuator_entity", REQ, T("Charge relay", "Töltő relé")),
                       ("discharge_entity", OPT, T("Discharge fan / damper", "Kisütő ventilátor / csappantyú")),
                       ("power_available_entity", OPT, T("Off-peak power available", "Vezérelt áram jelzése"))],
    "district_heating": [("actuator_entity", REQ, T("Flat zone valve (or TRV heads as an external thermostat)", "Lakásonkénti zónaszelep (vagy szelepfejek külső termosztátként)")),
                         ("return_temp_entity", OPT, T("Return temperature: the return limit", "Visszatérő hőmérséklet: visszatérő-korlát"))],
    "pellet_boiler": [("actuator_entity", REQ, T("Start relay (long runs, slow burn-out)", "Indító relé (hosszú futás, lassú leégés)")),
                      ("flame_entity", OPT, T("Flame / burning signal", "Láng / égés jelzője")),
                      ("buffer_top_entity", OPT, T("Buffer tank top (and bottom) thermometer", "Puffer felső (és alsó) hőmérője"))],
    "external_heat": [("actuator_entity", REQ, T("The room's zone valve – the heat source and pump run on their own control",
                                                 "A helyiség zónaszelepe – a hőtermelőt és a szivattyút a saját vezérlése indítja"))],
}
COMMON_READS = [("heat_energy_entity", OPT, T("Heat energy / consumption (gas m³, kWh, GJ): the heat need is learned from it",
                                              "Hőenergia / fogyasztás (gáz m³, kWh, GJ): ebből tanulja a hőigényt")),
                ("boiler_price_entity", OPT, T("Energy price and discounted allowance: the cost advice", "Energiaár és kedvezményes keret: költség-tanács")),
                ("reference_entity", OPT, T("Real heating signal: agreement and fault watch", "Tényleges fűtés jelzője: egyezés és hibafigyelés"))]
MEASURE_TEXT = {
    "pressure_entity": T("Water pressure (bar; psi, kPa, hPa, mbar converted) – low / high alert", "Víznyomás (bar; psi, kPa, hPa, mbar átváltva) – alacsony / magas jelzés"),
    "flow_temp_entity": T("Real flow temperature – ΔT with the return", "Valós előremenő – ΔT a visszatérővel"),
    "return_temp_entity": T("Return temperature", "Visszatérő hőmérséklet"),
    "modulation_entity": T("Modulation / compressor %", "Moduláció / kompresszor %"),
    "fault_code_entity": T("Fault code – all zeros and own \"no fault\" values are no fault", "Hibakód – csupa nulla és saját „nincs hiba” értékek nem hibák"),
    "heat_output_entity": T("Heat given off (heat meter, kWh) – the COP", "Leadott hő (hőmennyiségmérő, kWh) – a COP-hoz"),
    "flue_temp_entity": T("Flue gas temperature", "Füstgáz-hőmérséklet"),
    "fuel_level_entity": T("Fuel level (%) – little fuel alert", "Tüzelőanyag-szint (%) – kevés tüzelőanyag jelzés"),
    "core_temp_entity": T("Core temperature", "Maghőmérséklet"),
    "source_state_entity": T("The heat source's own state (e.g. from a PLC)", "A hőtermelő saját állapota (pl. PLC-ből)"),
    "hp_dhw_entity": T("Hot water signal (combi boiler): no fault meanwhile", "Melegvíz-jelző (kombi kazán): közben nincs hibajelzés"),
}

# --- what HC works out of it ------------------------------------------------------------------------------------
DERIVES = {
    "onoff_boiler": [(DONE, T("Boiler health from the power levels", "Kazán állapota a W-szintekből")),
                     (DONE, T("Learned after-heat and minutes per degree – per outdoor band, corrected by the outdoor temperature", "Tanult utánfűtés és perc/fok – kinti sávonként, a kinti hőmérséklet szerint korrigálva")),
                     (DONE, T("Starts and run time per day, week, season – too many starts an hour alert", "Indítások és üzemidő napra, hétre, szezonra – túl sűrű kapcsolgatás jelzés"))],
    "modulating_boiler": [(DONE, T("Flow setpoint as a sensor", "Előremenő cél saját szenzorként")),
                          (MEASURED, T("Real flow / return, ΔT, modulation, pressure, fault code", "Valós előremenő / visszatérő, ΔT, moduláció, nyomás, hibakód"))],
    "heat_pump": [(DONE, T("Defrost and hot water protected: no false fault", "Leolvasztás és melegvíz védve: nincs hamis hiba")),
                  (DONE, T("Long-run protection (minimum run and pause)", "Hosszú futás védelme (minimum futás és szünet)")),
                  (MEASURED, T("COP today, 7 days, season (heat given off ÷ power)", "COP ma, 7 nap, szezon (leadott hő ÷ villany)"))],
    "electric_boiler": [(DONE, T("Boiler health from the power levels", "Kazán állapota a W-szintekből"))],
    "air_conditioner": [(DONE, T("The AC's energy as the other source of the cost advice", "A klíma energiája másik hőforrásként a költség-tanácshoz")),
                        (MEASURED, T("Compressor %, COP with a heat meter", "Kompresszor %, COP hőmennyiségmérővel"))],
    "electric_heater": [(DONE, T("Heater health from the power draw", "Fűtő állapota az áramfelvételből")),
                        (DONE, T("Consumption (kWh)", "Fogyasztás (kWh)"))],
    "storage_heater": [(DONE, T("Charge time from the outdoor daily mean", "Töltési idő a kinti napi átlagból"))],
    "district_heating": [(DONE, T("Return limit", "Visszatérő-korlát")),
                         (DONE, T("Heat meter in GJ / MJ / MWh to kWh, no efficiency", "Hőmennyiségmérő GJ / MJ / MWh → kWh, hatásfok nélkül")),
                         (MEASURED, T("ΔT with a flow thermometer", "ΔT előremenő-hőmérővel"))],
    "pellet_boiler": [(DONE, T("Buffer charging, circuits as zones", "Puffer töltés, a körök zónaként"))],
    "external_heat": [(MEASURED, T("The heat source's state shown, fault code alert", "A hőtermelő állapota kiírva, hibakód-jelzés"))],
}
COMMON_DERIVES = [(DONE, T("House heat need (kWh/day) and heat loss (kW/K)", "Ház hőigénye (kWh/nap) és hőveszteség (kW/K)")),
                  (DONE, T("Cheaper heat source by price and allowance", "Olcsóbb hőforrás ár és keret szerint")),
                  (DONE, T("Agreement with the real heating, heating fault", "Egyezés a tényleges fűtéssel, fűtési hiba"))]

# --- 2. execution ---------------------------------------------------------------------------------------------------
CONTROL_TEXT = {
    "tpi": T("Demand % from the deviation and the outdoor temperature, then on / off time per cycle; learned coefficients.",
             "Igény % az eltérésből és a kinti hőfokból, ebből ciklusonként be / ki idő; tanult együtthatók."),
    "pid": T("Proportional, integral and derivative terms give the demand %, then the cycle's on time; anti-windup.",
             "Arányos, integráló és deriváló tag adja az igény %-ot, abból a ciklus be-ideje; integrál-védelem."),
    "curve": T("Flow setpoint from the outdoor temperature, shifted by the room's deviation (experimental).",
               "Előremenő cél a kinti hőfokból, a helyiség eltérése tolja (kísérleti)."),
    "onoff": T("Hysteresis with long minimum run and pause; no PWM.", "Hiszterézis hosszú minimum futással és szünettel; nincs PWM."),
    "ac": T("Shifts the AC's setpoint by the room thermometer (virtual i-Feel); never switches it.",
            "A klíma célját tolja a helyiséghőmérő szerint (virtuális i-Feel); nem kapcsolgatja."),
    "storage": T("Night charge by the outdoor daily mean, timed to the end of the off-peak window; daytime discharge.",
                 "Éjszakai töltés a kinti napi átlag szerint, a vezérelt áram ablakának végére; nappal kisütés."),
    "external": T("HC writes the target into an existing thermostat (TRV, Wi-Fi heater), which regulates.",
                  "A HC egy meglévő termosztátba írja a célt (TRV, wifis fűtő), az szabályoz."),
}
EXECUTION = [
    T("**Relay** in the cycle (switch / input_boolean), a **flow setpoint** (number) or a **target** (climate)",
      "**Relé** a ciklusban (switch / input_boolean), **előremenő cél** (number) vagy **célhőmérséklet** (climate)"),
    T("**Useful heat delay** (slow valve, late pump): run = useful time + delay; a full cycle only when the useful demand itself reaches it; the cycle must hold delay + minimum on + minimum off",
      "**Hasznos fűtés késése** (lassú szelep, késő szivattyú): futás = hasznos idő + késés; teljes ciklus csak, ha a hasznos igény maga eléri; a ciklus legalább késés + min. be + min. ki"),
    T("**Small demands** below the minimum run add up to a real run (always with a delay; an option without)",
      "**Kis igények** a minimális égés alatt egy rendes égéssé gyűlnek (késésnél mindig; egyébként opció)"),
    T("**Coasting** after a burn and **mid-cycle start** (options, off by default)",
      "**Utánfűtés-kivárás** égés után és **ciklus közbeni indítás** (opciók, alapból ki)"),
    T("**No new start before the target goes down**: within 30 min (option) of a scheduled lowering, while the room is already at or above the coming target; a running burn is not cut",
      "**Nincs új indítás célcsökkenés előtt**: az ütemezett csökkenés előtt 30 percen belül (opció), ha a helyiség már most legalább olyan meleg, mint a váltás utáni cél; a futó égést nem vágja el"),
    T("**Check back**: real heating, flame, power – agreement or fault", "**Visszaellenőrzés**: tényleges fűtés, láng, áramfelvétel – egyezés vagy hiba"),
    T("**Failsafe**: three failed steps in a row switch the heat off (also right after a start); each side step and actuator part on its own",
      "**Hibavédelem**: három egymás utáni hibás lépés kikapcsolja a fűtést (újraindítás után is); minden mellékág és beavatkozó-rész külön fut"),
]

# --- 3. emitter and room ----------------------------------------------------------------------------------------
ROOM_COMMON = [
    ("indoor_entity", REQ, T("Room thermometer (several: the room group's mean)", "Helyiség hőmérője (több: a helyiségcsoport átlaga)")),
    ("window_entities", OPT, T("Windows and doors: frost protection while open", "Ablakok és ajtók: nyitva fagyvédelem")),
    ("presence_entities", OPT, T("Presence: household or per room", "Jelenlét: háztartás vagy helyiségenként")),
    ("target_source_entity", OPT, T("Target source: a wall thermostat's knob becomes the manual target", "Célhő forrása: a fali termosztát tekerője kézi célként")),
    ("window_drop_entities", OPT, T("Fast temperature drop: a window without a contact", "Gyors hőesés: ablak érzékelő nélkül")),
    ("radiators", MEAS, T("Radiator thermometer per room: does it get heat", "Radiátor-hőmérő helyiségenként: kap-e meleget")),
    ("humidity", MEAS, T("Humidity per room: dew point, mould risk", "Páratartalom helyiségenként: harmatpont, penész-kockázat")),
]
ROOM_READS = {
    "radiator_single": [("room_trvs", OPT, T("TRV heads in some rooms: own target, calibration", "Szelepfejek egyes helyiségekben: saját cél, kalibrálás")),
                        ("room_sensors", OPT, T("Watched rooms' thermometers (advice only)", "Megfigyelt helyiségek hőmérői (csak tanács)")),
                        ("zone_temp_entity", OPT, T("Adjoining space (e.g. a winter garden) and its doors", "Csatlakozó tér (pl. télikert) és ajtói"))],
    "radiator_trv": [("room_trvs", REQ, T("TRV heads: each room's target; calibrated to the room thermometer", "Szelepfejek: helyiségenkénti cél; a helyiség hőmérőjéhez kalibrálva"))],
    "radiator_zones": [("zone_entities", REQ, T("Zone thermostats (HC); the central boiler follows the open zones", "Zóna-termosztátok (HC); a központi kazán a nyitott zónákat követi")),
                       ("valve_feedback_entity", OPT, T("Valve feedback (end switch / position)", "Szelep visszajelzése (végállás / helyzet)")),
                       ("pump_entity", OPT, T("Circulation pump: overrun, weekly exercise", "Keringető szivattyú: utánfutás, heti átmozgatás"))],
    "floor_single": [("floor_entity", OPT, T("Floor sensor: surface limit (water floor 29 °C)", "Padlóhőmérő: felületi korlát (vizes padló 29 °C)"))],
    "floor_zones": [("floor_entity", OPT, T("Floor sensor: surface limit", "Padlóhőmérő: felületi korlát")),
                    ("valve_feedback_entity", OPT, T("Valve actuator feedback", "Szelepmotor visszajelzése"))],
    "mixed_no_circuit": [("floor_entity", OPT, T("Floor sensor: its limit caps the shared flow", "Padlóhőmérő: a maximuma korlátozza a közös előremenőt"))],
    "mixed_rtl": [("floor_entity", OPT, T("Floor sensor (the RTL stays the protection)", "Padlóhőmérő (az RTL marad a védelem)"))],
    "mixed_mixing": [("floor_entity", OPT, T("Floor sensor: the floor loop may get its own curve", "Padlóhőmérő: a padlókör külön görbét kaphat"))],
    "room_unit": [("floor_entity", OPT, T("Electric floor (mat, cable): floor sensor required, limit 27 °C", "Elektromos padló (szőnyeg, kábel): padlószenzor kötelező, korlát 27 °C"))],
    "fan_coil": [("actuator_entity", REQ, T("Water valve: TPI / PID switches it", "Vízszelep: a TPI / PID kapcsolja")),
                 ("fan_entity", OPT, T("Fan: speed by the demand, overrun", "Ventilátor: fordulat az igény szerint, utánfutás")),
                 ("coil_temp_entity", OPT, T("Coil temperature: no fan while it is cold", "Hőcserélő hőmérséklete: hidegen nem indul a ventilátor"))],
}
ROOM_DERIVES = [
    (DONE, T("Room groups: mean thermometer, shared presence and window per room", "Helyiségcsoportok: átlag hőmérő, közös jelenlét és ablak")),
    (DONE, T("Silent sensor detection: fallback or frost protection", "Néma szenzor felismerése: tartalék vagy fagyvédelem")),
    (DONE, T("Room deviation and valve advice (watched rooms)", "Helyiségenkénti eltérés és szelep-tanács (megfigyelt helyiségek)")),
    (MEASURED, T("Cold radiator: minutes of heating added over the PWM pauses; \"warm\" follows the flow", "Hideg radiátor: a fűtési percek a PWM-szünetek között is összeadódnak; a „meleg” az előremenőhöz igazodik")),
    (MEASURED, T("Dew point and mould risk from the hours of high humidity", "Harmatpont és penész-kockázat a magas páratartalmú órákból")),
]
FLOOR_DERIVES = [(DONE, T("Floor tempering, floor fallback, limit by covering and probe position", "Padló-temperálás, padló-tartalék, korlát a burkolat és a szenzor helye szerint"))]

STEPS = [
    T("Inputs fresh?", "Bemenetek frissek?"), T("Paused? Shadow or live", "Szünetel? Árnyék vagy éles"),
    T("Season (summer rest)", "Szezon (nyári pihenő)"), T("Window open → frost protection", "Ablak nyitva → fagyvédelem"),
    T("Target: schedule, presence, manual, boost", "Cél: program, jelenlét, kézi, felfűtés"),
    T("Limits: floor, return, dew point, off-peak power", "Korlátok: padló, visszatérő, harmatpont, vezérelt áram"),
    T("Regulator: demand % / flow setpoint / setpoint shift", "Szabályozó: igény % / előremenő cél / céleltolás"),
    T("Execution: PWM, flow setpoint, TRV targets, fan", "Végrehajtás: PWM, előremenő cél, TRV-célok, ventilátor"),
    T("Check back: real heating, flame, power", "Visszaellenőrzés: tényleges fűtés, láng, áramfelvétel"),
]

W = {
    "title": T("HC Thermostat – decision chain", "HC Thermostat – döntési sor"),
    "intro": T("One heating step on three levels: the heat source, the execution (regulator and actuator) and the emitter with its room – what HC reads at each level and what it works out. Generated from the code by `tools/decision_chain.py`.",
               "Egy fűtési lépés három szinten: a hőforrás, a végrehajtás (szabályozó és beavatkozó) és a fűtőkészülék a helyiséggel – szintenként mit olvas a HC, és mit számol ki belőle. A kódból generálja a `tools/decision_chain.py`."),
    "legend": T("**required** · *option* · 📏 measurement (Settings → Measurements, or the rooms form) · ✅ HC works it out · 📏✅ worked out when the measurement is given",
                "**kötelező** · *opció* · 📏 mérés (Beállítások → Mérések, vagy a helyiségek űrlapja) · ✅ a HC kiszámolja · 📏✅ kiszámolja, ha a mérést megadod"),
    "chain": T("The chain", "A lánc"), "steps": T("One step, in this order", "Egy lépés, ebben a sorrendben"),
    "sources": T("1. Heat sources", "1. Hőforrások"), "systems": T("3. Emitters and rooms", "3. Fűtőkészülékek és helyiségek"),
    "execution": T("2. Execution", "2. Végrehajtás"), "matrix": T("Heat source × emitter", "Hőforrás × fűtőkészülék"),
    "reads": T("Reads and switches", "Mit olvas és kapcsol"), "derives": T("Works out", "Mit nyer ki"),
    "measures": T("Measurements (optional)", "Mérések (nem kötelező)"), "controls": T("Controls (recommended first)", "Szabályzók (az ajánlott elöl)"),
    "timing": T("Starting timing (cycle / min. on / min. off)", "Kezdő időzítés (ciklus / min. be / min. ki)"),
    "rec": T("recommended", "ajánlott"), "pos": T("possible", "lehetséges"), "no": T("not recommended", "nem ajánlott"),
    "common": T("Every room", "Minden helyiség"), "min": T("min", "perc"), "h": T("h", "óra"),
    "box1": T("1 Heat source", "1 Hőforrás"), "box1b": T("reads · switches · works out", "olvas · kapcsol · kiszámol"),
    "box2": T("2 Execution", "2 Végrehajtás"), "box2b": T("regulator → actuator → check back", "szabályozó → beavatkozó → visszaellenőrzés"),
    "box3": T("3 Emitter and room", "3 Fűtőkészülék és helyiség"), "box3b": T("room thermometer · TRV · floor · window", "helyiség-hőmérő · TRV · padló · ablak"),
    "matrix_intro": T("The setup shows this cell as its advice; in a cell: the status and the recommended control.",
                      "A beállítás ezt a cellát mutatja ajánlásként; cellánként az állapot és az ajánlott szabályzó."),
    "fan_note": T("A fan coil switches its own water valve whatever feeds it: TPI, PID or an external thermostat.",
                  "A fan-coil a saját vízszelepét kapcsolja, bármi táplálja: TPI, PID vagy külső termosztát."),
}
SHORT = {"tpi": "TPI", "pid": "PID", "curve": T("curve", "görbe"), "onoff": "on-off", "ac": T("shift", "eltolás"),
         "storage": T("charge", "töltés"), "external": T("external", "külső")}
MARK = {REQ: lambda t: f"**{t}**", OPT: lambda t: f"*{t}*", MEAS: lambda t: f"📏 {t}"}
DMARK = {DONE: "✅", MEASURED: "📏✅"}


def _t(x, lang):
    return x[lang] if isinstance(x, dict) else x


def _dur(s: float, lang: str) -> str:
    return f"{s / 3600:g} {_t(W['h'], lang)}" if s >= 3600 else f"{s / 60:g} {_t(W['min'], lang)}"


def _valid_systems(source: str) -> list[str]:
    return [y for y in SYSTEMS if not cell(y, source).text_en.startswith("This heat source does not fit")]


def render(lang: str) -> str:
    lab = _labels(lang)
    o: list[str] = [f"# {_t(W['title'], lang)}", "", _t(W["intro"], lang), "", _t(W["legend"], lang), "",
                    f"## {_t(W['chain'], lang)}", "", "```mermaid", "flowchart LR",
                    f'  S["{_t(W["box1"], lang)}<br/>{_t(W["box1b"], lang)}"] --> '
                    f'E["{_t(W["box2"], lang)}<br/>{_t(W["box2b"], lang)}"] --> '
                    f'R["{_t(W["box3"], lang)}<br/>{_t(W["box3b"], lang)}"]',
                    "  R -. " + ("room temperature" if lang == "en" else "helyiség hőmérséklete") + " .-> E", "```", "",
                    f"## {_t(W['steps'], lang)}", "", "```mermaid", "flowchart TD"]
    for i, step in enumerate(STEPS, 1):
        o.append(f'  N{i}["{i}. {_t(step, lang)}"]' + (f" --> N{i + 1}" if i < len(STEPS) else ""))
    o += ["```", "", f"## {_t(W['sources'], lang)}", ""]
    for src in SOURCES:
        o += ["<details>", f"<summary><b>{lab['heat_source'][src]}</b></summary>", "", f"**{_t(W['reads'], lang)}**", ""]
        rows = list(READS[src]) + ([] if src == "air_conditioner" else
                                   [r for r in COMMON_READS if not (src == "external_heat" and r[0] == "boiler_price_entity")])
        o += [f"- {MARK[k](_t(text, lang))} `{key}`" if not key.startswith("external") else f"- {MARK[k](_t(text, lang))}"
              for key, k, text in rows]
        meas = [k for k in ms.fields_for(src) if not (k == "return_temp_entity" and src == "district_heating")]
        if src in ms.DHW_SOURCES and src != "heat_pump":
            meas.append("hp_dhw_entity")
        if meas:
            o += ["", f"**{_t(W['measures'], lang)}**", ""] + [f"- 📏 {_t(MEASURE_TEXT[k], lang)} `{k}`" for k in meas]
        o += ["", f"**{_t(W['derives'], lang)}**", ""]
        o += [f"- {DMARK[k]} {_t(text, lang)}" for k, text in DERIVES[src] + ([] if src == "air_conditioner" else COMMON_DERIVES)]
        ctl = controls(src)
        o += ["", f"**{_t(W['controls'], lang)}:** " + " · ".join(
            (f"**{lab['control'][c]}**" if i == 0 else lab["control"][c]) for i, c in enumerate(ctl))]
        timings = []
        for y in _valid_systems(src):
            t = default_timing(y, src)
            item = f"{_dur(t['cycle_s'], lang)} / {_dur(t['min_on_s'], lang)} / {_dur(t['min_off_s'], lang)}"
            if not timings or timings[-1][1] != item:
                timings.append(([lab["system"][y]], item))
            else:
                timings[-1][0].append(lab["system"][y])
        o += ["", f"**{_t(W['timing'], lang)}:**", ""] + [f"- {item} – {', '.join(names)}" for names, item in timings]
        o += ["", "</details>", ""]
    o += [f"## {_t(W['execution'], lang)}", ""]
    o += [f"- **{lab['control'][c]}** – {_t(CONTROL_TEXT[c], lang)}" for c in ("tpi", "pid", "curve", "onoff", "ac", "storage", "external")]
    o += [""] + [f"- {_t(x, lang)}" for x in EXECUTION] + ["", _t(W["fan_note"], lang), ""]
    o += [f"## {_t(W['systems'], lang)}", "", f"**{_t(W['common'], lang)}**", ""]
    o += [f"- {MARK[k](_t(text, lang))}" + (f" `{key}`" if key.endswith(("_entity", "_entities")) else "") for key, k, text in ROOM_COMMON]
    o += [""] + [f"- {DMARK[k]} {_t(text, lang)}" for k, text in ROOM_DERIVES] + [""]
    for y in SYSTEMS:
        o += ["<details>", f"<summary><b>{lab['system'][y]}</b></summary>", ""]
        o += [f"- {MARK[k](_t(text, lang))} `{key}`" for key, k, text in ROOM_READS[y]]
        if y.startswith("floor") or y.startswith("mixed"):
            o += [f"- {DMARK[k]} {_t(text, lang)}" for k, text in FLOOR_DERIVES]
        o += ["", "</details>", ""]
    o += [f"## {_t(W['matrix'], lang)}", "", _t(W["matrix_intro"], lang), ""]
    o.append("| | " + " | ".join(lab["heat_source"][s].split(" (")[0] for s in SOURCES) + " |")
    o.append("|---|" + "---|" * len(SOURCES))
    for y in SYSTEMS:
        cells = []
        for s in SOURCES:
            c = cell(y, s)
            st = {"recommended": ("✅", W["rec"]), "possible": ("🟡", W["pos"]), "not_recommended": ("⛔", W["no"])}[c.status.value]
            first = controls(s, y)[0]
            short = SHORT.get(first, first)
            cells.append(f"{st[0]} {_t(short, lang)}" if c.status.value != "not_recommended" else st[0])
        o.append(f"| {lab['system'][y]} | " + " | ".join(cells) + " |")
    o += ["", "✅ " + _t(W["rec"], lang) + " · 🟡 " + _t(W["pos"], lang) + " · ⛔ " + _t(W["no"], lang), ""]
    return "\n".join(o)


def main(argv: list[str]) -> int:
    stale = []
    for lang in LANGS:
        text = render(lang)
        if "--check" in argv:
            if not OUT[lang].exists() or OUT[lang].read_text(encoding="utf-8") != text:
                stale.append(OUT[lang].name)
        else:
            OUT[lang].write_text(text, encoding="utf-8")
    if stale:
        print("out of date:", ", ".join(stale), "– run python tools/decision_chain.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""0.87.0: "why heating / why not" for the central boiler, the buffer tank, the mixing circuit and the heat pump
coordination – the same plain card as a room thermostat's (core/summary.py): a state word, why in everyday words,
when it changes and, where it is certain, what to do. Only what the decision holds is told; a missing number leaves
its line out. `names` turns a zone's entity id into its name (the coordinator gives it; absent: as it is).
"""

from __future__ import annotations

from .summary import COOLING, FAULT, HEATING, IDLE, OFF, PAUSED, WAITING, _n  # noqa: F401  (COOLING/PAUSED: one set)

_FAIL = {
    "hu": {"failsafe": ("A döntés többször egymás után hibára futott, ezért biztonsági okból kikapcsolva.",
                        "Nézd meg a naplót és a Javítások oldalt."),
           "safety_stop": ("Életvédelmi leállítás: egy biztonsági érzékelő jelzett, minden fűtés áll.",
                           "Szüntesd meg a jelzés okát, majd nyugtázd a leállítást.")},
    "en": {"failsafe": ("The decision failed several times in a row, so it is switched off for safety.",
                        "Look at the log and the Repairs page."),
           "safety_stop": ("Life-safety stop: a safety detector went off, all heating stands.",
                           "Remove the alarm's cause, then acknowledge the stop.")},
}
_HEAD = {
    "hu": {HEATING: "Fűt", IDLE: "Nem fűt", WAITING: "Vár", FAULT: "Hiba", OFF: "Ki", "charging": "Tölt",
           "full": "Feltöltve", "ready": "Elég meleg", "waiting_demand": "Igényre vár", "on": "Be", "standby": "Készenlét",
           "summer": "Nyári üzem", "no_demand": "Nincs tartós igény", "stop": "Leállítva"},
    "en": {HEATING: "Heating", IDLE: "Not heating", WAITING: "Waiting", FAULT: "Fault", OFF: "Off", "charging": "Charging",
           "full": "Charged", "ready": "Warm enough", "waiting_demand": "Waiting for demand", "on": "On",
           "standby": "Standby", "summer": "Summer mode", "no_demand": "No lasting demand", "stop": "Stopped"},
}


def _lang(language: str) -> str:
    return "hu" if str(language).startswith("hu") else "en"


def _who(items, names: dict | None) -> str:
    return ", ".join((names or {}).get(x, x) for x in items)


def _card(state: str, head: str, lines: list, live: bool, lang: str) -> dict:
    lines = [x for x in lines if x]
    return {"state": state, "headline": head, "lines": lines, "shadow": not live,
            "note": None if live else ("Árnyék mód: ezt tenné, de nem kapcsol." if lang == "hu"
                                       else "Shadow mode: this is what it would do; it switches nothing.")}


def _failed(reason: str, lang: str, live: bool) -> dict | None:
    if reason not in _FAIL[lang]:
        return None
    why, act = _FAIL[lang][reason]
    return _card(FAULT, _HEAD[lang]["stop" if reason == "safety_stop" else FAULT], [why, act], live, lang)


# --- the buffer tank ----------------------------------------------------------------------------------------------
def summarize_buffer(d, language: str = "en", live: bool = True, names: dict | None = None) -> dict:
    lang = _lang(language)
    hu, H = lang == "hu", _HEAD[lang]
    if (card := _failed(d.reason, lang, live)) is not None:
        return card
    det = d.details or {}
    top, bottom = _n(d.top, lang), _n(d.bottom, lang)
    on, off = _n(det.get("buffer_on"), lang), _n(det.get("buffer_off"), lang)
    end = (("az alja", bottom) if d.bottom is not None else ("a teteje", top)) if hu else \
        (("the bottom", bottom) if d.bottom is not None else ("the top", top))
    asking = (f"Hőt kér: {_who(d.asking, names)}." if hu else f"Asking for heat: {_who(d.asking, names)}.") if d.asking else None
    r = d.reason
    if r == "charging":
        return _card(HEATING, H["charging"], [
            f"A teteje {top} °C; addig tölt, amíg {end[0]} el nem éri a {off} °C-ot (most {end[1]} °C)." if hu
            else f"The top is {top} °C; it charges until {end[0]} reaches {off} °C (now {end[1]} °C).", asking], live, lang)
    if r == "full":
        return _card(IDLE, H["full"], [
            f"{end[0][:1].upper()}{end[0][1:]} {end[1]} °C – elérte a {off} °C-os határt." if hu
            else f"{end[0][:1].upper()}{end[0][1:]} is {end[1]} °C – it reached the {off} °C limit.",
            f"Újra tölt, ha a teteje {on} °C alá hűl." if hu else f"It charges again when the top falls below {on} °C."],
            live, lang)
    if r == "ready":
        return _card(IDLE, H["ready"], [
            f"A teteje {top} °C – a {on} °C-os indítási határ fölött, most nem kell tölteni." if hu
            else f"The top is {top} °C – above the {on} °C start limit, no charge needed now.",
            f"Akkor tölt, ha a teteje {on} °C alá hűl." if hu else f"It charges when the top falls below {on} °C.",
            asking], live, lang)
    if r == "waiting_demand":
        return _card(WAITING, H["waiting_demand"], [
            f"A teteje {top} °C, de most egy zóna sem kér hőt – csak igényre tölt." if hu
            else f"The top is {top} °C, but no zone asks for heat right now – it charges on demand only."], live, lang)
    if r == "min_off":
        return _card(WAITING, H[WAITING], [
            f"Töltene (a teteje {top} °C), de a legrövidebb szünet még tart – utána indul." if hu
            else f"It would charge (the top is {top} °C), but the shortest pause is not over yet – then it starts.",
            asking], live, lang)
    if r == "frost":
        return _card(HEATING, H["charging"], [
            f"Fagyvédelem: a teteje csak {top} °C, ezért tölt." if hu else f"Frost protection: the top is only {top} °C, so it charges."],
            live, lang)
    if r == "no_sensor":
        return _card(FAULT, H[FAULT], [
            "Nincs friss mérés a puffer tetején, ezért nem tölt." if hu else "No fresh reading at the top of the tank, so it does not charge.",
            "Nézd meg a puffer felső hőmérőjét." if hu else "Check the tank's top thermometer."], live, lang)
    if r == "max_charge":
        return _card(FAULT, H[FAULT], [
            "A töltés túl sokáig tartott, ezért leállt, és szünetet tart." if hu
            else "The charge took too long, so it stopped and pauses.",
            "Nézd meg, megy-e a hőforrás és a töltőszivattyú." if hu else "Check that the heat source and the charging pump run."],
            live, lang)
    return _card(IDLE, H[IDLE], [str(r)], live, lang)


# --- the central boiler -------------------------------------------------------------------------------------------
def summarize_central(d, language: str = "en", live: bool = True, names: dict | None = None) -> dict:
    lang = _lang(language)
    hu, H = lang == "hu", _HEAD[lang]
    if (card := _failed(d.reason, lang, live)) is not None:
        return card
    det = d.details or {}
    who = _who(d.asking, names)
    flow = (f"Előremenő cél: {_n(d.flow_setpoint, lang)} °C." if hu else f"Flow target: {_n(d.flow_setpoint, lang)} °C.") \
        if d.flow_setpoint is not None else None
    stuck = det.get("stuck") or []
    stuck_line = (f"Nem nyit a szelep: {_who(stuck, names)} – nézd meg a szelepet vagy a visszajelzését." if hu
                  else f"A valve does not open: {_who(stuck, names)} – check the valve or its feedback.") if stuck else None
    r = d.reason
    if r == "heating":
        return _card(HEATING, H[HEATING], [f"Hőt kér: {who}." if hu else f"Asking for heat: {who}.", flow, stuck_line], live, lang)
    if r == "waiting_valves":
        return _card(WAITING, H[WAITING], [
            f"Hőt kér: {who}, de a zónaszelepek még nem nyitottak ki." if hu
            else f"Asking for heat: {who}, but the zone valves have not opened yet.", stuck_line], live, lang)
    if r == "min_on":
        return _card(HEATING, H[HEATING], [
            "A zónák már nem kérnek hőt, de a legrövidebb égésidőt kivárja (a kazán védelme)." if hu
            else "The zones ask for no more heat, but it waits out the shortest run (protecting the boiler)."], live, lang)
    if r == "min_off":
        return _card(WAITING, H[WAITING], [
            f"Hőt kér: {who}, de a legrövidebb szünet még tart – utána indul." if hu
            else f"Asking for heat: {who}, but the shortest pause is not over yet – then it starts."], live, lang)
    if r == "valves_closed":
        return _card(IDLE, H[IDLE], [
            "Leállt: a zónaszelepek bezártak, nincs hova adni a hőt." if hu
            else "Stopped: the zone valves closed, there is nowhere to put the heat.", stuck_line], live, lang)
    return _card(IDLE, H[IDLE], ["Egyik zóna sem kér hőt." if hu else "No zone asks for heat."], live, lang)


# --- the mixing circuit -------------------------------------------------------------------------------------------
def summarize_circuit(d, language: str = "en", live: bool = True, names: dict | None = None) -> dict:
    lang = _lang(language)
    hu, H = lang == "hu", _HEAD[lang]
    if (card := _failed(d.reason, lang, live)) is not None:
        return card
    if d.target is None:
        return _card(OFF, H[OFF], ["Nincs kiadott előremenő cél." if hu else "No flow target given out."], live, lang)
    tgt = _n(d.target, lang)
    out = (f" Kint {_n(d.outdoor, lang)} °C." if hu else f" Outdoors {_n(d.outdoor, lang)} °C.") if d.outdoor is not None else ""
    cap = None
    if d.cap_state == "limited" or (d.shortfall or 0) >= 0.5:
        cap = (f"A görbe {_n(d.demand_target, lang)} °C-ot kérne, de a puffer most csak {tgt} °C-ot ad." if hu
               else f"The curve would ask for {_n(d.demand_target, lang)} °C, but the tank gives only {tgt} °C now.")
    elif d.cap_state == "cold":
        cap = ("A puffer hideg: a kör a legkisebb előremenőn megy." if hu else "The tank is cold: the circuit runs on its lowest flow.")
    elif d.cap_state in ("stale", "no_data"):
        cap = ("A puffer hőmérséklete régi vagy hiányzik – a korlát most nem biztos." if hu
               else "The tank's temperature is old or missing – the cap is not certain now.")
    held = None
    if d.raw is not None and abs(float(d.raw) - float(d.target)) >= 0.5 and d.reason in ("confirming", "min_interval", "deadband", "ramp"):
        held = (f"A számolt cél {_n(d.raw, lang)} °C; a változást fokozatosan adja ki." if hu
                else f"The worked-out target is {_n(d.raw, lang)} °C; the change is given out step by step.")
    if d.demand:
        who = _who(d.lasting or d.asking, names)
        return _card(HEATING, H[HEATING], [
            (f"Kiadott előremenő: {tgt} °C.{out}" if hu else f"Flow given out: {tgt} °C.{out}"), cap, held,
            (f"Tartós hőigény: {who}." if hu else f"Lasting demand: {who}.")
            if who else None], live, lang)
    return _card(IDLE, H["no_demand"], [
        f"Egyik zóna sem kér tartósan hőt: a kör alapcélon megy ({tgt} °C).{out}" if hu
        else f"No zone asks for heat for long: the circuit runs on its base target ({tgt} °C).{out}", cap], live, lang)


# --- the heat pump coordination -----------------------------------------------------------------------------------
HP_WHY = {
    "hu": {"fail_safe_on": "Nincs kinti mérés, ezért biztonsági okból bekapcsolva.",
           "no_outdoor": "Nincs kinti mérés: az előző állapot marad.",
           "no_buffer": "Nincs pufferhőmérséklet: az előző állapot marad.",
           "cold_on": "Hideg van kint, ezért bekapcsolva tartja.", "frost": "Fagyvédelem: tölt.",
           "low_charge": "Alacsony a puffer töltöttsége, ezért tölt.", "heat_needed": "Hő kell a zónáknak, ezért tölt.",
           "heating": "Tölti a puffert.", "charging": "Tölti a puffert.",
           "wood": "Más hőforrás (fatüzelés) tölti a puffert, a hőszivattyú pihen.", "summer": "Nyári üzem: nem fűt.",
           "idle_off": "Régóta nincs hőigény, ezért kikapcsolva.", "standby": "Készenlétben: bekapcsolva, de nem fűt.",
           "off": "Nincs igény, nem tölt.", "min_on": "A legrövidebb futásidőt még kivárja.",
           "min_off": "Töltene, de a legrövidebb szünet még tart.",
           "reserve_low": "Kevés a tartalék a pufferben, ezért tölt.",
           "reserve_low_kwh": "Kevés a hő-tartalék (kWh) a pufferben, ezért tölt.",
           "charging_reserve": "Tartalékot tölt a pufferbe.", "reserve_ok": "Van elég tartalék a pufferben, nem kell tölteni.",
           "reserve_full": "Feltöltve: megvan a tartalék.", "no_demand": "Nincs tartós hőigény.",
           "reserve_runs_out": "A fogyás üteme szerint hamarosan elfogy a tartalék, ezért tölt."},
    "en": {"fail_safe_on": "No outdoor reading, so it is on for safety.",
           "no_outdoor": "No outdoor reading: the last state stays.",
           "no_buffer": "No tank temperature: the last state stays.",
           "cold_on": "It is cold outdoors, so it keeps it on.", "frost": "Frost protection: it charges.",
           "low_charge": "The tank's charge is low, so it charges.", "heat_needed": "The zones need heat, so it charges.",
           "heating": "It charges the tank.", "charging": "It charges the tank.",
           "wood": "Another source (wood) charges the tank; the heat pump rests.", "summer": "Summer mode: no heating.",
           "idle_off": "No heat demand for long, so it is off.", "standby": "Standby: on, but not heating.",
           "off": "No demand, no charging.", "min_on": "It waits out the shortest run.",
           "min_off": "It would charge, but the shortest pause is not over yet.",
           "reserve_low": "Little reserve in the tank, so it charges.",
           "reserve_low_kwh": "Little heat reserve (kWh) in the tank, so it charges.",
           "charging_reserve": "It charges a reserve into the tank.", "reserve_ok": "Enough reserve in the tank, no charge needed.",
           "reserve_full": "Charged: the reserve is there.", "no_demand": "No lasting heat demand.",
           "reserve_runs_out": "At this pace the reserve runs out soon, so it charges."},
}


def summarize_hp(d, language: str = "en", live: bool = True, names: dict | None = None) -> dict:
    lang = _lang(language)
    hu, H = lang == "hu", _HEAD[lang]
    if (card := _failed(d.reason, lang, live)) is not None:
        return card
    det = d.details or {}
    if d.summer:
        state, head = OFF, H["summer"]
    elif d.enable and d.heat_demand:
        state, head = HEATING, H["charging"]
    elif d.enable:
        state, head = IDLE, H["standby"]
    elif d.reason == "min_off":
        state, head = WAITING, H[WAITING]
    else:
        state, head = IDLE, H[OFF]
    tank = None
    if det.get("top") is not None:
        charge = det.get("charge")
        tank = (f"A puffer teteje {_n(det['top'], lang)} °C" + (f", töltöttsége {round(float(charge))} %." if charge is not None else ".")
                if hu else f"The tank's top is {_n(det['top'], lang)} °C" + (f", its charge {round(float(charge))} %." if charge is not None else "."))
    target = (f"Kiadott előremenő cél: {_n(d.target, lang)} °C." if hu else f"Flow target given out: {_n(d.target, lang)} °C.") \
        if d.target is not None and d.enable and d.heat_demand else None
    return _card(state, head, [HP_WHY[lang].get(d.reason, str(d.reason)), tank, target], live, lang)

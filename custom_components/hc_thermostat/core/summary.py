"""0.84.0: "why heating / why not" – the decision in a few plain lines, above the technical details.

A state word (heating, not heating, paused, waiting, fault, off, cooling), why in everyday words, where the target
comes from, when it changes next and – only where it is certain – what the user can do. Only what the decision and
the supervisor already know is used: no number is made up, a line that cannot be told is left out. The technical
sentence (core/messages.py) stays as it is below it.
"""

from __future__ import annotations

from datetime import datetime

from .model import Decision, Reason

# the state of each reason: (key, regardless of the output?) – None: from the output (heating / not heating)
HEATING, IDLE, PAUSED, WAITING, FAULT, OFF, COOLING = "heating", "idle", "paused", "waiting", "fault", "off", "cooling"

STATE_OF: dict[Reason, str | None] = {
    Reason.REGULATING: None, Reason.AT_TARGET: IDLE, Reason.BOOST: HEATING, Reason.AFTERHEAT: WAITING,
    Reason.FROST: HEATING, Reason.DISABLED: OFF, Reason.SENSOR_LOST: FAULT, Reason.WINDOW: PAUSED,
    Reason.SEASON_OFF: OFF, Reason.RESTART_HOLD: WAITING, Reason.RESTART_BURN: WAITING, Reason.EXTERNAL: None,
    Reason.VALVE_EXERCISE: WAITING, Reason.AC_HEAT: HEATING, Reason.AC_COOL: COOLING, Reason.AC_PAUSE: PAUSED,
    Reason.FLOOR_LIMIT: PAUSED, Reason.FLOOR_COOL: COOLING, Reason.DEW_POINT: PAUSED, Reason.STORAGE_CHARGE: HEATING,
    Reason.STORAGE_WAIT: IDLE, Reason.FLOOR_TEMPER: HEATING, Reason.THERMOSTAT_CALL: HEATING,
    Reason.THERMOSTAT_IDLE: IDLE, Reason.MANAGED_OFF: OFF, Reason.SAFETY_STOP: FAULT,
}

STATE_WORDS = {
    "hu": {HEATING: "Fűt", IDLE: "Nem fűt", PAUSED: "Szünetel", WAITING: "Vár", FAULT: "Hiba", OFF: "Ki",
           COOLING: "Hűt"},
    "en": {HEATING: "Heating", IDLE: "Not heating", PAUSED: "Paused", WAITING: "Waiting", FAULT: "Fault", OFF: "Off",
           COOLING: "Cooling"},
}

# why, in everyday words; {where}: "a ház" / "a helyiség" (the house / the room), {Where} capitalised
WHY = {
    "hu": {
        "regulating_on": "{Where} a cél alatt van (bent {indoor} °C, cél {target} °C).",
        "regulating_off": "Most szünet a fűtési szakaszok között: a hőt adagolva adja, hogy ne lője túl (bent {indoor} °C, cél {target} °C).",
        Reason.AT_TARGET: "{Where} elérte a célt (bent {indoor} °C, cél {target} °C).",
        Reason.BOOST: "Gyors felfűtés a {target} °C-os célig, legkésőbb {until}-ig.",
        Reason.AFTERHEAT: "A felfűtés után a radiátorok még melegítenek, addig nem indul újra.",
        Reason.FROST: "Fagyvédelem: bent a határ alá hűlt, ezért fűt.",
        Reason.DISABLED: "A termosztát ki van kapcsolva.",
        Reason.SENSOR_LOST: "A hőmérő nem küld friss adatot, ezért tartalék üzemben megy.",
        Reason.WINDOW: "Nyitva van egy ablak vagy ajtó.",
        "window_drop": "Gyorsan esik a hőmérséklet – valószínűleg nyitva van egy ablak.",
        Reason.SEASON_OFF: "Nyári pihenő: kint melegebb a napi átlag, a fűtési idény szünetel.",
        Reason.RESTART_HOLD: "Újraindulás után megvárja a friss mérést, utána dönt.",
        Reason.RESTART_BURN: "Újraindulás után leállít egy fölösleges égést.",
        Reason.EXTERNAL: "A fűtést a termosztát kapcsolja; a HC {target} °C-os célt adott neki.",
        Reason.VALVE_EXERCISE: "Rövid szelepmozgatás, hogy a régóta zárt szelep ne ragadjon be; a kazán nem indul.",
        Reason.AC_HEAT: "A klíma fűt a {target} °C-os célig.",
        Reason.AC_COOL: "A klíma hűt.",
        Reason.AC_PAUSE: "A klíma szünetel: a legkisebb fokozaton is túllőne a célon.",
        Reason.FLOOR_LIMIT: "A padló elérte a megengedett hőfokot, vissza kell hűlnie.",
        Reason.FLOOR_COOL: "Padlóhűtés a {target} °C-os célig.",
        Reason.DEW_POINT: "Túl párás a levegő: a padló most nem hűthető (harmatpont-védelem).",
        Reason.STORAGE_CHARGE: "A hőtároló töltődik a vezérelt áramos időszakban.",
        Reason.STORAGE_WAIT: "A hőtároló most nem töltődik.",
        Reason.FLOOR_TEMPER: "{Where} elég meleg, csak a padlót tartja langyosan.",
        Reason.THERMOSTAT_CALL: "A fali termosztát fűtést kér.",
        Reason.THERMOSTAT_IDLE: "A fali termosztát nem kér fűtést.",
        Reason.MANAGED_OFF: "A termosztátot kézzel kikapcsolták, a HC nem kapcsolja vissza.",
        Reason.SAFETY_STOP: "Életvédelmi leállítás: egy biztonsági érzékelő (füst, gáz, CO, víz) jelzett, minden fűtés áll.",
        "coast": "Most állt le, és bent még emelkedik a hőmérséklet: kivárja, mielőtt újraindul.",
        "pre_change": "Hamarosan alacsonyabb lesz a cél, és bent már most melegebb: nem indít új égést.",
        "preheat_soon": "Pár perc múlva indul a reggeli felfűtés, addig nem indít rövid égést.",
        "load_limit": "Más elektromos fűtés használja most a teljesítménykeretet, ez a fűtés a sorára vár.",
        "min_off": "Fűtést kér (bent {indoor} °C, cél {target} °C), de a legrövidebb szünet még tart – utána indul (a kazán védelme).",
        "min_on": "A cél közelében van, de a legrövidebb égésidőt még kivárja (a kazán védelme).",
        "return_limit": "A visszatérő víz túl meleg, a szelep zárva marad, amíg le nem hűl.",
        "no_power": "Nincs vezérelt áram, most nem fűthet.",
    },
    "en": {
        "regulating_on": "{Where} is below its target ({indoor} °C inside, target {target} °C).",
        "regulating_off": "A pause between heating runs: it doses the heat so it does not overshoot ({indoor} °C inside, target {target} °C).",
        Reason.AT_TARGET: "{Where} has reached its target ({indoor} °C inside, target {target} °C).",
        Reason.BOOST: "A quick heat-up to {target} °C, until {until} at the latest.",
        Reason.AFTERHEAT: "The radiators still give heat after the heat-up; no new start until then.",
        Reason.FROST: "Frost protection: it got colder inside than the limit, so it heats.",
        Reason.DISABLED: "The thermostat is switched off.",
        Reason.SENSOR_LOST: "The thermometer sends no fresh reading, so it runs on its fallback.",
        Reason.WINDOW: "A window or a door is open.",
        "window_drop": "The temperature falls fast – probably a window is open.",
        Reason.SEASON_OFF: "Summer rest: the outdoor daily average is warm, the heating season pauses.",
        Reason.RESTART_HOLD: "After a restart it waits for a fresh reading before it decides.",
        Reason.RESTART_BURN: "After a restart it stops an unnecessary burn.",
        Reason.EXTERNAL: "The thermostat switches the heating; HC gave it a {target} °C target.",
        Reason.VALVE_EXERCISE: "A short valve exercise so the long-closed valve does not seize; the boiler does not start.",
        Reason.AC_HEAT: "The air conditioner heats to {target} °C.",
        Reason.AC_COOL: "The air conditioner cools.",
        Reason.AC_PAUSE: "The air conditioner pauses: even at its lowest it would overshoot the target.",
        Reason.FLOOR_LIMIT: "The floor reached its allowed temperature and has to cool down.",
        Reason.FLOOR_COOL: "Floor cooling to {target} °C.",
        Reason.DEW_POINT: "The air is too humid: the floor cannot be cooled now (dew point protection).",
        Reason.STORAGE_CHARGE: "The storage heater charges in the off-peak hours.",
        Reason.STORAGE_WAIT: "The storage heater does not charge now.",
        Reason.FLOOR_TEMPER: "{Where} is warm enough; it only keeps the floor lukewarm.",
        Reason.THERMOSTAT_CALL: "The wall thermostat asks for heat.",
        Reason.THERMOSTAT_IDLE: "The wall thermostat asks for no heat.",
        Reason.MANAGED_OFF: "The thermostat was switched off by hand; HC does not switch it back on.",
        Reason.SAFETY_STOP: "Life-safety stop: a safety detector (smoke, gas, CO, water) went off, all heating stands.",
        "coast": "It just stopped and it is still getting warmer inside: it waits before starting again.",
        "pre_change": "The target goes down soon and it is already warmer inside: no new start.",
        "preheat_soon": "The morning heat-up starts in a few minutes; no short run until then.",
        "load_limit": "Other electric heating uses the power budget now; this one waits for its turn.",
        "min_off": "It asks for heat ({indoor} °C inside, target {target} °C), but the shortest pause is not over yet – then it starts (protecting the boiler).",
        "min_on": "It is near the target, but waits out the shortest run time (protecting the boiler).",
        "return_limit": "The return water is too warm; the valve stays closed until it cools.",
        "no_power": "No off-peak power now, so it cannot heat.",
    },
}

PRESET_WORDS = {
    "hu": {"comfort": "Komfort", "home": "Otthon", "sleep": "Alvás", "eco": "Eco", "away": "Távol",
           "vacation": "Szabadság", "boost": "Gyors felfűtés"},
    "en": {"comfort": "Comfort", "home": "Home", "sleep": "Sleep", "eco": "Eco", "away": "Away",
           "vacation": "Vacation", "boost": "Boost"},
}

# reasons where the target is what the user wants to know about
_TARGET_REASONS = {Reason.REGULATING, Reason.AT_TARGET, Reason.BOOST, Reason.AFTERHEAT, Reason.EXTERNAL,
                   Reason.AC_HEAT, Reason.FLOOR_TEMPER}
_NEXT_REASONS = {Reason.REGULATING, Reason.AT_TARGET, Reason.AFTERHEAT, Reason.EXTERNAL, Reason.AC_HEAT,
                 Reason.FLOOR_TEMPER, Reason.SENSOR_LOST}
_OWN_OUTPUT = {Reason.EXTERNAL, Reason.THERMOSTAT_CALL, Reason.THERMOSTAT_IDLE, Reason.AC_HEAT, Reason.AC_COOL,
               Reason.AC_PAUSE, Reason.FLOOR_COOL, Reason.DEW_POINT}


def _n(v, lang: str) -> str:
    if v is None:
        return "–"
    t = f"{float(v):.1f}".rstrip("0").rstrip(".")
    return t.replace(".", ",") if lang == "hu" else t


def _t(v) -> str | None:
    return v.strftime("%H:%M") if isinstance(v, datetime) else None


def _target_line(d: Decision, ctx: dict, lang: str) -> str | None:
    hu, tgt = lang == "hu", _n(d.target, lang)
    names = PRESET_WORDS[lang]
    early = ctx.get("early")
    if d.manual:
        until = _t(d.manual_until)
        return (f"A cél {tgt} °C, kézzel állítva – " + (f"{until}-ig." if until else "a következő ütemezett váltásig.")
                if hu else f"The target is {tgt} °C, set by hand – " + (f"until {until}." if until else "until the next scheduled change."))
    if early and ctx.get("preset") is None:
        until = _t(early.get("until"))
        return (f"A cél már most {tgt} °C: reggeli felfűtés, hogy {until}-ra meglegyen." if hu
                else f"The target is already {tgt} °C: the morning heat-up, so it is reached by {until}.")
    preset = ctx.get("preset")
    if preset and preset != "boost":
        until = _t(ctx.get("preset_until"))
        when = ((f"{until}-ig" if until else "hazaérkezésig" if ctx.get("preset_until_home") else "visszavonásig") if hu
                else (f"until {until}" if until else "until someone comes home" if ctx.get("preset_until_home") else "until changed"))
        return (f"A cél {tgt} °C: {names.get(preset, preset)} előbeállítás, {when}." if hu
                else f"The target is {tgt} °C: the {names.get(preset, preset)} preset, {when}.")
    presence = ctx.get("presence")
    if presence == "vacation":
        return f"A cél {tgt} °C, mert szabadságon vagytok." if hu else f"The target is {tgt} °C: you are on vacation."
    if presence == "away":
        return f"A cél {tgt} °C, mert senki sincs otthon." if hu else f"The target is {tgt} °C: nobody is home."
    level = ctx.get("week_level")
    if level:
        return (f"A cél {tgt} °C: a heti program szerint most {names.get(level, level)}." if hu
                else f"The target is {tgt} °C: the weekly program's {names.get(level, level)} level now.")
    active = ctx.get("active")
    if active == "sleep":
        start, end = (ctx.get("night") or ("", ""))[:2]
        return (f"A cél {tgt} °C, mert éjszaka van ({start}–{end})." if hu
                else f"The target is {tgt} °C: it is night ({start}–{end}).")
    if active == "home":
        return f"A cél {tgt} °C: nappali, otthoni cél." if hu else f"The target is {tgt} °C: the daytime home target."
    return None


def _next_line(d: Decision, ctx: dict, lang: str, season_on_below: float | None) -> str | None:
    hu = lang == "hu"
    if d.reason == Reason.WINDOW:
        return "Becsukás után folytatja." if hu else "It goes on once it is closed."
    if d.reason == Reason.SEASON_OFF and season_on_below is not None:
        v = _n(season_on_below, lang)
        return (f"Visszakapcsol, ha a kinti napi átlag {v} °C alá esik." if hu
                else f"It comes back when the outdoor daily average falls below {v} °C.")
    if d.reason == Reason.VALVE_EXERCISE and _t((d.details or {}).get("until") or (d.details or {}).get("exercise_until")):
        at = _t((d.details or {}).get("until") or (d.details or {}).get("exercise_until"))
        return f"{at}-kor véget ér." if hu else f"It ends at {at}."
    if d.reason not in _NEXT_REASONS or d.manual and d.manual_until is not None:
        return None
    at, nxt = ctx.get("next_at"), ctx.get("next_target")
    if not isinstance(at, datetime):
        return None
    if ctx.get("preset") and ctx.get("preset") != "boost":
        return (f"{_t(at)}-kor véget ér az előbeállítás, utána az ütemezés szerint megy." if hu
                else f"At {_t(at)} the preset ends and the schedule takes over.")
    if nxt is None or abs(float(nxt) - float(d.target)) < 0.05:
        return None
    up = float(nxt) > float(d.target)
    return ((f"{_t(at)}-kor a cél {_n(nxt, lang)} °C-ra " + ("nő." if up else "csökken.")) if hu
            else f"At {_t(at)} the target goes {'up' if up else 'down'} to {_n(nxt, lang)} °C.")


def _action_line(d: Decision, ctx: dict, lang: str, presets: tuple, state: str) -> str | None:
    hu, det = lang == "hu", d.details or {}
    if d.reason == Reason.WINDOW and not ctx.get("drop"):
        return "Csukd be az ablakot vagy az ajtót." if hu else "Close the window or the door."
    if d.reason == Reason.SENSOR_LOST or det.get("indoor_frozen"):
        return ("Nézd meg a hőmérő elemét és kapcsolatát." if hu
                else "Check the thermometer's battery and connection.")
    if d.reason == Reason.DISABLED:
        return "Bekapcsolás: a termosztát módja legyen Fűtés." if hu else "To switch on: set the thermostat to Heat."
    if d.reason == Reason.MANAGED_OFF:
        return "Kapcsold vissza a termosztáton." if hu else "Switch it back on at the thermostat."
    if d.reason == Reason.SAFETY_STOP:
        return ("Szüntesd meg a jelzés okát, majd nyugtázd a leállítást." if hu
                else "Remove the alarm's cause, then acknowledge the stop.")
    if d.manual and d.reason in (Reason.REGULATING, Reason.AT_TARGET):
        return ("A kézi cél törlése: válaszd az Auto előbeállítást." if hu
                else "To drop the manual target: choose the Auto preset.")
    if d.reason in (Reason.REGULATING, Reason.AT_TARGET) and state == IDLE:
        offer = [w for p, w in (("comfort", "Komfort" if hu else "Comfort"), ("boost", "Gyors felfűtés" if hu else "Boost"))
                 if p in presets]
        if offer:
            joined = (" vagy " if hu else " or ").join(offer)
            return f"Ha most melegebb kell: {joined}." if hu else f"If you want it warmer now: {joined}."
    return None


def summarize(d: Decision, ctx: dict | None = None, language: str = "en", room: bool = False, live: bool = True,
              actual: bool | None = None, presets: tuple = (), season_on_below: float | None = None) -> dict:
    """The plain summary of one decision: {state, headline, lines, shadow}. `ctx`: Supervisor.summary_context()."""
    lang = "hu" if str(language).startswith("hu") else "en"
    hu, ctx, det = lang == "hu", ctx or {}, d.details or {}
    state = STATE_OF.get(d.reason)
    if state is None:
        state = HEATING if d.output else IDLE
    words = WHY[lang]
    where = ("a helyiség" if room else "a ház") if hu else ("the room" if room else "the house")
    fill = {"where": where, "Where": where[:1].upper() + where[1:], "indoor": _n(d.indoor, lang),
            "target": _n(d.target, lang), "until": _t(det.get("until")) or "–"}
    key = d.reason
    if d.reason == Reason.REGULATING:
        key = "regulating_on" if d.output else "regulating_off"
    if d.reason == Reason.WINDOW and ctx.get("drop"):
        key = "window_drop"
    for limit in ("coast", "pre_change", "preheat_soon", "load_limit", "min_off", "return_limit", "no_power"):
        if d.limited_by == limit and not d.output:
            key = limit
    if d.limited_by == "min_on" and d.output and d.reason == Reason.REGULATING:
        key = "min_on"
    why = words[key].format(**fill)
    if det.get("indoor_frozen"):
        why += (" A hőmérő órák óta ugyanazt mutatja, beragadt mérésnek veszi." if hu
                else " The thermometer has shown the same value for hours; it is treated as stuck.")
    lines = [why]
    if d.reason in _TARGET_REASONS:
        line = _target_line(d, ctx, lang)
        if line:
            lines.append(line)
    line = _next_line(d, ctx, lang, season_on_below)
    if line:
        lines.append(line)
    if live and actual is True and not d.output and d.reason not in _OWN_OUTPUT:
        lines.append("Közben mégis fűt: a kazán meleg vizet készíthet, vagy más is kapcsolja a kimenetet." if hu
                     else "It heats anyway: the boiler may be making hot water, or something else switches the output.")
    line = _action_line(d, ctx, lang, tuple(presets or ()), state)
    if line:
        lines.append(line)
    headline = STATE_WORDS[lang][state]
    return {"state": state, "headline": headline, "lines": lines, "shadow": not live,
            "note": ("Árnyék mód: ezt tenné, de nem kapcsol." if hu else "Shadow mode: this is what it would do; it switches nothing.")
            if not live else None}


def as_markdown(summary: dict) -> str:
    """0.86.0: for a config flow page – the state word bold, the lines as a list."""
    head = ([f"*{summary['note']}*"] if summary.get("note") else []) + [f"**{summary['headline']}**"]
    return "\n\n".join(head) + "\n" + "\n".join(f"- {x}" for x in summary["lines"])


def as_text(summary: dict) -> str:
    """One paragraph (a sensor attribute, a notification, a voice answer)."""
    parts = ([summary["note"]] if summary.get("note") else []) + [f"{summary['headline']}."] + list(summary["lines"])
    return " ".join(parts)


# --- a TRV room (0.84.0): its own target and valve heads ----------------------------------------------------------
ROOM_WHY = {
    "hu": {"follow": "a ház célját követi", "home": "saját otthoni cél", "night": "saját éjszakai cél",
           "household_away": "senki sincs otthon", "household_vacation": "szabadságon vagytok",
           "absent": "senki sincs a helyiségben, ezért csökkentve", "manual": "kézzel állítva (a következő változásig)",
           "preset_home": "előbeállítás: jelen van", "preset_away": "előbeállítás: távol",
           "leading": "vezető helyiség: a ház célja", "house": "a ház célja"},
    "en": {"follow": "it follows the house target", "home": "its own home target", "night": "its own night target",
           "household_away": "nobody is home", "household_vacation": "you are on vacation",
           "absent": "nobody is in the room, so it is set back", "manual": "set by hand (until the next change)",
           "preset_home": "preset: present", "preset_away": "preset: away",
           "leading": "the leading room: the house target", "house": "the house target"},
}


def summarize_room(room: dict, language: str = "en") -> dict:
    """A TRV room's plain summary from its state (coordinator.room_states)."""
    lang = "hu" if str(language).startswith("hu") else "en"
    hu = lang == "hu"
    reason, temp, target = room.get("reason"), room.get("temperature"), room.get("target")
    if room.get("enabled") is False or reason == "off":
        state = OFF
    elif room.get("window") or reason == "window":
        state = PAUSED
    elif temp is None:
        state = FAULT
    else:
        state = HEATING if room.get("heating") else IDLE
    lines = []
    if state == PAUSED:
        lines.append("Nyitva az ablak: a szelepfejek fagyvédelmen." if hu else "The window is open: the heads are on frost protection.")
        lines.append("Becsukás után folytatja." if hu else "It goes on once it is closed.")
    elif state == OFF:
        lines.append("A helyiség ki van kapcsolva (fagyvédelem)." if hu else "The room is switched off (frost protection).")
    elif state == FAULT:
        lines.append("A helyiség hőmérője nem küld adatot." if hu else "The room's thermometer sends no reading.")
        lines.append("Nézd meg a hőmérő elemét és kapcsolatát." if hu else "Check the thermometer's battery and connection.")
    else:
        t, g = _n(temp, lang), _n(target, lang)
        why = ROOM_WHY[lang].get(str(reason), "")
        lines.append((f"Bent {t} °C, a cél {g} °C" + (f" – {why}." if why else ".")) if hu
                     else f"{t} °C inside, target {g} °C" + (f" – {why}." if why else "."))
        if state == HEATING:
            lines.append("A szelepfejek nyitva, a helyiség fűtést kap." if hu else "The heads are open, the room gets heat.")
        elif target is not None and temp < target - 0.3:
            lines.append("A fejek nyitni akarnak, de a kazán most nem fűt – a ház döntése szerint." if hu
                         else "The heads want to open, but the boiler is not heating now – by the house's decision.")
        if room.get("asking"):
            lines.append("Fűtést kér a kazántól." if hu else "It asks the boiler for heat.")
    return {"state": state, "headline": STATE_WORDS[lang][state], "lines": lines, "shadow": False, "note": None}

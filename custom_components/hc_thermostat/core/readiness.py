"""0.83.0: the go-live checklist – what an instance still lacks before it may switch the heating.

Three levels: "block" (going live is refused until it is solved), "warn" (going live is allowed, but worth fixing) and
"ok" / "info" (for the record). The facts are gathered by `readiness.py` (Home Assistant's states, the instance's
own data); this module only judges them, so every rule is tested without Home Assistant.

Nothing here switches, changes a setting or goes live on its own: the list is shown in the "Go live" step, the HC
info panel and at the end of the setup wizard, and only the "Go live" steps refuse while a blocker is open.
"""

from __future__ import annotations

from dataclasses import dataclass, field

BLOCK, WARN, OK, INFO = "block", "warn", "ok", "info"
SHADOW_MIN_H = 24.0  # a day in shadow mode before going live (a warning, not a blocker)
STALE_S = 2 * 3600  # an input that has not reported for two hours


@dataclass
class EntityFact:
    key: str  # the setting's key (indoor_entity, actuator_entity, ...)
    entity_id: str
    kind: str  # "core" (the input the decision stands on), "input" (any other input), "output", "trv" (a valve head)
    exists: bool = True
    available: bool = True
    age_s: float | None = None  # since its last report (None: unknown)
    problem: str | None = None  # what the instance itself says: lost / stale / out_of_range / jump


@dataclass
class Facts:
    role: str = "standalone"
    live: bool = False
    control: str | None = None
    entities: list[EntityFact] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)  # required, but not set (keys)
    hc_conflicts: list[tuple[str, str]] = field(default_factory=list)  # (output, the other HC instance)
    automations: list[tuple[str, list[str]]] = field(default_factory=list)  # (output, automations / scripts)
    static: bool = False  # only the settings (a new instance from the wizard): no run to judge yet
    decided: bool = False  # at least one decision went through
    shadow_h: float | None = None  # hours in shadow mode so far
    step_errors: int = 0  # failed decisions in a row now
    faults_24h: int = 0  # decisions with a fault in the last day
    safety: bool | None = None  # the life-safety stop tripped (None: no safety inputs)
    guard: str | None = None  # None: no local guard; "ok"; otherwise its error
    guard_fits: bool = False  # a relay the local guard could take (a suggestion when there is none)
    targets: dict[str, float] | None = None
    night: tuple[str, str] | None = None
    settings: dict | None = None  # 0.85.0: the regulation settings with the system's recommended values (risks)


@dataclass
class Item:
    id: str
    level: str
    params: dict = field(default_factory=dict)


def _fmt_age(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    minutes = int(seconds // 60)
    return f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"


def evaluate(f: Facts) -> list[Item]:
    items: list[Item] = []
    add = lambda id_, level, **p: items.append(Item(id_, level, p))  # noqa: E731

    # --- what is missing from the settings -------------------------------------------------------------------------
    for key in f.missing:
        add("missing", BLOCK, key=key)

    # --- inputs and outputs ----------------------------------------------------------------------------------------
    for e in f.entities:
        core = e.kind in ("core", "output")
        if not e.exists:
            add("entity_gone", BLOCK if core else WARN, key=e.key, entity=e.entity_id)
        elif not e.available:
            add("entity_unavailable", BLOCK if core else WARN, key=e.key, entity=e.entity_id)
        elif e.kind in ("core", "input") and (e.problem in ("lost", "stale") or (e.age_s is not None and e.age_s > STALE_S)):
            add("entity_stale", WARN, key=e.key, entity=e.entity_id, age=_fmt_age(e.age_s))
        elif e.kind in ("core", "input") and e.problem in ("out_of_range", "jump"):
            add("entity_implausible", WARN, key=e.key, entity=e.entity_id, why=e.problem)
    if f.entities and not any(i.id.startswith("entity_") or i.id == "missing" for i in items):
        add("entities_ok", OK, n=len(f.entities))

    # --- one writer per output -------------------------------------------------------------------------------------
    for entity, other in f.hc_conflicts:
        add("hc_conflict", BLOCK, entity=entity, other=other)
    for entity, names in f.automations:
        add("automation_conflict", WARN, entity=entity, names=", ".join(names[:5]) + (" …" if len(names) > 5 else ""))

    # --- the shadow run --------------------------------------------------------------------------------------------
    if not f.static:
        if not f.decided:
            add("no_decision", BLOCK)
        elif not f.live and f.shadow_h is not None and f.shadow_h < SHADOW_MIN_H:
            add("short_shadow", WARN, hours=round(f.shadow_h, 1), need=int(SHADOW_MIN_H))
        elif not f.live and f.shadow_h is not None:
            add("shadow_ok", OK, hours=int(f.shadow_h))
        if f.step_errors:
            add("failing", WARN, n=f.step_errors)
        elif f.faults_24h:
            add("faults", WARN, n=f.faults_24h)

    # --- protections -----------------------------------------------------------------------------------------------
    if f.safety is True:
        add("safety_tripped", BLOCK)
    elif f.safety is False:
        add("safety_ok", OK)
    if f.guard is not None:
        if f.guard == "ok":
            add("guard_ok", OK)
        else:
            add("guard_unreachable", BLOCK, error=f.guard)
    elif f.guard_fits:
        add("guard_suggested", INFO)

    # --- settings that contradict each other -----------------------------------------------------------------------
    t = f.targets or {}
    frost = t.get("frost_temp")
    if frost is not None:
        low = [k for k in ("target_vacation", "target_away", "target_night", "target_home")
               if t.get(k) is not None and t[k] <= frost]
        if low:
            add("targets_below_frost", WARN, keys=low, frost=frost)
    home = t.get("target_home")
    if home is not None:
        high = [k for k in ("target_night", "target_away", "target_vacation") if t.get(k) is not None and t[k] > home]
        if high:
            add("targets_above_home", WARN, keys=high, home=home)
    items.extend(setting_risks(f.settings))
    if f.night and f.night[0] and f.night[0] == f.night[1]:
        add("night_empty", INFO, at=f.night[0])  # the same start and end: no night on purpose (core/schedule.py)
    return items


HP_MIN_ON_S, HP_MIN_OFF_S = 1200.0, 600.0  # the heat pump's defaults (core/model.py HcConfig)


def setting_risks(st: dict | None) -> list[Item]:
    """0.85.0: settings far from what HC recommends for this heat source and system – warnings, never blockers
    (there may be a reason). The recommended values are HC's own defaults (core/matrix.py default_timing, HcConfig)."""
    if not st:
        return []
    out: list[Item] = []
    rec = st.get("rec") or {}

    def low(key, value, recommended, threshold=None):
        if value is None or recommended is None:
            return
        limit = threshold if threshold is not None else recommended / 2
        if float(value) < limit:
            out.append(Item("risk_" + key, WARN, {"value": int(value), "rec": int(recommended)}))

    if st.get("pwm"):
        low("min_off_s", st.get("min_off_s"), rec.get("min_off_s"))
        low("min_on_s", st.get("min_on_s"), rec.get("min_on_s"))
        water_floor = st.get("floor") and not st.get("electric_floor")
        low("cycle_s", st.get("cycle_s"), rec.get("cycle_s"), 1200.0 if water_floor else None)
    if st.get("heat_pump"):
        low("hp_min_on_s", st.get("hp_min_on_s"), HP_MIN_ON_S)
        low("hp_min_off_s", st.get("hp_min_off_s"), HP_MIN_OFF_S)
    if st.get("floor") and st.get("floor_limit") is not None:
        top = 27.0 if st.get("electric_floor") else 29.0
        if float(st["floor_limit"]) > top:
            out.append(Item("risk_floor_limit", WARN, {"value": f"{float(st['floor_limit']):g}", "rec": f"{top:g}"}))
    if st.get("frost_temp") is not None and float(st["frost_temp"]) < 5.0:
        out.append(Item("risk_frost_temp", WARN, {"value": f"{float(st['frost_temp']):g}"}))
    if st.get("curve") and st.get("floor") and st.get("flow_max") is not None and float(st["flow_max"]) > 45.0:
        out.append(Item("risk_flow_max", WARN, {"value": f"{float(st['flow_max']):g}"}))
    if st.get("guard") and st.get("guard_ttl_s") is not None and st.get("guard_every_s") \
            and float(st["guard_ttl_s"]) < 2 * float(st["guard_every_s"]):
        out.append(Item("risk_guard_ttl", WARN, {"value": int(st["guard_ttl_s"]), "every": int(st["guard_every_s"])}))
    return out


def summary(items: list[Item]) -> dict:
    blocks = sum(1 for i in items if i.level == BLOCK)
    warns = sum(1 for i in items if i.level == WARN)
    return {"ready": blocks == 0, "blocks": blocks, "warns": warns}


# --- words -------------------------------------------------------------------------------------------------------

KEY_WORDS = {
    "hu": {"indoor_entity": "belső hőmérő", "outdoor_entity": "kinti hőmérő", "actuator_entity": "kazán relé",
           "external_climate": "termosztát / klíma", "flow_setpoint_entity": "előremenő cél",
           "heat_enable_entity": "fűtés engedélyező", "room_sensors": "helyiség hőmérő", "zone_entities": "zónák",
           "boiler_entity": "hőtermelő kapcsoló", "pump_entity": "keringető szivattyú",
           "buffer_top_entity": "puffer felső hőmérő", "circuit_output_entity": "keverőkör előremenő cél",
           "circuit_buffer": "a kör puffere", "hp_buffer": "a hőszivattyú puffere", "hp_switch_entity": "hőszivattyú BE/KI",
           "hp_target_entity": "hőszivattyú előremenő cél", "hp_demand_entity": "hőszivattyú hőigény jel",
           "hp_summer_entity": "nyári üzem jel", "hp_exercise_entity": "megjáratás jel", "output": "kimenet",
           "target_home": "otthon", "target_night": "éjszaka", "target_away": "távol", "target_vacation": "szabadság",
           "room_trvs": "szelepfej", "floor_entity": "padló hőmérő", "trv_heads": "szelepfej"},
    "en": {"indoor_entity": "indoor sensor", "outdoor_entity": "outdoor sensor", "actuator_entity": "boiler relay",
           "external_climate": "thermostat / AC", "flow_setpoint_entity": "flow setpoint",
           "heat_enable_entity": "heating enable", "room_sensors": "room sensor", "zone_entities": "zones",
           "boiler_entity": "heat source switch", "pump_entity": "circulation pump",
           "buffer_top_entity": "tank top sensor", "circuit_output_entity": "circuit flow target",
           "circuit_buffer": "the circuit's tank", "hp_buffer": "the heat pump's tank", "hp_switch_entity": "heat pump ON/OFF",
           "hp_target_entity": "heat pump flow target", "hp_demand_entity": "heat pump demand signal",
           "hp_summer_entity": "summer mode signal", "hp_exercise_entity": "exercise signal", "output": "output",
           "target_home": "home", "target_night": "night", "target_away": "away", "target_vacation": "vacation",
           "room_trvs": "valve head", "floor_entity": "floor sensor", "trv_heads": "valve head"},
}

# id -> (title, where to fix it); {key} is the setting's name in words
WORDS = {
    "hu": {
        "missing": ("Hiányzik: {key}", "Hőmérők és ablakok, illetve kimenetnél: Más eszköz vezérli a fűtést"),
        "entity_gone": ("{key} nem létezik: {entity}", "Hőmérők és ablakok – kimenetnél: Más eszköz vezérli a fűtést (átnevezték vagy törölték?)"),
        "entity_unavailable": ("{key} nem elérhető: {entity}", "Nézd meg az eszközt (elem, hálózat, integráció)"),
        "entity_stale": ("{key} régóta nem küldött adatot ({age}): {entity}", "Nézd meg az eszköz elemét és kapcsolatát"),
        "entity_implausible": ("{key} értéke valószínűtlen: {entity}", "Nézd meg az érzékelő helyét és mérését"),
        "entities_ok": ("Mind a(z) {n} érzékelő és kimenet elérhető", ""),
        "hc_conflict": ("Egy másik HC-példány ({other}) is vezérli: {entity}", "Egy kimenetet csak egy példány vezérelhet"),
        "automation_conflict": ("Automatizálás is kapcsolja: {entity} ({names})", "Kapcsold ki ezeket, vagy győződj meg róla, hogy nem ütköznek a HC-vel"),
        "no_decision": ("Még nem volt sikeres döntés", "Várj néhány percet, és nézd meg a HC info panelt"),
        "short_shadow": ("Csak {hours} órája fut árnyék módban (javasolt: {need} óra)", "Nézd át az árnyék döntéseket a HC info panelen"),
        "shadow_ok": ("{hours} órája fut árnyék módban", ""),
        "failing": ("A döntés most hibára fut ({n}× egymás után)", "Nézd meg a naplót és a Javítások oldalt (Miért fűt / miért nem?)"),
        "faults": ("Az elmúlt napban {n} hibás döntés volt", "Nézd meg a döntési naplót a HC info panelen"),
        "safety_tripped": ("Az életvédelmi leállítás ki van oldva", "Szüntesd meg az okát, majd nyugtázd"),
        "safety_ok": ("Az életvédelmi bemenetek rendben", ""),
        "guard_ok": ("A helyi védő elérhető", ""),
        "guard_unreachable": ("A helyi védő nem érhető el ({error})", "Szakértői beállítások → Helyi védő: cím, jelszó, a Shelly hálózata"),
        "guard_suggested": ("Nincs helyi védő (javasolt)", "Ha a HC vagy a HA leáll, a helyi védő a relén tartja a fagyvédelmet"),
        "targets_below_frost": ("Célhőmérséklet a fagyvédelem ({frost} °C) alatt vagy azon: {keys}", "Milyen meleg legyen, és mikor?"),
        "targets_above_home": ("Az otthoni cél ({home} °C) fölött: {keys}", "Milyen meleg legyen, és mikor?"),
        "risk_min_off_s": ("A minimális szünet ({value} s) kevesebb, mint az ajánlott ({rec} s) fele", "Szakértői beállítások → Szabályozás: túl sűrű indítás koptatja a kazánt és a relét"),
        "risk_min_on_s": ("A minimális futás ({value} s) kevesebb, mint az ajánlott ({rec} s) fele", "Szakértői beállítások → Szabályozás: a rövid égés alig ad hőt, sok indítással"),
        "risk_cycle_s": ("A ciklusidő ({value} s) túl rövid ehhez a rendszerhez (ajánlott: {rec} s)", "Szakértői beállítások → Szabályozás: rövid ciklusnál a szelep alig nyit ki, máris zár"),
        "risk_hp_min_on_s": ("A hőszivattyú legrövidebb futása ({value} s) kevesebb, mint az ajánlott ({rec} s) fele", "Szakértői beállítások → Szabályozás: a kompresszor rövid futásai koptatnak"),
        "risk_hp_min_off_s": ("A hőszivattyú legrövidebb szünete ({value} s) kevesebb, mint az ajánlott ({rec} s) fele", "Szakértői beállítások → Szabályozás: a kompresszornak pihennie kell két indítás között"),
        "risk_floor_limit": ("A padlóhatár {value} °C – a szokásos {rec} °C fölött", "Szakértői beállítások → Padló: túl meleg padló a burkolatot és a lábat is terheli"),
        "risk_frost_temp": ("A fagyvédelem csak {value} °C", "Milyen meleg legyen, és mikor?: 5 °C alatt a hidegebb falak mögött a cső már fagyhat"),
        "risk_flow_max": ("Padlón a görbe legnagyobb előremenője {value} °C (45 °C fölött)", "Szakértői beállítások → Szabályozás: a padló és az esztrich nem bírja a forró vizet"),
        "risk_guard_ttl": ("A helyi védő bérlete ({value} s) rövidebb, mint a megújítás ({every} s) kétszerese", "Szakértői beállítások → Helyi védő: egy kimaradt megújításnál már átvenné a vezérlést"),
        "night_empty": ("Nincs éjszakai csökkentés (kezdete és vége ugyanaz: {at})", "Ha kell éjszakai időszak: Milyen meleg legyen, és mikor?"),
    },
    "en": {
        "missing": ("Missing: {key}", "Thermometers and windows, or for an output: Another device drives the heating"),
        "entity_gone": ("{key} does not exist: {entity}", "Thermometers and windows – for an output: Another device drives the heating (renamed or removed?)"),
        "entity_unavailable": ("{key} is unavailable: {entity}", "Check the device (battery, network, integration)"),
        "entity_stale": ("{key} has not reported for {age}: {entity}", "Check the device's battery and connection"),
        "entity_implausible": ("{key} reads an implausible value: {entity}", "Check the sensor's place and reading"),
        "entities_ok": ("All {n} sensors and outputs are available", ""),
        "hc_conflict": ("Another HC instance ({other}) drives it too: {entity}", "One output, one instance"),
        "automation_conflict": ("An automation switches it too: {entity} ({names})", "Turn them off, or make sure they do not fight HC"),
        "no_decision": ("No decision has gone through yet", "Wait a few minutes and look at the HC info panel"),
        "short_shadow": ("In shadow mode for {hours} h only ({need} h suggested)", "Review the shadow decisions in the HC info panel"),
        "shadow_ok": ("In shadow mode for {hours} h", ""),
        "failing": ("The decision fails now ({n}× in a row)", "Look at the log and the Repairs page"),
        "faults": ("{n} decisions with a fault in the last day", "Look at the decision log in the HC info panel"),
        "safety_tripped": ("The life-safety stop is tripped", "Remove its cause, then acknowledge it"),
        "safety_ok": ("The life-safety inputs are fine", ""),
        "guard_ok": ("The local guard answers", ""),
        "guard_unreachable": ("The local guard does not answer ({error})", "Expert settings → Local guard: address, password, the Shelly's network"),
        "guard_suggested": ("No local guard (suggested)", "If HC or Home Assistant stops, the guard keeps frost protection on the relay"),
        "targets_below_frost": ("Target at or below frost protection ({frost} °C): {keys}", "How warm, and when?"),
        "targets_above_home": ("Above the home target ({home} °C): {keys}", "How warm, and when?"),
        "risk_min_off_s": ("The minimum pause ({value} s) is less than half the recommended {rec} s", "Expert settings → Regulation: frequent starts wear the boiler and the relay"),
        "risk_min_on_s": ("The minimum run ({value} s) is less than half the recommended {rec} s", "Expert settings → Regulation: short burns give little heat, with many starts"),
        "risk_cycle_s": ("The cycle ({value} s) is too short for this system (recommended {rec} s)", "Expert settings → Regulation: on a short cycle the valve barely opens before it closes"),
        "risk_hp_min_on_s": ("The heat pump's shortest run ({value} s) is less than half the recommended {rec} s", "Expert settings → Regulation: short compressor runs wear it"),
        "risk_hp_min_off_s": ("The heat pump's shortest pause ({value} s) is less than half the recommended {rec} s", "Expert settings → Regulation: the compressor needs rest between starts"),
        "risk_floor_limit": ("The floor limit is {value} °C – above the usual {rec} °C", "Expert settings → Floor: a too warm floor strains the covering and the feet"),
        "risk_frost_temp": ("Frost protection is only {value} °C", "How warm, and when?: below 5 °C a pipe behind a colder wall may already freeze"),
        "risk_flow_max": ("On a floor the curve's highest flow is {value} °C (above 45 °C)", "Expert settings → Regulation: the floor and the screed do not take hot water"),
        "risk_guard_ttl": ("The local guard's lease ({value} s) is shorter than twice the renewal ({every} s)", "Expert settings → Local guard: one missed renewal and it takes over"),
        "night_empty": ("No night setback (it starts and ends at {at})", "If a night is wanted: How warm, and when?"),
    },
}

HEAD = {
    "hu": {"ready": "Élesíthető", "warns": "Élesíthető, {w} figyelmeztetéssel",
           "blocked": "Még nem élesíthető: {b} akadály", "block": "Akadály", "warn": "Figyelmeztetés",
           "ok": "Rendben", "info": "Javaslat"},
    "en": {"ready": "Ready to go live", "warns": "Ready to go live, with {w} warnings",
           "blocked": "Not ready to go live: {b} blockers", "block": "Blocker", "warn": "Warning",
           "ok": "OK", "info": "Suggestion"},
}

_ORDER = {BLOCK: 0, WARN: 1, INFO: 2, OK: 3}


def render(items: list[Item], lang: str = "en") -> dict:
    """The list in words, the blockers first."""
    lang = "hu" if str(lang).startswith("hu") else "en"
    keys, words = KEY_WORDS[lang], WORDS[lang]

    def name(k):
        return keys.get(k, k)

    out = []
    for i in sorted(items, key=lambda i: _ORDER.get(i.level, 9)):
        p = dict(i.params)
        if "key" in p:
            p["key"] = name(p["key"])
            p["key"] = p["key"][:1].upper() + p["key"][1:] if i.id != "missing" else p["key"]
        if "keys" in p:
            p["keys"] = ", ".join(name(k) for k in p["keys"])
        title, fix = words.get(i.id, (i.id, ""))
        out.append({"id": i.id, "level": i.level, "title": title.format(**p), "fix": fix})
    s = summary(items)
    h = HEAD[lang]
    head = h["blocked"].format(b=s["blocks"]) if s["blocks"] else h["warns"].format(w=s["warns"]) if s["warns"] else h["ready"]
    return {**s, "head": head, "items": out, "levels": {k: h[k] for k in (BLOCK, WARN, OK, INFO)}}


def as_text(rendered: dict) -> str:
    """For a config flow description: the head line and the blockers / warnings as a Markdown list."""
    lines = [f"**{rendered['head']}**"]
    marks = {BLOCK: "⛔", WARN: "⚠️", INFO: "💡", OK: "✅"}
    for it in rendered["items"]:
        if it["level"] == OK:
            continue
        lines.append(f"- {marks[it['level']]} {it['title']}" + (f" – {it['fix']}" if it["fix"] else ""))
    return "\n".join(lines)

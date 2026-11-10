"""Decision log texts in both languages."""

from __future__ import annotations

from .model import Decision, Reason

REASONS: dict[Reason, dict[str, str]] = {
    Reason.REGULATING: {"hu": "Szabályoz: cél {target} °C, igény {demand} %.", "en": "Regulating: target {target} °C, demand {demand} %."},
    Reason.AT_TARGET: {"hu": "Nem fűt: a ház elérte a célt ({target} °C).", "en": "Not heating: the house reached the target ({target} °C)."},
    Reason.BOOST: {"hu": "Felfűtés a {target} °C-os célig: leáll, amikor az utómelegedéssel együtt eléri (most várható {forecast} °C), legkésőbb {until}-kor.",
                   "en": "Boost to {target} °C: stops when the after-heat will reach it (now expected {forecast} °C), at {until} at the latest."},
    Reason.AFTERHEAT: {"hu": "Utómelegedés: a felfűtés után a radiátorok még melegítenek, addig nem gyújt újra.",
                       "en": "After-heat: the radiators still warm the house after the boost, no new start until it ends."},
    Reason.FROST: {"hu": "Fagyvédelem: a benti hőfok a határ alá esett.", "en": "Frost protection: the indoor temperature fell below the limit."},
    Reason.DISABLED: {"hu": "Kikapcsolva.", "en": "Switched off."},
    Reason.SENSOR_LOST: {"hu": "Nincs friss benti hőfok: tartalék üzem, igény {demand} %.", "en": "No fresh indoor temperature: fallback, demand {demand} %."},
    Reason.WINDOW: {"hu": "Szünet: nyitva van egy ablak vagy ajtó.", "en": "Paused: a window or door is open."},
    Reason.SEASON_OFF: {"hu": "Nyári pihenő: magas a kinti napi átlag.", "en": "Summer rest: the outdoor daily average is high."},
    Reason.RESTART_HOLD: {"hu": "Újraindítás után vár: nem indít fölöslegesen.", "en": "Waiting after restart: no unnecessary start."},
    Reason.RESTART_BURN: {"hu": "Újraindítás utáni fölösleges égést állít meg.", "en": "Stopping an unnecessary burn after restart."},
    Reason.VALVE_EXERCISE: {"hu": "Szelepmozgatás: a régóta zárt szelep néhány percre kinyit, hogy ne ragadjon be ({until}-ig); a kazán nem indul.",
                            "en": "Valve exercise: the long-closed valve opens for a few minutes so it does not seize (until {until}); the boiler does not start."},
    Reason.AC_HEAT: {"hu": "Klíma fűt: cél {target} °C (teraszi hőmérő szerint), a klímán beállítva {setpoint} °C.", "en": "AC heating: target {target} °C (room thermometer), set on the unit {setpoint} °C."},
    Reason.AC_COOL: {"hu": "Klíma hűt: cél {aim} °C (helyiség-hőmérő szerint), a klímán beállítva {setpoint} °C.", "en": "AC cooling: target {aim} °C (room thermometer), set on the unit {setpoint} °C."},
    Reason.AC_PAUSE: {"hu": "Klíma szünetel: a határán ({setpoint} °C) is túllépné a {aim} °C-os célt; visszakapcsol, ha a helyiség a cél másik oldalára ér.", "en": "AC paused: even at its limit ({setpoint} °C) it would overshoot the {aim} °C target; it resumes when the room crosses the target."},
    Reason.EXTERNAL: {"hu": "A külső termosztát szabályoz, cél {target} °C.", "en": "The external thermostat regulates, target {target} °C."},
    Reason.FLOOR_LIMIT: {"hu": "Padlóhőfok-limit: a padló {floor} °C, a határ {floor_max} °C – nem fűt, amíg a padló vissza nem hűl.",
                         "en": "Floor limit: the floor is {floor} °C, the limit {floor_max} °C – no heat until the floor cools down."},
    Reason.STORAGE_CHARGE: {"hu": "Hőtároló feltöltése.", "en": "Charging the storage heater."},
    Reason.STORAGE_WAIT: {"hu": "Hőtároló: most nem tölt.", "en": "Storage heater: not charging now."},
    Reason.FLOOR_COOL: {"hu": "Padlóhűtés: cél {target} °C.", "en": "Floor cooling: target {target} °C."},
    Reason.DEW_POINT: {"hu": "Harmatpont-védelem: a padló nem hűthető most.", "en": "Dew point protection: the floor cannot be cooled now."},
}


_MANUAL = {"hu": (" Kézi cél.", " Kézi cél {until}-ig."), "en": (" Manual target.", " Manual target until {until}.")}


def _num(value, lang: str) -> str:
    if value is None:
        return "–"
    text = f"{value:g}"
    return text.replace(".", ",") if lang == "hu" else text


def _storage_text(d: dict, lang: str) -> str:
    """Storage heater: how much it charges, when, and the discharge."""
    hu = lang == "hu"
    pct = round((d.get("charge_fraction") or 0) * 100)
    why, start, end = d.get("charge_why"), d.get("charge_start"), d.get("charge_end")
    if why == "none":
        text = " Ma éjjel nem kell feltölteni." if hu else " No charge needed tonight."
    elif why == "charging":
        text = f" {pct} %-ra tölt, {end}-ig." if hu else f" Charging to {pct} %, until {end}."
    elif why == "no_power":
        text = (f" {pct} %-ra töltene ({start}–{end}), de nincs vezérelt áram." if hu
                else f" Would charge to {pct} % ({start}–{end}), but the controlled power is off.")
    else:
        text = f" Következő feltöltés: {pct} %, {start}–{end}." if hu else f" Next charge: {pct} %, {start}–{end}."
    if d.get("discharge"):
        text += " Kisütés: be." if hu else " Discharge: on."
    return text


def _cool_text(d: dict, lang: str) -> str:
    """Floor cooling: the dew point and why the cooling stops, if it does."""
    hu = lang == "hu"
    why = d.get("why")
    if why == "lost":
        return (" Nincs friss páratartalom: harmatpont nélkül nem hűt." if hu
                else " No fresh humidity: no cooling without a dew point.")
    dew, safe = _num(d.get("dew_point"), lang), _num(d.get("safe_flow"), lang)
    text = f" Harmatpont {dew} °C, a víz legalább {safe} °C." if hu else f" Dew point {dew} °C, the water at least {safe} °C."
    if d.get("flow") is not None and why is None:
        text += f" Előremenő {_num(d.get('flow'), lang)} °C." if hu else f" Flow {_num(d.get('flow'), lang)} °C."
    if why == "humid":
        text += (" Túl párás: ilyen meleg vízzel alig hűtene, ezért leáll." if hu
                 else " Too humid: water this warm would hardly cool, so it stops.")
    elif why == "floor":
        text += (f" A padló {_num(d.get('floor'), lang)} °C, a határ {_num(d.get('floor_limit'), lang)} °C – szünet." if hu
                 else f" The floor is {_num(d.get('floor'), lang)} °C, the limit {_num(d.get('floor_limit'), lang)} °C – paused.")
    elif why == "no_floor":
        text += (" Ki/be vezérlésnél padlószenzor nélkül nem hűt." if hu
                 else " On/off control does not cool without a floor sensor.")
    return text


def explain(decision: Decision, language: str = "en", room: bool = False) -> str:
    """room: the instance heats one room (a heater, an AC unit, a zone) – "the room" instead of "the house"."""
    lang = "hu" if language.startswith("hu") else "en"
    details = decision.details or {}
    until = details.get("until") or details.get("exercise_until")
    forecast = details.get("forecast")
    text = REASONS[decision.reason][lang].format(
        target=f"{decision.target:g}".replace(".", ",") if lang == "hu" else f"{decision.target:g}",
        demand=round(decision.demand * 100),
        until=until.strftime("%H:%M") if until else "–",
        forecast=(f"{forecast:.1f}".replace(".", ",") if lang == "hu" else f"{forecast:.1f}") if forecast is not None else "–",
        setpoint=_num(details.get("setpoint"), lang), aim=_num(details.get("aim"), lang),
        floor=_num(details.get("floor"), lang), floor_max=_num(details.get("floor_max"), lang))
    if decision.reason == Reason.FLOOR_LIMIT and details.get("floor_why") == "lost":
        text = ("Padlószenzor nélkül nem fűt: nincs friss padlóhőfok (elektromos padlófűtésnél ez kötelező)." if lang == "hu"
                else "No heat without the floor sensor: no fresh floor temperature (required for electric floor heating).")
    if decision.reason == Reason.SENSOR_LOST and details.get("no_blind"):
        text = ("Nincs friss benti hőfok: elektromos fűtés vakon nem fűt (igény 0 %)." if lang == "hu"
                else "No fresh indoor temperature: electric heat does not run blind (demand 0 %).")
    if decision.limited_by == "load_limit" and "load_limit_kw" in details:
        used, limit = _num(details.get("load_used_kw"), lang), _num(details.get("load_limit_kw"), lang)
        text += (f" Terheléskorlát: most {used} kW fűt a {limit} kW-ból, ez a zóna vár a sorára." if lang == "hu"
                 else f" Load limit: {used} kW of {limit} kW already heating, this zone waits for its turn.")
    if details.get("mode") == "cool":
        text += _cool_text(details, lang)
    if "charge_fraction" in details:
        text += _storage_text(details, lang)
    if decision.limited_by == "return_limit":
        r, m = _num(details.get("return"), lang), _num(details.get("return_max"), lang)
        text += (f" Visszatérő-korlát: a visszatérő víz {r} °C (határ {m} °C), a szelep zárva marad." if lang == "hu"
                 else f" Return limit: the return water is {r} °C (limit {m} °C), the valve stays closed.")
    if "fan_pct" in details:
        why, pct = details.get("fan_why"), details.get("fan_pct")
        if why == "heating":
            text += f" Ventilátor {pct} %." if lang == "hu" else f" Fan {pct} %."
        elif why == "overrun":
            text += " Ventilátor utánfut." if lang == "hu" else " Fan overrun."
        elif why == "cold_coil":
            text += (" A ventilátor vár, amíg a hőcserélő átmelegszik." if lang == "hu"
                     else " The fan waits until the coil is warm.")
    if decision.limited_by == "no_power":
        text += (" A vezérelt áram most nincs bekapcsolva: nem kapcsol." if lang == "hu"
                 else " The controlled power is off now: nothing is switched.")
    if room:
        text = text.replace("a ház ", "a helyiség ").replace("the house", "the room")
    if decision.reason == Reason.WINDOW and details.get("window_source") == "drop":
        rate = details.get("drop_rate")
        rate_text = (f"{rate:.1f}".replace(".", ",") if lang == "hu" else f"{rate:.1f}") if rate else "–"
        text = (f"Szünet: gyors hőesés ({rate_text} °C/óra) – valószínűleg nyitott ablak." if lang == "hu"
                else f"Paused: fast temperature drop ({rate_text} °C/h) – a window is probably open.")
    if details.get("assist"):
        aim = _num(details.get("aim"), lang)
        text += (f" Segít a ház fűtésében {aim} °C-ig: a klíma az olcsóbb, és nyitva a konyhaajtó." if lang == "hu"
                 else f" Helping to heat the house up to {aim} °C: cheaper than the boiler, the door is open.")
    if details.get("yield"):
        m = _num(details.get("yield"), lang)
        text += (f" Az olcsóbb klíma fűt, a kazán {m} °C-kal a cél alatt tart (tartalék)." if lang == "hu"
                 else f" The cheaper heat pump leads, the boiler holds {m} °C below the target as a backup.")
    if details.get("hp_mode") in ("defrost", "dhw"):
        what = {"defrost": ("leolvaszt", "defrosts"), "dhw": ("használati melegvizet készít", "makes hot water")}[details["hp_mode"]]
        text += (f" A hőszivattyú most {what[0]}: a ház fűtése addig szünetel, ez nem hiba." if lang == "hu"
                 else f" The heat pump {what[1]} now: the house waits, this is no fault.")
    if details.get("room_demand"):
        rooms = ", ".join(details["room_demand"])
        text += f" Hőt kér: {rooms}." if lang == "hu" else f" Asking for heat: {rooms}."
    if decision.flow_setpoint is not None:
        flow = f"{decision.flow_setpoint:g}"
        text += f" Előremenő: {flow.replace('.', ',')} °C." if lang == "hu" else f" Flow: {flow} °C."
    if decision.manual and decision.reason not in (Reason.DISABLED, Reason.EXTERNAL, Reason.AC_PAUSE):
        plain, until = _MANUAL[lang]
        text += until.format(until=decision.manual_until.strftime("%H:%M")) if decision.manual_until else plain
    return text

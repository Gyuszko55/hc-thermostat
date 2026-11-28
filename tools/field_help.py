"""0.85.0: the "when to change it" help of the critical settings – the single source of the three parts (when to
change it, the recommended range, the risk) that are appended to the fields' descriptions in translations/*.json.

Run `python tools/field_help.py` after editing: it rewrites the descriptions of every listed field in every step and
section where the field appears (config and options flow), keeping the field's own sentence before the help.
Running it twice changes nothing (the help is replaced, not appended again).
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat" / "translations"
MARK = {"hu": "**Mikor változtass:**", "en": "**When to change it:**"}
REC = {"hu": "**Ajánlott:**", "en": "**Recommended:**"}

# key: (hu: when, recommended, risk), (en: when, recommended, risk)
HELP: dict[str, tuple[tuple[str, str, str], tuple[str, str, str]]] = {
    "target_home": (("ha napközben otthon hűvös vagy túl meleg van.", "20–22 °C; fokonként kb. 6 % fűtési energia.",
                     "a túl magas cél sokat fogyaszt és száraz levegőt ad."),
                    ("when it is too cool or too warm at home in the day.", "20–22 °C; each degree costs about 6 % heating energy.",
                     "a high target uses a lot and dries the air.")),
    "target_night": (("ha éjjel hideg van, vagy reggel lassú a felfűtés.", "az otthoni célnál 1–3 °C-kal kevesebb.",
                      "nagyobb csökkentésnél a reggeli felfűtés hosszabb és erősebb."),
                     ("when it is cold at night or the morning rise is slow.", "1–3 °C below the home target.",
                      "a deeper setback makes the morning rise longer and harder.")),
    "target_away": (("ha hazaérve túl hideg van, vagy többet akarsz spórolni.", "15–18 °C.",
                     "túl alacsony célnál a hazaérkezés utáni felfűtés sokáig tart."),
                    ("when it is too cold on coming home, or to save more.", "15–18 °C.",
                     "a too low target makes the heat-up after coming home long.")),
    "frost_temp": (("szinte soha; csak ha nagyon hideg helyiség (garázs, műhely) a fűtött tér.", "6–8 °C.",
                    "5 °C alatt a hidegebb falak mögött a cső már fagyhat."),
                   ("almost never; only for a very cold space (garage, workshop).", "6–8 °C.",
                    "below 5 °C a pipe behind a colder wall may already freeze.")),
    "control": (("ha más eszköz kerül a fűtésre (pl. fali termosztát, klíma), vagy a mostani nem tartja a célt.",
                 "relés kazánnál TPI vagy PID; padlónál TPI hosszú ciklussal; moduláló kazánnál görbe.",
                 "a váltás új tanulással jár: pár napig árnyék módban érdemes figyelni."),
                ("when another device drives the heating (a wall thermostat, an AC) or the current one misses the target.",
                 "TPI or PID for a relay boiler; TPI with a long cycle for a floor; the curve for a modulating boiler.",
                 "a change starts the learning again: watch it in shadow mode for a few days.")),
    "cycle_s": (("ha túl sűrűn vagy túl ritkán indul a fűtés.",
                 "radiátornál 600–1200 s, padlónál 1800–3600 s, pelletnél 3600 s, villanyfűtőnél 600 s.",
                 "rövid ciklusnál padlón a szelep alig nyit ki, máris zár; túl hosszúnál nagyobb a hőmérséklet-ingadozás."),
                ("when the heating starts too often or too seldom.",
                 "600–1200 s for radiators, 1800–3600 s for a floor, 3600 s for pellets, 600 s for an electric heater.",
                 "on a floor a short cycle closes the valve before it is open; a too long one swings the temperature more.")),
    "min_on_s": (("ha a kazán gyártója hosszabb égést kér, vagy lassú szelepek vannak.",
                  "gázkazánnál 180–300 s, padlónál 600–900 s, pelletnél 2700 s.",
                  "a rövid égés alig ad hőt, sok indítással."),
                 ("when the boiler's maker asks for longer burns, or with slow valves.",
                  "180–300 s for a gas boiler, 600–900 s for a floor, 2700 s for pellets.",
                  "short burns give little heat, with many starts.")),
    "min_off_s": (("szinte soha; ha a kazán gyártója hosszabb szünetet kér.",
                   "gázkazánnál 180–300 s, hőszivattyúnál 300–600 s, villanyfűtésnél 60–180 s.",
                   "túl rövid érték: sűrű indítás, a kazán és a relé gyorsabban kopik."),
                  ("almost never; when the boiler's maker asks for a longer pause.",
                   "180–300 s for a gas boiler, 300–600 s for a heat pump, 60–180 s for electric heat.",
                   "too short: frequent starts wear the boiler and the relay faster.")),
    "valve_delay_s": (("ha termoelektromos szelepek vagy későn induló szivattyú van.", "0 = nincs; termoelektromos szelepnél kb. 300 s.",
                       "nullán hagyva lassú szelepeknél a rövid ciklusok nagy része nyitással telik."),
                      ("with thermoelectric valves or a pump that starts late.", "0 = none; about 300 s for thermoelectric valves.",
                       "left at zero with slow valves, much of each short run goes on opening.")),
    "onoff_hysteresis": (("ha túl sokszor kapcsol, vagy túl nagy a hőmérséklet-ingadozás.", "0,2–0,5 °C.",
                          "kisebb értéknél sűrűbb kapcsolás, nagyobbnál hűvösebb mélypontok."),
                         ("when it switches too often, or the temperature swings too much.", "0.2–0.5 °C.",
                          "smaller: more switching; larger: cooler lows.")),
    "tpi_coef_int": (("ha tartósan a cél alatt vagy fölött marad (a tanulás ezt magától is állítja).", "0,4–0,8 (alap 0,6).",
                      "nagy érték túllövést, kicsi lassú felzárkózást ad."),
                     ("when it stays below or above the target for long (the learning adjusts it too).", "0.4–0.8 (default 0.6).",
                      "a high value overshoots, a low one catches up slowly.")),
    "pid_kp": (("ha a hiányra túl lassan vagy túl hevesen reagál.", "0,3–0,6 (alap 0,4).",
                "túl nagy értéknél be-ki leng a cél körül."),
               ("when it answers a shortfall too slowly or too hard.", "0.3–0.6 (default 0.4).",
                "too high: it swings around the target.")),
    "pid_ki_per_hour": (("ha tartósan pár tizeddel a cél alatt marad.", "0,1–0,5 óránként.",
                         "túl nagy értéknél lassú, órás lengések."),
                        ("when it stays a few tenths below the target for long.", "0.1–0.5 per hour.",
                         "too high: slow swings over hours.")),
    "curve_slope": (("ha hidegben hűvös (növeld) vagy enyhe időben túl meleg (csökkentsd) a lakás.",
                     "radiátornál 1,2–1,6, padlónál 0,3–0,7.", "kis lépésekben (0,1) változtass, és várj egy napot."),
                    ("when it is cool in cold weather (raise it) or too warm in mild weather (lower it).",
                     "1.2–1.6 for radiators, 0.3–0.7 for a floor.", "change in small steps (0.1) and wait a day.")),
    "curve_shift": (("ha minden időben egyformán hűvös vagy meleg van.", "−3…+3 °C.",
                     "nagy eltolás helyett inkább a meredekséget vagy a célt állítsd."),
                    ("when it is equally cool or warm in every weather.", "−3…+3 °C.",
                     "rather than a large shift, set the slope or the target.")),
    "flow_min": (("ha enyhe időben hideg marad a radiátor vagy a padló.", "radiátornál 25–30 °C, padlónál 22–25 °C.",
                  "kazánnál túl alacsony előremenőn kondenzálhat a nem kondenzációs kazán."),
                 ("when the radiators or the floor stay cold in mild weather.", "25–30 °C for radiators, 22–25 °C for a floor.",
                  "a non-condensing boiler may condense on a too low flow.")),
    "flow_max": (("ha a legnagyobb hidegben sem melegszik fel a lakás.", "radiátornál 65–75 °C, hőszivattyúnál 50–55 °C, padlónál legfeljebb 45 °C.",
                  "padlón 45 °C fölött az esztrich és a burkolat sérülhet."),
                 ("when the home does not warm up even in the coldest weather.", "65–75 °C for radiators, 50–55 °C for a heat pump, at most 45 °C for a floor.",
                  "on a floor above 45 °C the screed and the covering may be damaged.")),
    "hp_min_on_s": (("ha a hőszivattyú gyártója más futásidőt ír elő.", "1200 s (20 perc) vagy több.",
                     "a kompresszor rövid futásai koptatnak és rontják a COP-t."),
                    ("when the heat pump's maker gives another run time.", "1200 s (20 min) or more.",
                     "short compressor runs wear it and lower the COP.")),
    "hp_min_off_s": (("ha a hőszivattyú gyártója más szünetet ír elő.", "600 s (10 perc) vagy több.",
                      "a kompresszornak pihennie kell két indítás között."),
                     ("when the heat pump's maker gives another pause.", "600 s (10 min) or more.",
                      "the compressor needs rest between starts.")),
    "floor_max": (("csak ha a burkolat gyártója más határt ír elő; 0 = a HC a burkolat és a szenzor helye szerint dönt.",
                   "csempénél 29 °C, fánál és laminált alatt 27 °C; villanypadlónál 27 °C.",
                   "túl meleg padló a burkolatot és a lábat is terheli."),
                  ("only when the covering's maker gives another limit; 0 = HC decides by the covering and the probe.",
                   "29 °C under tiles, 27 °C under wood and laminate; 27 °C for an electric floor.",
                   "a too warm floor strains the covering and the feet.")),
    "floor_hysteresis": (("ha a padlóhatárnál túl sűrűn kapcsol.", "0,5–1,5 °C (alap 1).", "kisebb értéknél sűrűbb kapcsolás a határon."),
                         ("when it switches too often at the floor limit.", "0.5–1.5 °C (default 1).", "smaller: more switching at the limit.")),
    "dew_margin": (("szinte soha; párás helyiségben inkább növeld.", "2–3 °C.",
                    "kisebb ráhagyásnál a padlón és a csöveken lecsapódhat a pára."),
                   ("almost never; rather raise it in a humid room.", "2–3 °C.",
                    "with a smaller margin water may condense on the floor and the pipes.")),
    "return_max": (("ha a távhőszolgáltató visszatérő-határt ír elő.", "0 = nincs; a szolgáltató értéke (gyakran 40–50 °C).",
                    "túl alacsony határnál a szelep alig nyit, hideg marad a lakás."),
                   ("when the district heating supplier sets a return limit.", "0 = none; the supplier's value (often 40–50 °C).",
                    "a too low limit barely opens the valve and the home stays cold.")),
    "frozen_after_h": (("ha egy hőmérő ritkán küld adatot, és tévesen beragadtnak látszik.", "radiátornál 3 óra, padlónál 8 óra; 0 = ki.",
                        "kikapcsolva egy beragadt hőmérő mellett a HC vakon fűthet vagy nem fűthet."),
                       ("when a thermometer reports seldom and looks stuck by mistake.", "3 h for radiators, 8 h for a floor; 0 = off.",
                        "switched off, a stuck thermometer may make HC heat blind or not at all.")),
    "window_drop_rate": (("ha tévesen ablaknyitást jelez (növeld), vagy nem veszi észre a szellőztetést (csökkentsd).",
                          "1,5 °C/óra (alap).", "túl kicsi érték fűtés közben is szünetet tarthat."),
                         ("when it reports an open window by mistake (raise it) or misses airing (lower it).",
                          "1.5 °C/h (default).", "a too small value may pause even while heating.")),
    "season_off_above": (("ha tavasszal túl korán vagy későn áll le a fűtés.", "15–18 °C napi átlag.",
                          "túl alacsony érték hűvös tavaszi napokon is leállítja a fűtést."),
                         ("when the heating stops too early or late in spring.", "15–18 °C daily average.",
                          "a too low value stops the heating on cool spring days too.")),
    "season_on_below": (("ha ősszel túl korán vagy későn indul a fűtés.", "12–14 °C napi átlag, a vége alatt legalább 2 °C-kal.",
                         "a két határ közti kis különbség ide-oda kapcsolgatja az idényt."),
                        ("when the heating starts too early or late in autumn.", "12–14 °C daily average, at least 2 °C below the end.",
                         "a small gap between the two limits flips the season back and forth.")),
    "guard_sp": (("ha a HC kiesése alatt a tartalék program túl hideget vagy meleget tartana.", "a nappali célnál 1–2 °C-kal kevesebb (alap 20,5 °C).",
                  "túl alacsony érték egy hosszabb kiesésnél kihűti a lakást."),
                 ("when the fallback program would hold too cold or too warm while HC is down.", "1–2 °C below the day target (default 20.5 °C).",
                  "a too low value cools the home in a longer outage.")),
    "guard_ttl_s": (("szinte soha.", "a megújítás legalább kétszerese (alap 300 s, megújítás 60 s).",
                     "rövid bérletnél egy kimaradt megújítás már átadja a vezérlést a helyi védőnek."),
                    ("almost never.", "at least twice the renewal (default 300 s, renewal 60 s).",
                     "with a short lease one missed renewal already hands control to the local guard.")),
    "guard_max_on_s": (("villanyfűtésnél, amelynek nincs saját határoló termosztátja.", "0 = nincs; villanyfűtőnél 7200 s.",
                        "villanyfűtésnél határ nélkül egy hibás mérés órákig fűthet."),
                       ("for electric heat with no limit thermostat of its own.", "0 = none; 7200 s for an electric heater.",
                        "without a limit, a wrong reading may heat electric heat for hours.")),
}


def help_text(key: str, lang: str) -> str:
    when, rec, risk = HELP[key][0 if lang == "hu" else 1]
    return f"{MARK[lang]} {when[:1].upper()}{when[1:]} {REC[lang]} {rec} ⚠ {risk[:1].upper()}{risk[1:]}"


def _apply(desc: dict, data: dict, lang: str) -> int:
    n = 0
    for key in HELP:
        if key not in data:
            continue
        own = (desc.get(key) or "").split(MARK[lang])[0].strip()
        desc[key] = (own + "\n\n" if own else "") + help_text(key, lang)
        n += 1
    return n


def main() -> None:
    for lang in ("hu", "en"):
        path = ROOT / f"{lang}.json"
        doc = json.loads(path.read_text())
        n = 0
        for flow in ("config", "options"):
            for step in doc.get(flow, {}).get("step", {}).values():
                for part in [step, *(step.get("sections") or {}).values()]:
                    if any(k in HELP for k in part.get("data") or {}):
                        n += _apply(part.setdefault("data_description", {}), part["data"], lang)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        print(lang, n, "fields")


if __name__ == "__main__":
    main()

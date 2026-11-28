"""0.84.0: "why heating / why not" – the plain summary (core/summary.py) and the supervisor's context for it."""

from datetime import datetime, timedelta

from core.model import Decision, HcConfig, Inputs, Presence, Reading, Reason
from core.summary import STATE_OF, STATE_WORDS, WHY, as_text, summarize
from core.supervisor import Supervisor

NOW = datetime(2026, 11, 28, 23, 10)
NIGHT = {"preset": None, "active": "sleep", "presence": "home", "night": ("22:00", "05:30"),
         "next_at": datetime(2026, 11, 29, 5, 30), "next_target": 22.5}


def _d(reason=Reason.REGULATING, **kw):
    base = dict(now=NOW, reason=reason, target=21.0, indoor=20.6, outdoor=3.0)
    base.update(kw)
    return Decision(**base)


def test_every_reason_has_a_state_and_words_in_both_languages():
    assert set(STATE_OF) == set(Reason)
    for lang in ("hu", "en"):
        for r in Reason:
            s = summarize(_d(r, details={"until": NOW + timedelta(minutes=20)}), {}, lang)
            assert s["headline"] in STATE_WORDS[lang].values() and s["lines"] and s["lines"][0]
            assert "{" not in " ".join(s["lines"])
        assert WHY["hu"].keys() == WHY["en"].keys()


def test_a_night_regulating_pause_tells_why_where_the_target_comes_from_and_what_comes():
    s = summarize(_d(output=False), NIGHT, "hu", presets=("comfort", "boost"))
    assert s["headline"] == "Nem fűt" and not s["shadow"]
    assert s["lines"] == [
        "Most szünet a fűtési szakaszok között: a hőt adagolva adja, hogy ne lője túl (bent 20,6 °C, cél 21 °C).",
        "A cél 21 °C, mert éjszaka van (22:00–05:30).",
        "05:30-kor a cél 22,5 °C-ra nő.",
        "Ha most melegebb kell: Komfort vagy Gyors felfűtés.",
    ]
    on = summarize(_d(output=True), NIGHT, "en", room=True)
    assert on["headline"] == "Heating" and on["lines"][0].startswith("The room is below its target")
    assert len(on["lines"]) == 3  # no "warmer now" offer while it heats


def test_manual_target_preset_away_and_optimal_start():
    manual = summarize(_d(Reason.AT_TARGET, manual=True, manual_until=datetime(2026, 11, 29, 1, 0)), NIGHT, "hu")
    assert manual["lines"][1] == "A cél 21 °C, kézzel állítva – 01:00-ig."
    assert manual["lines"][-1] == "A kézi cél törlése: válaszd az Auto előbeállítást."
    assert not any("05:30" in x for x in manual["lines"])  # the manual target ends first
    preset = summarize(_d(Reason.AT_TARGET, target=23), {"preset": "comfort", "preset_until": datetime(2026, 11, 29, 2, 10),
                                                         "next_at": datetime(2026, 11, 29, 2, 10)}, "hu")
    assert preset["lines"][1:3] == ["A cél 23 °C: Komfort előbeállítás, 02:10-ig.",
                                    "02:10-kor véget ér az előbeállítás, utána az ütemezés szerint megy."]
    home = summarize(_d(Reason.AT_TARGET), {"preset": "away", "preset_until_home": True}, "hu")
    assert home["lines"][1] == "A cél 21 °C: Távol előbeállítás, hazaérkezésig."
    away = summarize(_d(Reason.AT_TARGET, target=18), {"presence": "away", "active": "away"}, "en")
    assert away["lines"][1] == "The target is 18 °C: nobody is home."
    early = summarize(_d(target=22.5, output=True), {**NIGHT, "early": {"until": datetime(2026, 11, 29, 5, 30)}}, "hu")
    assert early["lines"][1] == "A cél már most 22,5 °C: reggeli felfűtés, hogy 05:30-ra meglegyen."


def test_window_sensor_and_frozen_reading():
    w = summarize(_d(Reason.WINDOW), {}, "hu")
    assert (w["headline"], w["lines"]) == ("Szünetel", ["Nyitva van egy ablak vagy ajtó.", "Becsukás után folytatja.",
                                                         "Csukd be az ablakot vagy az ajtót."])
    drop = summarize(_d(Reason.WINDOW), {"drop": ("sensor.bed", 2.0)}, "hu")
    assert drop["lines"][0].startswith("Gyorsan esik") and len(drop["lines"]) == 2  # no "close it": not sure which
    lost = summarize(_d(Reason.SENSOR_LOST, indoor=None, demand=0.35), {}, "hu")
    assert lost["headline"] == "Hiba" and lost["lines"][-1] == "Nézd meg a hőmérő elemét és kapcsolatát."
    frozen = summarize(_d(output=True, details={"indoor_frozen": True}), {}, "en")
    assert "stuck" in frozen["lines"][0] and frozen["lines"][-1].startswith("Check the thermometer")


def test_limits_shadow_mismatch_and_text():
    coast = summarize(_d(limited_by="coast", output=False), {}, "hu")
    assert coast["lines"][0].startswith("Most állt le, és bent még emelkedik")
    shadow = summarize(_d(output=False), {}, "hu", live=False, actual=True)
    assert shadow["shadow"] and shadow["note"] == "Árnyék mód: ezt tenné, de nem kapcsol."
    assert not any("Közben mégis fűt" in x for x in shadow["lines"])  # in shadow the old control runs: no mismatch
    live = summarize(_d(Reason.AT_TARGET), {}, "hu", actual=True)
    assert "Közben mégis fűt" in live["lines"][1]
    assert summarize(_d(Reason.EXTERNAL), {}, "hu", actual=True)["lines"][-1] != live["lines"][1]
    season = summarize(_d(Reason.SEASON_OFF), {}, "hu", season_on_below=15.0)
    assert season["headline"] == "Ki" and season["lines"][1] == "Visszakapcsol, ha a kinti napi átlag 15 °C alá esik."
    assert as_text(shadow).startswith("Árnyék mód: ezt tenné, de nem kapcsol. Nem fűt. Most szünet")


def test_the_supervisors_context():
    sup = Supervisor(HcConfig(night_start="22:00", night_end="05:30"))
    sup.step(Inputs(now=NOW, indoor=Reading(20.6), outdoor=Reading(3.0)))
    ctx = sup.summary_context(NOW)
    assert ctx["active"] == "sleep" and ctx["presence"] == "home" and ctx["preset"] is None
    assert ctx["next_at"].strftime("%H:%M") == "05:30" and ctx["next_target"] == sup.cfg.target_home
    sup.step(Inputs(now=NOW + timedelta(seconds=30), indoor=Reading(20.6), presence=Presence.AWAY))
    ctx = sup.summary_context(NOW + timedelta(seconds=30))
    assert ctx["active"] == "away" and ctx["next_at"] is None


def test_a_trv_room():
    from core.summary import summarize_room
    room = {"reason": "night", "temperature": 19.2, "target": 20.0, "heating": True, "enabled": True, "asking": True}
    s = summarize_room(room, "hu")
    assert s["headline"] == "Fűt" and s["lines"] == ["Bent 19,2 °C, a cél 20 °C – saját éjszakai cél.",
                                                     "A szelepfejek nyitva, a helyiség fűtést kap.", "Fűtést kér a kazántól."]
    cold = summarize_room({**room, "heating": False, "asking": False}, "en")
    assert cold["headline"] == "Not heating" and "by the house's decision" in cold["lines"][1]
    assert summarize_room({**room, "window": True}, "hu")["headline"] == "Szünetel"
    assert summarize_room({**room, "temperature": None}, "hu")["lines"][-1].startswith("Nézd meg")
    assert summarize_room({**room, "enabled": False}, "en")["headline"] == "Off"


def test_minimum_times_return_limit_and_no_power():
    s = summarize(_d(target=22.0, indoor=18.9, demand=1.0, output=False, limited_by="min_off", manual=True), {}, "hu")
    assert s["headline"] == "Nem fűt" and s["lines"][0].startswith("Fűtést kér (bent 18,9 °C, cél 22 °C), de a legrövidebb szünet")
    on = summarize(_d(output=True, limited_by="min_on"), {}, "en")
    assert on["headline"] == "Heating" and on["lines"][0].startswith("It is near the target, but waits out")
    assert summarize(_d(output=False, limited_by="no_power"), {}, "hu")["lines"][0] == "Nincs vezérelt áram, most nem fűthet."
    assert "visszatérő" in summarize(_d(output=False, limited_by="return_limit"), {}, "hu")["lines"][0]


def test_0871_a_room_without_a_reading_right_after_start_waits():
    from core.summary import summarize_room
    room = {"reason": "follow", "temperature": None, "target": 21.0, "heating": False, "enabled": True}
    s = summarize_room(room, "hu", starting=True)
    assert s["state"] == "waiting" and s["headline"] == "Vár" and s["lines"][0].startswith("Újraindulás után még nincs mérés")
    assert summarize_room(room, "hu")["state"] == "fault"  # later it is a fault

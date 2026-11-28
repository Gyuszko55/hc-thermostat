"""0.87.0: the roles' summary wired in (plain.py, the decision sensors, the climates) and the Assist intent."""

import asyncio
import importlib
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

plain = importlib.import_module("hc_thermostat.plain")
hc_intent = importlib.import_module("hc_thermostat.intent")
climate = importlib.import_module("hc_thermostat.climate")
sensor = importlib.import_module("hc_thermostat.sensor")
from hc_thermostat.core.buffer import BufferDecision  # noqa: E402
from hc_thermostat.core.model import Decision, Reason  # noqa: E402

NOW = datetime(2026, 11, 28, 14, 0)


def _st(name):
    return SimpleNamespace(state="heat", attributes={"friendly_name": name})


def _hass(states=None, entries=()):
    states = states or {}
    return SimpleNamespace(config=SimpleNamespace(language="hu"), states=SimpleNamespace(get=states.get),
                           config_entries=SimpleNamespace(async_entries=lambda d: list(entries)))


def test_role_plain_names_zones_and_knows_the_mode():
    hass = _hass({"climate.bath": _st("Fürdő")})
    d = BufferDecision(NOW, True, "charging", 44.0, 52.0, ("climate.bath",), {"buffer_on": 45.0, "buffer_off": 65.0})
    c = SimpleNamespace(data=d, hass=hass, mode="active")
    s = plain.role_plain(c, "buffer")
    assert s["headline"] == "Tölt" and s["lines"][-1] == "Hőt kér: Fürdő." and not s["shadow"]
    shadow = SimpleNamespace(data=d, hass=hass, write=SimpleNamespace(mode="shadow"))
    assert plain.role_plain(shadow, "buffer", "en")["shadow"]
    assert plain.role_plain(SimpleNamespace(data=None, hass=hass), "buffer") is None
    c.plain_summary = lambda language=None: plain.role_plain(c, "buffer", language)
    attrs = plain._summary_attrs(c)
    assert attrs["summary_headline"] == "Tölt" and attrs["summary_lines"][-1] == "Hőt kér: Fürdő." and attrs["summary_note"] is None


def test_the_sensors_and_climates_do_not_record_it():
    for cls in (sensor.HcDecision, sensor.HcBufferDecision, sensor.HcHpDecision, sensor.HcCircuitTarget,
                sensor.HcCentralDecision, climate.HcClimate, climate.HcRoomClimate):
        assert set(plain.SUMMARY_KEYS) <= set(cls._unrecorded_attributes), cls.__name__
    room = {"reason": "follow", "temperature": 20.1, "target": 21.0, "heating": True, "enabled": True}
    attrs = climate._room_summary(room, True, _hass())
    assert attrs["summary_headline"] == "Fűt" and attrs["summary_lines"][0].startswith("Bent 20,1 °C, a cél 21 °C")
    assert climate._room_summary(room, False, _hass()) == {}


class _Coord:
    def __init__(self, headline="Nem fűt", rooms=None):
        self.headline, self.room_states = headline, rooms or {}

    def plain_summary(self, lang=None):
        hu = str(lang).startswith("hu")
        return {"state": "idle", "headline": self.headline,
                "lines": ["A ház elérte a célt (bent 22,6 °C, cél 22,5 °C)." if hu else "The house reached its target.",
                          "A cél 22,5 °C: nappali, otthoni cél.", "Ha most melegebb kell: Komfort."], "note": None}


def _entry(title, c, **conf):
    return SimpleNamespace(title=title, runtime_data=c, data={"role": "standalone", **conf}, options={})


def test_the_intent_answers_the_house_a_room_and_an_instance():
    bath = {"name": "Fürdőszoba", "area": None, "trv": True, "reason": "night", "temperature": 21.4, "target": 22.0,
            "heating": True, "enabled": True}
    living = {"name": "Nappali", "area": None, "trv": False, "reason": "leading"}
    house = _Coord(rooms={"bath": bath, "living": living})
    hass = _hass(entries=[_entry("Olajradiátor", _Coord("Vár"), mode="shadow"),
                          _entry("Kazán HC", house, mode="active")])
    text = hc_intent.answer(hass, None, "hu")
    assert text == "Kazán HC: Nem fűt. A ház elérte a célt (bent 22,6 fok, cél 22,5 fok). A cél 22,5 fok: nappali, otthoni cél."
    room = hc_intent.answer(hass, "fürdőben", "hu")
    assert room.startswith("Fürdőszoba: Fűt. Bent 21,4 fok, a cél 22 fok – saját éjszakai cél.")
    watched = hc_intent.answer(hass, "a nappaliban", "hu")
    assert watched.startswith("Nappali a ház fűtését követi (Kazán HC): Nem fűt.")
    assert hc_intent.answer(hass, "olajradiátor", "en").startswith("Olajradiátor: Vár. The house reached its target.")
    assert hc_intent.answer(_hass(), None, "hu") == "Nincs HC fűtésvezérlő."


def test_the_handler_is_an_llm_tool_and_speaks():
    from homeassistant.helpers import intent as ha_intent
    h = hc_intent.WhyHeatingHandler()
    assert h.intent_type == "HcWhyHeating" and h.platforms is None and "why the heating" in h.description
    hass = _hass(entries=[_entry("Kazán HC", _Coord(), mode="active")])
    resp = SimpleNamespace(speech=None, response_type=None)
    resp.async_set_speech = lambda t: setattr(resp, "speech", t)
    obj = SimpleNamespace(hass=hass, slots={"name": {"value": "kazán"}}, language="hu", create_response=lambda: resp)
    out = asyncio.run(h.async_handle(obj))
    assert out.speech.startswith("Kazán HC: Nem fűt.") and out.response_type == ha_intent.IntentResponseType.QUERY_ANSWER
    obj.slots = {"hc_nev": {"value": "kazánban"}}  # the custom sentences' list
    assert asyncio.run(h.async_handle(obj)).speech.startswith("Kazán HC: Nem fűt.")

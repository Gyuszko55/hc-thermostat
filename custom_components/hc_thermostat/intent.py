"""0.87.0: "Why is (isn't) it heating?" for Assist – the plain summary (core/summary.py, core/summary_roles.py) spoken.

The intent `HcWhyHeating` has a description, so an LLM conversation agent (Assist API) gets it as a tool on its own;
for the built-in agent a few sentences in custom_sentences/<language>/ point at it (README). One optional slot,
`name`: an HC instance, a room or an area, matched loosely ("fürdőben" finds "Fürdőszoba"); without it the house's
leading instance answers. Read only: nothing is switched.
"""

from __future__ import annotations

import unicodedata

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, intent

from .const import DOMAIN

INTENT_WHY = "HcWhyHeating"


async def async_setup_intents(hass: HomeAssistant) -> None:
    intent.async_register(hass, WhyHeatingHandler())


def _norm(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", str(text or "").casefold())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return [w for w in "".join(ch if ch.isalnum() else " " for ch in plain).split() if w]


def _score(query: list[str], name: str) -> int:
    """The longest common start (at least 4 letters) of a query word and a name word – Hungarian endings
    ("fürdőben", "nappaliban") still find the name; 0 = no match."""
    best = 0
    for q in query:
        for w in _norm(name):
            n = 0
            while n < min(len(q), len(w)) and q[n] == w[n]:
                n += 1
            if n >= min(4, len(w)) and n > best:
                best = n
    return best


def _candidates(hass) -> list[dict]:
    """Every HC instance with a summary, and every room of a room thermostat (a TRV room has its own)."""
    out = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        c = getattr(entry, "runtime_data", None)
        if c is None or not hasattr(c, "plain_summary"):
            continue
        conf = {**entry.data, **entry.options}
        role = conf.get("role", "standalone")
        out.append({"kind": "instance", "name": entry.title, "c": c, "role": role,
                    "live": conf.get("mode") == "active"})
        for key, st in (getattr(c, "room_states", None) or {}).items():
            out.append({"kind": "room", "name": st.get("name") or key, "area": st.get("area"), "c": c, "state": st,
                        "trv": bool(st.get("trv")), "role": role, "host": entry.title})
    return out


def _area_name(hass, area_id: str | None) -> str:
    if not area_id:
        return ""
    try:
        from homeassistant.helpers import area_registry as ar
        area = ar.async_get(hass).async_get_area(area_id)
        return area.name if area else ""
    except Exception:
        return ""


def _speech(text: str, lang: str) -> str:
    return text.replace(" °C", " fok" if lang == "hu" else " degrees")


def answer(hass, query: str | None, language: str) -> str:
    from .core.summary import summarize_room
    lang = "hu" if str(language or "").startswith("hu") else "en"
    hu = lang == "hu"
    cands = _candidates(hass)
    if not cands:
        return "Nincs HC fűtésvezérlő." if hu else "There is no HC heating control."
    pick = None
    if query:
        words = _norm(query)
        scored = [(max(_score(words, x["name"]), _score(words, _area_name(hass, x.get("area")))), x) for x in cands]
        scored = [(s, x) for s, x in scored if s > 0]
        if scored:
            pick = max(scored, key=lambda sx: (sx[0], sx[1]["kind"] == "room"))[1]
    if pick is None:  # the house: a live room thermostat first, else any room thermostat, else the first instance
        rooms = [x for x in cands if x["kind"] == "instance" and x["role"] in ("standalone", "zone")]
        pick = next((x for x in rooms if x["live"]), rooms[0] if rooms else next(x for x in cands if x["kind"] == "instance"))
    if pick["kind"] == "room" and pick["trv"]:
        s = summarize_room(pick["state"], lang)
        title = pick["name"]
    elif pick["kind"] == "room":
        s = pick["c"].plain_summary(lang)
        title = (f"{pick['name']} a ház fűtését követi ({pick['host']})" if hu
                 else f"{pick['name']} follows the house's heating ({pick['host']})")
    else:
        s = pick["c"].plain_summary(lang)
        title = pick["name"]
    if not s:
        return (f"{title}: még nincs döntés." if hu else f"{title}: no decision yet.")
    parts = [f"{title}: {s['headline']}."] + list(s["lines"][:2])
    if s.get("note"):
        parts.insert(1, s["note"])
    return _speech(" ".join(parts), lang)


class WhyHeatingHandler(intent.IntentHandler):
    """Why the heating (HC Thermostat) is heating or not – in plain words."""

    intent_type = INTENT_WHY
    description = ("Explains in plain words why the heating (HC Thermostat) is or is not heating right now, where its "
                   "target temperature comes from and when it changes next. Optionally give the name of a room, an "
                   "area or a heating instance; without it the whole house is answered.")
    # "name" for an LLM agent; "hc_nev" / "hc_name" for custom sentences (a list called "name" would override Home
    # Assistant's own entity name list)
    slot_schema = {vol.Optional("name"): cv.string, vol.Optional("hc_nev"): cv.string, vol.Optional("hc_name"): cv.string}
    platforms = None

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        slots = self.async_validate_slots(intent_obj.slots)
        query = next(((slots.get(k) or {}).get("value") for k in ("name", "hc_nev", "hc_name") if slots.get(k)), None)
        text = answer(intent_obj.hass, query, intent_obj.language)
        response = intent_obj.create_response()
        response.response_type = intent.IntentResponseType.QUERY_ANSWER
        response.async_set_speech(text)
        return response

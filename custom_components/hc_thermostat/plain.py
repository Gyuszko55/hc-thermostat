"""0.87.0: the plain "why heating / why not" summary of a central boiler, buffer tank, mixing circuit or heat pump
coordination instance (core/summary_roles.py) – their coordinators' `plain_summary()` call this."""

from __future__ import annotations

import logging

from .const import MODE_SHADOW

_LOGGER = logging.getLogger(__name__)


def _names(hass, ids) -> dict:
    out = {}
    for entity_id in ids or ():
        st = hass.states.get(entity_id) if isinstance(entity_id, str) and "." in entity_id else None
        if st is not None:
            out[entity_id] = st.attributes.get("friendly_name", entity_id)
    return out


def role_plain(c, role: str, language: str | None = None) -> dict | None:
    d = getattr(c, "data", None)
    if d is None:
        return None
    from .core import summary_roles as sr
    lang = language or str(getattr(c.hass.config, "language", "") or "en")
    write = getattr(c, "write", None)
    mode = getattr(write, "mode", None) or getattr(c, "mode", None) or MODE_SHADOW
    live = mode != MODE_SHADOW
    try:
        if role == "buffer":
            return sr.summarize_buffer(d, lang, live, _names(c.hass, d.asking))
        if role == "central":
            return sr.summarize_central(d, lang, live, _names(c.hass, [*d.asking, *(d.details or {}).get("stuck", [])]))
        if role == "circuit":
            return sr.summarize_circuit(d, lang, live, _names(c.hass, [*d.lasting, *d.asking]))
        if role == "hp_coord":
            return sr.summarize_hp(d, lang, live)
    except Exception:  # the summary is a report – it must never stop anything
        _LOGGER.debug("No plain summary for %s", role, exc_info=True)
    return None


SUMMARY_KEYS = ("summary", "summary_state", "summary_headline", "summary_lines", "summary_note")


def _summary_attrs(c) -> dict:
    """0.84.0: the plain summary as one paragraph and its state word key (heating / idle / paused / …)."""
    try:
        from .core.summary import as_text
        s = c.plain_summary()
    except Exception:  # never let a report line take the decision sensor down
        return {}
    if not s:
        return {}
    # 0.87.0: also as headline + lines (the dial card shows the headline and the first line, the rest on a tap)
    return {"summary": as_text(s), "summary_state": s["state"], "summary_headline": s["headline"],
            "summary_lines": list(s["lines"]), "summary_note": s.get("note")}


def starting(hass) -> bool:
    """0.87.1: Home Assistant started less than core/summary.STARTING_S ago (the room thermometers may not have
    reported yet)."""
    try:
        from homeassistant.util import dt as dt_util
        from .coordinator import ha_started
        from .core.summary import STARTING_S
        t = ha_started(hass)
        return t is not None and (dt_util.utcnow() - t).total_seconds() < STARTING_S
    except Exception:
        return False

"""0.89.0: the numbers of the last days for the goals' estimate and the advice (core/tuning.py), from the
recorder. Read only; cached for half an hour per instance."""

from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

import voluptuous as vol
from homeassistant.components import websocket_api

from .ai_report import _history, _series
from .const import DOMAIN
from .core import day_report as dr

_LOGGER = logging.getLogger(__name__)
DAYS = 7
GAP_S = 1800.0
_CACHE: dict[str, tuple[float, dict]] = {}


def _thermostat(hass, entry) -> str | None:
    try:
        reg = er.async_get(hass)
        for ent in er.async_entries_for_config_entry(reg, entry.entry_id):
            if ent.domain == "climate" and (ent.unique_id or "").removeprefix(f"{entry.entry_id}_") == "thermostat":
                return ent.entity_id
    except Exception:
        _LOGGER.debug("No thermostat entity", exc_info=True)
    return None


def runs(points: list, start, end) -> list[float]:
    """The length (s) of every on-stretch of an on/off series within [start, end)."""
    out, began, prev = [], None, None
    for t, v in points:
        if t < start:
            prev = v
            began = start if v is True else None
            continue
        if t >= end:
            break
        if v is True and prev is not True:
            began = t
        elif v is not True and prev is True and began is not None:
            out.append((t - began).total_seconds())
            began = None
        prev = v
    return out


def gaps(points: list, start, end, limit: float = GAP_S) -> list[float]:
    """Stretches (s) over `limit` while a sensor was unavailable or unknown."""
    out, began = [], None
    for t, v in [*points, (end, "end")]:
        t = max(t, start)
        bad = v is None and v != "end"
        if bad and began is None:
            began = t
        elif not bad and began is not None:
            if (t - began).total_seconds() > limit:
                out.append((t - began).total_seconds())
            began = None
    return out


async def async_stats(hass, entry, conf: dict) -> dict | None:
    hit = _CACHE.get(entry.entry_id)
    if hit and time.monotonic() - hit[0] < 1800:
        return hit[1]
    end = dt_util.now()
    start = end - timedelta(days=DAYS)
    climate = _thermostat(hass, entry)
    actuator = conf.get("actuator_entity") if (conf.get("control") or "tpi") in ("tpi", "pid", "onoff") else None
    indoor = conf.get("indoor_entity")
    ids = [e for e in (climate, actuator, indoor) if isinstance(e, str)]
    data = await _history(hass, ids, start, end)
    if not data:
        return None
    out: dict = {}
    first = None
    if climate and data.get(climate):
        cs = _series(data[climate], "climate")
        first = next((t for t, v in cs if isinstance(v, tuple) and v[1] is not None), None)
        stats = dr.climate_stats(cs, start, end)
        span_s = (end - max(first or start, start)).total_seconds()
        days = max(span_s / 86400, 0.0)
        out["days"] = round(days, 1)
        if days > 0:
            out["cold_h_day"] = stats["cold_h"] / days
            out["overheated_h_day"] = stats["overheated_h"] / days
        dev, n = 0.0, 0
        for _, v in cs:
            if isinstance(v, tuple) and v[0] == "heat" and v[1] is not None and v[2] is not None:
                dev += abs(v[1] - v[2])
                n += 1
        if n:
            out["dev_c"] = dev / n
        if not actuator:
            heat = [(t, None if not isinstance(v, tuple) or v[0] in ("unavailable", "unknown") else v[3] == "heating")
                    for t, v in cs]
            r = runs(heat, max(first or start, start), end)
            if days > 0:
                out["starts_day"] = len(r) / days
    if actuator and data.get(actuator):
        series = _series(data[actuator], "on")
        begin = max(first or series[0][0], start)
        days = max((end - begin).total_seconds() / 86400, 0.0)
        out.setdefault("days", round(days, 1))
        r = runs(series, begin, end)
        if days > 0 and r:
            out["starts_day"] = len(r) / days
            from .core.tuning import effective
            min_on = float(effective(conf).get("min_on_s") or 300.0)
            out["short_runs_pct"] = 100.0 * sum(1 for x in r if x < 1.5 * min_on) / len(r)
    if indoor and data.get(indoor):
        g = gaps(_series(data[indoor], "number"), start, end)
        if g:
            out["quiet_gaps"] = len(g)
            out["longest_gap_h"] = max(g) / 3600
    _CACHE[entry.entry_id] = (time.monotonic(), out)
    return out


async def async_advice(hass, entry, lang: str) -> dict:
    from .core.tuning import advice_text, advise
    conf = {**entry.data, **entry.options}
    if conf.get("role") not in (None, "standalone", "zone"):
        return {"items": [], "text": ""}
    stats = await async_stats(hass, entry, conf)
    items = advise(stats, conf)
    return {"items": items, "days": (stats or {}).get("days"),
            "text": advice_text(items, lang, (stats or {}).get("days") or 0.0, shadow=conf.get("mode") != "active")}


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/advice", vol.Required("entry_id"): str,
                                  vol.Optional("language"): str})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_advice(hass, connection, msg) -> None:
    """0.89.0: advice from the last days' numbers, for the HC info panel."""
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        connection.send_error(msg["id"], "not_found", "no such HC instance")
        return
    lang = "hu" if str(msg.get("language") or hass.config.language or "").startswith("hu") else "en"
    try:
        connection.send_result(msg["id"], await async_advice(hass, entry, lang))
    except Exception:  # advice never breaks the panel
        _LOGGER.exception("The advice failed")
        connection.send_result(msg["id"], {"items": [], "text": ""})

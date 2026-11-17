"""0.71.0 – AI analysis of a house's heating: yesterday's numbers worked out by HC from the recorder
(core/day_report.py), explained by the user's own AI Task entity (`ai_task_entity`) with observations and things to
do. It only advises: nothing is changed by it.

It belongs to the house's leading instance (the one the HC info panel shows the house under) and covers every member
of that house: rooms, plant, sources. Made every day at `ai_report_time` (only with an AI Task entity given) and on
request (the button, the panel). Without an AI Task entity the numbers alone are kept. The result is kept over a
restart and announced with the `hc_thermostat_ai_report` event.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import json
import logging

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (CONF_BOILER_POWER, CONF_BOILER_PRICE, CONF_BOILER_PRICE_MANUAL, CONF_CONTROL, CONF_ENERGY_FACTOR,
                    CONF_HEAT_ENERGY, CONF_HEAT_SOURCE, CONF_MODE, CONF_OTHER_PRICE, CONF_OTHER_PRICE_MANUAL,
                    CONF_OUTDOOR, CONF_ROLE, CONF_SYSTEM, DOMAIN)
from .core import day_report as dr

_LOGGER = logging.getLogger(__name__)
CONF_AI_TASK = "ai_task_entity"
CONF_AI_TIME = "ai_report_time"
AI_TIME_DEFAULT = "06:30:00"
EVENT = f"{DOMAIN}_ai_report"
ELECTRIC = ("heat_pump", "electric_boiler", "air_conditioner", "electric_heater", "storage_heater")
# the entities of a member worth a day's look, by the key in their unique id (f"{entry_id}_{key}")
KEYS = {"decision": "states", "boiler_health": "states", "fault": "on", "buffer_decision": "states",
        "buffer_charge": "number", "circuit_target": "number", "circuit_demand": "on", "hp_decision": "states",
        "hp_enable": "on", "hp_target": "number", "central_decision": "states", "central_pump": "on"}


def _num(value):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _price(hass, conf: dict, entity_key: str, manual_key: str) -> float | None:
    state = hass.states.get(conf.get(entity_key)) if conf.get(entity_key) else None
    value = _num(state.state) if state is not None else None
    return value if value else (_num(conf.get(manual_key)) or None)


def day_bounds(now: datetime) -> tuple[datetime, datetime]:
    """Yesterday, local midnight to midnight."""
    today = dt_util.start_of_local_day(now)
    return today - timedelta(days=1), today


async def _history(hass, entity_ids: list[str], start: datetime, end: datetime) -> dict:
    if not entity_ids:
        return {}
    from homeassistant.components.recorder import get_instance, history

    def fetch():
        return history.get_significant_states(hass, start - timedelta(hours=6), end, entity_ids,
                                              significant_changes_only=False, minimal_response=False,
                                              no_attributes=False, include_start_time_state=True)
    try:
        return await get_instance(hass).async_add_executor_job(fetch) or {}
    except Exception:  # no recorder, a purged day: the numbers that can be had
        _LOGGER.debug("No history for the AI report", exc_info=True)
        return {}


def _series(states, kind: str) -> list:
    out = []
    for s in states or []:
        t = getattr(s, "last_updated", None) or getattr(s, "last_changed", None)
        v = s.state
        if kind == "number":
            v = _num(v)
        elif kind == "on":
            v = None if v in ("unavailable", "unknown") else v == "on"
        elif kind == "climate":
            a = s.attributes or {}
            v = (s.state, _num(a.get("current_temperature")), _num(a.get("temperature")), a.get("hvac_action"),
                 a.get("preset_mode"))
        out.append((t, v))
    return out


def house_entries(hass, host_id: str) -> list:
    """The host instance first, then the members of its house (loaded ones only)."""
    from .info import house_links
    link = house_links(hass).get(host_id)
    ids = [host_id] + ([m for m in link.members if m != host_id] if link is not None and link.host == host_id else [])
    out = []
    for i in ids:
        e = hass.config_entries.async_get_entry(i)
        if e is not None and getattr(e, "runtime_data", None) is not None:
            out.append(e)
    return out


async def collect(hass, host_entry, now: datetime | None = None) -> dict:
    """The numbers of yesterday for the whole house."""
    now = now or dt_util.now()
    start, end = day_bounds(now)
    reg = er.async_get(hass)
    entries = house_entries(hass, host_entry.entry_id)
    wanted: dict[str, tuple] = {}  # entity id -> (entry id, key, kind)
    for e in entries:
        for ent in er.async_entries_for_config_entry(reg, e.entry_id):
            key = (ent.unique_id or "").removeprefix(f"{e.entry_id}_")
            if key == "thermostat" and ent.domain == "climate":
                wanted[ent.entity_id] = (e.entry_id, key, "climate")
            elif key in KEYS:
                wanted[ent.entity_id] = (e.entry_id, key, KEYS[key])
    conf0 = {**host_entry.data, **host_entry.options}
    extra = {}
    for e in entries:
        c = {**e.data, **e.options}
        for k in (CONF_HEAT_ENERGY, CONF_BOILER_POWER):
            if c.get(k):
                extra[c[k]] = (e.entry_id, k)
    outdoor_id = conf0.get(CONF_OUTDOOR)
    ids = list(wanted) + list(extra) + ([outdoor_id] if outdoor_id else [])
    hist = await _history(hass, ids, start, end)
    members = []
    for e in entries:
        c = {**e.data, **e.options}
        role = c.get(CONF_ROLE, "standalone")
        m: dict = {"name": e.title, "role": role, "heat_source": c.get(CONF_HEAT_SOURCE), "system": c.get(CONF_SYSTEM),
                   "control": c.get(CONF_CONTROL), "mode": c.get(CONF_MODE, "shadow")}
        for k in ("target_home", "target_night", "target_eco", "target_away", "night_start", "night_end"):
            if c.get(k) is not None and role in ("standalone", "zone"):
                m[k] = c[k]
        for eid, (owner, key, kind) in wanted.items():
            if owner != e.entry_id:
                continue
            series = _series(hist.get(eid), kind)
            if kind == "climate":
                m["thermostat"] = dr.climate_stats(series, start, end)
            elif kind == "states":
                m[key] = dr.durations(series, start, end)
            elif kind == "on":
                m[key] = dr.on_stats(series, start, end)
            else:
                m[key] = dr.number_stats(series, start, end)
        # energy and cost: a fuel / energy meter, a power meter, or heating hours × the rated power
        electric = c.get(CONF_HEAT_SOURCE) in ELECTRIC
        fuel = power_kwh = None
        if c.get(CONF_HEAT_ENERGY):
            fuel = dr.meter_delta(_series(hist.get(c[CONF_HEAT_ENERGY]), "number"), start, end)
        if c.get(CONF_BOILER_POWER):
            st = hass.states.get(c[CONF_BOILER_POWER])
            unit = str((st.attributes.get("unit_of_measurement") if st else "") or "")
            to_kw = {"W": 0.001, "kW": 1.0}.get(unit)
            if to_kw:
                power_kwh = dr.energy_kwh_from_power(_series(hist.get(c[CONF_BOILER_POWER]), "number"), start, end, to_kw)
        heating_h = ((m.get("thermostat") or {}).get("heating") or {}).get("hours")
        if heating_h is None and m.get("hp_enable"):
            heating_h = m["hp_enable"]["hours"]
        price = (_price(hass, c, CONF_OTHER_PRICE, CONF_OTHER_PRICE_MANUAL) or _price(hass, c, CONF_BOILER_PRICE, CONF_BOILER_PRICE_MANUAL)) \
            if electric else _price(hass, c, CONF_BOILER_PRICE, CONF_BOILER_PRICE_MANUAL)
        energy = dr.energy_and_cost(heating_h, float(c.get("boiler_power_kw") or 0), None if electric else fuel,
                                    float(c.get(CONF_ENERGY_FACTOR) or 0), price,
                                    fuel if electric and fuel is not None else power_kwh, electric)
        if energy:
            if "fuel" in energy and c.get(CONF_HEAT_ENERGY):
                st = hass.states.get(c[CONF_HEAT_ENERGY])
                energy["unit"] = (st.attributes.get("unit_of_measurement") if st else None) or None
            if "cost" in energy:
                energy["currency"] = getattr(hass.config, "currency", None)
            m["energy"] = energy
        members.append(m)
    issues = []
    for (domain, issue_id), issue in ir.async_get(hass).issues.items():
        if domain == DOMAIN and issue.active and not issue.dismissed_version:
            issues.append({"kind": issue.translation_key, **(issue.translation_placeholders or {})})
    out_stats = dr.number_stats(_series(hist.get(outdoor_id), "number"), start, end) if outdoor_id else None
    return {"house": host_entry.title, "day": start.date().isoformat(), "outdoor": out_stats, "members": members,
            "open_issues": issues}


PROMPT = {
    "hu": """Egy Home Assistant HC Thermostat-tal vezérelt ház tegnapi fűtését értékeld, MAGYARUL, tömören, laikusnak is érthetően.
Csak az alábbi adatokból dolgozz: ne találj ki számot, eszközt vagy eseményt. A számokat a HC számolta a naplóból.
Mezők: thermostat.room = helyiség-hőmérséklet (átlag/min/max), target = cél, cold_h = órák a cél alatt 0,3 °C-nál
többel, overheated_h = órák a cél fölött 0,5 °C-nál többel, heating = fűtési órák és indítások, presets = órák
üzemmódonként, decision/…_decision = órák döntési okonként, energy = energia/költség (how: measured = mért,
estimated = becsült), mode: shadow = csak számol, nem kapcsol; active = vezérel. open_issues = nyitott HC-jelzések.
Ha egy példány a célja fölött volt, de alig vagy egyáltalán nem fűtött, azt a ház többi hőforrása melegítette – ez
nem az ő hibája és nem érzékelőhiba. Egy mindig fűtő (heating 24 h) klímánál a fűtési óra csak az üzemmódot jelzi.
Teendőnek csak konkrét, ellenőrizhető javaslatot írj (beállítás neve, eszköz ellenőrzése); ha minden rendben, írd:
„Nincs teendő.” A HC semmit nem állít át magától – ezek javaslatok a felhasználónak.""",
    "en": """Assess yesterday's heating of a house run by the Home Assistant HC Thermostat, in ENGLISH, briefly, for a layperson.
Use only the data below: invent no number, device or event. HC worked the numbers out from the recorder.
Fields: thermostat.room = room temperature (mean/min/max), target = target, cold_h = hours more than 0.3 °C below
target, overheated_h = hours more than 0.5 °C above, heating = heating hours and starts, presets = hours per mode,
decision/…_decision = hours per decision reason, energy = energy/cost (how: measured / estimated), mode: shadow =
only works out, switches nothing; active = in control. open_issues = open HC warnings.
An instance above its target while it hardly heated or not at all was warmed by the house's other sources – not its
fault and not a sensor fault. For an AC heating all day (heating 24 h) the hours only show its mode.
Things to do: only concrete, checkable suggestions (a setting's name, a device to check); if all is well, write
"Nothing to do." HC changes nothing by itself – these are suggestions for the user.""",
}
STRUCTURE = {
    "hu": {"score": "A nap fűtésének pontszáma 1–10 (10 = kényelmes és takarékos, hiba nélkül).",
           "summary": "2–3 mondatos összefoglaló.",
           "observations": "Legfeljebb 5 megfigyelés, mindegyik új sorban.",
           "todos": "Legfeljebb 4 konkrét teendő, mindegyik új sorban; vagy „Nincs teendő.”"},
    "en": {"score": "The day's heating score 1–10 (10 = comfortable and economical, no faults).",
           "summary": "A 2–3 sentence summary.",
           "observations": "At most 5 observations, each on a new line.",
           "todos": "At most 4 concrete things to do, each on a new line; or \"Nothing to do.\""},
}


async def ask_ai(hass, ai_entity: str, facts: dict, lang: str) -> dict:
    words = STRUCTURE[lang]
    structure = {"score": {"description": words["score"], "required": True,
                           "selector": {"number": {"min": 1, "max": 10, "step": 1}}}}
    for k in ("summary", "observations", "todos"):
        structure[k] = {"description": words[k], "required": True, "selector": {"text": {"multiline": True}}}
    resp = await hass.services.async_call(
        "ai_task", "generate_data",
        {"task_name": f"HC – {facts.get('house')} {facts.get('day')}", "entity_id": ai_entity,
         "instructions": PROMPT[lang] + "\n\n" + json.dumps(facts, ensure_ascii=False, default=str),
         "structure": structure},
        blocking=True, return_response=True)
    data = (resp or {}).get("data") or {}
    return {"score": _num(data.get("score")), "summary": str(data.get("summary") or "").strip(),
            "observations": dr.parse_lines(data.get("observations")), "todos": dr.parse_lines(data.get("todos"))}


class AiReporter:
    """Keeps and makes the house's report; owned by the leading instance's coordinator."""

    def __init__(self, hass, entry) -> None:
        self.hass, self.entry = hass, entry
        self.report: dict | None = None
        self.running = False
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.ai_report")

    async def async_load(self) -> None:
        try:
            self.report = await self._store.async_load()
        except Exception:
            self.report = None

    @property
    def ai_entity(self) -> str | None:
        return {**self.entry.data, **self.entry.options}.get(CONF_AI_TASK) or None

    async def async_run(self, now: datetime | None = None) -> dict:
        if self.running:
            return self.report or {}
        self.running = True
        now = now or dt_util.now()
        lang = "hu" if str(getattr(self.hass.config, "language", "") or "").startswith("hu") else "en"
        try:
            facts = await collect(self.hass, self.entry, now)
            report: dict = {"day": facts["day"], "made": now.isoformat(), "facts": facts, "ai": None, "error": None,
                            "ai_entity": self.ai_entity}
            if self.ai_entity:
                try:
                    report["ai"] = await ask_ai(self.hass, self.ai_entity, facts, lang)
                except Exception as err:  # the numbers are kept, the AI's answer is missing
                    _LOGGER.warning("HC AI report: the AI Task did not answer: %s", err)
                    report["error"] = str(err)
            self.report = report
            await self._store.async_save(report)
            ai = report.get("ai") or {}
            self.hass.bus.async_fire(EVENT, {"entry_id": self.entry.entry_id, "house": facts["house"],
                                             "day": facts["day"], "score": ai.get("score"),
                                             "summary": ai.get("summary"), "todos": ai.get("todos") or []})
            return report
        finally:
            self.running = False

    def daily_time(self) -> tuple[int, int, int]:
        raw = str({**self.entry.data, **self.entry.options}.get(CONF_AI_TIME) or AI_TIME_DEFAULT)
        try:
            parts = [int(p) for p in raw.split(":")] + [0, 0]
            return parts[0] % 24, parts[1] % 60, parts[2] % 60
        except ValueError:
            return 6, 30, 0

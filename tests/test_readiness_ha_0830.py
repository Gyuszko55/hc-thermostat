"""0.83.0: the go-live checklist's facts from Home Assistant (readiness.py) and where it stops going live."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

rd = importlib.import_module("hc_thermostat.readiness")
cf = importlib.import_module("hc_thermostat.config_flow")

NOW = datetime.now(timezone.utc)


def _st(state="21.0", age_s=60, **attrs):
    t = NOW - timedelta(seconds=age_s)
    return SimpleNamespace(state=state, attributes=attrs, last_updated=t, last_reported=t)


def _hass(states, entries=(), data=None):
    entries = list(entries)
    return SimpleNamespace(
        states=SimpleNamespace(get=states.get), data=data or {}, config=SimpleNamespace(language="hu"),
        config_entries=SimpleNamespace(async_entries=lambda d: entries,
                                       async_get_entry=lambda i: next((e for e in entries if e.entry_id == i), None)))


def _entry(entry_id="a", title="Nappali", runtime=None, **conf):
    return SimpleNamespace(entry_id=entry_id, title=title, domain="hc_thermostat", data=conf, options={},
                           runtime_data=runtime)


BASE = {"role": "standalone", "control": "tpi", "indoor_entity": "sensor.living", "actuator_entity": "switch.boiler",
        "outdoor_entity": "sensor.out", "window_entities": ["binary_sensor.w"]}


def test_outputs_inputs_and_missing_by_role():
    assert rd.outputs_of(BASE) == [("actuator_entity", "switch.boiler")]
    trv = {"role": "standalone", "control": "trv", "actuator_entity": "switch.x",
           "rooms": [{"trvs": ["climate.a", "climate.b"], "sensors": ["sensor.r"]}]}
    assert rd.outputs_of(trv) == [("trv_heads", "climate.a"), ("trv_heads", "climate.b")]  # no relay under TRVs
    assert ("room_sensors", "sensor.r", "input") in rd.inputs_of(trv)
    assert rd.outputs_of({"role": "hp_coord", "hp_switch_entity": "switch.hp"}) == [("hp_switch_entity", "switch.hp")]
    assert rd.inputs_of({"role": "buffer", "buffer_top_entity": "sensor.top"}) == [("buffer_top_entity", "sensor.top", "core")]
    assert ("outdoor_entity", "sensor.out", "core") in rd.inputs_of({**BASE, "control": "curve"})
    hass = _hass({})
    assert rd.missing_of(hass, {"role": "standalone", "control": "tpi"}) == ["indoor_entity", "output"]
    assert rd.missing_of(hass, {"role": "standalone", "control": "external", "external_climate": "climate.t"}) == []
    assert rd.missing_of(hass, {"role": "central"}) == ["zone_entities", "boiler_entity"]
    assert rd.missing_of(hass, {"role": "hp_coord", "hp_switch_entity": "switch.hp", "hp_buffer": "gone"}) == ["hp_buffer"]


def test_static_check_for_the_wizard():
    hass = _hass({"sensor.living": _st(), "switch.boiler": _st("off", age_s=9e5), "sensor.out": _st("4")})
    r = rd.static_check(hass, BASE)
    assert r["ready"] and r["warns"] == 1  # the window sensor does not exist: a warning
    assert [i["id"] for i in r["items"]] == ["entity_gone"]
    r = rd.static_check(_hass({"sensor.living": _st()}), BASE)
    assert not r["ready"] and r["head"] == "Még nem élesíthető: 1 akadály"


def test_another_instance_and_an_automation_on_the_same_output():
    other = _entry("b", "Fürdő HC", **{**BASE, "indoor_entity": "sensor.bath"})
    auto = SimpleNamespace(entity_id="automation.boiler_off",
                           action_script=SimpleNamespace(referenced_entities={"switch.boiler"}))
    notify = SimpleNamespace(entity_id="automation.boiler_notify",  # only triggered by it: no conflict
                             action_script=SimpleNamespace(referenced_entities={"notify.phone"}))
    hass = _hass({"sensor.living": _st(), "switch.boiler": _st("off"), "sensor.out": _st("4"),
                  "binary_sensor.w": _st("off"), "automation.boiler_off": _st("on", friendly_name="Kazán ki")},
                 entries=[other], data={"automation": SimpleNamespace(entities=[auto, notify])})
    r = rd.static_check(hass, BASE, entry_id="a")
    ids = {i["id"]: i for i in r["items"]}
    assert ids["hc_conflict"]["level"] == "block" and "Fürdő HC" in ids["hc_conflict"]["title"]
    assert ids["automation_conflict"]["level"] == "warn" and "Kazán ki" in ids["automation_conflict"]["title"]


class _Guard:
    def __init__(self, answer):
        self.answer, self.asked = answer, 0
        self.link = SimpleNamespace(problem=lambda now: None)

    async def probe(self, now):
        self.asked += 1
        return self.answer


def _coord(**kw):
    base = dict(mode="shadow", data=object(), sensor_problems={}, step_errors=0, log=[], safety=None, guard=None,
                mode_since=NOW - timedelta(hours=30),
                cfg=SimpleNamespace(target_home=21, target_night=19, target_away=17, target_vacation=15, frost_temp=7,
                                    night_start="22:00", night_end="06:00"))
    base.update(kw)
    return SimpleNamespace(**base)


def _states():
    return {"sensor.living": _st(age_s=9e4), "switch.boiler": _st("off"), "sensor.out": _st("4"),
            "binary_sensor.w": _st("off")}


def test_async_check_of_a_running_instance():
    guard = _Guard("ok")
    c = _coord(guard=guard)
    entry = _entry(runtime=c, **BASE)
    r = asyncio.run(rd.async_check(_hass(_states(), [entry]), entry, "en"))
    # a room thermostat's sensors are judged by its own watch, not by the age of the last report (a BLE sensor
    # sends on change only)
    assert r["ready"] and r["warns"] == 0 and guard.asked == 1
    c.sensor_problems = {"sensor.living": "stale"}
    c.mode_since = NOW - timedelta(hours=3)
    c.log = [{"time": NOW.isoformat(), "fault": "sensor"}, {"time": (NOW - timedelta(days=2)).isoformat(), "fault": "x"}]
    r = asyncio.run(rd.async_check(_hass(_states(), [entry]), entry, "en"))
    assert {i["id"] for i in r["items"] if i["level"] == "warn"} == {"entity_stale", "short_shadow", "faults"}
    assert "1 decisions with a fault" in next(i["title"] for i in r["items"] if i["id"] == "faults")
    c.guard, c.data = _Guard("ClientConnectorError"), None
    c.safety = SimpleNamespace(latch=SimpleNamespace(tripped=True))
    r = asyncio.run(rd.async_check(_hass(_states(), [entry]), entry, "en"))
    assert {i["id"] for i in r["items"] if i["level"] == "block"} == {"no_decision", "safety_tripped", "guard_unreachable"}


def test_a_buffer_sensor_is_judged_by_its_age_and_lite_is_left_out():
    c = SimpleNamespace(mode="shadow", data=object(), failsafe=SimpleNamespace(errors=0), log=[])
    entry = _entry(runtime=c, role="buffer", buffer_top_entity="sensor.top")
    r = asyncio.run(rd.async_check(_hass({"sensor.top": _st("60", age_s=3 * 3600)}, [entry]), entry, "hu"))
    assert [i["id"] for i in r["items"] if i["level"] == "warn"] == ["entity_stale"]
    lite = _entry(runtime=SimpleNamespace(), role="lite")
    assert asyncio.run(rd.async_check(_hass({}, [lite]), lite))["ready"] is None


def test_going_live_is_refused_only_from_shadow_with_a_blocker(monkeypatch):
    async def blocked(hass, entry, lang=None, conf=None):
        return {"ready": False}
    monkeypatch.setattr(rd, "async_check", blocked)
    run = lambda current, ui: asyncio.run(cf._not_ready(None, None, current, ui))  # noqa: E731
    assert run({"mode": "shadow"}, {"mode": "active"}) == {"base": "not_ready"}
    assert run({"mode": "shadow"}, {"mode": "trial"}) == {"base": "not_ready"}
    assert run({"mode": "shadow"}, {"mode": "shadow"}) == {}  # staying in shadow: never stopped
    assert run({"mode": "active"}, {"mode": "active"}) == {}  # already live: editing a setting is not going live

    async def broken(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(rd, "async_check", broken)
    assert run({"mode": "shadow"}, {"mode": "active"}) == {}  # a failing checklist never stops the form


def test_the_go_live_form_shows_the_list_and_texts_exist():
    import json
    src = (ROOT / "custom_components/hc_thermostat/config_flow.py").read_text()
    assert '"checklist": as_text(ready)' in src and 'errors["base"] = "not_ready"' in src
    for lang in ("hu", "en"):
        t = json.loads((ROOT / f"custom_components/hc_thermostat/translations/{lang}.json").read_text())
        assert "{checklist}" in t["options"]["step"]["go_live"]["description"]
        assert t["options"]["error"]["not_ready"]
    js = (ROOT / "custom_components/hc_thermostat/www/hc-info-panel.js").read_text()
    assert 'type: "hc_thermostat/readiness"' in js and "Élesíthető?" in js
    wjs = (ROOT / "custom_components/hc_thermostat/www/hc-wizard-panel.js").read_text()
    assert "this._readiness()" in wjs

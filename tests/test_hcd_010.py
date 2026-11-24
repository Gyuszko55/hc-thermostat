"""hcd 0.1.0 (F2): the standalone service – settings, feeds, the engine (inputs as the integration builds them),
the shadow comparison and its page."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from hc_core.inputs import SampleTable
from hc_core.model import Reason

from hcd import compare as cmp_
from hcd import config as cfg_
from hcd import feeds
from hcd import import_ha
from hcd.engine import Engine
from hcd.web import render

TZ = ZoneInfo("Europe/Budapest")
T0 = datetime(2026, 11, 20, 14, 0, tzinfo=TZ)  # afternoon: home target, no night
UTC = timezone.utc

HC = {
    "name": "Boiler", "system": "radiator_single", "heat_source": "onoff_boiler", "control": "pid",
    "indoor_entity": "sensor.ht", "outdoor_entity": "sensor.out", "presence_entities": ["sensor.home"],
    "window_entities": ["binary_sensor.w1"], "zone_door_entities": ["binary_sensor.door"],
    "zone_temp_entity": "sensor.terrace", "zone_max_diff": 2.0, "actuator_entity": "switch.boiler",
    "flame_entity": "binary_sensor.flame", "heat_energy_entity": "sensor.gas", "extra_heat_entity": "sensor.ac",
    "window_drop_entities": ["sensor.ht", "sensor.kitchen"], "target_home": 22.5, "target_night": 21.0,
    "night_start": "22:00", "night_end": "05:30", "season_enabled": False, "learning_enabled": False,
    "rooms": [{"key": "nappali", "name": "Nappali", "area": "nappali", "sensors": ["sensor.ht"], "trvs": []},
              {"key": "terasz", "name": "Terasz", "area": "terasz", "sensors": ["sensor.terrace"], "trvs": [],
               "windows": ["binary_sensor.terrace_door"]}],
    "leading_room": "nappali",
}


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def fill(t, now, indoor="21.0", outdoor="5.0", home="Otthon", window="off", door="off", flame="off"):
    t.put("sensor.ht", indoor, now, {"unit_of_measurement": "°C"})
    t.put("sensor.out", outdoor, now, {"unit_of_measurement": "°C"})
    t.put("sensor.home", home, now)
    t.put("binary_sensor.w1", window, now)
    t.put("binary_sensor.door", door, now)
    t.put("binary_sensor.terrace_door", "off", now)
    t.put("sensor.terrace", "18.0", now, {"unit_of_measurement": "°C"})
    t.put("binary_sensor.flame", flame, now)
    t.put("switch.boiler", "off", now)


# --- settings -----------------------------------------------------------------------------------------------------
def test_config_parses_and_checks():
    c = cfg_.parse({"hc": HC, "sources": {
        "sensor.ht": {"kind": "ha", "seen_from": "sensor.ht_seen"},
        "binary_sensor.w1": {"kind": "z2m", "device": "Door_1", "field": "contact", "invert": True},
        "switch.boiler": {"kind": "shelly_rpc", "host": "192.0.2.10"}},
        "ha": {"url": "http://ha", "token_env": "T"}, "mqtt": {"host": "broker"}}, env={"T": "secret"})
    assert c.ha_token == "secret" and c.sources["binary_sensor.w1"].invert and c.kinds() == {"ha", "z2m", "shelly_rpc"}
    with pytest.raises(cfg_.ConfigError):
        cfg_.parse({"hc": HC, "sources": {"x": {"kind": "z2m", "device": "D"}}, "mqtt": {"host": "b"}}, env={})
    with pytest.raises(cfg_.ConfigError):
        cfg_.parse({"hc": HC, "sources": {"x": {"kind": "ha"}}}, env={})  # no Home Assistant address
    with pytest.raises(cfg_.ConfigError):
        cfg_.parse({"sources": {}}, env={})


# --- feeds --------------------------------------------------------------------------------------------------------
def test_z2m_values():
    S = cfg_.Source
    assert feeds.z2m_value(S("b", "z2m", device="Door_1", field="contact", invert=True), {"contact": True}) == ("off", {})
    assert feeds.z2m_value(S("b", "z2m", device="Door_1", field="contact", invert=True), {"contact": False})[0] == "on"
    assert feeds.z2m_value(S("f", "z2m", device="P", field="power", above=115), {"power": 118})[0] == "on"
    assert feeds.z2m_value(S("f", "z2m", device="P", field="power", above=115), {"power": 7})[0] == "off"
    assert feeds.z2m_value(S("t", "z2m", device="T", field="temperature"), {"temperature": 22.34}) == (
        "22.34", {"unit_of_measurement": "°C"})
    assert feeds.z2m_value(S("t", "z2m", device="T", field="temperature"), {"humidity": 50}) is None


def test_apply_z2m_keeps_the_device_time():
    t = SampleTable()
    srcs = [cfg_.Source("sensor.kitchen", "z2m", device="Kitchen TH", field="temperature"),
            cfg_.Source("sensor.other", "z2m", device="Other", field="temperature")]
    now = datetime(2026, 11, 19, 21, 0, tzinfo=UTC)
    done = feeds.apply_z2m(t, srcs, "Kitchen TH", {"temperature": 22.5, "last_seen": "2026-11-19T20:50:38.000Z"}, now)
    assert done == ["sensor.kitchen"] and t.get("sensor.other") is None
    s = t.get("sensor.kitchen")
    assert s.seen == datetime(2026, 11, 19, 20, 50, 38, tzinfo=UTC) and s.last_reported == now


def test_apply_ha_with_seen_from():
    t = SampleTable()
    states = [{"entity_id": "sensor.ht", "state": "22.7", "attributes": {"unit_of_measurement": "°C"},
               "last_reported": "2026-11-19T20:50:14+00:00", "last_updated": "2026-11-19T20:49:47+00:00"},
              {"entity_id": "sensor.ht_seen", "state": "2026-11-19T20:55:07+00:00"}]
    src = [cfg_.Source("sensor.ht", "ha", seen_from="sensor.ht_seen"), cfg_.Source("sensor.gone", "ha")]
    assert feeds.apply_ha(t, src, states) == ["sensor.ht"]
    s = t.get("sensor.ht")
    assert s.seen == datetime(2026, 11, 19, 20, 55, 7, tzinfo=UTC)
    assert s.last_reported == datetime(2026, 11, 19, 20, 50, 14, tzinfo=UTC)


# --- the engine ---------------------------------------------------------------------------------------------------
def test_engine_needs_these_sources():
    e = Engine(HC, SampleTable(), None, at(-600))
    assert e.entities() == {"sensor.ht", "sensor.out", "sensor.home", "binary_sensor.w1", "binary_sensor.door",
                            "sensor.terrace", "switch.boiler", "binary_sensor.flame", "sensor.gas", "sensor.ac",
                            "sensor.kitchen", "binary_sensor.terrace_door"}
    assert e.unsupported == []
    assert Engine({**HC, "floor_entity": "sensor.floor"}, SampleTable(), None, at(0)).unsupported == ["floor_entity"]


def test_engine_heats_a_cold_house_and_stops_for_a_window():
    t = SampleTable()
    e = Engine(HC, t, None, at(-600))  # running for 10 minutes
    fill(t, at(0), indoor="20.0")
    d = e.step(at(0))
    assert d.target == 22.5 and d.reason in (Reason.BOOST, Reason.REGULATING) and d.output
    fill(t, at(5), indoor="20.0", window="on")
    for m in range(5, 9):
        d = e.step(at(m))
    assert d.reason == Reason.WINDOW and not d.output


def test_engine_zone_door_and_the_terrace_window():
    t = SampleTable()
    e = Engine(HC, t, None, at(-600))
    fill(t, at(0), indoor="22.0", door="on")  # the door to a 4 °C colder terrace: not coupled, counts as open
    assert e.build_inputs(at(0)).window_open
    fill(t, at(1), indoor="22.0")
    t.put("binary_sensor.terrace_door", "on", at(1))  # the terrace room's own contact (a room without TRVs)
    assert e.build_inputs(at(1)).window_open


def test_engine_restart_hold_until_a_real_report():
    t = SampleTable()
    e = Engine(HC, t, None, at(0))  # just started
    fill(t, at(0), indoor="22.0")
    assert e.step(at(1)).reason == Reason.RESTART_HOLD
    assert e.step(at(4)).reason == Reason.RESTART_HOLD  # past the 2-minute grace, still the first value
    fill(t, at(5), indoor="22.0")  # reported again after the settle time
    assert e.step(at(5)).reason != Reason.RESTART_HOLD


def test_engine_presence_and_flame():
    t = SampleTable()
    e = Engine({**HC, "target_away": 18.0}, t, None, at(-600))
    fill(t, at(0), indoor="21.0", home="Távol", flame="on")
    i = e.build_inputs(at(0))
    assert i.presence.value != "home" and i.actual_heating is True


def test_engine_saves_and_restores(tmp_path):
    t = SampleTable()
    e = Engine(HC, t, tmp_path / "state.json", at(-600))
    fill(t, at(0), indoor="20.0")
    e.step(at(0))
    assert (tmp_path / "state.json").exists()
    e2 = Engine(HC, t, tmp_path / "state.json", at(1))
    assert e2.load() and e2.sup.state()["pwm"] == e.sup.state()["pwm"]


def test_mirror_target_follows_home_assistant():
    t = SampleTable()
    e = Engine(HC, t, None, at(-600))
    fill(t, at(0), indoor="21.0")
    assert e.mirror_target("comfort", None, at(0)) and e.sup.preset == "comfort"
    assert not e.mirror_target("comfort", None, at(1))
    assert e.mirror_target("auto", 23.5, at(2)) and e.sup.preset is None and e.sup.manual_target == 23.5
    assert e.step(at(3)).target == 23.5


# --- comparison and page ------------------------------------------------------------------------------------------
def test_ha_side_and_day_summary(tmp_path):
    states = {"sensor.dec": {"state": "regulating"}, "switch.boiler": {"state": "on"},
              "climate.boiler_hc": {"attributes": {"demand": 24, "temperature": 22.5, "current_temperature": 22.1,
                                                  "preset_mode": "auto", "manual_target": None}}}
    side = cmp_.ha_side(states, {"decision": "sensor.dec", "climate": "climate.boiler_hc", "relay": "switch.boiler"})
    assert side == {"reason": "regulating", "relay": 1, "demand": 24.0, "target": 22.5, "indoor": 22.1,
                    "preset": "auto", "manual_target": None}
    c = cmp_.Comparison(tmp_path / "c.sqlite")
    t = SampleTable()
    e = Engine(HC, t, None, at(-600))
    for m in range(10):
        fill(t, at(m), indoor="20.0")
        d = e.step(at(m))
        c.record(at(m).astimezone(UTC), "2026-11-20", d, {**side, "relay": int(m < 5), "reason": d.reason.value})
    s = c.day_summary("2026-11-20", 60)
    assert s["steps"] == 10 and s["reason_agree_pct"] == 100.0 and s["ha_burn_min"] == 5.0
    assert s["hcd_burn_min"] == sum(r["hcd_output"] for r in c.recent()) * 1.0
    html = render({"name": "Boiler", "version": "0.1.0", "core": "0.78.1", "decision": {"reason": "regulating"},
                   "today": s, "recent": c.recent(), "days": [s], "feeds": {"Home Assistant": True}})
    assert "Boiler" in html and "regulating" in html and "2026-11-20" in html
    diff = c.disagreements("2026-11-20")
    assert len(diff) == 5 and all(r["hcd_output"] != r["ha_relay"] for r in diff)


def test_import_ha_builds_settings_and_state():
    diag = {"data": {"title": "Boiler", "data": {"indoor_entity": "sensor.ht"}, "options": HC,
                     "info": {"state": {"preset": None, "pwm": {"x": 1}}}}}
    settings, state = import_ha.build(diag, {"decision": "sensor.dec"})
    assert settings["hc"]["target_home"] == 22.5 and settings["compare"] == {"decision": "sensor.dec"}
    assert set(settings["sources"]) == Engine(HC, SampleTable(), None, at(0)).entities()
    assert all(v == {"kind": "ha"} for v in settings["sources"].values())
    assert state == {"supervisor": {"preset": None, "pwm": {"x": 1}}}


def test_disagreements_endpoint():
    import asyncio
    from aiohttp.test_utils import TestClient, TestServer
    from hcd.web import make_app

    asked = []

    def diff(day):
        asked.append(day)
        return [{"ts": "x", "hcd_reason": "boost", "ha_reason": "regulating"}]

    async def run():
        async with TestClient(TestServer(make_app(lambda: {}, diff))) as client:
            r = await client.get("/api/disagreements?day=2026-11-20")
            assert r.status == 200 and (await r.json())[0]["hcd_reason"] == "boost"
            r = await client.get("/api/disagreements")
            assert await r.json() == [{"ts": "x", "hcd_reason": "boost", "ha_reason": "regulating"}]

    asyncio.run(run())
    assert asked == ["2026-11-20", None]


# --- 0.1.3 (security review): the page --------------------------------------------------------------------------------
def test_page_binds_locally_by_default_and_lets_in_only_the_allowed(tmp_path):
    import asyncio
    from types import SimpleNamespace
    from hcd.config import load
    from hcd.web import make_app
    p = tmp_path / "hcd.yaml"
    p.write_text("name: X\nhc: {}\nsources: {}\n", encoding="utf-8")
    cfg = load(str(p))
    assert cfg.web_host == "127.0.0.1" and cfg.web_allow == []
    app = make_app(lambda: {"ok": True}, allow=["172.30.32.2"])
    (mw,) = app.middlewares

    async def handler(request):
        return "passed"

    async def go(remote):
        return await mw(SimpleNamespace(remote=remote), handler)

    assert asyncio.run(go("172.30.32.2")) == "passed"
    assert asyncio.run(go("192.0.2.7")).status == 403
    open_app = make_app(lambda: {})
    (mw2,) = open_app.middlewares
    assert asyncio.run(mw2(SimpleNamespace(remote="192.0.2.7"), handler)) == "passed"  # no list: as before


def test_addon_runs_unprivileged_and_reads_share_only():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "hcd" / "addon"
    run = (root / "run.sh").read_text()
    assert "exec su-exec hcd" in run and '["172.30.32.2"]+' in run and '--web-allow "$ALLOW"' in run
    assert "install -m 600 -o hcd" in run
    docker = (root / "Dockerfile").read_text()
    assert "adduser -D -H -s /sbin/nologin hcd" in docker and ">=" not in docker
    conf = (root / "config.yaml").read_text()
    assert "read_only: true" in conf and "share:rw" not in conf and "web_allow: []" in conf


def test_allow_list_takes_host_names_and_mapped_addresses(monkeypatch):
    import asyncio
    import socket
    from types import SimpleNamespace
    from hcd.web import _ip, make_app
    assert _ip("::ffff:172.30.32.2") == "172.30.32.2" and _ip("local-hcd") is None
    app = make_app(lambda: {}, allow=["172.30.32.2", "a1b2c3d4-my-addon"])
    (mw,) = app.middlewares

    async def handler(request):
        return "passed"

    async def go(remote):
        loop = asyncio.get_running_loop()

        async def fake(host, port, type=0):
            assert host == "a1b2c3d4-my-addon"
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.33.4", 0))]
        monkeypatch.setattr(loop, "getaddrinfo", fake)
        return await mw(SimpleNamespace(remote=remote), handler)

    assert asyncio.run(go("172.30.33.4")) == "passed"  # the named add-on
    assert asyncio.run(go("::ffff:172.30.32.2")) == "passed"  # the ingress proxy, IPv6-mapped
    assert asyncio.run(go("172.30.33.9")).status == 403


def test_allow_list_resolves_a_host_name_right_after_a_boot(monkeypatch):
    """monotonic() is the uptime: below 300 s (a fresh host or CI runner) the first lookup must still happen."""
    import asyncio
    import socket
    import time
    from types import SimpleNamespace
    from hcd.web import make_app
    monkeypatch.setattr(time, "monotonic", lambda: 42.0)
    app = make_app(lambda: {}, allow=["masik-addon"])
    (mw,) = app.middlewares

    async def handler(request):
        return "passed"

    async def go(remote):
        async def fake(host, port, type=0):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.30.33.7", 0))]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake)
        return await mw(SimpleNamespace(remote=remote), handler)

    assert asyncio.run(go("172.30.33.7")) == "passed"
    assert asyncio.run(go("172.30.33.8")).status == 403

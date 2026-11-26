"""0.79.2: HC Lite – the settings HC sends match the script's own, the status reads, the client talks to a Shelly."""

import asyncio
import importlib
import json
import re
import sys
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

lite = importlib.import_module("hc_thermostat.core.lite")
SCRIPT = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")
BASE = ROOT / "custom_components" / "hc_thermostat"


def _script_cfg_keys() -> set[str]:
    body = SCRIPT[SCRIPT.index("function cfgOut()"):SCRIPT.index("function status()")]
    return set(re.findall(r"(\w+): C\.", body))


def test_the_settings_are_the_scripts_own():
    payload = lite.settings_payload(lite.LiteSettings())
    assert set(payload) == _script_cfg_keys()


def test_settings_from_the_form_are_cleaned():
    s = lite.LiteSettings.from_conf({"lite_sp_day": 22.5, "lite_day": "05:30:00", "lite_night": "25:00",
                                     "lite_ctl": "pd", "lite_cycle": 900.4, "lite_hyst": 9, "lite_shadow": False})
    assert (s.sp_day, s.day, s.night, s.ctl, s.cycle, s.hyst, s.shadow) == (22.5, "05:30", "22:00", "hyst", 900, 0.4, False)
    assert lite.LiteSettings().shadow is True  # a new instance starts in shadow


def test_a_push_only_when_the_device_holds_something_else():
    p = lite.settings_payload(lite.LiteSettings())
    assert lite.needs_push(None, p)
    assert not lite.needs_push(dict(p), p)
    assert not lite.needs_push({**p, "sp_day": 21}, p)  # 21 == 21.0
    assert lite.needs_push({**p, "night": "21:30"}, p)
    assert lite.needs_push({k: v for k, v in p.items() if k != "kp"}, p)


def test_the_status_reads():
    v = lite.view({"v": 1, "mode": "away", "period": "away", "sp": 16, "temp": 19.4, "relay": True, "shadow": True,
                   "real_relay": False, "demand": None, "reason": "below target", "hold": None, "starts_today": 3,
                   "on_min_today": 41})
    assert (v.mode, v.target, v.temp, v.heating, v.shadow, v.real_relay, v.starts_today) == ("away", 16, 19.4, True, True, False, 3)
    assert lite.view({"error": "bad token"}) is None and lite.view(None) is None
    assert lite.view({"mode": "weird"}).mode == "auto"


def test_the_role_its_platforms_and_the_words():
    const = importlib.import_module("hc_thermostat.const")
    assert "lite" in const.ROLES and set(const.LITE_PLATFORMS) == {"binary_sensor", "climate", "sensor"}
    cf = importlib.import_module("hc_thermostat.config_flow")
    form = {str(k) for k in cf._lite_settings_fields({})}
    assert form == {f"lite_{k}" for k in lite.settings_payload(lite.LiteSettings())}
    for lang in ("en", "hu"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text("utf-8"))
        assert "lite" in tr["selector"]["role"]["options"]
        for sec in ("config", "options"):
            assert set(tr[sec]["step"]["lite_settings"]["data"]) == form
            assert {"lite_url", "lite_token", "lite_password"} <= set(tr[sec]["step"]["lite"]["data"])
            assert {"lite_url", "lite_token", "lite_password", "lite_unreachable"} <= set(tr[sec]["error"])
        for key in ("lite_ctl", "lite_ns", "lite_sensor"):
            assert set(tr["selector"][key]["options"])
        assert tr["entity"]["climate"]["lite_thermostat"] and tr["entity"]["binary_sensor"]["lite_boiler"]
        assert {"lite_reason", "lite_starts_today", "lite_on_today"} <= set(tr["entity"]["sensor"])


class FakeLite:
    """The script's endpoint: GET status, POST with the token (or 403)."""

    def __init__(self) -> None:
        self.cfg = None
        self.mode = "auto"
        self.log: list[str] = []

    def status(self) -> dict:
        return {"v": 1, "mode": self.mode, "sp": 21.0, "temp": 20.1, "relay": False, "shadow": True, "cfg": self.cfg}

    async def handle(self, request: web.Request) -> web.Response:
        if request.method == "GET":
            self.log.append("GET")
            return web.json_response(self.status())
        body = json.loads(await request.text())
        if body.get("tok") != "tok1":
            self.log.append("POST 403")
            return web.json_response({"error": "bad token"}, status=403)
        if "set" in body:
            self.cfg = body["set"]
        if "mode" in body:
            self.mode = body["mode"]
        self.log.append("POST " + ",".join(sorted(k for k in body if k != "tok")))
        return web.json_response(self.status())


def _with_device(fn, monkeypatch):
    import aiohttp
    ac = importlib.import_module("homeassistant.helpers.aiohttp_client")
    client = importlib.import_module("hc_thermostat.lite")

    async def main():
        fake = FakeLite()
        app = web.Application()
        app.router.add_route("*", "/script/1/lite", fake.handle)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        session = aiohttp.ClientSession()
        monkeypatch.setattr(ac, "async_get_clientsession", lambda hass: session)
        try:
            return await fn(client, f"http://127.0.0.1:{port}/script/1/lite", fake)
        finally:
            await session.close()
            await runner.cleanup()

    return asyncio.run(main())


def test_the_client_reads_and_writes(monkeypatch):
    async def run(mod, url, fake):
        c = mod.LiteClient(None, url, "tok1")
        st = await c.status()
        assert st["mode"] == "auto"
        st = await c.send(set=lite.settings_payload(lite.LiteSettings()), mode="away")
        assert st["mode"] == "away" and fake.cfg["sp_day"] == 21.0
        bad = mod.LiteClient(None, url, "nope")
        try:
            await bad.send(mode="off")
            raise AssertionError("a wrong token must fail")
        except mod.LiteError as err:
            assert "403" in str(err)
        return fake.log

    assert _with_device(run, monkeypatch) == ["GET", "POST mode,set", "POST 403"]


def test_the_config_check(monkeypatch):
    cf = importlib.import_module("hc_thermostat.config_flow")

    async def run(mod, url, fake):
        ok = await cf._lite_check(None, {"lite_url": url, "lite_token": "tok1"})
        wrong = await cf._lite_check(None, {"lite_url": url, "lite_token": "x"})
        bad_url = await cf._lite_check(None, {"lite_url": "192.168.1.5", "lite_token": "tok1"})
        gone = await cf._lite_check(None, {"lite_url": "http://127.0.0.1:9/script/1/lite", "lite_token": "tok1"})
        return ok, wrong, bad_url, gone

    ok, wrong, bad_url, gone = _with_device(run, monkeypatch)
    assert ok == {} and wrong == {"lite_token": "lite_token"} and bad_url == {"lite_url": "lite_url"}
    assert gone == {"base": "lite_unreachable"}


def test_the_dial_card_shows_lite():
    card_file = ROOT / "frontend" / "hc-dial-card.js"  # the card lives in its own repository; not in every tree
    if card_file.exists():
        card = card_file.read_text("utf-8")
        assert 'a.control_type === "lite"' in card and "LITE·TPI" in card and "LITE·HIST" in card
    src = (BASE / "lite.py").read_text("utf-8")
    assert '"control_type": "lite"' in src and '"hc_mode": "shadow" if v.shadow else "active"' in src

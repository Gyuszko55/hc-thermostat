"""0.76.0: the HC side of the local guard – the lease (core/guard.py), its sender (guard_client.py), the executor
switching the relay through the guard, the settings, the sensor, the Repairs text and the panel row."""

import asyncio
import importlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "hc_thermostat"

from core.guard import GuardLink, GuardSettings, UNREACHABLE_AFTER_S  # noqa: E402
from core.model import HcConfig  # noqa: E402

T0 = datetime(2026, 11, 18, 14, 0, tzinfo=timezone.utc)


def at(s):
    return T0 + timedelta(seconds=s)


# --- the lease ------------------------------------------------------------------------------------------------------------
def test_when_to_send():
    link = GuardLink(GuardSettings(every_s=60))
    assert link.due(at(0), True)
    link.sent(at(0), True, {"mode": "handback"})
    assert not link.due(at(30), True)
    assert link.due(at(30), False)  # a changed command at once
    assert link.due(at(60), True)  # the renewal
    link.failed(at(61), "TimeoutError")
    assert link.due(at(70), True)  # after a failure every step


def test_payload_carries_the_fallback_values_and_the_token():
    link = GuardLink(GuardSettings(sp=19.5, hyst=0.4, min_on_s=420, min_off_s=360, no_sensor="duty", push="http://n/t"),
                     token="abc")
    p = link.payload(True)
    assert p["cmd"] == "on" and p["ttl"] == 300 and p["seq"] == 1 and p["tok"] == "abc"
    assert p["fb"] == {"sp": 19.5, "hyst": 0.4, "min_on": 420, "min_off": 360, "max_on": 0, "ns": "duty",
                       "don": 1200, "doff": 2400, "push": "http://n/t"}
    assert link.payload(False)["seq"] == 2 and "tok" not in GuardLink(GuardSettings()).payload(False)


def test_problems_unreachable_and_taken_over():
    link = GuardLink(GuardSettings())
    link.failed(at(0), "ClientConnectorError")
    assert link.problem(at(UNREACHABLE_AFTER_S - 1)) is None
    assert link.problem(at(UNREACHABLE_AFTER_S)) == "unreachable"
    assert link.info(at(UNREACHABLE_AFTER_S))["mode"] == "unreachable"
    link.sent(at(700), True, {"mode": "fallback", "temp": 19.9, "sp": 20.5, "lease_left": 300})
    assert link.problem(at(700)) == "taken_over" and link.info(at(700))["temp"] == 19.9
    link.sent(at(760), True, {"mode": "handback"})
    assert link.problem(at(760)) is None  # handing back: no entry
    link.sent(at(900), True, {"mode": "normal"})
    assert link.problem(at(900)) is None and link.info(at(900))["mode"] == "normal"


def test_settings_from_the_instance():
    gc = importlib.import_module("hc_thermostat.guard_client")
    cfg = HcConfig(guard_sp=19.0, min_on_s=420, guard_no_sensor="duty")
    s = gc.settings_from(cfg, {"guard_push_url": "http://ntfy/x"})
    assert s.sp == 19.0 and s.min_on_s == 420 and s.no_sensor == "duty" and s.push == "http://ntfy/x"
    assert HcConfig().guard_every_s == 60 and HcConfig().guard_ttl_s == 300


# --- the sender ---------------------------------------------------------------------------------------------------------
class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def json(self, content_type=None):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Session:
    def __init__(self, status=200, body=None, boom=None):
        self.status, self.body, self.boom, self.posts = status, body or {"mode": "handback"}, boom, []

    def post(self, url, json=None):
        self.posts.append((url, json))
        if self.boom:
            raise self.boom
        return _Resp(self.status, self.body)


def _sender(monkeypatch, session):
    gc = importlib.import_module("hc_thermostat.guard_client")
    import homeassistant.helpers.aiohttp_client as ac
    monkeypatch.setattr(ac, "async_get_clientsession", lambda hass: session)
    return gc, gc.GuardSender(SimpleNamespace(), "http://10.0.0.5/script/1/hc", GuardLink(GuardSettings()))


def test_sender_posts_and_keeps_the_answer(monkeypatch):
    session = _Session()
    gc, snd = _sender(monkeypatch, session)
    asyncio.run(snd.send(at(0), True))
    assert session.posts[0][0] == "http://10.0.0.5/script/1/hc" and session.posts[0][1]["cmd"] == "on"
    assert snd.link.mode() == "handback"
    asyncio.run(snd.send(at(20), True))
    assert len(session.posts) == 1  # not due


def test_sender_failures_raise_and_are_remembered(monkeypatch):
    gc, snd = _sender(monkeypatch, _Session(status=403, body={"error": "bad token"}))
    with pytest.raises(gc.GuardError):
        asyncio.run(snd.send(at(0), True))
    assert snd.link.error == "HTTP 403" and snd.link.fail_since == at(0)
    gc, snd = _sender(monkeypatch, _Session(boom=OSError("no route")))
    asyncio.run(snd.send(at(0), False))  # 0.78.4: no answer once – the lease still holds, tried again next step
    assert snd.link.error == "OSError"
    with pytest.raises(gc.GuardError):
        asyncio.run(snd.send(at(150), False))  # half the lease without an answer: a relay fault


# --- the executor -------------------------------------------------------------------------------------------------------
def test_executor_switches_through_the_guard():
    ex_mod = importlib.import_module("hc_thermostat.executor")
    calls, sent = [], []

    async def svc(domain, service, data, blocking=False):
        calls.append((domain, service, data))

    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: SimpleNamespace(state="off")),
                           services=SimpleNamespace(async_call=svc))
    ex = ex_mod.Executor(hass, "active", "switch.boiler", None)

    class G:
        async def send(self, now, on, safety=False):
            sent.append(on)

    ex.guard = G()
    asyncio.run(ex.apply(SimpleNamespace(now=T0, output=True, external=None)))
    assert sent == [True] and calls == []  # the relay service is not called
    ex.guard = None
    asyncio.run(ex.apply(SimpleNamespace(now=T0, output=True, external=None)))
    assert calls and calls[0][1] == "turn_on"


# --- HC's lease taken by the real guard script --------------------------------------------------------------------------
def test_the_guard_script_takes_hcs_lease():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    link = GuardLink(GuardSettings(sp=19.0), token="k1")  # 0.78.2: the token is required
    body = json.dumps(link.payload(True))
    js = r"""
const code = require("fs").readFileSync(process.argv[1], "utf8");
let relay = false, ep = null, kvs = {};
const Shelly = { addStatusHandler() {}, getComponentStatus(t) { if (t === "sys") return { uptime: 100, unixtime: 1e9 }; if (t === "switch") return { output: relay };
  if (t === "bthomesensor") return { value: 21.0, last_updated_ts: 1e9 }; return null; },
  call(m, p, cb) { if (m === "Switch.Set") relay = p.on; if (m === "KVS.Set") kvs[p.key] = p.value; if (m === "KVS.GetMany") { cb && cb({ items: [{ key: "hc_guard_token", value: "k1" }] }); return; } cb && cb({}); } };
new Function("Shelly", "Timer", "HTTPServer", "print", code)(Shelly, { set() {} }, { registerEndpoint(n, cb) { ep = cb; } }, () => {});
let out; ep({ method: "POST", body: process.argv[2] }, { send() { out = { code: this.code, body: JSON.parse(this.body) }; } });
console.log(JSON.stringify({ out, fb: JSON.parse(kvs.hc_guard_fb) }));
"""
    res = subprocess.run([node, "-e", js, str(ROOT / "guard" / "shelly" / "hc_guard.js"), body],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["out"]["code"] == 200 and r["out"]["body"]["mode"] == "handback" and r["out"]["body"]["sp"] == 19.0
    assert r["fb"]["sp"] == 19.0
    link.sent(T0, True, r["out"]["body"])
    assert link.mode() == "handback" and link.problem(T0) is None


# --- settings, sensor, texts --------------------------------------------------------------------------------------------
def test_settings_texts_and_redaction():
    from hc_thermostat import config_flow as cf
    keys = {str(k) for k in cf._guard_fields(HcConfig(), {})}
    assert keys == set(cf.SETTINGS_SECTIONS["guard"])
    assert cf._guard_errors({}) == {}
    assert cf._guard_errors({"guard_url": "10.0.0.5/script/1/hc"}) == {"guard_url": "guard_url"}
    assert cf._guard_errors({"guard_url": "http://10.0.0.5/script/1/hc", "guard_token": "k",
                             "guard_ttl_s": 90, "guard_every_s": 60}) == {"guard_ttl_s": "guard_ttl"}
    # 0.78.2 (security review H3): no guard without its token
    assert cf._guard_errors({"guard_url": "http://10.0.0.5/script/1/hc"}) == {"guard_token": "guard_token_required"}
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        sec = tr["options"]["step"]["settings"]["sections"]["guard"]
        assert all(sec["data"][k] and sec["data_description"][k] for k in keys)
        assert tr["options"]["error"]["guard_url"] and tr["options"]["error"]["guard_ttl"]
        assert tr["options"]["error"]["guard_token_required"]
        assert set(tr["selector"]["guard_no_sensor"]["options"]) == {"off", "duty"}
        assert set(tr["entity"]["sensor"]["guard"]["state"]) == {"normal", "grace", "fallback", "nosensor", "handback", "safety", "unreachable"}
        assert "{problem}" in tr["issues"]["guard_problem"]["description"]
    diag = (BASE / "diagnostics.py").read_text()
    assert '"guard_token"' in diag and '"guard_push_url"' in diag
    src = (BASE / "sensor.py").read_text()
    assert "class HcGuard(" in src and 'getattr(c, "guard", None) is not None' in src
    js = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "guardText" in js
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9")


def test_upload_tool_chunks_and_refuses_gen1(monkeypatch, capsys):
    import importlib.util
    spec = importlib.util.spec_from_file_location("upload_shelly", ROOT / "guard" / "upload_shelly.py")
    up = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(up)
    calls = []

    def fake(host, method, params=None):
        calls.append((method, params))
        return {"Shelly.GetDeviceInfo": {"gen": 3, "model": "S3SW-001X16EU", "ver": "1.5.0"},
                "Script.List": {"scripts": []}, "Script.Create": {"id": 2}}.get(method, {})

    monkeypatch.setattr(up, "rpc", fake)
    monkeypatch.setattr(sys, "argv", ["x", "10.0.0.50", "--token", "t"])
    assert up.main() == 0
    puts = [p for m, p in calls if m == "Script.PutCode"]
    assert "".join(p["code"] for p in puts) == (ROOT / "guard" / "shelly" / "hc_guard.js").read_text()
    assert puts[0]["append"] is False and all(p["append"] for p in puts[1:])
    assert ("KVS.Set", {"key": "hc_guard_token", "value": "t"}) in calls
    assert "http://10.0.0.50/script/2/hc" in capsys.readouterr().out
    monkeypatch.setattr(up, "rpc", lambda h, m, p=None: {"gen": 1, "model": "SHSW-1"})
    assert up.main() == 1

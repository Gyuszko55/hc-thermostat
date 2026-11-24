"""0.78.2 (security review H3 + M1): the local guard takes nothing without its token, HC can protect the device with
its own password (Shelly digest auth), and HC's life-safety stop is the guard's own "safety" command – off at once,
latched on the device until an ordinary lease."""

import asyncio
import importlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT / "custom_components"))
sys.path.insert(0, str(ROOT / "tests"))

from test_guard_shelly_760 import run, snaps  # noqa: E402

guard = importlib.import_module("hc_thermostat.core.guard")
client = importlib.import_module("hc_thermostat.guard_client")
model = importlib.import_module("hc_thermostat.core.model")
executor_mod = importlib.import_module("hc_thermostat.executor")

T0 = datetime(2026, 11, 20, 20, 0, tzinfo=timezone.utc)


def to_normal():
    return [{"lease": "off"}, {"adv": 60, "lease": "off"}, {"adv": 70, "lease": "off"}, {"adv": 10}]


# --- H3: no token, no lease -----------------------------------------------------------------------------------------
def test_without_a_token_the_guard_takes_no_lease_and_no_push():
    out = run([{"lease": "on", "tok": ""}, {"lease": "on", "tok": "anything"}, {"q": "t=18.0"}, {"snap": "s"}],
              {"no_token": True})
    assert [o["code"] for o in out[:3]] == [403, 403, 403]
    assert out[0]["body"]["error"] == "no token set"
    assert out[3]["mode"] == "fallback"  # only its own program
    assert run([{"get": True}], {"no_token": True})[0]["body"]["token"] is False


def test_with_a_token_a_wrong_one_is_refused():
    out = run([{"lease": "on", "tok": "wrong"}, {"lease": "on"}])
    assert out[0]["code"] == 403 and out[1]["code"] == 200 and out[1]["body"]["token"] is True


# --- M1: the safety command -----------------------------------------------------------------------------------------
def test_safety_switches_off_at_once_and_latches():
    s = snaps(run(to_normal() + [{"lease": "on"}, {"adv": 30, "snap": "on"},
                                 {"lease": "safety"}, {"snap": "stop"},
                                 {"adv": 1200, "temp": 15.0, "snap": "no_lease"}]))
    assert s["on"]["relay"] and s["on"]["mode"] == "normal"
    # 30 s into a burn (min_on 300 s): off at once all the same
    assert s["stop"]["relay"] is False and s["stop"]["mode"] == "safety" and s["stop"]["kvs"]["hc_guard_stop"] == "1"
    # the lease ran out, the room is cold: still no fallback heating while latched
    assert s["no_lease"]["relay"] is False and s["no_lease"]["mode"] == "safety"
    assert s["stop"]["posts"] >= 1  # the stop is announced


def test_the_latch_holds_over_a_restart_and_clears_with_an_ordinary_lease():
    preset = {"kvs": {"hc_guard_stop": "1", "hc_guard_token": "t0k"}}
    s = snaps(run([{"temp": 15.0, "adv": 30, "snap": "boot"}, {"lease": "off"}, {"snap": "cleared"},
                   {"adv": 60, "lease": "on"}, {"adv": 70, "lease": "on"}, {"adv": 10, "snap": "back"}], preset))
    assert s["boot"]["mode"] == "safety" and s["boot"]["relay"] is False
    assert s["cleared"]["mode"] == "handback" and s["cleared"]["kvs"]["hc_guard_stop"] == "0"
    assert s["back"]["mode"] == "normal" and s["back"]["relay"] is True


def test_hc_sends_safety_and_back():
    link = guard.GuardLink(guard.GuardSettings(), token="k")
    assert link.payload(False, safety=True)["cmd"] == "safety"
    link.sent(T0, False, {"mode": "safety"}, safety=True)
    assert link.due(T0 + timedelta(seconds=5), False, safety=True) is False  # same command, not yet due
    assert link.due(T0 + timedelta(seconds=5), False) is True  # the stop acknowledged: "off" at once


def test_executor_gives_the_guard_the_stop():
    sent = []

    class G:
        async def send(self, now, on, safety=False):
            sent.append((on, safety))

    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: SimpleNamespace(state="on")), data={})
    ex = executor_mod.Executor(hass, "active", "switch.boiler", None)
    ex.guard = G()
    stop = model.Decision(T0, model.Reason.SAFETY_STOP, 7.0, None, None, demand=0.0, output=False)
    asyncio.run(ex.apply(stop))
    asyncio.run(ex.apply(model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.5, output=True)))
    assert sent == [(False, True), (True, False)]


# --- H3: the device password ----------------------------------------------------------------------------------------
class _Resp:
    status = 200

    async def json(self, content_type=None):
        return {"mode": "normal"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Got(_Resp):
    async def read(self):
        return b"{}"


def _send(password, monkeypatch):
    seen = []

    class Session:
        def post(self, url, json=None, **kw):
            seen.append(kw)
            return _Resp()

        def get(self, url, **kw):  # 0.78.3: the challenge comes from a bodiless GET first
            return _Got()

    ac = importlib.import_module("homeassistant.helpers.aiohttp_client")
    monkeypatch.setattr(ac, "async_get_clientsession", lambda hass: Session())
    snd = client.GuardSender(None, "http://10.0.0.5/script/1/hc", guard.GuardLink(guard.GuardSettings(), "k"),
                             password=password)
    asyncio.run(snd.send(T0, True))
    return seen


def test_digest_auth_only_with_a_password(monkeypatch):
    import aiohttp
    kw = _send("s3cret-pass", monkeypatch)[0]
    (mw,) = kw["middlewares"]
    assert isinstance(mw, aiohttp.DigestAuthMiddleware)
    assert _send("", monkeypatch)[0] == {}


def test_secrets_stay_out_of_diagnostics_and_the_panel():
    diag = (BASE / "diagnostics.py").read_text()
    assert '"guard_password"' in diag and '"guard_url"' in diag
    info = (BASE / "info.py").read_text()
    assert '_SECRET_KEYS = ("guard_token", "guard_password")' in info and 'k in _SECRET_KEYS and v' in info
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        sec = tr["options"]["step"]["settings"]["sections"]["guard"]
        assert sec["data"]["guard_password"] and sec["data_description"]["guard_password"]


def test_upload_tool_makes_a_token_and_warns_without_a_password(monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("upload_shelly", ROOT / "guard" / "upload_shelly.py")
    up = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(up)
    calls = []

    def fake(host, method, params=None):
        calls.append((method, params))
        return {"Shelly.GetDeviceInfo": {"gen": 3, "id": "shelly1minig4-abc", "model": "S4SW", "ver": "1.6",
                                         "auth_en": False},
                "Script.List": {"scripts": []}, "Script.Create": {"id": 1}}.get(method, {})

    monkeypatch.setattr(up, "rpc", fake)
    monkeypatch.delenv("HC_GUARD_TOKEN", raising=False)
    monkeypatch.delenv("HC_GUARD_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "argv", ["upload_shelly.py", "10.0.0.5"])
    assert up.main() == 0
    tok = next(p["value"] for m, p in calls if m == "KVS.Set" and p["key"] == "hc_guard_token")
    out = capsys.readouterr().out
    assert len(tok) >= 20 and tok in out and "WARNING: the device has no password" in out
    # --set-password: SetAuth with ha1 = sha256(admin:<id>:<password>)
    calls.clear()
    monkeypatch.setenv("HC_GUARD_PASSWORD", "long-enough-pw")
    monkeypatch.setenv("HC_GUARD_TOKEN", "given-token")
    monkeypatch.setattr(up, "use_password", lambda host, pw: calls.append(("use_password", pw)))
    monkeypatch.setattr(sys, "argv", ["upload_shelly.py", "10.0.0.5", "--set-password"])
    assert up.main() == 0
    import hashlib
    auth = next(p for m, p in calls if m == "Shelly.SetAuth")
    assert auth["ha1"] == hashlib.sha256(b"admin:shelly1minig4-abc:long-enough-pw").hexdigest()
    assert ("use_password", "long-enough-pw") in calls
    assert ("KVS.Set", {"key": "hc_guard_token", "value": "given-token"}) in calls
    assert "given-token" not in capsys.readouterr().out  # a given token is never printed


# --- M2: max_on in every mode, stale readings -----------------------------------------------------------------------
LONG = {"kvs": {"hc_guard_fb": json.dumps({"sp": 25.0, "hyst": 0.6, "min_on": 300, "min_off": 300, "max_on": 1800,
                                           "ns": "off", "don": 1200, "doff": 2400, "push": ""}), "hc_guard_token": "t0k"}}


def test_max_on_cuts_a_long_run_in_fallback_too():
    # 19.8 °C, target 25: the fallback thermostat would heat for ever
    s = snaps(run([{"adv": 10, "snap": "on"}, {"adv": 1790, "snap": "cut"}, {"adv": 200, "snap": "pause"},
                   {"adv": 200, "snap": "again"}], LONG))
    assert s["on"]["mode"] == "fallback" and s["on"]["relay"]
    assert s["cut"]["relay"] is False and s["pause"]["relay"] is False  # 30 min, then min_off
    assert s["again"]["relay"] is True  # a bounded duty, not endless heating


def test_max_on_cuts_the_last_command_in_grace():
    fb = {"max_on": 360}
    # the relay comes on at ~900 s (after min_off); the lease (300 s) runs out at 1090, grace lasts until 1390
    steps = to_normal() + [{"adv": 60, "lease": "off", "fb": fb}] * 6 + [{"lease": "on", "fb": fb},
                                                                        {"adv": 200, "snap": "on"},
                                                                        {"adv": 230, "snap": "grace"},
                                                                        {"adv": 50, "snap": "cut"}]
    s = snaps(run(steps))
    assert s["on"]["relay"] and s["on"]["mode"] == "normal"
    assert s["grace"]["mode"] == "grace" and s["grace"]["relay"]  # the last command stays ...
    assert s["cut"]["mode"] == "grace" and s["cut"]["relay"] is False  # ... but not beyond max_on


def test_a_reading_of_unknown_age_is_no_reading():
    s = snaps(run([{"nosync": True, "adv": 330, "snap": "nosync"}]))  # past the min_on of the boot burn
    assert s["nosync"]["mode"] == "nosensor" and s["nosync"]["relay"] is False


def test_electric_heaters_get_a_max_on_by_default():
    matrix = importlib.import_module("hc_thermostat.core.matrix")
    assert matrix.source_defaults("radiator_single", "electric_heater")["guard_max_on_s"] == 7200.0
    assert "guard_max_on_s" not in matrix.source_defaults("radiator_single", "gas_boiler")

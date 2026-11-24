"""0.78.4: upload_shelly.py reaches a password-protected Shelly – SHA-256 digest through aiohttp (the standard
library's urllib knows none), the challenge once, every later call signed in advance, a 429 waited out."""

import asyncio
import hashlib
import importlib.util
import json
import sys
import threading
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
REALM, PW = "shelly1minig4-test", "long-enough-pw"


def _h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


class FakeRpc:
    def __init__(self, protected: bool, busy_first: int = 0) -> None:
        self.protected = protected
        self.busy = busy_first
        self.nonce = 0
        self.calls: list[str] = []
        self.challenges = 0
        self.kvs: dict = {}
        self.code = ""

    def _ok(self, request) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Digest "):
            return False
        f = {k.strip(): v.strip().strip('"') for k, v in (p.split("=", 1) for p in auth[7:].split(","))}
        want = _h(":".join([_h(f"admin:{REALM}:{PW}"), f["nonce"], f["nc"], f["cnonce"], f["qop"],
                            _h(f"{request.method}:{f['uri']}")]))
        return f.get("nonce") == f"n{self.nonce}" and f.get("response") == want

    async def handle(self, request):
        method = request.match_info["m"]
        body = json.loads(await request.read() or b"{}")
        if self.busy:
            self.busy -= 1
            return web.Response(status=429)
        if self.protected and method != "Shelly.GetDeviceInfo" and not self._ok(request):
            self.nonce += 1
            self.challenges += 1
            return web.Response(status=401, headers={"WWW-Authenticate":
                                f'Digest qop="auth", realm="{REALM}", nonce="n{self.nonce}", algorithm=SHA-256'})
        self.calls.append(method)
        if method == "Shelly.GetDeviceInfo":
            return web.json_response({"gen": 4, "id": REALM, "model": "S4SW", "ver": "2.2.0", "auth_en": self.protected})
        if method == "Shelly.SetAuth":
            self.protected = True
            return web.json_response(None)
        if method == "Script.List":
            return web.json_response({"scripts": []})
        if method == "Script.Create":
            return web.json_response({"id": 1})
        if method == "Script.PutCode":
            self.code = (self.code if body.get("append") else "") + body["code"]
        if method == "KVS.Set":
            self.kvs[body["key"]] = body["value"]
        return web.json_response({})


def _serve(fake):
    started = threading.Event()
    box = {}

    def run():
        loop = asyncio.new_event_loop()
        app = web.Application()
        app.router.add_post("/rpc/{m}", fake.handle)
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, "127.0.0.1", 0)
        loop.run_until_complete(site.start())
        box["port"] = site._server.sockets[0].getsockname()[1]
        box["loop"], box["runner"] = loop, runner
        started.set()
        loop.run_forever()
        loop.run_until_complete(runner.cleanup())

    t = threading.Thread(target=run, daemon=True)
    t.start()
    started.wait(5)
    return box, t


def _tool():
    spec = importlib.util.spec_from_file_location("upload_shelly_0784", ROOT / "guard" / "upload_shelly.py")
    up = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(up)
    return up


def _run(fake, monkeypatch, *args, env=None):
    box, t = _serve(fake)
    up = _tool()
    monkeypatch.setattr(up, "BUSY_TRIES", 4)
    monkeypatch.setattr(up.asyncio, "sleep", _nosleep)
    for k in ("HC_GUARD_TOKEN", "HC_GUARD_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(sys, "argv", ["upload_shelly.py", f"127.0.0.1:{box['port']}", *args])
    try:
        return up.main()
    finally:
        up._CLIENT.close()
        box["loop"].call_soon_threadsafe(box["loop"].stop)
        t.join(5)


async def _nosleep(s):
    return None


def test_uploads_to_a_protected_device_with_one_challenge(monkeypatch):
    fake = FakeRpc(protected=True)
    assert _run(fake, monkeypatch, "--sensor", "none", env={"HC_GUARD_PASSWORD": PW, "HC_GUARD_TOKEN": "tok"}) == 0
    assert fake.code == (ROOT / "guard" / "shelly" / "hc_guard.js").read_text("ascii")
    assert fake.kvs["hc_guard_token"] == "tok" and fake.kvs["hc_guard_sensor"] == "none"
    assert fake.calls[-1] == "Script.Start"
    assert fake.challenges == 1  # every call after the first one signed in advance


def test_sets_the_password_then_signs(monkeypatch):
    fake = FakeRpc(protected=False)
    assert _run(fake, monkeypatch, "--set-password", env={"HC_GUARD_PASSWORD": PW, "HC_GUARD_TOKEN": "tok"}) == 0
    assert "Shelly.SetAuth" in fake.calls and fake.protected and fake.calls[-1] == "Script.Start"


def test_a_busy_device_is_waited_out(monkeypatch):
    fake = FakeRpc(protected=True, busy_first=2)
    assert _run(fake, monkeypatch, env={"HC_GUARD_PASSWORD": PW, "HC_GUARD_TOKEN": "tok"}) == 0


def test_a_wrong_password_says_so(monkeypatch):
    fake = FakeRpc(protected=True)
    try:
        _run(fake, monkeypatch, env={"HC_GUARD_PASSWORD": "wrong-password", "HC_GUARD_TOKEN": "tok"})
    except SystemExit as err:
        assert "refused the password" in str(err)
    else:
        raise AssertionError("no error for a wrong password")

"""0.78.3: a password-protected Shelly closes the connection on a script endpoint request that carries a body and no
Authorization – no 401, no challenge. HC first GETs the guard's status (that 401 brings the challenge), then sends the
lease signed in advance; a broken connection gets one fresh challenge and one retry."""

import asyncio
import hashlib
import importlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from aiohttp import web

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

guard = importlib.import_module("hc_thermostat.core.guard")
client = importlib.import_module("hc_thermostat.guard_client")

T0 = datetime(2026, 11, 21, 5, 0, tzinfo=timezone.utc)
REALM, PW = "shelly1minig4-test", "long-enough-pw"


def _h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


class FakeShelly:
    """Digest SHA-256 as a Gen4 does it; a body without Authorization: the connection is closed."""

    def __init__(self, nonces_last: int = 100) -> None:
        self.nonce_n = 0
        self.nonces_last = nonces_last  # how many requests a nonce is good for
        self.uses = 0
        self.log: list[str] = []

    def _challenge(self) -> web.Response:
        self.nonce_n += 1
        self.uses = 0
        return web.Response(status=401, headers={"WWW-Authenticate":
                            f'Digest qop="auth", realm="{REALM}", nonce="n{self.nonce_n}", algorithm=SHA-256'})

    def _ok(self, request) -> bool:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Digest "):
            return False
        f = dict(part.strip().split("=", 1) for part in auth[7:].split(","))
        f = {k: v.strip('"') for k, v in f.items()}
        if f.get("nonce") != f"n{self.nonce_n}" or self.uses >= self.nonces_last:
            return False
        want = _h(":".join([_h(f"admin:{REALM}:{PW}"), f["nonce"], f["nc"], f["cnonce"], f["qop"],
                            _h(f"{request.method}:{f['uri']}")]))
        self.uses += 1
        return f.get("response") == want

    async def handle(self, request: web.Request) -> web.StreamResponse:
        body = await request.read()
        if self._ok(request):
            self.log.append(f"{request.method} ok")
            return web.json_response({"mode": "normal", "relay": request.method == "POST"})
        if body and "Authorization" not in request.headers:
            self.log.append(f"{request.method} reset")
            request.transport.abort()  # what the Shelly does: no answer at all
            return web.Response()
        self.log.append(f"{request.method} 401")
        return self._challenge()


async def _serve(fake):
    app = web.Application()
    app.router.add_route("*", "/script/1/hc", fake.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}/script/1/hc"


def _sends(fake, password, n, monkeypatch):
    import aiohttp
    ac = importlib.import_module("homeassistant.helpers.aiohttp_client")

    async def main():
        runner, url = await _serve(fake)
        session = aiohttp.ClientSession()
        monkeypatch.setattr(ac, "async_get_clientsession", lambda hass: session)
        link = guard.GuardLink(guard.GuardSettings(), "k")
        snd = client.GuardSender(None, url, link, password=password)
        out = []
        try:
            for i in range(n):
                link._last_sent = None  # every step due
                try:
                    await snd.send(T0, bool(i % 2 == 0))
                    out.append("ok")
                except client.GuardError as err:
                    out.append(str(err))
        finally:
            await session.close()
            await runner.cleanup()
        return out

    return asyncio.run(main())


def _force_due(monkeypatch):
    monkeypatch.setattr(guard.GuardLink, "due", lambda self, now, on, safety=False: True)


def test_the_lease_goes_signed_after_a_bodiless_challenge(monkeypatch):
    _force_due(monkeypatch)
    fake = FakeShelly()
    assert _sends(fake, PW, 3, monkeypatch) == ["ok", "ok", "ok"]
    # one challenge (GET 401 → GET ok), then every POST signed in advance – never a reset
    assert fake.log == ["GET 401", "GET ok", "POST ok", "POST ok", "POST ok"]


def test_a_stale_nonce_gets_a_fresh_challenge_and_one_retry(monkeypatch):
    _force_due(monkeypatch)
    fake = FakeShelly(nonces_last=2)  # the GET and the first POST, then the nonce is spent
    assert _sends(fake, PW, 3, monkeypatch) == ["ok", "ok", "ok"]
    assert "POST reset" not in fake.log and fake.nonce_n >= 2


def test_a_wrong_password_says_so(monkeypatch):
    _force_due(monkeypatch)
    out = _sends(FakeShelly(), "wrong-password", 1, monkeypatch)
    assert out == ["HTTP 401 (device password)"]


def test_without_a_password_no_get_first(monkeypatch):
    _force_due(monkeypatch)

    class Open(FakeShelly):
        def _ok(self, request):
            return True

    fake = Open()
    assert _sends(fake, "", 2, monkeypatch) == ["ok", "ok"]
    assert fake.log == ["POST ok", "POST ok"]


# --- 0.78.4: a missed renewal while the lease holds is no relay fault ----------------------------------------------
class _Busy:
    status = 429

    async def read(self):
        return b""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _busy_sender(monkeypatch, password="long-enough-pw"):
    from datetime import timedelta  # noqa: F401
    ac = importlib.import_module("homeassistant.helpers.aiohttp_client")

    class Session:
        def get(self, url, **kw):
            return _Busy()

        def post(self, url, **kw):
            return _Busy()

    monkeypatch.setattr(ac, "async_get_clientsession", lambda hass: Session())
    return client.GuardSender(None, "http://10.0.0.5/script/1/hc", guard.GuardLink(guard.GuardSettings(), "k"),
                              password=password)


def test_a_refused_renewal_right_after_start_is_tolerated_then_a_fault(monkeypatch):
    from datetime import timedelta
    snd = _busy_sender(monkeypatch)
    asyncio.run(snd.send(T0, False))  # the 429 after a reload: no exception, so no relay fault
    assert snd.link.error == "HTTP 429" and snd.link.fail_since == T0
    asyncio.run(snd.send(T0 + timedelta(seconds=120), False))  # still within half the lease
    with pytest.raises(client.GuardError):
        asyncio.run(snd.send(T0 + timedelta(seconds=150), False))  # the lease is at risk now


def test_tolerance_counts_from_the_last_renewal(monkeypatch):
    from datetime import timedelta
    snd = _busy_sender(monkeypatch)
    snd.link.sent(T0, False, {"mode": "normal"})
    asyncio.run(snd.send(T0 + timedelta(seconds=60), False))  # the next renewal fails: tolerated
    with pytest.raises(client.GuardError):
        asyncio.run(snd.send(T0 + timedelta(seconds=150), False))  # 150 s since the lease was last taken


def test_the_safety_stop_is_never_tolerated(monkeypatch):
    snd = _busy_sender(monkeypatch)
    with pytest.raises(client.GuardError):
        asyncio.run(snd.send(T0, False, safety=True))

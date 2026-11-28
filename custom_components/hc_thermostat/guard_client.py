"""0.76.0: sends HC's relay command as a lease to the local guard (core/guard.py; guard/shelly/hc_guard.js).

0.78.2 (security review H3): with the device's password given, every lease goes with the Shelly's digest auth
(user "admin", SHA-256) – a device protected by Shelly.SetAuth covers the script's endpoint and its whole RPC with it.

0.78.3: a Shelly closes the connection on a script endpoint request that carries a body and no Authorization – no
401, so no digest challenge, and every lease failed with ClientOSError. A bodiless GET (the guard's status) does get
the challenge; the lease then goes signed in advance (preemptive). A broken connection gets one fresh challenge and
one retry within the same send."""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging

from .core.guard import GuardLink, GuardSettings

_LOGGER = logging.getLogger(__name__)
TIMEOUT_S = 5.0
PROBE_EVERY_S = 300  # 0.83.0: the go-live checklist asks the guard at most this often
SHELLY_USER = "admin"  # Gen2+ devices: the only user


def _disconnected() -> type:
    from aiohttp import ServerDisconnectedError
    return ServerDisconnectedError


_REFUSED = ("HTTP 401", "HTTP 403")  # 0.78.4: a wrong password / token is a setting to fix – a fault at once


class GuardError(Exception):
    """The guard did not take the lease (no answer, an error code, a refused token)."""


def settings_from(cfg, conf: dict) -> GuardSettings:
    """The fallback values from the instance's settings; the minimum times are HC's own."""
    return GuardSettings(every_s=cfg.guard_every_s, ttl_s=cfg.guard_ttl_s, sp=cfg.guard_sp, hyst=cfg.guard_hyst,
                         min_on_s=cfg.min_on_s, min_off_s=cfg.min_off_s, max_on_s=cfg.guard_max_on_s,
                         no_sensor=cfg.guard_no_sensor, duty_on_s=cfg.guard_duty_on_s,
                         duty_off_s=cfg.guard_duty_off_s, push=str(conf.get("guard_push_url") or ""))


class GuardSender:
    def __init__(self, hass, url: str, link: GuardLink, password: str = "") -> None:
        self._hass = hass
        self.url = url
        self.link = link
        self._password = password or ""
        self._auth = None  # the digest middleware, made at the first send (it keeps the device's nonce)
        self._primed = False  # 0.78.3: the middleware holds a challenge from a bodiless request
        self._warned = False  # 0.78.4: a missed renewal logged once per streak
        self._probe: tuple[datetime, str] | None = None  # 0.83.0: the checklist's last status request

    def _middlewares(self) -> tuple:
        if not self._password:
            return ()
        if self._auth is None:
            from aiohttp import DigestAuthMiddleware
            self._auth = DigestAuthMiddleware(SHELLY_USER, self._password)
        return (self._auth,)

    async def _prime(self, session, extra: dict) -> None:
        """0.78.3: GET the guard's status – the 401 on a bodiless request carries the challenge the middleware keeps."""
        async with session.get(self.url, **extra) as resp:
            await resp.read()
            if resp.status == 401:
                raise GuardError("HTTP 401 (device password)")
            if resp.status != 200:
                raise GuardError(f"HTTP {resp.status}")
        self._primed = True

    async def send(self, now: datetime, on: bool, safety: bool = False) -> None:
        if not self.link.due(now, on, safety):
            return
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        body = self.link.payload(on, safety)
        try:
            session = async_get_clientsession(self._hass)
            mw = self._middlewares()
            extra = {"middlewares": mw} if mw else {}
            for attempt in (0, 1):
                try:
                    async with asyncio.timeout(TIMEOUT_S):
                        if mw and not self._primed:
                            await self._prime(session, extra)
                        async with session.post(self.url, json=body, **extra) as resp:
                            if resp.status != 200:
                                raise GuardError(f"HTTP {resp.status}")
                            status = await resp.json(content_type=None)
                    break
                except (OSError, _disconnected()) as err:
                    self._primed = False  # a stale nonce or a closed connection: a fresh challenge next time
                    if not mw or attempt:
                        raise
                    _LOGGER.debug("Guard lease: %s – one retry with a fresh challenge", type(err).__name__)
        except GuardError as err:
            self.link.failed(now, str(err))
            if not str(err).startswith(_REFUSED) and self._tolerated(now, safety):
                return
            raise
        except Exception as err:  # no answer, a broken reply: the guard keeps its last lease, then falls back
            self.link.failed(now, type(err).__name__)
            if self._tolerated(now, safety):
                return
            raise GuardError(type(err).__name__) from err
        if self._warned:
            _LOGGER.info("Guard lease renewed again (%s)", self.url)
        self._warned = False
        self.link.sent(now, on, status, safety)

    async def probe(self, now: datetime) -> str:
        """0.83.0: the go-live checklist – does the guard answer? A bodiless GET of its status (no lease, nothing
        switched), remembered for five minutes so an open panel does not hammer the device. "ok" or the error."""
        if self._probe is not None and (now - self._probe[0]).total_seconds() < PROBE_EVERY_S:
            return self._probe[1]
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        try:
            session = async_get_clientsession(self._hass)
            mw = self._middlewares()
            extra = {"middlewares": mw} if mw else {}
            async with asyncio.timeout(TIMEOUT_S):
                async with session.get(self.url, **extra) as resp:
                    await resp.read()
                    result = "ok" if resp.status == 200 else f"HTTP {resp.status}"
        except Exception as err:  # no answer: the checklist says so, nothing else changes
            result = type(err).__name__
        self._probe = (now, result)
        return result

    def _tolerated(self, now: datetime, safety: bool) -> bool:
        """0.78.4: a missed renewal (no answer, 429, 5xx) while the guard's lease still holds is no relay fault – HC tries again at the next
        step. Before, a single refused request (a Shelly's 429 right after the instance reloaded) made the fault sensor
        and its notification go on for a minute. A fault from half the lease time on (the lease is then at risk), and
        at once for the life-safety stop."""
        if safety:
            return False
        since = self.link.last_ok or self.link.fail_since or now  # the lease runs from the last renewal it took
        if (now - since).total_seconds() >= self.link.s.ttl_s / 2:
            return False
        if not self._warned:
            _LOGGER.warning("Guard lease not renewed (%s: %s) – trying again, the lease still holds",
                            self.url, self.link.error)
            self._warned = True
        return True

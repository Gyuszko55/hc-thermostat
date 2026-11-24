"""hcd service: `python -m hcd --config /share/hcd/hcd.yaml`.

Every `step_s` seconds: poll Home Assistant and the Shelly relays, take the Zigbee2MQTT messages that came in, decide,
compare with the integration (shadow), save. A web page on `web_port`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime, timezone
import logging
from pathlib import Path
import signal
from zoneinfo import ZoneInfo

import aiohttp
from aiohttp import web

import hc_core
from hc_core.inputs import SampleTable
from hc_core.messages import explain

from . import __version__
from .compare import Comparison, ha_side
from .config import load
from .engine import Engine
from .feeds import HaFeed, ShellyRpcFeed, Z2mFeed
from .web import make_app

_LOGGER = logging.getLogger("hcd")


async def supervisor_mqtt(session: aiohttp.ClientSession) -> dict:
    """The MQTT broker's address and login from the Supervisor (an add-on with `services: [mqtt:need]`)."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    async with session.get("http://supervisor/services/mqtt", headers={"Authorization": f"Bearer {token}"},
                           timeout=aiohttp.ClientTimeout(total=10)) as r:
        r.raise_for_status()
        d = (await r.json()).get("data") or {}
    return {"host": d.get("host"), "port": d.get("port") or 1883, "username": d.get("username"),
            "password": d.get("password")}


async def serve(config_path: str, web_host: str | None = None, web_allow: str | None = None) -> None:
    cfg = load(config_path)
    if web_host:  # 0.1.3: the add-on listens for its ingress, and lets in only the Supervisor's proxy
        cfg.web_host = web_host
    if web_allow:
        cfg.web_allow = [a.strip() for a in web_allow.split(",") if a.strip()]
    tz = ZoneInfo(cfg.timezone)
    data = Path(cfg.data_dir)
    data.mkdir(parents=True, exist_ok=True)
    table = SampleTable()
    started = datetime.now(timezone.utc)
    engine = Engine(cfg.hc, table, data / "state.json", started)
    if engine.load():
        _LOGGER.info("state restored from %s", data / "state.json")
    elif cfg.seed_state and Path(cfg.seed_state).exists():
        engine.restore(json.loads(Path(cfg.seed_state).read_text(encoding="utf-8")))
        _LOGGER.info("state seeded from %s", cfg.seed_state)
    missing = sorted(engine.entities() - set(cfg.sources))
    if missing:
        _LOGGER.warning("no source for: %s – these read as unavailable", ", ".join(missing))
    if engine.unsupported:
        _LOGGER.warning("settings not handled by hcd yet: %s", ", ".join(engine.unsupported))
    comparison = Comparison(data / "compare.sqlite") if cfg.compare else None

    async with aiohttp.ClientSession() as session:
        if cfg.mqtt.get("host") == "supervisor":  # inside a Home Assistant add-on: the broker the Supervisor names
            cfg.mqtt.update(await supervisor_mqtt(session))
        ha = HaFeed(cfg, table, session) if (cfg.ha_url and cfg.ha_token) else None
        shelly = ShellyRpcFeed(cfg, table, session)
        z2m = Z2mFeed(cfg, table) if "z2m" in cfg.kinds() else None
        tasks = [asyncio.create_task(z2m.run())] if z2m else []

        def status() -> dict:
            d = engine.last
            local_day = datetime.now(tz).date().isoformat()
            out = {
                "name": cfg.name, "version": __version__, "core": hc_core.__version__, "mode": "shadow",
                "started": started.isoformat(), "unsupported": engine.unsupported, "missing_sources": missing,
                "feeds": {"Home Assistant": bool(ha and ha.ok), **({"Zigbee2MQTT": z2m.connected} if z2m else {})},
                "decision": None if d is None else {
                    "reason": d.reason.value, "output": d.output, "demand": round(d.demand * 100), "target": d.target,
                    "indoor": d.indoor, "outdoor": d.outdoor, "text_hu": explain(d, "hu"), "text_en": explain(d, "en"),
                    "at": d.now.isoformat()},
            }
            if comparison:
                out["today"] = comparison.day_summary(local_day, cfg.step_s)
                out["recent"] = comparison.recent(60)
                days = [r[0] for r in comparison.db.execute("select distinct day from steps order by day desc limit 14")]
                out["days"] = [comparison.day_summary(x, cfg.step_s) for x in days]
                out["disagreements"] = comparison.disagreements(local_day, 200)
            return out

        def disagreements(day: str | None) -> list[dict]:
            if not comparison:
                return []
            return comparison.disagreements(day or datetime.now(tz).date().isoformat(), 2000)

        runner = web.AppRunner(make_app(status, disagreements, cfg.web_allow))
        await runner.setup()
        await web.TCPSite(runner, cfg.web_host, cfg.web_port).start()  # 0.1.3: 127.0.0.1 unless told otherwise
        _LOGGER.info("hcd %s (hc-core %s) – %s, shadow, page on %s:%d%s", __version__, hc_core.__version__,
                      cfg.name, cfg.web_host, cfg.web_port, f" (only {', '.join(cfg.web_allow)})" if cfg.web_allow else "")

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, stop.set)
            except NotImplementedError:
                pass
        while not stop.is_set():
            if ha:
                await ha.poll()
            await shelly.poll()
            now = datetime.now(tz)
            ha_now = ha_side(ha.states, cfg.compare) if (ha and cfg.compare) else None
            if ha_now:
                engine.mirror_target(ha_now.get("preset"), ha_now.get("manual_target"), now)
            try:
                decision = engine.step(now)
            except Exception:
                _LOGGER.exception("decision failed")
            else:
                if comparison and ha_now:
                    comparison.record(now.astimezone(timezone.utc), now.date().isoformat(), decision, ha_now)
            try:
                await asyncio.wait_for(stop.wait(), timeout=cfg.step_s)
            except asyncio.TimeoutError:
                pass
        engine.save()
        for t in tasks:
            t.cancel()
        await runner.cleanup()


def main() -> None:
    ap = argparse.ArgumentParser(prog="hcd")
    ap.add_argument("--config", required=True)
    ap.add_argument("--log-level", default="INFO")
    ap.add_argument("--web-host", default=None, help="0.1.3: the page's address (default: the settings', 127.0.0.1)")
    ap.add_argument("--web-allow", default=None, help="0.1.3: comma-separated remote addresses let in")
    args = ap.parse_args()
    logging.basicConfig(level=args.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(serve(args.config, args.web_host, args.web_allow))


if __name__ == "__main__":
    main()

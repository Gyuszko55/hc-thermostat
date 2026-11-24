"""Feeds: fill the core's sample table from Home Assistant, Zigbee2MQTT (MQTT) and Shelly devices (RPC)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Iterable

import aiohttp

from hc_core.inputs import SampleTable

from .config import Config, Source

_LOGGER = logging.getLogger(__name__)
TEMPERATURE_FIELDS = {"temperature", "local_temperature", "device_temperature"}


def parse_time(value: Any) -> datetime | None:
    """An ISO time (Zigbee2MQTT's `last_seen`, a timestamp entity) as an aware UTC datetime; None if it is none."""
    if not isinstance(value, str) or not value or value in ("unknown", "unavailable"):
        return None
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


# --- Zigbee2MQTT -----------------------------------------------------------------------------------------------------
def z2m_value(source: Source, payload: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The source's state text and attributes from a device's payload; None when the payload lacks the field."""
    if source.field not in payload:
        return None
    value = payload[source.field]
    attrs: dict[str, Any] = {}
    if source.above is not None:
        try:
            return ("on" if float(value) >= source.above else "off"), attrs
        except (TypeError, ValueError):
            return "unavailable", attrs
    if isinstance(value, bool):
        on = (not value) if source.invert else value
        return ("on" if on else "off"), attrs
    if value is None:
        return "unavailable", attrs
    if source.field in TEMPERATURE_FIELDS:
        attrs["unit_of_measurement"] = "°C"
    return str(value), attrs


def apply_z2m(table: SampleTable, sources: Iterable[Source], device: str, payload: dict[str, Any],
              now: datetime) -> list[str]:
    """One Zigbee2MQTT message: every source bound to this device takes its field; returns the sources updated."""
    seen = parse_time(payload.get("last_seen"))
    done = []
    for s in sources:
        if s.kind != "z2m" or s.device != device:
            continue
        got = z2m_value(s, payload)
        if got is None:
            continue
        table.put(s.entity_id, got[0], now, got[1], seen=seen)
        done.append(s.entity_id)
    return done


class Z2mFeed:
    """Listens to the Zigbee2MQTT device topics of the bound sources (needs `aiomqtt`)."""

    def __init__(self, cfg: Config, table: SampleTable) -> None:
        self.cfg, self.table = cfg, table
        self.sources = [s for s in cfg.sources.values() if s.kind == "z2m"]
        self.base = cfg.mqtt.get("base_topic") or "zigbee2mqtt"
        self.connected = False
        self.messages = 0

    async def run(self) -> None:
        import aiomqtt  # only where Zigbee sources are used

        devices = sorted({s.device for s in self.sources})
        while True:
            try:
                async with aiomqtt.Client(hostname=self.cfg.mqtt["host"], port=int(self.cfg.mqtt.get("port") or 1883),
                                          username=self.cfg.mqtt.get("username") or None,
                                          password=self.cfg.mqtt.get("password") or None,
                                          identifier="hcd") as client:
                    for d in devices:
                        await client.subscribe(f"{self.base}/{d}")
                    self.connected = True
                    _LOGGER.info("MQTT: listening to %d Zigbee2MQTT device(s)", len(devices))
                    async for msg in client.messages:
                        device = str(msg.topic)[len(self.base) + 1:]
                        try:
                            payload = json.loads(msg.payload)
                        except (ValueError, TypeError):
                            continue
                        if isinstance(payload, dict):
                            apply_z2m(self.table, self.sources, device, payload, datetime.now(timezone.utc))
                            self.messages += 1
            except Exception as exc:  # the broker restarts, the network drops: try again
                self.connected = False
                _LOGGER.warning("MQTT: %s – retrying in 10 s", exc)
                await asyncio.sleep(10)


# --- Home Assistant --------------------------------------------------------------------------------------------------
def apply_ha(table: SampleTable, sources: Iterable[Source], states: list[dict[str, Any]]) -> list[str]:
    """Home Assistant's states (REST `/api/states`) into the table, for the `ha` sources.

    The REST answer keeps an old `last_reported` while a value does not change, so a source with `seen_from` takes
    the device's own time from that timestamp entity."""
    by_id = {s["entity_id"]: s for s in states}
    done = []
    for src in sources:
        if src.kind != "ha" or src.entity_id not in by_id:
            continue
        st = by_id[src.entity_id]
        at = parse_time(st.get("last_reported")) or parse_time(st.get("last_updated")) or datetime.now(timezone.utc)
        seen = parse_time((by_id.get(src.seen_from) or {}).get("state")) if src.seen_from else None
        table.put(src.entity_id, st.get("state"), at, st.get("attributes") or {}, seen=seen)
        done.append(src.entity_id)
    return done


class HaFeed:
    """Polls Home Assistant's states (also the ones the comparison reads)."""

    def __init__(self, cfg: Config, table: SampleTable, session: aiohttp.ClientSession) -> None:
        self.cfg, self.table, self.session = cfg, table, session
        self.sources = [s for s in cfg.sources.values() if s.kind == "ha"]
        self.states: dict[str, dict[str, Any]] = {}
        self.ok = False

    async def poll(self) -> None:
        try:
            async with self.session.get(f"{self.cfg.ha_url}/api/states",
                                        headers={"Authorization": f"Bearer {self.cfg.ha_token}"},
                                        timeout=aiohttp.ClientTimeout(total=15)) as r:
                r.raise_for_status()
                states = await r.json()
        except Exception as exc:
            self.ok = False
            _LOGGER.warning("Home Assistant: %s", exc)
            return
        self.states = {s["entity_id"]: s for s in states}
        apply_ha(self.table, self.sources, states)
        self.ok = True


# --- Shelly (Gen2+ RPC) ----------------------------------------------------------------------------------------------
class ShellyRpcFeed:
    """Reads a Shelly switch's output (Switch.GetStatus) – the relay as it really is."""

    def __init__(self, cfg: Config, table: SampleTable, session: aiohttp.ClientSession) -> None:
        self.table, self.session = table, session
        self.sources = [s for s in cfg.sources.values() if s.kind == "shelly_rpc"]

    async def poll(self) -> None:
        for s in self.sources:
            now = datetime.now(timezone.utc)
            try:
                async with self.session.get(f"http://{s.host}/rpc/Switch.GetStatus", params={"id": str(s.switch)},
                                            timeout=aiohttp.ClientTimeout(total=5)) as r:
                    r.raise_for_status()
                    data = await r.json()
                self.table.put(s.entity_id, "on" if data.get("output") else "off", now)
            except Exception as exc:
                _LOGGER.debug("Shelly %s: %s", s.host, exc)
                self.table.put(s.entity_id, "unavailable", now)

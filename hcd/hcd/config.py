"""hcd's settings: one HC instance (the same keys as the Home Assistant integration's options) and where each of its
sources is read from.

    name: Boiler
    timezone: Europe/Budapest
    step_s: 60
    hc: {...}                       # the instance's settings, as HC keeps them (import_ha writes them)
    sources:                        # every entity the settings name, bound to a feed
      sensor.living_room_temperature: {kind: ha, seen_from: sensor.living_room_last_seen}
      sensor.kitchen_temperature: {kind: z2m, device: Kitchen TH, field: temperature}
      binary_sensor.zone_door: {kind: z2m, device: Door_1, field: contact, invert: true}
      binary_sensor.boiler_flame: {kind: z2m, device: Plug_boiler, field: power, above: 115}
      switch.boiler: {kind: shelly_rpc, host: 192.0.2.10, switch: 0}  # a documentation address (RFC 5737)
    ha: {url: http://supervisor/core, token_env: SUPERVISOR_TOKEN}
    mqtt: {host: core-mosquitto, port: 1883, username: ..., password: ..., base_topic: zigbee2mqtt}
    compare: {decision: sensor.boiler_hc_decision, climate: climate.boiler_hc, relay: switch.boiler}
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any

import yaml

KINDS = ("ha", "z2m", "shelly_rpc")


@dataclass(frozen=True)
class Source:
    entity_id: str
    kind: str
    seen_from: str | None = None  # ha: a timestamp entity with the device's own "last seen" time
    device: str | None = None  # z2m: the device's friendly name (or IEEE address)
    field: str | None = None  # z2m: the payload field
    invert: bool = False  # z2m: a contact's "true" (closed) is "off" (not open)
    above: float | None = None  # z2m: a number at or above this is "on" (a power draw as a burner signal)
    host: str | None = None  # shelly_rpc
    switch: int = 0  # shelly_rpc: the switch id


@dataclass
class Config:
    name: str
    hc: dict[str, Any]
    sources: dict[str, Source]
    timezone: str = "UTC"
    step_s: float = 60.0
    ha_url: str | None = None
    ha_token: str | None = None
    mqtt: dict[str, Any] = field(default_factory=dict)
    compare: dict[str, str] = field(default_factory=dict)
    data_dir: str = "/data"
    web_port: int = 8099
    web_host: str = "127.0.0.1"  # 0.1.3 (security review): only this machine by default – the page has no login
    web_allow: list[str] = field(default_factory=list)  # 0.1.3: remote addresses let in (empty: everyone who reaches it)
    seed_state: str | None = None  # a state file to start from when hcd has none (import_ha --state)
    # 0.1.4: in shadow the house follows the integration's relay, not hcd's – so hcd's own lessons would come from
    # results of decisions it never made and drift away. With an HC entry id here, hcd takes the integration's learned
    # values (its learner state, from the entry's diagnostics) at start and every `learned_every_s`.
    learned_from: str | None = None
    learned_every_s: float = 900.0

    def kinds(self) -> set[str]:
        return {s.kind for s in self.sources.values()}


class ConfigError(ValueError):
    pass


def parse(raw: dict[str, Any], env: dict[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    if not isinstance(raw, dict) or not isinstance(raw.get("hc"), dict):
        raise ConfigError("the settings need an `hc` mapping (the instance's settings)")
    sources: dict[str, Source] = {}
    for entity_id, spec in (raw.get("sources") or {}).items():
        spec = dict(spec or {})
        kind = spec.pop("kind", "ha")
        if kind not in KINDS:
            raise ConfigError(f"{entity_id}: unknown source kind {kind!r} (one of {', '.join(KINDS)})")
        if kind == "z2m" and not (spec.get("device") and spec.get("field")):
            raise ConfigError(f"{entity_id}: a z2m source needs `device` and `field`")
        if kind == "shelly_rpc" and not spec.get("host"):
            raise ConfigError(f"{entity_id}: a shelly_rpc source needs `host`")
        unknown = set(spec) - {"seen_from", "device", "field", "invert", "above", "host", "switch"}
        if unknown:
            raise ConfigError(f"{entity_id}: unknown setting(s) {', '.join(sorted(unknown))}")
        sources[entity_id] = Source(entity_id, kind, **spec)
    ha = raw.get("ha") or {}
    token = ha.get("token") or env.get(ha.get("token_env") or "SUPERVISOR_TOKEN")
    cfg = Config(
        name=str(raw.get("name") or raw["hc"].get("name") or "HC"),
        hc=dict(raw["hc"]),
        sources=sources,
        timezone=str(raw.get("timezone") or "UTC"),
        step_s=float(raw.get("step_s") or 60.0),
        ha_url=(ha.get("url") or None),
        ha_token=token,
        mqtt=dict(raw.get("mqtt") or {}),
        compare=dict(raw.get("compare") or {}),
        data_dir=str(raw.get("data_dir") or "/data"),
        web_port=int(raw.get("web_port") or 8099),
        web_host=str(raw.get("web_host") or "127.0.0.1"),
        web_allow=[str(a) for a in (raw.get("web_allow") or [])],
        seed_state=raw.get("seed_state") or None,
        learned_from=(str(raw["learned_from"]) if raw.get("learned_from") else None),
        learned_every_s=max(60.0, float(raw.get("learned_every_s") or 900.0)),
    )
    if "ha" in cfg.kinds() and not (cfg.ha_url and cfg.ha_token):
        raise ConfigError("`ha` sources need `ha.url` and a token")
    if cfg.learned_from and not (cfg.ha_url and cfg.ha_token):
        raise ConfigError("`learned_from` needs `ha.url` and a token")
    if "z2m" in cfg.kinds() and not cfg.mqtt.get("host"):
        raise ConfigError("`z2m` sources need `mqtt.host` (or `host: supervisor` inside a Home Assistant add-on)")
    return cfg


def load(path: str | Path, env: dict[str, str] | None = None) -> Config:
    with open(path, encoding="utf-8") as f:
        return parse(yaml.safe_load(f) or {}, env)

"""Make an hcd settings file from an HC instance in Home Assistant: `python -m hcd.import_ha --entry <id> --out x.yaml`.

Reads the instance's diagnostics (its settings and the supervisor's state) through Home Assistant's REST API. Every
entity the settings read becomes an `ha` source; change the ones a device can give directly (z2m, shelly_rpc).
With `--state`, the supervisor's current state (learned values, PWM phase, boost) is written as hcd's state file, so
the shadow comparison starts from where the integration is.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

import yaml

from .engine import Engine
from hc_core.inputs import SampleTable
from datetime import datetime, timezone


def fetch(url: str, token: str, entry: str) -> dict:
    req = urllib.request.Request(f"{url}/api/diagnostics/config_entry/{entry}",
                                 headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def build(diag: dict, compare: dict | None = None) -> tuple[dict, dict]:
    data = diag.get("data") or {}
    hc = {**(data.get("data") or {}), **(data.get("options") or {})}
    engine = Engine(hc, SampleTable(), None, datetime.now(timezone.utc))
    settings = {
        "name": hc.get("name") or (data.get("title") or "HC"),
        "timezone": "Europe/Budapest",
        "step_s": 60,
        "hc": hc,
        "sources": {e: {"kind": "ha"} for e in sorted(engine.entities())},
        "ha": {"url": "http://supervisor/core", "token_env": "SUPERVISOR_TOKEN"},
        "compare": compare or {},
    }
    state = {"supervisor": (data.get("info") or {}).get("state") or {}}
    return settings, state


def main() -> None:
    ap = argparse.ArgumentParser(prog="hcd.import_ha")
    ap.add_argument("--entry", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--state", help="also write the supervisor's state here (hcd's state.json)")
    ap.add_argument("--url", default=os.environ.get("HA_URL", "http://supervisor/core"))
    ap.add_argument("--token", default=os.environ.get("HA_TOKEN") or os.environ.get("SUPERVISOR_TOKEN"))
    ap.add_argument("--decision", help="compare: the integration's decision sensor")
    ap.add_argument("--climate", help="compare: the integration's climate entity")
    ap.add_argument("--relay", help="compare: the relay the integration switches")
    args = ap.parse_args()
    if not args.token:
        sys.exit("no token (HA_TOKEN / SUPERVISOR_TOKEN or --token)")
    compare = {k: v for k, v in (("decision", args.decision), ("climate", args.climate), ("relay", args.relay)) if v}
    settings, state = build(fetch(args.url, args.token, args.entry), compare)
    with open(args.out, "w", encoding="utf-8") as f:
        yaml.safe_dump(settings, f, allow_unicode=True, sort_keys=False)
    if args.state:
        with open(args.state, "w", encoding="utf-8") as f:
            json.dump(state, f)
    print(f"{args.out}: {len(settings['sources'])} source(s)" + (f", state → {args.state}" if args.state else ""))


if __name__ == "__main__":
    main()

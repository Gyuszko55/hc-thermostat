#!/usr/bin/env python3
"""Put the HC local guard script on a Shelly Gen3 / Gen4 (0.76.0).

    python3 guard/upload_shelly.py 10.0.0.50 [--sensor bthomesensor:200 | temperature:100 | none]
                                             [--safety input:0:on] [--deadman 180] [--set-password]

Creates (or replaces) the script "hc_guard", uploads guard/shelly/hc_guard.js in chunks, turns on autostart, writes
the KVS keys the script reads and starts it. Prints the lease URL for the HC settings. Needs aiohttp 3.12 or later
(`pip install aiohttp`).

0.78.2 (security review H3):
- the token is required: HC_GUARD_TOKEN from the environment (or --token); without one a new random token is made,
  written to the device and printed once – put it into HC's settings (Local guard → Token);
- a device with a password: HC_GUARD_PASSWORD from the environment (or --password) – digest auth, user admin;
- --set-password protects the device with that password first (Shelly.SetAuth). Give the same password to HC
  (Local guard → Device password) and to Home Assistant's Shelly integration (reconfigure the device there).
Secrets in the environment stay out of the shell history and the process list.

0.78.4: the calls go through aiohttp – the standard library's urllib knows no SHA-256 digest (the only one a Shelly
Gen2+ offers), so a protected device could not be reached. One session and one digest middleware for the whole run:
the challenge comes once, every later call is signed in advance (a Shelly answers a burst of 401s with 429); a 429
is waited out and tried again.
"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

CODE = Path(__file__).resolve().parent / "shelly" / "hc_guard.js"
LITE = Path(__file__).resolve().parent / "shelly" / "hc_lite.js"  # 0.79.2: HC Lite – a whole thermostat on the relay
CHUNK = 1024
BUSY_TRIES = 4  # a 429: wait 2, 4, 6 s and try again
TIMEOUT_S = 10


class _Client:
    """One event loop, one aiohttp session and (with a password) one digest middleware for the whole run."""

    def __init__(self) -> None:
        self.password = ""
        self.loop: asyncio.AbstractEventLoop | None = None
        self.session = None

    async def _session(self):
        if self.session is None:
            try:
                import aiohttp
            except ImportError:  # pragma: no cover - depends on the machine
                raise SystemExit("upload_shelly.py needs aiohttp 3.12 or later: pip install aiohttp") from None
            mw = (aiohttp.DigestAuthMiddleware("admin", self.password),) if self.password else ()
            self.session = aiohttp.ClientSession(middlewares=mw, timeout=aiohttp.ClientTimeout(total=TIMEOUT_S))
        return self.session

    async def _call(self, host: str, method: str, params: dict | None) -> dict:
        session = await self._session()
        for attempt in range(BUSY_TRIES):
            async with session.post(f"http://{host}/rpc/{method}", json=params or {}) as resp:
                if resp.status == 429 and attempt < BUSY_TRIES - 1:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                if resp.status == 401:
                    raise SystemExit(f"{method}: the device refused the password (HTTP 401)")
                if resp.status != 200:
                    raise SystemExit(f"{method}: HTTP {resp.status} {(await resp.text())[:200]}")
                return json.loads(await resp.read() or b"{}") or {}
        raise SystemExit(f"{method}: the device stays busy (HTTP 429)")  # pragma: no cover

    def run(self, coro):
        if self.loop is None:
            self.loop = asyncio.new_event_loop()
        return self.loop.run_until_complete(coro)

    def close(self) -> None:
        if self.session is not None:
            self.run(self.session.close())
            self.session = None
        if self.loop is not None:
            self.loop.close()
            self.loop = None


_CLIENT = _Client()


def use_password(host: str, password: str) -> None:
    """Digest auth (SHA-256, user admin) for every later call."""
    if _CLIENT.session is not None and _CLIENT.password != password:
        _CLIENT.run(_CLIENT.session.close())
        _CLIENT.session = None
    _CLIENT.password = password


def rpc(host: str, method: str, params: dict | None = None) -> dict:
    return _CLIENT.run(_CLIENT._call(host, method, params))


def set_auth(host: str, info: dict, password: str) -> None:
    """Shelly.SetAuth: ha1 = sha256("admin:<device id>:<password>")."""
    realm = info["id"]
    ha1 = hashlib.sha256(f"admin:{realm}:{password}".encode()).hexdigest()
    rpc(host, "Shelly.SetAuth", {"user": "admin", "realm": realm, "ha1": ha1})


def _auth(a, info: dict, password: str) -> int:
    if a.set_password:
        if not info.get("auth_en"):
            set_auth(a.host, info, password)
            print("The device is now protected with the password (user admin).")
        use_password(a.host, password)
    elif password or info.get("auth_en"):
        if not password:
            print("The device has a password: give it in HC_GUARD_PASSWORD (or --password)")
            return 2
        use_password(a.host, password)
    return 0


def _put(host: str, name: str, code: str) -> int:
    scripts = rpc(host, "Script.List").get("scripts", [])
    sid = next((s["id"] for s in scripts if s.get("name") == name), None)
    if sid is None:
        sid = rpc(host, "Script.Create", {"name": name})["id"]
    else:
        rpc(host, "Script.Stop", {"id": sid})
    for i in range(0, len(code), CHUNK):
        rpc(host, "Script.PutCode", {"id": sid, "code": code[i:i + CHUNK], "append": i > 0})
    rpc(host, "Script.SetConfig", {"id": sid, "config": {"enable": True}})
    return sid


# 0.82.5: the BTHome object ids of a temperature and a humidity (0x45 / 0x02, 0x2E / 0x03)
TEMP_OBJ = (69, 2)
HUM_OBJ = (46, 3)


def bthome_find(host: str) -> tuple[int | None, int | None]:
    """The relay's own BTHome sensors: the first temperature and humidity id (a fresh pairing numbers them by object
    id, so 200 is often the battery – measured on a Shelly 1 Gen4 with a BLU H&T)."""
    comps = rpc(host, "Shelly.GetComponents", {"dynamic_only": True}).get("components") or []
    temp = hum = None
    for c in comps:
        key, cfg = str(c.get("key", "")), c.get("config") or {}
        if not key.startswith("bthomesensor:"):
            continue
        sid, obj = int(key.split(":")[1]), cfg.get("obj_id")
        if obj in TEMP_OBJ and temp is None:
            temp = sid
        elif obj in HUM_OBJ and hum is None:
            hum = sid
    return temp, hum


def lite(a) -> int:
    """0.79.2: HC Lite – its own script ("hc_lite"), settings in hc_lite_cfg (kept; only the sensor and shadow are
    set here), the token in hc_lite_token. The guard script, if any, is left alone (do not run both on one relay)."""
    token = a.token or os.environ.get("HC_GUARD_TOKEN", "")
    password = a.password or os.environ.get("HC_GUARD_PASSWORD", "")
    if a.set_password and len(password) < 8:
        print("--set-password: give a password of at least 8 characters (HC_GUARD_PASSWORD)")
        return 2
    kind, _, sid_s = a.sensor.partition(":")
    hum_id = None
    if a.sensor in ("auto", "bthomesensor", "bthomesensor:auto") or (kind == "bthomesensor" and sid_s.isdigit()):
        # 0.82.5: find the BLU H&T's temperature (and humidity) on the relay; a given id must be a temperature
        temp, hum_id = bthome_find(a.host)
        if kind == "bthomesensor" and sid_s.isdigit() and int(sid_s) != temp:
            print(f"bthomesensor:{sid_s} is not a temperature on this relay"
                  + (f" – using bthomesensor:{temp}" if temp is not None else ""))
        if temp is None:
            print("No BTHome temperature on the relay: pair the BLU H&T first (Shelly page → Components / Bluetooth"
                  " → add device), then run this again")
            return 2
        kind, sid_s = "bthomesensor", str(temp)
        print(f"Thermometer: bthomesensor:{temp}" + (f", humidity: bthomesensor:{hum_id}" if hum_id is not None else ""))
    if kind not in ("bthomesensor", "temperature") or not sid_s.isdigit():
        print("--lite needs --sensor auto (the BLU H&T paired to the relay), bthomesensor:<id> or temperature:<id> (an add-on probe)")
        return 2
    from compact_js import compact  # 0.80.0: without comments and indentation (the relay keeps less in its heap)
    code = compact(LITE.read_text("ascii"))
    info = rpc(a.host, "Shelly.GetDeviceInfo")
    rc = _auth(a, info, password)
    if rc:
        return rc
    if int(info.get("gen", 0)) < 2:
        print(f"{info.get('model')}: generation {info.get('gen')} has no scripting – use a Gen3 / Gen4 relay")
        return 1
    guard = next((s for s in rpc(a.host, "Script.List").get("scripts", []) if s.get("name") == "hc_guard"), None)
    if guard and guard.get("running"):
        print("hc_guard runs on this relay – stop it first: one script must own the relay")
        return 1
    sid = _put(a.host, "hc_lite", code)
    items = rpc(a.host, "KVS.GetMany", {"match": "hc_lite_cfg"}).get("items") or []
    if isinstance(items, dict):  # older firmware: an object by key
        items = [{"key": k, **v} for k, v in items.items()]
    try:
        cfg = json.loads(next((i.get("value") for i in items if i.get("key") == "hc_lite_cfg"), None) or "{}")
    except ValueError:
        cfg = {}
    cfg.update(sensor=kind, sensor_id=int(sid_s), shadow=bool(a.shadow))
    if hum_id is not None and int(cfg.get("hum_id", -1)) < 0:
        cfg["hum_id"] = hum_id
    rpc(a.host, "KVS.Set", {"key": "hc_lite_cfg", "value": json.dumps(cfg)})
    made = not token
    if made:
        token = secrets.token_urlsafe(18)
    rpc(a.host, "KVS.Set", {"key": "hc_lite_token", "value": token})
    rpc(a.host, "Script.Start", {"id": sid})
    print(f"HC Lite is running as script {sid} on {info.get('model')} ({info.get('ver')})"
          + (" – SHADOW: it decides, the relay is not switched" if a.shadow else ""))
    print(f"Status: http://{a.host}/script/{sid}/lite   page: http://{a.host}/script/{sid}/lite?page=1")
    if made:
        print(f"Token (new, shown only now): {token}")
        print("  Keep it: the relay's page asks for it (First steps → Token), and Home Assistant too (HC Lite).")
    if not info.get("auth_en") and not a.set_password:
        print("WARNING: the device has no password – the page stays read only and anyone on the network can switch "
              "the relay. Run again with --set-password (HC_GUARD_PASSWORD).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("--sensor", default="auto",
                    help="auto (with --lite: the BLU H&T paired to the relay), bthomesensor:<id>, temperature:<id> or none")
    ap.add_argument("--token", default="", help="better: HC_GUARD_TOKEN in the environment; none: a new one is made")
    ap.add_argument("--password", default="", help="the device's password; better: HC_GUARD_PASSWORD in the environment")
    ap.add_argument("--set-password", action="store_true", help="protect the device with that password first")
    ap.add_argument("--safety", default="", help="input:<id>:on|off – the input wired to the life-safety chain's "
                    "auxiliary contact and its state when the chain is closed (all clear)")
    ap.add_argument("--deadman", type=int, default=None, help="0.77.1: seconds after which the relay switches itself "
                    "off unless the running script re-arms it (default 180 on the device; 0 = none, else 60-3600)")
    ap.add_argument("--lite", action="store_true", help="0.79.2: upload HC Lite (a complete thermostat on the relay) "
                    "instead of the guard; --sensor gives its BLU H&T (bthomesensor:<id>)")
    ap.add_argument("--shadow", action="store_true", help="with --lite: decide and report, never switch the relay")
    a = ap.parse_args()
    if a.lite:
        return lite(a)
    if a.deadman is not None and a.deadman != 0 and not 60 <= a.deadman <= 3600:
        print("--deadman: 0 or 60-3600 seconds")
        return 2
    token = a.token or os.environ.get("HC_GUARD_TOKEN", "")
    password = a.password or os.environ.get("HC_GUARD_PASSWORD", "")
    if a.set_password and len(password) < 8:
        print("--set-password: give a password of at least 8 characters (HC_GUARD_PASSWORD)")
        return 2
    code = CODE.read_text("ascii")  # the device refuses longer code with many non-ASCII characters
    info = rpc(a.host, "Shelly.GetDeviceInfo")  # open also on a protected device
    if a.set_password:
        if not info.get("auth_en"):
            set_auth(a.host, info, password)
            print("The device is now protected with the password (user admin).")
        use_password(a.host, password)
    elif password or info.get("auth_en"):
        if not password:
            print("The device has a password: give it in HC_GUARD_PASSWORD (or --password)")
            return 2
        use_password(a.host, password)
    if int(info.get("gen", 0)) < 2:
        print(f"{info.get('model')}: generation {info.get('gen')} has no scripting – use a Gen3 / Gen4 relay")
        return 1
    scripts = rpc(a.host, "Script.List").get("scripts", [])
    sid = next((s["id"] for s in scripts if s.get("name") == "hc_guard"), None)
    if sid is None:
        sid = rpc(a.host, "Script.Create", {"name": "hc_guard"})["id"]
    else:
        rpc(a.host, "Script.Stop", {"id": sid})
    for i in range(0, len(code), CHUNK):
        rpc(a.host, "Script.PutCode", {"id": sid, "code": code[i:i + CHUNK], "append": i > 0})
    rpc(a.host, "Script.SetConfig", {"id": sid, "config": {"enable": True}})
    if a.sensor == "auto":  # 0.82.5: the guard's own thermometer, if a BLU H&T is paired to the relay
        temp, _ = bthome_find(a.host)
        a.sensor = f"bthomesensor:{temp}" if temp is not None else "none"
        print(f"Guard thermometer: {a.sensor}")
    rpc(a.host, "KVS.Set", {"key": "hc_guard_sensor", "value": a.sensor})
    made = not token
    if made:
        token = secrets.token_urlsafe(18)
    rpc(a.host, "KVS.Set", {"key": "hc_guard_token", "value": token})
    if a.safety:
        rpc(a.host, "KVS.Set", {"key": "hc_guard_safety", "value": a.safety})
    if a.deadman is not None:
        rpc(a.host, "KVS.Set", {"key": "hc_guard_deadman", "value": str(a.deadman)})
    rpc(a.host, "Script.Start", {"id": sid})
    print(f"hc_guard is running as script {sid} on {info.get('model')} ({info.get('ver')})")
    print(f"HC settings → Local guard → address: http://{a.host}/script/{sid}/hc")
    if made:
        print(f"HC settings → Local guard → token (new, shown only now): {token}")
    if not info.get("auth_en") and not a.set_password:
        print("WARNING: the device has no password – anyone on the network can switch the relay. "
              "Run again with --set-password (HC_GUARD_PASSWORD).")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    finally:
        _CLIENT.close()

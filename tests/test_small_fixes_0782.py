"""0.78.2 (security review, the small ones): a relay entity that is gone is a failed relay part; with a watchdog
script the relay goes on only through it; a safety input without a reading for 10 minutes is a Repairs entry; the
drawing's escape covers the apostrophe."""

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

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT / "custom_components"))

executor_mod = importlib.import_module("hc_thermostat.executor")
model = importlib.import_module("hc_thermostat.core.model")
safety = importlib.import_module("hc_thermostat.core.safety")
hub_mod = importlib.import_module("hc_thermostat.safety_hub")

T0 = datetime(2026, 11, 21, 6, 0, tzinfo=timezone.utc)


class _Hass:
    def __init__(self, states, fail_script=False):
        self._s, self.calls, self.data = states, [], {}
        self.states = SimpleNamespace(get=self._s.get)
        self.services = SimpleNamespace(async_call=self._call)
        self.fail_script = fail_script

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data, blocking))
        if domain == "script" and self.fail_script:
            raise RuntimeError("the device did not answer")


def _on():
    return model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=1.0, output=True)


def test_a_relay_that_is_gone_is_a_failed_part():
    ex = executor_mod.Executor(_Hass({}), "active", "switch.gone", None)
    asyncio.run(ex.apply(_on()))
    assert ex.failed == {"relay"}


def test_on_only_through_the_watchdog_script_and_its_failure_counts():
    hass = _Hass({"switch.b": SimpleNamespace(state="off", attributes={})})
    ex = executor_mod.Executor(hass, "active", "switch.b", None, keep_alive_s=60, keep_script="script.rearm")
    asyncio.run(ex.apply(_on()))
    assert hass.calls == [("script", "rearm", {}, True)] and ex.failed == set()
    hass2 = _Hass({"switch.b": SimpleNamespace(state="off", attributes={})}, fail_script=True)
    ex2 = executor_mod.Executor(hass2, "active", "switch.b", None, keep_alive_s=60, keep_script="script.rearm")
    asyncio.run(ex2.apply(_on()))
    assert ex2.failed == {"relay"} and not [c for c in hass2.calls if c[0] == "homeassistant"]  # never on without it


def test_a_lost_safety_input_becomes_a_repairs_entry(monkeypatch):
    shown = {}
    monkeypatch.setattr(hub_mod.ir, "async_create_issue", lambda h, d, i, **k: shown.__setitem__(i, k))
    monkeypatch.setattr(hub_mod.ir, "async_delete_issue", lambda h, d, i: shown.pop(i, None))
    states = {"binary_sensor.smoke": SimpleNamespace(state="unavailable", attributes={"friendly_name": "Füst"})}
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), data={}, config=SimpleNamespace(language="hu"),
                           async_create_task=lambda c: c.close(), bus=SimpleNamespace(async_fire=lambda *a: None))
    hub = hub_mod.SafetyHub.__new__(hub_mod.SafetyHub)
    hub.hass, hub.latch, hub.watched, hub._announced, hub._lost_shown = hass, safety.SafetyLatch(), {"e": ["binary_sensor.smoke"]}, False, ()
    assert hub.check(T0) is False and shown == {}
    assert hub.check(T0 + timedelta(minutes=11)) is False  # it never trips on a lost reading ...
    assert shown["safety_input_lost"]["translation_placeholders"] == {"inputs": "Füst"}  # ... but it is reported
    states["binary_sensor.smoke"] = SimpleNamespace(state="off", attributes={})
    hub.check(T0 + timedelta(minutes=12))
    assert shown == {}
    for lang in ("en", "hu"):
        assert "{inputs}" in json.loads((BASE / "translations" / f"{lang}.json").read_text())["issues"]["safety_input_lost"]["description"]


def test_escape_covers_the_apostrophe():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    for f in ("hc-overview.js", "hc-house-view.js", "hc-info-panel.js"):
        line = next(l for l in (BASE / "www" / f).read_text().splitlines() if l.startswith("const esc ="))
        line = line.split("  //")[0]  # without a trailing comment
        out = subprocess.run([node, "-e", line.replace("const esc", "var esc") + ";console.log(esc(\"a'b\"))"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        assert out == "a&#39;b", f

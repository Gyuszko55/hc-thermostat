"""Packaging checks and the promise of shadow mode."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "hc_thermostat"


def _keys(data, prefix=""):
    out = set()
    for key, value in data.items():
        out |= _keys(value, f"{prefix}{key}.") if isinstance(value, dict) else {prefix + key}
    return out


def test_translations_match():
    en = json.loads((BASE / "translations/en.json").read_text("utf8"))
    hu = json.loads((BASE / "translations/hu.json").read_text("utf8"))
    assert _keys(en) == _keys(hu)
    for data in (en, hu):
        assert set(data["entity"]["sensor"]["decision"]["state"]) == {r.value for r in __import__("core.model", fromlist=["Reason"]).Reason}


def test_matrix_options_have_labels():
    from core.matrix import SOURCES, SYSTEMS
    en = json.loads((BASE / "translations/en.json").read_text("utf8"))["selector"]
    assert set(en["heat_source"]["options"]) == set(SOURCES)
    assert set(en["system"]["options"]) == set(SYSTEMS)


def _executor(mode, relay="off", climate="heat", temperature=21.0):
    import sys
    sys.path.insert(0, str(ROOT))
    from custom_components.hc_thermostat.executor import Executor
    calls = []
    states = {
        "switch.boiler": SimpleNamespace(state=relay, attributes={}),
        "climate.room": SimpleNamespace(state=climate, attributes={"temperature": temperature}),
    }

    async def call(domain, service, data, blocking=False):
        calls.append((domain, service, data))

    hass = SimpleNamespace(states=SimpleNamespace(get=states.get), services=SimpleNamespace(async_call=call), data={})
    return Executor(hass, mode, "switch.boiler", "climate.room"), calls


def _decision(output=True, external=None):
    from custom_components.hc_thermostat.core.model import Decision, Reason
    return Decision(datetime(2026, 11, 10, tzinfo=timezone.utc), Reason.REGULATING, 21.0, 20.0, 0.0,
                    output=output, external=external)


def _command(hvac, target):
    from custom_components.hc_thermostat.core.model import ExternalCommand
    return ExternalCommand(hvac, target)


@pytest.mark.parametrize("output", [True, False])
def test_shadow_mode_never_calls_a_service(output):
    executor, calls = _executor("shadow", relay="off" if output else "on")
    asyncio.run(executor.apply(_decision(output)))
    asyncio.run(executor.apply(_decision(output, _command("off", 5.0))))
    assert calls == []


def test_active_relay_switches_only_on_difference():
    executor, calls = _executor("active", relay="off")
    asyncio.run(executor.apply(_decision(False)))
    assert calls == []
    asyncio.run(executor.apply(_decision(True)))
    assert calls == [("homeassistant", "turn_on", {"entity_id": "switch.boiler"})]


def test_active_does_not_touch_unavailable_device():
    executor, calls = _executor("active", relay="unavailable")
    asyncio.run(executor.apply(_decision(True)))
    assert calls == []


def test_active_external_commands():
    executor, calls = _executor("active", climate="heat", temperature=20.0)
    asyncio.run(executor.apply(_decision(True, _command("heat", 21.0))))
    assert calls == [("climate", "set_temperature", {"entity_id": "climate.room", "temperature": 21.0})]
    executor, calls = _executor("active", climate="heat")
    asyncio.run(executor.apply(_decision(False, _command("off", 21.0))))
    assert calls == [("climate", "set_hvac_mode", {"entity_id": "climate.room", "hvac_mode": "off"})]

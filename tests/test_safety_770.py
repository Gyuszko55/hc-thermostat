"""0.77.0: the life-safety stop – the latch (core/safety.py), the supervisor's stop above every reason, the shared hub,
the heat pump coordination, the entities, the settings and the texts."""

import asyncio
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from core.messages import explain  # noqa: E402
from core.model import HcConfig, Inputs, Reading, Reason  # noqa: E402
from core.safety import SafetyLatch  # noqa: E402
from core.supervisor import Supervisor  # noqa: E402

T0 = datetime(2026, 11, 18, 16, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, boost_enabled=False, learning_enabled=False,
           target_home=21.0, control="tpi")


def at(m):
    return T0 + timedelta(minutes=m)


# --- the latch ------------------------------------------------------------------------------------------------------------
def test_the_latch_trips_holds_and_lets_go_only_when_clear():
    lt = SafetyLatch()
    assert not lt.check(at(0), {"binary_sensor.smoke": "off", "binary_sensor.chain": "off"})
    assert lt.check(at(1), {"binary_sensor.smoke": "on", "binary_sensor.chain": "off"})
    assert lt.by == ["binary_sensor.smoke"] and lt.since == at(1)
    assert lt.check(at(2), {"binary_sensor.smoke": "off", "binary_sensor.chain": "on"})  # holds, and adds
    assert lt.by == ["binary_sensor.chain", "binary_sensor.smoke"]
    assert not lt.acknowledge(at(3))  # the chain is still open
    assert lt.check(at(4), {"binary_sensor.smoke": "off", "binary_sensor.chain": "off"})  # cleared, still latched
    assert lt.acknowledge(at(5), "user-1") and not lt.tripped and lt.cleared_by == "user-1"


def test_an_unreadable_input_does_not_trip_but_blocks_the_acknowledgement():
    lt = SafetyLatch()
    assert not lt.check(at(0), {"binary_sensor.co": "unavailable"}) and lt.unknown == ["binary_sensor.co"]
    lt.check(at(1), {"binary_sensor.co": "on"})
    lt.check(at(2), {"binary_sensor.co": "unavailable"})
    assert not lt.acknowledge(at(3))


def test_the_latch_survives_a_restart_and_a_broken_record_stays_safe():
    lt = SafetyLatch()
    lt.check(at(0), {"binary_sensor.gas": "on"})
    fresh = SafetyLatch()
    fresh.restore(json.loads(json.dumps(lt.state())))
    assert fresh.tripped and fresh.by == ["binary_sensor.gas"] and fresh.since == at(0)
    broken = SafetyLatch()
    broken.restore({"tripped": False, "since": "not a date"})
    assert broken.tripped


# --- the supervisor -------------------------------------------------------------------------------------------------------
def _in(m, indoor, stop=False, **kw):
    return Inputs(now=at(m), indoor=Reading(indoor), outdoor=Reading(-5.0), safety_stop=stop,
                  safety=("binary_sensor.smoke",) if stop else (), **kw)


def test_the_stop_is_above_everything_and_switches_off_at_once():
    sup = Supervisor(HcConfig(**DAY))
    d = sup.step(_in(0, 18.0))
    assert d.output  # far below the target: heating
    d = sup.step(_in(1, 18.0, stop=True))  # 1 min into a burn: no minimum run time
    assert d.reason == Reason.SAFETY_STOP and not d.output and d.demand == 0.0 and d.limited_by == "safety_stop"
    assert d.details["safety_by"] == ["binary_sensor.smoke"]
    assert "ÉLETVÉDELMI LEÁLLÍTÁS" in explain(d, "hu") and "LIFE-SAFETY STOP" in explain(d, "en")
    d = sup.step(_in(2, 4.0, stop=True))  # frost: still nothing
    assert d.reason == Reason.SAFETY_STOP and not d.output
    d = sup.step(_in(30, 18.0))
    assert d.reason != Reason.SAFETY_STOP


def test_a_managed_thermostat_and_an_air_conditioner_are_switched_off():
    for control in ("external", "ac"):
        sup = Supervisor(HcConfig(**{**DAY, "control": control}))
        d = sup.step(_in(0, 18.0, stop=True))
        assert d.reason == Reason.SAFETY_STOP and d.external is not None and d.external.hvac == "off"


# --- the hub --------------------------------------------------------------------------------------------------------------
class _Store:
    saved = []

    def __init__(self, *a):
        pass

    async def async_load(self):
        return {"tripped": True, "since": T0.isoformat(), "by": ["binary_sensor.chain"]}

    async def async_save(self, data):
        _Store.saved.append(data)


def _hub(monkeypatch, states):
    sh = importlib.import_module("hc_thermostat.safety_hub")
    monkeypatch.setattr(sh, "Store", _Store)
    issues = []
    monkeypatch.setattr(sh.ir, "async_create_issue", lambda *a, **k: issues.append(("create", a[2])))
    monkeypatch.setattr(sh.ir, "async_delete_issue", lambda *a, **k: issues.append(("delete", a[2])))
    events, tasks = [], []
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: SimpleNamespace(state=states[e], attributes={"friendly_name": e}) if e in states else None),
                           bus=SimpleNamespace(async_fire=lambda ev, data=None: events.append((ev, data))),
                           async_create_task=lambda coro: tasks.append(coro) or coro.close(),
                           config=SimpleNamespace(language="hu"), data={})
    return sh, sh.hub_of(hass), events, issues


def test_the_hub_trips_once_announces_and_acknowledges(monkeypatch):
    states = {"binary_sensor.chain": "off", "binary_sensor.smoke": "off"}
    sh, hub, events, issues = _hub(monkeypatch, states)
    hub.watch("a", ["binary_sensor.chain"])
    hub.watch("b", ["binary_sensor.smoke", "binary_sensor.chain"])
    assert hub.inputs() == ["binary_sensor.chain", "binary_sensor.smoke"]
    assert not hub.check(T0)
    states["binary_sensor.smoke"] = "on"
    assert hub.check(T0) and hub.check(at(1))
    assert [e for e in events if e[0] == sh.EVENT_STOP] and len([e for e in events if e[0] == sh.EVENT_STOP]) == 1
    assert ("create", "safety_stop") in issues
    assert not hub.acknowledge("u")  # smoke still on
    states["binary_sensor.smoke"] = "off"
    assert hub.acknowledge("u") and not hub.latch.tripped
    assert [e for e in events if e[0] == sh.EVENT_CLEAR] and ("delete", "safety_stop") in issues
    hub.watch("b", [])
    assert hub.inputs() == ["binary_sensor.chain"]


def test_the_hub_restores_a_stop_from_before_the_restart(monkeypatch):
    sh, hub, events, issues = _hub(monkeypatch, {"binary_sensor.chain": "off"})
    hub.watch("a", ["binary_sensor.chain"])
    asyncio.run(hub.async_load())
    assert hub.check(T0) and hub.latch.by == ["binary_sensor.chain"]


# --- the rest -------------------------------------------------------------------------------------------------------------
def test_wiring_settings_entities_and_texts():
    from hc_thermostat import config_flow as cf
    from hc_thermostat.const import HP_COORD_PLATFORMS
    assert "safety_entities" == cf.SETTINGS_SECTIONS["protection"][0]
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda d: []))
    assert "safety_entities" in {str(k) for k in cf._hpc_fields(hass, {})}
    assert "button" in HP_COORD_PLATFORMS
    from hc_thermostat.core.hp_coord import REASONS
    assert "safety_stop" in REASONS
    src = (BASE / "hp_coord_coordinator.py").read_text()
    assert 'reason="safety_stop"' in src and "enable=False, heat_demand=False" in src
    assert "class HcSafetyStop(" in (BASE / "binary_sensor.py").read_text()
    assert "class HcSafetyAck(" in (BASE / "button.py").read_text()
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        assert tr["options"]["step"]["settings"]["sections"]["protection"]["data"]["safety_entities"]
        assert tr["config"]["step"]["hp_coord"]["data"]["safety_entities"]
        assert tr["entity"]["binary_sensor"]["safety_stop"]["name"] and tr["entity"]["button"]["safety_ack"]["name"]
        assert tr["entity"]["sensor"]["decision"]["state"]["safety_stop"]
        assert tr["entity"]["sensor"]["hp_decision"]["state"]["safety_stop"]
        assert "{by}" in tr["issues"]["safety_stop"]["description"]
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0")

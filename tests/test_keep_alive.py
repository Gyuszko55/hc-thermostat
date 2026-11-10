"""0.15.0: resending "on" to a relay that switches itself off (Shelly auto-off as a safety net)."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
executor_mod = importlib.import_module("hc_thermostat.executor")
model = importlib.import_module("hc_thermostat.core.model")
cc = importlib.import_module("hc_thermostat.central_coordinator")
central = importlib.import_module("hc_thermostat.core.central")

T0 = datetime(2026, 11, 9, 5, 30, 24, tzinfo=timezone.utc)


class AutoOffRelay:
    """A relay that switches itself off `auto_off_s` after the last "on" command, like a Shelly."""

    def __init__(self, auto_off_s=900):
        self.auto_off_s = auto_off_s
        self.on = False
        self.last_on: datetime | None = None
        self.now = T0
        self.calls = []
        self.states = SimpleNamespace(get=self._get)
        self.services = SimpleNamespace(async_call=self._call)

    def _get(self, entity_id):
        if self.on and (self.now - self.last_on).total_seconds() >= self.auto_off_s:
            self.on = False
        return SimpleNamespace(state="on" if self.on else "off", attributes={})

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((self.now, service))
        self.on = service == "turn_on"
        if self.on:
            self.last_on = self.now


def _decision(now, output):
    return model.Decision(now, model.Reason.BOOST, 22.5, 21.0, 2.7, demand=1.0, output=output)


def _run(ex, relay, minutes, output=True):
    """Steps every 30 s; returns the seconds the relay was off while the decision said on."""
    off = 0
    for k in range(minutes * 2):
        relay.now = T0 + timedelta(seconds=30 * k)
        if output and relay._get("switch.boiler").state == "off" and k:
            off += 30
        asyncio.run(ex.apply(_decision(relay.now, output)))
    return off


def test_without_keep_alive_the_auto_off_cuts_a_long_burn():
    relay = AutoOffRelay()
    ex = executor_mod.Executor(relay, "active", "switch.boiler", None)
    assert _run(ex, relay, 40) > 0  # the morning of 11-09: off at 15 and 30 minutes


def test_keep_alive_keeps_a_long_burn_going():
    relay = AutoOffRelay()
    ex = executor_mod.Executor(relay, "active", "switch.boiler", None, keep_alive_s=60)
    assert _run(ex, relay, 40) == 0
    sends = [c for c in relay.calls if c[1] == "turn_on"]
    assert 38 <= len(sends) <= 41  # about once a minute, not every 30 s step


def test_keep_alive_never_sends_on_while_the_decision_is_off():
    relay = AutoOffRelay()
    ex = executor_mod.Executor(relay, "active", "switch.boiler", None, keep_alive_s=60)
    _run(ex, relay, 10, output=False)
    assert relay.calls == []


def test_keep_alive_does_nothing_in_shadow_mode():
    relay = AutoOffRelay()
    ex = executor_mod.Executor(relay, "shadow", "switch.boiler", None, keep_alive_s=60)
    _run(ex, relay, 5)
    assert relay.calls == []


def test_keep_alive_option_reaches_the_config():
    assert model.HcConfig.from_mapping({"keep_alive_s": 60}).keep_alive_s == 60
    assert model.HcConfig().keep_alive_s == 0


def test_central_boiler_keep_alive():
    relay = AutoOffRelay()
    coord = SimpleNamespace(hass=relay, conf={cc.CONF_BOILER: "switch.boiler"},
                            keep_alive=executor_mod.KeepAlive(60))
    for k in range(80):  # 40 minutes on
        relay.now = T0 + timedelta(seconds=30 * k)
        if k:
            assert relay._get("switch.boiler").state == "on"
        asyncio.run(cc.CentralCoordinator._switch(coord, True, relay.now))
    assert central.CentralConfig(central_keep_alive_s=60).central_keep_alive_s == 60


def test_keep_alive_tolerates_steps_a_little_early():
    ka = executor_mod.KeepAlive(60)
    ka.sent(T0)
    assert ka.due(T0 + timedelta(seconds=59, microseconds=990000))  # step drift: still this step, not the next
    assert not ka.due(T0 + timedelta(seconds=30))

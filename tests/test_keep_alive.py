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


class Gen1Relay(AutoOffRelay):
    """A Shelly gen1 as measured on 2026-11-08/09: an "on" to a relay that is already on does NOT restart its
    auto-off timer – only a "turn on with timer" (the watchdog script, here domain "script") does."""

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((self.now, domain, service))
        if domain == "script":
            self.on, self.last_on = True, self.now  # /relay/0?turn=on&timer=900: on, timer restarted
        elif service == "turn_on":
            if not self.on:
                self.on, self.last_on = True, self.now
        else:
            self.on = False


def test_gen1_relay_cuts_a_long_burn_even_with_keep_alive():
    relay = Gen1Relay()
    ex = executor_mod.Executor(relay, "active", "switch.boiler", None, keep_alive_s=60)
    assert _run(ex, relay, 40) > 0  # the 15-minute cut seen live (11-08 16:58, 11-09 05:45 and 06:00)


def test_watchdog_script_keeps_a_long_burn_and_rearms_the_timer():
    relay = Gen1Relay()
    ex = executor_mod.Executor(relay, "active", "switch.boiler", None, keep_alive_s=60, keep_script="script.rearm")
    assert _run(ex, relay, 40) == 0  # 40 minutes on, never cut
    scripts = [c for c in relay.calls if c[1] == "script"]
    assert len(scripts) >= 39  # about once a minute
    assert sum(1 for c in relay.calls if c[2] == "turn_on" and c[1] != "script") == 1  # the relay itself: once


def test_dead_home_assistant_still_switches_off_by_the_device():
    relay = Gen1Relay()
    ex = executor_mod.Executor(relay, "active", "switch.boiler", None, keep_alive_s=60, keep_script="script.rearm")
    _run(ex, relay, 10)
    relay.now = relay.now + timedelta(minutes=16)  # Home Assistant stopped: nobody re-arms
    assert relay._get("switch.boiler").state == "off"


def test_off_does_not_run_the_script():
    relay = Gen1Relay()
    ex = executor_mod.Executor(relay, "active", "switch.boiler", None, keep_alive_s=60, keep_script="script.rearm")
    _run(ex, relay, 5, output=False)
    assert not [c for c in relay.calls if c[1] == "script"]

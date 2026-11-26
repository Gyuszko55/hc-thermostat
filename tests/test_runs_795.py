"""0.79.5: "starts today" counts heating runs. With a relay: each time it switches on (on the event, so a short one is
not missed); a flame also lights for hot water and relights within a run. Without a relay: the heating signal's
starts, but not while hot water is made. (A user's count: 25 relay runs, the counter showed 32 of 42 flame lights.)"""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core import measures as ms  # noqa: E402

T0 = datetime(2026, 11, 25, 6, 0, tzinfo=timezone.utc)


def test_the_counter_counts_runs_given_to_it():
    r = ms.RunCounter()
    for m in range(0, 60, 5):  # a flame flickering in the ticks: not counted when the starts come from the relay
        r.update(T0 + timedelta(minutes=m), m % 10 == 0, count_starts=False)
    assert r.summary(T0 + timedelta(hours=1))["starts_today"] == 0
    assert r.summary(T0 + timedelta(hours=1))["hours_today"] > 0  # the run time is still kept
    r.start(T0 + timedelta(minutes=3))
    r.start(T0 + timedelta(minutes=40))
    s = r.summary(T0 + timedelta(hours=1))
    assert (s["starts_today"], s["starts_24h"], s["starts_last_hour"]) == (2, 2, 2)
    r2 = ms.RunCounter()
    r2.update(T0, False)
    r2.update(T0 + timedelta(minutes=1), True)
    assert r2.summary(T0 + timedelta(minutes=2))["starts_today"] == 1  # the old way, without the count_starts flag


def _coord(conf, states=None):
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    c = object.__new__(coord_mod.HcCoordinator)
    states = states or {}
    c.hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: states.get(e)))
    c.conf, c.runs = conf, ms.RunCounter()
    return coord_mod, c


def test_the_relay_is_the_run(monkeypatch):
    pytest.importorskip("homeassistant")
    coord_mod, c = _coord({"actuator_entity": "switch.boiler", "flame_entity": "binary_sensor.flame"})
    assert c._run_entity() == "switch.boiler"
    assert _coord({"actuator_entity": "climate.trv"})[1]._run_entity() is None
    assert _coord({"flame_entity": "binary_sensor.flame"})[1]._run_entity() is None
    seen = {}
    monkeypatch.setattr(coord_mod, "async_track_state_change_event",
                        lambda hass, ids, cb: seen.update(ids=ids, cb=cb) or (lambda: None))
    c.async_track_runs()
    assert seen["ids"] == ["switch.boiler"]
    ev = lambda old, new: SimpleNamespace(data={"old_state": old and SimpleNamespace(state=old),  # noqa: E731
                                                "new_state": new and SimpleNamespace(state=new)})
    for old, new in (("off", "on"), ("on", "off"), ("unavailable", "on"), ("off", "on"), (None, "on"), ("on", "on")):
        seen["cb"](ev(old, new))
    assert sum(d["starts"] for d in c.runs.days.values()) == 2


def test_no_relay_no_hot_water_starts():
    src = (ROOT / "coordinator.py").read_text("utf-8")
    assert "count_starts=self._run_entity() is None" in src and 'dhw.state == "on"' in src
    assert "coordinator.async_track_runs()" in (ROOT / "__init__.py").read_text("utf-8")

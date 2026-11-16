"""0.51.1 – lessons from Better Thermostat 2.0 and Smart Thermostat 2026.11:
a renamed entity is followed, "nan" / "inf" is no reading, a lasting problem is a Repairs entry (with
degraded_since), and the PID integral is kept over a short off."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.model import HcConfig
from core.regulators import PidRegulator
from rename import renamed, replace_id
from units import finite, to_c

T0 = datetime(2026, 11, 15, 6, 0, tzinfo=timezone.utc)


# --- 1. a renamed entity ---------------------------------------------------------------------------------------
def test_replace_id_everywhere_but_only_exact():
    value = {"indoor": "sensor.t", "windows": ["binary_sensor.w", "sensor.t"], "rooms": [
        {"name": "Nappali", "thermometers": ["sensor.t"], "trvs": ("climate.h",)}], "sensor.t": 1,
        "other": "sensor.t_humidity", "n": 3}
    out = replace_id(value, "sensor.t", "sensor.new")
    assert out["indoor"] == "sensor.new" and out["windows"] == ["binary_sensor.w", "sensor.new"]
    assert out["rooms"][0]["thermometers"] == ["sensor.new"] and out["rooms"][0]["trvs"] == ("climate.h",)
    assert "sensor.new" in out and "sensor.t" not in out
    assert out["other"] == "sensor.t_humidity" and out["n"] == 3  # a prefix is not the entity


def test_renamed_says_when_nothing_changes():
    assert renamed({"indoor": "sensor.a"}, {"windows": []}, "sensor.x", "sensor.y") is None
    data, options = renamed({"indoor": "sensor.a"}, {"windows": ["sensor.a"]}, "sensor.a", "sensor.b")
    assert data == {"indoor": "sensor.b"} and options == {"windows": ["sensor.b"]}


# --- 2. "nan" / "inf" ----------------------------------------------------------------------------------------
def test_nan_and_inf_are_no_reading():
    for bad in ("nan", "NaN", "inf", "-inf", float("nan")):
        assert finite(bad) is None
        assert to_c(bad, "°C") is None
    assert finite("21.5") == 21.5 and finite("unknown") is None and finite(None) is None
    assert to_c("21.5", "°C") == 21.5


# --- 3. the Repairs entry ------------------------------------------------------------------------------------
def _module():
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from custom_components.hc_thermostat import coordinator
    return coordinator


def _coordinator(problems, language="hu"):
    states = {"sensor.t": SimpleNamespace(attributes={"friendly_name": "Nappali hőmérő"})}
    return SimpleNamespace(
        sensor_problems=problems, degraded_since=None,
        hass=SimpleNamespace(config=SimpleNamespace(language=language), states=SimpleNamespace(get=states.get)),
        config_entry=SimpleNamespace(entry_id="e511", title="Boiler HC"))


def test_a_lasting_problem_is_a_repairs_entry_that_clears_itself(monkeypatch):
    mod = _module()
    calls = []
    monkeypatch.setattr(mod.ir, "async_create_issue", lambda hass, domain, issue_id, **kw: calls.append(("create", issue_id, kw)))
    monkeypatch.setattr(mod.ir, "async_delete_issue", lambda hass, domain, issue_id: calls.append(("delete", issue_id)))
    c = _coordinator({})
    mod.HcCoordinator._sync_repair(c, T0)
    assert calls == [] and c.degraded_since is None  # all well from the start: nothing to do
    c.sensor_problems = {"sensor.t": "lost"}
    mod.HcCoordinator._sync_repair(c, T0)
    assert calls[-1][0] == "create" and calls[-1][1] == "sensor_problem_e511"
    kw = calls[-1][2]
    assert kw["translation_key"] == "sensor_problem" and kw["translation_placeholders"]["name"] == "Boiler HC"
    assert "Nappali hőmérő (sensor.t): nem elérhető" in kw["translation_placeholders"]["problems"]
    assert c.degraded_since == T0
    mod.HcCoordinator._sync_repair(c, T0 + timedelta(minutes=1))
    assert len(calls) == 1 and c.degraded_since == T0  # unchanged: not created again, the start is kept
    c.sensor_problems = {}
    mod.HcCoordinator._sync_repair(c, T0 + timedelta(minutes=2))
    assert calls[-1] == ("delete", "sensor_problem_e511") and c.degraded_since is None


def test_the_repairs_entry_never_stops_the_decision(monkeypatch):
    mod = _module()

    def boom(*a, **k):
        raise RuntimeError("no registry")
    monkeypatch.setattr(mod.ir, "async_create_issue", boom)
    c = _coordinator({"hc_supervisor": "internal_error"}, language="en")
    mod.HcCoordinator._sync_repair(c, T0)  # does not raise
    assert c.degraded_since == T0


# --- 4. the integral over a short off ------------------------------------------------------------------------
def test_the_pid_integral_is_kept_over_a_short_off():
    reg = PidRegulator(HcConfig(control="pid"))
    for i in range(20):
        reg.update(21.0, 20.0, 5.0, T0 + timedelta(minutes=i))
    learned = reg.integral
    assert learned > 0
    reg.hold(T0 + timedelta(minutes=25))  # off (or a window) for a while
    assert reg.integral == learned
    reg.update(21.0, 20.0, 5.0, T0 + timedelta(minutes=26))
    assert reg.integral >= learned  # not thrown away when the heat is back
    state = reg.state()
    again = PidRegulator(HcConfig(control="pid"))
    again.restore(state)
    assert again.integral == reg.integral  # and over a restart


def test_the_pause_switch_opts_in_to_an_in_place_rename():
    """HA 2026.11: an entity with its own async_added_to_hass but no async_entity_id_changed is removed and added
    again on a rename (until 2027.11); the pause switch keys nothing on its id, so it opts in."""
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from custom_components.hc_thermostat.switch import HcSupervisionPaused
    assert "async_entity_id_changed" in HcSupervisionPaused.__dict__
    assert HcSupervisionPaused.async_entity_id_changed(SimpleNamespace(), "switch.old") is None


def test_version():
    root = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
    assert json.loads((root / "manifest.json").read_text())["version"] in ("0.51.1", "0.51.2", "0.52.0", "0.52.1", "0.53.0", "0.54.0", "0.55.0", "0.56.0", "0.56.1", "0.57.0", "0.57.1")
    for lang in ("hu", "en"):
        issue = json.loads((root / "translations" / f"{lang}.json").read_text())["issues"]["sensor_problem"]
        assert "{name}" in issue["title"] and "{problems}" in issue["description"]

"""0.78.0: the core reads raw states without Home Assistant (core/inputs.py), and the core is a package of its own."""

import ast
import importlib
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import inputs as in_
from core.model import Reading

T0 = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)
CORE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat" / "core"


def at(s):
    return T0 + timedelta(seconds=s)


def test_to_c_matches_home_assistant():
    units = importlib.import_module("hc_thermostat.units") if "hc_thermostat" in sys.modules else None
    if units is None:
        sys.path.insert(0, str(CORE.parents[1]))
        units = importlib.import_module("hc_thermostat.units")
    for value in (-40, -3.5, 0, 21.7, 72.5, 100, "68", "nan", "inf", None, "x"):
        for unit in ("°C", "°F", "F", "℉", "K", "%", None, "W"):
            a, b = in_.to_c(value, unit), units.to_c(value, unit)
            assert (a is None and b is None) or math.isclose(a, b, abs_tol=1e-9), (value, unit, a, b)


def test_value_and_reading_from_a_sample_table():
    t = in_.SampleTable()
    t.put("sensor.room", "71.6", at(0), {"unit_of_measurement": "°F"})
    t.put("weather.home", "rainy", at(0), {"temperature": 4.0, "temperature_unit": "°C"})
    t.put("sensor.dead", "unavailable", at(0))
    assert in_.reading(t, "sensor.room", at(90)) == Reading(pytest.approx(22.0), 90.0)
    assert in_.reading(t, "weather.home", at(0)).value == 4.0
    assert in_.reading(t, "sensor.dead", at(0)) == Reading()
    assert in_.reading(t, "sensor.none", at(0)) == Reading() and in_.reading(t, None, at(0)) == Reading()


def test_home_assistant_state_is_a_sample():
    # a Home Assistant State has the same four fields – the integration passes hass.states as it is
    state = SimpleNamespace(entity_id="sensor.x", state="20.5", attributes={"unit_of_measurement": "°C"},
                            last_reported=at(0))
    view = SimpleNamespace(get=lambda e: state if e == "sensor.x" else None)
    assert in_.reading(view, "sensor.x", at(30)) == Reading(20.5, 30.0)


def test_switches_and_contacts():
    t = in_.SampleTable()
    t.put("binary_sensor.w1", "off", at(0))
    t.put("binary_sensor.w2", "on", at(0))
    t.put("binary_sensor.w3", "unavailable", at(0))
    assert in_.any_on(t, ["binary_sensor.w1", "binary_sensor.w2"])
    assert not in_.any_on(t, ["binary_sensor.w1", "binary_sensor.w3", "binary_sensor.gone"]) and not in_.any_on(t, None)
    assert in_.switch_on(t, "binary_sensor.w2") is True and in_.switch_on(t, "binary_sensor.w1") is False
    assert in_.switch_on(t, "binary_sensor.w3") is None and in_.switch_on(t, None) is None


def test_group_reading_uses_fresh_ones_only():
    t = in_.SampleTable()
    t.put("sensor.a", "22.0", at(0))
    t.put("sensor.b", "23.0", at(500))
    t.put("sensor.old", "10.0", at(-99999))
    r = in_.group_reading(t, ["sensor.a", "sensor.b", "sensor.old", "sensor.none"], at(600), 3600)
    assert r == Reading(22.5, 100.0)
    assert in_.group_reading(t, ["sensor.old"], at(600), 3600) is None


def test_restart_confirm():
    t = in_.SampleTable()
    c = in_.RestartConfirm(T0, 900)
    assert not c.check(t, ["sensor.a", None], at(10))  # nothing yet
    t.put("sensor.a", "21.6", at(15))  # the restored value
    assert not c.check(t, ["sensor.a"], at(20))
    t.put("sensor.a", "21.6", at(200))  # a real report, the same value
    assert c.check(t, ["sensor.a"], at(210)) and c.confirmed
    assert in_.RestartConfirm(T0, 900).check(t, [], at(900))  # the wait is over


def test_outdoor_average_keeps_its_old_behaviour():
    avg = in_.OutdoorAverage()
    out = [avg.update(5.0 + i, at(i * 600)) for i in range(6)]
    assert out[:5] == [None] * 5 and out[5] == pytest.approx(7.5)
    assert avg.update(100.0, at(5 * 600 + 60)) == pytest.approx(7.5)  # within 10 minutes: not taken
    assert avg.update(None, at(7 * 600)) == pytest.approx(7.5)
    restored = in_.OutdoorAverage(avg.state())
    assert restored.state() == avg.state()
    assert restored.update(None, at(6 * 600 + 86400)) is None  # all older than 24 hours


def test_core_is_self_contained():
    """Every core module imports only the standard library and its own siblings – so it runs as `hc_core` too."""
    stdlib = set(sys.stdlib_module_names)
    for path in CORE.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] in stdlib, (path.name, alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    assert node.module.split(".")[0] in stdlib | {"__future__"}, (path.name, node.module)
                else:
                    assert node.level == 1, (path.name, node.module)  # never reaches out of the package


def test_core_imports_as_hc_core():
    saved = {n: m for n, m in sys.modules.items() if n == "hc_core" or n.startswith("hc_core.")}
    for name in saved:
        del sys.modules[name]
    spec = importlib.util.spec_from_file_location("hc_core", CORE / "__init__.py", submodule_search_locations=[str(CORE)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules["hc_core"] = pkg
    try:
        spec.loader.exec_module(pkg)
        sup = importlib.import_module("hc_core.supervisor")
        model = importlib.import_module("hc_core.model")
        d = sup.Supervisor(model.HcConfig()).step(model.Inputs(now=T0, indoor=model.Reading(20.0), outdoor=model.Reading(5.0)))
        assert d.reason is not None
        assert pkg.__version__ == __import__("json").loads((CORE.parent / "manifest.json").read_text())["version"]
    finally:
        for name in [n for n in sys.modules if n == "hc_core" or n.startswith("hc_core.")]:
            del sys.modules[name]
        sys.modules.update(saved)


# --- 0.78.1: the device's own "last seen" time, and the settle time after a start ------------------------------------
def test_seen_time_ages_the_reading():
    t = in_.SampleTable()
    # Zigbee2MQTT re-sent a cached value just now, but the device was last heard 2 hours ago
    t.put("sensor.th", "26.35", at(0), {"unit_of_measurement": "°C"}, seen=at(-7200))
    assert in_.reading(t, "sensor.th", at(0)) == Reading(26.35, 7200.0)
    assert in_.reported_at(t.get("sensor.th")) == at(-7200)
    t.put("sensor.plain", "20", at(-30))
    assert in_.reported_at(t.get("sensor.plain")) == at(-30)


def test_restart_confirm_ignores_the_first_minutes():
    # 11-19 21:11: the restored H&T value was written twice, ms apart – that confirmed the reading too early
    t = in_.SampleTable()
    c = in_.RestartConfirm(T0, 900, settle_s=180)
    t.put("sensor.ht", "22.6", at(2))
    assert not c.check(t, ["sensor.ht"], at(2))
    t.put("sensor.ht", "22.6", at(2.01))  # the second restore write
    assert not c.check(t, ["sensor.ht"], at(60))
    t.put("sensor.ht", "22.6", at(91))  # a bridge re-sending its cache
    assert not c.check(t, ["sensor.ht"], at(150))
    t.put("sensor.ht", "22.7", at(463))  # the H&T woke and reported
    assert c.check(t, ["sensor.ht"], at(470))


def test_restart_confirm_with_seen_time():
    t = in_.SampleTable()
    c = in_.RestartConfirm(T0, 900, settle_s=180)
    t.put("sensor.th", "22.1", at(91), seen=at(-600))  # re-sent cache: the device spoke before the start
    assert not c.check(t, ["sensor.th"], at(100))
    t.put("sensor.th", "22.1", at(95), seen=at(95))  # the device itself spoke after the start: confirmed at once
    assert c.check(t, ["sensor.th"], at(100))


def test_seen_view_links_a_last_seen_sibling():
    seen_view = importlib.import_module("hc_thermostat.seen_view")
    st = lambda e, v, rep: SimpleNamespace(entity_id=e, state=v, attributes={}, last_reported=rep)
    states = {"sensor.th_temperature": st("sensor.th_temperature", "22.1", at(0)),
              "sensor.th_last_seen": st("sensor.th_last_seen", "2026-11-19T11:00:00+00:00", at(0))}
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    view = seen_view.SeenView(hass)
    view._links["sensor.th_temperature"] = ("sensor.th_last_seen", datetime.now(timezone.utc))
    s = view.get("sensor.th_temperature")
    assert s.seen == datetime(2026, 11, 19, 11, 0, tzinfo=timezone.utc) and s.state == "22.1"
    assert in_.reading(view, "sensor.th_temperature", at(0)).age_s == 3600.0
    states["sensor.th_last_seen"] = st("sensor.th_last_seen", "unavailable", at(0))
    assert getattr(view.get("sensor.th_temperature"), "seen", None) is None  # no time: the plain state
    assert view.get("sensor.none") is None
    # without a registry (a bare hass) nothing is linked
    assert seen_view.SeenView(hass).get("sensor.th_temperature") is states["sensor.th_temperature"]

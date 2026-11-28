"""0.66.0: a heat source problem goes to Repairs (and a notification blueprint comes with HC), diagnostics can be
downloaded, the targets and the night have a short menu item of their own, the mode is changed only in the menu, and
the everyday-irrelevant sensors are diagnostic."""

import asyncio
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "hc_thermostat"


def _coordinator_with(state):
    from hc_thermostat import coordinator as co
    calls = []
    fake_ir = SimpleNamespace(
        async_create_issue=lambda hass, dom, iid, **kw: calls.append(("create", iid, kw)),
        async_delete_issue=lambda hass, dom, iid: calls.append(("delete", iid)),
        IssueSeverity=SimpleNamespace(ERROR="error", WARNING="warning"))
    c = object.__new__(co.HcCoordinator) if hasattr(co, "HcCoordinator") else None
    return co, c, calls, fake_ir


def test_source_problem_goes_to_repairs_after_five_minutes(monkeypatch):
    from hc_thermostat import coordinator as co
    cls = next(v for v in vars(co).values() if isinstance(v, type) and hasattr(v, "_sync_source_repair"))
    calls = []
    monkeypatch.setattr(co.ir, "async_create_issue", lambda hass, dom, iid, **kw: calls.append(("create", iid, kw)))
    monkeypatch.setattr(co.ir, "async_delete_issue", lambda hass, dom, iid: calls.append(("delete", iid)))
    c = object.__new__(cls)
    c.hass = SimpleNamespace(config=SimpleNamespace(language="hu"))
    c.config_entry = SimpleNamespace(entry_id="e1", title="Kazán")
    c.health = SimpleNamespace(state="no_flame")
    t0 = datetime(2026, 11, 16, 21, 0)
    c._sync_source_repair(t0)
    c._sync_source_repair(t0 + timedelta(minutes=4))
    assert not [x for x in calls if x[0] == "create"]
    c._sync_source_repair(t0 + timedelta(minutes=5))
    kind, iid, kw = calls[-1]
    assert kind == "create" and iid == "source_problem_e1" and kw["severity"] == co.ir.IssueSeverity.ERROR
    assert "nem gyújt be" in kw["translation_placeholders"]["problem"] and kw["translation_placeholders"]["since"] == "21:00"
    n = len(calls)
    c._sync_source_repair(t0 + timedelta(minutes=6))
    assert len(calls) == n  # not created again
    c.health.state = "ok"
    c._sync_source_repair(t0 + timedelta(minutes=7))
    assert calls[-1] == ("delete", "source_problem_e1")
    c.health.state = "learning"  # a quiet state is no problem
    c._sync_source_repair(t0 + timedelta(minutes=20))
    assert calls[-1] == ("delete", "source_problem_e1")


def test_repairs_texts_and_blueprint():
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        issue = tr["issues"]["source_problem"]
        assert "{name}" in issue["title"] and "{problem}" in issue["description"] and "{since}" in issue["description"]
    bp = (ROOT / "blueprints" / "automation" / "hc_thermostat" / "hc_problem_notify.yaml").read_text()
    assert "integration: hc_thermostat" in bp and "integration: mobile_app" in bp and "type: notify" in bp
    assert "state_attr(trigger.entity_id, 'health')" in bp


def test_diagnostics_redacts_the_house_name():
    from hc_thermostat import diagnostics as dg
    assert "home_name" in dg.TO_REDACT
    entry = SimpleNamespace(title="X", data={"home_name": "Családi ház", "indoor_entity": "sensor.t"}, options={"home_name": "Y"})
    out = asyncio.run(dg.async_get_config_entry_diagnostics(SimpleNamespace(), entry))
    assert out["data"]["home_name"] == "**REDACTED**" and out["data"]["indoor_entity"] == "sensor.t"
    assert out["options"]["home_name"] == "**REDACTED**"
    assert "diagnostics" in json.loads((BASE / "manifest.json").read_text())["after_dependencies"]


def test_targets_menu_and_mode_only_in_the_menu():
    src = (BASE / "config_flow.py").read_text()
    assert 'menu = ["targets", "presets", "check", "sensors"]' in src and "async def async_step_targets" in src  # 0.86.0: by task
    assert "user_input[CONF_MODE] = current.get(CONF_MODE, MODE_SHADOW)  # 0.66.0" in src
    for lang in ("hu", "en"):
        st = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]["step"]
        assert st["init"]["menu_options"]["targets"]
        assert set(st["targets"]["data"]) == {"target_home", "target_night", "target_away", "target_vacation", "frost_temp",
                                              "night_start", "night_end", "night_start_weekend", "night_end_weekend"}  # 0.67.0


def test_diagnostic_sensors():
    src = (BASE / "sensor.py").read_text()
    assert src.count("self._attr_entity_category = EntityCategory.DIAGNOSTIC") == 5
    assert "self._attr_entity_registry_enabled_default = any(conf.get(k)" in src
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3", "0.82.4", "0.82.5", "0.82.6", "0.82.7", "0.83.0", "0.84.0", "0.85.0", "0.86.0", "0.87.0", "0.87.1", "0.88.0", "0.89.0")

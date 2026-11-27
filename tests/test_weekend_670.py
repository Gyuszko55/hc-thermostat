"""0.67.0: a weekend night (the nights ending on Saturday and Sunday morning), and the fine-tuning sections only in
the user's Advanced mode – their values kept when the settings are saved."""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from hc_thermostat.core import schedule as sc  # noqa: E402

TZ = timezone(timedelta(hours=1))
FRI = datetime(2026, 11, 20, 12, 0, tzinfo=TZ)  # a Friday


def at(day_offset, h, m=0):
    return (FRI + timedelta(days=day_offset)).replace(hour=h, minute=m)


def test_without_weekend_times_as_before():
    for now in (at(0, 21, 59), at(0, 22, 0), at(1, 5, 59), at(1, 6, 0), at(2, 3, 0)):
        old = now.time() >= datetime(1, 1, 1, 22).time() or now.time() < datetime(1, 1, 1, 6).time()
        assert sc.is_night(now, "22:00", "06:00") == old
    assert sc.next_boundary(at(0, 12), "22:00:00", "06:00:00") == at(0, 22)
    assert sc.night_end_at(at(0, 23), "22:00", "06:00") == at(1, 6)
    assert not sc.is_night(at(0, 23), "22:00", "22:00") and sc.next_boundary(at(0, 23), "22:00", "22:00") is None


def test_weekend_night_friday_and_saturday_evenings():
    n = ("22:00", "06:00", "23:30", "08:00")
    assert not sc.is_night(at(0, 22, 30), *n)  # Friday evening: the weekend night starts at 23:30
    assert sc.is_night(at(0, 23, 30), *n)
    assert sc.is_night(at(1, 7, 0), *n) and not sc.is_night(at(1, 8, 0), *n)  # Saturday morning until 08:00
    assert sc.night_end_at(at(0, 23, 45), *n) == at(1, 8)
    assert sc.is_night(at(2, 7, 30), *n)  # Sunday morning
    assert sc.is_night(at(2, 22, 15), *n)  # Sunday evening: the weekday night (it ends on Monday)
    assert not sc.is_night(at(3, 6, 30), *n)  # Monday 06:30
    assert sc.next_boundary(at(0, 12), *n) == at(0, 23, 30)
    assert sc.next_boundary(at(1, 9), *n) == at(1, 23, 30)
    assert sc.next_boundary(at(2, 9), *n) == at(2, 22)


def test_only_one_weekend_time_is_ignored_and_refused_in_the_form():
    assert sc.is_night(at(0, 22, 30), "22:00", "06:00", "23:30", None)
    from hc_thermostat import config_flow as cf
    assert cf._weekend_errors({"night_start_weekend": "23:30:00"}) == {"night_end_weekend": "weekend_both"}
    assert cf._weekend_errors({}) == {} and cf._weekend_errors({"night_start_weekend": "23:30", "night_end_weekend": "08:00"}) == {}


def test_supervisor_uses_the_weekend_night():
    from hc_thermostat.core.model import HcConfig
    from hc_thermostat.core.supervisor import Supervisor
    sup = Supervisor(HcConfig(night_start="22:00", night_end="06:00", night_start_weekend="23:30", night_end_weekend="08:00"))
    assert not sup._is_night(at(0, 22, 30)) and sup._is_night(at(1, 7, 30))
    assert sup._night_end_at(at(1, 1)) == at(1, 8)
    plain = Supervisor(HcConfig(night_start="22:00", night_end="06:00"))
    assert plain._is_night(at(0, 22, 30)) and not plain._is_night(at(1, 7, 30))


def test_fine_tuning_only_in_advanced_mode_and_kept():
    from hc_thermostat import config_flow as cf
    assert set(cf.ADVANCED_SECTIONS) == {"regulation", "energy", "adjoining", "house", "measures"}
    assert cf._advanced(SimpleNamespace(context={})) and not cf._advanced(SimpleNamespace(context={"show_advanced_options": False}))
    src = (BASE / "config_flow.py").read_text()
    assert 'user_input = {**getattr(self, "_hidden", {}), **user_input}  # 0.67.0' in src
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]
        assert "{advanced}" in tr["step"]["settings"]["description"]
        for step in ("targets", "settings"):
            assert tr["step"][step]["data"]["night_start_weekend"] and tr["step"][step]["data_description"]["night_end_weekend"]
        assert tr["error"]["weekend_both"]
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3", "0.82.4", "0.82.5")


def test_without_advanced_mode_the_hidden_values_survive_a_save():
    from hc_thermostat import config_flow as cf
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data={"role": "standalone", "control": "tpi", "heat_source": "onoff_boiler",
                                  "system": "radiator_single", "indoor_entity": "sensor.nappali"},
                            options={"mode": "active", "cycle_s": 2400, "min_on_s": 420, "energy_factor": 8.55,
                                     "pre_change_max_s": 3600.0},
                            title="Kazán", entry_id="e1")
    type(flow).config_entry = property(lambda self: entry)
    flow.context = {"show_advanced_options": False}
    flow.async_show_form = lambda **kw: ("form", kw)
    kind, kw = asyncio.run(flow.async_step_settings())
    keys = [str(k) for k in kw["data_schema"].schema]
    assert not set(keys) & set(cf.ADVANCED_SECTIONS) and "functions" in keys and "protection" in keys
    assert "Haladó" in kw["description_placeholders"]["advanced"] or "Advanced" in kw["description_placeholders"]["advanced"]
    flow.async_step_presets = lambda: asyncio.sleep(0, result=("presets", flow._settings))
    kind, saved = asyncio.run(flow.async_step_settings({"target_home": 21.5, "functions": {"boost_enabled": True}}))
    assert kind == "presets"
    assert saved["cycle_s"] == 2400 and saved["min_on_s"] == 420 and saved["pre_change_max_s"] == 3600.0
    assert saved["target_home"] == 21.5 and saved["mode"] == "active"
    flow.context = {"show_advanced_options": True}
    kind, kw = asyncio.run(flow.async_step_settings())
    assert "regulation" in [str(k) for k in kw["data_schema"].schema] and kw["description_placeholders"]["advanced"] == ""

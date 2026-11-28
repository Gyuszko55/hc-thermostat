"""0.88.0: what a save changes (core/settings_diff.py)."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "hc_thermostat"))

from core.model import HcConfig  # noqa: E402
from core.settings_diff import as_markdown, changes, defaults_of, label_map, lines  # noqa: E402


def test_only_real_changes_count():
    d = defaults_of(HcConfig)
    before = {"mode": "shadow", "target_comfort": 21.0, "indoor_entity": "sensor.a", "outdoor_entity": None}
    after = {"mode": "active", "target_comfort": 21.5, "indoor_entity": "sensor.a", "outdoor_entity": "",
             "target_eco": d["target_eco"]}  # a form saving a default it did not store before changes nothing
    assert changes(before, after, defaults=d) == ["target_comfort"]  # the mode is left out on purpose
    assert changes({"x": 1}, {"x": 1.0}) == [] and changes({"p": ("a", "b")}, {"p": ["a", "b"]}) == []
    assert changes({"_internal": 1}, {"_internal": 2}) == []


def test_the_lines_in_plain_words():
    before = {"target_comfort": 21.0, "presets_enabled": ["eco"], "window_drop": True, "outdoor_entity": None,
              "rooms": [{"key": "a"}], "guard_token": "abc"}
    after = {"target_comfort": 21.5, "presets_enabled": ["eco", "away"], "window_drop": False,
             "outdoor_entity": "sensor.kint", "rooms": [{"key": "b"}], "guard_token": "xyz"}
    rows = lines(before, after, "hu", {"target_comfort": "Komfort cél"}, {"sensor.kint": "Kinti hőmérő"})
    assert "Komfort cél: 21 → 21,5" in rows
    assert "outdoor_entity: nincs → Kinti hőmérő" in rows and "window_drop: be → ki" in rows
    assert "presets_enabled: eco → eco, away" in rows and "rooms: megváltozott" in rows
    assert "guard_token: megváltozott" in rows and not any("xyz" in r or "abc" in r for r in rows)  # never shown
    assert as_markdown([], "hu") == "Nincs változás."
    many = as_markdown([f"k{i}" for i in range(25)], "en")
    assert many.count("\n- ") == 20 and many.endswith("and 5 more settings")


def test_labels_from_the_translations():
    tr = {"component.hc_thermostat.options.step.targets.data.target_comfort": "Komfort cél",
          "component.hc_thermostat.options.step.settings.sections.regulation.data.kp": "Arányos tag",
          "component.hc_thermostat.config.step.entities.data.target_comfort": "másik",
          "component.hc_thermostat.config.step.entities.data.indoor_entity": "Benti hőmérő\nmásodik sor",
          "component.other.options.step.x.data.y": "nem ez"}
    assert label_map(tr, "hc_thermostat") == {"target_comfort": "Komfort cél", "kp": "Arányos tag",
                                              "indoor_entity": "Benti hőmérő"}

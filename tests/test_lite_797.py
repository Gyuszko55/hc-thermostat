"""0.79.7: HC Lite – preheat: the day target starts early by the room's shortfall."""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
lite = importlib.import_module("hc_thermostat.core.lite")
BASE = ROOT / "custom_components" / "hc_thermostat"
SCRIPT = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")


def test_preheat_settings_are_cleaned_and_sent():
    s = lite.LiteSettings()
    assert (s.pre, s.pre_max) == (30, 120)
    s = lite.LiteSettings.from_conf({"lite_pre": 0, "lite_pre_max": 500})
    assert (s.pre, s.pre_max) == (0, 120)
    p = lite.settings_payload(lite.LiteSettings.from_conf({"lite_pre": 45.0, "lite_pre_max": 90}))
    assert (p["pre"], p["pre_max"]) == (45, 90)


def test_the_script_knows_preheat_and_the_words_exist():
    assert "function preheat(L, v)" in SCRIPT and 'st.period = "preheat"' in SCRIPT
    for lang in ("en", "hu"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text("utf-8"))
        for sec in ("config", "options"):
            step = tr[sec]["step"]["lite_settings"]
            for k in ("lite_pre", "lite_pre_max"):
                assert step["data"][k] and step["data_description"][k]
                assert "{" not in step["data_description"][k]

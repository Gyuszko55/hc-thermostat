"""0.79.8: HC Lite – boost: far below the target it heats without a break."""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
lite = importlib.import_module("hc_thermostat.core.lite")
BASE = ROOT / "custom_components" / "hc_thermostat"
SCRIPT = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")


def test_boost_settings_are_cleaned_and_sent():
    s = lite.LiteSettings()
    assert (s.boost, s.boost_end) == (1.0, 0.3)
    s = lite.LiteSettings.from_conf({"lite_boost": 0, "lite_boost_end": 9})
    assert (s.boost, s.boost_end) == (0.0, 0.3)
    p = lite.settings_payload(lite.LiteSettings.from_conf({"lite_boost": 1.5, "lite_boost_end": 0.2}))
    assert (p["boost"], p["boost_end"]) == (1.5, 0.2)


def test_the_script_knows_boost_and_the_words_exist():
    assert 'want(true, t, "boost")' in SCRIPT and "boost: st.boost" in SCRIPT
    for lang in ("en", "hu"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text("utf-8"))
        for sec in ("config", "options"):
            step = tr[sec]["step"]["lite_settings"]
            for k in ("lite_boost", "lite_boost_end"):
                assert step["data"][k] and step["data_description"][k]
                assert "{" not in step["data_description"][k]

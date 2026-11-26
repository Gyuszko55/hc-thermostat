"""0.79.4: HC Lite PI mode – a third control choice, its integral time, the integral in the status and on the dial card."""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

lite = importlib.import_module("hc_thermostat.core.lite")
BASE = ROOT / "custom_components" / "hc_thermostat"


def test_three_control_modes():
    assert lite.CTL == ("hyst", "tpi", "pid")
    s = lite.LiteSettings.from_conf({"lite_ctl": "pid", "lite_ti": 7200})
    assert (s.ctl, s.ti) == ("pid", 7200)
    assert lite.LiteSettings.from_conf({"lite_ti": 60}).ti == 14400  # out of range: the default
    assert lite.settings_payload(s)["ti"] == 7200


def test_the_integral_reads():
    v = lite.view({"mode": "auto", "integral": 0.12, "demand": 0.5})
    assert v.integral == 0.12
    assert lite.view({"mode": "auto"}).integral is None


def test_words_and_the_card():
    for lang in ("en", "hu"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text("utf-8"))
        assert set(tr["selector"]["lite_ctl"]["options"]) == {"hyst", "tpi", "pid"}
        for sec in ("config", "options"):
            st = tr[sec]["step"]["lite_settings"]
            assert st["data"]["lite_ti"] and st["data_description"]["lite_ti"]
    card_file = ROOT / "frontend" / "hc-dial-card.js"  # the card lives in its own repository; not in every tree
    if card_file.exists():
        assert '"LITE·PID"' in card_file.read_text("utf-8")
    assert '"integral": v.integral' in (BASE / "lite.py").read_text("utf-8")

"""0.79.6: HC Lite – a Wi-Fi H&T pushes its reading to the relay (sensor "push")."""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
lite = importlib.import_module("hc_thermostat.core.lite")
BASE = ROOT / "custom_components" / "hc_thermostat"
SCRIPT = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")


def test_push_is_a_sensor_choice():
    s = lite.LiteSettings.from_conf({"lite_sensor": "push", "lite_sensor_max_age": 7200})
    assert (s.sensor, s.sensor_max_age) == ("push", 7200)
    assert lite.LiteSettings.from_conf({"lite_sensor": "wifi"}).sensor == "bthomesensor"


def test_the_script_takes_push_and_the_words_exist():
    assert 'n.sensor === "push"' in SCRIPT and "function pushTemp(q)" in SCRIPT
    for lang in ("en", "hu"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text("utf-8"))
        assert set(tr["selector"]["lite_sensor"]["options"]) == set(lite.SENSORS)


def test_no_placeholder_braces_in_the_lite_words():
    # the frontend reads { } as a message argument: "${ev.tC}" showed "Translation error: MALFORMED_ARGUMENT"
    for lang in ("en", "hu"):
        text = (BASE / "translations" / f"{lang}.json").read_text("utf-8")
        assert "${" not in text and "{ev." not in text

"""0.79.9: HC Lite – web set-up on the relay: HC takes over a change made there (the settings revision)."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
lite = importlib.import_module("hc_thermostat.core.lite")
BASE = ROOT / "custom_components" / "hc_thermostat"
SCRIPT = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")


def _p(**kw):
    return lite.settings_payload(lite.LiteSettings.from_conf({f"lite_{k}": v for k, v in kw.items()}))


def test_who_is_right():
    hc = _p(sp_day=22.5)
    dev = _p(sp_day=23.0)
    assert lite.sync_action(dict(hc), hc, 5, 5) == "none"
    assert lite.sync_action(dev, hc, 6, 5) == "adopt", "changed on the relay after the last sync"
    assert lite.sync_action(dev, hc, 5, 5) == "push", "HC's own change is the newer"
    assert lite.sync_action(dev, hc, 6, None) == "push", "a first sync: HC pushes, as before"
    assert lite.sync_action(dev, hc, None, 5) == "push", "an older script without a revision"
    assert lite.sync_action(dev, hc, True, 0) == "push"


def test_the_device_settings_become_the_options():
    o = lite.options_from_device({**_p(), "sp_day": 23.0, "day": "05:30", "cycle": 2700, "boost": 99})
    assert o["lite_sp_day"] == 23.0 and o["lite_day"] == "05:30" and o["lite_cycle"] == 2700
    assert o["lite_boost"] == 1.0, "an out-of-range value is cleaned to the default"
    assert set(o) == {f"lite_{k}" for k in _p()}


def test_the_script_counts_its_revision_and_hc_keeps_it():
    assert 'save("hc_lite_rev", String(REV))' in SCRIPT and "init_tok" in SCRIPT and "UI_SRC" in SCRIPT
    src = (BASE / "lite.py").read_text("utf-8")
    assert "sync_action(" in src and "async_update_entry" in src and '"lite_rev"' in src
    assert "await central.async_load()  # 0.79.9" in (BASE / "__init__.py").read_text("utf-8")

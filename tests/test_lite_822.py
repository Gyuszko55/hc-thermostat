"""0.82.2: from an outside review of HC Lite 0.82.0 – adding a relay set up on its own page keeps its settings (not
shadow), and the presets' memo (an open window) survives a restart. The script's own fixes have desk tests
(guard/tests/hc_lite_review.test.mjs)."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
lite = importlib.import_module("hc_thermostat.core.lite")
BASE = ROOT / "custom_components" / "hc_thermostat"


def test_a_live_relay_keeps_its_settings_when_added():
    dev = {**lite.settings_payload(lite.LiteSettings()), "shadow": False, "sp_day": 22.5, "ctl": "pid", "btn": 200}
    opts = lite.options_from_device(dev)
    assert opts["lite_shadow"] is False and opts["lite_sp_day"] == 22.5 and opts["lite_btn"] == 200
    payload = lite.settings_payload(lite.LiteSettings.from_conf(opts))
    assert lite.sync_action(dev, payload, 3, None) == "none", "the first sync has nothing to push"


def test_the_form_starts_from_the_relay():
    src = (BASE / "config_flow.py").read_text("utf-8")
    assert "found: dict | None = None" in src and 'found["cfg"] = st["cfg"]' in src
    assert "options_from_device(cfg) if cfg else {}" in src


def test_the_memo_is_kept():
    src = (BASE / "lite.py").read_text("utf-8")
    assert '"memo": self.memo' in src and 'data.get("memo")' in src and "if self.memo != before:" in src

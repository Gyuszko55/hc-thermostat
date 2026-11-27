"""0.65.1: a user-friendliness pass – the info panel's decision rows in words (no raw keys or entity ids), a role line
in the header, wider cards, the heat pump chart open, no version numbers or "(shadow)" in the form titles, the zone's
house name, and the learning sensors saying why they have no value yet."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"


def _tr(lang):
    return json.loads((BASE / "translations" / f"{lang}.json").read_text())


def test_panel_rows_in_words():
    js = (BASE / "www" / "hc-info-panel.js").read_text()
    for key in ("enable", "heat_demand", "hold_reason", "charge_mode", "demand_charge", "reserve_kwh", "cap_state", "lasting",
                "demand_target", "trend_c_h", "stop_layer"):
        assert js.count(f"{key}: \"") >= 2, key  # Hungarian and English label
    assert "REASON_KEYS.has(k)" in js and "NAME_LIST_KEYS.has(k)" in js and "_ename(id)" in js
    assert "this._ename(z.name)" in js
    assert "ROLE_TXT" in js and "hp_coord: \"Hőszivattyú-koordináció (puffertöltés)\"" in js
    assert "minmax(270px, 1fr)" in js and "word-break:normal" in js
    assert "curve: true, hp_chart: true" in js
    assert "nincs (nincs puffer vagy kikapcsolva)" not in js


def test_form_texts_without_versions_and_shadow():
    import re
    for lang in ("hu", "en"):
        tr = _tr(lang)
        flat = json.dumps({k: tr[k] for k in ("config", "options")}, ensure_ascii=False)
        assert not re.search(r"\b0\.\d\d\.\d\b", flat)
        for top in ("config", "options"):
            assert "(" not in tr[top]["step"]["circuit"]["title"] and "(" not in tr[top]["step"]["hp_coord"]["title"]
        assert "később" not in tr["options"]["step"]["hp_coord_settings"]["data"]["hp_offset"]
        assert tr["options"]["step"]["settings"]["sections"]["adjoining"]["data"]["home_name"]


def test_zone_house_name_in_settings():
    src = (BASE / "config_flow.py").read_text()
    assert 'if current.get(CONF_ROLE) == "zone":  # 0.65.1: a zone has no rooms step' in src
    assert "CONF_HOUSE_LINK, CONF_HOME_NAME)," in src  # in the "adjoining" fold-out
    assert 'user_input[CONF_HOME_NAME] = str(user_input.get(CONF_HOME_NAME) or "").strip()' in src


def test_learning_sensors_say_why():
    src = (BASE / "sensor.py").read_text()
    assert src.count('"status": "learning"') == 2 and src.count('"status": "ok" if d.heat_need_kw is not None else "learning"') == 1
    assert '"no_data" if advice == "unknown" else advice' in src
    for lang in ("hu", "en"):
        es = _tr(lang)["entity"]["sensor"]
        assert set(es["heat_loss"]["state_attributes"]["status"]["state"]) == {"learning", "manual", "learned"}
        assert set(es["time_constant"]["state_attributes"]["status"]["state"]) == {"learning", "manual", "learned"}
        assert set(es["heat_need"]["state_attributes"]["status"]["state"]) == {"ok", "learning"}
        assert es["source_advice"]["state"]["no_data"]
    assert '_attr_options = [k for k in ADVICE_TEXT if k != "unknown"] + ["no_data"]' in src


def test_version():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3", "0.82.4")

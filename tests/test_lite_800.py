"""0.80.0: HC Lite with a heat pump – the heat source, cooling, the dew point, buffer probes; the compact script."""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
sys.path.insert(0, str(ROOT / "guard"))
lite = importlib.import_module("hc_thermostat.core.lite")
compact_js = importlib.import_module("compact_js")
BASE = ROOT / "custom_components" / "hc_thermostat"
SCRIPT = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")


def _s(**kw):
    return lite.LiteSettings.from_conf({f"lite_{k}": v for k, v in kw.items()})


def test_new_settings_and_their_defaults():
    s = _s()
    assert (s.src, s.sc_day, s.sc_night, s.sc_away, s.hum_id, s.dew_id, s.dew_margin, s.buf, s.bufn) == \
        ("gas", 25.0, 26.0, 28.0, -1, -1, 2.0, (), ())
    s = _s(src="hp", sc_day=24.5, hum_id=201, dew_id=101, buf="100, 102, x, 250, 103, 104", bufn="teteje, alja")
    assert s.src == "hp" and s.sc_day == 24.5 and s.hum_id == 201 and s.dew_id == 101
    assert s.buf == (100, 102, 103), "add-on ids only, at most 3"
    assert s.bufn == ("teteje", "alja")
    assert _s(src="oil").src == "gas" and _s(sc_day=35).sc_day == 25.0 and _s(dew_id=250).dew_id == -1


def test_the_payload_is_what_the_script_takes():
    p = lite.settings_payload(_s(src="hp", buf=[100, 101], bufn=["a", "b"]))
    assert p["buf"] == [100, 101] and p["bufn"] == ["a", "b"], "lists, as JSON"
    for k in ("src", "sc_day", "sc_night", "sc_away", "hum_id", "dew_id", "dew_margin", "buf", "bufn"):
        assert f"C.{k} = " in SCRIPT or f"C.{k}" in SCRIPT, k
        assert f"{k}: C.{k}" in SCRIPT, f"cfgOut has {k}"
    dev = dict(p)
    assert lite.sync_action(dev, p, 3, 3) == "none", "the device's lists compare equal"
    o = lite.options_from_device(dev)
    assert o["lite_buf"] == "100, 101" and o["lite_bufn"] == "a, b", "as the form's text"
    assert lite.settings_payload(lite.LiteSettings.from_conf(o)) == p


def test_view_reads_cooling_and_the_probes():
    st = {"mode": "auto", "relay": True, "hvac": "cool", "hum": 55, "dew": 16.1, "pipe": 19.5, "dew_stop": False,
          "dew_warn": True, "buf": [55.5, None], "cfg": {"src": "hp", "buf": [100, 101], "bufn": ["teteje"]}}
    v = lite.view(st)
    assert v.hvac == "cool" and v.src == "hp" and v.humidity == 55 and v.dew_point == 16.1 and v.pipe == 19.5
    assert v.dew_warn is True and v.dew_stop is False
    assert v.buffer == (("teteje", 55.5), (None, None))
    old = lite.view({"mode": "auto", "relay": False})
    assert old.hvac == "heat" and old.src == "gas" and old.buffer == (), "an older script"


def test_climate_cools_only_with_a_heat_pump():
    src = (BASE / "lite.py").read_text("utf-8")
    assert "HVACMode.COOL" in src and 'settings.src == "hp"' in src and "HVACAction.COOLING" in src
    assert 'hvac="cool" if hvac_mode == HVACMode.COOL else "heat"' in src
    assert "current_humidity" in src and "class LiteBuffer" in src and '"lite_dew_point"' in src


def test_form_and_translations():
    cf = (BASE / "config_flow.py").read_text("utf-8")
    for k in ("src", "sc_day", "sc_night", "sc_away", "hum_id", "dew_id", "dew_margin", "buf", "bufn"):
        assert f'"{k}"' in cf or f'"lite_{k}"' in cf, k
    for lang in ("hu", "en"):
        t = json.loads((BASE / "translations" / f"{lang}.json").read_text("utf-8"))
        for flow in ("config", "options"):
            data = t[flow]["step"]["lite_settings"]["data"]
            assert all(f"lite_{k}" in data for k in ("src", "sc_day", "hum_id", "dew_id", "buf", "bufn"))
        assert set(t["selector"]["lite_src"]["options"]) == {"gas", "hp"}
        assert "{n}" in t["entity"]["sensor"]["lite_buffer"]["name"]
        assert {"lite_dew_point", "lite_flow_pipe"} <= set(t["entity"]["sensor"])


def test_the_script_keeps_its_settings_in_parts():
    assert 'save("hc_lite_c" + (i + 1)' in SCRIPT and "len + one > 220" in SCRIPT
    assert 'save("hc_lite_cfg", now)' not in SCRIPT, "one value of 255+ characters: the device refuses it"


def test_the_compact_script_is_current_and_ascii():
    out = ROOT / "guard" / "shelly" / "hc_lite.min.js"
    assert out.read_text("ascii") == compact_js.build(), "run: python3 guard/compact_js.py"
    code = compact_js.compact(SCRIPT)
    assert "//" not in code.replace("https://", "").replace("http://", ""), "no comment left"
    assert len(code) < len(SCRIPT) * 0.8
    assert '"https://cdn.jsdelivr.net/gh/' in code, "strings untouched"
    assert "compact(LITE.read_text" in (ROOT / "guard" / "upload_shelly.py").read_text("utf-8")


def test_compact_keeps_strings_with_slashes_and_quotes():
    src = 'let a = "x // y"; // gone\nlet b = \'it\\\'s // ok\'; // gone too\n   // only a comment\n'
    assert compact_js.compact(src) == 'let a = "x // y";\nlet b = \'it\\\'s // ok\';\n'

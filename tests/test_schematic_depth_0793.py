"""0.79.3: the hydraulic diagram in two depths and an info-first part panel (a tester's design idea #7, variant 2)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

WWW = Path(__file__).resolve().parents[1] / "custom_components/hc_thermostat/www"
OV = WWW / "hc-overview.js"


def _call(expr: str):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f'const OV = await import({json.dumps(OV.as_uri())}); console.log(JSON.stringify({expr}));'
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


BOILER = {"entry_id": "b1", "title": "HC Boiler", "heat_source": "onoff_boiler", "role": "standalone", "mode": "active",
          "actual": True, "text_hu": "Szabályoz: cél 21 °C, igény 40 %.",
          "decision": {"reason": "regulating", "indoor": 20.6, "target": 21.0, "outdoor": -2.0, "demand": 0.4, "output": True,
                       "heat_need_kw": 2.5},
          "inputs": {"indoor": {"value": 20.6, "age_s": 95}, "outdoor": {"value": -2.0, "age_s": 3000}},
          "measures": {"flow_temp": 52.0, "return_temp": 41.0, "runs": {"starts_today": 6, "hours_today": 2.5}},
          "switch_log": [{"t": "2026-11-25T08:35:57+01:00", "on": True}], "health": {"state": "ok"},
          "entities": {"actuator_entity": [{"entity_id": "switch.boiler", "state": "on"}]},
          "room_list": [{"name": "Living room", "leading": True}, {"name": "Kitchen"}]}
ALL = [BOILER]


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _kinds(html: str) -> dict:
    """label -> kind word of each value row"""
    rows = re.findall(r'<span class="spkind (\w+)">[^<]*</span></td><td>([^<]*)</td>', html)
    return {label: kind for kind, label in rows}


def test_user_depth_tells_what_happens_and_why():
    html = _call(f'OV.partInfo({json.dumps(ALL)}, "member:b1", {{ lang: "hu", depth: "user" }})')
    t = _text(html)
    assert "Boiler Gázkazán" in t and "fűt · 20,6 °C → 21,0 °C" in t
    assert "Szabályoz: cél 21 °C, igény 40 %." in t
    k = _kinds(html)
    assert k["Cél"] == "req" and k["Bent"] == "meas" and k["HC parancs"] == "out" and k["Hőforrás"] == "fb"
    # the technical rows only in maintenance depth
    assert "Igény" not in k and "Hőigény" not in k and "switch.boiler" not in html and "mérés kora" not in t
    assert 'data-sch-open="member:b1"' in html


def test_maintenance_depth_adds_why_in_detail_estimates_never_measured():
    html = _call(f'OV.partInfo({json.dumps(ALL)}, "member:b1", {{ lang: "hu", depth: "maint" }})')
    t, k = _text(html), _kinds(html)
    assert k["Igény"] == "calc" and "40 %" in t
    assert k["Hőigény"] == "est" and "2,50 kW" in t  # an estimate, never a measurement
    assert k["Ok (kód)"] == "calc" and "regulating" in t
    assert "mérés kora 95 mp" in t and "mérés kora 50 perc" in t
    assert k["Indítás ma"] == "meas" and k["Utolsó kapcsolás"] == "out" and "08:35 · be" in t
    assert "rendben" in t and "switch.boiler" in html


def test_command_against_feedback():
    differ = {**BOILER, "actual": False}
    act = _text(_call(f'OV.partInfo({json.dumps([differ])}, "member:b1", {{ lang: "hu", depth: "maint" }})'))
    assert "A parancs és a visszajelzés most eltér." in act
    sh = _text(_call(f'OV.partInfo({json.dumps([{**differ, "mode": "shadow"}])}, "member:b1", {{ lang: "hu", depth: "maint" }})'))
    assert "Árnyékban a valódi hőforrás" in sh and "árnyék – a HC nem kapcsol" in sh
    same = _text(_call(f'OV.partInfo({json.dumps(ALL)}, "member:b1", {{ lang: "hu", depth: "maint" }})'))
    assert "eltér" not in same


def test_heat_pump_target_kinds_and_buffer_estimates():
    hp = {"entry_id": "h1", "title": "HP", "heat_source": "heat_pump", "role": "hp_coord", "mode": "shadow",
          "decision": {"details": {"target_check": {"reported": 45, "given": 44, "raw": 43.6, "writing": False}}}}
    buf = {"entry_id": "t1", "title": "Tank", "role": "buffer", "stock": {"layers": [{"temp": 55}, {"temp": 40}],
                                                                       "stored_kwh": 8.2, "charge": 60}}
    k = _kinds(_call(f'OV.partInfo({json.dumps([hp, buf])}, "member:h1", {{ lang: "hu", depth: "user" }})'))
    assert k["A hőforrás beállított célja"] == "fb" and k["HC kéri"] == "out" and k["Számolt cél"] == "calc"
    k = _kinds(_call(f'OV.partInfo({json.dumps([hp, buf])}, "member:t1", {{ lang: "hu", depth: "user" }})'))
    assert k["Puffer-rétegek 1"] == "meas" and k["Tárolt hő"] == "est" and k["Töltöttség"] == "est"
    assert "HC parancs" not in k


def test_unknown_part_nothing_and_english():
    assert _call(f'OV.partInfo({json.dumps(ALL)}, "member:zz", {{}})') == ""
    assert _call(f'OV.partInfo({json.dumps(ALL)}, "room:x", {{}})') == ""
    en = _text(_call(f'OV.partInfo({json.dumps(ALL)}, "member:b1", {{ lang: "en", depth: "maint" }})'))
    assert "estimated" in en and "Heat need" in en and "Open" in en


def test_depth_switch_and_the_drawing():
    sw = _call('OV.depthSwitch("maint", { lang: "hu" })')
    assert 'data-sch-depth="user"' in sw and 'class="sel">Karbantartói' in sw and "nem jogosultság" in sw
    user = _call(f'OV.renderSchematic({json.dumps(ALL)}, {{ lang: "hu", depth: "user" }})')
    maint = _call(f'OV.renderSchematic({json.dumps(ALL)}, {{ lang: "hu", depth: "maint" }})')
    assert "smaint" not in user and "igény 40 % · regulating" in maint and "parancs ON · visszajelzés ON" in maint
    assert "@keyframes" not in _call("OV.OV_CSS")  # no moving water without a measured flow


def test_the_panel_uses_it():
    src = (WWW / "hc-info-panel.js").read_text("utf-8")
    assert "OV.partInfo(all, this._schKey" in src and "hc-info:depth" in src and "data-sch-open" in src
    assert 'this._pickPart(k)' in src  # "Open" still goes to the instance

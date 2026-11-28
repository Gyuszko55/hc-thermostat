"""0.60.0: the house at a glance (overview), the hydraulic diagram from the instances' links, the mixing circuit's
heating curve (info panel) and its preview table in the settings form."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
OV_PATH = BASE / "www" / "hc-overview.js"
OV = OV_PATH.read_text(encoding="utf-8")
PANEL = (BASE / "www" / "hc-info-panel.js").read_text(encoding="utf-8")


def _zone(sfx, title, circs, out=False, relay=None):
    return {"entry_id": "z_" + sfx, "title": title, "role": "zone", "mode": "shadow", "heat_source": "external_heat",
            "entities": {"actuator_entity": [{"entity_id": f"switch.{sfx}", "state": relay or ("on" if out else "off")}]},
            "decision": {"output": out, "target": 21, "indoor": 20.5, "outdoor": 3.0},
            "climate": {"entity_id": f"climate.{sfx}"}, "circuits": circs}


def _house():
    rad = {"entry_id": "c1", "title": "HC Radiátoros kör", "kind": "radiator", "target": 33.0}
    flo = {"entry_id": "c2", "title": "HC Padlófűtési kör", "kind": "floor", "target": 29.0}
    return [
        _zone("halo", "HC Hálószoba", [rad], True),
        _zone("furdo", "HC Fürdő", [rad, flo], True, relay="off"),
        _zone("nappali", "HC Nappali", [flo]),
        {"entry_id": "c1", "title": "HC Radiátoros kör", "role": "circuit", "mode": "shadow",
         "conf": {"circuit_kind": "radiator", "zone_entities": ["climate.halo", "climate.furdo"]},
         "config": {"circuit_kind": "radiator", "circuit_slope": 0.6, "circuit_flow_min": 30, "circuit_flow_max": 42, "circuit_room": 20, "circuit_kp": 1},
         "decision": {"target": 33, "raw": 33.4, "demand": True, "outdoor": 3.0, "t_room": 21, "deficit": 0.5,
                      "lasting": ["climate.halo", "climate.furdo"], "asking": ["climate.furdo"], "details": {"curve": 32.7}},
         "entities": {"circuit_output_entity": [{"entity_id": "number.plc", "state": "34", "unit": "°C"}]},
         "outputs": {"target": {"entity": "number.plc", "status": "conflict"}}, "write": {"write_mode": "trial"}},
        {"entry_id": "c2", "title": "HC Padlófűtési kör", "role": "circuit", "mode": "shadow",
         "conf": {"circuit_kind": "floor", "zone_entities": ["climate.furdo", "climate.nappali"]},
         "config": {"circuit_kind": "floor"}, "decision": {"target": 29, "demand": False}},
        {"entry_id": "b", "title": "HC Puffer", "role": "buffer", "mode": "shadow", "decision": {"output": False},
         "stock": {"layers": [{"name": "Puffer 1", "temp": 58}, {"name": "Puffer 4", "temp": 29}], "charge": 36,
                   "charge_method": "external", "stored_kwh": 24.5, "charge_layers": 41}, "trend": {"state": "emptying", "c_per_h": -1.4}},
        {"entry_id": "h", "title": "HC HP", "role": "hp_coord", "mode": "shadow", "conf": {"wood_entity": "input_boolean.wood"},
         "entities": {"hp_running_entity": [{"entity_id": "sensor.hp", "state": "41", "unit": "W"}]},
         "inputs": {"outdoor": 3.0, "wood_signal": True},
         "decision": {"enable": False, "heat_demand": False, "reason": "wood", "need": 35, "target": 40, "wood": "certain",
                      "details": {"hp_running": None, "hp_running_age_s": 1240, "top": 58, "low_charge_waits": True}}},
    ]


def _node(script: str) -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])


def test_overview_schematic_and_curve_in_node():
    script = f"""
import * as OV from {json.dumps(OV_PATH.as_uri())};
const all = {json.dumps(_house())};
const html = OV.renderOverview(all, {{ lang: "hu" }});
const sch = OV.renderSchematic(all, {{ lang: "hu" }});
const cur = OV.curveSvg(all[3].config, {{ ...all[3].decision, plc: 34 }}, {{ lang: "hu" }});
const tab = OV.curveTable({{ circuit_slope: 0.6, circuit_flow_min: 30, circuit_flow_max: 42, circuit_room: 20 }}, 3.2);
console.log(JSON.stringify({{
  why: html.includes("a fa tölti a puffert – a hőszivattyú vár") && html.includes("Fatüzelés: biztos"),
  lowWaits: html.includes("nincs helyiségi igény: nem indít"),
  modes: html.includes("felügyelt próba"), conflict: html.includes("→ target: conflict"),
  hpUnknown: html.includes("Hőszivattyú nem ismert"),
  tank: html.includes("töltöttség (meglévő érzékelő)") && html.includes("36 %") && html.includes("24,5 kWh (88 MJ) · 41 %"),
  diff: (html.match(/class="diff"/g) || []).length, plc: html.includes("34 °C"),
  rooms: (html.match(/<tr data-key="member:z_/g) || []).length,
  schRooms: (sch.match(/class="sroom/g) || []).length, schMix: (sch.match(/class="smix/g) || []).length,
  schShared: (sch.match(/radiátor \+ padlófűtés/g) || []).length, schWood: sch.includes("Fatüzelés"), schCoil: sch.includes("csőkígyó"),
  curve: cur.includes('class="cn"') && cur.includes('class="cc"') && cur.includes('class="cplc"') && cur.includes('class="ctg"'),
  tab: tab.map((r) => [r.outdoor, r.flow]), now: tab.some((r) => r.now),
}}));
"""
    out = _node(script)
    assert out["why"] and out["lowWaits"] and out["modes"] and out["conflict"] and out["hpUnknown"] and out["tank"]
    assert out["diff"] == 1 and out["plc"] and out["rooms"] == 3  # the bathroom: HC says ON, the relay is off
    # 0.63.0: a room on two circuits is drawn once, between them; the legend has a mixing valve too
    assert out["schRooms"] == 3 and out["schMix"] == 3 and out["schShared"] == 1 and out["schWood"] and out["schCoil"]
    assert out["curve"] and out["now"]
    tab = dict((o, f) for o, f in out["tab"])
    assert tab[-15] == 41 and tab[5] == 30 and tab[15] == 30  # 20 + 0.6 × 35 = 41; clamped at the 30 °C minimum


def test_panel_has_the_three_views_and_the_curve():
    assert 'import(new URL(`./hc-overview.js${new URL(import.meta.url).search}`' in PANEL
    assert '[["house", this._hu ? "Rajz" : "Drawing"], ["overview", this._hu ? "Áttekintés" : "Overview"], ["schematic", this._hu ? "Rendszerrajz" : "Hydraulic diagram"]]' in PANEL
    assert 'OV.renderOverview(all, { lang: L2 })' in PANEL and 'OV.renderSchematic(all, { lang: L2, depth })' in PANEL  # 0.79.3: with the depth
    assert 'd.role === "circuit" && OV ? this._section("curve"' in PANEL
    assert 'localStorage.setItem("hc-info:view", this._view)' in PANEL
    assert "export function renderOverview" in OV and "export function renderSchematic" in OV and "export function curveSvg" in OV


def test_settings_form_curve_preview():
    from hc_thermostat.config_flow import curve_preview, _circuit_settings
    hass = SimpleNamespace(config=SimpleNamespace(language="hu"),
                           states=SimpleNamespace(get=lambda e: SimpleNamespace(state="3.2", attributes={"unit_of_measurement": "°C"}) if e == "sensor.out" else None))
    md = curve_preview(hass, {"circuit_slope": 0.6, "circuit_flow_min": 30, "circuit_flow_max": 42, "outdoor_entity": "sensor.out"}, "radiator")
    lines = md.splitlines()
    assert lines[0].startswith("| Kint °C | -15 | -10 |") and "most 3,2" in lines[0]
    assert lines[2].startswith("| Előremenő °C | 41,0 | 38,0 | 35,0 | 32,0 | 30,0 | 30,0 | 30,0 |")  # min 30
    assert lines[3].startswith("| +1 °C helyiséghiánnyal | 42,0 |")  # max 42
    assert "circuit_preview" in {str(k) for k in _circuit_settings({}, "radiator")}
    for lang in ("en", "hu"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        for top in ("config", "options"):
            st = d[top]["step"]["circuit_settings"]
            assert "{curve}" in st["description"] and st["data"]["circuit_preview"]
    src = (BASE / "config_flow.py").read_text()
    assert src.count('description_placeholders={"curve": curve_preview(self.hass, values, kind)}') == 2


def test_version_600():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.60.0", "0.61.0", "0.62.0", "0.63.0", "0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3", "0.82.4", "0.82.5", "0.82.6", "0.82.7", "0.83.0", "0.84.0", "0.85.0", "0.86.0", "0.87.0")

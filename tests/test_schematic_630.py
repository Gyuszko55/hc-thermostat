"""0.63.0: the buffer system's diagram like a plant room overview (the tester's drawing): flow and return pipes, the
pump and mixing valve of each circuit, the tank's thermometers on its side, the wood boiler, the heat pump's coil, an
optional hot water tank with its pump, the rooms with icons (a room on two circuits once), legend and control info;
optional PLC readings of a circuit (pump runs, measured flow) and the hot water entities of the tank."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
OV_PATH = BASE / "www" / "hc-overview.js"


def _e(eid, state, unit=None):
    return [{"entity_id": eid, "state": state, "unit": unit}]


def _zone(sfx, title, circs, out=False):
    return {"entry_id": "z_" + sfx, "title": title, "role": "zone", "mode": "shadow", "heat_source": "external_heat",
            "decision": {"output": out, "target": 21, "indoor": 20.5}, "climate": {"entity_id": f"climate.{sfx}"},
            "circuits": circs}


def _house(dhw=True):
    tank_conf = {"buffer_volume_l": 1000, "zone_entities": ["climate.halo", "climate.furdo", "climate.nappali"]}
    tank_ent = {}
    if dhw:
        tank_conf.update(dhw_pump_entity="binary_sensor.hmv_pump", dhw_temp_entity="sensor.hmv", dhw_heater_entity="switch.bojler")
        tank_ent = {"dhw_pump_entity": _e("binary_sensor.hmv_pump", "on"), "dhw_temp_entity": _e("sensor.hmv", "48.5", "°C"),
                    "dhw_heater_entity": _e("switch.bojler", "off")}
    return [
        _zone("halo", "HC Hálószoba", [{"entry_id": "c1"}], True),
        _zone("furdo", "HC Fürdő", [{"entry_id": "c1"}, {"entry_id": "c2"}]),
        _zone("nappali", "HC Nappali/Konyha", [{"entry_id": "c2"}]),
        {"entry_id": "t", "title": "HC Puffer", "role": "buffer", "mode": "shadow", "conf": tank_conf, "entities": tank_ent,
         "stock": {"layers": [{"name": "top", "temp": 58}, {"name": "upper", "temp": 47}, {"name": "lower", "temp": 36},
                              {"name": "bottom", "temp": 29}], "volume_l": 1000, "charge": 52, "stored_kwh": 21.4}},
        {"entry_id": "c1", "title": "HC Radiátoros kör", "role": "circuit", "mode": "shadow",
         "conf": {"circuit_kind": "radiator", "zone_entities": ["climate.halo", "climate.furdo"],
                  "circuit_pump_entity": "binary_sensor.rad_pump", "circuit_flow_entity": "sensor.rad_flow"},
         "entities": {"circuit_pump_entity": _e("binary_sensor.rad_pump", "off"), "circuit_flow_entity": _e("sensor.rad_flow", "39.2", "°C")},
         "decision": {"target": 33, "demand": True, "outdoor": 4.0}},
        {"entry_id": "c2", "title": "HC Padlófűtési kör", "role": "circuit", "mode": "shadow",
         "conf": {"circuit_kind": "floor", "zone_entities": ["climate.furdo", "climate.nappali"]},
         "decision": {"target": 29, "demand": False, "outdoor": 4.0}},
        {"entry_id": "h", "title": "HC Hőszivattyú", "role": "hp_coord", "mode": "shadow",
         "conf": {"wood_temp_entity": "sensor.kazan", "hp_running_entity": "sensor.hp_w"},
         "entities": {"wood_temp_entity": _e("sensor.kazan", "71", "°C"), "hp_running_entity": _e("sensor.hp_w", "0", "W")},
         "decision": {"wood": "certain", "details": {"hp_running": False}}, "inputs": {"outdoor": 4.0}},
    ]


def _render(house, lang="hu"):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f"""
import * as OV from {json.dumps(OV_PATH.as_uri())};
console.log(JSON.stringify({{ s: OV.renderSchematic({json.dumps(house)}, {{ lang: {json.dumps(lang)} }}) }}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout.strip().splitlines()[-1])["s"]


def test_plant_room_drawing():
    s = _render(_house())
    assert "NaN" not in s and "undefined" not in s
    assert s.count('class="sroom') == 3  # the bathroom once
    assert "radiátor + padlófűtés" in s
    for txt in ("KÜLTÉR", "KAZÁNHÁZ", "Fatüzelésű kazán", "Levegő–víz hőszivattyú", "csőkígyós töltés", "Puffer 1 (teteje)",
                "Puffer 4 (alja)", "1000 L", "Jelmagyarázat", "Keringető szivattyú", "Keverőszelep (háromjáratú)",
                "Hőmérséklet-érzékelő", "A hőszivattyú a puffert csőkígyón keresztül fűti", "Vezérlés: árnyék (7)"):
        assert txt in s, txt
    assert s.count('class="ssen"') == 5  # four layers + the legend
    assert 'marker-end="url(#af' in s and 'marker-end="url(#ar' in s
    # icons: bed, bath, sofa; radiator and floor circuits
    assert s.count('class="sico"') >= 6


def test_hot_water_and_plc_readings():
    s = _render(_house())
    assert "HMV" in s and "HMV-szivattyú" in s and "48,5 °C" in s
    assert 'class="sheat "' in s and "villanyfűtés: OFF" in s  # the boiler's electric heater (PV / grid), off
    assert "mért 39,2 °C" in s  # the radiator circuit's measured flow
    # the radiator circuit's pump as the PLC says (off), though HC's enable is on; the floor one by HC's enable (none)
    assert s.count('<g class="spm off">') == 1
    assert "Keringető szivattyú: áll" in s and "HC szerint engedély: nem" in s
    assert "71,0 °C" in s  # the wood boiler's thermometer


def test_no_hot_water_no_tank_and_english():
    s = _render(_house(dhw=False), "en")
    assert "DHW" not in s and "PLANT ROOM" in s and "Legend" in s and "Tank 1 (top)" in s
    plain = _render([_zone("a", "HC A", [])])
    assert "Jelmagyarázat" not in plain  # an ordinary house keeps its simple drawing


def test_entity_fields_and_setup_plan():
    from hc_thermostat import config_flow
    from hc_thermostat.system_setup import plan
    keys = [str(k) for k in config_flow._buffer_fields({})]
    assert "dhw_pump_entity" in keys and "dhw_temp_entity" in keys
    src = (BASE / "config_flow.py").read_text(encoding="utf-8")
    assert "vol.Optional(CONF_CIRCUIT_PUMP" in src and "vol.Optional(CONF_CIRCUIT_FLOW" in src
    for lang in ("hu", "en"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        for sec in ("config", "options"):
            assert d[sec]["step"]["buffer"]["data"]["dhw_pump_entity"]
            assert d[sec]["step"]["circuit"]["data"]["circuit_flow_entity"]
    p = plan({"outdoor": "sensor.o", "buffer": {"top": "sensor.t", "dhw_pump": "switch.hmv", "dhw_temp": "sensor.hmv", "dhw_heater": "switch.b"},
              "circuits": [{"kind": "floor", "pump": "binary_sensor.p", "flow": "sensor.f"}],
              "rooms": [{"name": "N", "indoor": "sensor.n", "actuator": "switch.n", "circuits": ["floor"]}]})
    assert p["buffer"]["dhw_pump_entity"] == "switch.hmv" and p["buffer"]["dhw_temp_entity"] == "sensor.hmv"
    assert p["buffer"]["dhw_heater_entity"] == "switch.b"
    assert p["circuits"][0]["circuit_pump_entity"] == "binary_sensor.p" and p["circuits"][0]["circuit_flow_entity"] == "sensor.f"


def test_overview_cards_show_plc_and_hot_water():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = f"""
import * as OV from {json.dumps(OV_PATH.as_uri())};
console.log(JSON.stringify({{ h: OV.renderOverview({json.dumps(_house())}, {{ lang: "hu" }}) }}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    h = json.loads(res.stdout.strip().splitlines()[-1])["h"]
    assert "szivattyú (PLC)" in h and "mért előremenő" in h and "39,2 °C" in h
    assert "HMV" in h and "48,5 °C · HMV-szivattyú: fut · villanyfűtés: OFF" in h

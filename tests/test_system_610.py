"""0.61.0: wood told from the wood boiler's thermometer (5.7) and the buffer system setup path (5.2)."""

import asyncio
import importlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
wood = importlib.import_module("hc_thermostat.core.wood")
ss = importlib.import_module("hc_thermostat.system_setup")

T0 = datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)


def sec(s):
    return T0 + timedelta(seconds=s)


# --- 5.7 ------------------------------------------------------------------------------------------------------------
def test_wood_detector_two_thresholds_and_confirmation():
    d = wood.WoodDetector(wood.WoodConfig(wood_on_above=65, wood_off_below=60, wood_confirm_s=300))
    assert d.step(sec(0), 62) is None  # between, no state yet: not known
    assert d.step(sec(10), 40) is False  # first reading on a side decides at once
    assert d.step(sec(20), 66) is False  # above: waits for the confirmation
    assert d.step(sec(200), 70) is False
    assert d.step(sec(321), 71) is True  # 5 min above
    assert d.step(sec(400), 62) is True  # between: holds
    assert d.step(sec(500), 59) is True
    assert d.step(sec(600), 63) is True  # back between: the pending stop is dropped
    assert d.pending is None
    assert d.step(sec(700), 58) is True and d.step(sec(1001), 57) is False
    assert d.step(sec(1100), None) is None  # no reading: not known


def test_wood_from_temp_in_the_coordination():
    hc = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    states = {"sensor.kazan": SimpleNamespace(state="70", attributes={"unit_of_measurement": "°C"}, last_updated=T0, last_reported=T0)}
    c = SimpleNamespace(conf={"wood_temp_entity": "sensor.kazan", "wood_on_above": 65.0, "wood_off_below": 60.0},
                        hass=SimpleNamespace(states=SimpleNamespace(get=states.get)),
                        wood=wood.WoodDetector(wood.WoodConfig(65, 60, 300)), wood_temp=None)
    assert hc.HpCoordCoordinator._wood_signal(c, T0) is True and c.wood_temp == 70.0
    info = hc.HpCoordCoordinator.wood_info(c, T0)
    assert info["by"] == "temp" and info["on_above"] == 65.0 and info["state"] is True
    # a direct signal stays first
    c.conf["wood_entity"] = "binary_sensor.flue"
    states["binary_sensor.flue"] = SimpleNamespace(state="off", attributes={}, last_updated=T0, last_reported=T0)
    assert hc.HpCoordCoordinator._wood_signal(c, T0) is False


def test_wood_settings_and_texts():
    src = (BASE / "config_flow.py").read_text()
    assert 'vol.Optional(CONF_WOOD_TEMP, description={"suggested_value": current.get(CONF_WOOD_TEMP)}): _ent(CONF_WOOD_TEMP, "sensor"),' in src
    assert 'w("wood_on_above", 30, 95, 1, "°C"), w("wood_off_below", 25, 90, 1, "°C"), w("wood_confirm_s", 0, 3600, 60, "s"),' in src
    cf = importlib.import_module("hc_thermostat.config_flow")
    base = {"hp_flow_max": 55, "hp_flow_min": 25, "hp_cold_release_above": 7, "hp_cold_on_below": 5, "hp_charge_off": 0, "hp_charge_on": 0}
    assert cf._hpc_errors({**base, "wood_on_above": 60, "wood_off_below": 60}) == {"wood_off_below": "wood_order"}
    assert cf._hpc_errors({**base, "wood_on_above": 65, "wood_off_below": 60}) == {}
    for lang in ("en", "hu"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        for top in ("config", "options"):
            assert d[top]["step"]["hp_coord"]["data"]["wood_temp_entity"]
            assert d[top]["step"]["hp_coord_settings"]["data"]["wood_on_above"]
            assert d[top]["error"]["wood_order"]


# --- 5.2 ------------------------------------------------------------------------------------------------------------
REQ = {"home_name": "Ház fűtési rendszere", "prefix": "HC", "outdoor": "sensor.kint",
       "buffer": {"top": "sensor.p1", "upper": "sensor.p2", "lower": "sensor.p3", "bottom": "sensor.p4", "charge": "sensor.pct", "volume_l": 1000, "base_temp": 30},
       "heat_pump": {"enabled": True, "running": "sensor.hp_w"}, "wood": {"temp": "sensor.kazan", "wood_on_above": 65, "wood_off_below": 60, "wood_confirm_s": 300},
       "circuits": [{"kind": "radiator", "output": "number.plc_rad"}, {"kind": "floor"}],
       "rooms": [{"name": "Hálószoba", "indoor": "sensor.h", "actuator": "switch.h", "circuits": ["radiator"]},
                 {"name": "Fürdő", "indoor": "sensor.f", "actuator": "switch.f", "circuits": ["radiator", "floor"]},
                 {"name": "Nappali", "indoor": "sensor.n", "actuator": "switch.n", "circuits": ["floor"]}]}


def test_plan_of_a_buffer_system():
    p = ss.plan(REQ, "hu")
    names = [z["data"]["name"] for z in p["zones"]]
    assert names == ["HC Hálószoba", "HC Fürdő", "HC Nappali"]
    bath = p["zones"][1]["data"]
    assert bath["system"] == "mixed_mixing" and bath["role"] == "zone" and bath["heat_source"] == "external_heat" and bath["control"] == "tpi"
    assert p["zones"][0]["data"]["system"] == "radiator_single" and p["zones"][2]["data"]["system"] == "floor_single"
    assert all(z["data"]["mode"] == "shadow" and z["data"]["home_name"] == "Ház fűtési rendszere" for z in p["zones"])
    assert p["buffer"]["name"] == "HC Puffer" and p["buffer"]["buffer_charge_entity"] == "sensor.pct" and "boiler_entity" not in p["buffer"]
    assert [c["name"] for c in p["circuits"]] == ["HC Radiátoros kör", "HC Padlófűtési kör"]
    assert p["circuits"][0]["circuit_output_entity"] == "number.plc_rad" and p["circuits"][1]["circuit_flow_max"] == 36.0
    assert p["hp"]["wood_temp_entity"] == "sensor.kazan" and p["hp"]["hp_running_entity"] == "sensor.hp_w"
    with pytest.raises(ValueError, match="room_incomplete"):
        ss.plan({**REQ, "rooms": [{"name": "X", "indoor": "sensor.x"}]})
    with pytest.raises(ValueError, match="wood_order"):
        ss.plan({**REQ, "wood": {"temp": "sensor.kazan", "wood_on_above": 60, "wood_off_below": 62}})


def test_ws_system_creates_and_links_in_order(monkeypatch):
    made = []

    class Flow:
        async def async_init(self, domain, context, data):
            assert context == {"source": "wizard"}
            eid = f"e{len(made)}"
            made.append((eid, data))
            return {"result": SimpleNamespace(entry_id=eid)}

    hass = SimpleNamespace(config=SimpleNamespace(language="hu"),
                           config_entries=SimpleNamespace(flow=Flow(), async_entries=lambda d: [SimpleNamespace(title="Cirkó HC")]))

    async def climate_of(h, entry_id, timeout=0):
        return f"climate.{entry_id}"
    monkeypatch.setattr(ss, "_climate_of", climate_of)
    out = {}
    conn = SimpleNamespace(send_result=lambda i, r: out.update(r=r), send_error=lambda i, c, m: out.update(e=(c, m)))
    asyncio.run(_call(ss.ws_system, hass, conn, {"id": 1, **REQ}))
    assert "e" not in out, out
    roles = [d["role"] for _, d in made]
    assert roles == ["zone", "zone", "zone", "buffer", "circuit", "circuit", "hp_coord"]
    buf = made[3][1]
    assert buf["zone_entities"] == ["climate.e0", "climate.e1", "climate.e2"]
    rad, flo, hp = made[4][1], made[5][1], made[6][1]
    assert rad["circuit_buffer"] == "e3" and rad["zone_entities"] == ["climate.e0", "climate.e1"]
    assert flo["zone_entities"] == ["climate.e1", "climate.e2"]  # the bathroom on both circuits, one zone
    assert hp["hp_buffer"] == "e3"
    assert out["r"]["error"] is None and len(out["r"]["created"]) == 7


def _call(fn, hass, conn, msg):
    # the websocket decorators keep the coroutine function reachable through the closure chain
    f = fn
    while hasattr(f, "__wrapped__"):
        f = f.__wrapped__
    return f(hass, conn, msg)


def test_name_clash_is_refused():
    hass = SimpleNamespace(config=SimpleNamespace(language="hu"),
                           config_entries=SimpleNamespace(async_entries=lambda d: [SimpleNamespace(title="HC Puffer")]))
    out = {}
    conn = SimpleNamespace(send_result=lambda i, r: out.update(r=r), send_error=lambda i, c, m: out.update(e=(c, m)))
    asyncio.run(_call(ss.ws_system, hass, conn, {"id": 1, **REQ}))
    assert out["e"][0] == "name_taken" and "HC Puffer" in out["e"][1]


def test_setup_panel_path_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    path = (BASE / "www" / "hc-system-setup.js").as_uri()
    script = f"""
import * as S from {json.dumps(path)};
const s = S.emptySystem(); const T = S.SYS_TXT.hu;
const m0 = S.missing(s, 1, T);
Object.assign(s.dev, {{ outdoor: "sensor.kint", top: "sensor.p1", wood_temp: "sensor.kazan" }});
const m1 = S.missing(s, 1, T);
s.rooms = [{{ name: "Fürdő", indoor: "sensor.f", actuator: "switch.f", rad: true, floor: true }}];
const m2 = S.missing(s, 2, T);
const r = S.request(s);
console.log(JSON.stringify({{ m0, m1, m2, rooms: r.rooms, circuits: r.circuits.map((c) => c.kind), wood: r.wood, schema: S.devSchema(s).map((x) => x.name) }}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    o = json.loads(res.stdout.strip().splitlines()[-1])
    assert o["m0"] == "Kell a kinti hőmérő." and o["m1"] is None and o["m2"] is None
    assert o["rooms"][0]["circuits"] == ["radiator", "floor"] and o["circuits"] == ["radiator", "floor"]
    assert o["wood"]["temp"] == "sensor.kazan" and "wood_on_above" in o["schema"] and "rad_output" in o["schema"]


def test_panel_and_wizard_wiring():
    wp = (BASE / "www" / "hc-wizard-panel.js").read_text(encoding="utf-8")
    assert "import(new URL(`./hc-system-setup.js${new URL(import.meta.url).search}`" in wp
    assert 'this._sys = this._sys || new SYS.SystemSetup(this); this._sysMode = true;' in wp
    wz = (BASE / "wizard.py").read_text()
    assert "from .system_setup import ws_system" in wz and "websocket_api.async_register_command(hass, ws_system)" in wz


def test_version_610():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.61.0", "0.62.0", "0.63.0", "0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2")


def test_plain_house_schematic_in_node():
    """A house with no buffer system (a gas boiler with its rooms, an AC, an oil heater) was an empty diagram."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    house = [
        {"entry_id": "a", "title": "Boiler HC", "role": "standalone", "heat_source": "onoff_boiler", "actual": True,
         "decision": {"output": True, "indoor": 22, "target": 22.5},
         "room_list": [{"name": "Nappali", "leading": True, "temperature": 22}, {"name": "Konyha", "temperature": 22.8, "target": 22.5},
                       {"name": "Hálószoba", "temperature": 21.8, "heated": False}]},
        {"entry_id": "b", "title": "Nappali klíma", "role": "standalone", "heat_source": "air_conditioner", "decision": {"output": True, "indoor": 18.7, "target": 19},
         "room_list": [{"name": "Dolgozószoba", "leading": True}]},
        {"entry_id": "c", "title": "Olajradiátor", "role": "standalone", "heat_source": "electric_heater", "decision": {"output": False, "indoor": 21.8, "target": 21},
         "room_list": [{"name": "Hálószoba", "leading": True}]},
    ]
    path = (BASE / "www" / "hc-overview.js").as_uri()
    script = f"""
import * as OV from {json.dumps(path)};
const s = OV.renderSchematic({json.dumps(house)}, {{ lang: "hu" }});
console.log(JSON.stringify({{ rooms: (s.match(/class="sroom/g) || []).length, gas: s.includes("Gázkazán"), on: s.includes(">ég<"),
  units: s.includes("Helyiségi egységek"), ac: s.includes(">Klíma<"), unheated: s.includes("nem fűti") }}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    o = json.loads(res.stdout.strip().splitlines()[-1])
    assert o == {"rooms": 5, "gas": True, "on": True, "units": True, "ac": True, "unheated": True}

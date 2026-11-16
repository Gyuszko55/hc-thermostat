"""0.59.0: a tester's findings on a buffer system with two mixing circuits (wood + monoblock heat pump on the coil):
no phantom room from a circuit, no boiler box per room zone, rooms named by their instance, a bathroom with radiator
and floor on one thermostat, the low-charge start only with a room demand (optional), a stale "runs" reading not
trusted, the buffer's relay optional, a zone's water shown as its circuits' targets."""

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
JS_PATH = BASE / "www" / "hc-house-view.js"
JS = JS_PATH.read_text(encoding="utf-8")
hpc = importlib.import_module("hc_thermostat.core.hp_coord")

T0 = datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)


def sec(s: float) -> datetime:
    return T0 + timedelta(seconds=s)


# --- 5.4: the low-charge start only with a room demand ---------------------------------------------------------------
def _inputs(**kw):
    base = dict(outdoor=3.0, top=40.0, charge=3.0, circuits=(hpc.CircuitNeed("radiator", False, 33.0, 2.0),))
    return hpc.HpInputs(**{**base, **kw})


def test_low_charge_starts_without_demand_by_default():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_charge_on=4, hp_charge_off=10, hp_min_on_s=0, hp_min_off_s=0))
    d = h.step(sec(0), _inputs())
    assert d.heat_demand and d.reason == "low_charge"  # unchanged behaviour


def test_low_charge_waits_for_a_room_demand_when_set():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_charge_on=4, hp_charge_off=10, hp_charge_needs_demand=True,
                                             hp_min_on_s=0, hp_min_off_s=0))
    d = h.step(sec(0), _inputs())
    assert not d.heat_demand and not d.enable and d.details.get("low_charge_waits") is True
    # a circuit with a lasting demand: now the low charge starts it
    d = h.step(sec(60), _inputs(circuits=(hpc.CircuitNeed("radiator", True, 33.0, 2.0),), top=60.0))
    assert d.heat_demand and d.reason == "low_charge"
    # the charge rises to 6 % (below the 10 % stop) and the demand ends: it stops on the temperatures alone
    d = h.step(sec(120), _inputs(charge=6.0, top=60.0))
    assert not d.heat_demand


def test_low_charge_with_demand_keeps_charging_to_the_stop_limit():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_charge_on=4, hp_charge_off=10, hp_charge_needs_demand=True,
                                             hp_min_on_s=0, hp_min_off_s=0))
    need = (hpc.CircuitNeed("radiator", True, 33.0, 2.0),)
    assert h.step(sec(0), _inputs(circuits=need, top=60.0)).heat_demand
    d = h.step(sec(60), _inputs(circuits=need, top=60.0, charge=6.0))
    assert d.heat_demand and d.reason == "charging"


def test_charge_option_in_the_settings_and_texts():
    src = (BASE / "config_flow.py").read_text()
    assert 'b("hp_charge_needs_demand")' in src
    for lang in ("en", "hu"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        assert d["options"]["step"]["hpc_settings"]["data"]["hp_charge_needs_demand"] if "hpc_settings" in d["options"]["step"] \
            else "hp_charge_needs_demand" in json.dumps(d)


# --- 5.6: a stale "runs" reading ------------------------------------------------------------------------------------
def test_stale_power_reading_is_not_running():
    hc = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    old = T0 - timedelta(minutes=30)
    states = {"sensor.w": SimpleNamespace(state="1544", attributes={"unit_of_measurement": "W"}, last_updated=old, last_reported=old),
              "sensor.w0": SimpleNamespace(state="41", attributes={"unit_of_measurement": "W"}, last_updated=old, last_reported=old),
              "sensor.fresh": SimpleNamespace(state="1544", attributes={"unit_of_measurement": "W"}, last_updated=T0, last_reported=T0)}
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    assert hc.on_state(hass, "sensor.w", T0) is None  # 30 min old "runs": not known
    assert hc.on_state(hass, "sensor.w0", T0) is False  # an old low reading stays "does not run"
    assert hc.on_state(hass, "sensor.fresh", T0) is True
    assert hc.RUNNING_MAX_AGE_S == 900.0


# --- 5.1: labels and the optional buffer relay ----------------------------------------------------------------------
def test_buffer_relay_optional_and_relay_label():
    src = (BASE / "config_flow.py").read_text()
    assert 'vol.Optional(CONF_BOILER, description={"suggested_value": current.get(CONF_BOILER)}): _entity("switch", "input_boolean"),\n        vol.Optional(CONF_ZONES' in src
    hu = (BASE / "translations" / "hu.json").read_text(encoding="utf-8")
    assert "zónaszelep / helyiségi relé" in hu and "üresen a HC csak figyeli a tartályt" in hu


# --- 5.5: the zone's circuits -----------------------------------------------------------------------------------------
def test_zone_info_lists_its_circuits():
    info = (BASE / "info.py").read_text()
    assert '"circuits": _circuits_of(hass, (clim or {}).get("entity_id"))' in info
    panel = (BASE / "www" / "hc-info-panel.js").read_text(encoding="utf-8")
    assert '["mix_targets", "emitter", "Keverőkör előremenő célja"' in panel
    assert '((d.circuits || []).length ? null : CA(d, "flow_request"))' in panel


# --- 3.1–3.4: the house drawing (run in node when it is there) ------------------------------------------------------
def _zone(sfx, title, circs, area=None, out=False):
    return {"entry_id": "z_" + sfx, "title": title, "role": "zone", "mode": "shadow", "heat_source": "external_heat",
            "system": "radiator_single", "control": "tpi",
            "entities": {"indoor_entity": [{"entity_id": f"sensor.{sfx}_t", "name": f"{sfx} konyha hőmérő", "state": "21"}],
                         "actuator_entity": [{"entity_id": f"switch.{sfx}", "name": "relé", "state": "on" if out else "off"}]},
            "conf": {}, "decision": {"output": out, "target": 21, "indoor": 21}, "inputs": {},
            "climate": {"entity_id": f"climate.{sfx}", "attributes": {}}, "circuits": circs, "room_list": [],
            "entity_areas": {f"sensor.{sfx}_t": area} if area else {},
            "areas": [{"area_id": "halo", "name": "Hálószoba"}, {"area_id": "konyha", "name": "Konyha"},
                      {"area_id": "furdo", "name": "Fürdőszoba"}], "floors": []}


def test_house_of_a_buffer_system_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    rad = {"entry_id": "c1", "title": "HC Radiátoros kör", "kind": "radiator", "target": 33.0}
    flo = {"entry_id": "c2", "title": "HC Padlófűtési kör", "kind": "floor", "target": 29.0}
    host = _zone("halo", "HC Hálószoba", [rad], "halo")
    members = [_zone("moso", "HC Mosókonyha", [rad]), _zone("furdo", "HC Fürdőszoba", [rad, flo], "furdo", True),
               {"entry_id": "c1", "title": "HC Radiátoros kör", "role": "circuit", "config": {"circuit_kind": "radiator"},
                "decision": {"target": 33, "demand": True}},
               {"entry_id": "c2", "title": "HC Padlófűtési kör", "role": "circuit", "config": {"circuit_kind": "floor"},
                "decision": {"target": 29, "demand": False}},
               {"entry_id": "b", "title": "HC Puffer", "role": "buffer", "decision": {"output": False},
                "stock": {"layers": [{"name": "top", "temp": 58}, {"name": "bottom", "temp": 30}], "top": 58, "charge": 36, "stored_kwh": 24}},
               {"entry_id": "h", "title": "HC HP", "role": "hp_coord", "conf": {"wood_entity": "input_boolean.wood"},
                "decision": {"target": 40, "wood": "certain", "details": {"hp_running": False}}}]
    script = f"""
import {{ fromInfo, renderHouse }} from {json.dumps(JS_PATH.as_uri())};
const host = {json.dumps(host)}, members = {json.dumps(members)};
const vm = fromInfo(host, {{ lang: "hu", members }});
const svg = renderHouse(vm, {{ width: 900 }}).svg;
console.log(JSON.stringify({{
  rooms: vm.rooms.map((r) => [r.name, r.emitter, (r.extras || []).map((e) => e.emitter)]),
  kinds: vm.sources.map((q) => q.kind), circuits: vm.circuits.map((c) => [c.kind, c.target]),
  tank: vm.tank && vm.tank.charge, ext: svg.includes("Külső hőtermelő"), mix: (svg.match(/class="mix/g) || []).length,
  wood: svg.includes("Fatüzelésű kazán"), phantom: vm.rooms.some((r) => r.name === "Helyiség")
}}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    names = [r[0] for r in out["rooms"]]
    assert not out["phantom"] and "Helyiség" not in names  # 3.1: no room from a circuit
    assert "Mosókonyha" in names and "Konyha" not in names  # 3.4: named by the instance
    bath = next(r for r in out["rooms"] if r[0] == "Fürdőszoba")
    assert bath[1] == "radiator" and "floor" in bath[2]  # 3.3: one room, both emitters
    assert out["kinds"] == ["wood_boiler", "heat_pump"]  # 3.2: no zone is a heat source
    assert not out["ext"] and out["wood"] and out["mix"] == 2
    assert sorted(out["circuits"]) == [["floor", 29], ["radiator", 33]] and out["tank"] == 36


def test_house_view_source_markers():
    assert 'if (role === "circuit") { circuits.push(circuitOf(mi)); continue; }' in JS
    assert 'const zoneM = role === "zone" || mi.heat_source === "external_heat";' in JS
    assert "function titleRoom(title, areas)" in JS and "function hpSources(mi)" in JS
    assert 'wood_boiler: "Fatüzelésű kazán"' in JS
def test_version_590():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.59.0", "0.60.0", "0.61.0", "0.62.0", "0.63.0")

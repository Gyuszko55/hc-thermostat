"""0.58.0: every heating system drawn the way it is built – district heating as a flat in a block (flat station or
radiators on the risers), pellet store, manifold, electric floor with its board, storage heaters wired from the board."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
JS = (BASE / "www" / "hc-house-view.js").read_text(encoding="utf-8")


def test_district_heating_is_a_flat_in_a_block():
    assert 'const apt = src0.kind === "district_heating";' in JS
    assert "if (apt) drawBlock();" in JS and "if (apt) drawPlate();" in JS
    assert "function drawBlock()" in JS and "function drawPlate()" in JS
    assert "if (!apt) out.push(`<path d=\"M${X0 + gI}" in JS  # no attic
    assert 'pipe(`M${xf},0 V${Ht}`, "f", prim);' in JS  # the building's risers


def test_district_connection_station_or_direct():
    assert 'connection: kind === "district_heating" ? (conf.district_connection === "direct" ? "direct" : "station") : null' in JS
    assert "if (direct && n === 1) return drawDirect(g, b, list);" in JS
    assert "function drawDirect(g, b, list)" in JS and 'class="alloc"' in JS and 'class="door"' in JS
    assert 'class="hmeter"' in JS  # the heat meter on the flat station


def test_district_connection_option_and_texts():
    src = (BASE / "config_flow.py").read_text()
    assert '_select(("station", "direct"), "district_connection")' in src
    assert '"devices": ("district_connection",' in src
    for lang in ("en", "hu"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        sec = d["options"]["step"]["settings"]["sections"]["devices"]
        assert sec["data"]["district_connection"] and sec["data_description"]["district_connection"]
        assert set(d["selector"]["district_connection"]["options"]) == {"station", "direct"}


def test_pellet_store_and_fire_door():
    assert 'class="silo"' in JS and 'class="pell"' in JS and 'class="auger"' in JS and 'class="pwin' in JS
    assert "fuelLevel: num(info.measures?.fuel_level)" in JS
    assert 'k === "pellet_boiler" ? "pel"' in JS or '{solid ? "pel" :' in JS  # 0.59.0: wood boilers too


def test_manifold_for_floor_loops():
    assert 'if (rooms.some((r) => r.emitter === "floor"))' in JS and 'class="mani"' in JS


def test_electric_floor_and_storage_heaters_are_wired_from_the_board():
    assert 'kind === "electric_heater" && sys.startsWith("floor") ? "efloor"' in JS
    assert 'kind === "storage_heater" ? "storage" : "none"' in JS  # every room of a storage heater instance
    assert "const elec = !hyd && (efl || sto);" in JS
    assert "util = hyd ? { util: true } : elec ? { util: true, elec: true } : null" in JS
    assert "function drawElec(g)" in JS and 'class="eboard"' in JS and 'class="emeter"' in JS
    assert '} else if (em === "efloor") {' in JS and 'class="efl"' in JS
    assert "function cable(d, on, kind)" in JS and "cab-l" in JS and "cab-n" in JS
    assert 'efloor: "Elektromos padlófűtés"' in JS and 'efloor: "Electric floor heating"' in JS


def test_version():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.58.0", "0.59.0", "0.60.0", "0.61.0", "0.62.0", "0.63.0", "0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0")

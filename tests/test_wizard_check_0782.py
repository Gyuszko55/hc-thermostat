"""0.78.2 (security review L1/L2): the setup wizard's websocket commands take only what the panel's pickers and the
options flow's fields offer – each entity in a domain its field allows, each setting in its range, bounded lists."""

import asyncio
import copy
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
sys.path.insert(0, str(ROOT / "tests"))

from test_system_610 import REQ, _call  # noqa: E402

wc = importlib.import_module("hc_thermostat.wizard_check")
wz = importlib.import_module("hc_thermostat.wizard")
ss = importlib.import_module("hc_thermostat.system_setup")


def test_entities_by_domain():
    ok = wc.check_entities({"indoor_entity": "sensor.t", "actuator_entity": "switch.boiler",
                            "window_entities": ["binary_sensor.w1", "binary_sensor.w2"]})
    assert ok["window_entities"] == ["binary_sensor.w1", "binary_sensor.w2"]
    for bad in ({"actuator_entity": "lock.front_door"}, {"actuator_entity": "light.x"},
                {"external_climate": "switch.x"}, {"indoor_entity": "sensor.T"}, {"indoor_entity": 5},
                {"window_entities": ["binary_sensor.w"] * (wc.MAX_LIST + 1)}, {"flow_setpoint_entity": "number."}):
        with pytest.raises(wc.Invalid):
            wc.check_entities(bad)
    assert set(wc.ENTITY_DOMAINS) == set(wz.ENTITY_KEYS)  # every key the wizard writes has its rule


def test_settings_in_range():
    ok = wc.check_settings({"cycle_s": "900", "night_start": "22:00:00", "floor_temper": True, "floor_probe": "surface"})
    assert ok["cycle_s"] == 900.0
    for bad in ({"cycle_s": "fast"}, {"cycle_s": float("nan")}, {"cycle_s": 10}, {"target_home": 80},
                {"night_start": "25:00"}, {"floor_temper": "yes"}, {"floor_probe": "x"}, {"cycle_s": True}):
        with pytest.raises(wc.Invalid):
            wc.check_settings(bad)
    assert set(wc.SETTING_RULES) == set(wz.SETTING_KEYS)


def _apply(msg):
    out = {}
    conn = SimpleNamespace(send_result=lambda i, r: out.update(r=r), send_error=lambda i, c, m: out.update(e=(c, m)))
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda d: []), states=SimpleNamespace(get=lambda e: None))
    base = {"id": 1, "name": "X", "heat_source": "onoff_boiler", "system": "radiator_single", "control": "tpi",
            "entities": {"indoor_entity": "sensor.t", "actuator_entity": "switch.b"}, "settings": {}, "start_active": False}
    asyncio.run(_call(wz.ws_apply, hass, conn, {**base, **msg}))
    return out


def test_ws_apply_refuses_a_lock_and_a_bad_setting():
    out = _apply({"entities": {"indoor_entity": "sensor.t", "actuator_entity": "lock.front_door"}})
    assert out["e"][0] == "invalid_value" and "actuator_entity" in out["e"][1]
    out = _apply({"settings": {"cycle_s": "NaN"}})
    assert out["e"][0] == "invalid_value" and "cycle_s" in out["e"][1]


def _system(msg, entries=None):
    out = {}
    conn = SimpleNamespace(send_result=lambda i, r: out.update(r=r), send_error=lambda i, c, m: out.update(e=(c, m)))
    entries = entries or {}
    hass = SimpleNamespace(config=SimpleNamespace(language="hu"),
                           config_entries=SimpleNamespace(async_entries=lambda d: [], async_get_entry=entries.get))
    asyncio.run(_call(ss.ws_system, hass, conn, {"id": 1, "dry_run": True, **msg}))
    return out


def test_ws_system_checks_values_and_existing_rooms():
    assert "e" not in _system(copy.deepcopy(REQ))  # the reference request goes through
    bad = copy.deepcopy(REQ)
    bad["rooms"][0]["actuator"] = "lock.door"
    assert _system(bad)["e"][0] == "invalid_value"
    bad = copy.deepcopy(REQ)
    bad["buffer"]["volume_l"] = "lots"
    assert "buffer.volume_l" in _system(bad)["e"][1]
    bad = copy.deepcopy(REQ)
    bad["rooms"] = ["not a dict"]
    assert _system(bad)["e"][0] == "invalid_value"
    # an existing room must be an HC zone – not another integration's entry, nor an HC buffer
    room = {"entry_id": "other", "circuits": ["radiator"]}
    for entry in (SimpleNamespace(domain="netatmo", data={}, options={}),
                  SimpleNamespace(domain="hc_thermostat", data={"role": "buffer"}, options={})):
        req = {**copy.deepcopy(REQ), "rooms": [room]}
        assert _system(req, {"other": entry})["e"] == ("invalid_value", "room.entry_id does not fit")
    zone = SimpleNamespace(domain="hc_thermostat", data={"role": "zone"}, options={})
    assert "e" not in _system({**copy.deepcopy(REQ), "rooms": [room]}, {"other": zone})

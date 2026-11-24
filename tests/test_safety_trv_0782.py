"""0.78.2 (security review M4): a life-safety stop takes every TRV head to the frost level – also in shadow and over a
target set on the head by hand; a head switched off stays off."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
sys.path.insert(0, str(ROOT / "tests"))

from test_retail_450 import METRIC, _Hass, _st  # noqa: E402

model = importlib.import_module("hc_thermostat.core.model")
trv = importlib.import_module("hc_thermostat.core.trv")
coord_mod = importlib.import_module("hc_thermostat.coordinator")

T0 = datetime(2026, 11, 20, 22, 0, tzinfo=timezone.utc)


def _coord(monkeypatch, mode, heads):
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: T0)
    monkeypatch.setattr(coord_mod.dt_util, "utcnow", lambda: T0)
    states = {"sensor.n": _st("sensor.n", "21"), "sensor.k": _st("sensor.k", "20"), **heads}
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass, c.mode = _Hass(states, METRIC), mode
    c.conf = {"rooms": [{"key": "n", "name": "N", "sensors": ["sensor.n"], "trvs": ["climate.n_trv"]},
                        {"key": "k", "name": "K", "sensors": ["sensor.k"], "trvs": ["climate.k_trv"]}],
              "leading_room": "n"}
    c.cfg = model.HcConfig.from_mapping({**c.conf, "frost_temp": 7.0})
    c.trv_targets, c.trv_cal, c.trv_info = trv.TrvTargets(), trv.TrvCalibration(), {}
    c._room_groups, c._trv_groups, c._specs = None, None, None
    c._started = T0 - timedelta(hours=1)
    c.room_demand, c.asking_rooms, c.data = trv.RoomDemand(), [], None
    return c


def _head(eid, state="heat", target=21.0):
    return {eid: _st(eid, state, temperature=target, current_temperature=20.0, target_temp_step=0.5, min_temp=5,
                     max_temp=30)}


def _stop():
    return model.Decision(T0, model.Reason.SAFETY_STOP, 21.0, 21.0, 0.0, demand=0.0, output=False,
                          limited_by="safety_stop")


def _writes(c):
    return {d["entity_id"]: d["temperature"] for dom, svc, d in c.hass.calls if svc == "set_temperature"}


def test_every_head_goes_to_frost_also_in_shadow(monkeypatch):
    c = _coord(monkeypatch, "shadow", {**_head("climate.n_trv"), **_head("climate.k_trv", target=23.0)})
    asyncio.run(c._apply_trvs(_stop()))
    assert _writes(c) == {"climate.n_trv": 7.0, "climate.k_trv": 7.0}
    assert c.room_states["k"]["reason"] == "safety_stop" and c.room_states["n"]["target"] == 7.0


def test_a_hand_set_target_does_not_survive_the_stop(monkeypatch):
    c = _coord(monkeypatch, "active", {**_head("climate.n_trv"), **_head("climate.k_trv")})
    asyncio.run(c._apply_trvs(_stop()))  # frost written
    c.hass._states["climate.k_trv"] = _head("climate.k_trv", target=7.0)["climate.k_trv"]
    c.hass._states["climate.n_trv"] = _head("climate.n_trv", target=7.0)["climate.n_trv"]
    asyncio.run(c._apply_trvs(_stop()))  # both took it
    c.hass._states["climate.k_trv"] = _head("climate.k_trv", target=24.0)["climate.k_trv"]  # turned up by hand
    c.hass.calls.clear()
    asyncio.run(c._apply_trvs(_stop()))
    assert _writes(c) == {"climate.k_trv": 7.0}
    assert c.trv_info["K"]["heads"]["climate.k_trv"]["plan"] == "safety_stop"


def test_an_off_head_stays_off_and_shadow_without_a_stop_writes_nothing(monkeypatch):
    c = _coord(monkeypatch, "shadow", {**_head("climate.n_trv", state="off"), **_head("climate.k_trv")})
    asyncio.run(c._apply_trvs(_stop()))
    assert _writes(c) == {"climate.k_trv": 7.0}
    c2 = _coord(monkeypatch, "shadow", {**_head("climate.n_trv"), **_head("climate.k_trv")})
    asyncio.run(c2._apply_trvs(model.Decision(T0, model.Reason.REGULATING, 21.0, 21.0, 0.0, output=True)))
    assert c2.hass.calls == []

"""0.30.0: TRV rooms – per room offset to the house target, calibration of the heads by the room thermometers."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from core.trv import CAL_MAX, TrvCalibration, TrvTargets

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

T0 = datetime(2026, 11, 10, 18, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


# --- calibration -------------------------------------------------------------------------------------------------
def test_calibration_starts_from_the_first_pair_and_follows_slowly():
    cal = TrvCalibration()
    assert cal.update("climate.bed", 23.0, 21.0, at(0)) == 2.0  # head next to the radiator reads 2 °C high
    assert cal.update("climate.bed", 22.0, 21.0, at(1)) > 1.9  # one odd minute moves it little
    for minute in range(2, 240):
        value = cal.update("climate.bed", 22.0, 21.0, at(minute))
    assert abs(value - 1.0) < 0.05  # after hours it settles on the new difference


def test_calibration_is_bounded_and_kept_without_a_reading():
    cal = TrvCalibration()
    assert cal.update("climate.bed", 30.0, 20.0, at(0)) == CAL_MAX
    assert cal.update("climate.bed", None, 20.0, at(1)) == CAL_MAX  # the head did not report: keep
    assert cal.update("climate.other", 22.0, None, at(1)) == 0.0  # no room thermometer: no calibration


def test_calibration_survives_a_restart():
    cal = TrvCalibration()
    cal.update("climate.bed", 23.0, 21.0, at(0))
    again = TrvCalibration()
    again.restore(cal.state())
    assert again.update("climate.bed", 21.0, 21.0, at(60)) == 2.0  # first pair after the restart only sets the clock


# --- targets ----------------------------------------------------------------------------------------------------
def test_calibration_only_changes_are_written_seldom():
    t = TrvTargets()
    plan = t.plan("climate.bed", 19.0, "heat", 20.0, want=21.0, now=at(0))  # room 19 °C + 2 calibration
    assert plan.reason == "write" and plan.target == 21.0
    t.written("climate.bed", 21.0, 19.0, at(0))
    assert t.plan("climate.bed", 19.0, "heat", 21.0, want=20.5, now=at(10)).reason == "wait"
    assert t.plan("climate.bed", 19.0, "heat", 21.0, want=20.5, now=at(31)).target == 20.5
    # a new room target (the schedule) is written at once
    assert t.plan("climate.bed", 17.0, "heat", 21.0, want=18.5, now=at(32)).target == 18.5


def test_hand_change_on_the_head_still_wins():
    t = TrvTargets()
    t.written("climate.bed", 21.0, 19.0, at(0))
    assert t.plan("climate.bed", 19.0, "heat", 23.0, want=21.5, now=at(60)).reason == "manual"


# --- in the coordinator ------------------------------------------------------------------------------------------
class _Hass:
    def __init__(self, states):
        self._states, self.calls, self.data = states, [], {}
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))
        self.services = SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def _coordinator(states, conf):
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    model = importlib.import_module("hc_thermostat.core.model")
    trv = importlib.import_module("hc_thermostat.core.trv")
    c = object.__new__(coord_mod.HcCoordinator)
    c.hass, c.conf, c.mode = _Hass(states), conf, "active"
    c.cfg = model.HcConfig.from_mapping(conf)
    c.trv_targets, c.trv_cal, c.trv_info = trv.TrvTargets(), trv.TrvCalibration(), {}
    c._room_groups = {"Hálószoba": ["sensor.halo"]}
    c._trv_groups = {"Hálószoba": ["climate.halo_fej"], "Fürdő": ["climate.furdo_fej"]}
    return c, model


def _state(value, last=T0, **attrs):
    return SimpleNamespace(state=str(value), attributes=attrs, last_reported=last)


def test_rooms_get_their_offset_and_the_head_its_calibration(monkeypatch):
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: T0)
    monkeypatch.setattr(coord_mod.dt_util, "utcnow", lambda: T0)
    states = {"sensor.halo": _state(18.5),
              "climate.halo_fej": _state("heat", temperature=20.0, current_temperature=20.5, target_temp_step=0.5),
              "climate.furdo_fej": _state("heat", temperature=21.0, current_temperature=22.0, target_temp_step=0.5)}
    c, model = _coordinator(states, {"trv_offsets": {"Hálószoba": -2.0, "Fürdő": 1.0}, "trv_calibration": True})
    decision = model.Decision(T0, model.Reason.REGULATING, 21.0, 21.0, 0.0)
    asyncio.run(c._apply_trvs(decision))
    written = {d["entity_id"]: d["temperature"] for _, _, d in c.hass.calls}
    # bedroom: 21 − 2 = 19 °C, its head reads 2 °C above the room thermometer → 21 °C on the head
    # bathroom: 21 + 1 = 22 °C, no room thermometer there → no calibration
    assert written == {"climate.halo_fej": 21.0, "climate.furdo_fej": 22.0}
    assert c.trv_info["Hálószoba"]["target"] == 19.0 and c.trv_info["Hálószoba"]["heads"]["climate.halo_fej"]["calibration"] == 2.0
    assert c.room_target("Fürdő", 18.0) == 19.0  # follows the schedule (night 18 °C)


def test_without_offsets_and_calibration_the_house_target_as_before(monkeypatch):
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: T0)
    monkeypatch.setattr(coord_mod.dt_util, "utcnow", lambda: T0)
    states = {"sensor.halo": _state(18.5),
              "climate.halo_fej": _state("heat", temperature=19.0, current_temperature=20.5, target_temp_step=0.5),
              "climate.furdo_fej": _state("heat", temperature=21.0, current_temperature=22.0, target_temp_step=0.5)}
    c, model = _coordinator(states, {})
    asyncio.run(c._apply_trvs(model.Decision(T0, model.Reason.REGULATING, 21.0, 21.0, 0.0)))
    assert [d for _, _, d in c.hass.calls] == [{"entity_id": "climate.halo_fej", "temperature": 21.0}]

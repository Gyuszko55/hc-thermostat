"""0.38.0: a wired (dry-contact) wall thermostat as the demand source; the room thermometer becomes optional."""

import asyncio
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.matrix import default_timing, floor_system, source_defaults
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def cfg(system="floor_single", source="electric_heater", **kw):
    return HcConfig.from_mapping({**source_defaults(system, source), **default_timing(system, source), **DAY,
                                  "floor_system": floor_system(system), "demand_contact": True, **kw})


def step(sup, minute, call=True, indoor=None, floor=22.0, outdoor=5.0, **kw):
    return sup.step(Inputs(now=at(minute), indoor=Reading(indoor) if indoor is not None else Reading(),
                           outdoor=Reading(outdoor), floor=Reading(floor) if floor is not None else Reading(),
                           call=call, **kw))


@pytest.mark.parametrize("control", ["tpi", "onoff"])
def test_call_and_idle(control):
    sup = Supervisor(cfg(control=control))
    d = step(sup, 0, call=True)
    assert d.reason == Reason.THERMOSTAT_CALL and d.demand == 1.0 and d.output
    d = step(sup, 20, call=False)
    assert d.reason == Reason.THERMOSTAT_IDLE and d.demand == 0.0 and not d.output
    assert explain(d, "hu") == "A fali termosztát nem kér fűtést."
    assert explain(sup.step(Inputs(now=at(40), floor=Reading(22.0), call=True)), "en") == "The wall thermostat asks for heat."


def test_the_room_thermometer_does_not_decide():
    sup = Supervisor(cfg(control="tpi"))
    d = step(sup, 0, call=True, indoor=25.0)  # warm room, but the wall thermostat asks
    assert d.reason == Reason.THERMOSTAT_CALL and d.output
    sup = Supervisor(cfg(control="tpi"))
    d = step(sup, 0, call=False, indoor=15.0)
    assert d.reason == Reason.THERMOSTAT_IDLE and not d.output


def test_unavailable_contact_falls_back():
    sup = Supervisor(cfg(control="tpi"))  # electric floor with a floor sensor: the floor fallback
    d = step(sup, 0, call=None, floor=22.0)
    assert d.reason == Reason.SENSOR_LOST and d.details.get("floor_fallback") and d.output
    sup = Supervisor(cfg(system="radiator_single", source="onoff_boiler", control="tpi"))
    d = step(sup, 0, call=None, indoor=None, floor=None)  # no room reading either: the blind demand
    assert d.reason == Reason.SENSOR_LOST and d.demand == 0.35
    # 0.39.3: with a room reading the room thermometer is the backup (tests/test_fixes_392.py)


def test_precedence():
    sup = Supervisor(cfg(control="tpi", window_delay_s=0))
    assert step(sup, 0, window_open=True).reason == Reason.WINDOW
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, enabled=False).reason == Reason.DISABLED
    sup = Supervisor(cfg(control="tpi", season_enabled=True))
    assert step(sup, 0, outdoor_avg=20.0).reason == Reason.SEASON_OFF
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, uptime_s=10).reason == Reason.RESTART_HOLD
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, call=False, indoor=5.0).reason == Reason.FROST  # frost by the room thermometer
    sup = Supervisor(cfg(control="tpi"))
    assert step(sup, 0, call=False, floor=7.0).reason == Reason.FROST  # no room thermometer: by the floor


def test_no_boost_and_regulator_held():
    sup = Supervisor(cfg(system="radiator_single", source="onoff_boiler", control="pid", boost_enabled=True))
    d = step(sup, 0, call=True, indoor=15.0, floor=None)
    assert d.reason == Reason.THERMOSTAT_CALL
    assert sup.regulator.integral == 0.0


def test_floor_limit_wins():
    sup = Supervisor(cfg(control="tpi"))  # electric floor: 27 °C
    d = step(sup, 0, call=True, floor=27.5)
    assert d.reason == Reason.FLOOR_LIMIT and not d.output


def test_tempering_while_idle():
    # 0.39.3: without a room thermometer only the absolute night value tempers (tests/test_fixes_392.py)
    sup = Supervisor(cfg(control="tpi", floor_temper=True))
    d = step(sup, 0, call=False, floor=21.0)
    assert d.reason == Reason.THERMOSTAT_IDLE and not d.output
    sup = Supervisor(cfg(control="tpi", floor_temper=True))
    d = step(sup, 0, call=False, indoor=22.5, floor=21.0)  # a room thermometer above the margin stops it
    assert d.reason == Reason.THERMOSTAT_IDLE and not d.output


def test_without_the_option_the_contact_is_ignored():
    sup = Supervisor(cfg(control="tpi", demand_contact=False))
    d = step(sup, 0, call=True, indoor=25.0)
    assert d.reason == Reason.AT_TARGET


# --- through the coordinator, with no room thermometer ---------------------------------------------------
def _entry(**data):
    base = {"name": "Mat", "role": "standalone", "heat_source": "electric_heater", "system": "floor_single",
            "control": "tpi", "actuator_entity": "switch.mat", "floor_entity": "sensor.floor",
            "demand_entity": "binary_sensor.wall", "mode": "shadow"}
    return SimpleNamespace(data={**base, **data}, options={}, entry_id="e380", title="Mat", domain="hc_thermostat",
                           async_on_unload=lambda f: None)


def test_coordinator_runs_without_an_indoor_entity():
    pytest.importorskip("homeassistant")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from homeassistant.core import HomeAssistant
    from homeassistant.util import dt as dt_util
    from custom_components.hc_thermostat.coordinator import HcCoordinator
    from custom_components.hc_thermostat.info import jsonable

    async def run():
        hass = HomeAssistant(tempfile.mkdtemp())
        try:
            c = HcCoordinator(hass, _entry())
            assert c.cfg.demand_contact and c.cfg.floor_system
            c._started = dt_util.utcnow() - timedelta(hours=1)
            hass.states.async_set("sensor.floor", "22.0")
            hass.states.async_set("switch.mat", "off")
            hass.states.async_set("binary_sensor.wall", "on")
            d = await c._async_update_data()
            assert d.reason == Reason.THERMOSTAT_CALL and d.output and d.indoor is None
            hass.states.async_set("binary_sensor.wall", "off")
            d = await c._async_update_data()
            assert d.reason == Reason.THERMOSTAT_IDLE
            hass.states.async_set("binary_sensor.wall", "unavailable")
            d = await c._async_update_data()
            assert d.reason == Reason.SENSOR_LOST and d.details.get("floor_fallback")
            assert jsonable(c.last_inputs)["call"] is None
            explain(d, "hu")
            await c.async_backfill()  # no indoor entity: nothing to seed, no error
            await c.async_backfill_rooms()
        finally:
            await hass.async_stop(force=True)

    asyncio.run(run())

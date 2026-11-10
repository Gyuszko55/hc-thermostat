"""0.27.0: a central modulating boiler with zones – every zone asks for a flow by its own curve, the boiler gets
the highest request of the open asking zones."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from core.central import CentralBoiler, CentralConfig, ZoneState
from core.curve import flow_request
from core.matrix import default_curve
from core.model import HcConfig

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
cc = importlib.import_module("hc_thermostat.central_coordinator")

T0 = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)


def zone(name, flow=None, wants=True, opened=True, trv=True):
    return ZoneState(name, wants, demand=0.5 if wants else 0.0, valve_open=(True if opened else False) if wants else None,
                     valve_on_since=T0 if wants else None, trv=trv, flow_request=flow)


def test_the_highest_request_of_the_open_zones_sets_the_flow():
    boiler = CentralBoiler(CentralConfig(central_flow_min=25, central_flow_max=75))
    d = boiler.step(T0, [zone("floor", 32.0), zone("radiators", 58.5), zone("idle", 70.0, wants=False)])
    assert d.output and d.flow_setpoint == 58.5
    assert d.details["flow_by"] == "radiators" and d.details["flow_requests"] == {"floor": 32.0, "radiators": 58.5}


def test_a_zone_whose_valve_is_still_closed_does_not_set_the_flow():
    boiler = CentralBoiler()
    d = boiler.step(T0, [zone("floor", 32.0), zone("radiators", 60.0, opened=False)])
    assert d.output and d.flow_setpoint == 32.0


def test_no_request_uses_the_default_and_the_limits_hold():
    boiler = CentralBoiler(CentralConfig(central_flow_default=50, central_flow_max=65))
    assert boiler.step(T0, [zone("old")]).flow_setpoint == 50.0  # a zone without the attribute (older HC)
    boiler = CentralBoiler(CentralConfig(central_flow_max=65))
    assert boiler.step(T0, [zone("cold", 80.0)]).flow_setpoint == 65.0


def test_no_flow_while_the_boiler_is_off():
    boiler = CentralBoiler()
    d = boiler.step(T0, [zone("floor", 32.0, wants=False)])
    assert not d.output and d.flow_setpoint is None and "flow_by" not in d.details


def test_zone_flow_request_follows_its_curve():
    floor = HcConfig.from_mapping({k: v for k, v in default_curve("floor_zones", "modulating_boiler").items()})
    rad = HcConfig.from_mapping({k: v for k, v in default_curve("radiator_zones", "modulating_boiler").items()})
    # 21 °C target, 0 °C outside, room at target: floor 21 + 0.5 × 21 = 31.5, radiators 21 + 1.4 × 21 = 50.4
    assert flow_request(floor, 21.0, 21.0, 0.0) == 31.5
    assert flow_request(rad, 21.0, 21.0, 0.0) == 50.4
    assert flow_request(rad, 21.0, 20.0, 0.0) == 53.4  # one degree short: + room_kp
    assert flow_request(floor, 21.0, 21.0, -40.0) == 45.0  # clamped to the floor's flow_max
    assert flow_request(rad, 21.0, None, 0.0) is None


def test_read_zones_takes_the_flow_request():
    attrs = {"hvac_action": "heating", "control_type": "tpi", "demand": 60, "fault": False, "flow_request": 33.5}
    states = {"climate.floor": SimpleNamespace(state="heat", attributes=attrs)}
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: states.get(e)))
    zones = cc.read_zones(hass, ["climate.floor"], {}, T0)
    assert zones[0].flow_request == 33.5
    attrs.pop("flow_request")
    assert cc.read_zones(hass, ["climate.floor"], {}, T0 + timedelta(seconds=30))[0].flow_request is None

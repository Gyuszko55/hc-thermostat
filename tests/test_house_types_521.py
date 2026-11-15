"""0.52.1: the defaults checked on two more house types – a heavy house on a floor slab and a light, fast house –
besides the radiator house they were tuned on (tests/sim.py `HOUSES`).

What the simulator found and this release fixes:
- the frozen-thermometer check took a working 0.1 °C thermometer on a slab for lost for a third of the time
  (a regulated room shows one value for up to 17 h there): floors no longer judge a value near the target;
- the heat of the last two hours before a lowering arrives after it on a slab: floors hold 2 h (was 30 min);
- a light house lost ~0.8 °C in the 30 minutes held before a lowering: with τ known the hold stops at
  `pre_change_sag`.
"""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.matrix import default_timing, source_defaults
from core.model import HcConfig, Reason
from sim import HOUSES, Run, light_house, radiator_house, slab_house

SYSTEM = {"radiator": ("radiator_single", "onoff_boiler"), "slab": ("floor_single", "onoff_boiler"),
          "light": ("fan_coil", "heat_pump")}
BASE = dict(target_home=21.0, night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def _cfg(kind, **kw) -> HcConfig:
    system, source = SYSTEM[kind]
    return HcConfig.from_mapping({"control": "tpi", **source_defaults(system, source), **BASE,
                                  **default_timing(system, source), **kw})


# --- the three houses ------------------------------------------------------------------------------------------------
def test_the_houses_differ_as_intended():
    rise = {}
    for kind, make in HOUSES.items():
        heated, cold = make(indoor=20.0, outdoor=0.0), make(indoor=20.0, outdoor=0.0)
        for _ in range(120):  # one hour at full power, against the same house unheated
            heated.advance(True)
            cold.advance(False)
        rise[kind] = heated.indoor - cold.indoor
    assert rise["light"] > rise["radiator"] > rise["slab"] > 0
    assert rise["slab"] < 0.15  # the screed takes the first hour's heat
    slab = slab_house(indoor=21.0)
    slab.radiator = 0.5
    for _ in range(240):  # two hours off: the screed still gives heat
        slab.advance(False)
    assert slab.radiator > 0.3


# --- 1. the frozen check --------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", list(HOUSES))
@pytest.mark.parametrize("control", ["tpi", "pid"])
@pytest.mark.parametrize("outdoor", [-15.0, 0.0, 10.0])
def test_a_working_thermometer_is_never_taken_for_frozen(kind, control, outdoor):
    run = Run(_cfg(kind, control=control), HOUSES[kind](indoor=21.0, outdoor=outdoor), resolution=0.1)
    run.run(hours=72)
    assert not any((d.details or {}).get("indoor_frozen") for d in run.decisions)
    assert all(d.indoor is not None for d in run.decisions)


def test_the_heat_pump_on_a_slab_neither():
    cfg = HcConfig.from_mapping({"control": "onoff", **source_defaults("floor_single", "heat_pump"), **BASE,
                                 **default_timing("floor_single", "heat_pump")})
    for outdoor in (-15.0, 10.0):
        run = Run(cfg, slab_house(indoor=21.0, outdoor=outdoor), resolution=0.1)
        run.run(hours=72)
        assert not any((d.details or {}).get("indoor_frozen") for d in run.decisions)


def test_before_the_fix_the_slab_lost_its_thermometer():
    """The old rule (no band) on the same house: hours of a working thermometer counted as lost."""
    run = Run(_cfg("slab", frozen_band=0.0, frozen_after_h=3.0), slab_house(indoor=21.0, outdoor=0.0), resolution=0.1)
    run.run(hours=72)
    assert sum(1 for d in run.decisions if d.indoor is None) > 120 * 5


class _Stuck(Run):
    """A thermometer that stopped at one value: the room itself goes on."""

    stuck: float = 19.0

    def _reading(self) -> float:
        return self.stuck


@pytest.mark.parametrize("kind", list(HOUSES))
def test_a_stuck_thermometer_far_from_the_target_is_still_found(kind):
    hours = 8 if kind == "slab" else 3  # a floor waits longer: a cold screed warms the room that slowly
    assert _cfg(kind).frozen_after_h == hours
    run = _Stuck(_cfg(kind), HOUSES[kind](indoor=19.0, outdoor=0.0), resolution=0.1)
    run.run(hours=hours + 1)
    found = [d for d in run.decisions if (d.details or {}).get("indoor_frozen")]
    assert found and found[0].now - run.decisions[0].now <= timedelta(hours=hours, minutes=5)


@pytest.mark.parametrize("outdoor", [-20.0, -15.0, 0.0])
@pytest.mark.parametrize("start", [15.0, 18.0, 21.0])
def test_a_cold_slab_warming_up_is_not_taken_for_frozen(outdoor, start):
    """Warming up at full power from a cold screed, the room may show one value far below the target for 5 h."""
    run = Run(_cfg("slab", control="pid"), slab_house(indoor=start, outdoor=outdoor), resolution=0.1)
    run.run(hours=48)
    assert not any((d.details or {}).get("indoor_frozen") for d in run.decisions)


# --- 2. the hold before a lowering -------------------------------------------------------------------------------------
def _evening(kind, **kw):
    """Home target 21 until 22:00, then 18; from 10:00, the room at 21."""
    cfg = _cfg(kind, night_start="22:00", night_end="06:00", target_night=18.0, **kw)
    run = Run(cfg, HOUSES[kind](indoor=21.0, outdoor=0.0))
    run.now = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
    run.run(hours=14)
    change = run.now - timedelta(hours=2)
    last_hour = [d for d in run.decisions if change - timedelta(hours=1) <= d.now < change]
    at = next(d for d in run.decisions if d.now >= change)
    return run, sum(30 for d in last_hour if d.output) / 60, at.indoor


def test_the_slab_holds_two_hours_before_a_lowering():
    assert source_defaults("floor_single", "heat_pump")["pre_change_s"] == 7200.0
    _, burn, at = _evening("slab")
    _, burn_old, at_old = _evening("slab", pre_change_s=1800.0)
    assert burn == 0 and burn_old >= 30  # 30 min was shorter than one cycle: the last start still came
    assert at_old - at < 0.2  # and costs little: the screed keeps the room


def test_a_light_house_does_not_sag_more_than_allowed_with_tau_known():
    _, _, sagged = _evening("light")  # no τ: the 0.48.3 hold, the room loses ~0.8 °C
    _, _, kept = _evening("light", house_tau_h=12.0)
    assert sagged < 20.0 and kept > 20.2


def test_the_radiator_house_is_unchanged():
    run, burn, at = _evening("radiator", house_tau_h=72.0)
    assert burn == 0 and abs(at - 20.69) < 0.05  # as in 0.52.0


# --- 3. the boost ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", list(HOUSES))
def test_a_boost_never_overshoots(kind):
    run = Run(_cfg(kind, boost_enabled=True), HOUSES[kind](indoor=19.0, outdoor=0.0))
    run.run(hours=12)
    assert any(d.reason == Reason.BOOST for d in run.decisions)
    assert max(d.indoor for d in run.decisions) <= 21.3


# --- the settings show a floor's defaults ---------------------------------------------------------------------------------
def test_the_settings_show_the_floor_hold():
    root = Path(__file__).resolve().parents[1] / "custom_components"
    sys.path.insert(0, str(root))
    cf = importlib.import_module("hc_thermostat.config_flow")
    flow = cf.HcOptionsFlow()
    entry = SimpleNamespace(data={"role": "standalone", "control": "tpi", "heat_source": "onoff_boiler",
                                  "system": "floor_single", "indoor_entity": "sensor.n", "actuator_entity": "switch.r"},
                            options={"mode": "shadow"}, title="Floor", entry_id="f1")
    type(flow).config_entry = property(lambda self: entry)
    flow.hass = None
    flow.async_show_form = lambda **kw: ("form", kw)
    schema = asyncio.run(flow.async_step_settings())[1]["data_schema"]
    marker = next(k for k in schema.schema if str(k) == "regulation")
    hold = next(k for k in schema.schema[marker].schema.schema if str(k) == "pre_change_s")
    assert hold.default() == 7200.0

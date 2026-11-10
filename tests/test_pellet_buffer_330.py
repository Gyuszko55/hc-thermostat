"""0.33.0: pellet boiler (on/off with long runs) and the buffer tank role (charges the tank by its temperatures)."""

from datetime import datetime, timedelta, timezone

from core.boiler_health import health_kind
from core.buffer import BufferCharger, BufferConfig
from core.matrix import Status, cell, controls, default_timing, source_defaults
from core.model import HcConfig, Inputs, Reading
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 6, 0, tzinfo=timezone.utc)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


# --- pellet boiler -----------------------------------------------------------------------------------------------
def test_pellet_matrix_controls_and_timing():
    assert cell("radiator_single", "pellet_boiler").status == Status.RECOMMENDED
    assert "puffer" in cell("floor_single", "pellet_boiler").text_hu
    assert controls("pellet_boiler") == ["onoff", "external"]
    assert default_timing("radiator_single", "pellet_boiler") == {"cycle_s": 3600.0, "min_on_s": 2700.0, "min_off_s": 1200.0}
    assert health_kind("pellet_boiler") == "pellet"
    assert "heat_pump" not in source_defaults("radiator_single", "pellet_boiler")


def test_pellet_runs_long():
    cfg = HcConfig.from_mapping({**default_timing("radiator_single", "pellet_boiler"), "control": "onoff",
                                 "night_start": "00:00", "night_end": "00:00", "season_enabled": False, "learning_enabled": False})
    sup = Supervisor(cfg)
    assert sup.step(Inputs(now=at(0), indoor=Reading(20.0), outdoor=Reading(0.0))).output
    d = sup.step(Inputs(now=at(20), indoor=Reading(21.5), outdoor=Reading(0.0)))  # warm already, but 45 minutes at least
    assert d.output and d.limited_by == "min_on"
    assert not sup.step(Inputs(now=at(46), indoor=Reading(21.5), outdoor=Reading(0.0))).output
    d = sup.step(Inputs(now=at(50), indoor=Reading(20.0), outdoor=Reading(0.0)))  # cold again, but 20 minutes pause
    assert not d.output and d.limited_by == "min_off"


# --- buffer tank -------------------------------------------------------------------------------------------------
def test_buffer_charges_from_low_to_full():
    b = BufferCharger()
    assert b.step(at(0), 50.0, 40.0).reason == "ready"
    d = b.step(at(1), 45.0, 35.0)
    assert d.output and d.reason == "charging"
    assert b.step(at(30), 60.0, 50.0).output  # keeps on until full, whatever the top says
    d = b.step(at(60), 70.0, 65.0)
    assert not d.output and d.reason == "full"


def test_one_sensor_uses_the_top_for_full():
    b = BufferCharger()
    assert b.step(at(0), 40.0, None).output
    assert b.step(at(40), 66.0, None).reason == "full"


def test_demand_led_waits_for_a_zone():
    b = BufferCharger()
    d = b.step(at(0), 40.0, 30.0, asking=(), zones_given=True)
    assert not d.output and d.reason == "waiting_demand"
    d = b.step(at(1), 40.0, 30.0, asking=("climate.nappali",), zones_given=True)
    assert d.output and d.asking == ("climate.nappali",)
    assert b.step(at(10), 50.0, 40.0, asking=(), zones_given=True).output  # the zone is satisfied: still fills up


def test_pause_between_charges_and_frost():
    b = BufferCharger(BufferConfig(buffer_min_off_s=1200))
    b.step(at(0), 40.0, 30.0)
    b.step(at(30), 70.0, 66.0)  # full
    assert b.step(at(40), 44.0, 35.0).reason == "min_off"
    assert b.step(at(51), 44.0, 35.0).output
    f = BufferCharger(BufferConfig(buffer_demand_led=True))
    d = f.step(at(0), 6.0, 5.0, asking=(), zones_given=True)
    assert d.output and d.reason == "frost"


def test_no_sensor_no_charge():
    b = BufferCharger()
    b.step(at(0), 40.0, 30.0)
    d = b.step(at(1), None, 30.0)
    assert not d.output and d.reason == "no_sensor"


def test_restore():
    b = BufferCharger()
    b.step(at(0), 40.0, 30.0)
    again = BufferCharger()
    again.restore(b.state())
    assert again.output and again.step(at(5), 50.0, 40.0).reason == "charging"

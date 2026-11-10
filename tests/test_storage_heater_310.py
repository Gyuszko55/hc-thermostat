"""0.31.0: storage heater on controlled power – night charge by the outdoor average, timed to the end of the window,
discharge by the room; electric heat waits while the controlled power is off."""

from datetime import datetime, timezone

from core.matrix import Status, cell, controls
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.storage import charge_fraction, window
from core.supervisor import Supervisor

TZ = timezone.utc
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def t(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=TZ)


def test_window_over_midnight():
    assert window(t(10, 23), "22:00", "06:00") == (t(10, 22), t(11, 6))
    assert window(t(11, 3), "22:00", "06:00") == (t(10, 22), t(11, 6))
    assert window(t(11, 12), "22:00", "06:00") == (t(11, 22), t(12, 6))  # by day: tonight's window
    assert window(t(11, 12), "13:00", "15:00") == (t(11, 13), t(11, 15))
    assert window(t(11, 16), "13:00", "15:00") == (t(12, 13), t(12, 15))


def test_charge_fraction():
    assert charge_fraction(21.0, 3.0, -15.0) == 0.5  # 18 of 36 degrees
    assert charge_fraction(21.0, -20.0, -15.0) == 1.0
    assert charge_fraction(21.0, 22.0, -15.0) == 0.0
    assert charge_fraction(21.0, None, -15.0) == 1.0  # no outdoor reading: full (safe side)
    assert charge_fraction(21.0, 3.0, -15.0, bias=0.2) == 0.7


def test_matrix():
    assert cell("room_unit", "storage_heater").status == Status.RECOMMENDED
    assert cell("radiator_single", "storage_heater").status == Status.NOT_RECOMMENDED
    assert controls("storage_heater") == ["storage"]


def storage(**kw):
    return Supervisor(HcConfig.from_mapping({**DAY, "control": "storage", "target_home": 21.0, "storage_charge_h": 8.0,
                                             "curve_design_outdoor": -15.0, **kw}))


def step(s, now, indoor=20.0, avg=3.0, power=None, enabled=True, window_open=False):
    return s.step(Inputs(now=now, indoor=Reading(indoor), outdoor=Reading(avg), outdoor_avg=avg,
                         power_available=power, enabled=enabled, window_open=window_open))


def test_charge_is_timed_to_the_end_of_the_window():
    s = storage()
    d = step(s, t(10, 23))  # half charge (4 h) of an 8 h window 22–06: starts at 02:00
    assert d.reason == Reason.STORAGE_WAIT and not d.output
    assert d.details["charge_start"] == "02:00" and d.details["charge_fraction"] == 0.5
    assert "Következő feltöltés: 50 %, 02:00–06:00" in explain(d, "hu")
    d = step(s, t(11, 2, 30))
    assert d.reason == Reason.STORAGE_CHARGE and d.output and "50 %-ra tölt, 06:00-ig" in explain(d, "hu")
    assert not step(s, t(11, 6, 1)).output


def test_the_fraction_is_fixed_once_charging():
    s = storage()
    assert step(s, t(11, 2, 30), avg=3.0).output  # 50 % → 02:00–06:00
    d = step(s, t(11, 2, 45), avg=12.0)  # warmer average would mean 25 % (from 04:00)
    assert d.output and d.details["charge_fraction"] == 0.5


def test_no_controlled_power_no_charge():
    s = storage()
    d = step(s, t(11, 3), power=False)
    assert not d.output and d.details["charge_why"] == "no_power" and "nincs vezérelt áram" in explain(d, "hu")
    assert step(s, t(11, 3, 5), power=True).output


def test_warm_day_and_summer_no_charge():
    s = storage()
    d = step(s, t(11, 3), avg=22.0)
    assert not d.output and "Ma éjjel nem kell feltölteni" in explain(d, "hu")
    s = storage(season_enabled=True)
    s.season_on = False
    assert not step(s, t(11, 3), avg=20.0).output


def test_discharge_follows_the_room():
    s = storage()
    assert step(s, t(11, 12), indoor=20.6).details["discharge"]  # 0.4 below 21: fan on
    assert step(s, t(11, 12, 5), indoor=20.9).details["discharge"]  # still below the target: keeps on
    assert not step(s, t(11, 12, 10), indoor=21.0).details["discharge"]
    step(s, t(11, 12, 15), indoor=20.0, window_open=True)
    assert not step(s, t(11, 12, 30), indoor=20.0, window_open=True).details["discharge"]  # after the window delay


def test_frost_charges_and_discharges_whenever_there_is_power():
    s = storage()
    d = step(s, t(11, 12), indoor=5.0, power=True)
    assert d.reason == Reason.FROST and d.output and d.details["discharge"]
    assert not step(s, t(11, 12, 5), indoor=5.0, power=False).output


# --- controlled power for direct electric heat ---------------------------------------------------------------------
def test_electric_heater_waits_for_the_controlled_power():
    s = Supervisor(HcConfig.from_mapping({**DAY, "control": "pid", "cycle_s": 600, "min_on_s": 120, "min_off_s": 120}))
    d = s.step(Inputs(now=t(11, 12), indoor=Reading(18.0), outdoor=Reading(0.0), power_available=False))
    assert not d.output and d.limited_by == "no_power" and "vezérelt áram most nincs" in explain(d, "hu")
    assert s.regulator.integral == 0.0  # no wind-up while waiting
    d = s.step(Inputs(now=t(11, 12, 1), indoor=Reading(18.0), outdoor=Reading(0.0), power_available=True))
    assert d.output

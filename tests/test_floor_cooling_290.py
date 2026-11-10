"""0.29.0: floor cooling by a reversible heat pump in summer, never below the dew point (+ margin)."""

from datetime import datetime, timedelta, timezone

from core.cooling import dew_point
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 7, 10, 14, 0, tzinfo=timezone.utc)
SUMMER = dict(night_start="00:00", night_end="00:00", learning_enabled=False, heat_pump=True, floor_cooling=True,
              hp_min_on_s=1200, hp_min_off_s=600)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


def sup(control="curve", **kw):
    s = Supervisor(HcConfig.from_mapping({**SUMMER, "control": control, **kw}))
    s.season_on = False  # a hot summer day: the heating season rests
    return s


def step(s, minute, indoor=27.0, rh=50.0, floor=None):
    return s.step(Inputs(now=at(minute), indoor=Reading(indoor), outdoor=Reading(30.0),
                         humidity=Reading(rh) if rh is not None else Reading(),
                         floor=Reading(floor) if floor is not None else Reading()))


def test_dew_point():
    assert dew_point(26.0, 50.0) == 14.8
    assert dew_point(26.0, 70.0) == 20.1
    assert dew_point(20.0, 100.0) == 20.0
    assert dew_point(26.0, 0.0) is None and dew_point(26.0, 120.0) is None


def test_curve_cools_with_the_set_flow_when_the_air_is_dry():
    d = step(sup(), 0, indoor=27.0, rh=40.0)  # dew point 12.2 °C: 18 °C water is safe
    assert d.reason == Reason.FLOOR_COOL and d.output and d.flow_setpoint == 18.0
    assert d.details["mode"] == "cool" and d.details["dew_point"] == 12.2
    assert "Padlóhűtés: cél 26 °C. Harmatpont 12,2 °C" in explain(d, "hu")


def test_humid_air_raises_the_flow():
    d = step(sup(), 0, indoor=27.0, rh=55.0)  # dew point 17.2 → safe flow 19.2 → 19.5 °C
    assert d.output and d.flow_setpoint == 19.5 and d.details["safe_flow"] == 19.2


def test_too_humid_stops_at_once():
    s = sup()
    assert step(s, 0, indoor=27.0, rh=55.0).output
    d = step(s, 1, indoor=27.0, rh=70.0)  # dew point 21.1 → safe 23.1 > 22: water this warm would hardly cool
    assert d.reason == Reason.DEW_POINT and not d.output and d.flow_setpoint is None
    assert d.details["why"] == "humid" and "Túl párás" in explain(d, "hu")  # within the 20 min minimum run: stopped anyway


def test_no_humidity_no_cooling():
    d = step(sup(), 0, indoor=28.0, rh=None)
    assert d.reason == Reason.DEW_POINT and not d.output and "Nincs friss páratartalom" in explain(d, "hu")


def test_the_floor_sensor_stops_the_cooling_and_resumes_with_hysteresis():
    s = sup()
    assert step(s, 0, indoor=27.0, rh=50.0, floor=22.0).output  # dew 15.9 → safe 17.9; floor min 19
    d = step(s, 1, indoor=27.0, rh=50.0, floor=19.0)
    assert d.reason == Reason.DEW_POINT and d.details["why"] == "floor" and d.details["floor_limit"] == 19.0
    d = step(s, 20, indoor=27.0, rh=50.0, floor=19.3)
    assert d.reason == Reason.DEW_POINT  # within 0.5 °C: still paused
    d = step(s, 30, indoor=27.0, rh=50.0, floor=19.6)
    assert d.reason == Reason.FLOOR_COOL and d.output


def test_onoff_needs_the_floor_sensor():
    d = step(sup("onoff"), 0, indoor=27.0, rh=40.0)
    assert d.reason == Reason.DEW_POINT and d.details["why"] == "no_floor" and not d.output
    d = step(sup("onoff"), 0, indoor=27.0, rh=40.0, floor=23.0)
    assert d.reason == Reason.FLOOR_COOL and d.output and d.flow_setpoint is None


def test_room_hysteresis_and_minimum_run():
    s = sup()
    assert not step(s, 0, indoor=26.3).output  # below target + 0.5: no cooling yet
    assert step(s, 1, indoor=26.6).output
    d = step(s, 10, indoor=25.4)  # cool enough, but the heat pump runs at least 20 minutes
    assert d.output and d.reason == Reason.FLOOR_COOL and d.limited_by == "min_on"
    d = step(s, 25, indoor=25.4)
    assert not d.output and d.reason == Reason.SEASON_OFF and d.details["mode"] == "cool"


def test_without_floor_cooling_summer_stays_a_rest():
    s = sup(floor_cooling=False)
    d = step(s, 0, indoor=29.0)
    assert d.reason == Reason.SEASON_OFF and not d.output and "mode" not in d.details


def test_heating_season_is_untouched():
    s = sup()
    s.season_on = True
    d = s.step(Inputs(now=at(0), indoor=Reading(19.0), outdoor=Reading(0.0), humidity=Reading(50.0)))
    assert d.reason == Reason.REGULATING and "mode" not in d.details

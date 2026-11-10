"""0.5.0: the boost stops on a forecast of the after-heat, then waits for it."""

from datetime import timedelta

from core.messages import explain
from core.model import HcConfig, Reason
from core.supervisor import Supervisor
from sim import House, Run, START

CFG = HcConfig(target_home=23.0, night_start="00:00", night_end="00:00", season_enabled=False,
               boost_enabled=True, cycle_s=1800, min_on_s=300, min_off_s=300)


def _house(indoor=21.7):
    # Like the real house: 17.3 kW boiler, 74.5 W/K loss -> 232 K at full power; a 72 h time constant
    # gives the measured ~0.04-0.05 °C/min rise, and the radiators add 0.5-0.8 °C after-heat.
    return House(indoor=indoor, outdoor=8.0, loss_tau_s=72 * 3600.0, full_power_delta=232.0, radiator_tau_s=900.0)


def test_boost_starts_from_08_degrees():
    run = Run(CFG, _house(indoor=22.2))
    assert run.tick().reason == Reason.BOOST
    run = Run(CFG, _house(indoor=22.3))
    assert run.tick().reason != Reason.BOOST


def test_boost_reaches_target_fast_with_small_overshoot():
    run = Run(CFG, _house())
    run.run(hours=3)
    temps = [d.indoor for d in run.decisions]
    reasons = [d.reason for d in run.decisions]
    assert Reason.BOOST in reasons and Reason.AFTERHEAT in reasons
    assert max(temps) <= CFG.target_home + 0.3
    reached = next(i for i, t in enumerate(temps) if t >= CFG.target_home - 0.2)
    assert reached * 30 / 60 <= 60  # within an hour from 1.3 °C below


def test_boost_stops_before_the_target_itself():
    run = Run(CFG, _house())
    first_after = None
    for _ in range(240):
        d = run.tick()
        if d.reason != Reason.BOOST:
            first_after = d
            break
    assert first_after is not None
    assert first_after.indoor < CFG.target_home  # the after-heat does the rest


def test_no_new_burn_during_after_heat():
    run = Run(CFG, _house())
    run.run(hours=2)
    quiet = [d for d in run.decisions if d.reason == Reason.AFTERHEAT]
    assert quiet and not any(d.output for d in quiet[2:])  # min_on may finish the last minutes of the boost


def test_only_flame_minutes_count():
    run = Run(CFG, _house())
    d = run.run(minutes=10, actual=False)  # relay on, but the burner does not light
    assert d.reason == Reason.BOOST
    assert d.details["flame_min"] == 0.0
    assert d.details["forecast"] == round(d.indoor, 2)


def test_boost_text_names_forecast_and_latest_end():
    run = Run(CFG, _house())
    d = run.run(minutes=5)
    text = explain(d, "hu")
    assert "várható" in text and "legkésőbb" in text and ":" in text


def test_quiet_ends_when_the_house_cools_again():
    sup = Supervisor(CFG)
    now = START
    sup._end_boost(now, 22.5, 23.0)
    assert sup._quiet(now + timedelta(minutes=5), 23.0, 22.6) is True
    assert sup._quiet(now + timedelta(minutes=6), 23.0, 22.35) is False


def test_quiet_ends_when_the_target_changes():
    sup = Supervisor(CFG)
    sup._end_boost(START, 22.5, 23.0)
    assert sup._quiet(START + timedelta(minutes=1), 21.0, 22.6) is False


def test_quiet_waits_while_still_rising_but_not_forever():
    sup = Supervisor(CFG)
    sup._end_boost(START, 22.0, 23.0)
    temp = 22.0
    for minute in range(1, 61):
        temp += 0.01
        quiet = sup._quiet(START + timedelta(minutes=minute), 23.0, temp)
        if minute < 60:
            assert quiet is True
    assert quiet is False  # the 60 minute cap

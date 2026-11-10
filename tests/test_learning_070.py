"""0.7.0: the supervisor learns the after-heat of a boost and how hard the TPI has to push."""

from datetime import datetime, timedelta, timezone

from core.learning import Learner, band
from core.model import HcConfig, Reason
from core.supervisor import Supervisor
from sim import House, Run, START

CFG = HcConfig(target_home=23.0, night_start="00:00", night_end="00:00", season_enabled=False,
               boost_enabled=True, cycle_s=1800, min_on_s=300, min_off_s=300)


def _house(indoor=21.7, radiator_tau_s=900.0):
    return House(indoor=indoor, outdoor=8.0, loss_tau_s=72 * 3600.0, full_power_delta=232.0,
                 radiator_tau_s=radiator_tau_s)


def _boost_once(run, hours=3):
    run.run(hours=hours)
    return [d for d in run.decisions if d.reason == Reason.BOOST]


def test_a_clean_boost_teaches_the_after_heat():
    run = Run(CFG, _house(radiator_tau_s=1500.0))  # slower radiators: more after-heat than the 0.8 assumed
    _boost_once(run)
    learned = run.sup.learner.learned
    assert learned.boosts == 1
    assert band(8.0) == "mild"
    assert learned.afterheat["mild"] != CFG.boost_afterheat
    assert learned.last_boost["used"] is True
    assert 5.0 <= learned.minutes_per_degree["mild"] <= 60.0


def test_learning_reduces_the_overshoot_of_the_next_boost():
    house = _house(radiator_tau_s=2400.0)  # much more after-heat than assumed: the first boost overshoots
    run = Run(CFG, house)
    run.run(hours=3)
    first_peak = max(d.indoor for d in run.decisions)
    overshoots = [first_peak - CFG.target_home]
    for _ in range(3):
        house.indoor = 21.7
        house.radiator = 0.0
        run.decisions.clear()
        run.sup._boost_armed = True
        run.run(hours=3)
        overshoots.append(max(d.indoor for d in run.decisions) - CFG.target_home)
    assert run.sup.learner.learned.boosts >= 3
    assert overshoots[-1] < overshoots[0]


def test_a_window_during_the_after_heat_teaches_nothing():
    run = Run(CFG, _house())
    while run.tick().reason != Reason.AFTERHEAT:
        pass
    run.house.window_open = True
    run.run(minutes=5)
    run.house.window_open = False
    run.run(hours=2)
    assert run.sup.learner.learned.boosts == 0


def test_short_boost_teaches_nothing():
    learner = Learner(CFG)
    learner.boost_started(START, 23.0, 22.2, 8.0)
    learner.observe(22.5, 23.0, False)
    learner.boost_stopped(22.5, 3.0)
    learner.observe(22.9, 23.0, False)
    learner.boost_finished(peak_found=True)
    assert learner.learned.boosts == 0 and learner.learned.last_boost["used"] is False


def test_steps_are_bounded():
    learner = Learner(CFG)
    learner.boost_started(START, 23.0, 21.0, 8.0)
    learner.observe(21.1, 23.0, False)
    learner.boost_stopped(21.1, 30.0)
    temp = 21.1
    while temp < 23.6:  # a huge after-heat of 2.5 °C, risen step by step
        temp += 0.1
        learner.observe(temp, 23.0, False)
    learner.boost_finished(peak_found=True)
    assert learner.learned.afterheat["mild"] <= CFG.boost_afterheat + 0.2
    assert learner.learned.trim <= 0.1


def _day_of_regulation(learner, day, error, hours=10):
    t = datetime(2026, 11, day, 8, 0, tzinfo=timezone.utc)
    for _ in range(int(hours * 120)):
        learner.regulating(t, 30.0, 22.0, 22.0 - error)
        t += timedelta(seconds=30)


def test_a_day_well_below_target_makes_the_tpi_stronger():
    learner = Learner(CFG)
    _day_of_regulation(learner, 9, error=0.5)
    _day_of_regulation(learner, 10, error=0.0, hours=0.1)  # the next day closes the first
    assert learner.tpi_coef_int == CFG.tpi_coef_int + 0.1
    assert 0 < learner.tpi_offset <= 0.05
    assert learner.learned.days == 1


def test_a_day_with_overshoot_makes_the_tpi_softer():
    learner = Learner(CFG)
    _day_of_regulation(learner, 9, error=-0.4)
    _day_of_regulation(learner, 10, error=0.0, hours=0.1)
    assert learner.tpi_coef_int == CFG.tpi_coef_int - 0.1
    assert -0.05 <= learner.tpi_offset < 0


def test_a_short_day_teaches_nothing():
    learner = Learner(CFG)
    _day_of_regulation(learner, 9, error=0.5, hours=2)
    _day_of_regulation(learner, 10, error=0.0, hours=0.1)
    assert learner.learned.days == 0 and learner.tpi_offset == 0.0


def test_the_morning_heat_up_does_not_count_as_a_shortfall():
    sup = Supervisor(HcConfig(target_home=22.0, target_night=20.0, night_start="22:00", night_end="06:00",
                              season_enabled=False))
    run = Run(sup.cfg, _house(indoor=20.0), sup=sup, now=datetime(2026, 11, 9, 5, 0, tzinfo=timezone.utc))
    run.run(hours=2)  # 06:00 the target goes up by 2 °C
    assert sup.learner._under_s == 0.0


def test_learned_values_survive_a_restart_and_can_be_reset():
    run = Run(CFG, _house(radiator_tau_s=1500.0))
    _boost_once(run)
    saved = run.sup.state()
    fresh = Supervisor(CFG)
    fresh.restore(saved)
    assert fresh.learner.learned.afterheat == run.sup.learner.learned.afterheat
    fresh.learner.reset()
    assert fresh.learner.learned.boosts == 0 and fresh.learner.afterheat(8.0) == CFG.boost_afterheat


def test_learning_switched_off_uses_the_settings():
    run = Run(CFG, _house(radiator_tau_s=1500.0))
    _boost_once(run)
    off = HcConfig(**{**CFG.__dict__, "learning_enabled": False})
    sup = Supervisor(off)
    sup.restore(run.sup.state())
    assert sup.learner.afterheat(8.0) == off.boost_afterheat
    assert sup.learner.tpi_coef_int == off.tpi_coef_int and sup.learner.tpi_offset == 0.0

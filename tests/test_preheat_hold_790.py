"""0.79.0: no short regulating run just before the optimal start (the developer's house, 11-23 and 11-24 mornings:
a 6-minute run 1 and 14 minutes before the morning rise, then the rise waited out the minimum pause – two burner
starts minutes apart)."""

from datetime import datetime, timedelta, timezone

from core.messages import explain
from core.model import HcConfig, Inputs, Presence, Reading
from core.supervisor import Supervisor

LOCAL = timezone(timedelta(hours=1))
BASE = dict(control="pid", pid_kp=0.5, pid_ki_per_hour=0.2, target_home=22.5, target_night=21.0,
            night_start="22:00", night_end="06:00", cycle_s=1800, min_on_s=300, min_off_s=300,
            season_enabled=False, boost_enabled=False, learning_enabled=False,
            house_loss_w_k=100.0, house_gains_kw=0.3, house_tau_h=90.0, optimal_start=True)


def _sup(**kw):
    sup = Supervisor(HcConfig(**{**BASE, **kw}))
    sup.regulator.integral = 0.25  # a small regulating demand, as near the night target
    return sup


def _step(sup, now, room):
    return sup.step(Inputs(now=now, indoor=Reading(room), outdoor=Reading(0.0), presence=Presence.HOME))


def test_no_short_run_just_before_the_morning_rise():
    sup = _sup()
    d = _step(sup, datetime(2026, 11, 24, 5, 0, tzinfo=LOCAL), 20.9)  # the rise needs ~47 min: it starts in ~13
    assert d.target == 21.0 and not d.output and d.limited_by == "preheat_soon"
    assert 0 < d.details["preheat_soon"]["in_min"] <= 20
    assert "reggeli felfűtés" in explain(d, "hu") and "morning rise" in explain(d, "en")
    # a few minutes later the optimal start begins: one start
    for k in range(1, 25):
        d = _step(sup, datetime(2026, 11, 24, 5, k, tzinfo=LOCAL), 20.9)
        if d.target == 22.5:
            break
    assert d.target == 22.5 and d.output


def test_further_out_it_regulates_as_usual():
    d = _step(_sup(), datetime(2026, 11, 24, 4, 20, tzinfo=LOCAL), 20.9)  # the rise is ~50 min away
    assert d.limited_by != "preheat_soon" and d.output


def test_a_cold_room_is_not_held():
    d = _step(_sup(), datetime(2026, 11, 24, 5, 0, tzinfo=LOCAL), 20.6)  # 0.4 °C under: more than 0.3
    assert d.limited_by != "preheat_soon"


def test_it_can_be_switched_off():
    d = _step(_sup(preheat_hold_min=0), datetime(2026, 11, 24, 5, 0, tzinfo=LOCAL), 20.9)
    assert d.limited_by != "preheat_soon"


def test_a_running_burn_is_not_cut():
    sup = _sup()
    d = _step(sup, datetime(2026, 11, 24, 4, 20, tzinfo=LOCAL), 20.9)
    assert d.output
    d = _step(sup, datetime(2026, 11, 24, 4, 52, tzinfo=LOCAL), 20.9)  # new cycle, the relay is still on
    assert d.limited_by != "preheat_soon"

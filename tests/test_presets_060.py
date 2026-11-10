"""0.6.0: standard preset names, targets, and when a preset chosen by hand ends."""

from datetime import datetime, timedelta, timezone

from core.model import HcConfig, Inputs, Presence, Reading, Reason
from core.supervisor import Supervisor

LOCAL = timezone(timedelta(hours=1))
CFG = HcConfig(target_home=22.0, target_night=20.0, target_away=18.0, target_vacation=17.5, target_comfort=23.0,
               target_eco=19.0, night_start="22:00", night_end="06:00", season_enabled=False)
T0 = datetime(2026, 11, 9, 14, 0, tzinfo=LOCAL)


def _step(sup, now, presence=Presence.HOME, indoor=21.0):
    return sup.step(Inputs(now=now, indoor=Reading(indoor), outdoor=Reading(5.0), presence=presence))


def test_each_preset_has_its_target():
    for preset, target in [("comfort", 23.0), ("home", 22.0), ("sleep", 20.0), ("eco", 19.0), ("away", 18.0),
                           ("vacation", 17.5)]:
        sup = Supervisor(CFG)
        sup.set_preset(preset, T0)
        assert _step(sup, T0).target == target, preset


def test_comfort_ends_after_three_hours():
    sup = Supervisor(CFG)
    sup.set_preset("comfort", T0)
    assert sup.preset_until == T0 + timedelta(hours=3)
    assert _step(sup, T0 + timedelta(hours=2, minutes=59)).target == 23.0
    assert _step(sup, T0 + timedelta(hours=3)).target == 22.0
    assert sup.preset is None


def test_home_and_sleep_end_at_the_next_night_start_or_end():
    sup = Supervisor(CFG)
    sup.set_preset("home", T0)
    assert sup.preset_until == datetime(2026, 11, 9, 22, 0, tzinfo=LOCAL)
    night = datetime(2026, 11, 9, 23, 30, tzinfo=LOCAL)
    sup.set_preset("sleep", night)
    assert sup.preset_until == datetime(2026, 11, 10, 6, 0, tzinfo=LOCAL)


def test_eco_lasts_until_changed():
    sup = Supervisor(CFG)
    sup.set_preset("eco", T0)
    assert _step(sup, T0 + timedelta(days=3)).target == 19.0
    sup.set_preset("auto", T0 + timedelta(days=3))
    assert _step(sup, T0 + timedelta(days=3, seconds=30)).target == 22.0


def test_away_ends_when_someone_arrives():
    sup = Supervisor(CFG)
    _step(sup, T0)
    sup.set_preset("away", T0)
    assert _step(sup, T0 + timedelta(minutes=1)).target == 18.0  # still home, chosen before leaving
    assert _step(sup, T0 + timedelta(minutes=30), presence=Presence.AWAY).target == 18.0
    assert _step(sup, T0 + timedelta(hours=4), presence=Presence.HOME).target == 22.0
    assert sup.preset is None


def test_choosing_a_preset_clears_a_manual_target():
    sup = Supervisor(CFG)
    _step(sup, T0)
    sup.manual_target = 24.0
    assert _step(sup, T0 + timedelta(minutes=1)).target == 24.0
    sup.set_preset("eco", T0 + timedelta(minutes=2))
    decision = _step(sup, T0 + timedelta(minutes=3))
    assert decision.target == 19.0 and decision.manual is False


def test_manual_target_under_a_timed_preset_ends_with_the_preset():
    sup = Supervisor(CFG)
    sup.set_preset("comfort", T0)
    _step(sup, T0)
    sup.manual_target = 23.5
    assert _step(sup, T0 + timedelta(minutes=1)).manual_until == T0 + timedelta(hours=3)


def test_boost_preset_starts_one_boost_and_keeps_the_preset():
    cfg = HcConfig(**{**CFG.__dict__, "boost_enabled": False})  # works even with the automatic boost off
    sup = Supervisor(cfg)
    sup.set_preset("home", T0)
    _step(sup, T0, indoor=21.6)
    sup.set_preset("boost", T0 + timedelta(seconds=30))
    decision = _step(sup, T0 + timedelta(minutes=1), indoor=21.6)
    assert decision.reason == Reason.BOOST and sup.boosting
    assert sup.preset == "home"


def test_boost_preset_without_a_deficit_does_nothing_later():
    sup = Supervisor(CFG)
    sup.set_preset("boost", T0)
    assert _step(sup, T0, indoor=22.4).reason != Reason.BOOST  # above target: nothing to do
    assert _step(sup, T0 + timedelta(minutes=30), indoor=21.0).reason != Reason.BOOST  # and not later either


def test_old_night_preset_is_renamed_on_restore():
    sup = Supervisor(CFG)
    sup.restore({"preset": "night"})
    assert sup.preset == "sleep"


def test_preset_end_preview_for_a_menu():
    sup = Supervisor(CFG)
    preview = sup.preset_end_preview(["auto", "comfort", "home", "eco", "away", "boost"], T0)
    assert "auto" not in preview
    assert preview["comfort"] == "PT3H"  # a duration, so the attribute does not change every update
    assert preview["home"] == datetime(2026, 11, 9, 22, 0, tzinfo=LOCAL).isoformat()
    assert preview["eco"] is None and preview["away"] == "home" and preview["boost"] == "once"
    assert sup.preset is None  # a preview changes nothing

"""0.4.2: fresh cycle after going live / switching on, and a visible manual target."""

from datetime import datetime, timedelta, timezone

from core.messages import explain
from core.model import HcConfig, Inputs, Presence, Reading, Reason
from core.supervisor import Supervisor

LOCAL = timezone(timedelta(hours=1))
CFG = HcConfig(target_home=22.0, night_start="22:00", night_end="06:00", cycle_s=1800, min_on_s=300,
               min_off_s=300, season_enabled=False)


def _inputs(now, indoor=21.4, presence=Presence.HOME):
    return Inputs(now=now, indoor=Reading(indoor), outdoor=Reading(8.0), presence=presence)


def test_new_cycle_starts_heating_at_once():
    sup = Supervisor(CFG)
    start = datetime(2026, 11, 8, 15, 57, tzinfo=LOCAL)
    # An old cycle that began 19 minutes ago: its on part (about 11 minutes) is over.
    sup.pwm.cycle_start = start
    sup.pwm.last_change = start - timedelta(hours=1)
    now = start + timedelta(minutes=19)
    assert sup.step(_inputs(now)).output is False  # waits for the old cycle phase
    sup.new_cycle()
    decision = sup.step(_inputs(now + timedelta(seconds=30)))
    assert decision.reason == Reason.REGULATING
    assert decision.output is True


def test_new_cycle_still_respects_minimum_off_time():
    sup = Supervisor(CFG)
    now = datetime(2026, 11, 8, 16, 16, tzinfo=LOCAL)
    sup.pwm.last_change = now - timedelta(seconds=60)  # switched off a minute ago
    sup.pwm.output = False
    sup.new_cycle()
    decision = sup.step(_inputs(now))
    assert decision.output is False
    assert decision.limited_by == "min_off"


def test_manual_target_shows_until_next_schedule_change():
    sup = Supervisor(CFG)
    now = datetime(2026, 11, 8, 16, 42, tzinfo=LOCAL)
    sup.step(_inputs(now))
    sup.manual_target = 23.0
    decision = sup.step(_inputs(now + timedelta(seconds=30)))
    assert decision.manual is True
    assert decision.target == 23.0
    assert decision.manual_until == datetime(2026, 11, 8, 22, 0, tzinfo=LOCAL)
    assert explain(decision, "hu").endswith("Kézi cél 22:00-ig.")
    assert explain(decision, "en").endswith("Manual target until 22:00.")


def test_manual_target_after_night_start_runs_until_morning():
    sup = Supervisor(CFG)
    now = datetime(2026, 11, 8, 23, 10, tzinfo=LOCAL)
    sup.step(_inputs(now))
    sup.manual_target = 21.0
    decision = sup.step(_inputs(now + timedelta(seconds=30)))
    assert decision.manual_until == datetime(2026, 11, 9, 6, 0, tzinfo=LOCAL)


def test_manual_target_while_away_has_no_fixed_end():
    sup = Supervisor(CFG)
    now = datetime(2026, 11, 8, 12, 0, tzinfo=LOCAL)
    sup.step(_inputs(now, presence=Presence.AWAY))
    sup.manual_target = 20.0
    decision = sup.step(_inputs(now + timedelta(seconds=30), presence=Presence.AWAY))
    assert decision.manual is True
    assert decision.manual_until is None
    assert explain(decision, "hu").endswith("Kézi cél.")


def test_manual_target_ends_at_schedule_change():
    sup = Supervisor(CFG)
    now = datetime(2026, 11, 8, 21, 59, tzinfo=LOCAL)
    sup.step(_inputs(now))
    sup.manual_target = 23.0
    assert sup.step(_inputs(now + timedelta(seconds=30))).manual is True
    after = sup.step(_inputs(now + timedelta(minutes=2)))
    assert after.manual is False
    assert after.target == CFG.target_night
    assert "Kézi" not in explain(after, "hu")


def test_hungarian_text_uses_decimal_comma():
    sup = Supervisor(HcConfig(target_home=22.5, night_start="00:00", night_end="00:00", season_enabled=False))
    decision = sup.step(_inputs(datetime(2026, 11, 8, 12, 0, tzinfo=LOCAL), indoor=21.4))
    assert "22,5 °C" in explain(decision, "hu")
    assert "22.5 °C" in explain(decision, "en")

"""0.48.2: the boost by the outdoor temperature – the nearest learned band instead of the default, a smooth outdoor
correction within and across the bands, the after-heat lesson finished above the target too and kept over a
restart."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from core.learning import BAND_CENTRE, Learned, Learner, outdoor_factor  # noqa: E402
from core.model import HcConfig, Reason  # noqa: E402
from core.supervisor import Supervisor  # noqa: E402
from sim import House, Run  # noqa: E402

CFG = HcConfig(target_home=23.0, night_start="00:00", night_end="00:00", season_enabled=False,
               boost_enabled=True, cycle_s=1800, min_on_s=300, min_off_s=300)


def _learner(**learned):
    lr = Learner(CFG)
    lr.learned = Learned(**learned)
    return lr


def test_outdoor_factor():
    assert outdoor_factor(5.0, 5.0) == 1.0
    assert outdoor_factor(15.0, 5.0) == pytest.approx(0.8)  # 10 °C warmer: 20 % less burning
    assert outdoor_factor(-5.0, 5.0) == pytest.approx(1.2)
    assert outdoor_factor(40.0, 0.0) == 0.7 and outdoor_factor(-40.0, 0.0) == 1.4
    assert outdoor_factor(None, 5.0) == 1.0


def test_this_mornings_boost_uses_the_mild_band_corrected_for_14_degrees():
    """The house learned four boosts at 5–10 °C (mild); this morning was 14 °C (warm, nothing learned yet). Before:
    the defaults (0.8 °C after-heat, 17 min/°C). Now: the mild values, corrected for the warmer day."""
    lr = _learner(afterheat={"mild": 0.871}, minutes_per_degree={"mild": 18.403})
    f = outdoor_factor(14.0, BAND_CENTRE["mild"])
    assert lr.afterheat(14.0) == pytest.approx(0.871 / f, abs=0.001) and lr.afterheat(14.0) > 1.0
    assert lr.minutes_per_degree(14.0) == pytest.approx(18.403 * f, abs=0.001) and lr.minutes_per_degree(14.0) < 16
    assert lr.afterheat(5.0) == 0.871  # at the band's reference: as learned
    assert _learner().afterheat(14.0) == CFG.boost_afterheat  # nothing learned: the default, as before


def test_a_new_band_takes_its_first_boosts_outdoor_as_reference():
    from datetime import datetime, timezone
    lr = _learner(afterheat={"mild": 0.871}, minutes_per_degree={"mild": 18.4})
    lr.boost_started(datetime(2026, 11, 13, 5, 30, tzinfo=timezone.utc), 22.5, 21.1, 14.0)
    for t in (21.4, 21.8, 22.2, 22.5, 22.8):
        lr.observe(t, 22.5, False)
    lr.boost_stopped(21.9, 31.0)
    lr.boost_finished(peak_found=True)
    assert lr.learned.outdoor_ref["warm"] == 14.0 and "warm" in lr.learned.afterheat
    assert lr.learned.last_boost["used"] is True and lr.learned.boosts == 1


def test_the_boost_record_survives_a_restart():
    from datetime import datetime, timezone
    lr = _learner()
    lr.boost_started(datetime(2026, 11, 13, 5, 30, tzinfo=timezone.utc), 22.5, 21.1, 14.0)
    lr.observe(22.0, 22.5, False)
    lr.boost_stopped(21.9, 31.0)
    again = Learner(CFG)
    again.restore(lr.state())
    assert again.boost is not None and again.boost.indoor_stop == 21.9 and again.boost.peak == 22.0
    assert again.boost.start.hour == 5 and again.boost.outdoor == 14.0
    again.restore({**lr.state(), "boost": {"start": "broken"}})  # a bad record is dropped
    assert again.boost is None


def _house(outdoor):
    return House(indoor=21.1, outdoor=outdoor, loss_tau_s=72 * 3600.0, full_power_delta=232.0, radiator_tau_s=1800.0)


def test_the_lesson_finishes_above_the_target_and_over_a_restart():
    """A boost that ends above the target (at_target) is learned without waiting for the regulation, and a restart
    in the after-heat (this morning's 07:09) keeps it."""
    run = Run(CFG, _house(8.0))
    run.run(minutes=45)  # the boost and the start of its after-heat
    assert any(d.reason == Reason.BOOST for d in run.decisions)
    fresh = Supervisor(CFG)
    fresh.restore(run.sup.state())  # a restart
    run.sup = fresh
    run.run(hours=2)
    assert fresh.learner.learned.boosts == 1 and fresh.learner.learned.last_boost["used"]


def test_a_warm_day_after_mild_lessons_overshoots_less():
    """Four boosts learned at 5 °C, then one at 14 °C: the corrected after-heat stops the burner sooner."""
    def peak(correct):
        run = Run(CFG, _house(5.0))
        for _ in range(4):
            run.house.indoor = 21.1
            run.house.radiator = 0.0
            run.sup._boost_armed = True
            run.run(hours=3)
        if not correct:  # the old behaviour: nothing learned for the warm band → the defaults
            run.sup.learner.learned.afterheat = {}
            run.sup.learner.learned.minutes_per_degree = {}
        run.house.outdoor, run.house.indoor, run.house.radiator = 14.0, 21.1, 0.0
        run.decisions.clear()
        run.sup._boost_armed = True
        run.run(hours=3)
        return max(d.indoor for d in run.decisions)
    assert peak(True) <= peak(False)

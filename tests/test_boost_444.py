"""0.44.4: a boost survives a restart, and a new boost counts the burns just before it.

11-12 10:49 a boost started at 21.6 °C (target 22.5, limit 11:14). A door pause and a Home Assistant restart at
11:05 (the 0.44.3 deploy) cut it; the restart forgot the 13 burn minutes, started a fresh boost with a new limit
(11:35), and burned 12.5 more minutes. About 25 minutes of burning instead of ~14: the house peaked at 22.9 °C.
"""

import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

from core.model import HcConfig, Reason
from core.supervisor import Supervisor
from sim import House, Run

CFG = HcConfig(target_home=22.5, night_start="00:00", night_end="00:00", season_enabled=False,
               boost_enabled=True, cycle_s=1800, min_on_s=300, min_off_s=300, learning_enabled=False)


def _house(indoor=21.5):
    return House(indoor=indoor, outdoor=8.0, loss_tau_s=72 * 3600.0, full_power_delta=232.0, radiator_tau_s=2400.0)  # slow radiators: the room barely moves in 14 min


def _restart(run, keep_boost=True, down_min=3):
    """Home Assistant restarts: a new supervisor from the saved state, the boiler off meanwhile."""
    state = copy.deepcopy(run.sup.state())
    json.dumps(state["boost"])  # what the store writes
    if not keep_boost:
        state.pop("boost")  # before 0.44.4
    for _ in range(down_min * 2):
        run.house.advance(False)
        run.now += timedelta(seconds=30)
    sup = Supervisor(CFG)
    sup.restore(state)
    run.sup, run.uptime_s = sup, 0.0
    return run


def _flame_min(run):
    """Burn minutes of the boost phase (first 50 minutes)."""
    return sum(30 for d in run.decisions[:100] if d.output) / 60


def _boost_with_restart(keep_boost):
    run = Run(CFG, _house())
    run.run(minutes=14)
    assert run.decisions[0].reason == Reason.BOOST and run.sup.boosting
    _restart(run, keep_boost)
    run.run(hours=2)
    return run


def test_a_restart_does_not_restart_the_boost():
    plain = Run(CFG, _house())
    plain.run(hours=2, minutes=17)
    new = _boost_with_restart(True)
    old = _boost_with_restart(False)
    assert _flame_min(old) > _flame_min(plain) + 5  # the old behaviour: burns again from zero
    assert _flame_min(new) <= _flame_min(plain) + 1.5
    peak = lambda r: max(d.indoor for d in r.decisions)  # noqa: E731
    assert peak(new) < peak(old)
    assert peak(new) <= CFG.target_home + 0.3


def test_the_restored_boost_keeps_its_limit_and_burn_minutes():
    run = Run(CFG, _house())
    run.run(minutes=10)
    until, flame = run.sup._boost_until, run.sup._boost_flame_s
    _restart(run)
    assert run.sup._boost_until == until and run.sup._boost_flame_s == flame


def test_a_boost_saved_long_ago_is_not_resumed():
    run = Run(CFG, _house())
    run.run(minutes=10)
    _restart(run, down_min=40)
    run.uptime_s = 1e9
    run.tick()
    assert run.sup._boost_until is None or run.sup._boost_flame_s == 0.0


def test_a_new_boost_counts_the_burns_just_before_it():
    sup = Supervisor(CFG)
    t = Run(CFG, _house()).now
    sup._flame_log = [[t - timedelta(minutes=20), t - timedelta(minutes=8)]]  # 12 min, ended 8 min ago
    prior = sup._prior_flame_min(t)
    assert 9 < prior < 11  # weight 1 - 8/45
    sup._flame_log = [[t - timedelta(minutes=70), t - timedelta(minutes=50)]]
    assert sup._prior_flame_min(t) == 0.0  # long ago: its after-heat has arrived


def test_a_boost_after_a_restart_without_saved_boost_still_counts_the_burns():
    """No saved boost (e.g. a crash before the save): the burn log still tells a new boost what came before."""
    run = Run(CFG, _house())
    run.run(minutes=14)
    state = copy.deepcopy(run.sup.state())
    state["boost"].update(until=None, armed=True)  # saved before the boost began
    sup = Supervisor(CFG)
    sup.restore(state)
    run.sup, run.uptime_s = sup, 0.0
    run.run(hours=2)
    restarted = [d for d in run.decisions[28:] if d.reason == Reason.BOOST]
    assert restarted and restarted[0].details["prior_min"] > 8


def test_version():
    root = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
    assert json.loads((root / "manifest.json").read_text())["version"] in ("0.44.4", "0.44.5", "0.45.0", "0.46.0", "0.47.0", "0.48.0", "0.48.1")

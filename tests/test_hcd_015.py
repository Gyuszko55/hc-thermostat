"""hcd 0.1.5: in shadow, hcd also takes the integration's regulator state (the PID integral)."""
from datetime import datetime, timezone

from hc_core.inputs import SampleTable
from hcd.engine import Engine

from tests.test_hcd_010 import HC

NOW = datetime(2026, 11, 25, 8, 0, tzinfo=timezone.utc)


def test_engine_takes_the_integrations_integral():
    e = Engine({**HC, "control": "pid"}, SampleTable(), None, NOW)
    e.sup.regulator.integral = 0.065
    assert e.follow_regulator({"integral": 0.0363})
    assert e.sup.regulator.integral == 0.0363


def test_a_foreign_or_broken_regulator_state_is_left_alone():
    e = Engine({**HC, "control": "pid"}, SampleTable(), None, NOW)
    e.sup.regulator.integral = 0.05
    for bad in ({}, None, {"integral": "x"}, {"integral": 0.1, "other": 1}, {"offset": 0.1}):
        assert not e.follow_regulator(bad)
    assert e.sup.regulator.integral == 0.05


def test_the_status_says_whether_it_followed():
    src = open("hcd/hcd/__main__.py", encoding="utf-8").read()
    assert 'engine.follow_regulator(sup.get("regulator") or {})' in src and "regulator=reg" in src

"""hcd 0.1.4: in shadow, hcd takes the integration's learned values instead of drifting on its own."""
from datetime import datetime, timezone

import pytest

from hc_core.inputs import SampleTable
from hcd import config as cfg_
from hcd.engine import Engine

from tests.test_hcd_010 import HC

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def test_learned_from_parses_and_needs_home_assistant():
    c = cfg_.parse({"hc": HC, "ha": {"url": "http://x", "token": "t"}, "learned_from": "abc", "learned_every_s": 10})
    assert c.learned_from == "abc" and c.learned_every_s == 60.0  # at least a minute
    assert cfg_.parse({"hc": HC}, env={}).learned_from is None
    with pytest.raises(cfg_.ConfigError):
        cfg_.parse({"hc": HC, "learned_from": "abc"}, env={})


def test_engine_takes_the_integrations_learner_state():
    e = Engine({**HC, "learning_enabled": True}, SampleTable(), None, NOW)
    other = Engine({**HC, "learning_enabled": True}, SampleTable(), None, NOW)
    other.sup.learner.learned.trim = 0.175
    other.sup.learner.learned.tpi_offset = -0.166
    assert e.follow_learned(other.sup.learner.state())
    assert e.sup.learner.learned.trim == 0.175 and e.sup.learner.learned.tpi_offset == -0.166
    assert not e.follow_learned({}) and not e.follow_learned({"learned": None})

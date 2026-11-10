"""0.28.0: several electric zones share a power budget – a zone switches on only when its power fits, waits in
order, its cycle starts when it gets the room (staggered zones), and a zone heating without a pause hands over."""

from datetime import datetime, timedelta, timezone

from core.load import LoadClient, LoadManager
from core.messages import explain
from core.model import HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, learning_enabled=False)


def at(minutes):
    return T0 + timedelta(minutes=minutes)


# --- manager -----------------------------------------------------------------------------------------------------
def test_room_under_the_limit():
    m = LoadManager()
    assert m.request("a", 2.0, 3.5, at(0))
    assert not m.request("b", 2.0, 3.5, at(0))  # 4 kW would exceed 3.5
    assert m.request("c", 1.5, 3.5, at(0))  # but 1.5 kW fits... b waits since 0 and does not fit: c may go
    m.report("a", False, False, at(1))
    assert m.request("b", 2.0, 3.5, at(1))  # a is off: 1.5 + 2 fits


def test_first_come_first_served():
    m = LoadManager()
    m.request("a", 2.0, 2.0, at(0))
    assert not m.request("b", 2.0, 2.0, at(0))
    assert not m.request("c", 2.0, 2.0, at(1))
    m.report("a", False, False, at(2))
    assert not m.request("c", 2.0, 2.0, at(2))  # b has waited longer
    assert m.request("b", 2.0, 2.0, at(2))


def test_a_zone_that_no_longer_wants_heat_leaves_the_queue():
    m = LoadManager()
    m.request("a", 2.0, 2.0, at(0))
    m.request("b", 2.0, 2.0, at(0))
    m.report("b", False, False, at(1))  # b's demand dropped
    m.report("a", False, False, at(1))
    assert m.request("c", 2.0, 2.0, at(1))


def test_stale_entries_are_forgotten():
    m = LoadManager()
    m.request("gone", 2.0, 2.0, at(0))
    assert not m.request("b", 2.0, 2.0, at(5))
    assert m.request("b", 2.0, 2.0, at(11))  # "gone" has not reported for 11 minutes


def test_a_running_zone_hands_over_at_its_next_cycle():
    m = LoadManager()
    m.request("a", 2.0, 2.0, at(0))
    for minute in range(1, 30):  # b keeps asking every minute (as its decisions do)
        assert not m.request("b", 2.0, 2.0, at(minute))
        m.request("a", 2.0, 2.0, at(minute))
    assert not m.request("a", 2.0, 2.0, at(30), renew=True)  # b has waited: a hands over
    assert m.request("b", 2.0, 2.0, at(30))
    assert m.snapshot(at(30)) == {"on": {"b": 2.0}, "waiting": ["a"]}
    for minute in range(31, 60):
        m.request("a", 2.0, 2.0, at(minute))
        m.request("b", 2.0, 2.0, at(minute))
    assert not m.request("b", 2.0, 2.0, at(60), renew=True)  # b's full cycle is over: a's turn again
    assert m.request("a", 2.0, 2.0, at(60))


def test_a_restored_running_relay_counts():
    m = LoadManager()
    m.report("a", True, False, at(0), kw=2.0)  # on after a restart, never asked
    assert m.used(at(0)) == 2.0
    assert not m.request("b", 2.0, 3.0, at(0))


# --- in the supervisor ------------------------------------------------------------------------------------------
def zone(m, name, kw=2.0, limit=2.0):
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi", "cycle_s": 1800, "min_on_s": 300, "min_off_s": 300,
                                            "boiler_power_kw": kw, "load_limit_kw": limit}))
    sup.load = LoadClient(m, name, kw, limit)
    return sup


def step(sup, minute, indoor=18.0):
    return sup.step(Inputs(now=at(minute), indoor=Reading(indoor), outdoor=Reading(0.0)))


def test_two_zones_on_one_budget_take_turns():
    m = LoadManager()
    a, b = zone(m, "a"), zone(m, "b")
    da, db = step(a, 0), step(b, 0)
    assert da.output and not db.output and db.limited_by == "load_limit"
    assert db.details["load_used_kw"] == 2.0 and db.details["load_waiting"] == ["b"]
    assert "Terheléskorlát: most 2 kW fűt a 2 kW-ból" in explain(db, "hu")
    assert db.reason == Reason.REGULATING  # still regulating, only waiting
    # a heats its whole cycle without a pause (cold room: demand 100 %), at its next cycle it hands over to b
    for minute in range(1, 30):
        assert step(a, minute).output and not step(b, minute).output
    da = step(a, 30)
    assert not da.output and da.limited_by == "load_limit"
    assert step(b, 30).output
    assert b.pwm.cycle_start == at(30)  # b's cycle starts when it got the room: its full on-time is kept


def test_frost_also_obeys_the_fuse():
    m = LoadManager()
    a, b = zone(m, "a"), zone(m, "b")
    step(a, 0, indoor=5.0)
    d = step(b, 0, indoor=5.0)
    assert d.reason == Reason.FROST and not d.output


def test_without_a_limit_nothing_changes():
    sup = Supervisor(HcConfig.from_mapping({**DAY, "control": "tpi", "cycle_s": 1800, "min_on_s": 300, "min_off_s": 300}))
    assert sup.load is None and step(sup, 0).output

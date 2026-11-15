"""0.54.0: the stratified buffer tank, the hold of a given-out target, and a mixing circuit's flow target (shadow)."""

import asyncio
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
strat = importlib.import_module("hc_thermostat.core.stratified")
hold_mod = importlib.import_module("hc_thermostat.core.setpoint_hold")
circ = importlib.import_module("hc_thermostat.core.circuit")

T0 = datetime(2026, 11, 15, 6, 0, tzinfo=timezone.utc)
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


# --- the stratified tank -------------------------------------------------------------------------------------------
FOUR = ["top", "upper", "lower", "bottom"]


def test_stored_heat_and_charge_of_four_layers():
    conf = {"buffer_volume_l": 1000, "buffer_base_temp": 25, "buffer_off": 65}
    s = strat.stock({"top": 60, "upper": 50, "lower": 40, "bottom": 30}, FOUR, conf)
    # 250 l each × 1.163 Wh/(l·K) × (35 + 25 + 15 + 5) K = 23.26 kWh
    assert s.stored_kwh == pytest.approx(23.26, abs=0.01)
    assert s.capacity_kwh == pytest.approx(46.52, abs=0.01)
    assert s.charge == s.charge_layers == pytest.approx(50.0)
    assert s.charge_method == "layers"
    assert s.top == 60 and s.bottom == 30 and s.mean == 45
    assert not s.estimated


def test_an_existing_percentage_is_taken_over_unchanged():
    s = strat.stock({"top": 60, "bottom": 30}, ["top", "bottom"], {"buffer_volume_l": 1000}, external=4.0)
    assert s.charge == 4.0 and s.charge_method == "external"
    assert s.charge_layers is not None and s.charge_layers != 4.0  # the own estimate stays beside it


def test_shares_from_the_settings_and_even_when_unset():
    assert strat.shares(FOUR, {}) == {n: 0.25 for n in FOUR}
    sh = strat.shares(FOUR, {"buffer_share_top": 10, "buffer_share_upper": 20, "buffer_share_lower": 30, "buffer_share_bottom": 40})
    assert sh["top"] == pytest.approx(0.1) and sh["bottom"] == pytest.approx(0.4)
    sh = strat.shares(["top", "bottom"], {"buffer_share_top": 50})  # unset: an even share (50) → half and half
    assert sh == {"top": 0.5, "bottom": 0.5}


def test_a_lost_thermometer_takes_its_neighbours_reading_and_says_so():
    s = strat.stock({"top": 60, "upper": None, "lower": 40, "bottom": 30}, FOUR, {"buffer_volume_l": 1000})
    upper = next(l for l in s.layers if l.name == "upper")
    assert upper.temp == 50.0 and not upper.measured  # equally near above and below: their mean
    assert s.estimated


def test_no_volume_no_kwh_but_a_charge():
    s = strat.stock({"top": 50}, ["top"], {})
    assert s.stored_kwh is None and s.capacity_kwh is None
    assert s.charge == pytest.approx(62.5)  # (50 − 25) / (65 − 25)
    assert s.usable(35, 5, 2)["usable_kwh"] is None
    assert s.usable(35, 5, 2)["satisfied"] is True


def test_usable_heat_for_a_floor_and_a_radiator_circuit():
    s = strat.stock({"top": 45, "upper": 40, "lower": 32, "bottom": 28}, FOUR, {"buffer_volume_l": 1000})
    floor = s.usable(33, circuit_dt=5, margin=2)  # needs 35: top + upper reach; down to 28
    assert floor["satisfied"] and floor["reach"] == 2
    assert floor["usable_kwh"] == pytest.approx(250 * 0.001163 * ((45 - 28) + (40 - 28)), abs=0.01)
    rad = s.usable(48, circuit_dt=10, margin=2)  # needs 50: nothing reaches
    assert rad["satisfied"] is False and rad["reach"] == 0 and rad["usable_kwh"] == 0
    assert s.usable(None, 5, 2)["satisfied"] is None


def test_trend_charging_emptying_steady():
    tr = strat.StockTrend()
    conf = {"buffer_volume_l": 1000}
    assert tr.add(at(0), strat.stock({"top": 40, "bottom": 30}, ["top", "bottom"], conf))["state"] is None
    t = tr.add(at(20), strat.stock({"top": 44, "bottom": 34}, ["top", "bottom"], conf))
    assert t["state"] == "charging" and t["c_per_h"] == pytest.approx(12.0)
    assert t["kwh_per_h"] == pytest.approx(1000 * 0.001163 * 12, abs=0.05)
    tr = strat.StockTrend()
    tr.add(at(0), strat.stock({"top": 44}, ["top"], {}))
    assert tr.add(at(30), strat.stock({"top": 42}, ["top"], {}))["state"] == "emptying"
    tr = strat.StockTrend()
    tr.add(at(0), strat.stock({"top": 44}, ["top"], {}))
    assert tr.add(at(30), strat.stock({"top": 44.1}, ["top"], {}))["state"] == "steady"


# --- the hold of a given-out target ---------------------------------------------------------------------------------
def H(**kw):
    return hold_mod.SetpointHold(hold_mod.HoldConfig(**kw))


def test_first_value_goes_out_then_small_changes_are_held():
    h = H()
    r = h.step(at(0), 33.2, 22, 36)
    assert r.reason == "start" and r.value == 33.0 and r.changed
    assert h.step(at(1), 34.0, 22, 36).reason == "deadband"  # 1.0 < 1.5
    assert h.step(at(60), 32.0, 22, 36).value == 33.0


def test_a_change_must_last_and_respect_the_interval():
    h = H(deadband=1.5, confirm_s=600, min_interval_s=1500, max_rise=0, urgent=0)
    h.step(at(0), 30, 22, 50)
    assert h.step(at(5), 33, 22, 50).reason == "confirming"
    assert h.step(at(10), 30.5, 22, 50).reason == "deadband"  # went back: the wait starts over
    assert h.step(at(12), 33, 22, 50).reason == "confirming"
    assert h.step(at(22), 33, 22, 50).reason == "min_interval"  # confirmed, but only 22 minutes since the start
    r = h.step(at(25), 33, 22, 50)
    assert r.reason == "changed" and r.value == 33.0
    assert r.next_allowed == at(50)


def test_rises_are_ramped_lowering_is_not():
    h = H(deadband=1.5, confirm_s=0, min_interval_s=0, max_rise=3, urgent=0)
    h.step(at(0), 30, 22, 55)
    r = h.step(at(1), 40, 22, 55)
    assert r.reason == "ramp" and r.value == 33.0
    r = h.step(at(2), 40, 22, 55)
    assert r.value == 36.0
    r = h.step(at(3), 25, 22, 55)
    assert r.reason == "changed" and r.value == 25.0


def test_short_pulses_never_change_the_target():
    """Acceptance 3: zones opening and closing every five minutes do not move the given-out target."""
    h = H()  # defaults: 1.5 °C, 10 min confirmation, 25 min interval
    h.step(at(0), 30, 22, 55)
    changes = 0
    for i in range(1, 25):  # two hours, the raw target flips every 5 minutes
        r = h.step(at(5 * i), 33 if i % 2 else 30, 22, 55)
        changes += r.changed
    assert changes == 0 and h.value == 30.0


def test_urgent_difference_skips_the_wait_but_not_the_rise_limit():
    h = H(deadband=1.5, confirm_s=600, min_interval_s=1500, max_rise=3, urgent=5)
    h.step(at(0), 30, 22, 55)
    assert h.step(at(1), 37, 22, 55).reason == "confirming"  # one reading is not enough even when urgent
    r = h.step(at(3), 37, 22, 55)
    assert r.reason == "urgent" and r.value == 33.0


def test_a_lowered_limit_is_applied_at_once():
    h = H()
    h.step(at(0), 40, 22, 55)
    r = h.step(at(1), 40, 22, 36)
    assert r.reason == "limit" and r.value == 36.0
    r = h.step(at(2), 40, 22, 35.8)  # off the 0.5 grid: the limit itself
    assert r.value == 35.8


def test_no_input_keeps_the_target():
    h = H()
    h.step(at(0), 40, 22, 55)
    r = h.step(at(1), None, 22, 55)
    assert r.reason == "no_input" and r.value == 40.0 and not r.changed


def test_restart_keeps_a_recent_target_and_forgets_an_old_one():
    h = H()
    h.step(at(0), 40, 22, 55)
    saved = h.state(at(30))
    fresh = H()
    fresh.restore(saved, at(40))
    assert fresh.value == 40.0 and fresh.last_change == at(0)
    assert fresh.step(at(41), 44, 22, 55).reason == "confirming"  # no jump right after the restart
    old = H()
    old.restore(saved, at(30 + 7 * 60))
    assert old.value is None
    old.restore({"value": "x", "last_change": "nonsense"}, at(0))
    assert old.value is None


# --- the mixing circuit ---------------------------------------------------------------------------------------------
def Z(name, asking, target=21.0, indoor=20.5, fault=False):
    return circ.ZoneReading(name, asking, target, indoor, fault)


def test_floor_defaults_and_its_ceiling():
    cfg = circ.CircuitConfig.from_conf({"circuit_kind": "floor"})
    assert (cfg.circuit_slope, cfg.circuit_flow_min, cfg.circuit_flow_max, cfg.circuit_dt) == (0.5, 22.0, 36.0, 5.0)
    cfg = circ.CircuitConfig.from_conf({"circuit_kind": "floor", "circuit_flow_max": 34})
    assert cfg.circuit_flow_max == 34
    assert circ.CircuitConfig.from_conf({"circuit_kind": "bogus"}).circuit_kind == "radiator"
    m = circ.MixingCircuit(circ.CircuitConfig.from_conf({"circuit_kind": "floor"}))
    d = m.step(at(0), [Z("climate.a", True, 22, 19)], outdoor=-20)
    assert d.raw == 36.0 and d.target == 36.0  # 22 + 0.5 × 42 + 3 = 46 → the floor's 36 °C ceiling


def test_floor_only_demand_stays_low_and_radiator_demand_does_not_leak():
    """Acceptance 1 and 2: each circuit by its own zones and curve."""
    floor = circ.MixingCircuit(circ.CircuitConfig.from_conf({"circuit_kind": "floor"}))
    rad = circ.MixingCircuit(circ.CircuitConfig.from_conf({"circuit_kind": "radiator"}))
    f = floor.step(at(0), [Z("climate.living", True, 21, 20.5)], outdoor=0)
    r = rad.step(at(0), [Z("climate.bath", True, 23, 21)], outdoor=0)
    assert f.target == pytest.approx(32.0)  # 21 + 0.5 × 21 + 1 × 0.5 = 32.0
    assert r.target == pytest.approx(54.5)  # 23 + 1.2 × 23 + 2 × 2 = 54.6 → 54.5
    assert f.target <= 36


def test_lasting_demand_survives_a_tpi_pause():
    m = circ.MixingCircuit()
    assert m.step(at(0), [Z("climate.a", True)], outdoor=5).demand
    d = m.step(at(20), [Z("climate.a", False)], outdoor=5)
    assert d.demand and d.lasting == ("climate.a",) and d.asking == ()
    assert not m.step(at(31), [Z("climate.a", False)], outdoor=5).demand


def test_no_demand_uses_the_reference_room_and_a_fault_zone_does_not_count():
    m = circ.MixingCircuit(circ.CircuitConfig(circuit_slope=1.0, circuit_room=20))
    d = m.step(at(0), [Z("climate.a", True, 25, 15, fault=True)], outdoor=10)
    assert not d.demand and d.t_room == 20 and d.deficit == 0
    assert d.raw == 30.0


def test_no_outdoor_holds_the_given_out_target():
    m = circ.MixingCircuit()
    first = m.step(at(0), [Z("climate.a", True)], outdoor=0)
    d = m.step(at(40), [Z("climate.a", True)], outdoor=None)
    assert d.reason == "no_input" and d.target == first.target and d.raw is None
    assert d.details["no_outdoor"]


def test_circuit_state_round_trip():
    m = circ.MixingCircuit()
    m.step(at(0), [Z("climate.a", True)], outdoor=0)
    data = json.loads(json.dumps(m.state(at(5))))
    n = circ.MixingCircuit()
    n.restore(data, at(10))
    assert n.hold.value == m.hold.value and "climate.a" in n.last_ask
    n.restore({"last_ask": {"climate.b": "nope"}}, at(10))  # a broken value is skipped


def test_a_sudden_lasting_cold_spell_moves_the_target_early():
    """Acceptance 4: a large, lasting rise goes out before the interval ends (ramped)."""
    m = circ.MixingCircuit()
    m.step(at(0), [Z("climate.a", True, 21, 21)], outdoor=10)  # 21 + 1.2 × 11 = 34.2 → 34.0
    m.step(at(1), [Z("climate.a", True, 21, 21)], outdoor=0)  # 46.2 now: urgent, waits 2 minutes
    d = m.step(at(4), [Z("climate.a", True, 21, 21)], outdoor=0)
    assert d.reason == "urgent" and d.target == 37.0


# --- Home Assistant side --------------------------------------------------------------------------------------------
def test_translations_cover_the_new_keys():
    for lang in ("en", "hu"):
        tr = json.loads((BASE / f"translations/{lang}.json").read_text("utf8"))
        for flow in ("config", "options"):
            assert {"circuit", "circuit_settings"} <= set(tr[flow]["step"])
            assert "buffer_upper_entity" in tr[flow]["step"]["buffer"]["data"]
            assert "circuit_order" in tr[flow]["error"]
        assert "circuit" in tr["selector"]["role"]["options"]
        assert set(tr["selector"]["circuit_kind"]["options"]) == set(circ.KINDS)
        for key in ("buffer_charge", "buffer_stored", "buffer_trend", "circuit_target", "circuit_raw"):
            assert key in tr["entity"]["sensor"]
        assert "circuit_demand" in tr["entity"]["binary_sensor"]


class FakeHass:
    def __init__(self, states):
        self._states = states
        self.states = SimpleNamespace(get=lambda e: self._states.get(e))


def _st(value, entity_id="sensor.x", unit="°C", age_min=0.0, **attrs):
    when = T0 - timedelta(minutes=age_min)
    return SimpleNamespace(entity_id=entity_id, state=str(value), attributes={"unit_of_measurement": unit, **attrs},
                           last_updated=when, last_reported=when)


def test_reading_the_zones_and_the_outdoor_thermometer():
    cc = importlib.import_module("hc_thermostat.circuit_coordinator")
    hass = FakeHass({
        "climate.a": SimpleNamespace(state="heat", attributes={"hvac_action": "heating", "temperature": 21, "current_temperature": 20.2}),
        "climate.b": SimpleNamespace(state="off", attributes={"hvac_action": "heating", "temperature": 21}),
        "climate.c": SimpleNamespace(state="unavailable", attributes={}),
        "sensor.out": _st(-3.5, "sensor.out"),
        "sensor.old": _st(4, "sensor.old", age_min=4 * 60),
        "sensor.mad": _st(90, "sensor.mad"),
    })
    zones = cc.read_circuit_zones(hass, ["climate.a", "climate.b", "climate.c", "climate.gone"])
    assert [z.asking for z in zones] == [True, False, False, False]
    assert zones[0].target == 21 and zones[0].indoor == 20.2
    assert zones[2].fault and zones[3].fault
    assert cc.read_outdoor(hass, "sensor.out", T0) == -3.5
    assert cc.read_outdoor(hass, "sensor.old", T0) is None  # a dead sensor keeps its value
    assert cc.read_outdoor(hass, "sensor.mad", T0) is None
    assert cc.read_outdoor(hass, None, T0) is None


def test_buffer_percentage_reading():
    bc = importlib.import_module("hc_thermostat.buffer_coordinator")
    hass = FakeHass({"sensor.p": _st("4", unit="%"), "sensor.bad": _st("abc"), "sensor.old": _st("50", age_min=120)})
    assert bc._percent(hass, "sensor.p", T0, 3600) == 4.0
    assert bc._percent(hass, "sensor.bad", T0, 3600) is None
    assert bc._percent(hass, "sensor.old", T0, 3600) is None
    assert bc._percent(hass, None, T0, 3600) is None


def test_the_circuit_role_writes_only_through_the_writer():
    src = (BASE / "circuit_coordinator.py").read_text("utf8")
    assert "async_call" not in src  # 0.54.0: no service call of its own (0.56.0: only through output_writer)
    assert "WriteControl(hass, entry, data)" in src  # shadow unless a trial / active mode is chosen

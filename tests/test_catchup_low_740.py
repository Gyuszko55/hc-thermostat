"""0.74.0 (a tester's 24 h on a buffer house): the low-temperature catch-up. Radiator rooms stayed 0.3–0.5 °C below
23.2 °C on a circuit asking ~32 °C – under the 0.5 °C threshold, so the TPI paused every hour (and with it the
thermoelectric valves and the pump). Opt-in: on a circuit that asks (its demanded target) for less than 45.0 °C the
catch-up starts at 0.3 °C, after 30 min (radiators) / 2 h (floor), and ends at 0.1 / 0.2 °C."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from core.messages import explain  # noqa: E402
from core.model import HcConfig, Inputs, Reading, Reason  # noqa: E402
from core.supervisor import Supervisor  # noqa: E402

T0 = datetime(2026, 11, 18, 8, 0, tzinfo=timezone.utc)
DAY = dict(night_start="00:00", night_end="00:00", season_enabled=False, boost_enabled=False, learning_enabled=False,
           target_home=23.2, control="tpi")
LOW = {**DAY, "catchup_low": True}
RAD = (("radiator", 32.5),)


def at(m):
    return T0 + timedelta(minutes=m)


def _step(sup, m, indoor, circuits=RAD, outdoor=5.0, uptime=1e9):
    return sup.step(Inputs(now=at(m), indoor=Reading(indoor), outdoor=Reading(outdoor), circuits=circuits,
                           uptime_s=uptime))


def _first_on(sup, indoor, circuits=RAD, until=400):
    for m in range(until):
        if "catchup" in _step(sup, m, indoor, circuits).details:
            return m
    return None


# --- 1. the tester's case -------------------------------------------------------------------------------------------
def test_radiator_on_a_low_circuit_catches_up_from_0_3():
    sup = Supervisor(HcConfig(**LOW))
    on = _first_on(sup, 22.8)  # 0.4 °C behind: never with the 0.5 °C threshold
    assert on == 45  # 15 min to confirm the circuit + 30 min below 0.3 °C (counted from the confirmation)
    d = _step(sup, on + 1, 22.95)  # 0.25 behind: still the whole cycle, no PWM pause
    assert d.demand == 1.0 and d.output and d.details["catchup"]["low"] and d.details["catchup"]["release"] == 0.1
    assert "Alacsony hőfokú kör" in explain(d, "hu") and "Low-temperature circuit" in explain(d, "en")
    m = d.details["catchup_mode"]
    assert m["mode"] == "low" and m["kind"] == "radiator" and m["flow"] == 32.5 and m["gap"] == 0.3
    assert m["after_min"] == 30 and m["active"]
    d = _step(sup, on + 2, 23.1)  # within 0.1: the TPI again
    assert "catchup" not in d.details and d.details["catchup_mode"]["last_exit"]["why"] == "release"


def test_off_by_default_nothing_changes():
    sup = Supervisor(HcConfig(**DAY))
    assert _first_on(sup, 22.8) is None  # 0.4 °C: under the 0.5 °C threshold, as before
    assert "catchup_mode" not in _step(sup, 401, 22.8).details
    assert HcConfig().catchup_low is False and HcConfig().catchup_low_limit == 45.0


# --- 2. the 45 °C limit and its noise -------------------------------------------------------------------------------
def test_the_limit_is_strict_below_45():
    for flow, low in ((44.9, True), (45.0, False), (45.1, False)):
        sup = Supervisor(HcConfig(**LOW))
        assert (_first_on(sup, 22.8, (("radiator", flow),)) is not None) is low, flow


def test_noise_around_the_limit_does_not_switch():
    sup = Supervisor(HcConfig(**LOW))
    for m in range(120):  # 44.9 ↔ 45.0 every 5 minutes: never 15 min the same
        flow = 44.9 if (m // 5) % 2 else 45.0
        d = _step(sup, m, 22.8, (("radiator", flow),))
        assert d.details["catchup_mode"]["mode"] == "normal" and "catchup" not in d.details
    # confirmed low, then a short spell above: stays low
    sup = Supervisor(HcConfig(**LOW))
    for m in range(20):
        _step(sup, m, 23.2)
    assert sup._low
    for m in range(20, 30):
        d = _step(sup, m, 23.2, (("radiator", 46.0),))
    assert sup._low and d.details["catchup_mode"]["pending"] == "normal"
    for m in range(30, 40):
        _step(sup, m, 23.2, (("radiator", 46.0),))
    assert not sup._low  # 15 min above: normal


# --- 3. a cold tank or a stopped pump does not make a low-temperature system ----------------------------------------
def test_the_demanded_target_decides_not_the_measured_flow():
    sup = Supervisor(HcConfig(**LOW))
    # the circuit asks 50 °C (the measured flow may be 25 °C behind a stopped pump – it is not an input at all)
    assert _first_on(sup, 22.8, (("radiator", 50.0),)) is None
    assert _step(sup, 401, 22.8, (("radiator", 50.0),)).details["catchup_mode"]["mode"] == "normal"


# --- 4. floor -------------------------------------------------------------------------------------------------------
def test_floor_waits_two_hours_and_lets_go_at_0_2():
    sup = Supervisor(HcConfig(**LOW))
    floor = (("floor", 30.0),)
    assert _first_on(sup, 22.8, floor) == 15 + 120
    d = _step(sup, 136, 23.0, floor)  # 0.2 behind: the floor's release
    assert "catchup" not in d.details and d.details["catchup_mode"]["release"] == 0.2


def test_a_floor_room_on_a_radiator_circuit_waits_like_a_floor():
    sup = Supervisor(HcConfig(**{**LOW, "floor_system": True}))
    assert _first_on(sup, 22.8) == 15 + 120


def test_floor_safety_still_first():
    sup = Supervisor(HcConfig(**{**LOW, "floor_max": 27.0}))
    for m in range(200):
        d = sup.step(Inputs(now=at(m), indoor=Reading(22.8), outdoor=Reading(5.0), circuits=(("floor", 30.0),),
                            floor=Reading(28.0)))
        assert not d.output and d.reason == Reason.FLOOR_LIMIT


# --- 5. combined room, missing data, explicit settings, restart, new target -----------------------------------------
def test_a_bathroom_in_two_circuits():
    both_low = (("radiator", 35.0), ("floor", 30.0))
    sup = Supervisor(HcConfig(**LOW))
    assert _first_on(sup, 22.8, both_low) == 15 + 120  # low, but waits like the floor
    sup = Supervisor(HcConfig(**LOW))
    assert _first_on(sup, 22.8, (("radiator", 50.0), ("floor", 30.0))) is None  # one branch is not low


def test_missing_circuit_data_keeps_the_room_own_threshold():
    for circuits in ((), (("radiator", None),), (("radiator", 32.0), ("floor", None))):
        sup = Supervisor(HcConfig(**LOW))
        assert _first_on(sup, 22.8, circuits) is None
        assert _step(sup, 401, 22.8, circuits).details["catchup_mode"]["mode"] == "unknown"
    # data lost after the confirmation: back to the room's own thresholds at once
    sup = Supervisor(HcConfig(**LOW))
    for m in range(20):
        _step(sup, m, 23.2)
    assert sup._low
    _step(sup, 20, 23.2, ())
    assert not sup._low


def test_explicit_settings():
    sup = Supervisor(HcConfig(**{**LOW, "catchup_gap": 0.0}))  # the catch-up switched off: off on a low circuit too
    assert _first_on(sup, 22.6) is None
    sup = Supervisor(HcConfig(**{**LOW, "catchup_low_gap": 0.4, "catchup_low_after_s": 600}))
    assert _first_on(sup, 22.85) is None  # 0.35 < the user's 0.4
    sup = Supervisor(HcConfig(**{**LOW, "catchup_low_gap": 0.4, "catchup_low_after_s": 600}))
    assert _first_on(sup, 22.8) == 25
    sup = Supervisor(HcConfig(**{**DAY, "catchup_gap": 0.3}))  # the room's own 0.3 still works without the option
    assert _first_on(sup, 22.8) == 30


def test_kept_over_a_restart_and_a_grace_while_the_circuits_load():
    sup = Supervisor(HcConfig(**LOW))
    for m in range(50):
        _step(sup, m, 22.8)
    assert sup._low and sup._catchup
    fresh = Supervisor(HcConfig(**LOW))
    fresh.restore(json.loads(json.dumps(sup.state(), default=str)))
    assert fresh._low and fresh._catchup and fresh._low_info["kind"] == "radiator"
    d = _step(fresh, 51, 22.8, (), uptime=60)  # the circuit is not loaded yet (and the restart hold, as before)
    assert fresh._low and d.details["catchup_mode"]["mode"] == "low" and d.reason == Reason.RESTART_HOLD
    d = _step(fresh, 70, 22.8, (), uptime=20 * 60)  # still nothing after the confirmation time: own thresholds
    assert not fresh._low


def test_a_new_target_starts_the_count_again():
    sup = Supervisor(HcConfig(**LOW))
    on = _first_on(sup, 22.8)
    assert sup._catchup_step(at(on + 1), 23.5, 22.8, False) is None
    assert sup._catchup_exit["why"] == "target"


def test_waiting_is_shown():
    sup = Supervisor(HcConfig(**LOW))
    for m in range(30):
        d = _step(sup, m, 22.8)
    m = d.details["catchup_mode"]
    assert not m["active"] and m["waiting_min"] == 14


# --- 6. the room finds its circuits -----------------------------------------------------------------------------------
def test_the_coordinator_reads_the_circuits_listing_the_room(monkeypatch):
    co = importlib.import_module("hc_thermostat.coordinator")
    reg_entries = [SimpleNamespace(domain="climate", unique_id="room1_climate", entity_id="climate.bath"),
                   SimpleNamespace(domain="climate", unique_id="room1_room_x", entity_id="climate.bath_x")]
    monkeypatch.setattr(co.er, "async_get", lambda hass: None)
    monkeypatch.setattr(co.er, "async_entries_for_config_entry", lambda reg, eid: reg_entries)

    def circuit(kind, target, ok=True, zones=("climate.bath",)):
        rt = SimpleNamespace(data=SimpleNamespace(demand_target=target), last_update_success=ok,
                             circuit=SimpleNamespace(cfg=SimpleNamespace(circuit_kind=kind)))
        return SimpleNamespace(data={"role": "circuit", "zone_entities": list(zones)}, options={}, runtime_data=rt)

    entries = [circuit("radiator", 34.0), circuit("floor", 29.5), circuit("radiator", 60.0, zones=("climate.other",)),
               circuit("radiator", 40.0, ok=False),
               SimpleNamespace(data={"role": "boiler"}, options={}, runtime_data=None)]
    fake = SimpleNamespace(hass=SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda d: entries)),
                           config_entry=SimpleNamespace(entry_id="room1"))
    assert co.HcCoordinator._circuits(fake) == (("radiator", 34.0), ("floor", 29.5), ("radiator", None))


def test_settings_translations_panel_and_version():
    from hc_thermostat import config_flow as cf
    keys = ("catchup_low", "catchup_low_limit", "catchup_low_gap", "catchup_low_after_s", "catchup_low_floor_after_s",
            "catchup_low_release", "catchup_low_floor_release", "catchup_low_confirm_s")
    for k in keys:
        assert k in cf.SETTINGS_SECTIONS["regulation"]
    for lang in ("hu", "en"):
        sec = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]["step"]["settings"]["sections"]["regulation"]
        for k in keys:
            assert sec["data"][k] and sec["data_description"][k]
    js = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "catchupModeText" in js and "catchup_mode" in js
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2")

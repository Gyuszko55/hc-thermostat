"""0.55.0: heat pump coordination for a buffer tank (shadow) – the ON/OFF request, the heat demand, the flow target with
the manual offset, wood first, the cold-weather ON and the long no-demand stop. The acceptance tests of the reference
design (a wood boiler and a monoblock heat pump on a 1000 l tank, a radiator and a floor circuit) are marked."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
hpc = importlib.import_module("hc_thermostat.core.hp_coord")

T0 = datetime(2026, 11, 15, 6, 0, tzinfo=timezone.utc)
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


FLOOR = lambda demand=True, target=33.0: hpc.CircuitNeed("floor", demand, target, 2.0)  # noqa: E731
RAD = lambda demand=True, target=48.0: hpc.CircuitNeed("radiator", demand, target, 2.0)  # noqa: E731


def I(**kw):
    base = dict(outdoor=2.0, top=30.0, charge=None, trend_c_h=0.0, circuits=(FLOOR(),))
    base.update(kw)
    return hpc.HpInputs(**base)


def HP(**kw):
    return hpc.HeatPumpCoordinator(hpc.HpConfig(**kw))


def test_floor_only_asks_a_low_target():
    """Acceptance 1: only the floor asks – the heat pump target follows the floor's need, not the radiators'."""
    h = HP(hp_reserve=5, hp_flow_max=55)
    d = h.step(at(0), I(circuits=(FLOOR(), RAD(demand=False))))
    assert d.heat_demand and d.enable and d.reason == "heat_needed"
    assert d.need == 35.0 and d.target == 40.0  # 33 + 2 margin + 5 reserve


def test_radiator_demand_raises_it_within_the_limit():
    """Acceptance 2: the radiators ask too – the higher need, never above the maximum (after the offset)."""
    h = HP(hp_reserve=5, hp_flow_max=50)
    d = h.step(at(0), I(circuits=(FLOOR(), RAD()), offset=4))
    assert d.need == 50.0 and d.raw == 50.0 and d.target == 50.0  # 50 + 5 + 4 → clamped to 50


def test_offset_example_36_plus_6_is_42():
    """Acceptance 8: the manual correction – 36 °C needed (with no reserve), +6 °C → 42 °C asked."""
    h = HP(hp_reserve=0)
    d = h.step(at(0), I(circuits=(hpc.CircuitNeed("floor", True, 34.0, 2.0),), offset=6))
    assert d.target == 42.0
    assert h.step(at(1), I(offset=20)).details["offset"] == 8.0  # never beyond ±8


def test_short_pulses_do_not_move_the_target():
    """Acceptance 3: the circuits' given-out targets are steady; a zone flicker does not change the heat pump's."""
    h = HP()
    first = h.step(at(0), I()).target
    for k in range(1, 25):
        d = h.step(at(5 * k), I(circuits=(FLOOR(demand=True),), top=30 + (k % 2)))
        assert d.target == first


def test_a_sudden_lasting_rise_goes_out_early_and_ramped():
    """Acceptance 4: the radiator circuit jumps up for good – an urgent change after two minutes, by 3 °C."""
    h = HP(hp_reserve=5)
    h.step(at(0), I())  # 40
    h.step(at(1), I(circuits=(FLOOR(), RAD(target=50.0))))  # raw 57 → clamped 55: urgent, waits 2 minutes
    d = h.step(at(4), I(circuits=(FLOOR(), RAD(target=50.0))))
    assert d.hold_reason == "urgent" and d.target == 43.0


def test_warm_tank_makes_no_demand():
    """Acceptance 5: wood keeps the tank warm – no heat pump heating."""
    h = HP()
    d = h.step(at(0), I(top=62.0, trend_c_h=4.0, wood_signal=True))
    assert not d.heat_demand and not d.enable and d.wood == "certain"
    assert d.target == 25.0  # the lowest: nothing to make


def test_wood_charging_holds_off_a_start():
    h = HP()
    d = h.step(at(0), I(top=32.0, trend_c_h=5.0, wood_signal=True))  # below the need, but wood is filling it
    assert not d.heat_demand and d.reason == "wood"
    d = HP().step(at(0), I(top=32.0, trend_c_h=5.0, hp_running=False))  # no signal, but the heat pump does not run
    assert d.wood == "likely" and d.reason == "wood"
    d = HP().step(at(0), I(top=32.0, trend_c_h=5.0))  # not known whether the heat pump runs: shown, not used
    assert d.wood == "possible" and d.heat_demand and d.reason == "heat_needed"
    d = HP().step(at(0), I(top=32.0, trend_c_h=5.0, hp_running=True))  # its own heat
    assert d.wood == "none"


def test_cold_weather_on_with_wood_and_no_demand():
    """Acceptance 6: wood, +4 °C outside, the monoblock option on – ON requested without heat demand."""
    h = HP(hp_cold_on=True)
    d = h.step(at(0), I(outdoor=4.0, top=60.0, wood_signal=True, circuits=(FLOOR(demand=False),)))
    assert d.enable and d.reason == "cold_on" and not d.heat_demand
    assert d.target == 25.0  # ON is not a heating command: the lowest target


def test_cold_weather_on_release_needs_lasting_warmth():
    h = HP(hp_cold_on=True, hp_cold_release_s=3600)
    h.step(at(0), I(outdoor=3.0, top=60.0, circuits=()))
    assert h.step(at(10), I(outdoor=6.0, top=60.0, circuits=())).enable  # between 5 and 7: still on
    assert h.step(at(20), I(outdoor=8.0, top=60.0, circuits=())).enable  # above 7, but not for an hour yet
    h.step(at(40), I(outdoor=6.5, top=60.0, circuits=()))  # dipped: the hour starts over
    assert h.step(at(100), I(outdoor=8.0, top=60.0, circuits=())).enable
    d = h.step(at(161), I(outdoor=8.0, top=60.0, circuits=()))
    assert not d.cold_on and not d.enable


def test_long_no_demand_stop_and_cold_wins():
    """Acceptance 7: 24 hours with no demand – OFF; unless the cold-weather ON holds (it wins, and says so)."""
    h = HP(hp_standby=True, hp_idle_hours=24)
    quiet = I(top=50.0, circuits=(FLOOR(demand=False),))
    assert h.step(at(0), quiet).reason == "standby" and h.enable
    assert h.step(at(23 * 60), quiet).reason == "standby"
    d = h.step(at(24 * 60 + 1), quiet)
    assert d.reason == "idle_off" and not d.enable
    h = HP(hp_standby=True, hp_idle_hours=24, hp_cold_on=True)
    h.step(at(0), I(outdoor=2.0, top=50.0, circuits=(FLOOR(demand=False),)))
    d = h.step(at(25 * 60), I(outdoor=2.0, top=50.0, circuits=(FLOOR(demand=False),)))
    assert d.enable and d.reason == "cold_on" and d.details["idle_overridden"]


def test_lost_inputs_do_not_cycle():
    """Acceptance 9: no outdoor reading – no random switching; with the monoblock option a fail-safe ON."""
    h = HP()
    h.step(at(0), I())  # heating, ON
    for k in range(1, 10):
        d = h.step(at(k), I(outdoor=None))
        assert d.enable and d.reason == "no_outdoor"
    h = HP()
    for k in range(10):
        assert not h.step(at(k), I(outdoor=None, top=60.0)).enable
    d = HP(hp_cold_on=True).step(at(0), I(outdoor=None, top=60.0))
    assert d.enable and d.reason == "fail_safe_on"
    h = HP()
    h.step(at(0), I())
    d = h.step(at(1), I(top=None))
    assert d.enable and d.reason == "no_buffer"


def test_hysteresis_and_charge_percent():
    h = HP(hp_hyst=3, hp_min_on_s=0, hp_min_off_s=0)
    assert h.step(at(0), I(top=34.0)).heat_demand  # need 35
    assert h.step(at(1), I(top=36.0)).reason == "heating"  # below 35 + 3
    assert not h.step(at(2), I(top=38.5)).heat_demand
    h = HP(hp_charge_on=4, hp_charge_off=10, hp_min_on_s=0, hp_min_off_s=0)
    quiet = dict(top=40.0, circuits=(FLOOR(demand=False),))
    assert h.step(at(0), I(charge=3.5, **quiet)).reason == "low_charge"
    assert h.step(at(1), I(charge=7.0, **quiet)).reason == "charging"
    assert not h.step(at(2), I(charge=10.0, **quiet)).heat_demand
    assert HP().step(at(0), I(top=7.0, circuits=())).reason == "frost"


def test_minimum_on_and_off():
    h = HP(hp_min_on_s=1800, hp_min_off_s=900)
    h.step(at(0), I(top=30.0))
    d = h.step(at(5), I(top=60.0))
    assert d.enable and d.reason == "min_on" and not d.heat_demand
    assert not h.step(at(31), I(top=60.0)).enable
    d = h.step(at(35), I(top=30.0))
    assert not d.enable and d.reason == "min_off"
    assert h.step(at(47), I(top=30.0)).enable


def test_buffer_zones_when_no_circuit_is_linked():
    h = HP(hp_standby=True, hp_idle_hours=1)
    h.step(at(0), I(circuits=(), zones_asking=True, top=50.0))
    assert h.step(at(90), I(circuits=(), zones_asking=True, top=50.0)).reason == "standby"  # asking: not idle


def test_restart_round_trip():
    h = HP(hp_cold_on=True)
    h.step(at(0), I(outdoor=3.0))
    data = json.loads(json.dumps(h.state(at(1))))
    n = HP(hp_cold_on=True)
    n.restore(data, at(5))
    assert n.enable and n.heating and n.cold_latched and n.hold.value == h.hold.value
    m = HP()  # the option was switched off meanwhile: no latch comes back
    m.restore(data, at(5))
    assert not m.cold_latched
    m.restore({"last_change": "nonsense"}, at(5))


# --- Home Assistant side --------------------------------------------------------------------------------------------
def test_running_signal_reading():
    hc = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    st = lambda state, **a: SimpleNamespace(state=state, attributes=a)  # noqa: E731
    hass = SimpleNamespace(states=SimpleNamespace(get={
        "binary_sensor.hp": st("on"), "switch.hp": st("off"), "climate.hp": st("heat", hvac_action="heating"),
        "climate.idle": st("heat", hvac_action="idle"), "sensor.w": st("850", unit_of_measurement="W"), "sensor.w0": st("12", unit_of_measurement="W"),  # 0.57.1: units
        "sensor.x": st("unavailable"), "sensor.txt": st("abc")}.get))
    assert hc.on_state(hass, "binary_sensor.hp") is True
    assert hc.on_state(hass, "switch.hp") is False
    assert hc.on_state(hass, "climate.hp") is True and hc.on_state(hass, "climate.idle") is False
    assert hc.on_state(hass, "sensor.w") is True and hc.on_state(hass, "sensor.w0") is False
    assert hc.on_state(hass, "sensor.x") is None and hc.on_state(hass, "sensor.txt") is None
    assert hc.on_state(hass, None) is None and hc.on_state(hass, "sensor.gone") is None


def test_translations_and_shadow_only():
    for lang in ("en", "hu"):
        tr = json.loads((BASE / f"translations/{lang}.json").read_text("utf8"))
        for flow in ("config", "options"):
            assert {"hp_coord", "hp_coord_settings"} <= set(tr[flow]["step"])
            assert {"cold_order", "charge_order"} <= set(tr[flow]["error"])
        assert "no_buffer" in tr["config"]["abort"]
        assert "hp_coord" in tr["selector"]["role"]["options"]
        assert set(tr["entity"]["sensor"]["hp_decision"]["state"]) == set(hpc.REASONS)
        assert {"hp_enable", "hp_heat_demand"} <= set(tr["entity"]["binary_sensor"])
        assert "hp_offset" in tr["entity"]["number"]
        fields = set(tr["config"]["step"]["hp_coord_settings"]["data"])
        assert fields == {k for k in hpc.HpConfig.__dataclass_fields__} | {"wood_on_above", "wood_off_below", "wood_confirm_s"}  # 0.61.0
    for name in ("hp_coord_coordinator.py", "core/hp_coord.py", "number.py"):
        assert "async_call" not in (BASE / name).read_text("utf8")  # 0.55.0: no service call at all


def test_config_flow_forms_and_no_name_clash():
    """The settings form has every rule; a name clash once hid the heat pump instance's own `_hp_fields`."""
    import ast
    tree = ast.parse((BASE / "config_flow.py").read_text("utf8"))
    names = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    assert len(names) == len(set(names))
    cf = importlib.import_module("hc_thermostat.config_flow")
    hass = SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda d: []))
    keys = {str(k) for k in cf._hpc_settings({})}
    assert keys == set(hpc.HpConfig.__dataclass_fields__) | {"wood_on_above", "wood_off_below", "wood_confirm_s"}  # 0.61.0: wood by temperature
    assert {str(k) for k in cf._hpc_fields(hass, {})} == {"hp_buffer", "outdoor_entity", "hp_running_entity", "wood_entity", "wood_temp_entity",
                                                         "hp_target_entity", "hp_switch_entity", "hp_demand_entity",  # 0.56.0
                                                         "hp_summer_entity", "hp_exercise_entity",  # 0.57.0
                                                         "hp_target_round", "hp_water_temp_entity"}  # 0.64.0
    assert cf._hpc_errors({"hp_flow_min": 25, "hp_flow_max": 55, "hp_cold_on_below": 5, "hp_cold_release_above": 7,
                           "hp_charge_on": 0, "hp_charge_off": 10}) == {}

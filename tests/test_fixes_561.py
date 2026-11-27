"""0.56.1: wood first also over a low charge and a running heating (`hp_wood_first`), and the confirmation wait of
a written target (`write_confirm_s`) for slow cloud devices such as Tuya."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
hpc = importlib.import_module("hc_thermostat.core.hp_coord")
og = importlib.import_module("hc_thermostat.core.output_guard")

T0 = datetime(2026, 11, 15, 6, 0, tzinfo=timezone.utc)
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
UP = 1e6


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def sec(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


FLOOR = hpc.CircuitNeed("floor", True, 33.0, 2.0)


def I(**kw):
    base = dict(outdoor=8.0, top=30.0, charge=None, trend_c_h=0.0, circuits=(FLOOR,))
    base.update(kw)
    return hpc.HpInputs(**base)


# --- wood first ------------------------------------------------------------------------------------------------------
def test_wood_holds_back_a_low_charge_start():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_charge_on=10, hp_min_off_s=0))
    d = h.step(at(0), I(charge=4.0, wood_signal=True))
    assert not d.heat_demand and d.reason == "wood" and d.wood == "certain" and not d.enable


def test_wood_stops_a_running_heating():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_min_on_s=0, hp_min_off_s=0))
    d = h.step(at(0), I(top=30.0))
    assert d.heat_demand and d.reason == "heat_needed"
    d = h.step(at(10), I(top=33.0, wood_signal=True))  # still below need + hysteresis, but wood is burning
    assert not d.heat_demand and d.reason == "wood" and not d.enable
    assert d.target == 25.0 or d.raw == 25.0  # the target goes back to the lowest


def test_likely_wood_also_stops_the_low_charge_heating():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_charge_on=10, hp_min_on_s=0))
    assert h.step(at(0), I(charge=5.0, top=40.0, circuits=())).reason == "low_charge"
    # the heat pump is known to be off and the tank warms fast: another source
    d = h.step(at(5), I(charge=6.0, top=41.0, circuits=(), hp_running=False, trend_c_h=4.0))
    assert d.wood == "likely" and not d.heat_demand and d.reason == "wood"


def test_frost_stays_above_wood():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig())
    d = h.step(at(0), I(top=6.0, wood_signal=True))
    assert d.heat_demand and d.reason == "frost"


def test_cold_weather_on_stays_on_with_wood_at_the_lowest_target():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_cold_on=True, hp_charge_on=10))
    d = h.step(at(0), I(outdoor=-3.0, charge=3.0, wood_signal=True))
    assert d.enable and d.reason == "cold_on" and not d.heat_demand
    assert d.raw == 25.0  # ON, but no heating command


def test_fail_safe_on_stays_with_wood():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_cold_on=True))
    d = h.step(at(0), I(outdoor=None, wood_signal=True))
    assert d.enable and d.reason == "fail_safe_on"


def test_wood_first_off_keeps_the_0550_order():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_wood_first=False, hp_charge_on=10))
    d = h.step(at(0), I(charge=4.0, wood_signal=True))
    assert d.heat_demand and d.reason == "low_charge"
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_wood_first=False, hp_min_on_s=0))
    h.step(at(0), I(top=30.0))
    assert h.step(at(10), I(top=33.0, wood_signal=True)).reason == "heating"


def test_wood_first_is_on_by_default_and_in_the_settings():
    assert hpc.HpConfig().hp_wood_first is True
    src = (BASE / "config_flow.py").read_text()
    assert 'b("hp_wood_first")' in src
    for lang in ("en", "hu"):
        assert json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8")) and \
            (BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8").count('"hp_wood_first"') >= 2  # 0.65.2: + explanations and sections


# --- confirmation wait -----------------------------------------------------------------------------------------------
def test_a_late_echo_of_the_old_value_is_neither_a_rewrite_nor_a_conflict():
    g = og.OutputGuard(confirm_s=60)
    g.wrote(sec(0), 40.0)
    # Tuya first reports the old 35 again (cloud refresh), 20 s later
    assert g.decide(sec(25), 40.0, 35.0, sec(20), UP) == (False, "confirming")
    # then the written value arrives
    assert g.decide(sec(50), 40.0, 40.0, sec(45), UP) == (False, "in_sync")
    assert g.confirmed and g.unconfirmed == 0 and not g.conflict


def test_no_echo_is_written_again_at_most_three_times_then_not_accepted():
    g = og.OutputGuard(confirm_s=60)
    t = 0
    assert g.decide(sec(t), 40.0, 35.0, sec(-600), UP) == (True, "write")
    g.wrote(sec(t), 40.0)
    for n in range(1, 4):
        assert g.decide(sec(t + 30), 40.0, 35.0, sec(-600), UP) == (False, "confirming")
        t += 61
        assert g.decide(sec(t), 40.0, 35.0, sec(-600), UP) == (True, "write")
        g.wrote(sec(t), 40.0)
        assert g.unconfirmed == n
    t += 61
    assert g.decide(sec(t), 40.0, 35.0, sec(-600), UP) == (False, "not_accepted")
    assert g.decide(sec(t + 600), 40.0, 35.0, sec(-600), UP) == (False, "not_accepted")
    # a new value HC wants is written again, and the count starts over
    assert g.decide(sec(t + 700), 42.0, 35.0, sec(-600), UP) == (True, "write")
    g.wrote(sec(t + 700), 42.0)
    assert g.unconfirmed == 0


def test_a_late_confirmation_ends_not_accepted():
    g = og.OutputGuard(confirm_s=10, max_retries=0)
    g.wrote(sec(0), 40.0)
    assert g.decide(sec(20), 40.0, 35.0, sec(-60), UP) == (False, "not_accepted")
    assert g.decide(sec(200), 40.0, 40.0, sec(190), UP) == (False, "in_sync") and g.confirmed


def test_after_confirmation_a_change_is_foreign_as_before():
    g = og.OutputGuard(confirm_s=60)
    g.wrote(sec(0), 40.0)
    assert g.decide(sec(15), 40.0, 40.0, sec(12), UP) == (False, "in_sync")
    # the PLC writes 45 within the confirmation window, after HC's value was confirmed: someone else
    assert g.decide(sec(40), 40.0, 45.0, sec(30), UP) == (False, "conflict")


def test_a_change_after_the_wait_that_was_never_hcs_is_foreign():
    g = og.OutputGuard(confirm_s=60)
    g.wrote(sec(0), 40.0)
    assert g.decide(sec(200), 40.0, 45.0, sec(150), UP) == (False, "conflict")


def test_rewrite_with_unchanged_value_after_confirmation_resets_the_count():
    g = og.OutputGuard(confirm_s=60, keepalive_s=600)
    g.wrote(sec(0), 40.0)
    assert g.decide(sec(10), 40.0, 40.0, sec(5), UP) == (False, "in_sync")
    assert g.decide(sec(700), 40.0, 40.0, sec(5), UP) == (True, "keepalive")
    g.wrote(sec(700), 40.0)
    assert g.unconfirmed == 0 and not g.confirmed
    assert g.decide(sec(710), 40.0, 40.0, sec(5), UP) == (False, "in_sync") and g.confirmed


def test_onoff_switch_uses_the_wait_too():
    g = og.OutputGuard(tolerance=0.0, confirm_s=60)
    g.wrote(sec(0), 1.0)
    assert g.decide(sec(30), 1.0, 0.0, sec(-300), UP) == (False, "confirming")
    assert g.decide(sec(40), 1.0, 1.0, sec(35), UP) == (False, "in_sync")


def test_write_confirm_setting_default_and_wiring():
    const = (BASE / "const.py").read_text()
    assert 'CONF_WRITE_CONFIRM = "write_confirm_s"' in const and "WRITE_CONFIRM_DEFAULT = 60" in const
    assert "CONF_WRITE_CONFIRM" in (BASE / "config_flow.py").read_text()
    for f in ("circuit_coordinator.py", "hp_coord_coordinator.py"):
        assert "confirm_s=" in (BASE / f).read_text()
    for lang in ("en", "hu"):
        assert (BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8").count('"write_confirm_s"') >= 2  # 0.65.2: + explanations
    panel = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "not_accepted" in panel and "confirming" in panel


def test_version():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.56.1", "0.57.0", "0.57.1", "0.58.0", "0.59.0", "0.60.0", "0.61.0", "0.62.0", "0.63.0", "0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0", "0.70.1", "0.71.0", "0.71.1", "0.71.2", "0.71.3", "0.71.4", "0.72.0", "0.73.0", "0.74.0", "0.75.0", "0.76.0", "0.77.0", "0.77.1", "0.77.2", "0.77.3", "0.78.0", "0.78.1", "0.78.2", "0.78.3", "0.78.4", "0.79.0", "0.79.1", "0.79.2", "0.79.3", "0.79.4", "0.79.5", "0.79.6", "0.79.7", "0.79.8", "0.79.9", "0.80.0", "0.81.0", "0.81.1", "0.81.2", "0.82.0", "0.82.1", "0.82.2", "0.82.3")

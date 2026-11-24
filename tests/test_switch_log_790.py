"""0.79.0: the 24-hour rolling start count, the switch log (every commanded output change with the PWM cycle and the
catch-up state) and the heat pump's charging reason kept beside a cold-weather ON. A tester's request (11-24)."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core import measures as ms  # noqa: E402

hpc = importlib.import_module("hc_thermostat.core.hp_coord")
T0 = datetime(2026, 11, 24, 0, 0, tzinfo=timezone.utc)


def test_starts_24h_is_rolling_not_since_midnight():
    r = ms.RunCounter()
    t = T0 - timedelta(hours=6)  # 18:00 the day before
    for h in range(36):  # one start an hour for 36 hours
        r.update(t + timedelta(hours=h), False)
        r.update(t + timedelta(hours=h, minutes=20), True)
    now = t + timedelta(hours=35, minutes=30)  # 05:30 the next day
    assert r.starts_24h(now) == 24
    assert r.summary(now)["starts_24h"] == 24
    assert r.summary(now)["starts_today"] < 24  # since midnight: fewer


def test_switch_log_records_changes_only():
    log = ms.SwitchLog(keep=5)
    assert log.update(T0, False) is False  # the first value seen is not a change
    assert log.update(T0 + timedelta(minutes=1), False) is False
    assert log.update(T0 + timedelta(minutes=2), True, indoor=20.9, target=21.0, demand=0.31, reason="regulating",
                      cycle_s=3600.0, cycle_pos_s=0, carry_s=12.0, catchup=False, catchup_low="low") is True
    item = log.items[-1]
    assert item["on"] is True and item["demand"] == 0.31 and item["cycle_s"] == 3600.0 and item["catchup_low"] == "low"
    assert "limited_by" not in item  # None is left out
    log.update(T0 + timedelta(minutes=20), False, reason="regulating")
    assert log.count(T0 + timedelta(minutes=30)) == 1 and log.count(T0 + timedelta(minutes=30), on=False) == 1
    assert log.count(T0 + timedelta(hours=25)) == 0


def test_switch_log_keeps_the_last_and_survives_a_restart():
    log = ms.SwitchLog(keep=3)
    log.update(T0, False)
    for i in range(1, 8):
        log.update(T0 + timedelta(minutes=i), i % 2 == 1)
    assert len(log.items) == 3
    back = ms.SwitchLog(keep=3)
    back.restore(log.state())
    assert list(back.items) == list(log.items) and back.last is log.last
    back.restore({"items": [{"t": 1, "on": True}, "x", {"t": "2026-11-24T00:00:00+00:00", "on": "yes"}]})  # junk ignored
    assert len(back.items) == 3


def test_heat_reason_is_there_without_the_cold_weather_on_too():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_reserve=5))
    d = h.step(T0, hpc.HpInputs(outdoor=2.0, top=30.0, charge=None, trend_c_h=0.0,
                                  circuits=(hpc.CircuitNeed("floor", True, 33.0, 2.0),)))
    assert d.heat_demand and d.details["heat_reason"] == d.reason == "heat_needed"


def test_heat_reason_beside_cold_on():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_reserve=5, hp_cold_on=True, hp_cold_on_below=5.0))
    d = h.step(T0, hpc.HpInputs(outdoor=-3.0, top=30.0, charge=None, trend_c_h=0.0,
                                  circuits=(hpc.CircuitNeed("floor", True, 33.0, 2.0),)))
    assert d.reason == "cold_on" and d.heat_demand and d.details["heat_reason"] == "heat_needed"

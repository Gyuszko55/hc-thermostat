"""0.48.1: an outside review of 0.47.0–0.48.0 – the valve delay PWM (measured), small demands, the failsafe without
an earlier decision, the cold radiator over PWM pauses, fault codes, hPa, the CI actions pinned."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core import measures as ms  # noqa: E402
from core.matrix import fit_cycle, min_cycle_s  # noqa: E402
from core.model import HcConfig  # noqa: E402
from core.pwm import Pwm  # noqa: E402

T0 = datetime(2026, 11, 13, tzinfo=timezone.utc)


def _useful(cycle, delay, demand, carry=False, min_on=300, min_off=300, hours=12):
    """The share of the time with useful heat: a run gives heat only after the delay (the water stays warm while the
    relay stays on into the next cycle)."""
    p = Pwm(HcConfig(cycle_s=cycle, min_on_s=min_on, min_off_s=min_off, valve_delay_s=delay, pwm_carry=carry))
    on_since, useful, dt = None, 0.0, 30
    for k in range(int(hours * 3600 / dt)):
        now = T0 + timedelta(seconds=k * dt)
        out, _ = p.step(now, demand)
        if out:
            on_since = on_since or now
            useful += dt if (now - on_since).total_seconds() >= delay else 0
        else:
            on_since = None
    return useful / (hours * 3600)


# --- 1. the valve delay: no jump to a full cycle --------------------------------------------------------------------
@pytest.mark.parametrize("cycle,delay", [(1800, 300), (1800, 600), (2400, 600), (1200, 300)])
def test_useful_heat_follows_the_demand_with_a_valve_delay(cycle, delay):
    for demand in (0.1, 0.2, 0.3, 0.4, 0.6):
        assert _useful(cycle, delay, demand) == pytest.approx(demand, abs=0.06), (cycle, delay, demand)


def test_the_review_table_30_min_5_min():
    """Before: 70 % gave 99 %; 20–60 % were right."""
    got = [round(_useful(1800, 300, d) * 100) for d in (0.2, 0.3, 0.4, 0.6, 0.7)]
    assert got == [20, 30, 40, 60, 70]


def test_a_full_cycle_only_when_the_useful_demand_reaches_it():
    p = Pwm(HcConfig(cycle_s=1800, min_on_s=300, min_off_s=300, valve_delay_s=600))
    assert p._on_time(0.4) == 720 + 600  # 12 useful minutes + the delay: below 25 minutes, not a full cycle
    assert p._on_time(0.7) == 1500  # 21 + 10 minutes > 25: capped at the pause (before: a full cycle)
    assert p._short == pytest.approx(1260 - 900)  # the 6 useful minutes it could not give are carried
    assert p._on_time(0.85) == 1800  # the useful demand itself reaches the cycle minus the pause


def test_a_cycle_too_short_for_the_delay():
    assert min_cycle_s(600, 300, 300) == 1200
    assert fit_cycle(900, 600, 300, 300) == 1800.0  # 1.5 × 20 minutes, in whole 5 minutes
    assert fit_cycle(1800, 600, 300, 300) == 1800 and fit_cycle(600, 0, 300, 300) == 600
    cf = importlib.import_module("hc_thermostat.config_flow") if _has_ha() else None
    if cf:
        assert cf._cycle_too_short({"valve_delay_s": 600, "cycle_s": 900, "min_on_s": 300, "min_off_s": 300})
        assert not cf._cycle_too_short({"valve_delay_s": 0, "cycle_s": 600, "min_on_s": 300, "min_off_s": 300})


def _has_ha():
    try:
        import homeassistant  # noqa: F401
        return True
    except ImportError:
        return False


# --- 2. small demands ----------------------------------------------------------------------------------------------
def test_small_demands_add_up_when_turned_on():
    """15-minute cycle, 5-minute minimum: 30 % used to give nothing; collected it gives its 30 %."""
    assert _useful(900, 0, 0.3) == 0.0  # off by default: 270 s < 300 s gives nothing, as before
    assert _useful(900, 0, 0.3, carry=True) == pytest.approx(0.3, abs=0.03)
    assert _useful(900, 0, 0.2, carry=True) == pytest.approx(0.2, abs=0.03)
    assert HcConfig().pwm_carry is False


# --- 3. the failsafe without an earlier decision ---------------------------------------------------------------
def test_the_failsafe_switches_off_without_an_earlier_decision(monkeypatch):
    pytest.importorskip("homeassistant")
    coord_mod = importlib.import_module("hc_thermostat.coordinator")
    c = object.__new__(coord_mod.HcCoordinator)
    c.config_entry, c.data, c.sensor_problems, c.managed = SimpleNamespace(title="Probe"), None, {}, False
    c.cfg = HcConfig(frost_temp=7.0)
    c.step_errors = coord_mod.FAILSAFE_AFTER - 1
    try:
        raise RuntimeError("the first step after a start fails")
    except RuntimeError:
        d = asyncio.run(c._failsafe(T0))
    assert d.output is False and d.fault is True and d.details["failsafe"] == coord_mod.FAILSAFE_AFTER
    assert c.sensor_problems[coord_mod.FAILSAFE_KEY] == "internal_error"


# --- 4. the cold radiator over PWM pauses ----------------------------------------------------------------------------
def test_a_radiator_cold_over_several_short_burns():
    w = ms.RadiatorWatch()
    t, status = T0, None
    for burn in range(3):  # three 8-minute burns with 12-minute pauses: 24 minutes of heating, never warm
        for m in range(0, 20):
            heating = m < 8
            status = w.update(t, 21.0, 19.0, heating, True)
            t += timedelta(minutes=1)
    assert status == "cold" and w.cold_for_min() >= 20
    w.update(t, 21.0, 21.5, False, False)  # the room needs no more heat: starts again
    assert w.cold_for_min() == 0


def test_warm_is_relative_to_the_flow_and_lower_for_a_heat_pump():
    assert ms.RadiatorWatch.warm(29.0, 21.0, flow=35.0)  # 40 % of the flow's 14 °C lead: 26.6 °C
    assert not ms.RadiatorWatch.warm(24.0, 21.0, flow=35.0)
    assert ms.RadiatorWatch.warm(26.0, 21.0, low_temp=True) and not ms.RadiatorWatch.warm(26.0, 21.0)


# --- 5. fault codes, hPa, CI -----------------------------------------------------------------------------------------
def test_zero_fault_codes_and_own_no_fault_values():
    for ok in ("00", "F.00", "0x00", "E-0", "0.0", "0", "ok"):
        assert not ms.fault_active(ok), ok
    for bad in ("E133", "F.28", "0x1A", "12"):
        assert ms.fault_active(bad), bad
    assert not ms.fault_active("255", ("255", "Normál"))
    assert ms.Limits.from_conf({"fault_ok_values": "255, Normál"}).fault_ok == ("255", "Normál")


def test_pressure_in_hpa():
    pytest.importorskip("homeassistant")
    src = (ROOT / "coordinator.py").read_text()
    assert '"hpa": 1000.0' in src


def test_ci_actions_are_pinned():
    wf = (ROOT.parents[1] / ".github" / "workflows" / "validate.yml").read_text()
    assert "hassfest@master" not in wf and "hacs/action@main" not in wf
    assert "hassfest@86d4564" in wf

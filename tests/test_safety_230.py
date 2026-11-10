"""0.23.0: unbelievable readings, burning without command, overheating, electric heat without flame checks."""

from datetime import datetime, timedelta, timezone

from core.boiler_health import BoilerHealth, health_kind
from core.model import HcConfig, Reading
from core.plausibility import Plausibility

T0 = datetime(2026, 11, 9, 20, 0, tzinfo=timezone.utc)
CFG = HcConfig()


def at(minutes):
    return T0 + timedelta(minutes=minutes)


# --- plausibility -------------------------------------------------------------------------------------------
def test_out_of_range_counts_as_lost():
    p = Plausibility(3, 35, 4, 600)
    assert p.check(at(0), Reading(21.0)).value == 21.0
    assert p.check(at(1), Reading(0.0)).value is None
    assert p.problem == "out_of_range"
    assert p.check(at(2), Reading(45.0)).value is None
    assert p.check(at(3), Reading(21.2)).value == 21.2 and p.problem is None


def test_a_glitch_keeps_the_last_believed_value():
    p = Plausibility(3, 35, 4, 600)
    p.check(at(0), Reading(21.0))
    r = p.check(at(1), Reading(12.0))
    assert r.value == 21.0 and p.problem == "jump"
    assert p.check(at(2), Reading(21.1)).value == 21.1 and p.problem is None


def test_a_new_level_that_holds_is_believed():
    p = Plausibility(3, 35, 4, 600)
    p.check(at(0), Reading(21.0))
    for m in range(1, 11):  # the suspicion starts at minute 1
        assert p.check(at(m), Reading(15.0)).value == 21.0
    assert p.check(at(11), Reading(15.0)).value == 15.0 and p.problem is None


def test_slow_change_is_never_a_jump():
    p = Plausibility(3, 35, 4, 600)
    v = 21.0
    for m in range(0, 120, 5):
        v -= 0.5
        assert p.check(at(m), Reading(v)).value == v


def test_outdoor_has_no_jump_check():
    p = Plausibility(-45, 55)
    p.check(at(0), Reading(3.0))
    assert p.check(at(1), Reading(15.0)).value == 15.0
    assert p.check(at(2), Reading(-60.0)).value is None


# --- boiler health ------------------------------------------------------------------------------------------
def run(health, steps, indoor=None, target=None, every_s=30):
    """steps: (minute, relay_on, power W[, indoor]) held until the next step."""
    out, idx, t = [], 0, 0.0
    end = steps[-1][0]
    while t / 60 <= end:
        m = t / 60
        while idx + 1 < len(steps) and steps[idx + 1][0] <= m:
            idx += 1
        step = steps[idx]
        room = step[3] if len(step) > 3 else indoor
        out.append(health.update(T0 + timedelta(seconds=t), step[1], step[2], None, False, room, target))
        t += every_s
    return out


def test_hot_water_with_relay_off_is_normal():
    # a 20-minute shower and a 15-minute one in the same hour: the combi boiler burns with the relay off
    states = run(BoilerHealth(CFG), [(0, False, 120), (20, False, 6), (30, False, 120), (45, False, 6), (60, False, 6)])
    assert set(states) == {"ok"}


def test_burning_all_hour_with_relay_off_is_uncommanded():
    states = run(BoilerHealth(CFG), [(0, False, 120), (60, False, 120)])
    assert states[-1] == "uncommanded_burn"
    assert "uncommanded_burn" not in states[: 44 * 2]


def test_electric_heater_drawing_with_relay_off():
    h = BoilerHealth(CFG, "electric")
    states = run(h, [(0, False, 1500), (6, False, 1500)])
    assert states[-1] == "uncommanded_burn"


def test_overheating():
    # relay on, burning, the room 2.3 above the target and rising
    steps = [(m, True, 120, 21.0 + 2.0 + m * 0.02) for m in range(0, 31)]
    states = run(BoilerHealth(CFG), steps, target=21.0)
    assert states[-1] == "overheating"


def test_warm_room_without_heating_is_no_overheating():
    steps = [(m, False, 6, 23.5 + m * 0.02) for m in range(0, 31)]
    assert set(run(BoilerHealth(CFG), steps, target=21.0)) == {"ok"}


def test_warm_but_falling_room_is_no_overheating():
    steps = [(m, True, 120, 23.6 - m * 0.01) for m in range(0, 31)]
    assert "overheating" not in run(BoilerHealth(CFG), steps, target=21.0)


def test_electric_heater_with_own_thermostat_is_ok():
    # relay on, the oil radiator's own thermostat switches it off and on: no flame and no "no response" checks
    steps = [(0, True, 1500), (10, True, 0), (25, True, 1500), (35, True, 0), (60, True, 0)]
    assert set(run(BoilerHealth(CFG, "electric"), steps)) == {"ok"}


def test_electric_heater_below_the_old_burn_level_is_not_no_flame():
    cfg = HcConfig(power_idle_w=5, power_burn_w=300)
    steps = [(0, True, 150), (30, True, 150)]
    assert set(run(BoilerHealth(cfg, "electric"), steps)) == {"ok"}


def test_kind_by_source():
    assert health_kind("onoff_boiler") == "flame"
    assert health_kind("modulating_boiler") == "flame"
    assert health_kind("electric_heater") == "electric"
    assert health_kind("electric_boiler") == "electric"
    assert health_kind(None) == "flame"


def test_gas_boiler_checks_unchanged():
    states = run(BoilerHealth(CFG), [(0, True, 6), (5, True, 6)])
    assert states[-1] == "no_response"

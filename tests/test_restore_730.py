"""0.73.0 (a tester's request): supervised restore – a Tuya heat pump came back from off / auto with 12 °C and HC, as
designed, stopped writing it as a conflict. Optional: a lasting conflict is written again, a few times, then reported."""

import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
og = importlib.import_module("hc_thermostat.core.output_guard")
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

T0 = datetime(2026, 11, 17, 14, 0, tzinfo=timezone.utc)
UP = 1e6


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def _taken(g, minute=0.0, value=45.0):
    """HC wrote `value` and the unit confirmed it."""
    assert g.decide(at(minute), value, 30.0, at(minute - 60), UP) == (True, "write")
    g.wrote(at(minute), value)
    assert g.decide(at(minute + 1), value, value, at(minute + 0.5), UP)[1] == "in_sync" and g.confirmed


def test_off_by_default_a_conflict_stays_as_before():
    g = og.OutputGuard(confirm_s=60)
    _taken(g)
    for m in (3, 30, 300):
        assert g.decide(at(m), 45.0, 12.0, at(2), UP) == (False, "conflict")


def test_a_lasting_conflict_is_restored_and_a_restore_that_holds_starts_the_count_again():
    g = og.OutputGuard(confirm_s=60, restore_after_s=600, restore_tries=3)
    _taken(g)
    assert g.decide(at(3), 45.0, 12.0, at(2), UP) == (False, "conflict")  # 14:26 off → back with 12 °C
    assert g.decide(at(12), 45.0, 12.0, at(2), UP) == (False, "conflict")  # still waiting
    assert g.decide(at(13), 45.0, 12.0, at(2), UP) == (True, "restore")
    g.wrote(at(13), 45.0)
    assert g.restore_count == 1
    assert g.decide(at(14), 45.0, 45.0, at(13.5), UP)[1] == "in_sync"  # it took it
    assert g.decide(at(25), 45.0, 45.0, at(13.5), UP)[1] == "in_sync"
    assert g.restore_count == 0  # held for 10 minutes: the count starts again


def test_a_unit_that_keeps_its_own_value_fails_after_the_tries_and_waits_for_a_new_target():
    g = og.OutputGuard(confirm_s=60, restore_after_s=600, restore_tries=3)
    _taken(g)
    m, restores = 3.0, 0
    status = None
    while m < 200 and status != "failed":
        write, status = g.decide(at(m), 45.0, 12.0, at(m - 0.5), UP)
        if write:
            restores += 1
            g.wrote(at(m), 45.0)
            # the unit echoes 45 for a moment, then goes back to 12 (its app / mode keeps it)
            assert g.decide(at(m + 0.5), 45.0, 45.0, at(m + 0.2), UP)[1] == "in_sync"
        m += 1
    assert status == "failed" and restores == 3 and g.failed and g.failed_want == 45.0
    assert g.decide(at(m + 60), 45.0, 12.0, at(m - 1), UP) == (False, "failed")  # no fight
    assert g.decide(at(m + 61), 40.0, 12.0, at(m - 1), UP) == (True, "write")  # HC wants another value: again
    assert not g.failed and g.restore_count == 0


def test_failed_clears_when_the_unit_shows_hcs_value_again():
    g = og.OutputGuard(confirm_s=60, restore_after_s=60, restore_tries=1)
    _taken(g)
    g.decide(at(3), 45.0, 12.0, at(2), UP)
    assert g.decide(at(4.1), 45.0, 12.0, at(2), UP) == (True, "restore")
    g.wrote(at(4.1), 45.0)
    g.decide(at(4.5), 45.0, 45.0, at(4.2), UP)
    g.decide(at(5), 45.0, 12.0, at(4.8), UP)
    assert g.decide(at(6.5), 45.0, 12.0, at(4.8), UP) == (False, "failed")
    assert g.decide(at(7), 45.0, 45.0, at(6.8), UP)[1] in ("in_sync", "write") and not g.failed


def test_an_unaccepted_value_is_restored_too():
    g = og.OutputGuard(confirm_s=60, restore_after_s=600, restore_tries=2, max_retries=1)
    assert g.decide(at(0), 45.0, 30.0, at(-60), UP) == (True, "write")
    g.wrote(at(0), 45.0)
    assert g.decide(at(2), 45.0, 30.0, at(-60), UP) == (True, "write")  # no echo: one retry
    g.wrote(at(2), 45.0)
    assert g.decide(at(4), 45.0, 30.0, at(-60), UP) == (False, "not_accepted")
    assert g.decide(at(14.5), 45.0, 30.0, at(-60), UP) == (True, "restore")


def test_settings_sensor_repairs_and_drawing():
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        st = tr["options"]["step"]["hp_coord"]
        assert st["data"]["write_restore_min"] and len(st["data_description"]["write_restore_min"]) > 150
        assert tr["entity"]["binary_sensor"]["hp_write_problem"]["name"]
        assert "{entity}" in tr["issues"]["write_failed"]["description"]
    from hc_thermostat import config_flow as cf
    keys = {str(k) for k in cf._write_fields("hp_coord", {})}
    assert {"write_restore_min", "write_restore_tries"} <= keys
    assert "write_restore_min" not in {str(k) for k in cf._write_fields("circuit", {})}
    assert "HcHpWriteProblem(c)" in (BASE / "binary_sensor.py").read_text()
    assert "rstFail" in (BASE / "www" / "hc-overview.js").read_text()
    assert '"restore": {"status"' in (BASE / "hp_coord_coordinator.py").read_text()


def test_mode_counts_with_the_restore_on():
    from types import SimpleNamespace
    from hc_thermostat.output_writer import OutputWriter
    st = SimpleNamespace(state="auto", attributes={"hvac_modes": ["off", "heat", "auto"]}, last_changed=T0)
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda e: st))
    plain = OutputWriter(hass, "climate.hp", onoff=True)
    strict = OutputWriter(hass, "climate.hp", onoff=True, restore_s=600)
    assert plain.read()[0] == 1.0  # as before: any mode but off is on
    assert strict.read()[0] == 0.5  # auto instead of heat: a difference to restore
    st.state = "heat"
    assert strict.read()[0] == 1.0
    st.state = "off"
    assert strict.read()[0] == 0.0


def test_every_restore_writes_what_hc_asks_now():
    g = og.OutputGuard(confirm_s=60, restore_after_s=600, restore_tries=3)
    _taken(g)
    g.decide(at(3), 45.0, 12.0, at(2), UP)
    # the wood fire started meanwhile: HC asks 30 °C now – the restore writes that (the unit is at 12)
    assert g.decide(at(13), 30.0, 12.0, at(2), UP) == (True, "restore")

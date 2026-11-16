"""0.62.0 (tester's second round on a buffer system): the mixing circuit's target stays on the curve in a TPI / PWM
pause (the pump enable is the separate demand), the plant (tank, circuits, heat pump coordination) joins one house by
its links, and the source watch says no_data only for a reading that was set and got lost."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from hc_thermostat.core.boiler_health import QUIET_STATES, STATES, BoilerHealth  # noqa: E402
from hc_thermostat.core.circuit import CircuitConfig, MixingCircuit, ZoneReading  # noqa: E402
from hc_thermostat.core.house import Facts, houses  # noqa: E402
from hc_thermostat.core.model import HcConfig as ControllerConfig  # noqa: E402

T0 = datetime(2026, 11, 16, 6, 0)


def _floor(**kw):
    return MixingCircuit(CircuitConfig.from_conf({"circuit_kind": "floor", "circuit_slope": 0.5, **kw}))


def test_pause_keeps_the_curve_at_the_zones_target():
    c = _floor()
    zones = [ZoneReading("nappali", False, 23.2, 22.9), ZoneReading("furdo", False, 22.0, 21.8)]
    d = c.step(T0, zones, 5.6)
    assert not d.demand and d.t_room == 23.2 and d.details["room_from"] == "zones"
    assert d.raw == pytest.approx(23.2 + 0.5 * (23.2 - 5.6), abs=0.01)  # 32.0, not the 20 °C room's 27.2


def test_no_drop_after_the_hold_runs_out():
    c = _floor(circuit_hold_s=1800)
    ask = [ZoneReading("nappali", True, 23.2, 22.5)]
    pause = [ZoneReading("nappali", False, 23.2, 22.9)]
    first = c.step(T0, ask, 5.6)
    later = c.step(T0 + timedelta(minutes=45), pause, 5.6)  # the hold is over: no lasting demand
    assert first.demand and not later.demand
    assert later.t_room == first.t_room == 23.2
    # the curve stays; only the room correction (a demand's deficit) is gone
    assert later.raw == pytest.approx(first.raw - first.details["correction"], abs=0.01)


def test_old_behaviour_and_fallback():
    off = _floor(circuit_idle_keep=False)
    d = off.step(T0, [ZoneReading("nappali", False, 23.2, 22.9)], 5.6)
    assert d.t_room == 20.0 and d.details["room_from"] == "default"
    none = _floor()
    d = none.step(T0, [ZoneReading("nappali", False, None, 22.9), ZoneReading("x", False, 24.0, 20, fault=True)], 5.6)
    assert d.t_room == 20.0 and d.details["room_from"] == "default"
    d = none.step(T0, [ZoneReading("nappali", True, 22.0, 21.0), ZoneReading("halo", False, 24.0, 20)], 5.6)
    assert d.t_room == 22.0 and d.details["room_from"] == "demand"  # with demand only the asking zones count


def test_hp_need_still_only_from_demanding_circuits():
    from hc_thermostat.core import hp_coord
    src = Path(hp_coord.__file__).read_text(encoding="utf-8")
    assert "for c in i.circuits if c.demand and c.target is not None" in src


def _f(eid, role, link="auto", rooms=(), zones=(), feeds=(), area=None):
    return Facts(entry_id=eid, title=eid, role=role, link=link, rooms=tuple(rooms), leading_area=area,
                 zone_entries=tuple(zones), feeds_from=tuple(feeds))


def _plant(buffer_zones=()):
    zones = [_f("halo", "zone", "own", [("halo", "a_halo")], area="a_halo")]
    zones += [_f(z, "zone", "halo", [(z, "a_" + z)], area="a_" + z) for z in ("gyerek", "moso", "furdo", "nappali")]
    return zones + [
        _f("rad", "circuit", "halo", zones=("halo", "gyerek", "furdo"), feeds=("buf",)),
        _f("flo", "circuit", "halo", zones=("furdo", "nappali"), feeds=("buf",)),
        _f("buf", "buffer", zones=buffer_zones),
        _f("hp", "hp_coord", feeds=("buf",)),
    ]


def test_buffer_system_is_one_house():
    links = houses(_plant())
    assert {e for e, l in links.items() if l.host == "halo"} == {"halo", "gyerek", "moso", "furdo", "nappali", "rad",
                                                                  "flo", "buf", "hp"}
    assert links["buf"].why == "plant" and links["hp"].why == "plant"
    assert set(links["halo"].members) >= {"buf", "hp", "rad", "flo"}


def test_buffer_with_zones_still_by_zones_and_hp_follows():
    links = houses(_plant(buffer_zones=("halo", "nappali")))
    assert links["buf"].why == "zones" and links["hp"].host == "halo"


def test_tank_and_heat_pump_alone_tank_is_the_house():
    links = houses([_f("hp", "hp_coord", feeds=("buf",)), _f("buf", "buffer")])
    assert links["hp"].host == "buf" and links["buf"].host == "buf"


def test_explicit_own_wins():
    facts = _plant()
    facts[-1] = _f("hp", "hp_coord", "own", feeds=("buf",))
    links = houses(facts)
    assert links["hp"].host == "hp" and links["buf"].host == "halo"


def test_unwatched_source_is_no_no_data():
    cfg = ControllerConfig()
    h = BoilerHealth(cfg, "electric")
    for m in range(0, 30, 1):
        state = h.update(T0 + timedelta(minutes=m), m % 10 < 5, None, None, False, watched=False)
    assert state == "unwatched" and not h.problem
    lost = BoilerHealth(cfg, "electric")
    for m in range(0, 30, 1):
        state = lost.update(T0 + timedelta(minutes=m), True, None, None, False)
    assert state == "no_data" and lost.problem
    assert "unwatched" in STATES and "unwatched" in QUIET_STATES


def test_heating_fault_still_shows_unwatched():
    h = BoilerHealth(ControllerConfig(), "electric")
    assert h.update(T0, True, None, None, True, watched=False) == "heating_fault"


def test_translations_and_forms():
    for lang in ("hu", "en"):
        d = json.loads((BASE / "translations" / f"{lang}.json").read_text(encoding="utf-8"))
        assert d["entity"]["sensor"]["boiler_health"]["state"]["unwatched"]
        for step in ("buffer", "circuit", "hp_coord"):
            assert d["options"]["step"][step]["data"]["house_link"]
        assert d["options"]["step"]["circuit_settings"]["data"]["circuit_idle_keep"]
        assert d["config"]["step"]["circuit_settings"]["data"]["circuit_idle_keep"]
    from hc_thermostat.config_flow import _circuit_settings
    keys = [str(k) for k in _circuit_settings({}, "floor")]
    assert "circuit_idle_keep" in keys
    src = (BASE / "config_flow.py").read_text(encoding="utf-8")
    assert src.count("_house_select(self, current)  # 0.62.0") == 3
    assert '"pump_enable": d.demand' in (BASE / "sensor.py").read_text(encoding="utf-8")


def test_overview_warning_words_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    ov = (BASE / "www" / "hc-overview.js").as_uri()
    zone = lambda eid, st: {"entry_id": eid, "title": "HC " + eid, "role": "zone", "health": {"state": st},  # noqa: E731
                            "decision": {"target": 21, "indoor": 20.5}}
    all_ = [zone("Halo", "unwatched"), zone("Gyerek", "learning"), zone("Moso", "no_data")]
    script = f"""
import * as OV from {json.dumps(ov)};
const html = OV.renderOverview({json.dumps(all_)}, {{ lang: "hu" }});
console.log(JSON.stringify({{ html }}));
"""
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    html = json.loads(res.stdout.strip().splitlines()[-1])["html"]
    assert "unwatched" not in html and "learning" not in html
    assert "hőforrás-figyelés: a hőforrás teljesítménymérője / lángjele nem ad adatot" in html

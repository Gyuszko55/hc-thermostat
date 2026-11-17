"""0.71.0: the house's AI analysis of yesterday – HC works the numbers out, the AI only explains and suggests."""

import asyncio
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from hc_thermostat.core import day_report as dr  # noqa: E402

D0 = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
D1 = D0 + timedelta(days=1)


def h(x):
    return D0 + timedelta(hours=x)


def test_number_stats_time_weighted_with_carry_in():
    pts = [(D0 - timedelta(hours=2), 20.0), (h(12), 22.0)]
    s = dr.number_stats(pts, D0, D1)
    assert s == {"mean": 21.0, "min": 20.0, "max": 22.0, "hours": 24.0}
    assert dr.number_stats([], D0, D1) is None
    assert dr.number_stats([(h(1), None)], D0, D1) is None


def test_durations_and_on_stats():
    pts = [(D0, "regulating"), (h(6), "at_target"), (h(18), "unavailable"), (h(20), "regulating")]
    assert dr.durations(pts, D0, D1) == {"at_target": 12.0, "regulating": 10.0}
    on = [(D0, False), (h(1), True), (h(2), False), (h(3), True), (h(5), False)]
    assert dr.on_stats(on, D0, D1) == {"hours": 3.0, "starts": 2}


def test_climate_stats_cold_and_overheated_hours():
    pts = [(D0, ("heat", 21.5, 22.5, "heating", "home")),  # 1 °C below: cold
           (h(4), ("heat", 22.4, 22.5, "idle", "home")),
           (h(10), ("heat", 23.2, 22.5, "idle", "home")),  # 0.7 above: overheated
           (h(12), ("off", 22.0, None, "off", None))]
    s = dr.climate_stats(pts, D0, D1)
    assert s["cold_h"] == 4.0 and s["overheated_h"] == 2.0
    assert s["heating"] == {"hours": 4.0, "starts": 0} and s["presets"] == {"off": 12.0, "home": 12.0}
    assert s["target"]["mean"] == 22.5 and s["room"]["max"] == 23.2


def test_energy():
    assert dr.energy_kwh_from_power([(D0, 1000.0), (h(2), 0.0)], D0, D1) == 2.0
    assert dr.meter_delta([(D0 - timedelta(hours=1), 100.0), (h(5), 101.5), (h(20), 103.0)], D0, D1) == 3.0
    assert dr.meter_delta([(h(5), 1.0)], D0, D1) is None
    gas = dr.energy_and_cost(3.0, 18.0, None, 9.0, 300.0, None, False)
    assert gas == {"fuel": 6.0, "heat_kwh": 54.0, "how": "estimated", "cost": 1800.0}
    assert dr.energy_and_cost(3.0, 18.0, 4.2, 9.0, None, None, False)["how"] == "measured"
    assert dr.energy_and_cost(None, 0, None, 0, 70.0, 5.0, True) == {"electric_kwh": 5.0, "how": "measured", "cost": 350.0}
    assert dr.energy_and_cost(None, 0, None, 0, None, None, True) == {}


def test_parse_lines():
    assert dr.parse_lines("• egy\n- kettő\n1. három\n\nNincs teendő.") == ["egy", "kettő", "három"]
    assert dr.parse_lines(["a", "b"]) == ["a", "b"]


def test_ask_ai_sends_numbers_and_structure():
    from hc_thermostat import ai_report as ar
    sent = {}

    async def call(domain, service, data, blocking=False, return_response=False):
        sent.update(domain=domain, service=service, data=data)
        return {"data": {"score": "7", "summary": "Rendben.", "observations": "• a\n• b", "todos": "Nincs teendő."}}

    hass = SimpleNamespace(services=SimpleNamespace(async_call=call))
    out = asyncio.run(ar.ask_ai(hass, "ai_task.x", {"house": "Ház", "day": "2026-11-16", "members": []}, "hu"))
    assert out == {"score": 7.0, "summary": "Rendben.", "observations": ["a", "b"], "todos": []}
    assert sent["domain"] == "ai_task" and sent["service"] == "generate_data" and sent["data"]["entity_id"] == "ai_task.x"
    assert set(sent["data"]["structure"]) == {"score", "summary", "observations", "todos"}
    assert "csak javaslat" in sent["data"]["instructions"].lower() or "nem állít át" in sent["data"]["instructions"]
    assert '"house": "Ház"' in sent["data"]["instructions"]


def test_daily_time_and_day_bounds():
    from hc_thermostat import ai_report as ar
    rep = ar.AiReporter.__new__(ar.AiReporter)
    rep.entry = SimpleNamespace(data={}, options={"ai_report_time": "07:15:00"})
    assert rep.daily_time() == (7, 15, 0)
    rep.entry = SimpleNamespace(data={}, options={})
    assert rep.daily_time() == (6, 30, 0)


def test_form_texts_panel():
    from hc_thermostat import config_flow as cf
    assert {"ai_task_entity", "ai_report_time"} <= set(cf.SETTINGS_SECTIONS["functions"])
    for lang in ("hu", "en"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text())
        sec = tr["options"]["step"]["settings"]["sections"]["functions"]
        assert sec["data"]["ai_task_entity"] and len(sec["data_description"]["ai_task_entity"]) > 100
        assert tr["entity"]["sensor"]["ai_report"]["name"] and tr["entity"]["button"]["ai_report_now"]["name"]
    panel = (BASE / "www" / "hc-info-panel.js").read_text()
    for s in ("_aiButton", "_aiModal", "hc_thermostat/ai_report_run", "data-ai=\"open\""):
        assert s in panel

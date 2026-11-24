"""0.78.2 (security review): the manual AI analysis (button, panel) is rate limited – at most every 15 minutes and
MANUAL_PER_DAY a day; the scheduled morning report is not counted."""

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT / "custom_components"))

ai_mod = importlib.import_module("hc_thermostat.ai_report")

T0 = datetime(2026, 11, 21, 9, 0, tzinfo=timezone.utc)


def _reporter(monkeypatch):
    runs = []

    async def collect(hass, entry, now):
        runs.append(now)
        return {"day": "2026-11-20", "house": "H"}

    monkeypatch.setattr(ai_mod, "collect", collect)

    class _Store:
        async def async_save(self, data):
            pass

    r = object.__new__(ai_mod.AiReporter)
    r.hass = SimpleNamespace(config=SimpleNamespace(language="hu"), bus=SimpleNamespace(async_fire=lambda *a: None))
    r.entry = SimpleNamespace(entry_id="E", data={}, options={})
    r.report, r.running, r._store = None, False, _Store()
    r._manual_day, r._manual_count, r._manual_last = None, 0, None
    return r, runs


def test_cooldown_and_daily_cap(monkeypatch):
    r, runs = _reporter(monkeypatch)
    asyncio.run(r.async_run(T0, manual=True))
    with pytest.raises(ai_mod.AiLimited, match="perc múlva"):
        asyncio.run(r.async_run(T0 + timedelta(minutes=5), manual=True))
    t = T0
    for _ in range(ai_mod.MANUAL_PER_DAY - 1):
        t += timedelta(seconds=ai_mod.MANUAL_COOLDOWN_S)
        asyncio.run(r.async_run(t, manual=True))
    assert len(runs) == ai_mod.MANUAL_PER_DAY
    with pytest.raises(ai_mod.AiLimited, match="holnap"):
        asyncio.run(r.async_run(t + timedelta(hours=1), manual=True))
    asyncio.run(r.async_run(t + timedelta(hours=1)))  # the scheduled run is not limited
    asyncio.run(r.async_run(T0 + timedelta(days=1), manual=True))  # a new day
    assert len(runs) == ai_mod.MANUAL_PER_DAY + 2


def test_button_and_panel_use_the_limit():
    assert "async_run(manual=True)" in (BASE / "button.py").read_text()
    info = (BASE / "info.py").read_text()
    assert "async_run(manual=True)" in info and '"rate_limited"' in info
    assert "await coordinator.ai.async_run()" in (BASE / "__init__.py").read_text()  # the morning run: unlimited

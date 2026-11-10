"""0.16.1: seeding the heat need from statistics skips the first, partial day of a new heat sensor."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
cc = importlib.import_module("hc_thermostat.coordinator")

D0 = datetime(2026, 10, 10, tzinfo=timezone.utc)


def _stats(first_day: int, days: int):
    rows = lambda key, val: [{"start": (D0 + timedelta(days=first_day + i)).timestamp(), key: val} for i in range(days)]
    return {"sensor.gas": rows("change", 2.0), "sensor.in": rows("mean", 22.0), "sensor.out": rows("mean", 4.0)}


def test_sensor_older_than_the_window_keeps_every_day():
    s = cc.seed_samples(_stats(0, 30), "sensor.gas", "sensor.in", "sensor.out", None, 9.0, 3.0, D0.timestamp())
    assert len(s) == 30 and s[0][1] == 18.0 and s[0][2] == 18.0 * 24


def test_new_sensor_drops_its_first_partial_day():
    s = cc.seed_samples(_stats(27, 3), "sensor.gas", "sensor.in", "sensor.out", None, 9.0, 3.0, D0.timestamp())
    assert len(s) == 2


def test_millisecond_starts_and_small_delta_days():
    st = _stats(0, 3)
    for rows in st.values():
        for r in rows:
            r["start"] *= 1000
    st["sensor.out"][1]["mean"] = 20.0  # only 2 K: not a heating day
    s = cc.seed_samples(st, "sensor.gas", "sensor.in", "sensor.out", None, 9.0, 3.0, D0.timestamp())
    assert len(s) == 2

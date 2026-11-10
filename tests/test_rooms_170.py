"""0.17.0: room thermometers next to the main one – advice only, the main thermometer decides."""

import importlib
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
rooms = importlib.import_module("hc_thermostat.core.rooms")
cc = importlib.import_module("hc_thermostat.coordinator")

T0 = datetime(2026, 11, 9, 0, 0, tzinfo=timezone.utc)


def _feed(m, hours, devs, quiet=True, start=T0):
    """devs: room -> deviation; steps of 30 s for `hours` hours."""
    for k in range(int(hours * 120)):
        now = start + timedelta(seconds=30 * k)
        m.update(now, 22.0, {r: 22.0 + d for r, d in devs.items()}, quiet)
    return start + timedelta(hours=hours)


def test_learning_until_36_quiet_hours():
    m = rooms.RoomMonitor(0.4)
    end = _feed(m, 30, {"Konyha": 0.6})
    a = m.advice(end, ["Konyha"])[0]
    assert a.advice == "learning" and a.hours == 29  # the running hour is not closed yet
    end = _feed(m, 10, {"Konyha": 0.6}, start=end)
    a = m.advice(end, ["Konyha"])[0]
    assert a.advice == "down" and a.deviation == 0.6


def test_up_ok_and_noisy_hours_do_not_count():
    m = rooms.RoomMonitor(0.4)
    end = _feed(m, 40, {"Hálószoba": -0.7, "Nappali2": 0.1})
    _feed(m, 10, {"Hálószoba": 5.0}, quiet=False, start=end)  # heat-up/window: ignored
    adv = {a.room: a for a in m.advice(end + timedelta(hours=10), ["Hálószoba", "Nappali2"])}
    assert adv["Hálószoba"].advice == "up" and adv["Nappali2"].advice == "ok"


def test_old_hours_leave_the_window():
    m = rooms.RoomMonitor(0.4)
    end = _feed(m, 40, {"Konyha": 0.8})
    assert m.advice(end + timedelta(hours=60), ["Konyha"])[0].advice == "learning"


def test_announcements_first_repeat_and_back_to_ok():
    m = rooms.RoomMonitor(0.4)
    a = [rooms.RoomAdvice("Konyha", "down", 0.6, 40)]
    t = T0
    assert [x.advice for x in m.announcements(t, a)] == ["down"]
    assert m.announcements(t + timedelta(days=1), a) == []
    assert [x.advice for x in m.announcements(t + timedelta(days=3, minutes=1), a)] == ["down"]
    ok = [rooms.RoomAdvice("Konyha", "ok", 0.1, 50)]
    assert [x.advice for x in m.announcements(t + timedelta(days=4), ok)] == ["ok"]
    assert m.announcements(t + timedelta(days=5), ok) == []
    assert m.announcements(t, [rooms.RoomAdvice("Hálószoba", "ok", 0.0, 40)]) == []  # never advised: silent


def test_texts():
    hu = rooms.room_text(rooms.Announcement("Konyha", "down", 0.62, 60))
    assert "melegebb" in hu and "lejjebb" in hu and "0,6" in hu and "negyed" in hu
    assert "feljebb" in rooms.room_text(rooms.Announcement("Hálószoba", "up", -1.2, 48)) 
    assert "+0,2" in rooms.room_text(rooms.Announcement("Konyha", "ok", 0.2, 48))
    assert "warmer" in rooms.room_text(rooms.Announcement("Konyha", "down", 0.6, 48), "en")


def test_state_round_trip():
    m = rooms.RoomMonitor(0.4)
    end = _feed(m, 40, {"Konyha": 0.6})
    m.announcements(end, m.advice(end, ["Konyha"]))
    n = rooms.RoomMonitor(0.4)
    n.restore(m.state())
    assert n.advice(end, ["Konyha"])[0].advice == "down" and n.announcements(end, n.advice(end, ["Konyha"])) == []


def test_seed_room_hours_median_per_room():
    start = T0.timestamp()
    stats = {"sensor.main": [{"start": start, "mean": 22.0}],
             "sensor.k1": [{"start": start, "mean": 22.5}], "sensor.k2": [{"start": start, "mean": 23.5}],
             "sensor.k3": [{"start": start, "mean": 22.7}]}
    out = cc.seed_room_hours(stats, "sensor.main", {"Konyha": ["sensor.k1", "sensor.k2", "sensor.k3"]})
    assert len(out) == 1 and out[0][1] == "Konyha" and abs(out[0][2] - 0.7) < 1e-9

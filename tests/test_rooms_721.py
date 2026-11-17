"""0.72.1: a room without a thermometer or a TRV head (a hallway) no longer blocks saving the rooms form."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

from hc_thermostat import room_form as rf  # noqa: E402


def _check(rooms, leading="nappali"):
    return rf.check_rooms("hu", rooms, leading, False, set(), {}, lambda e: e)


def test_a_room_without_measurement_is_saved():
    rooms = [{"key": "nappali", "name": "Nappali", "sensors": ["sensor.n"]},
             {"key": "konyha", "name": "Konyha", "sensors": ["sensor.k"], "trvs": ["climate.k"]},
             {"key": "hallway", "name": "Előszoba"}]
    assert _check(rooms) is None


def test_the_other_checks_stay():
    rooms = [{"key": "nappali", "name": "Nappali", "sensors": ["sensor.n"]},
             {"key": "a", "name": "Konyha", "sensors": ["sensor.n"]}]
    assert "Konyha" in _check(rooms)  # the same thermometer in two rooms
    assert _check([{"key": "x", "name": ""}]) is not None  # a room without a name

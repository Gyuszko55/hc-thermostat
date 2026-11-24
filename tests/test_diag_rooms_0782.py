"""0.78.2 (security review): diagnostics replace every room name by "room:<key>" – consistently, so hcd's import from
them still matches the rooms up – and redact the guard's address and password."""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

diag = importlib.import_module("hc_thermostat.diagnostics")


def test_room_names_become_keys_everywhere():
    options = {"rooms": [{"key": "n", "name": "Nappali", "sensors": ["sensor.n"]},
                         {"key": "konyha", "name": "konyha", "trvs": ["climate.k"]}],
               "leading_room": "n", "trv_offsets": {"Nappali": 0.5}, "guard_url": "http://192.0.2.5/script/1/hc",
               "guard_password": "pw"}
    info = {"rooms": {"trv": {"Nappali": {"key": "n"}}, "asking": ["Nappali"], "advice": [{"room": "Nappali"}]}}
    names = diag.room_names([options])
    out = diag.redact_rooms(diag.async_redact_data(options, diag.TO_REDACT), names)
    assert out["rooms"][0]["name"] == "room:n" and out["trv_offsets"] == {"room:n": 0.5}
    assert out["rooms"][1]["name"] == "konyha"  # the same as its key: kept, so references by key stay intact
    assert out["leading_room"] == "n" and out["guard_url"] == "**REDACTED**" and out["guard_password"] == "**REDACTED**"
    i = diag.redact_rooms(info, {**diag.room_names(info), **names})
    assert i["rooms"]["trv"] == {"room:n": {"key": "n"}} and i["rooms"]["asking"] == ["room:n"]
    assert i["rooms"]["advice"] == [{"room": "room:n"}]
    assert "Nappali" not in repr(out) + repr(i)

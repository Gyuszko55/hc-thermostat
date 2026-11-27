"""0.82.0: HC Lite presets – comfort, sleep, away with an end, vacation, window, the weekend program today, a BLU
button on the relay; Home Assistant's presence, calendar and windows turn into commands (plan_commands)."""

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))
lite = importlib.import_module("hc_thermostat.core.lite")
BASE = ROOT / "custom_components" / "hc_thermostat"
SCRIPT = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")
NOW = 1_795_800_000.0


def _v(**kw):
    st = {"mode": "auto", "preset": "schedule", **kw}
    return lite.view(st)


def test_the_new_settings_go_to_the_device_and_are_cleaned():
    s = lite.LiteSettings.from_conf({"lite_cf_delta": 1.5, "lite_cf_time": 3600, "lite_btn": 204})
    p = lite.settings_payload(s)
    assert p["cf_delta"] == 1.5 and p["cf_time"] == 3600 and p["btn"] == 204
    bad = lite.LiteSettings.from_conf({"lite_cf_delta": 9, "lite_cf_time": 60, "lite_btn": 500})
    assert (bad.cf_delta, bad.cf_time, bad.btn) == (1.0, 7200, -1)
    for k in ("cf_delta", "cf_time", "btn"):
        assert f"C.{k}" in SCRIPT, "the script takes and reports the same setting"


def test_the_status_reads_the_preset():
    v = lite.view({"mode": "auto", "preset": "comfort", "psrc": "button", "puntil": NOW + 7200, "vac": None,
                   "win_s": None, "we_today": True, "btn_ev": "single_push"})
    assert (v.preset, v.psrc, v.puntil, v.we_today, v.btn_ev) == ("comfort", "button", int(NOW + 7200), True, "single_push")
    old = lite.view({"mode": "away"})
    assert old.preset == "schedule" and old.psrc is None, "an older script without presets"
    assert lite.view({"mode": "auto", "preset": "bogus", "psrc": "x"}).preset == "schedule"


def test_presence_states():
    assert lite.presence_away("sensor", "Otthon") is False
    assert lite.presence_away("sensor", "Távol") is True
    assert lite.presence_away("sensor", "Szabadság") is True
    assert lite.presence_away("person", "home") is False
    assert lite.presence_away("person", "Munka") is True, "a person in another zone is away"
    assert lite.presence_away("binary_sensor", "on") is False
    assert lite.presence_away("sensor", "unavailable") is None
    assert lite.presence_away("sensor", "valami") is None


def test_calendar_words():
    assert lite.calendar_kind("Szabadság – Balaton") == "vacation"
    assert lite.calendar_kind("nyaralás") == "vacation"
    assert lite.calendar_kind("Home office") == "home"
    assert lite.calendar_kind("Otthon dolgozom") == "home"
    assert lite.calendar_kind("Fogorvos") is None
    assert lite.calendar_kind(None) is None


def test_everyone_away_20_minutes_then_away_for_12_hours_once():
    memo = {}
    assert lite.plan_commands(NOW, _v(), memo, away=True, away_since=NOW - 600) == [], "not yet 20 minutes"
    c = lite.plan_commands(NOW, _v(), memo, away=True, away_since=NOW - 1300)
    assert c == [{"mode": "away", "for": 43200, "src": "ha"}]
    assert lite.plan_commands(NOW + 30, _v(preset="away", psrc="ha", puntil=NOW + 43170), memo,
                              away=True, away_since=NOW - 1300) == [], "sent once for the episode"


def test_away_is_renewed_while_still_away():
    memo = {"pres": NOW - 1300}
    v = _v(preset="away", psrc="ha", puntil=NOW + 39000)
    assert lite.plan_commands(NOW, v, memo, away=True, away_since=NOW - 1300) == [{"mode": "away", "for": 43200, "src": "ha"}]
    v_button = _v(preset="away", psrc="button", puntil=None)
    assert lite.plan_commands(NOW, v_button, memo, away=True, away_since=NOW - 1300) == [], "a hand-set away is not touched"


def test_a_button_gesture_wins_until_the_next_real_change():
    memo = {"pres": NOW - 5000}
    # away was sent; then someone pressed comfort on the button (still "away" by presence)
    assert lite.plan_commands(NOW, _v(preset="comfort", psrc="button"), memo, away=True, away_since=NOW - 5000) == []
    # someone really comes home, then leaves again: a new episode
    assert lite.plan_commands(NOW + 60, _v(preset="comfort", psrc="button"), memo, away=False, away_since=NOW + 50) == []
    c = lite.plan_commands(NOW + 3000, _v(preset="comfort", psrc="button"), memo, away=True, away_since=NOW + 1500)
    assert c == [{"mode": "away", "for": 43200, "src": "ha"}]


def test_back_home_ends_away_and_vacation():
    memo = {"pres": NOW - 9000}
    assert lite.plan_commands(NOW, _v(preset="away", psrc="ha"), memo, away=False, away_since=NOW - 5) == [{"preset": "home", "src": "ha"}]
    memo = {"pres": NOW - 9000}
    assert lite.plan_commands(NOW, _v(preset="vacation", psrc="ha"), memo, away=False, away_since=NOW - 5) == [{"preset": "home", "src": "ha"}]
    memo = {"pres": NOW - 9000}
    assert lite.plan_commands(NOW, _v(preset="comfort"), memo, away=False, away_since=NOW - 5) == [], "nothing to end"


def test_after_a_restart_home_is_only_the_starting_point():
    memo = {}
    assert lite.plan_commands(NOW, _v(preset="away", psrc="button"), memo, away=False, away_since=NOW - 99999) == []
    assert memo["pres"] == NOW - 99999


def test_off_and_vacation_are_not_overridden_by_leaving():
    for p in ("off", "vacation"):
        assert lite.plan_commands(NOW, _v(preset=p), {}, away=True, away_since=NOW - 2000) == []


def test_a_vacation_event_once_with_its_end():
    memo = {}
    ev = ("Szabadság", NOW + 3 * 86400)
    assert lite.plan_commands(NOW, _v(), memo, event=ev, today="2026-11-27") == [{"vacation": int(NOW + 3 * 86400), "src": "ha"}]
    assert lite.plan_commands(NOW + 30, _v(preset="vacation"), memo, event=ev, today="2026-11-27") == []
    longer = ("Szabadság", NOW + 4 * 86400)
    assert lite.plan_commands(NOW + 60, _v(preset="vacation"), memo, event=longer, today="2026-11-27")[0]["vacation"] == int(NOW + 4 * 86400)


def test_a_home_day_event_the_weekend_program_once_a_day():
    memo = {}
    ev = ("Home office", NOW + 8 * 3600)
    assert lite.plan_commands(NOW, _v(), memo, event=ev, today="2026-11-27") == [{"we_today": True, "src": "ha"}]
    assert lite.plan_commands(NOW + 30, _v(), memo, event=ev, today="2026-11-27") == []
    assert lite.plan_commands(NOW, _v(), {}, event=ev, today="2026-11-27") != []
    assert lite.plan_commands(NOW, _v(we_today=True), {}, event=ev, today="2026-11-27") == [], "already on"
    assert lite.plan_commands(NOW, _v(), {}, event=("Fogorvos", NOW + 3600), today="2026-11-27") == []


def test_windows_open_two_minutes_then_frost_closed_back():
    memo = {}
    assert lite.plan_commands(NOW, _v(), memo, has_windows=True, window_since=NOW - 60) == []
    assert lite.plan_commands(NOW, _v(), memo, has_windows=True, window_since=NOW - 130) == [{"window": True, "for": 3600, "src": "ha"}]
    assert lite.plan_commands(NOW + 30, _v(preset="window"), memo, has_windows=True, window_since=NOW - 130) == [], "once per opening"
    assert lite.plan_commands(NOW + 60, _v(preset="window"), memo, has_windows=True, window_since=None) == [{"window": False, "src": "ha"}]
    assert lite.plan_commands(NOW + 90, _v(), memo, has_windows=True, window_since=None) == []


def test_no_status_no_commands():
    assert lite.plan_commands(NOW, None, {}, away=True, away_since=NOW - 9999) == []


def test_the_instance_wires_it_up():
    src = (BASE / "lite.py").read_text("utf-8")
    assert "plan_commands(" in src and "async_register_platform_entity_service" in src
    assert "PRESET_COMFORT" in src and "PRESET_SLEEP" in src and '"vacation"' in src
    assert "async_register_actions(hass)" in (BASE / "__init__.py").read_text("utf-8")
    svc = (BASE / "services.yaml").read_text("utf-8")
    assert "lite_comfort:" in svc and "lite_vacation:" in svc
    for lang in ("en", "hu"):
        tr = json.loads((BASE / "translations" / f"{lang}.json").read_text("utf-8"))
        assert {"lite_comfort", "lite_vacation"} <= set(tr["services"])
        assert set(tr["services"]["lite_vacation"]["fields"]) == {"until", "clear"}
        states = tr["entity"]["climate"]["lite_thermostat"]["state_attributes"]["preset_mode"]["state"]
        assert set(states) == {"home", "comfort", "sleep", "away", "vacation"}
        for sec in ("config", "options"):
            d = tr[sec]["step"]["lite_settings"]
            assert {"lite_cf_delta", "lite_cf_time", "lite_btn", "lite_presence", "lite_calendar", "lite_windows"} <= set(d["data"])
            assert {"lite_btn", "lite_presence", "lite_calendar", "lite_windows"} <= set(d["data_description"])


def test_the_script_listens_to_its_button_and_keeps_presets():
    assert "Shelly.addEventHandler(button)" in SCRIPT
    for k in ('"single_push"', '"double_push"', '"long_push"', 'save("hc_lite_mx"', "r.vacation", "r.window", "r.we_today",
              'sv: "0.82.0"'):
        assert k in SCRIPT, k

"""0.84.0: the plain summary wired in – the coordinator, the decision sensor's attributes, the info panel."""

import importlib
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

co = importlib.import_module("hc_thermostat.coordinator")
se = importlib.import_module("hc_thermostat.sensor")
inf = importlib.import_module("hc_thermostat.info")
model = importlib.import_module("hc_thermostat.core.model")


def _coord(mode="active", actual=False):
    d = model.Decision(now=datetime(2026, 11, 28, 23, 0), reason=model.Reason.AT_TARGET, target=21.0, indoor=21.2,
                       outdoor=2.0)
    sup = SimpleNamespace(summary_context=lambda now: {"active": "sleep", "presence": "home", "night": ("22:00", "05:30")})
    c = SimpleNamespace(data=d, supervisor=sup, hass=SimpleNamespace(config=SimpleNamespace(language="hu")),
                        room_wording=False, mode=mode, actual=actual,
                        cfg=model.HcConfig(presets_enabled=("comfort", "eco")))
    c.plain_summary = lambda language=None: co.HcCoordinator.plain_summary(c, language)
    return c


def test_coordinator_summary_and_sensor_attributes():
    c = _coord()
    s = c.plain_summary()
    assert s["headline"] == "Nem fűt" and s["lines"][1] == "A cél 21 °C, mert éjszaka van (22:00–05:30)."
    assert s["lines"][-1] == "Ha most melegebb kell: Komfort."
    attrs = se._summary_attrs(c)
    assert attrs["summary_state"] == "idle" and attrs["summary"].startswith("Nem fűt. A ház elérte a célt")
    assert {"summary", "summary_state"} <= se.HcDecision._unrecorded_attributes
    shadow = _coord(mode="shadow").plain_summary("en")
    assert shadow["shadow"] and shadow["headline"] == "Not heating"
    c.data = None
    assert c.plain_summary() is None and se._summary_attrs(c) == {}


def test_a_broken_context_never_breaks_it():
    c = _coord()
    c.supervisor = SimpleNamespace(summary_context=lambda now: 1 / 0)
    assert c.plain_summary()["headline"] == "Nem fűt"  # without the target line, but there


def test_info_gives_both_languages_and_the_trv_rooms():
    c = _coord()
    assert inf._plain(c, "en")["headline"] == "Not heating"
    room = {"reason": "follow", "temperature": 20.1, "target": 21.0, "heating": False, "enabled": True}
    r = inf._room_plain(room, True)
    assert r["summary_hu"]["lines"][0] == "Bent 20,1 °C, a cél 21 °C – a ház célját követi."
    assert inf._room_plain(room, False) == {} and inf._room_plain({"reason": "unheated"}, True) == {}
    js = (ROOT / "custom_components/hc_thermostat/www/hc-info-panel.js").read_text()
    assert "this._plain(rd)" in js and "Miért fűt / miért nem?" in js

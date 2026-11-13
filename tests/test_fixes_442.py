"""0.44.2: room suggestions after the live finds of 11-12.

- The HP fan-coil test instance got the real kitchen head (driven by Cirkó HC) and a plain thermostat as heads: two
  instances wrote one head. A head another HC instance drives is no longer suggested or accepted.
- Outdoor thermometers (Udvar, Kert, another instance's outdoor sensor) became rooms – no longer.
- A main thermometer without an area had no leading room; it now gets one.
"""

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT.parent))
rooms_ha = importlib.import_module("hc_thermostat.rooms_ha")
wizard = importlib.import_module("hc_thermostat.wizard")


def _entry(entry_id, title, **conf):
    return SimpleNamespace(entry_id=entry_id, title=title, data={}, options=conf)


CIRKO = _entry("e1", "Cirkó HC", outdoor_entity="sensor.udvar_kint",
               rooms=[{"key": "konyha", "name": "Konyha", "trvs": ["climate.konyha_trv"]}], room_trvs=["climate.konyha_trv"])
OLAJ = _entry("e2", "Olajradiátor", outdoor_entity="sensor.garden_temperature")


def _hass(entries, states=()):
    st = {s.entity_id: s for s in states}
    return SimpleNamespace(config_entries=SimpleNamespace(async_entries=lambda domain: list(entries)),
                           states=SimpleNamespace(get=st.get, async_all=lambda domain=None: [
                               s for s in st.values() if domain is None or s.entity_id.startswith(domain + ".")]))


def _state(entity_id, value, name=None, device_class="temperature"):
    return SimpleNamespace(entity_id=entity_id, state=str(value), domain=entity_id.split(".")[0],
                           attributes={"friendly_name": name or entity_id, "device_class": device_class})


def test_heads_of_other_instances():
    hass = _hass([CIRKO, OLAJ])
    assert rooms_ha.heads_of_other_instances(hass, "e2") == {"climate.konyha_trv": "Cirkó HC"}
    assert rooms_ha.heads_of_other_instances(hass, "e1") == {}
    assert rooms_ha.heads_of_other_instances(None) == {}


def test_wizard_drops_a_head_another_instance_drives(monkeypatch):
    reg = SimpleNamespace(async_get=lambda e: None)
    monkeypatch.setattr(importlib.import_module("homeassistant.helpers.entity_registry"), "async_get", lambda hass: reg)
    hass = _hass([CIRKO])
    rooms = [{"key": "szim", "name": "Szim", "sensors": ["sensor.szim"]},
             {"key": "konyha", "name": "Konyha", "sensors": ["sensor.konyha"], "trvs": ["climate.konyha_trv"]}]
    out = wizard.wizard_rooms(hass, "pid", rooms, "szim", "sensor.szim", "e9")
    assert out["room_trvs"] == [] and [r["trvs"] for r in out["rooms"]] == [[], []]
    # the instance that drives it keeps it
    out = wizard.wizard_rooms(hass, "pid", rooms, "szim", "sensor.szim", "e1")
    assert out["room_trvs"] == ["climate.konyha_trv"]


def test_outdoor_areas_by_name(monkeypatch):
    names = {"courtyard": "Udvar", "kert": "Kert", "terasz": "Terasz", "nappali": "Nappali"}
    monkeypatch.setattr(rooms_ha, "area_name", lambda hass, a: names.get(a))
    assert rooms_ha.is_outdoor_area(None, "courtyard") and rooms_ha.is_outdoor_area(None, "kert")
    assert not rooms_ha.is_outdoor_area(None, "terasz") and not rooms_ha.is_outdoor_area(None, "nappali")
    assert not rooms_ha.is_outdoor_area(None, None)


def test_room_sensor_suggestion_skips_outdoor_thermometers(monkeypatch):
    areas = {"sensor.nappali": "nappali", "sensor.udvar_th": "courtyard", "sensor.garden_temperature": "kert",
             "sensor.wc": "wc", "sensor.main": "haloszoba"}
    names = {"nappali": "Nappali", "courtyard": "Udvar", "kert": "Kert", "wc": "WC", "haloszoba": "Hálószoba"}
    monkeypatch.setattr(rooms_ha, "area_id_of", lambda hass, e: areas.get(e))
    monkeypatch.setattr(rooms_ha, "area_name", lambda hass, a: names.get(a))
    hass = _hass([OLAJ], [_state(e, 21.0) for e in areas])
    got = rooms_ha.suggest_room_sensors(hass, {"indoor_entity": "sensor.main", "outdoor_entity": "sensor.kulso"})
    assert got == ["sensor.nappali", "sensor.wc"]  # before 0.44.2: Udvar and Kert too


def test_wizard_suggestion(monkeypatch):
    cand = {"areas": [
        {"area": "konyha", "name": "Konyha", "sensors": [{"id": "sensor.konyha", "head": False}],
         "trvs": [{"id": "climate.konyha_trv", "head": True, "taken_by": "Cirkó HC"}], "presence": []},
        {"area": "nappali", "name": "Nappali", "sensors": [{"id": "sensor.nappali", "head": False}],
         "trvs": [{"id": "climate.futes", "head": False}], "presence": []},
        {"area": "haloszoba", "name": "Hálószoba", "sensors": [], "trvs": [{"id": "climate.halo_trv", "head": True}],
         "presence": []},
        {"area": "courtyard", "name": "Udvar", "sensors": [{"id": "sensor.udvar", "head": False}], "trvs": [],
         "presence": [], "outdoor": True}], "tracking": [], "temperature": [], "climates": []}
    monkeypatch.setattr(wizard, "rooms_candidates", lambda hass: cand)
    monkeypatch.setattr(wizard, "area_id_of", lambda hass, e: None)
    hass = _hass([], [_state("sensor.szim", 20.0, "HP szim szoba")])
    conn = SimpleNamespace(result=None)
    conn.send_result = lambda _id, r: setattr(conn, "result", r)
    wizard.ws_rooms.__wrapped__(hass, conn, {"id": 1, "indoor": "sensor.szim"}) if hasattr(wizard.ws_rooms, "__wrapped__") \
        else wizard.ws_rooms(hass, conn, {"id": 1, "type": "hc_thermostat/wizard/rooms", "indoor": "sensor.szim"})
    s = {r["key"]: r for r in conn.result["suggest"]}
    assert conn.result["suggest_leading"] == "main" and s["main"]["sensors"] == ["sensor.szim"]
    assert "courtyard" not in s  # outdoor
    assert s["konyha"]["trvs"] == []  # Cirkó drives that head
    assert s["nappali"]["trvs"] == []  # a plain thermostat is no head
    assert s["haloszoba"]["trvs"] == ["climate.halo_trv"]


def test_version():
    assert json.loads((ROOT / "manifest.json").read_text())["version"] in ("0.44.2", "0.44.3", "0.44.4", "0.44.5", "0.45.0", "0.46.0", "0.47.0", "0.48.0", "0.48.1")


# --- PWM: a demand that grows past the minimum run mid-cycle (11-12 morning, Cirkó) ------------------------------
def test_pwm_starts_a_cycle_when_the_demand_grows_mid_cycle():
    from datetime import datetime, timedelta, timezone
    model = importlib.import_module("hc_thermostat.core.model")
    pwm_mod = importlib.import_module("hc_thermostat.core.pwm")
    cfg = model.HcConfig(cycle_s=1800.0, min_on_s=300.0, min_off_s=300.0, pwm_midcycle_start=True)  # 0.47.0: opt-in
    p = pwm_mod.Pwm(cfg)
    t0 = datetime(2026, 11, 12, 7, 17, tzinfo=timezone.utc)
    p.last_change = t0 - timedelta(hours=1)
    # 11-12: the cycle began at 15 % (4.5 min < 5 min: no burn), the demand reached 21 % at 7:24, 26 % at 7:29...
    demands = [(0, 0.15), (7, 0.21), (12, 0.26), (24, 0.32), (30, 0.38)]
    on_at = None
    for minute in range(0, 31):
        d = max(v for m, v in demands if m <= minute)
        out, _ = p.step(t0 + timedelta(minutes=minute), d)
        if out and on_at is None:
            on_at = minute
    assert on_at == 7  # before 0.44.2: 30 (the next cycle)


def test_pwm_does_not_restart_a_cycle_that_already_burned():
    from datetime import datetime, timedelta, timezone
    model = importlib.import_module("hc_thermostat.core.model")
    pwm_mod = importlib.import_module("hc_thermostat.core.pwm")
    cfg = model.HcConfig(cycle_s=1800.0, min_on_s=300.0, min_off_s=300.0)
    p = pwm_mod.Pwm(cfg)
    t0 = datetime(2026, 11, 12, 7, 0, tzinfo=timezone.utc)
    starts, last = 0, False
    for minute in range(0, 60):
        out, _ = p.step(t0 + timedelta(minutes=minute), 0.3 if minute < 20 else 0.5)
        starts += out and not last
        last = out
    assert starts == 2  # one burn per cycle, a higher demand mid-cycle does not add one

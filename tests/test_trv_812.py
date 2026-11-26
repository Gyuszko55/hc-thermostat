"""0.81.2: TRV heads only, by behaviour (a review of 0.81.1): the thermostat off / summer / the leading room's window
reach the heads; the head goes onto the input only after its offset was learned; the switch cycle writes the room's own
target; a rounding-safe 0.1 °C step; no relay driven; a Repairs entry without any head."""

import asyncio
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))

from core.model import Decision, HcConfig, Reason  # noqa: E402
from core.room_model import RoomSpec  # noqa: E402
from core.trv import TrvCalibration, TrvTargets  # noqa: E402
import hc_thermostat.coordinator as co  # noqa: E402
from hc_thermostat.const import MODE_ACTIVE  # noqa: E402

T0 = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
OPTS = ["local_temperature", "remote_temperature", "remote_source_offline"]


class _St:
    def __init__(self, state, attrs=None):
        self.state, self.attributes = state, dict(attrs or {})


class _Flat:
    """Two rooms, one TRVZB-like head each, with the external input and the sensor select on the head."""

    def __init__(self, room_temp=20.0, head_local=26.0):
        self.calls = []
        self.room_temp, self.head_local = room_temp, head_local
        self.s = {}
        for r in ("living", "bed"):
            self.s[f"climate.{r}_trv"] = _St("heat", {"temperature": 20.0, "current_temperature": head_local,
                                                      "min_temp": 4.0, "max_temp": 35.0, "target_temp_step": 0.5})
            self.s[f"select.{r}_trv_temperature_sensor_select"] = _St("local_temperature", {"options": OPTS})
            self.s[f"number.{r}_trv_external_temperature_input"] = _St("0.0")
        flat = self

        class _Svc:
            async def async_call(self, domain, service, data, blocking=False):
                flat.calls.append((domain, service, dict(data)))
                e = data["entity_id"]
                if service == "set_temperature":
                    flat.s[e].attributes["temperature"] = float(data["temperature"])
                elif service == "select_option":
                    flat.s[e] = _St(data["option"], {"options": OPTS})
                elif service == "set_value":
                    flat.s[e] = _St(str(data["value"]))

        class _States:
            def get(self, e):
                return flat.s.get(e)
        self.services, self.states, self.data = _Svc(), _States(), {}

    def target(self, room):
        return self.s[f"climate.{room}_trv"].attributes["temperature"]

    def sel(self, room):
        return self.s[f"select.{room}_trv_temperature_sensor_select"].state


def _coord(flat, monkeypatch, windows_bed=False):
    monkeypatch.setattr(co, "climate_attrs_c", lambda hass, a: dict(a))
    monkeypatch.setattr(co, "to_system", lambda hass, v, step=None: v)
    monkeypatch.setattr(co, "write_log", lambda hass: types.SimpleNamespace(note=lambda *a: None))
    c = co.HcCoordinator.__new__(co.HcCoordinator)
    c.hass, c.mode = flat, MODE_ACTIVE
    c.cfg = HcConfig(control="trv", frost_temp=7.0)
    c.trv_cal, c.trv_targets = TrvCalibration(), TrvTargets()
    c.issues = []
    specs = [RoomSpec(key="living", name="Living", sensors=["sensor.living_t"], trvs=["climate.living_trv"]),
             RoomSpec(key="bed", name="Bed", sensors=["sensor.bed_t"], trvs=["climate.bed_trv"])]
    c._specs_test = specs
    c.room_specs = lambda: (c._specs_test, "living")
    c._fresh_value = lambda ids, now: flat.room_temp
    c._room_reading = lambda spec, now: flat.room_temp
    c._trv_temp = lambda head: flat.s[head].attributes["current_temperature"]
    c._trv_ext = lambda head, now: (head.replace("climate.", "number.") + "_external_temperature_input",
                                    head.replace("climate.", "select.") + "_temperature_sensor_select")
    c._room_target = lambda spec, house, now, commit=True: types.SimpleNamespace(
        target=7.0 if (windows_bed and spec.key == "bed") else house, reason="window" if windows_bed else "follow")
    c._sync_trv_heads_issue = lambda missing: c.issues.append(missing)
    return c


def _run(c, reason=Reason.REGULATING, target=21.0, minutes=0.0):
    async def go():
        now = T0 + timedelta(minutes=minutes)
        co.dt_util.now = lambda: now  # noqa: B023 – the clock of this cycle
        await c._apply_trvs(Decision(now, reason, target, False, 0.0))
    real = co.dt_util.now
    try:
        asyncio.run(go())
    finally:
        co.dt_util.now = real


def test_thermostat_off_and_summer_take_every_head_to_frost(monkeypatch):
    for reason in (Reason.DISABLED, Reason.SEASON_OFF):
        flat = _Flat()
        c = _coord(flat, monkeypatch)
        _run(c, reason)
        assert flat.target("living") == 7.0 and flat.target("bed") == 7.0, reason
        assert c.room_states["bed"]["reason"] == "off"


def test_the_leading_rooms_window_closes_its_own_heads_only(monkeypatch):
    flat = _Flat(head_local=21.0)
    c = _coord(flat, monkeypatch)
    _run(c, Reason.WINDOW)
    assert flat.target("living") == 7.0, "the leading room's window"
    assert flat.target("bed") == 22.0, "the other room watches its own window (21 + its offset 1 while it learns)"


def test_the_head_goes_onto_the_input_only_after_learning(monkeypatch):
    flat = _Flat(room_temp=20.0, head_local=26.0)
    c = _coord(flat, monkeypatch)
    _run(c)
    assert flat.sel("living") == "local_temperature", "first the offset is learned on its own sensor"
    assert flat.target("living") == 26.0, "meanwhile: target + the learned offset (21 + 5, capped)"
    assert ("number", "set_value", {"entity_id": "number.living_trv_external_temperature_input", "value": 20.0}) \
        in flat.calls, "the input is filled already"
    _run(c, minutes=29)
    assert flat.sel("living") == "local_temperature"
    _run(c, minutes=31)
    assert flat.sel("living") == "remote_temperature", "after 30 minutes onto the room thermometer"
    assert flat.target("living") == 21.0, "and in the same cycle the room's own target – not the offset one"
    assert c.trv_cal.offset["climate.living_trv"] == 5.0, "kept for when the input drops out"


def test_an_offset_kept_from_before_counts_as_learned(monkeypatch):
    flat = _Flat()
    c = _coord(flat, monkeypatch)
    c.trv_cal.offset["climate.living_trv"] = 3.0
    _run(c)
    assert flat.sel("living") == "remote_temperature" and flat.target("living") == 21.0
    assert flat.sel("bed") == "local_temperature", "the other head has learned nothing yet"


def test_offline_falls_back_on_the_learned_offset_at_once(monkeypatch):
    flat = _Flat(room_temp=20.0, head_local=24.0)
    c = _coord(flat, monkeypatch)
    _run(c)
    _run(c, minutes=31)
    assert flat.target("living") == 21.0
    flat.s["select.living_trv_temperature_sensor_select"] = _St("remote_source_offline", {"options": OPTS})
    _run(c, minutes=32)
    assert flat.target("living") == 25.0, "21 + the offset learned on its own sensor (4)"
    assert not [x for x in flat.calls if x[1] == "select_option" and x[2]["option"] != "remote_temperature"]


def test_a_tenth_of_a_degree_is_a_change():
    o = types.SimpleNamespace(hass=_Flat(), _EXT_ON=co.HcCoordinator._EXT_ON,
                              _EXT_OFFLINE=co.HcCoordinator._EXT_OFFLINE, EXT_EVERY_S=600.0)
    ext = ("number.living_trv_external_temperature_input", None)
    w = lambda t, m: asyncio.run(co.HcCoordinator._write_trv_ext(o, "h", ext, t, T0 + timedelta(minutes=m)))  # noqa: E731
    bad = 0
    for i in range(150):
        o.hass.calls.clear()
        o._ext_written = {}
        o.__dict__["_ext_written"] = {}
        a = round(15.0 + i / 10, 1)
        w(a, 0)
        w(round(a + 0.1, 1), 1)
        bad += len([x for x in o.hass.calls if x[1] == "set_value"]) != 2
    assert bad == 0


def test_no_relay_is_driven_and_a_switch_clears_it():
    src = (ROOT / "coordinator.py").read_text("utf-8")
    assert 'None if self.cfg.control == "trv" else data.get(CONF_ACTUATOR)' in src
    cf = (ROOT / "config_flow.py").read_text("utf-8")
    assert 'if new == "trv":' in cf and "data[k] = None" in cf


def test_repairs_entry_without_any_head(monkeypatch):
    flat = _Flat()
    c = _coord(flat, monkeypatch)
    c._specs_test = [RoomSpec(key="living", name="Living", sensors=["sensor.living_t"])]
    _run(c)
    assert c.issues[-1] is True
    c._specs_test = [RoomSpec(key="living", name="Living", sensors=["sensor.living_t"], trvs=["climate.living_trv"])]
    _run(c)
    assert c.issues[-1] is False

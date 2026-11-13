"""0.47.0: an outside tester's points – a heat source with its own control (HC only switches the zone valve), the useful
heat delay of a slow thermoelectric valve and a late pump, the wizard from "Add integration", the basic settings at
the first setup."""

import asyncio
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core.matrix import Status, cell, controls, default_timing  # noqa: E402
from core.model import HcConfig, Inputs, Presence, Reading  # noqa: E402
from core.pwm import Pwm  # noqa: E402
from core.supervisor import Supervisor  # noqa: E402

T0 = datetime(2026, 11, 12, 0, 0, tzinfo=timezone.utc)


# --- 2. a heat source with its own control -----------------------------------------------------------------------
def test_external_heat_source_switches_only_the_zone_valve():
    assert controls("external_heat", "radiator_single") == ["tpi", "pid", "external"]
    assert controls("external_heat", "floor_single") == ["tpi", "pid", "external"]
    c = cell("radiator_single", "external_heat")
    assert c.status == Status.RECOMMENDED and "zónaszelep" in c.text_hu and "zone valve" in c.text_en
    assert cell("room_unit", "external_heat").status == Status.NOT_RECOMMENDED
    assert default_timing("radiator_single", "external_heat") == {"cycle_s": 1800.0, "min_on_s": 600.0, "min_off_s": 300.0}
    assert default_timing("floor_single", "external_heat")["cycle_s"] == 3600.0
    for lang in ("hu", "en"):
        assert json.loads((ROOT / "translations" / f"{lang}.json").read_text())["selector"]["heat_source"]["options"]["external_heat"]
    src = (ROOT / "sensor.py").read_text() + (ROOT / "binary_sensor.py").read_text()
    assert src.count('!= "external_heat"') == 2  # no boiler health / boiler problem for a source HC does not drive


# --- 3. useful heat delay ----------------------------------------------------------------------------------------
def _pwm(delay=600.0, cycle=900.0, min_on=300.0):
    return Pwm(HcConfig(cycle_s=cycle, min_on_s=min_on, min_off_s=300.0, valve_delay_s=delay))


def test_the_run_is_lengthened_by_the_delay():
    assert _pwm(0)._on_time(0.4) == 360.0  # as before
    p = _pwm(600, cycle=1800)
    assert p._on_time(0.4) == 720.0 + 600.0  # 12 useful minutes after 10 minutes of opening and pumping
    assert p._on_time(0.1) == 0.0  # 3 useful minutes: below the minimum, no 13-minute run for nothing


def test_small_demands_add_up_into_a_useful_run():
    p = _pwm(600, cycle=900, min_on=300)
    outs = []
    for k in range(int(3 * 900 / 30)):
        out, _ = p.step(T0 + timedelta(seconds=30 * k), 0.2)  # 3 minutes a cycle: too little alone
        outs.append(out)
    assert outs[:30] == [False] * 30  # the first cycle carries its 3 minutes on
    assert any(outs[30:60])  # the second: 6 minutes + 10 delay → one run
    assert p.state()["carry_s"] == 0.0 or not outs[-1]
    p.step(T0 + timedelta(hours=2), 0.0)
    assert p.carry_s == 0.0  # no demand: nothing is carried


def test_carry_survives_a_restart():
    p = _pwm()
    p.carry_s = 240.0
    q = _pwm()
    q.restore(p.state())
    assert q.carry_s == 240.0


def _sim(delay, outdoor, dead=600, cycle=900):
    cfg = HcConfig(control="pid", pid_kp=0.5, pid_ki_per_hour=0.2, target_home=21.0, night_start="00:00",
                   night_end="00:00", cycle_s=cycle, min_on_s=300, min_off_s=300, season_enabled=False,
                   boost_enabled=False, learning_enabled=False, valve_delay_s=delay)
    sup = Supervisor(cfg)
    room, since, useless, errs = 20.6, None, 0, []
    for k in range(24 * 120):
        now = T0 + timedelta(seconds=30 * k)
        d = sup.step(Inputs(now=now, indoor=Reading(round(room, 1)), outdoor=Reading(outdoor), presence=Presence.HOME))
        if d.output and since is None:
            since = now
        if not d.output and since is not None:
            useless += (now - since).total_seconds() <= dead
            since = None
        flowing = d.output and since is not None and (now - since).total_seconds() > dead
        room += (1.6 * flowing - 0.025 * (room - outdoor)) * 30 / 3600
        if k > 240:
            errs.append(abs(room - 21.0))
    return useless, sum(errs) / len(errs)


def test_simulation_slow_valve_and_late_pump():
    """5 min valve + 5 min pump delay (the tester's PLC), 15-minute cycle: without the delay a quarter to half of the
    runs end before any heat arrives; with it none do and the room keeps closer to its target."""
    for outdoor in (5.0, 12.0):
        old_useless, old_err = _sim(0, outdoor)
        # 0.48.1: a 15-minute cycle cannot hold a 10-minute delay with 5 + 5 minutes (the options refuse it): 30
        new_useless, new_err = _sim(600, outdoor, cycle=1800)
        assert old_useless >= 20 and new_useless == 0
        assert new_err < old_err * 0.7


# --- 4. / 5. the wizard from "Add integration", the basics at the first setup ---------------------------------------
def _flow():
    cf = importlib.import_module("hc_thermostat.config_flow")
    flow = cf.HcConfigFlow()
    flow._async_current_entries = lambda include_ignore=True: []
    flow.async_show_menu = lambda **kw: ("menu", kw)
    flow.async_show_form = lambda **kw: ("form", kw)
    flow.async_create_entry = lambda **kw: ("create", kw)
    flow.async_abort = lambda **kw: ("abort", kw)
    return cf, flow


def test_add_integration_offers_the_wizard_first(monkeypatch):
    cf, flow = _flow()
    kind, kw = asyncio.run(flow.async_step_user())
    assert kind == "menu" and kw["menu_options"] == ["open_wizard", "manual"]
    assert kw["step_id"] == "start" and hasattr(flow, "async_step_start")  # Home Assistant calls the menu's own step
    wizard = importlib.import_module("hc_thermostat.wizard")
    called = []

    async def setup(hass):
        called.append(hass)
    monkeypatch.setattr(wizard, "async_setup_wizard", setup)
    flow.hass = object()
    kind, kw = asyncio.run(flow.async_step_open_wizard())
    assert kind == "abort" and kw["reason"] == "use_wizard" and kw["description_placeholders"]["url"] == "/hc-wizard"
    assert called  # the panel is served now – before, only after the first instance
    kind, kw = asyncio.run(flow.async_step_manual())
    assert kind == "form" and kw["step_id"] == "user"


def test_the_first_setup_asks_the_targets_and_the_timing():
    cf, flow = _flow()
    flow._data = {"name": "Zóna", "role": "standalone", "heat_source": "external_heat", "system": "radiator_single",
                  "control": "pid", "actuator_entity": "switch.zona", "cycle_s": 1800.0, "min_on_s": 600.0,
                  "min_off_s": 300.0, "mode": "shadow"}
    kind, kw = asyncio.run(flow.async_step_basics())
    keys = [str(k) for k in kw["data_schema"].schema]
    assert kind == "form" and kw["step_id"] == "basics"
    assert keys == ["target_home", "target_night", "target_away", "night_start", "night_end", "cycle_s", "min_on_s",
                    "min_off_s", "valve_delay_s"]
    assert next(k for k in kw["data_schema"].schema if str(k) == "cycle_s").default() == 1800.0
    kind, kw = asyncio.run(flow.async_step_basics({"target_home": 22.0, "target_night": 20.0, "target_away": 17.0,
                                                   "night_start": "22:00", "night_end": "06:00", "cycle_s": 900,
                                                   "min_on_s": 300, "min_off_s": 300, "valve_delay_s": 600}))
    assert kind == "form" and kw["errors"] == {"cycle_s": "cycle_too_short"}  # 0.48.1: 10 + 5 + 5 > 15 minutes
    kind, kw = asyncio.run(flow.async_step_basics({"target_home": 22.0, "target_night": 20.0, "target_away": 17.0,
                                                   "night_start": "22:00", "night_end": "06:00", "cycle_s": 1800,
                                                   "min_on_s": 300, "min_off_s": 300, "valve_delay_s": 600}))
    assert kind == "create" and kw["data"]["valve_delay_s"] == 600 and kw["data"]["target_home"] == 22.0
    assert kw["data"]["actuator_entity"] == "switch.zona" and kw["data"]["mode"] == "shadow"
    flow._data = {**flow._data, "control": "external", "heat_source": "heat_pump"}
    keys = [str(k) for k in asyncio.run(flow.async_step_basics())[1]["data_schema"].schema]
    assert "cycle_s" not in keys and "valve_delay_s" not in keys  # a managed thermostat has no relay timing


def test_texts():
    for lang in ("hu", "en"):
        tr = json.loads((ROOT / "translations" / f"{lang}.json").read_text())
        assert set(tr["config"]["step"]["start"]["menu_options"]) == {"open_wizard", "manual"}
        assert "{url}" in tr["config"]["abort"]["use_wizard"]
        assert tr["config"]["step"]["basics"]["data"]["valve_delay_s"]
        st = tr["options"]["step"]["settings"]  # 0.49.0: in the "regulation" section
        assert st["sections"]["regulation"]["data"]["valve_delay_s"]
    js = (ROOT / "www" / "hc-wizard-panel.js").read_text()
    assert 'external_heat: ["Külső vezérlésű hőtermelő"' in js and '"valve_delay_s"]' in js
    assert json.loads((ROOT / "manifest.json").read_text())["version"] in ("0.47.0", "0.48.0", "0.48.1", "0.48.2", "0.48.3", "0.49.0")


# --- review of 11-12 evening: the failsafe covers the whole step, the executor's parts are separate, saves at once ---
from datetime import timedelta as _td  # noqa: E402

coord_mod = importlib.import_module("hc_thermostat.coordinator")
executor_mod = importlib.import_module("hc_thermostat.executor")
model = importlib.import_module("hc_thermostat.core.model")


class _Hass:
    def __init__(self, fail=(), on=()):
        self.calls, self.data, self._fail = [], {}, set(fail)
        st = lambda e: SimpleNamespace(entity_id=e, state="on" if e in on else "off", attributes={}, last_reported=T0)
        self.states = SimpleNamespace(get=st)
        self.services = SimpleNamespace(async_call=self._call)

    async def _call(self, domain, service, data, blocking=False):
        if data.get("entity_id") in self._fail:
            raise RuntimeError("unavailable")
        self.calls.append((domain, service, data))


def test_a_failing_fan_does_not_keep_the_relay_from_switching():
    hass = _Hass(fail={"fan.fc"})
    ex = executor_mod.Executor(hass, "active", "switch.valve", None, fan="fan.fc")
    d = model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.6, output=True, details={"fan_pct": 60})
    asyncio.run(ex.apply(d))
    assert ("homeassistant", "turn_on", {"entity_id": "switch.valve"}) in hass.calls
    assert ex.failed == {"fan"}


def _coordinator(fail_inputs=0, fail_side=False, on=()):
    c = object.__new__(coord_mod.HcCoordinator)
    hass = _Hass(on=on)
    c.hass, c.mode, c.step_errors, c.sensor_problems = hass, "active", 0, {}
    c.config_entry = SimpleNamespace(title="Probe")
    c.managed, c.managed_platform = False, None
    c._executor = executor_mod.Executor(hass, "active", "switch.boiler", None)
    c.data = model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.6, output=True)
    c._last_save = T0
    c.saves = 0
    left = {"n": fail_inputs}

    def build_inputs(now):
        if left["n"]:
            left["n"] -= 1
            raise RuntimeError("a sensor's state is broken")
        return Inputs(now=now, indoor=Reading(20.0), outdoor=Reading(5.0), presence=Presence.HOME)
    c.build_inputs = build_inputs
    c.supervisor = SimpleNamespace(step=lambda i: model.Decision(i.now, model.Reason.REGULATING, 21.0, 20.0, 5.0,
                                                                 demand=0.6, output=True), boosting=False)
    c._managed_details = lambda d: d
    boom = lambda *a: (_ for _ in ()).throw(RuntimeError("side"))
    c._record = boom if fail_side else (lambda d: None)
    c._compare_cost = lambda d: None
    c._update_health = boom if fail_side else (lambda d, now: None)
    c._update_rooms = lambda d, now: None

    async def apply_trvs(d):
        return None
    c._apply_trvs = apply_trvs

    async def save():
        c.saves += 1
    c.async_save = save
    return c


def test_failing_inputs_count_for_the_failsafe_and_switch_off(monkeypatch):
    c = _coordinator(fail_inputs=5, on=("switch.boiler",))
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: T0)
    for _ in range(2):
        try:
            asyncio.run(c._async_update_data())
        except RuntimeError:
            pass
    d = asyncio.run(c._async_update_data())
    assert d.output is False and c.sensor_problems[coord_mod.FAILSAFE_KEY] == "internal_error"
    assert c.hass.calls[-1] == ("homeassistant", "turn_off", {"entity_id": "switch.boiler"})


def test_a_failing_side_step_does_not_stop_the_relay(monkeypatch):
    c = _coordinator(fail_side=True)
    c.data = model.Decision(T0, model.Reason.REGULATING, 21.0, 20.0, 5.0, demand=0.0, output=False)
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: T0)
    d = asyncio.run(c._async_update_data())
    assert d.output is True and ("homeassistant", "turn_on", {"entity_id": "switch.boiler"}) in c.hass.calls
    assert c.sensor_problems[f"{coord_mod.SIDE_KEY}:record"] == "internal_error"
    assert c.sensor_problems[f"{coord_mod.SIDE_KEY}:health"] == "internal_error"


def test_the_state_is_saved_when_the_output_or_a_boost_changes(monkeypatch):
    c = _coordinator()
    clock = {"now": T0}
    monkeypatch.setattr(coord_mod.dt_util, "now", lambda: clock["now"])
    asyncio.run(c._async_update_data())  # the first step: the mark is set
    first = c.saves
    clock["now"] = T0 + _td(seconds=30)
    asyncio.run(c._async_update_data())
    assert c.saves == first  # nothing changed, within 10 minutes
    c.supervisor.boosting = True
    clock["now"] = T0 + _td(seconds=60)
    asyncio.run(c._async_update_data())
    assert c.saves == first + 1  # a boost started: saved at once


def test_coasting_and_mid_cycle_start_are_off_unless_turned_on():
    """0.47.0: measured on one house only – a new instance starts without them; the options turn them on."""
    cfg = HcConfig()
    assert cfg.coast_window_s == 0.0 and cfg.pwm_midcycle_start is False
    p = Pwm(HcConfig(cycle_s=1800.0, min_on_s=300.0, min_off_s=300.0))
    p.last_change = T0 - timedelta(hours=1)
    p.step(T0, 0.15)  # 4.5 min: below the minimum
    out, _ = p.step(T0 + timedelta(minutes=10), 0.26)  # grew past it mid-cycle, after its own on-time
    assert out is False  # waits for the next cycle, as before 0.44.2
    for lang in ("hu", "en"):
        data = json.loads((ROOT / "translations" / f"{lang}.json").read_text())["options"]["step"]["settings"]["sections"]["regulation"]["data"]
        assert data["coast_window_s"] and data["pwm_midcycle_start"]

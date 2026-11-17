"""0.57.1: fixes from an outside review of 0.57.0, before the heat pump and circuits are written live –
the running signal read by its unit, a climate target written on its own step and limits, a device restart is not a
second writer, an ON request never switches a climate to cooling, and the buffer's own zones keep a lasting demand."""

import asyncio
import importlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
og = importlib.import_module("hc_thermostat.core.output_guard")
hpc = importlib.import_module("hc_thermostat.core.hp_coord")

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
T0 = datetime(2026, 11, 16, 6, 0, tzinfo=timezone.utc)
UP = 1e6


def sec(s: float) -> datetime:
    return T0 + timedelta(seconds=s)


def st(state, **attrs):
    return SimpleNamespace(state=state, attributes=attrs, last_changed=T0, last_updated=T0)


# --- 1. the running signal by its unit -------------------------------------------------------------------------------
def test_running_signal_by_unit():
    hc = importlib.import_module("hc_thermostat.hp_coord_coordinator")
    states = {
        "sensor.kw": st("2.4", unit_of_measurement="kW"), "sensor.kw0": st("0.05", unit_of_measurement="kW"),
        "sensor.a": st("6.2", unit_of_measurement="A"), "sensor.a0": st("0.1", unit_of_measurement="A"),
        "sensor.hz": st("48", unit_of_measurement="Hz"), "sensor.hz0": st("0", unit_of_measurement="Hz"),
        "sensor.w": st("850", unit_of_measurement="W"), "sensor.pct": st("35", unit_of_measurement="%"),
        "sensor.nounit": st("2.4"), "sensor.temp": st("45", unit_of_measurement="°C"),
    }
    hass = SimpleNamespace(states=SimpleNamespace(get=states.get))
    on = lambda e: hc.on_state(hass, e, T0)  # noqa: E731  (0.59.0: "now" = the readings' time)
    assert on("sensor.kw") is True and on("sensor.kw0") is False  # 2.4 kW: runs (it was "not running" as watts)
    assert on("sensor.a") is True and on("sensor.a0") is False
    assert on("sensor.hz") is True and on("sensor.hz0") is False
    assert on("sensor.w") is True and on("sensor.pct") is True
    assert on("sensor.nounit") is None and on("sensor.temp") is None  # not known: never "certainly stands"


def test_a_kw_signal_no_longer_makes_its_own_heat_look_like_wood():
    """The review's case: the heat pump heats, its kW reading says it runs, the tank warms – that is not wood."""
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_min_on_s=0))
    i = dict(outdoor=2.0, top=30.0, trend_c_h=4.0, circuits=(hpc.CircuitNeed("floor", True, 33.0, 2.0),))
    assert h.step(sec(0), hpc.HpInputs(**i, hp_running=True)).heat_demand  # hp_running now True from 2.4 kW
    d = h.step(sec(600), hpc.HpInputs(**{**i, "top": 32.0}, hp_running=True))
    assert d.wood == "none" and d.heat_demand and d.reason == "heating"
    # with an unknown reading it is at most "possible", which changes nothing
    d = h.step(sec(1200), hpc.HpInputs(**{**i, "top": 33.0}, hp_running=None))
    assert d.wood == "possible" and d.heat_demand


# --- 2. a climate target on its step and limits ----------------------------------------------------------------------
class _Services:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, service, data, blocking=False):
        self.calls.append((domain, service, data))


def _hass(state):
    return SimpleNamespace(states=SimpleNamespace(get=lambda e: state if e == "climate.hp" else None),
                           services=_Services(), config=SimpleNamespace(units=SimpleNamespace(temperature_unit="°C")))


def _writer(hass, onoff=False):
    ow = importlib.import_module("hc_thermostat.output_writer")
    return ow.OutputWriter(hass, "climate.hp", onoff=onoff, confirm_s=60)


def test_climate_target_is_rounded_and_clamped():
    state = st("heat", temperature=40.0, target_temp_step=1, min_temp=25, max_temp=50, hvac_modes=["off", "heat"])
    hass = _hass(state)
    w = _writer(hass)
    assert w._climate_value(state, 42.5) in (42.0, 43.0)  # whole degrees
    assert w._climate_value(state, 58.0) == 50.0 and w._climate_value(state, 18.0) == 25.0
    no_step = st("heat", temperature=40.0, hvac_modes=["heat"])
    assert w._climate_value(no_step, 42.3) == 42.5  # 0.5 °C when the entity gives no step


def test_a_whole_degree_climate_confirms_instead_of_not_accepted():
    """The review's case 2: a device on 1 °C steps reported 43 for a written 42.5 – four writes, then not accepted."""
    state = st("heat", temperature=40.0, target_temp_step=1, min_temp=25, max_temp=55, hvac_modes=["off", "heat"])
    hass = _hass(state)
    w = _writer(hass)

    async def run():
        status = await w.apply(sec(0), 42.5, True, UP)
        assert status == "write"
        value = hass.services.calls[-1][2]["temperature"]
        assert value == round(value)  # a whole degree went out
        state.attributes["temperature"] = value  # the device holds it
        state.last_updated = sec(20)
        return await w.apply(sec(30), 42.5, True, UP), len(hass.services.calls)

    status, calls = asyncio.run(run())
    assert status == "in_sync" and calls == 1


# --- 3. a device restart is not a second writer ----------------------------------------------------------------------
def test_restart_with_default_value_is_written_again():
    g = og.OutputGuard(confirm_s=60)
    g.wrote(sec(0), 45.0)
    assert g.decide(sec(30), 45.0, 45.0, sec(10), UP) == (False, "in_sync") and g.confirmed
    assert g.decide(sec(600), 45.0, None, None, UP) == (False, "unavailable")  # the PLC restarts
    # it comes back with its default 35 – before 0.57.1 this was a conflict for good
    assert g.decide(sec(660), 45.0, 35.0, sec(650), UP) == (True, "write")
    assert not g.conflict
    g.wrote(sec(660), 45.0)
    assert g.decide(sec(700), 45.0, 45.0, sec(690), UP) == (False, "in_sync")


def test_back_with_hcs_own_value_needs_nothing():
    g = og.OutputGuard(confirm_s=60)
    g.wrote(sec(0), 45.0)
    g.decide(sec(30), 45.0, 45.0, sec(10), UP)
    g.decide(sec(600), 45.0, None, None, UP)
    assert g.decide(sec(660), 45.0, 45.0, sec(650), UP) == (False, "in_sync")


def test_a_change_without_unavailable_is_still_a_conflict():
    g = og.OutputGuard(confirm_s=60)
    g.wrote(sec(0), 45.0)
    g.decide(sec(30), 45.0, 45.0, sec(10), UP)
    assert g.decide(sec(600), 45.0, 35.0, sec(590), UP) == (False, "conflict")


def test_a_conflict_ends_when_the_device_restarts():
    g = og.OutputGuard(confirm_s=60)
    g.wrote(sec(0), 45.0)
    g.decide(sec(30), 45.0, 45.0, sec(10), UP)
    assert g.decide(sec(600), 45.0, 38.0, sec(590), UP)[1] == "conflict"
    g.decide(sec(900), 45.0, None, None, UP)
    assert g.decide(sec(960), 45.0, 35.0, sec(950), UP) == (True, "write") and not g.conflict


# --- 4. ON never switches a climate to cooling -----------------------------------------------------------------------
def test_on_request_picks_a_heating_mode_only():
    ow = importlib.import_module("hc_thermostat.output_writer")
    pick = ow.OutputWriter._heat_mode
    assert pick(st("off", hvac_modes=["off", "cool", "heat"])) == "heat"
    assert pick(st("off", hvac_modes=["off", "cool", "heat_cool"])) == "heat_cool"
    assert pick(st("off", hvac_modes=["off", "cool", "auto"])) == "auto"
    assert pick(st("off", hvac_modes=["off", "cool", "dry", "fan_only"])) is None
    assert pick(st("off")) == "heat"


def test_on_request_to_a_cooling_only_climate_is_an_error_not_cooling():
    state = st("off", hvac_modes=["off", "cool", "dry"])
    hass = _hass(state)
    w = _writer(hass, onoff=True)
    status = asyncio.run(w.apply(sec(0), True, True, UP))
    assert status == "error" and "heating mode" in (w.error or "")
    assert hass.services.calls == []


# --- 5. the buffer's own zones keep a lasting demand -----------------------------------------------------------------
def test_summer_ends_on_tpi_pulses_without_a_circuit():
    """The review's case: 12 h of 60 % TPI on the buffer's zones (no circuit) and it stayed summer."""
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_auto_summer=True, hp_min_on_s=0, hp_min_off_s=0))
    base = dict(outdoor=10.0, top=40.0, circuits=())
    h.step(sec(0), hpc.HpInputs(**base))
    assert h.step(sec(24 * 3600), hpc.HpInputs(**base)).summer
    t0 = 25 * 3600
    summer = True
    for k in range(0, 12 * 60, 1):  # every minute for 12 h: 6 min asking, 4 min pause (60 %)
        asking = (k % 10) < 6
        summer = h.step(sec(t0 + k * 60), hpc.HpInputs(**base, zones_asking=asking)).summer
        if not summer:
            break
    assert not summer and k <= 31  # winter after the 30 minutes, at the next ask


def test_zone_hold_survives_a_restart():
    h = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_auto_summer=True))
    h.step(sec(0), hpc.HpInputs(outdoor=10.0, top=40.0, zones_asking=True))
    data = json.loads(json.dumps(h.state(sec(0))))
    g = hpc.HeatPumpCoordinator(hpc.HpConfig(hp_auto_summer=True))
    g.restore(data, sec(60))
    assert g.zones_last_ask == sec(0)


def test_version():
    assert json.loads((BASE / "manifest.json").read_text())["version"] in ("0.57.1", "0.58.0", "0.59.0", "0.60.0", "0.61.0", "0.62.0", "0.63.0", "0.64.0", "0.64.1", "0.65.0", "0.65.1", "0.65.2", "0.65.3", "0.66.0", "0.67.0", "0.68.0", "0.69.0", "0.70.0")


def test_house_view_power_above_the_outdoor_unit():
    """0.57.1: the power drawn now stands above a heat pump's and an AC's outdoor unit (not in the plant room's label)."""
    js = (BASE / "www" / "hc-house-view.js").read_text(encoding="utf-8")
    assert "const unitPower = (ux, uw, uy, w, on, key) =>" in js
    assert "unitPower(ux, uw, uy, toW(q.power), q.running, key)" in js  # heat pump
    assert "g.acPower = r.unit?.power" in js and "g.acPower = ex.unit?.power" in js  # AC: own room and a member's
    assert 'src.kind !== "heat_pump" && src.power' in js

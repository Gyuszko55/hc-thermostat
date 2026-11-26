"""0.81.0: "TRV heads only" – a flat on district heating with TRV heads and room thermometers, no zone valve, no
boiler (a tester's panel flat: the wizard asked for a relay, a flame and a gas meter it does not have)."""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent))
from core.matrix import Status, cell, controls  # noqa: E402
from core.model import HcConfig, Inputs, Presence, Reading  # noqa: E402
from core.supervisor import Supervisor  # noqa: E402

T0 = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)
JS = (ROOT / "www" / "hc-wizard-panel.js").read_text("utf-8")


def test_offered_for_district_heating_first_on_a_trv_system():
    assert controls("district_heating", "radiator_trv")[0] == "trv"
    assert "trv" in controls("district_heating", "radiator_single")
    assert "trv" in controls("district_heating"), "the wizard's list (no system yet)"
    assert "trv" not in controls("district_heating", "floor_single"), "no heads on a floor"
    for src in ("onoff_boiler", "external_heat", "heat_pump"):
        assert "trv" not in controls(src, "radiator_trv"), src
    c = cell("radiator_trv", "district_heating")
    assert c.status == Status.RECOMMENDED and "Csak szelepfejek" in c.text_hu and "TRV heads only" in c.text_en


def test_the_supervisor_switches_nothing():
    cfg = HcConfig(control="trv", target_home=21.0, night_start="00:00", night_end="00:00", season_enabled=False,
                   boost_enabled=False, learning_enabled=False)
    sup = Supervisor(cfg)
    for k in range(20):
        d = sup.step(Inputs(now=T0 + timedelta(seconds=30 * k), indoor=Reading(18.0), outdoor=Reading(0.0),
                            presence=Presence.HOME))
        assert d.output is False and d.demand == 0.0 and d.external is None
    assert d.target == 21.0, "the target still goes to the rooms' heads"


def test_no_relay_asked_anywhere():
    cf = (ROOT / "config_flow.py").read_text("utf-8")
    assert 'elif self._data[CONF_CONTROL] != "trv":' in cf and 'elif new != "trv":' in cf
    assert 'control in ("tpi", "pid", "trv")' in cf, "rooms allowed"
    wz = (ROOT / "wizard.py").read_text("utf-8")
    assert '"trv": CONF_INDOOR' in wz and "missing_heads" in wz
    assert wz.count('("tpi", "pid", "trv")') >= 4
    assert 'trv: "indoor_entity"' in JS and '["tpi", "pid", "trv"].includes(this._s.control)' in JS
    assert 'c !== "external" && c !== "trv") sc.push(ent("return_temp_entity"' in JS, "no district return"
    assert 's.system === "radiator_trv" && ctl.includes("trv")' in JS
    assert 'rooms_supported' in (ROOT / "climate.py").read_text() and '("tpi", "pid", "trv")' in (ROOT / "climate.py").read_text()
    assert '("external", "ac", "trv")' in (ROOT / "sensor.py").read_text(), "no demand sensors"


def test_texts():
    for lang in ("hu", "en"):
        t = json.loads((ROOT / "translations" / f"{lang}.json").read_text("utf-8"))
        assert t["selector"]["control"]["options"]["trv"]
    assert 'trv: ["Csak szelepfejek"' in JS and 'trv: ["TRV heads only"' in JS
    assert "trv_need:" in JS and JS.count("trv_need") >= 3


def test_external_sensor_input_of_the_heads():
    src = (ROOT / "coordinator.py").read_text("utf-8")
    assert '_EXT_NUM = ("external_temperature_input", "kulso_homerseklet")' in src
    assert '_EXT_SEL = ("temperature_sensor_select", "homero_valasztas")' in src
    assert '_EXT_ON = ("remote_temperature", "external")' in src and '"set_value"' in src
    assert "cal = 0.0" in src, "with the room temperature in the head, no offset"
    assert "if self.mode == MODE_ACTIVE and ref is not None:" in src, "written only live"
    assert "e.platform != DOMAIN" in src, "HC's own room climate in the area is not a head"


def test_rooms_step_starts_with_the_heads_and_no_boiler_sensors():
    assert 's.control === "trv" && !s.roomList.length' in JS, "the areas with free heads come ticked"
    assert 's.multi = s.roomList.length > 0 || s.control === "trv"' in JS
    assert "hint_trv:" in JS and 's.control === "trv" ? t.hint_trv : t.hint' in JS
    bs = (ROOT / "binary_sensor.py").read_text("utf-8")
    assert '[HcFault(c)] if c.cfg.control == "trv"' in bs and '("external", "ac", "trv")' in bs


def test_heat_type_of_district_heating_is_not_a_gas_boiler():
    from hc_thermostat.climate import heat_type
    assert heat_type({"heat_source": "district_heating", "system": "radiator_trv"}) == "radiator"
    assert heat_type({"heat_source": "district_heating", "system": "floor_single"}) == "floor"
    assert heat_type({"control": "trv", "system": "radiator_trv"}) == "radiator"
    assert heat_type({"heat_source": "onoff_boiler", "system": "radiator_single"}) == "gas_boiler"


# 0.81.1: the real TRVZB select (Zigbee2MQTT) has local_temperature / remote_temperature / remote_source_offline
TRVZB = ["local_temperature", "remote_temperature", "remote_source_offline"]


class _St:
    def __init__(self, state, options=None):
        self.state, self.attributes = state, {"options": options or []}


class _Hass:
    def __init__(self, states):
        self.calls, self._s = [], states
        hass = self

        class _Svc:
            async def async_call(self, domain, service, data, blocking=False):
                hass.calls.append((domain, service, dict(data)))
                if service == "select_option":
                    hass._s[data["entity_id"]] = _St(data["option"], hass._s[data["entity_id"]].attributes["options"])

        class _States:
            def get(self, eid):
                return hass._s.get(eid)
        self.services, self.states = _Svc(), _States()


def _coord(states):
    import types
    from hc_thermostat.coordinator import HcCoordinator as C
    o = types.SimpleNamespace(hass=_Hass(states), _EXT_ON=C._EXT_ON, _EXT_OFFLINE=C._EXT_OFFLINE, EXT_EVERY_S=C.EXT_EVERY_S)
    o.write = lambda *a: C._write_trv_ext(o, *a)
    o.active = lambda ext: C._ext_active(o, ext)
    return o


EXT = ("number.nappali_trv_external_temperature_input", "select.nappali_trv_temperature_sensor_select")


def test_trvzb_select_goes_to_remote_temperature():
    import asyncio
    o = _coord({EXT[1]: _St("local_temperature", TRVZB)})
    assert o.active(EXT) is False, "on local: the head measures itself – the offset calibration stays"
    asyncio.run(o.write("climate.nappali_trv", EXT, 20.94, T0))
    assert ("select", "select_option", {"entity_id": EXT[1], "option": "remote_temperature"}) in o.hass.calls
    assert ("number", "set_value", {"entity_id": EXT[0], "value": 20.9}) in o.hass.calls
    assert o.active(EXT) is True


def test_offline_is_left_alone_and_the_offset_stays():
    import asyncio
    o = _coord({EXT[1]: _St("remote_source_offline", TRVZB)})
    asyncio.run(o.write("climate.nappali_trv", EXT, 21.0, T0))
    assert [c for c in o.hass.calls if c[1] == "select_option"] == [], "the head returns by itself on the new value"
    assert o.active(EXT) is False


def test_older_heads_with_an_external_option_and_heads_without_a_select():
    import asyncio
    o = _coord({EXT[1]: _St("internal", ["internal", "external"])})
    asyncio.run(o.write("climate.x", EXT, 20.0, T0))
    assert ("select", "select_option", {"entity_id": EXT[1], "option": "external"}) in o.hass.calls
    assert _coord({}).active((EXT[0], None)) is True, "no select: the input alone decides"
    o = _coord({EXT[1]: _St("local_temperature", ["local_temperature"])})
    asyncio.run(o.write("climate.x", EXT, 20.0, T0))
    assert [c for c in o.hass.calls if c[1] == "select_option"] == [] and o.active(EXT) is False


def test_the_offset_is_not_learned_while_the_head_is_on_the_input():
    src = (ROOT / "coordinator.py").read_text("utf-8")
    assert "on_ext = ext is not None and self._ext_active(ext)" in src
    assert "self.trv_cal.offset.get(head, 0.0) if on_ext" in src, "kept for remote_source_offline"
    from core.trv import TrvCalibration
    c = TrvCalibration()
    assert c.update("h", 24.0, 20.0, T0) == 4.0, "learned on the head's own sensor before the switch"
    assert c.offset.get("h") == 4.0, "what an offline head falls back on"


def test_wizard_texts_for_trv_heads_only_mention_no_boiler():
    js = (ROOT / "www" / "hc-wizard-panel.js").read_text("utf-8")
    assert 'this._s.control === "trv" ? "" : `<label class="chk"><input type="checkbox" data-rm-demand' in js, "no burn request"
    assert 'this._s.control === "trv" ? t.lead_hint_trv : t.lead_hint' in js and "a lakás fő hőmérője" in js
    assert 's.control === "trv" ? t.start_active_trv : t.start_active' in js and "azonnal állítja a szelepfejeket" in js
    assert 's.control === "trv" ? t.start_active_on_trv : t.start_active_on' in js and "sets the TRV heads at once" in js


def test_a_thermometer_change_on_the_head_is_written_at_once():
    src = (ROOT / "coordinator.py").read_text("utf-8")
    assert 'seen[head] != on_ext' in src and "self.trv_targets.last_write.pop(head, None)" in src
    from core.trv import TrvTargets
    tt = TrvTargets()
    tt.written("h", 24.0, 21.0, T0)  # on its own sensor: 21 + 3 offset
    assert tt.plan("h", 21.0, "heat", 24.0, want=21.0, now=T0 + timedelta(minutes=1)).reason == "wait"
    tt.last_write.pop("h", None)  # what the coordinator does when the head goes onto the input
    p = tt.plan("h", 21.0, "heat", 24.0, want=21.0, now=T0 + timedelta(minutes=1))
    assert p.reason == "write" and p.target == 21.0

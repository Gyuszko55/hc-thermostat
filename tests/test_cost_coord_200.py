"""0.20.0: boiler and heat pump coordinated by cost – the AC helps the house, the boiler yields."""

import importlib
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"))
model = importlib.import_module("core.model")
sup_mod = importlib.import_module("core.supervisor")
messages = importlib.import_module("core.messages")

T0 = datetime(2026, 11, 9, 14, 0, tzinfo=timezone.utc)


def _house(indoor, yield_margin):
    cfg = model.HcConfig(target_home=22.5, target_night=22.5, learning_enabled=False, boost_enabled=False, season_enabled=False)
    sup = sup_mod.Supervisor(cfg)
    return sup.step(model.Inputs(now=T0, indoor=model.Reading(indoor, 0), outdoor=model.Reading(5.0, 0),
                                 yield_margin=yield_margin))


def test_house_yields_but_shows_its_own_target():
    plain, yielding = _house(22.3, 0.0), _house(22.3, 0.5)
    assert plain.reason == model.Reason.REGULATING and yielding.target == 22.5
    assert yielding.demand < plain.demand
    assert yielding.details.get("yield") == 0.5 and "kazán 0,5 °C-kal" in messages.explain(yielding, "hu")


def test_house_at_backup_level_still_heats():
    d = _house(21.5, 0.5)  # 1 °C below: the boiler steps in
    assert d.demand > 0.3


def _ac(assist):
    cfg = model.HcConfig(control="ac", target_home=19.0, target_night=19.0, season_enabled=True)
    sup = sup_mod.Supervisor(cfg)
    return sup.step(model.Inputs(now=T0, indoor=model.Reading(19.0, 0), outdoor=model.Reading(5.0, 0), outdoor_avg=5.0,
                                 unit_temp=18.0, unit_step=1.0, unit_min=16.0, unit_max=30.0, assist_target=assist))


def test_ac_helps_up_to_the_house_target():
    own, helping = _ac(None), _ac(22.5)
    assert helping.external.target > own.external.target
    assert helping.details["aim"] == 22.5 and helping.details["assist"]
    assert "Segít a ház fűtésében" in messages.explain(helping, "hu")
    assert not _ac(18.0).details["assist"]  # a lower house target never lowers the terrace


def test_yield_with_the_shadow_regulator_and_heat_need():
    """0.20.1: the shadow regulator crashed on the new code path (live outage 11-09 13:49–13:55)."""
    cfg = model.HcConfig(target_home=22.5, target_night=22.5, learning_enabled=False, boost_enabled=False,
                         season_enabled=False, shadow_regulator=True, boiler_power_kw=17.3)
    sup = sup_mod.Supervisor(cfg)
    for i in range(3):
        sup.heat_need.add_sample(f"2026-11-0{i+1}", 30.0, 400.0)
    for k in range(4):
        d = sup.step(model.Inputs(now=T0.replace(minute=k), indoor=model.Reading(22.2, 0), outdoor=model.Reading(5.0, 0),
                                  yield_margin=0.5))
    assert d.reason == model.Reason.REGULATING and d.shadow is not None and d.heat_need_kw is not None
    assert abs(d.heat_need_kw - 0.075 * (22.5 - 5.0)) < 0.01  # the heat need is for the shown target


def test_heat_type_for_cards():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
    climate = importlib.import_module("hc_thermostat.climate")
    assert climate.heat_type({"heat_source": "air_conditioner", "system": "room_unit"}) == "air_conditioner"
    assert climate.heat_type({"heat_source": "heat_pump", "system": "floor_single"}) == "heat_pump"
    assert climate.heat_type({"heat_source": "onoff_boiler", "system": "floor_zones"}) == "floor"
    assert climate.heat_type({"heat_source": "onoff_boiler", "system": "radiator_single"}) == "gas_boiler"


def test_room_wording():
    d = model.Decision(T0, model.Reason.AT_TARGET, 21.0, 22.1, 5.0)
    assert "a ház elérte" in messages.explain(d, "hu")
    assert "a helyiség elérte" in messages.explain(d, "hu", room=True)
    assert "the room reached" in messages.explain(d, "en", room=True)

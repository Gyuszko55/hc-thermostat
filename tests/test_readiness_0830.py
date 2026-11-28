"""0.83.0: the go-live checklist (core/readiness.py) – the three levels, the words, the text for the form."""

from core.readiness import (BLOCK, INFO, OK, WARN, EntityFact, Facts, as_text, evaluate, render, summary)


def _ids(items, level=None):
    return [i.id for i in items if level is None or i.level == level]


def _good(**kw) -> Facts:
    base = dict(role="standalone", control="tpi", decided=True, shadow_h=30.0, guard="ok",
                entities=[EntityFact("indoor_entity", "sensor.living", "core", age_s=120),
                          EntityFact("actuator_entity", "switch.boiler", "output")],
                targets={"target_home": 21, "target_night": 19, "target_away": 17, "target_vacation": 15,
                         "frost_temp": 7}, night=("22:00", "06:00"))
    base.update(kw)
    return Facts(**base)


def test_a_good_instance_is_ready():
    items = evaluate(_good())
    assert summary(items) == {"ready": True, "blocks": 0, "warns": 0}
    assert set(_ids(items)) == {"entities_ok", "shadow_ok", "guard_ok"}


def test_a_gone_or_unavailable_core_input_or_output_blocks():
    f = _good(entities=[EntityFact("indoor_entity", "sensor.x", "core", exists=False),
                        EntityFact("actuator_entity", "switch.b", "output", available=False)])
    items = evaluate(f)
    assert _ids(items, BLOCK) == ["entity_gone", "entity_unavailable"]
    assert not summary(items)["ready"]


def test_another_input_only_warns():
    f = _good(entities=[EntityFact("indoor_entity", "sensor.x", "core"),
                        EntityFact("room_sensors", "sensor.bed", "input", available=False),
                        EntityFact("window_entities", "binary_sensor.w", "input", exists=False)])
    items = evaluate(f)
    assert _ids(items, WARN) == ["entity_unavailable", "entity_gone"]
    assert summary(items)["ready"]


def test_a_stale_or_implausible_input_warns_an_output_is_not_judged_by_age():
    f = _good(entities=[EntityFact("indoor_entity", "sensor.x", "core", age_s=3 * 3600),
                        EntityFact("outdoor_entity", "sensor.o", "input", problem="jump"),
                        EntityFact("actuator_entity", "switch.b", "output", age_s=10 * 86400)])
    items = evaluate(f)
    assert _ids(items, WARN) == ["entity_stale", "entity_implausible"]
    assert render(items, "hu")["items"][0]["title"].startswith("Belső hőmérő régóta nem küldött adatot (3 h 0 min)")


def test_missing_settings_block():
    items = evaluate(_good(missing=["indoor_entity", "output"]))
    assert _ids(items, BLOCK) == ["missing", "missing"]
    titles = [i["title"] for i in render(items, "hu")["items"] if i["id"] == "missing"]
    assert titles == ["Hiányzik: belső hőmérő", "Hiányzik: kimenet"]


def test_one_writer_another_hc_blocks_an_automation_warns():
    f = _good(hc_conflicts=[("switch.boiler", "Living room HC")],
              automations=[("switch.boiler", [f"Automation {n}" for n in range(7)])])
    items = evaluate(f)
    assert _ids(items, BLOCK) == ["hc_conflict"]
    assert _ids(items, WARN) == ["automation_conflict"]
    words = render(items, "en")["items"]
    assert "Automation 4 …" in words[1]["title"] and "Automation 5" not in words[1]["title"]


def test_the_shadow_run():
    assert _ids(evaluate(_good(decided=False)), BLOCK) == ["no_decision"]
    short = evaluate(_good(shadow_h=5.04))
    assert _ids(short, WARN) == ["short_shadow"] and short[-2].params == {"hours": 5.0, "need": 24}
    assert "short_shadow" not in _ids(evaluate(_good(shadow_h=5.0, live=True)))  # already live: not asked
    assert _ids(evaluate(_good(step_errors=2, faults_24h=4)), WARN) == ["failing"]
    assert _ids(evaluate(_good(faults_24h=4)), WARN) == ["faults"]


def test_a_new_instance_from_the_wizard_is_judged_on_its_settings_only():
    items = evaluate(_good(static=True, decided=False, shadow_h=None))
    assert summary(items)["ready"] and "no_decision" not in _ids(items)


def test_protections():
    assert _ids(evaluate(_good(safety=True)), BLOCK) == ["safety_tripped"]
    assert "safety_ok" in _ids(evaluate(_good(safety=False)), OK)
    assert _ids(evaluate(_good(guard="HTTP 401 (device password)")), BLOCK) == ["guard_unreachable"]
    no_guard = evaluate(_good(guard=None, guard_fits=True))
    assert _ids(no_guard, INFO) == ["guard_suggested"] and summary(no_guard)["ready"]
    assert "guard_suggested" not in _ids(evaluate(_good(guard=None, guard_fits=False)))


def test_targets_that_contradict_each_other_warn():
    t = {"target_home": 20, "target_night": 21, "target_away": 6, "target_vacation": 7, "frost_temp": 7}
    items = evaluate(_good(targets=t, night=("22:00", "22:00")))
    assert _ids(items, WARN) == ["targets_below_frost", "targets_above_home"]
    assert _ids(items, INFO) == ["night_empty"]  # the same start and end is "no night" on purpose
    words = {i["id"]: i["title"] for i in render(items, "hu")["items"]}
    assert words["targets_below_frost"] == "Célhőmérséklet a fagyvédelem (7 °C) alatt vagy azon: szabadság, távol"
    assert words["targets_above_home"] == "Az otthoni cél (20 °C) fölött: éjszaka"


def test_render_orders_blockers_first_and_heads():
    items = evaluate(_good(shadow_h=2, safety=True))
    r = render(items, "hu")
    assert [i["level"] for i in r["items"]][:2] == [BLOCK, WARN]
    assert r["head"] == "Még nem élesíthető: 1 akadály"
    assert render(evaluate(_good(shadow_h=2)), "hu")["head"] == "Élesíthető, 1 figyelmeztetéssel"
    assert render(evaluate(_good()), "en")["head"] == "Ready to go live"


def test_as_text_leaves_out_what_is_fine():
    text = as_text(render(evaluate(_good(shadow_h=2, guard=None, guard_fits=True)), "hu"))
    lines = text.splitlines()
    assert lines[0] == "**Élesíthető, 1 figyelmeztetéssel**"
    assert len(lines) == 3 and lines[1].startswith("- ⚠️ Csak 2") and lines[2].startswith("- 💡 Nincs helyi védő")


def test_every_id_has_words_in_both_languages():
    from core.readiness import WORDS
    assert WORDS["hu"].keys() == WORDS["en"].keys()


def test_a_valve_head_only_warns_and_is_not_judged_by_age():
    f = _good(entities=[EntityFact("indoor_entity", "sensor.x", "core"),
                        EntityFact("trv_heads", "climate.bed", "trv", available=False),
                        EntityFact("trv_heads", "climate.bath", "trv", age_s=9e5)])
    items = evaluate(f)
    assert _ids(items, WARN) == ["entity_unavailable"] and summary(items)["ready"]
    assert render(items, "hu")["items"][0]["title"] == "Szelepfej nem elérhető: climate.bed"


def test_0850_settings_far_from_the_recommended_values_warn():
    from core.readiness import setting_risks
    rec = {"cycle_s": 900.0, "min_on_s": 300.0, "min_off_s": 300.0}
    fine = {"pwm": True, "rec": rec, "cycle_s": 900, "min_on_s": 300, "min_off_s": 240, "frost_temp": 7}
    assert setting_risks(fine) == [] and setting_risks(None) == []
    bad = {**fine, "min_off_s": 60, "min_on_s": 120, "cycle_s": 300, "frost_temp": 4}
    assert [i.id for i in setting_risks(bad)] == ["risk_min_off_s", "risk_min_on_s", "risk_cycle_s", "risk_frost_temp"]
    floor = {"pwm": True, "rec": {"cycle_s": 3600.0, "min_on_s": 900.0, "min_off_s": 900.0}, "cycle_s": 1500,
             "min_on_s": 900, "min_off_s": 900, "floor": True, "floor_limit": 31.0, "curve": True, "flow_max": 50}
    assert [i.id for i in setting_risks(floor)] == ["risk_floor_limit", "risk_flow_max"]  # 1500 s: above 1200 on a floor
    assert [i.id for i in setting_risks({**floor, "cycle_s": 1000})][0] == "risk_cycle_s"
    assert [i.id for i in setting_risks({**floor, "electric_floor": True, "floor_limit": 28.0, "flow_max": 40,
                                               "rec": {"cycle_s": 1800.0, "min_on_s": 300.0, "min_off_s": 300.0}})] == ["risk_floor_limit"]
    hp = {"heat_pump": True, "hp_min_on_s": 300, "hp_min_off_s": 600, "guard": True, "guard_every_s": 60, "guard_ttl_s": 90}
    assert [i.id for i in setting_risks(hp)] == ["risk_hp_min_on_s", "risk_guard_ttl"]
    items = evaluate(_good(settings=bad))
    assert summary(items)["ready"] and summary(items)["warns"] == 4  # warnings, never blockers
    words = {i["id"]: i["title"] for i in render(items, "hu")["items"]}
    assert words["risk_min_off_s"] == "A minimális szünet (60 s) kevesebb, mint az ajánlott (300 s) fele"
    assert words["risk_frost_temp"] == "A fagyvédelem csak 4 °C"

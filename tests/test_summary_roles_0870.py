"""0.87.0: "why heating / why not" for the central boiler, the buffer tank, the mixing circuit and the heat pump
coordination (core/summary_roles.py)."""

from datetime import datetime

from core.buffer import BufferDecision
from core.central import CentralDecision
from core.circuit import CircuitDecision
from core.hp_coord import REASONS, HpDecision
from core.summary_roles import HP_WHY, summarize_buffer, summarize_central, summarize_circuit, summarize_hp

NOW = datetime(2026, 11, 28, 14, 0)
B = {"buffer_on": 45.0, "buffer_off": 65.0}


def _b(reason, output=False, top=50.0, bottom=40.0, asking=()):
    return BufferDecision(NOW, output, reason, top, bottom, asking, dict(B))


def test_the_buffer():
    s = summarize_buffer(_b("charging", True, 44, 52, ("climate.bath",)), "hu", names={"climate.bath": "Fürdő"})
    assert s["headline"] == "Tölt" and s["lines"] == [
        "A teteje 44 °C; addig tölt, amíg az alja el nem éri a 65 °C-ot (most 52 °C).", "Hőt kér: Fürdő."]
    full = summarize_buffer(_b("full", top=70, bottom=66), "hu")
    assert full["headline"] == "Feltöltve" and full["lines"] == ["Az alja 66 °C – elérte a 65 °C-os határt.",
                                                                 "Újra tölt, ha a teteje 45 °C alá hűl."]
    assert summarize_buffer(_b("ready", top=52), "en")["lines"][0].startswith("The top is 52 °C – above the 45 °C")
    assert summarize_buffer(_b("waiting_demand", top=44), "hu")["headline"] == "Igényre vár"
    lost = summarize_buffer(_b("no_sensor", top=None), "hu")
    assert lost["state"] == "fault" and lost["lines"][-1] == "Nézd meg a puffer felső hőmérőjét."
    one = summarize_buffer(_b("charging", True, 44, None), "hu")
    assert "amíg a teteje el nem éri" in one["lines"][0]  # one thermometer: the top tells the end
    shadow = summarize_buffer(_b("min_off", top=40), "hu", live=False)
    assert shadow["shadow"] and shadow["note"].startswith("Árnyék mód") and shadow["headline"] == "Vár"
    for r in ("charging", "full", "ready", "waiting_demand", "min_off", "frost", "no_sensor", "max_charge", "failsafe", "safety_stop"):
        for lang in ("hu", "en"):
            out = summarize_buffer(_b(r), lang)
            assert out["lines"] and "{" not in " ".join(out["lines"]) and out["lines"][0] != r


def test_the_central_boiler():
    s = summarize_central(CentralDecision(NOW, True, "heating", ("Fürdő", "Nappali"), ("Fürdő",), flow_setpoint=48.0), "hu")
    assert s["headline"] == "Fűt" and s["lines"] == ["Hőt kér: Fürdő, Nappali.", "Előremenő cél: 48 °C."]
    w = summarize_central(CentralDecision(NOW, False, "waiting_valves", ("Fürdő",), details={"stuck": ["Fürdő"]}), "hu")
    assert w["headline"] == "Vár" and w["lines"][1].startswith("Nem nyit a szelep: Fürdő")
    assert summarize_central(CentralDecision(NOW, False, "no_demand"), "en")["lines"] == ["No zone asks for heat."]
    for r in ("no_demand", "waiting_valves", "heating", "min_on", "min_off", "valves_closed", "failsafe", "safety_stop"):
        assert summarize_central(CentralDecision(NOW, False, r, ("A",)), "hu")["lines"]


def test_the_mixing_circuit():
    capped = CircuitDecision(NOW, 34.0, 36.0, "limit", True, ("Fürdő", "Nappali"), outdoor=2.0, demand_target=36.0,
                             cap=34.0, cap_state="limited", shortfall=2.0)
    s = summarize_circuit(capped, "hu")
    assert s["headline"] == "Fűt" and s["lines"] == [
        "Kiadott előremenő: 34 °C. Kint 2 °C.", "A görbe 36 °C-ot kérne, de a puffer most csak 34 °C-ot ad.",
        "Tartós hőigény: Fürdő, Nappali."]
    idle = summarize_circuit(CircuitDecision(NOW, 28.0, 28.0, "deadband", False), "en")
    assert idle["headline"] == "No lasting demand" and idle["lines"][0].startswith("No zone asks for heat for long")
    held = summarize_circuit(CircuitDecision(NOW, 30.0, 33.0, "confirming", True, ("A",)), "hu")
    assert "A számolt cél 33 °C; a változást fokozatosan adja ki." in held["lines"]
    assert summarize_circuit(CircuitDecision(NOW, None, None, "no_input", False), "hu")["headline"] == "Ki"
    assert summarize_circuit(CircuitDecision(NOW, 30.0, 30.0, "failsafe", False), "hu")["state"] == "fault"


def test_the_heat_pump_coordination():
    on = HpDecision(NOW, True, True, "reserve_low", 42.0, 42.0, "changed", details={"top": 38.0, "charge": 22.4})
    s = summarize_hp(on, "hu")
    assert s["headline"] == "Tölt" and s["lines"] == ["Kevés a tartalék a pufferben, ezért tölt.",
                                                      "A puffer teteje 38 °C, töltöttsége 22 %.",
                                                      "Kiadott előremenő cél: 42 °C."]
    assert summarize_hp(HpDecision(NOW, False, False, "wood", None, None, "no_input"), "en")["lines"][0].startswith("Another source")
    assert summarize_hp(HpDecision(NOW, False, False, "summer", None, None, "", summer=True), "hu")["headline"] == "Nyári üzem"
    assert summarize_hp(HpDecision(NOW, True, False, "standby", None, None, ""), "hu")["headline"] == "Készenlét"
    assert set(HP_WHY["hu"]) | {"failsafe", "safety_stop"} >= set(REASONS) and HP_WHY["hu"].keys() == HP_WHY["en"].keys()

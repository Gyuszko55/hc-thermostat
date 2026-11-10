"""0.34.0: the info panel's data – everything serialised to plain JSON."""

import importlib
import json
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.model import Decision, HcConfig, Inputs, Reading, Reason
from core.supervisor import Supervisor

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
info = importlib.import_module("hc_thermostat.info")

T0 = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def test_jsonable_handles_every_kind_of_inner_value():
    value = {"d": Decision(T0, Reason.REGULATING, 21.0, 20.0, 5.0, details={"why": None}), "r": Reading(1.23456, 30),
             "t": timedelta(minutes=2), "q": deque([1, 2]), "s": {3}, "n": None, "x": object()}
    out = info.jsonable(value)
    json.dumps(out)  # plain JSON
    assert out["d"]["reason"] == "regulating" and out["d"]["now"] == T0.isoformat()
    assert out["r"] == {"value": 1.2346, "age_s": 30} and out["t"] == 120.0 and out["q"] == [1, 2] and out["s"] == [3]


def test_the_whole_supervisor_state_and_inputs_serialise():
    sup = Supervisor(HcConfig.from_mapping({"control": "pid"}))
    inputs = Inputs(now=T0, indoor=Reading(19.0), outdoor=Reading(2.0))
    d = sup.step(inputs)
    json.dumps({"state": info.jsonable(sup.state()), "inputs": info.jsonable(inputs), "decision": info.jsonable(d),
                "config": info.jsonable(sup.cfg)})

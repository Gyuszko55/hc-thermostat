"""0.79.1: the circuit's details carry the outdoor-only reference curve and what is added on top (shadow only)."""
from datetime import datetime, timezone

from custom_components.hc_thermostat.core.circuit import CircuitConfig, MixingCircuit as Circuit

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def test_shadow_ref_splits_the_target():
    c = Circuit(CircuitConfig())
    d = c.step(NOW, [], 4.2)
    ref = d.details["shadow_ref"]
    cfg = c.cfg
    assert ref["ref_room"] == cfg.circuit_room
    assert ref["ref_curve"] == round(cfg.circuit_room + cfg.circuit_slope * max(cfg.circuit_room - 4.2, 0) + cfg.circuit_shift, 2)
    assert abs(ref["ref_curve"] + ref["room_lift"] + ref["correction"] + ref["trim"] - ref["raw"]) < 0.02


def test_no_outdoor_no_shadow_ref():
    assert "shadow_ref" not in Circuit(CircuitConfig()).step(NOW, [], None).details

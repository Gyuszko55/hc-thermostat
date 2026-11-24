"""0.79.1: one heat pump correction – the source in use is told, the form opens on it, a saved form wins."""
from datetime import datetime, timezone

from custom_components.hc_thermostat.core.hp_coord import HeatPumpCoordinator as HpCoordinator, HpConfig, HpInputs

NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def _step(cfg_offset, entity_offset):
    hp = HpCoordinator(HpConfig(hp_offset=cfg_offset))
    return hp.step(NOW, HpInputs(outdoor=5.0, top=40.0, charge=None, trend_c_h=None, circuits=(), zones_asking=False,
                                 offset=entity_offset)).details


def test_the_entity_set_apart_from_the_form_is_named():
    d = _step(0.0, 4.0)
    assert d["offset"] == 4.0 and d["offset_form"] == 0.0 and d["offset_source"] == "entity"


def test_the_same_value_is_the_form():
    assert _step(2.0, 2.0)["offset_source"] == "form"
    assert _step(1.5, None)["offset_source"] == "form" and _step(1.5, None)["offset"] == 1.5

"""0.65.2: the heat pump coordination's rules page in fold-out sections (classic and demand-based charging apart), and
explanations for the fields of the plant forms and the zone settings."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"

from hc_thermostat import config_flow as cf  # noqa: E402


def test_hp_rules_page_in_sections():
    form = cf._hpc_form({})
    top = [str(k) for k in form]
    assert {"hp_charge_mode", "hp_flow_min", "hp_flow_max", "hp_reserve", "hp_offset"} <= set(top)
    assert set(cf.HPC_SECTIONS) <= set(top)
    inside = {k for keys in cf.HPC_SECTIONS.values() for k in keys}
    assert inside | {"hp_charge_mode", "hp_flow_min", "hp_flow_max", "hp_reserve", "hp_offset"} == {str(k) for k in cf._hpc_settings({})}
    assert set(cf.HPC_SECTIONS["charge_classic"]) == {"hp_hyst", "hp_charge_on", "hp_charge_off", "hp_charge_needs_demand"}
    assert set(cf.HPC_SECTIONS["charge_demand"]) == {"hp_start_margin", "hp_start_kwh", "hp_stop_layer", "hp_stop_margin", "hp_coil_dt"}


def test_section_errors_go_above_the_form():
    ui = {k: v for k, v in {"hp_flow_min": 30, "hp_flow_max": 25, "hp_cold_on_below": 5, "hp_cold_release_above": 3,
                            "hp_charge_on": 0, "hp_charge_off": 0}.items()}
    errs = cf._hpc_section_errors(ui)
    assert errs.get("hp_flow_max") == "circuit_order" and errs.get("base") == "cold_order"
    flat = cf._flat({"hp_flow_min": 25, "cold": {"hp_cold_on": True}}, cf.HPC_SECTIONS)
    assert flat == {"hp_flow_min": 25, "hp_cold_on": True}


def test_every_plant_field_explained():
    for lang in ("hu", "en"):
        st = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]["step"]
        for step in ("buffer", "circuit", "hp_coord", "hp_coord_settings", "circuit_settings"):
            missing = [k for k in st[step]["data"] if k not in st[step].get("data_description", {}) and k != "circuit_preview"]
            assert not missing, (lang, step, missing)
        for name, keys in cf.HPC_SECTIONS.items():
            sec = st["hp_coord_settings"]["sections"][name]
            assert sec["name"] and set(keys) <= set(sec["data"]) and set(keys) <= set(sec["data_description"])


def test_zone_settings_explained():
    for lang in ("hu", "en"):
        st = json.loads((BASE / "translations" / f"{lang}.json").read_text())["options"]["step"]["settings"]
        missing = [k for k in st["data"] if k not in st.get("data_description", {})]
        for name, sec in st["sections"].items():
            missing += [f"{name}/{k}" for k in sec.get("data", {}) if k not in sec.get("data_description", {})]
        assert not missing, (lang, missing)

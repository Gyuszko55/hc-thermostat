"""The boiler state, flow target and shadow regulator sensors do not depend on the floor area (a slip of the
indentation in 0.51.2 put them under `if house_area_m2 > 0`). Read from the source, so it runs without Home Assistant."""

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat" / "sensor.py"


def _conditions_above(name: str) -> list[str]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    setup = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "async_setup_entry")
    found: list[list[str]] = []

    def walk(nodes, conds):
        for node in nodes:
            if isinstance(node, ast.If):
                walk(node.body, conds + [ast.unparse(node.test)])
                walk(node.orelse, conds)
            elif any(isinstance(x, ast.Name) and x.id == name for x in ast.walk(node)):
                found.append(conds)

    walk(setup.body, [])
    assert len(found) == 1, f"{name} is added {len(found)} times"
    return found[0]


def test_regulator_sensors_do_not_need_the_floor_area():
    for name in ("HcBoilerHealth", "HcFlowSetpoint", "HcShadowRegulator"):
        conds = _conditions_above(name)
        assert not any("house_area_m2" in c for c in conds), (name, conds)
        assert any("control not in" in c for c in conds), (name, conds)


def test_energy_rating_needs_only_the_floor_area():
    assert _conditions_above("HcEnergyRating") == ["c.cfg.house_area_m2 > 0"]

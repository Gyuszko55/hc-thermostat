from core.matrix import MATRIX, SOURCES, SYSTEMS, Status, cell, default_timing, own_control_supported


def test_every_cell_is_filled_in_both_languages():
    from core.matrix import ROOM_SOURCES
    water = [s for s in SOURCES if s not in ROOM_SOURCES and s not in ("district_heating", "pellet_boiler", "external_heat")]
    # the room units, district heating (0.32.0) and the fan coil come from cell(), not the table
    assert len(MATRIX) == len(water) * (len(SYSTEMS) - 2)
    for system in SYSTEMS:
        for source in SOURCES:
            c = cell(system, source)
            assert c.text_hu and c.text_en and c.text_hu != c.text_en


def test_known_cells():
    assert cell("mixed_no_circuit", "onoff_boiler").status == Status.NOT_RECOMMENDED
    assert cell("mixed_mixing", "onoff_boiler").status == Status.RECOMMENDED
    assert cell("mixed_rtl", "heat_pump").status == Status.NOT_RECOMMENDED


def test_own_control_only_for_relays_in_this_release():
    assert own_control_supported("onoff_boiler")
    assert not own_control_supported("heat_pump")


def test_floor_has_longer_cycles():
    assert default_timing("floor_single")["cycle_s"] > default_timing("radiator_single")["cycle_s"]


def test_electric_sources():
    assert cell("radiator_single", "electric_boiler").status == Status.RECOMMENDED
    assert cell("mixed_no_circuit", "electric_boiler").status == Status.NOT_RECOMMENDED
    assert cell("room_unit", "electric_heater").status == Status.RECOMMENDED
    assert cell("radiator_single", "electric_heater").status == Status.NOT_RECOMMENDED  # no water loop
    assert cell("room_unit", "electric_boiler").status == Status.NOT_RECOMMENDED
    assert own_control_supported("electric_boiler") and own_control_supported("electric_heater")
    assert default_timing("room_unit") == {"cycle_s": 600.0, "min_on_s": 120.0, "min_off_s": 120.0}


def test_electric_heat_type():
    import importlib, sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
    climate = importlib.import_module("hc_thermostat.climate")
    assert climate.heat_type({"heat_source": "electric_heater", "system": "room_unit"}) == "electric"
    assert climate.heat_type({"heat_source": "electric_boiler", "system": "floor_single"}) == "electric"

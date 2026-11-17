"""0.71.2: heat and energy quantities in kWh with their MJ beside them (1 kWh = 3.6 MJ) for an easier comparison."""

from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "hc_thermostat"


def test_panel_and_overview_show_mj():
    panel = (BASE / "www" / "hc-info-panel.js").read_text()
    assert "_kwh(v, dig = 1)" in panel and "* 3.6" in panel
    for use in ("this._kwh(c.heat_today_kwh)", "this._kwh(s.stored_kwh)", "this._kwh(dc.reserve_kwh)",
                "this._kwh(buf.usable_kwh)", "this._kwh(e.heat_kwh)", "this._kwh(e.electric_kwh)"):
        assert use in panel
    ov = (BASE / "www" / "hc-overview.js").read_text()
    assert "export const kwhMj" in ov and "kwhMj(num(st.stored_kwh), lang)" in ov and "MJ` : null" in ov

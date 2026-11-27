"""0.82.4: the relay script's version (SV) names a release: its web set-up loads from the tag v<SV>."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_the_script_version_is_a_release_in_the_changelog():
    sv = re.search(r'let SV = "(\d+\.\d+\.\d+)";', (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")).group(1)
    assert f"## {sv} – " in (ROOT / "CHANGELOG.md").read_text("utf-8"), f"no release {sv}: the page would load nothing"
    assert '@v" + SV + "/guard/shelly/hc_lite_ui.js"' in (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")


def test_the_on_time_only_gets_shorter():
    assert "if (d * C.cycle < st.of) st.of = d * C.cycle;" in (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")

"""0.78.2: the plain schematic (a boiler with its rooms) – return pipe, measured flow / return, TRV heads."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

OV = Path(__file__).resolve().parents[1] / "custom_components/hc_thermostat/www/hc-overview.js"


def _render(all_: list) -> str:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = (f'const OV = await import({json.dumps(OV.as_uri())});'
              f'console.log(JSON.stringify(OV.renderSchematic({json.dumps(all_)}, {{ lang: "hu" }})));')
    res = subprocess.run([node, "--input-type=module", "-e", script], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    return json.loads(res.stdout)


BOILER = {"entry_id": "a", "title": "Boiler HC", "heat_source": "onoff_boiler", "role": "standalone", "actual": False,
          "decision": {"indoor": 22.5, "target": 22.5}, "measures": {"flow_temp": 41.25, "return_temp": 33.5},
          "room_list": [{"name": "Nappali", "leading": True, "trvs": []},
                        {"name": "Konyha", "temperature": 23.0, "target": 22.5, "trvs": ["climate.konyha_trv"],
                         "names": {"climate.konyha_trv": "Konyha TRV"}, "asking": True,
                         "heads": {"climate.konyha_trv": {"head_target": 22.5, "head_temp": 23.2}}}]}


def test_return_pipe_temperatures_and_trv():
    svg = _render([BOILER])
    assert 'class="sp sf' in svg and 'class="sp sr' in svg  # flow and return
    assert "→ 41,3 °C" in svg or "→ 41,2 °C" in svg
    assert "← 33,5 °C" in svg
    assert 'class="strv on"' in svg and "Konyha TRV 22,5 °C" in svg and ">TRV<" in svg


def test_no_measures_no_trv_nothing_extra():
    b = {**BOILER, "measures": {}, "room_list": [{"name": "Nappali", "leading": True}]}
    svg = _render([b])
    assert 'class="stf"' not in svg and 'class="str"' not in svg and "strv" not in svg

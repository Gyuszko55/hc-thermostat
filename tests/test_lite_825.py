"""0.82.5: a clean install by someone else – the relay numbers a fresh BLU H&T's sensors by object id (measured on a
Shelly 1 Gen4: 200 battery, 201 humidity, 202 temperature), so the uploader finds the temperature and humidity itself
(--sensor auto, the default) and the READMEs say how to start."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _up():
    sys.path.insert(0, str(ROOT / "guard"))
    spec = importlib.util.spec_from_file_location("upload_shelly_825", ROOT / "guard" / "upload_shelly.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


FRESH = {"components": [
    {"key": "bthomedevice:200", "config": {"addr": "aa:bb"}},
    {"key": "bthomesensor:200", "config": {"obj_id": 1}},
    {"key": "bthomesensor:201", "config": {"obj_id": 46}},
    {"key": "bthomesensor:202", "config": {"obj_id": 69}},
]}


def test_the_uploader_finds_the_temperature_and_humidity(monkeypatch):
    up = _up()
    monkeypatch.setattr(up, "rpc", lambda host, method, params=None: FRESH if method == "Shelly.GetComponents" else {})
    assert up.bthome_find("10.0.0.5") == (202, 201)
    monkeypatch.setattr(up, "rpc", lambda host, method, params=None: {"components": []})
    assert up.bthome_find("10.0.0.5") == (None, None)


def test_auto_is_the_default_and_a_wrong_id_is_said():
    src = (ROOT / "guard" / "upload_shelly.py").read_text("utf-8")
    assert 'ap.add_argument("--sensor", default="auto"' in src
    assert "is not a temperature on this relay" in src and "pair the BLU H&T first" in src
    assert "Keep it: the relay's page asks for it" in src


def test_the_script_checks_its_sensors():
    js = (ROOT / "guard" / "shelly" / "hc_lite.js").read_text("ascii")
    for k in ("function tempId()", "isObj(C.sensor_id, 69, 2)", "sensor_warn:", "hum_warn:", "isObj(C.hum_id, 46, 3)"):
        assert k in js, k
    assert "sensorWarnUsing" in (ROOT / "guard" / "shelly" / "hc_lite_ui.js").read_text("utf-8")


def test_the_readmes_say_how_to_start():
    for f, words in (("README.md", ("### HC Lite", "upload_shelly.py <relay-ip> --lite", "keep it")),
                     ("README.hu.md", ("### HC Lite", "upload_shelly.py <relé-IP> --lite", "őrizd meg"))):
        txt = (ROOT / f).read_text("utf-8")
        for w in words:
            assert w in txt, (f, w)
    g = (ROOT / "guard" / "README.md").read_text("utf-8")
    assert "comes next" not in g and "first version" not in g and "bthomesensor:200 --set-password" not in g

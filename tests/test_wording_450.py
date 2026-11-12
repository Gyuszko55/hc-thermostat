"""0.45.0 wording: a HC room is „helyiség” in Hungarian (never a bare „szoba”), „room” in English; „terület” /
„area” only for a Home Assistant area."""
import json
import pathlib
import re
import unicodedata

BASE = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "hc_thermostat"
HU_FILES = ["translations/hu.json", "core/messages.py", "core/matrix.py", "wizard.py", "config_flow.py", "info.py",
            "climate.py", "rooms_ha.py", "core/rooms.py", "www/hc-wizard-panel.js", "www/hc-info-panel.js",
            "www/hc-house-view.js"]
# Room names where „szoba” is part of a compound name (and the house view's accentless name heuristics).
ALLOWED = re.compile(r"^(halo|furdo|elo|gyerek|vendeg|nappali|dolgozo)szoba")
WORD = re.compile(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű-]*[Ss]zob[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű-]*")


def _plain(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")


def _load(name):
    return json.loads((BASE / "translations" / name).read_text(encoding="utf-8"))


def _leaves(d, path=()):
    if isinstance(d, dict):
        for k, v in d.items():
            yield from _leaves(v, path + (k,))
    else:
        yield path, d


def test_no_bare_szoba_in_hungarian_texts():
    bad = []
    for name in HU_FILES:
        text = (BASE / name).read_text(encoding="utf-8")
        bad += [(name, w) for w in WORD.findall(text) if not ALLOWED.match(_plain(w))]
    assert bad == []


def test_translation_keys_and_placeholders_match():
    hu, en = dict(_leaves(_load("hu.json"))), dict(_leaves(_load("en.json")))
    assert set(hu) == set(en)
    ph = re.compile(r"\{[a-z_0-9]+\}")
    assert [k for k in hu if sorted(ph.findall(str(hu[k]))) != sorted(ph.findall(str(en[k])))] == []


def test_area_means_home_assistant_area():
    hu, en = _load("hu.json"), _load("en.json")
    room_hu, room_en = hu["options"]["step"]["room"], en["options"]["step"]["room"]
    assert room_en["data"]["area"] == "Area" and room_hu["data"]["area"] == "Terület"
    assert "room's area" in room_en["data_description"]["presence"]
    assert "helyiség területe" in room_hu["data_description"]["presence"]
    assert hu["options"]["step"]["rooms"]["title"] == "Helyiségek" and en["options"]["step"]["rooms"]["title"] == "Rooms"
    wiz = (BASE / "www" / "hc-wizard-panel.js").read_text(encoding="utf-8")
    assert 'add: "Add a room (area)…"' in wiz and 'add: "Helyiség hozzáadása (terület)…"' in wiz

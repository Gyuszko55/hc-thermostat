"""0.85.0: the critical settings carry "when to change it", the recommended range and the risk, in both languages."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import field_help  # noqa: E402


def _descriptions(lang):
    doc = json.loads((ROOT / f"custom_components/hc_thermostat/translations/{lang}.json").read_text())
    for flow in ("config", "options"):
        for step in doc[flow]["step"].values():
            for part in [step, *(step.get("sections") or {}).values()]:
                for key in part.get("data") or {}:
                    yield key, (part.get("data_description") or {}).get(key, "")


def test_every_critical_field_has_the_three_parts_everywhere_it_appears():
    assert len(field_help.HELP) >= 25
    for lang, mark, rec in (("hu", "**Mikor változtass:**", "**Ajánlott:**"), ("en", "**When to change it:**", "**Recommended:**")):
        seen = set()
        for key, text in _descriptions(lang):
            if key in field_help.HELP:
                seen.add(key)
                assert text.count(mark) == 1 and rec in text and "⚠" in text, (lang, key)
        assert seen == set(field_help.HELP), set(field_help.HELP) - seen  # every listed field exists in a form


def test_the_own_sentence_stays_first_and_the_tool_is_idempotent():
    hu = dict(_descriptions("hu"))
    assert hu["min_off_s"].startswith("Kikapcsolás után legalább ennyi ideig ki marad")
    before = (ROOT / "custom_components/hc_thermostat/translations/hu.json").read_text()
    subprocess.run([sys.executable, str(ROOT / "tools/field_help.py")], check=True, capture_output=True)
    assert (ROOT / "custom_components/hc_thermostat/translations/hu.json").read_text() == before

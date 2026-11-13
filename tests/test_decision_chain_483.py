"""0.48.3: the decision chain on GitHub – DECISION_CHAIN.md / .hu.md are generated from the code and stay current."""

import importlib.util
import re
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _gen():
    spec = importlib.util.spec_from_file_location("decision_chain", REPO / "tools" / "decision_chain.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_files_are_current():
    """A change of the matrix, the measurements or the texts needs `python tools/decision_chain.py`."""
    assert _gen().main(["--check"]) == 0


def test_every_heat_source_and_emitter_is_in_both_languages():
    gen = _gen()
    for lang in ("en", "hu"):
        text = gen.render(lang)
        labels = json.loads((REPO / "custom_components" / "hc_thermostat" / "translations" / f"{lang}.json").read_text())["selector"]
        for key, label in labels["heat_source"]["options"].items():
            assert f"<summary><b>{label}</b></summary>" in text, key
        for key, label in labels["system"]["options"].items():
            assert label in text, key
        assert text.count("```mermaid") == 2 and "| ⛔ |" in text or "⛔" in text
        assert "szoba" not in text.lower() or lang == "en"


def test_no_personal_data_and_linked_from_the_readmes():
    for name in ("DECISION_CHAIN.md", "DECISION_CHAIN.hu.md"):
        text = (REPO / name).read_text().lower()
        for word in (r"cirk[oó]", r"hern[aá]d", r"\bgyula\b", r"\bkata\b", r"192\.168\."):
            assert not re.search(word, text), (name, word)
    assert "(DECISION_CHAIN.md)" in (REPO / "README.md").read_text()
    assert "(DECISION_CHAIN.hu.md)" in (REPO / "README.hu.md").read_text()

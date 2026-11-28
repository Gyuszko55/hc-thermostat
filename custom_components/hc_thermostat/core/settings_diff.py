"""0.88.0: what a save changes, in plain words – before the save, and when going back to an earlier setting.

`changes(before, after)` compares the effective settings (`{**data, **options}`) key by key; the operating mode
(live / shadow) is left out on purpose: going live has its own confirmation, and restoring never makes an instance
live. `as_markdown()` gives the "old → new" lines for the confirmation page; `label_map()` turns the integration's
translations into field labels.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

SKIP = frozenset({"mode"})
SECRET = ("token", "password", "secret")  # a guard token or password is never shown, only that it changed
MAX_LINES = 20
WORDS = {
    "hu": {"on": "be", "off": "ki", "none": "nincs", "default": "alapérték", "changed": "megváltozott",
           "more": "és még {n} beállítás", "empty": "Nincs változás."},
    "en": {"on": "on", "off": "off", "none": "none", "default": "default", "changed": "changed",
           "more": "and {n} more settings", "empty": "Nothing changes."},
}


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def defaults_of(*classes) -> dict[str, Any]:
    """The default of every setting the config dataclasses know – a key missing from the saved settings has it."""
    from dataclasses import MISSING, fields
    out: dict[str, Any] = {}
    for cls in classes:
        for f in fields(cls):
            if f.name in out:
                continue
            if f.default is not MISSING:
                out[f.name] = f.default
            elif f.default_factory is not MISSING:  # type: ignore[misc]
                out[f.name] = f.default_factory()  # type: ignore[misc]
    return out


def _value(m: Mapping[str, Any], key: str, defaults: Mapping[str, Any]) -> Any:
    v = m.get(key)
    return defaults.get(key) if v is None else v


def changes(before: Mapping[str, Any], after: Mapping[str, Any], skip: Iterable[str] = SKIP,
            defaults: Mapping[str, Any] | None = None) -> list[str]:
    """The keys whose effective value differs. A missing key counts as its default (a form saving a default it did
    not store before changes nothing); a key that only appears or goes as None/'' counts as no change either."""
    skip = set(skip)
    defaults = defaults or {}
    out = []
    for key in sorted(set(before) | set(after)):
        if key in skip or key.startswith("_"):
            continue
        a, b = _value(before, key, defaults), _value(after, key, defaults)
        if a in (None, "", [], ()) and b in (None, "", [], ()):
            continue
        if not _same(a, b):
            out.append(key)
    return out


def fmt(value: Any, language: str = "en", names: Mapping[str, str] | None = None) -> str:
    w = WORDS["hu" if language == "hu" else "en"]
    names = names or {}
    if value is None or value == "" or value == [] or value == ():
        return w["none"]
    if isinstance(value, bool):
        return w["on"] if value else w["off"]
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
        return text.replace(".", ",") if language == "hu" else text
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return names.get(value, value)
    if isinstance(value, (list, tuple)):
        if all(isinstance(v, (str, int, float, bool)) for v in value):
            return ", ".join(fmt(v, language, names) for v in value)
        return w["changed"]
    return w["changed"]  # a nested room list, a week schedule …: too long to show, the label tells what changed


def lines(before: Mapping[str, Any], after: Mapping[str, Any], language: str = "en",
          labels: Mapping[str, str] | None = None, names: Mapping[str, str] | None = None,
          defaults: Mapping[str, Any] | None = None) -> list[str]:
    labels = labels or {}
    defaults = defaults or {}
    w = WORDS["hu" if language == "hu" else "en"]
    out = []
    for key in changes(before, after, defaults=defaults):
        a, b = _value(before, key, defaults), _value(after, key, defaults)
        label = labels.get(key) or key
        if any(word in key for word in SECRET) or fmt(a, language, names) == w["changed"] or fmt(b, language, names) == w["changed"]:
            out.append(f"{label}: {w['changed']}")
        elif key.endswith("_s") and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (a, b)):
            unit = "perc" if language == "hu" else "min"  # 0.89.0: seconds read as minutes
            out.append(f"{label}: {fmt(float(a) / 60, language)} → {fmt(float(b) / 60, language)} {unit}")
        else:
            out.append(f"{label}: {fmt(a, language, names)} → {fmt(b, language, names)}")
    return out


def as_markdown(rows: list[str], language: str = "en", limit: int = MAX_LINES) -> str:
    w = WORDS["hu" if language == "hu" else "en"]
    if not rows:
        return w["empty"]
    shown = [f"- {r}" for r in rows[:limit]]
    if len(rows) > limit:
        shown.append(f"- … {w['more'].format(n=len(rows) - limit)}")
    return "\n".join(shown)


def label_map(translations: Mapping[str, str], domain: str) -> dict[str, str]:
    """Field labels from the flattened translations (`component.<domain>.options.step.<step>.data.<key>`); the
    first step that names a key wins, the config flow's labels fill the gaps."""
    out: dict[str, str] = {}
    for flow in ("options", "config"):
        prefix = f"component.{domain}.{flow}.step."
        for full, text in translations.items():
            if not full.startswith(prefix) or ".data." not in full:
                continue
            key = full.rsplit(".data.", 1)[1]
            if "." in key or not text:
                continue
            out.setdefault(key, str(text).split("\n")[0].strip())
    return out

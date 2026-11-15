"""0.52.0: which state of a source means what – the built-in words plus the values chosen in the settings.

Before 0.52.0 a household presence source (an input_select, a sensor) counted as home only on "home" / "on" /
"otthon" and as on vacation only on "vacation" / "szabadság"; every other value was silently "away". An
input_select with "Itthon" / "Nyaralás" was therefore always away. Now the settings offer the source's own values,
the chosen ones count besides the built-in words, and a value that means nothing known is logged once.
The same for a heat pump's defrost / hot-water mode sensor.
"""

from __future__ import annotations

from collections.abc import Iterable

from .model import Presence

HOME = frozenset({"home", "on", "otthon"})
VACATION = frozenset({"vacation", "szabadság", "szabadsag"})
# the usual "not at home" values: no warning for these (a person in a named zone is away too, but is never warned)
AWAY = frozenset({"not_home", "away", "off", "távol", "tavol", "false", "0"})
BUSY = frozenset({"on", "true", "1", "defrost", "defrosting", "dhw", "hot_water", "domestic_hot_water",
                  "leolvasztás", "hmv"})
NO_STATE = ("unknown", "unavailable", "")
# the sources whose values are words someone chose (an input_select, a mode sensor) – only these are warned about
WORD_DOMAINS = ("input_select", "sensor", "select", "input_text")


def chosen(values: Iterable | str | None) -> frozenset[str]:
    """The values chosen in the settings, compared without case and surrounding spaces (a list or "a, b")."""
    if values is None:
        return frozenset()
    if isinstance(values, str):
        values = values.split(",")
    return frozenset(str(v).strip().lower() for v in values if str(v).strip())


def presence(states: Iterable[tuple[str, str]], home: Iterable | str | None = None,
             vacation: Iterable | str | None = None) -> tuple[Presence, list[tuple[str, str]]]:
    """The household presence from (entity_id, state) pairs, and the word-source values nothing knows.

    Home when any source says home (or there is no readable source), vacation when any says vacation, else away.
    A value is unknown only when the source is a word source, nothing was chosen for it in the settings and it is
    neither a built-in home, vacation nor away word."""
    own_home, own_vacation = chosen(home), chosen(vacation)
    home_words, vacation_words = HOME | own_home, VACATION | own_vacation
    values: list[str] = []
    unknown: list[tuple[str, str]] = []
    for entity_id, state in states:
        value = str(state or "").strip().lower()
        if value in NO_STATE:
            continue
        values.append(value)
        word_source = str(entity_id).split(".", 1)[0] in WORD_DOMAINS
        if word_source and not (own_home or own_vacation) and value not in home_words | vacation_words | AWAY:
            unknown.append((entity_id, state))
    if not values or any(v in home_words for v in values):
        return Presence.HOME, unknown
    return (Presence.VACATION if any(v in vacation_words for v in values) else Presence.AWAY), unknown


def busy(state: str | None, extra: Iterable | str | None = None) -> bool:
    """A heat pump's defrost / hot-water signal is on: a built-in word or a value chosen in the settings."""
    return str(state or "").strip().lower() in BUSY | chosen(extra)


def indoor_floor(plaus_min: float, frost_temp: float) -> float:
    """The lowest believable room temperature: never above the frost target minus 2 °C, so a cold but real room
    is believed and the frost protection can start (0.52.0)."""
    return min(float(plaus_min), float(frost_temp) - 2.0)


def source_values(state_obj) -> list[str]:
    """The values a source can take, for the settings' picker: its options (input_select, an enum sensor) and the
    value it has now."""
    if state_obj is None:
        return []
    out: list[str] = []
    for value in [*(state_obj.attributes.get("options") or []), state_obj.state]:
        value = str(value)
        if value.strip().lower() not in NO_STATE and value not in out:
            out.append(value)
    return out

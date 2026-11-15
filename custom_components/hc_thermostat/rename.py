"""0.51.1 (as Better Thermostat 2.0): follow a renamed entity.

The settings hold entity ids (thermometers, windows, heads, relays, meters …). When one of them is renamed in the
entity registry, the old id is replaced in the entry's data and options – the update listener reloads the instance
with the new id instead of reporting a lost sensor.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


def replace_id(value: Any, old: str, new: str) -> Any:
    """`value` with every exact `old` (a string, in lists, tuples and dicts – values and keys) replaced by `new`."""
    if isinstance(value, str):
        return new if value == old else value
    if isinstance(value, list):
        return [replace_id(v, old, new) for v in value]
    if isinstance(value, tuple):
        return tuple(replace_id(v, old, new) for v in value)
    if isinstance(value, dict):
        return {replace_id(k, old, new): replace_id(v, old, new) for k, v in value.items()}
    return value


def renamed(data: dict, options: dict, old: str, new: str) -> tuple[dict, dict] | None:
    """The new data and options, or None when neither holds `old`."""
    new_data, new_options = replace_id(dict(data), old, new), replace_id(dict(options), old, new)
    if new_data == dict(data) and new_options == dict(options):
        return None
    return new_data, new_options


@callback
def async_track_renames(hass: HomeAssistant, entry) -> CALLBACK_TYPE:
    @callback
    def _updated(event: Event) -> None:
        data = event.data
        old, new = data.get("old_entity_id"), data.get("entity_id")
        if data.get("action") != "update" or not old or not new or old == new:
            return
        changed = renamed(entry.data, entry.options, old, new)
        if changed is None:
            return
        _LOGGER.info("%s: %s was renamed to %s – the settings follow it", entry.title, old, new)
        hass.config_entries.async_update_entry(entry, data=changed[0], options=changed[1])

    return hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, _updated)

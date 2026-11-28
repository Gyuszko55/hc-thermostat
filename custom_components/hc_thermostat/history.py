"""0.88.0: the settings saved before each change, so an earlier one can be restored from the options menu.

One store per instance (`hc_thermostat.<entry_id>.history`), the last `KEEP` saves, newest first. Each item keeps the
options as they were before the save, when, and which settings the save changed. Restoring goes through the same
save, so it can be undone as well; the operating mode (live / shadow) is never restored.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)
KEEP = 10


def _store(hass, entry_id: str) -> Store:
    return Store(hass, 1, f"{DOMAIN}.{entry_id}.history")


async def async_load(hass, entry_id: str) -> list[dict[str, Any]]:
    try:
        data = await _store(hass, entry_id).async_load()
    except Exception:  # a broken history never stops the settings
        _LOGGER.warning("The settings history could not be read", exc_info=True)
        return []
    items = (data or {}).get("items") if isinstance(data, dict) else None
    return [i for i in (items or []) if isinstance(i, dict) and isinstance(i.get("options"), dict)]


async def async_push(hass, entry_id: str, options: dict[str, Any], changed: list[str]) -> None:
    items = await async_load(hass, entry_id)
    items.insert(0, {"at": dt_util.utcnow().isoformat(), "options": dict(options), "changed": list(changed)})
    try:
        await _store(hass, entry_id).async_save({"items": items[:KEEP]})
    except Exception:
        _LOGGER.warning("The settings history could not be saved", exc_info=True)


async def async_remove(hass, entry_id: str) -> None:
    await _store(hass, entry_id).async_remove()


async def async_labels(hass, language: str) -> dict[str, str]:
    from homeassistant.helpers.translation import async_get_translations

    from .core.settings_diff import label_map
    out: dict[str, str] = {}
    for category in ("options", "config"):
        try:
            out.update({k: v for k, v in label_map(
                await async_get_translations(hass, language, category, {DOMAIN}), DOMAIN).items() if k not in out})
        except Exception:
            _LOGGER.debug("No labels for %s", category, exc_info=True)
    return out


def entity_names(hass, *mappings) -> dict[str, str]:
    """Entity ids in the settings → their friendly names, for the comparison."""
    out: dict[str, str] = {}
    for m in mappings:
        for v in m.values():
            for x in (v if isinstance(v, (list, tuple)) else [v]):
                if isinstance(x, str) and "." in x and x not in out:
                    st = getattr(hass, "states", None)
                    s = st.get(x) if st is not None else None
                    if s is not None and s.attributes.get("friendly_name"):
                        out[x] = str(s.attributes["friendly_name"])
    return out

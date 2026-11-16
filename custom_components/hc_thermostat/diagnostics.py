"""0.66.0: downloadable diagnostics for a bug report (Settings → Devices & services → HC Thermostat → ⋮ → Download
diagnostics): the instance's settings and everything the HC info panel shows for it – the decision, the inputs, the
learned values, the outputs. The house name and free-text names are redacted; entity ids stay (they are needed to
read the report). Look it through before sharing it."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"home_name", "custom_rooms", "latitude", "longitude", "password", "token", "api_key"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    from .info import _instance, jsonable
    manifest = {}
    try:
        from homeassistant.loader import async_get_integration
        integration = await async_get_integration(hass, DOMAIN)
        manifest = {"version": str(integration.version)}
    except Exception:
        pass
    data: dict[str, Any] = {"integration": manifest, "title": entry.title,
                            "data": async_redact_data(dict(entry.data), TO_REDACT),
                            "options": async_redact_data(dict(entry.options), TO_REDACT)}
    try:
        data["info"] = async_redact_data(jsonable(_instance(hass, entry)), TO_REDACT)
    except Exception as err:  # a half-loaded instance: the settings are still worth having
        data["info_error"] = repr(err)
    return data

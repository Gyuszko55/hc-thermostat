"""0.66.0: downloadable diagnostics for a bug report (Settings → Devices & services → HC Thermostat → ⋮ → Download
diagnostics): the instance's settings and everything the HC info panel shows for it – the decision, the inputs, the
learned values, the outputs. Redacted: the house name, the room names (each becomes "room:<its key>"), the guard's
address, token and password, coordinates. Entity ids and the instance's title stay (they are needed to read the
report), and so do the friendly names of the entities shown – look it through before sharing it."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"home_name", "custom_rooms", "latitude", "longitude", "password", "token", "api_key",
             "guard_token", "guard_push_url", "tok", "guard_password", "guard_url",
             "lite_token", "lite_password", "lite_url"}  # 0.79.2  # 0.76.0: the guard's token and push topic


def room_names(obj: Any, found: dict[str, str] | None = None) -> dict[str, str]:
    """Room name -> its key, from every mapping that has both."""
    found = {} if found is None else found
    if isinstance(obj, dict):
        if isinstance(obj.get("key"), str) and isinstance(obj.get("name"), str) and obj["name"]:
            found[obj["name"]] = obj["key"]
        for v in obj.values():
            room_names(v, found)
    elif isinstance(obj, list):
        for v in obj:
            room_names(v, found)
    return found


def _usable(names: dict[str, str]) -> dict[str, str]:
    """A name that is also a room key stays: replacing it would break the references by key (and it shows no more
    than the key does)."""
    keys = set(names.values())
    return {n: k for n, k in names.items() if n not in keys}


def redact_rooms(obj: Any, names: dict[str, str] | None = None) -> Any:
    """0.78.2 (security review): every room name – the room's own, and wherever it is used as a mapping key (the TRV
    info, older per-room settings) or a value (advice, asking rooms) – becomes "room:<key>". One consistent
    replacement, so the report still reads, and hcd's import (it builds from these diagnostics) still matches the
    rooms up."""
    names = _usable(room_names(obj) if names is None else names)
    sub = lambda v: f"room:{names[v]}" if isinstance(v, str) and v in names else v  # noqa: E731
    if isinstance(obj, dict):
        return {sub(k): redact_rooms(v, names) for k, v in obj.items()}  # a room's own name too: "room:<key>"
    if isinstance(obj, list):
        return [redact_rooms(v, names) for v in obj]
    return sub(obj)


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    from .info import _instance, jsonable
    manifest = {}
    try:
        from homeassistant.loader import async_get_integration
        integration = await async_get_integration(hass, DOMAIN)
        manifest = {"version": str(integration.version)}
    except Exception:
        pass
    names = room_names([dict(entry.data), dict(entry.options)])
    data: dict[str, Any] = {"integration": manifest, "title": entry.title,
                            "data": redact_rooms(async_redact_data(dict(entry.data), TO_REDACT), names),
                            "options": redact_rooms(async_redact_data(dict(entry.options), TO_REDACT), names)}
    if entry.data.get("role") == "lite":  # 0.79.2: the device's own status is the instance's state
        c = getattr(entry, "runtime_data", None)
        data["info"] = {"lite_status": async_redact_data(dict(getattr(c, "data", None) or {}), TO_REDACT),
                        "settings_error": getattr(c, "pushed_error", None)}
        return data
    try:
        info = jsonable(_instance(hass, entry))
        data["info"] = redact_rooms(async_redact_data(info, TO_REDACT), {**room_names(info), **names})
    except Exception as err:  # a half-loaded instance: the settings are still worth having
        data["info_error"] = repr(err)
    return data

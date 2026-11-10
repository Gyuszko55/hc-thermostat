"""Room thermometers in Home Assistant: which room each one is in, and a first suggestion of which to use."""

from __future__ import annotations

import statistics

from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from .const import CONF_INDOOR, CONF_OUTDOOR, CONF_REFERENCE, CONF_ZONE_TEMP

PLAUSIBLE = (10.0, 32.0)  # a living room is in this range; fridges, freezers and radiators are not
SKIP_WORDS = ("hűtő", "huto", "fagyaszt", "radiátor", "radiator", "fridge", "freezer", "kazán", "boiler",
              "medence", "pool", "talaj", "soil", "akkumul", "battery", "processz", "cpu")
BATHROOM_WORDS = ("fürdő", "furdo", "bath")


def area_id_of(hass, entity_id: str) -> str | None:
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None:
        return None
    if entry.area_id:
        return entry.area_id
    if entry.device_id and (device := dr.async_get(hass).async_get(entry.device_id)):
        return device.area_id
    return None


def area_name(hass, area_id: str | None) -> str | None:
    area = ar.async_get(hass).async_get_area(area_id) if area_id else None
    return area.name if area else None


def group_by_room(hass, entity_ids: list[str]) -> dict[str, list[str]]:
    """Room name -> its thermometers (several in one room are combined by their median)."""
    rooms: dict[str, list[str]] = {}
    for entity_id in entity_ids:
        name = area_name(hass, area_id_of(hass, entity_id)) or entity_id
        rooms.setdefault(name, []).append(entity_id)
    return rooms


def room_value(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def suggest_room_sensors(hass, conf: dict) -> list[str]:
    """Temperature sensors in the other rooms of the home.

    Left out: the main, outdoor, reference and zone thermometers and every sensor in their rooms (the main room
    is the reference itself, the outdoor and zone rooms are not part of the home), bathrooms, sensors whose name
    says they measure something else, and readings no living room has.
    """
    skip_ids = {conf.get(k) for k in (CONF_INDOOR, CONF_OUTDOOR, CONF_REFERENCE, CONF_ZONE_TEMP)} - {None}
    skip_areas = {area_id_of(hass, e) for e in skip_ids} - {None}
    out = []
    for state in hass.states.async_all("sensor"):
        if state.attributes.get("device_class") != "temperature" or state.entity_id in skip_ids:
            continue
        area = area_id_of(hass, state.entity_id)
        if area is None or area in skip_areas:
            continue
        name = f"{state.entity_id} {state.attributes.get('friendly_name', '')} {area_name(hass, area) or ''}".lower()
        if any(w in name for w in SKIP_WORDS + BATHROOM_WORDS):
            continue
        try:
            value = float(state.state)
        except ValueError:
            continue
        if PLAUSIBLE[0] <= value <= PLAUSIBLE[1]:
            out.append(state.entity_id)
    return sorted(out)

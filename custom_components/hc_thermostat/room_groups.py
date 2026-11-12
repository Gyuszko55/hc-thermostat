"""0.46.0: a room's groups – HC's own entities for a room with more than one thermometer, presence source or window.

- temperature: the mean of the room's fresh thermometers (a silent one is left out), as HC regulates by it;
- presence: on while any source says someone is in the room (a room tracker naming the room, a motion sensor on);
- window: on while any contact of the room is open.

They come and go with the room and follow it when a member is added or taken out (the options save reloads the
instance). The regulation itself reads the members directly; the groups show what it works with.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .core.room_model import slugify

KINDS = ("temperature", "presence", "window")
_WORDS = {
    "hu": {"temperature": ("hőmérséklet", "homerseklet"), "presence": ("jelenlét", "jelenlet"), "window": ("ablak", "ablak")},
    "en": {"temperature": ("temperature", "temperature"), "presence": ("presence", "presence"), "window": ("window", "window")},
}


def group_unique_id(entry_id: str, key: str, kind: str) -> str:
    return f"{entry_id}_roomgrp_{key}_{kind}"


def _members(spec, kind: str) -> list[str]:
    return list({"temperature": spec.sensors, "presence": spec.presence, "window": spec.windows}[kind])


def groups_of(coordinator, kinds: tuple[str, ...]) -> list[tuple]:
    """(spec, kind) for every room and kind with two or more members (rooms of a single zone TPI / PID only)."""
    from .climate import rooms_supported
    if not rooms_supported(coordinator.conf):
        return []
    try:
        specs, _ = coordinator.room_specs()
    except Exception:
        return []
    if not (isinstance(coordinator.conf.get("rooms"), list) and coordinator.conf.get("rooms")):
        return []  # only rooms saved in 0.43.0+ (the legacy shape stays exactly as it was)
    return [(s, k) for s in specs for k in kinds if len(_members(s, k)) >= 2]


def remove_old_groups(hass, entry, domain: str, keep: set[str]) -> None:
    """A group whose room went, or that is down to one member: its entity goes."""
    prefix = f"{entry.entry_id}_roomgrp_"
    try:
        reg = er.async_get(hass)
    except Exception:
        return
    for e in list(er.async_entries_for_config_entry(reg, entry.entry_id)):
        if e.domain == domain and (e.unique_id or "").startswith(prefix) and e.unique_id not in keep:
            reg.async_remove(e.entity_id)


class _RoomGroup(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, spec, kind: str, domain: str) -> None:
        super().__init__(coordinator)
        from .climate import room_title, room_unique_id
        entry = coordinator.config_entry
        hass = coordinator.hass
        lang = "hu" if str(getattr(getattr(hass, "config", None), "language", "") or "").startswith("hu") else "en"
        word, slug_word = _WORDS[lang][kind]
        title = room_title(hass, spec)
        _, leading = coordinator.room_specs()
        self._key, self._kind = spec.key, kind
        self._attr_unique_id = group_unique_id(entry.entry_id, spec.key, kind)
        # on the room's device: "Konyha HC Hőmérséklet (csoport)"; on the instance's (leading room): with its name
        group = "csoport" if lang == "hu" else "group"
        self._attr_name = (f"{title} {word} ({group})" if spec.key == leading else f"{word.capitalize()} ({group})")
        self.entity_id = f"{domain}.{slugify(title)}_{slug_word}_hc"
        # the leading room has no device of its own: its groups are on the instance's device
        if spec.key == leading:
            self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
                                                manufacturer="HC Thermostat", model="Heat Conductor")
        else:  # the room's device, as its climate makes it (whichever platform comes first)
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, room_unique_id(entry.entry_id, spec.key))}, name=f"{title} HC",
                manufacturer="HC Thermostat", model="HC room", via_device=(DOMAIN, entry.entry_id))
        self._attr_icon = {"temperature": "mdi:thermometer-lines", "presence": "mdi:account-group",
                           "window": "mdi:window-open-variant"}[kind]

    @property
    def _spec(self):
        return next((s for s in self.coordinator.room_specs()[0] if s.key == self._key), None)

    @property
    def extra_state_attributes(self) -> dict:
        spec = self._spec
        return {"entity_id": _members(spec, self._kind) if spec is not None else [], "hc_room": self._key}


class RoomTemperatureGroup(_RoomGroup, SensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, spec) -> None:
        super().__init__(coordinator, spec, "temperature", "sensor")

    @property
    def native_value(self):
        value = self.coordinator.room_group_value(self._key, "temperature")
        return round(value, 2) if value is not None else None


class RoomBinaryGroup(_RoomGroup, BinarySensorEntity):
    def __init__(self, coordinator, spec, kind: str) -> None:
        super().__init__(coordinator, spec, kind, "binary_sensor")
        self._attr_device_class = (BinarySensorDeviceClass.OCCUPANCY if kind == "presence"
                                   else BinarySensorDeviceClass.WINDOW)

    @property
    def is_on(self):
        return self.coordinator.room_group_value(self._key, self._kind)

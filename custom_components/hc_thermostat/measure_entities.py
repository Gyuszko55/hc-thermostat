"""0.48.0: the sensors of the measurements (core/measures.py) – only the values HC works out itself.

Starts and run time today (the season in the attributes), COP (today; the week and the season in the attributes),
ΔT (flow − return), and the mould risk of a room with a humidity sensor (on the room's device; the house's, when the
instance itself has a humidity sensor). A reading HC only passes on (pressure, modulation…) gets no entity of its own:
it has one already, and the HC info panel shows it.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (CONF_ACTUATOR, CONF_FLAME, CONF_FLOW_TEMP, CONF_HEAT_ENERGY, CONF_HEAT_OUTPUT, CONF_HUMIDITY,
                    CONF_REFERENCE, CONF_RETURN, DOMAIN)
from .core.room_model import slugify
from .entity import HcEntity

RISKS = ["low", "moderate", "high"]
_RISK_WORD = {"hu": "Penész-kockázat", "en": "Mould risk"}


def counted(c) -> bool:
    return c.cfg.control not in ("external", "ac") and any(c.conf.get(k) for k in (CONF_ACTUATOR, CONF_FLAME, CONF_REFERENCE))


def measure_sensors(hass, entry, c) -> list:
    out: list = []
    if counted(c):
        out += [HcStartsToday(c), HcRunHoursToday(c)]
    if c.conf.get(CONF_HEAT_OUTPUT) and c.conf.get(CONF_HEAT_ENERGY):
        out.append(HcCop(c))
    if c.conf.get(CONF_FLOW_TEMP) and c.conf.get(CONF_RETURN):
        out.append(HcDeltaT(c))
    risks: list = []
    try:
        specs, leading = c.room_specs()
    except Exception:
        specs, leading = [], None
    if isinstance(c.conf.get("rooms"), list) and c.conf.get("rooms"):
        risks = [RoomMouldRisk(c, s, s.key == leading) for s in specs if s.humidity]
    if c.conf.get(CONF_HUMIDITY) and not risks:
        out.append(HcMouldRisk(c))
    prefix = f"{entry.entry_id}_mould_"
    keep = {r.unique_id for r in risks}
    try:
        reg = er.async_get(hass)
        for e in list(er.async_entries_for_config_entry(reg, entry.entry_id)):
            if e.domain == "sensor" and (e.unique_id or "").startswith(prefix) and e.unique_id not in keep:
                reg.async_remove(e.entity_id)
    except Exception:
        pass
    return out + risks


def _m(c) -> dict:
    return getattr(c, "measures", None) or {}


class HcStartsToday(HcEntity, SensorEntity):
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:fire-circle"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "starts_today")

    @property
    def native_value(self):
        runs = _m(self.coordinator).get("runs")
        return runs["starts_today"] if runs else None

    @property
    def extra_state_attributes(self) -> dict:
        runs = _m(self.coordinator).get("runs") or {}
        return {k: runs[k] for k in ("starts_week", "starts_season", "starts_last_hour", "season_from") if k in runs}


class HcRunHoursToday(HcEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "run_hours_today")

    @property
    def native_value(self):
        runs = _m(self.coordinator).get("runs")
        return runs["hours_today"] if runs else None

    @property
    def extra_state_attributes(self) -> dict:
        runs = _m(self.coordinator).get("runs") or {}
        return {k: runs[k] for k in ("hours_week", "hours_season", "season_from") if k in runs}


class HcCop(HcEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:heat-pump-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "cop")

    @property
    def native_value(self):
        cop = _m(self.coordinator).get("cop")
        return cop.get("cop_today") if cop else None

    @property
    def extra_state_attributes(self) -> dict:
        return dict(_m(self.coordinator).get("cop") or {})


class HcDeltaT(HcEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "°C"
    _attr_suggested_display_precision = 1
    _attr_icon = "mdi:thermometer-chevron-down"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "delta_t")

    @property
    def native_value(self):
        return _m(self.coordinator).get("delta_t")

    @property
    def extra_state_attributes(self) -> dict:
        m = _m(self.coordinator)
        return {k: m[k] for k in ("flow_temp", "return_temp") if k in m}


class HcMouldRisk(HcEntity, SensorEntity):
    """The instance's own humidity sensor: the mould risk of its room."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = RISKS
    _attr_icon = "mdi:water-percent-alert"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "mould_risk")

    @property
    def native_value(self):
        return (self.coordinator.mould_risk("_house") or {}).get("risk")

    @property
    def extra_state_attributes(self) -> dict:
        h = self.coordinator.mould_risk("_house") or {}
        return {"humidity": h.get("value"), "dew_point": h.get("dew_point")}


class RoomMouldRisk(CoordinatorEntity, SensorEntity):
    """A room's mould risk, on the room's device (the leading room's on the instance's)."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = RISKS
    _attr_icon = "mdi:water-percent-alert"
    _attr_translation_key = "room_mould_risk"

    def __init__(self, coordinator, spec, leading: bool) -> None:
        super().__init__(coordinator)
        from .climate import room_title, room_unique_id
        entry, hass = coordinator.config_entry, coordinator.hass
        lang = "hu" if str(getattr(getattr(hass, "config", None), "language", "") or "").startswith("hu") else "en"
        title = room_title(hass, spec)
        self._key = spec.key
        self._attr_unique_id = f"{entry.entry_id}_mould_{spec.key}"
        word = _RISK_WORD[lang]
        self._attr_name = f"{title} {word.lower()}" if leading else word
        self.entity_id = f"sensor.{slugify(title)}_{slugify(word)}_hc"
        if leading:
            self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
                                                manufacturer="HC Thermostat", model="Heat Conductor")
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, room_unique_id(entry.entry_id, spec.key))}, name=f"{title} HC",
                manufacturer="HC Thermostat", model="HC room", via_device=(DOMAIN, entry.entry_id))

    @property
    def native_value(self):
        return (self.coordinator.mould_risk(self._key) or {}).get("risk")

    @property
    def extra_state_attributes(self) -> dict:
        h = self.coordinator.mould_risk(self._key) or {}
        return {"humidity": h.get("value"), "dew_point": h.get("dew_point"), "hc_room": self._key}

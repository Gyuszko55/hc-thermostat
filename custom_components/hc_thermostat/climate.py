"""The thermostat of the supervisor. In shadow mode it changes no device."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_ROLE, CONF_VALVE_FEEDBACK, DOMAIN, PRESETS
from .core.room_model import ROOM_PRESETS, slugify
from .core.curve import flow_request, zone_flow_limit
from .core.model import Reason
from .core.regulators import controller_attributes
from .entity import HcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    coordinator = entry.runtime_data
    rooms = []
    if rooms_supported(coordinator.conf) and coordinator.other_rooms():
        host_device = _host_device_id(hass, entry)
        rooms = [HcRoomClimate(coordinator, spec, host_device) for spec in coordinator.other_rooms()]
    _remove_old_rooms(hass, entry, {r.unique_id for r in rooms})
    async_add_entities([HcClimate(coordinator), *rooms])


def rooms_supported(conf: dict) -> bool:
    """Rooms with their own climate (0.43.0): a single zone (standalone) with TPI / PID, like the TRV rooms before."""
    return conf.get(CONF_ROLE, "standalone") == "standalone" and conf.get("control", "tpi") in ("tpi", "pid")


def _host_device_id(hass, entry) -> str | None:
    """The host instance's device (the rooms' devices hang under it)."""
    try:
        return dr.async_get(hass).async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
            manufacturer="HC Thermostat", model="Heat Conductor").id
    except Exception:
        return None


def _via(host_device: str | None, entry_id: str) -> dict:
    """The parent device: by its id where Home Assistant knows `via_device_id` (2026.8+), else by its identifier."""
    if host_device and "via_device_id" in getattr(DeviceInfo, "__annotations__", {}):
        return {"via_device_id": host_device}
    return {"via_device": (DOMAIN, entry_id)}


def room_title(hass, spec) -> str:
    """A room's display name: its name; a room without an area (named after an entity id) by that entity's name."""
    if spec.area or "." not in spec.name:
        return spec.name
    st = hass.states.get(spec.name) if hass is not None else None
    return str(st.attributes.get("friendly_name") or spec.name) if st is not None else spec.name


def room_unique_id(entry_id: str, key: str) -> str:
    return f"{entry_id}_room_{key}"


def _remove_old_rooms(hass, entry, keep: set[str]) -> None:
    """A room taken out in the options: its climate and its device go too."""
    prefix = f"{entry.entry_id}_room_"
    try:
        ent_reg, dev_reg = er.async_get(hass), dr.async_get(hass)
    except Exception:
        return
    for e in list(er.async_entries_for_config_entry(ent_reg, entry.entry_id)):
        if e.domain == "climate" and (e.unique_id or "").startswith(prefix) and e.unique_id not in keep:
            ent_reg.async_remove(e.entity_id)
    for d in list(dr.async_entries_for_config_entry(dev_reg, entry.entry_id)):
        ident = next((i for dom, i in d.identifiers if dom == DOMAIN), "")
        if ident.startswith(prefix) and ident not in keep:
            dev_reg.async_remove_device(d.id)


class HcClimate(HcEntity, ClimateEntity):
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "thermostat")

    @property
    def current_temperature(self) -> float | None:
        return self.coordinator.data.indoor

    @property
    def target_temperature(self) -> float:
        return self.coordinator.data.target

    @property
    def hvac_mode(self) -> HVACMode:
        return HVACMode.HEAT if self.coordinator.enabled else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if not self.coordinator.enabled:
            return HVACAction.OFF
        data = self.coordinator.data
        if data.reason == Reason.VALVE_EXERCISE:
            return HVACAction.IDLE  # the valve is only exercised: a central boiler must not start for it
        if data.external is not None and data.external.hvac == "cool":
            return HVACAction.COOLING
        if (data.details or {}).get("mode") == "cool":  # floor cooling (0.29.0)
            return HVACAction.COOLING if data.output else HVACAction.IDLE
        return HVACAction.HEATING if data.output else HVACAction.IDLE

    @property
    def preset_modes(self) -> list[str]:
        enabled = set(self.coordinator.cfg.presets_enabled)
        return [p for p in PRESETS if p == "auto" or p in enabled]

    @property
    def preset_mode(self) -> str:
        sup = self.coordinator.supervisor
        if sup.boosting:
            return "boost"
        return sup.preset or "auto"

    @property
    def extra_state_attributes(self) -> dict:
        data, sup = self.coordinator.data, self.coordinator.supervisor
        return {
            "hc_mode": self.coordinator.mode,
            "demand": round(data.demand * 100),  # read by a central boiler instance
            "fault": data.fault,
            "valve_feedback": self.coordinator.conf.get(CONF_VALVE_FEEDBACK),  # read by a central boiler
            "valve_exercising": data.reason == Reason.VALVE_EXERCISE,  # read by a central boiler (pump exercise)
            "valve_exercise_next": (n.isoformat() if (n := sup.exercise.next_run(dt_util.now())) else None),
            "control_type": self.coordinator.cfg.control,
            "trv_heads": self.coordinator.all_heads() or None,  # 0.42.0: cards open HC info by a head
            "room_climates": self._room_climates() or None,  # 0.43.0: the rooms of this boiler (their HC climates)
            "leading_room": (lead.name if (lead := self.coordinator.leading_spec()) is not None else None),
            "flow_request": self._flow_request(),  # read by a central modulating boiler
            "flow_limit": zone_flow_limit(self.coordinator.conf, self.coordinator.cfg),  # ... its cap for this zone
            "heat_type": heat_type(self.coordinator.conf),  # icon hint for cards: boiler, floor, heat pump, AC
            "source_advice": self.coordinator.cost.advice,  # read by an air conditioner instance that may help
            "zone_door_open": self.coordinator.zone.get("door_open"),
            "zone_coupled": self.coordinator.zone.get("coupled"),
            "manual_target": data.target if data.manual else None,
            "manual_until": data.manual_until.isoformat() if data.manual_until else None,
            "preset_until": sup.preset_until.isoformat() if sup.preset_until else None,
            "preset_until_home": sup.preset_until_home,
            "preset_end_preview": sup.preset_end_preview(self.preset_modes, dt_util.now()),
            **controller_attributes(self.coordinator.cfg, sup, data.demand, dt_util.now()),
            **self._floor_attributes(),
            **self._managed_attributes(),
        }

    def _room_climates(self) -> list[str]:
        if not rooms_supported(self.coordinator.conf) or self.hass is None:
            return []
        reg = er.async_get(self.hass)
        entry_id = self.coordinator.config_entry.entry_id
        return [e for s in self.coordinator.other_rooms()
                if (e := reg.async_get_entity_id("climate", DOMAIN, room_unique_id(entry_id, s.key)))]

    def _managed_attributes(self) -> dict:
        """0.42.0, external / AC control: the managed thermostat's integration, the pause and "switched off by
        hand"; supervision_switch is the pause switch's entity_id (the dial card switches it)."""
        info = self.coordinator.managed_info()
        if info is None:
            return {}
        return {"managed_platform": info["platform"], "managed_adapter": info["adapter"],
                "supervision_paused": info["paused"], "supervision_switch": self.coordinator.supervision_switch_id(),
                "managed_off": info["managed_off"]}

    def _floor_attributes(self) -> dict:
        """The floor limit in effect (0.37.0); floor tempering (0.35.0): whether it heats for the floor now, the floor
        target."""
        cfg, data = self.coordinator.cfg, self.coordinator.data
        out = {"floor_limit": cfg.floor_limit} if cfg.floor_system and cfg.floor_limit > 0 else {}  # 0.37.0: in effect
        if cfg.floor_temper:
            out.update(floor_tempering=data.reason == Reason.FLOOR_TEMPER,
                       floor_target=(data.details or {}).get("floor_target"))
        return out

    def _flow_request(self) -> float | None:
        """Zone of a central modulating boiler: the flow its own curve asks for while it wants heat."""
        data = self.coordinator.data
        if self.coordinator.conf.get(CONF_ROLE) != "zone" or not data.output:
            return None
        if data.flow_setpoint is not None:  # a zone on its own curve already knows it
            return data.flow_setpoint
        return flow_request(self.coordinator.cfg, data.target, data.indoor, data.outdoor)

    async def async_set_temperature(self, **kwargs) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self.coordinator.supervisor.manual_target = float(temperature)
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.HEAT and not self.coordinator.enabled:
            self.coordinator.supervisor.new_cycle()  # Switched on: start now, not at the old cycle phase.
        self.coordinator.enabled = hvac_mode == HVACMode.HEAT
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self.coordinator.supervisor.set_preset(preset_mode, dt_util.now())
        await self.coordinator.async_request_refresh()


def heat_type(conf: dict) -> str:
    """The kind of heat for cards (hc-dial-card heat_type): from the heat source and the system."""
    source, system = conf.get("heat_source"), conf.get("system") or ""
    if source == "air_conditioner":
        return "air_conditioner"
    if source == "heat_pump":
        return "heat_pump"
    if source in ("electric_boiler", "electric_heater", "storage_heater"):
        return "electric"
    if system.startswith("floor"):
        return "floor"
    return "gas_boiler"



def _area_name(hass, area_id: str | None) -> str | None:
    """The device goes into the room's existing area (never a new area from a room name)."""
    if not area_id:
        return None
    try:
        from .rooms_ha import area_name
        return area_name(hass, area_id)
    except Exception:
        return None


_NO_TARGET = {
    "hu": "{room}: itt nincs szelepfej, a helyiség csak a kazánon át fűthető – a célját a(z) {host} termosztáton "
          "állítsd (a ház célját követi).",
    "en": "{room}: no TRV head here, the room is heated only through the boiler – set the target on {host} (the room "
          "follows the house target).",
}


class HcRoomClimate(CoordinatorEntity, ClimateEntity):
    """0.43.0: one room of the boiler. A TRV room regulates by its heads (its own target, presence, a manual target
    until the next change); a room without a TRV shows the house target and cannot be set (only the boiler reaches it)."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "room"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0

    def __init__(self, coordinator, spec, host_device: str | None = None) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        title = room_title(coordinator.hass, spec)
        self._key, self._name, self._trv = spec.key, title, bool(spec.trvs)
        self._attr_unique_id = room_unique_id(entry.entry_id, spec.key)
        # climate.<room>_hc (HA would put the area in front of the device name otherwise); a taken id gets _2
        self.entity_id = f"climate.{slugify(title)}_hc"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._attr_unique_id)}, name=f"{title} HC", manufacturer="HC Thermostat",
            model="HC room", suggested_area=_area_name(coordinator.hass, spec.area),
            **_via(host_device, entry.entry_id))
        if self._trv:
            self._attr_hvac_modes = [HVACMode.HEAT, HVACMode.OFF]
            self._attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
                                             | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)
        else:
            self._attr_hvac_modes = [HVACMode.HEAT]
            self._attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE

    @property
    def _state(self) -> dict:
        return self.coordinator.room_states.get(self._key) or {}

    @property
    def _spec(self):
        return next((s for s in self.coordinator.other_rooms() if s.key == self._key), None)

    @property
    def current_temperature(self) -> float | None:
        return self._state.get("temperature")

    @property
    def target_temperature(self) -> float | None:
        st = self._state
        if st:
            return st.get("target")
        return self.coordinator.data.target if self.coordinator.data is not None else None

    @property
    def hvac_mode(self) -> HVACMode:
        if not self.coordinator.enabled:
            return HVACMode.OFF if self._trv else HVACMode.HEAT
        if self._trv and not self.coordinator._ctl(self._key).enabled:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        return HVACAction.HEATING if self._state.get("heating") else HVACAction.IDLE

    @property
    def preset_modes(self) -> list[str] | None:
        return list(ROOM_PRESETS) if self._trv else None

    @property
    def preset_mode(self) -> str | None:
        if not self._trv:
            return None
        return self.coordinator._ctl(self._key).preset or "auto"

    @property
    def extra_state_attributes(self) -> dict:
        c, st, spec = self.coordinator, self._state, self._spec
        host = c.hass.states.get(self._host_entity()) if self._host_entity() else None
        out = {
            "hc_mode": c.mode,
            "hc_room": self._key,
            "room_name": self._name,
            "host_entity": self._host_entity(),
            "host_name": c.config_entry.title,
            "trv": self._trv,
            "trv_heads": list(spec.trvs) if spec is not None and spec.trvs else None,
            "heat_type": "radiator" if self._trv else heat_type(c.conf),
            "follows_house": not self._trv,
            "reason": st.get("reason"),
            "house_target": st.get("house_target"),
            "target_mode": spec.mode if spec is not None else None,
            "offset": spec.offset if spec is not None else None,
            "sensors": list(spec.sensors) if spec is not None else [],
            "presence": st.get("presence"),
            "presence_sources": list(spec.presence) if spec is not None and spec.presence else None,
            "absent_since": st.get("absent_since"),
            "manual_target": st.get("manual"),
            "demand_allowed": st.get("demand_allowed"),
            "asking": st.get("asking"),
            "advice": (st.get("advice") or {}).get("advice"),
            "advice_deviation": (st.get("advice") or {}).get("deviation"),
            "calibration": {h: v.get("calibration") for h, v in (st.get("heads") or {}).items()} or None,
            "control_type": c.cfg.control,
            "demand": 0,
        }
        if host is None:
            out.pop("host_entity")
        return out

    def _host_entity(self) -> str | None:
        try:
            return er.async_get(self.hass).async_get_entity_id(
                "climate", DOMAIN, f"{self.coordinator.config_entry.entry_id}_thermostat")
        except Exception:
            return None

    def _reject(self) -> None:
        # 0.45.0: translated by Home Assistant into the user's language (the text here is the fallback)
        lang = "hu" if str(self.hass.config.language or "").startswith("hu") else "en"
        place = {"room": self._name, "host": self.coordinator.config_entry.title}
        raise ServiceValidationError(_NO_TARGET[lang].format(**place), translation_domain=DOMAIN,
                                     translation_key="room_no_target", translation_placeholders=place)

    async def async_set_temperature(self, **kwargs) -> None:
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return
        if not self._trv:
            self._reject()
        ctl = self.coordinator._ctl(self._key)
        ctl.manual, ctl.preset = float(temperature), None
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if not self._trv:
            self._reject()
        self.coordinator._ctl(self._key).set_preset(None if preset_mode == "auto" else preset_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if not self._trv:
            if hvac_mode != HVACMode.HEAT:
                self._reject()
            return
        self.coordinator._ctl(self._key).enabled = hvac_mode == HVACMode.HEAT
        await self.coordinator.async_save()
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

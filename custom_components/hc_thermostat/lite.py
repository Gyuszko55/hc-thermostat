"""0.79.2: HC Lite in Home Assistant – an instance that manages the Shelly script (guard/shelly/hc_lite.js).

The device heats on its own. This side reads its status every 30 s, keeps its settings in line with the instance's
(the instance is the source of the settings; mode and a manual target may also come from the device's own page) and
offers a climate entity (for the HC dial card or any thermostat card), a few sensors and the boiler's state.
A device password goes as the Shelly's digest auth (user "admin"); a bodiless GET first gets the challenge, the
writes then go signed (a Shelly drops a POST with a body and no Authorization – see guard_client.py, 0.78.3).
"""

from __future__ import annotations

from datetime import timedelta
import json
import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.components.climate import (
    PRESET_AWAY, PRESET_COMFORT, PRESET_HOME, PRESET_SLEEP, ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature, UnitOfTime
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed

from .const import (CONF_LITE_CALENDAR, CONF_LITE_PASSWORD, CONF_LITE_PRESENCE, CONF_LITE_TOKEN, CONF_LITE_URL,
                    CONF_LITE_WINDOWS, DOMAIN)
from .core.lite import LiteSettings, options_from_device, plan_commands, presence_away, settings_payload, sync_action, view

_LOGGER = logging.getLogger(__name__)
SCAN = timedelta(seconds=30)
TIMEOUT_S = 8.0
SHELLY_USER = "admin"
PRESET_VACATION = "vacation"  # 0.82.0: set with the lite_vacation service (it needs a date)


class LiteError(Exception):
    """The device did not answer, refused the password or the token."""


class LiteClient:
    def __init__(self, hass, url: str, token: str, password: str = "") -> None:
        self._hass = hass
        self.url = url.rstrip("/")
        self._token = token or ""
        self._password = password or ""
        self._auth = None

    def _extra(self) -> dict:
        if not self._password:
            return {}
        if self._auth is None:
            from aiohttp import DigestAuthMiddleware
            self._auth = DigestAuthMiddleware(SHELLY_USER, self._password)
        return {"middlewares": (self._auth,)}

    async def _request(self, method: str, body: dict | None = None) -> dict:
        import aiohttp
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        session = async_get_clientsession(self._hass)
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_S)
        try:
            if method == "POST" and self._password:
                await self._request("GET")  # the challenge first (a bodiless request gets the 401)
            kw: dict[str, Any] = {"timeout": timeout, **self._extra()}
            if body is not None:
                kw["data"] = json.dumps(body)
            async with session.request(method, self.url, **kw) as resp:
                text = await resp.text()
                if resp.status == 401:
                    raise LiteError("HTTP 401 (device password)")
                if resp.status == 403:
                    raise LiteError("HTTP 403 (token)")
                if resp.status != 200:
                    raise LiteError(f"HTTP {resp.status}")
                return json.loads(text or "{}")
        except LiteError:
            raise
        except Exception as exc:  # noqa: BLE001 – no answer, a broken connection, not JSON
            raise LiteError(type(exc).__name__) from exc

    async def status(self) -> dict:
        return await self._request("GET")

    async def send(self, **body) -> dict:
        return await self._request("POST", {"tok": self._token, **body})


class LiteCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, entry) -> None:
        super().__init__(hass, _LOGGER, name=f"{entry.title} (HC Lite)", update_interval=SCAN, config_entry=entry)
        self.conf = {**entry.data, **entry.options}
        self.client = LiteClient(hass, str(self.conf.get(CONF_LITE_URL) or ""), str(self.conf.get(CONF_LITE_TOKEN) or ""),
                                 str(self.conf.get(CONF_LITE_PASSWORD) or ""))
        self.settings = LiteSettings.from_conf(self.conf)
        self.pushed_error: str | None = None
        self.known_rev: int | None = None  # 0.79.9: the device's settings revision at the last sync
        self.memo: dict = {}  # 0.82.0: which presence / calendar / window episode got its command
        self.auto_error: str | None = None
        from homeassistant.helpers.storage import Store
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        rev = data.get("lite_rev")
        self.known_rev = rev if isinstance(rev, int) else None
        memo = data.get("memo")  # 0.82.2: a window open over a restart still gets its "closed"
        self.memo = dict(memo) if isinstance(memo, dict) else {}

    async def async_save(self) -> None:
        await self._store.async_save({"lite_rev": self.known_rev, "memo": self.memo})

    async def _remember(self, rev: Any) -> None:
        if isinstance(rev, int) and not isinstance(rev, bool) and rev != self.known_rev:
            self.known_rev = rev
            await self.async_save()

    async def _async_update_data(self) -> dict:
        try:
            st = await self.client.status()
        except LiteError as exc:
            raise UpdateFailed(str(exc)) from exc
        payload = settings_payload(self.settings)
        action = sync_action(st.get("cfg"), payload, st.get("rev"), self.known_rev)
        if action == "adopt":  # 0.79.9: changed on the relay's web page – HC takes it over, never writes it back
            await self._remember(st.get("rev"))
            entry = self.config_entry
            self.hass.config_entries.async_update_entry(entry, options={**entry.options, **options_from_device(st["cfg"])})
            _LOGGER.info("%s: settings taken over from the device (changed there)", entry.title)
            return st  # the update listener reloads the instance with them
        if action == "push":
            try:
                st = await self.client.send(set=payload)
                self.pushed_error = None
                _LOGGER.info("%s: settings sent to the device", self.config_entry.title)
            except LiteError as exc:
                self.pushed_error = str(exc)  # shown; the device keeps heating by what it has
        await self._remember(st.get("rev"))
        return await self._automate(st)

    def _inputs(self) -> dict:
        """0.82.0: presence, the calendar's active event and the windows, as plain values for plan_commands."""
        from homeassistant.util import dt as dt_util
        hass, out = self.hass, {}
        pid = self.conf.get(CONF_LITE_PRESENCE)
        if pid and (s := hass.states.get(pid)) is not None:
            out["away"] = presence_away(pid.split(".")[0], s.state)
            out["away_since"] = s.last_changed.timestamp()
        cid = self.conf.get(CONF_LITE_CALENDAR)
        if cid and (s := hass.states.get(cid)) is not None and s.state == "on":
            end = dt_util.parse_datetime(str(s.attributes.get("end_time") or ""))
            if end is not None and end.tzinfo is None:
                end = end.replace(tzinfo=dt_util.get_default_time_zone())
            out["event"] = (s.attributes.get("message"), end.timestamp() if end else None)
            out["today"] = dt_util.now().date().isoformat()
        wins = self.conf.get(CONF_LITE_WINDOWS) or []
        if isinstance(wins, str):
            wins = [wins]
        if wins:
            out["has_windows"] = True
            opened = [s.last_changed.timestamp() for w in wins if (s := hass.states.get(w)) is not None and s.state == "on"]
            out["window_since"] = min(opened) if opened else None
        return out

    async def _automate(self, st: dict) -> dict:
        from homeassistant.util import dt as dt_util
        before = dict(self.memo)
        cmds = plan_commands(dt_util.utcnow().timestamp(), view(st), self.memo, **self._inputs())
        if self.memo != before:
            await self.async_save()
        for c in cmds:
            try:
                st = await self.client.send(**c)
                self.auto_error = None
                _LOGGER.info("%s: %s", self.config_entry.title, c)
            except LiteError as exc:
                self.auto_error = str(exc)  # tried again on the next episode / renewal; the relay goes on by itself
        return st

    async def async_command(self, **body) -> None:
        try:
            self.async_set_updated_data(await self.client.send(**body))
        except LiteError as exc:
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(f"HC Lite: {exc}") from exc


class LiteEntity(CoordinatorEntity[LiteCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LiteCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        page = coordinator.client.url + "?page=1"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title,
                                            manufacturer="HC Thermostat", model="HC Lite (Shelly script)",
                                            configuration_url=page if page.startswith("http") else None)

    @property
    def v(self):
        return view(self.coordinator.data)


class LiteClimate(LiteEntity, ClimateEntity):
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_preset_modes = [PRESET_HOME, PRESET_COMFORT, PRESET_SLEEP, PRESET_AWAY, PRESET_VACATION]  # 0.82.0
    _attr_min_temp = 5.0
    _attr_max_temp = 30.0
    _attr_target_temperature_step = 0.5
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "lite_thermostat")
        self._attr_name = None  # the device's name

    @property
    def hvac_modes(self):  # 0.80.0: a heat pump may also cool
        return [HVACMode.HEAT, HVACMode.COOL, HVACMode.OFF] if self.coordinator.settings.src == "hp" else [HVACMode.HEAT, HVACMode.OFF]

    @property
    def current_humidity(self):
        return self.v.humidity if self.v else None

    @property
    def current_temperature(self):
        return self.v.temp if self.v else None

    @property
    def target_temperature(self):
        return self.v.target if self.v else None

    @property
    def hvac_mode(self):
        if self.v is None:
            return None
        if self.v.mode == "off":
            return HVACMode.OFF
        return HVACMode.COOL if self.v.hvac == "cool" else HVACMode.HEAT

    @property
    def hvac_action(self):
        if self.v is None:
            return None
        if self.v.mode == "off" and not self.v.heating:
            return HVACAction.OFF
        if not self.v.heating or self.v.shadow:
            return HVACAction.IDLE
        return HVACAction.COOLING if self.v.hvac == "cool" else HVACAction.HEATING

    @property
    def preset_mode(self):
        if self.v is None:
            return None
        return {"away": PRESET_AWAY, "vacation": PRESET_VACATION, "comfort": PRESET_COMFORT,
                "sleep": PRESET_SLEEP}.get(self.v.preset, PRESET_HOME)

    @property
    def extra_state_attributes(self) -> dict:
        v = self.v
        if v is None:
            return {}
        return {"period": v.period, "reason": v.reason, "shadow": v.shadow, "would_heat": v.heating if v.shadow else None,
                "demand": v.demand, "integral": v.integral, "hold": v.hold, "starts_today": v.starts_today, "on_min_today": v.on_min_today,
                # 0.79.2: the HC dial card shows "LITE·HIST" / "LITE·TPI" (0.79.4: "LITE·PID") and its shadow mark from these
                "control_type": "lite", "lite_ctl": ((self.coordinator.data or {}).get("cfg") or {}).get("ctl"),
                "hc_mode": "shadow" if v.shadow else "active", "settings_error": self.coordinator.pushed_error,
                # 0.80.0: the heat source, cooling, the dew point and the buffer probes
                "heat_source": v.src, "lite_hvac": v.hvac, "dew_point": v.dew_point, "flow_pipe": v.pipe,
                "dew_stop": v.dew_stop, "dew_warn": v.dew_warn,
                "buffer": [{"name": n, "temp": t} for n, t in v.buffer] or None,
                # 0.82.0: the preset on the relay, who asked for it, its end; the weekend program today; the button
                "lite_preset": v.preset, "preset_source": v.psrc, "preset_until": _iso(v.puntil),
                "vacation_until": _iso(v.vacation), "window_left_s": v.window_s, "weekend_program_today": v.we_today,
                "last_button": v.btn_ev, "automation_error": self.coordinator.auto_error}

    async def async_set_temperature(self, **kwargs) -> None:
        if (t := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self.coordinator.async_command(target=float(t), hold="next")

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_command(mode="off")
        else:  # 0.80.0: heating or cooling, and the program again
            await self.coordinator.async_command(mode="auto", hvac="cool" if hvac_mode == HVACMode.COOL else "heat")

    async def async_turn_on(self) -> None:
        await self.coordinator.async_command(mode="auto")  # 0.80.0: heating or cooling, as it was

    async def async_turn_off(self) -> None:
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_set_preset_mode(self, preset_mode) -> None:
        if preset_mode == PRESET_VACATION:
            from homeassistant.exceptions import ServiceValidationError
            raise ServiceValidationError("HC Lite: a vacation needs its end – use the hc_thermostat.lite_vacation action")
        cmd = {PRESET_AWAY: {"mode": "away"}, PRESET_COMFORT: {"preset": "comfort"},
               PRESET_SLEEP: {"preset": "sleep"}}.get(preset_mode, {"preset": "home"})
        await self.coordinator.async_command(**cmd, src="ha")

    async def async_lite_comfort(self) -> None:
        """0.82.0 action: comfort (the program's target + its comfort step, for its comfort time; again: longer)."""
        await self.coordinator.async_command(preset="comfort", src="ha")

    async def async_lite_vacation(self, until=None, clear: bool = False) -> None:
        """0.82.0 action: away until `until` (preheated back on time); clear: end it now."""
        from homeassistant.exceptions import ServiceValidationError
        from homeassistant.util import dt as dt_util
        if clear or until is None:
            await self.coordinator.async_command(vacation=0, src="ha")
            return
        when = until if hasattr(until, "timestamp") else dt_util.parse_datetime(str(until))
        if when is None:
            raise ServiceValidationError("HC Lite: give the vacation's end as a date and time")
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt_util.get_default_time_zone())
        if when <= dt_util.now():
            raise ServiceValidationError("HC Lite: the vacation's end is already past")
        await self.coordinator.async_command(vacation=int(when.timestamp()), src="ha")


class LiteBoiler(LiteEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.HEAT

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "lite_boiler")

    @property
    def is_on(self):
        return None if self.v is None else self.v.heating

    @property
    def extra_state_attributes(self) -> dict:
        return {} if self.v is None else {"shadow": self.v.shadow, "real_relay": self.v.real_relay}


class LiteReason(LiteEntity, SensorEntity):
    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "lite_reason")

    @property
    def native_value(self):
        return None if self.v is None else self.v.reason

    @property
    def extra_state_attributes(self) -> dict:
        return {} if self.v is None else {"period": self.v.period, "mode": self.v.mode, "shadow": self.v.shadow}


class LiteNumber(LiteEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, key: str, field: str, unit) -> None:
        super().__init__(coordinator, key)
        self._field = field
        self._attr_native_unit_of_measurement = unit

    @property
    def native_value(self):
        return None if self.v is None else getattr(self.v, self._field)


class LiteBuffer(LiteEntity, SensorEntity):
    """0.80.0: a buffer probe on the relay's add-on (shown only; it steers nothing)."""
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, i: int, name: str | None) -> None:
        super().__init__(coordinator, f"lite_buffer_{i + 1}")
        self._i = i
        self._attr_translation_key = "lite_buffer"
        self._attr_translation_placeholders = {"n": str(i + 1)}
        if name:
            self._attr_name = name

    @property
    def native_value(self):
        b = self.v.buffer if self.v else ()
        return b[self._i][1] if self._i < len(b) else None


class LiteTemp(LiteEntity, SensorEntity):
    """0.80.0: the dew point and the flow pipe (cooling)."""
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, key: str, field: str) -> None:
        super().__init__(coordinator, key)
        self._field = field

    @property
    def native_value(self):
        return None if self.v is None else getattr(self.v, self._field)


def _iso(ts: int | None) -> str | None:
    if ts is None:
        return None
    from homeassistant.util import dt as dt_util
    return dt_util.as_local(dt_util.utc_from_timestamp(ts)).isoformat()


async def async_setup_climate(hass, entry, add) -> None:
    add([LiteClimate(entry.runtime_data)])



async def async_setup_binary_sensor(hass, entry, add) -> None:
    add([LiteBoiler(entry.runtime_data)])


async def async_setup_sensor(hass, entry, add) -> None:
    c = entry.runtime_data
    add([LiteReason(c), LiteNumber(c, "lite_starts_today", "starts_today", None),
         LiteNumber(c, "lite_on_today", "on_min_today", UnitOfTime.MINUTES)])
    s = c.settings  # 0.80.0: only what this relay has
    add([LiteBuffer(c, i, s.bufn[i] if i < len(s.bufn) else None) for i in range(len(s.buf))])
    if s.src == "hp" and (s.hum_id >= 100 or s.sensor == "push"):
        add([LiteTemp(c, "lite_dew_point", "dew_point")])
    if s.dew_id >= 0:
        add([LiteTemp(c, "lite_flow_pipe", "pipe")])


def async_register_actions(hass) -> None:
    """0.82.0: the presets' actions, once for the integration (async_setup); only an HC Lite thermostat answers them."""
    import voluptuous as vol
    from homeassistant.components.climate import DOMAIN as CLIMATE
    from homeassistant.helpers import config_validation as cv
    from homeassistant.helpers.service import async_register_platform_entity_service
    async_register_platform_entity_service(hass, DOMAIN, "lite_comfort", entity_domain=CLIMATE, schema={},
                                           func="async_lite_comfort")
    async_register_platform_entity_service(
        hass, DOMAIN, "lite_vacation", entity_domain=CLIMATE,
        schema={vol.Optional("until"): cv.datetime, vol.Optional("clear", default=False): cv.boolean},
        func="async_lite_vacation")

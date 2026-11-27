"""HC Thermostat: a heating supervisor above thermostats, with its own regulator."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .buffer_coordinator import BufferCoordinator
from .central_coordinator import CentralCoordinator
from .circuit_coordinator import CircuitCoordinator
from .hp_coord_coordinator import HpCoordCoordinator
from .const import CENTRAL_PLATFORMS, CIRCUIT_PLATFORMS, CONF_ROLE, DOMAIN, HP_COORD_PLATFORMS, LITE_PLATFORMS, PLATFORMS
from .coordinator import HcCoordinator, note_ha_start
from .rename import async_track_renames
from .rooms_ha import auto_humidity
from .wizard import async_register_panels, async_remove_panels, async_setup_wizard

_LOGGER = logging.getLogger(__name__)
AUTO_HUMIDITY_DONE = "humidity_auto"  # 0.50.0

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """The setup wizard panel ("HC setup" in the sidebar), available at any time."""
    note_ha_start(hass)  # 0.45.0: the restart protection counts from here
    await async_setup_wizard(hass)
    from .lite import async_register_actions
    async_register_actions(hass)  # 0.82.0: HC Lite comfort / vacation
    return True


def _central(entry: ConfigEntry) -> bool:
    """A central boiler, a buffer tank or a mixing circuit: no thermostat of its own, only its decision entities."""
    return entry.data.get(CONF_ROLE) in ("central", "buffer", "circuit", "hp_coord", "lite")


def _platforms(entry: ConfigEntry) -> list[str]:
    role = entry.data.get(CONF_ROLE)
    if role == "lite":
        return LITE_PLATFORMS
    return HP_COORD_PLATFORMS if role == "hp_coord" else CIRCUIT_PLATFORMS if role == "circuit" else CENTRAL_PLATFORMS


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await async_register_panels(hass)  # 0.45.0: back after the last instance was deleted
    if _central(entry):
        if entry.data.get(CONF_ROLE) == "lite":  # 0.79.2: HC Lite – a Shelly script heats, HA manages it
            from .lite import LiteCoordinator
            central = LiteCoordinator(hass, entry)
            await central.async_load()  # 0.79.9: the settings revision of the last sync
        elif entry.data.get(CONF_ROLE) == "buffer":
            central = BufferCoordinator(hass, entry)
            await central.async_load()
        elif entry.data.get(CONF_ROLE) in ("circuit", "hp_coord"):  # 0.54.0 / 0.55.0, shadow only
            central = (CircuitCoordinator if entry.data.get(CONF_ROLE) == "circuit" else HpCoordCoordinator)(hass, entry)
            await central.async_load()

            async def _save_circuit(_event) -> None:
                await central.async_save()

            entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _save_circuit))
        else:
            central = CentralCoordinator(hass, entry)
            await central.async_load()  # when the pump last ran (pump exercise, 0.39.0)
        await central.async_config_entry_first_refresh()
        entry.runtime_data = central
        await hass.config_entries.async_forward_entry_setups(entry, _platforms(entry))
        entry.async_on_unload(entry.add_update_listener(_async_reload))
        entry.async_on_unload(async_track_renames(hass, entry))  # 0.51.1: a renamed entity is followed
        return True
    _auto_humidity(hass, entry)
    coordinator = HcCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_backfill()
    await coordinator.async_backfill_rooms()
    await coordinator.async_refresh_climate()  # 0.51.0: the energy rating's year of outdoor means
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_track_target_source())
    entry.async_on_unload(coordinator.async_track_runs())  # 0.79.5: heating runs counted on the relay's switch-on
    entry.async_on_unload(coordinator.async_track_managed())  # 0.42.0: two-way with the managed thermostat
    entry.async_on_unload(coordinator.async_track_room_presence())  # 0.43.0: room presence sources
    # 0.71.0: the house's AI analysis – kept over a restart, made daily when an AI Task entity is given
    from .ai_report import AiReporter
    coordinator.ai = AiReporter(hass, entry)
    await coordinator.ai.async_load()
    if coordinator.ai.ai_entity:
        from homeassistant.helpers.event import async_track_time_change
        hour, minute, second = coordinator.ai.daily_time()

        async def _daily(_now) -> None:
            await coordinator.ai.async_run()
            coordinator.async_update_listeners()

        entry.async_on_unload(async_track_time_change(hass, _daily, hour=hour, minute=minute, second=second))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    entry.async_on_unload(async_track_renames(hass, entry))  # 0.51.1: a renamed entity is followed
    # 0.51.1: the instance's Repairs entry goes with it (a reload builds it again when the problem is still there)
    entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, f"sensor_problem_{entry.entry_id}"))
    entry.async_on_unload(lambda: ir.async_delete_issue(hass, DOMAIN, f"source_problem_{entry.entry_id}"))  # 0.66.0

    async def _save(_event) -> None:
        await coordinator.async_save()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _save))
    return True


def _auto_humidity(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """0.50.0: once per instance, the humidity sensors of the rooms' thermometers go into the settings (the user can
    untick them in the rooms form; they are not added back)."""
    if entry.options.get(AUTO_HUMIDITY_DONE):
        return
    try:
        found = auto_humidity(hass, {**entry.data, **entry.options}, entry.entry_id) or {}
    except Exception:  # a convenience: the instance starts without it
        _LOGGER.debug("No humidity sensors found for the rooms", exc_info=True)
        found = {}
    # before the update listener is set: no reload
    hass.config_entries.async_update_entry(entry, options={**entry.options, **found, AUTO_HUMIDITY_DONE: True})
    if found:
        _LOGGER.info("%s: humidity sensors of the rooms added to the settings", entry.title)


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The instance is deleted: its store goes. TRV heads and the managed thermostat keep the last target HC wrote
    (nothing is written back – README "Removing an instance"). 0.45.0: the last instance takes the panels with it."""
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()
    if not [e for e in hass.config_entries.async_entries(DOMAIN) if e.entry_id != entry.entry_id]:
        async_remove_panels(hass)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if _central(entry):
        if entry.data.get(CONF_ROLE) in ("central", "circuit", "hp_coord"):
            await entry.runtime_data.async_save()
        return await hass.config_entries.async_unload_platforms(entry, _platforms(entry))
    await entry.runtime_data.async_save()
    if (load := entry.runtime_data.supervisor.load) is not None:
        load.manager.release(load.name)  # free its room at once (options changed, removed)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

"""HC Thermostat: a heating supervisor above thermostats, with its own regulator."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .buffer_coordinator import BufferCoordinator
from .central_coordinator import CentralCoordinator
from .const import CENTRAL_PLATFORMS, CONF_ROLE, DOMAIN, PLATFORMS
from .coordinator import HcCoordinator
from .wizard import async_setup_wizard

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """The setup wizard panel ("HC setup" in the sidebar), available at any time."""
    await async_setup_wizard(hass)
    return True


def _central(entry: ConfigEntry) -> bool:
    """A central boiler or a buffer tank: no thermostat of its own, only its decision entities."""
    return entry.data.get(CONF_ROLE) in ("central", "buffer")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if _central(entry):
        if entry.data.get(CONF_ROLE) == "buffer":
            central = BufferCoordinator(hass, entry)
            await central.async_load()
        else:
            central = CentralCoordinator(hass, entry)
        await central.async_config_entry_first_refresh()
        entry.runtime_data = central
        await hass.config_entries.async_forward_entry_setups(entry, CENTRAL_PLATFORMS)
        entry.async_on_unload(entry.add_update_listener(_async_reload))
        return True
    coordinator = HcCoordinator(hass, entry)
    await coordinator.async_load()
    await coordinator.async_backfill()
    await coordinator.async_backfill_rooms()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(coordinator.async_track_target_source())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))

    async def _save(_event) -> None:
        await coordinator.async_save()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _save))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if _central(entry):
        return await hass.config_entries.async_unload_platforms(entry, CENTRAL_PLATFORMS)
    await entry.runtime_data.async_save()
    if (load := entry.runtime_data.supervisor.load) is not None:
        load.manager.release(load.name)  # free its room at once (options changed, removed)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

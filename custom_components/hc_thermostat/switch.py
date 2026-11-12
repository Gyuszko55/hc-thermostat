"""0.42.0: "HC supervision paused" – one switch per instance with external or AC control.

While on, HC writes nothing to the managed thermostat (its decision is still computed and logged); switched off, it
takes over the thermostat's current target as a manual target. Relay controls get no such switch: a paused relay
could stay on.
"""

from __future__ import annotations

import re

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import CONF_ROLE
from .entity import HcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    if entry.data.get(CONF_ROLE) in ("central", "buffer"):
        return
    c = entry.runtime_data
    if getattr(c, "managed", False):
        async_add_entities([HcSupervisionPaused(c)])


class HcSupervisionPaused(HcEntity, SwitchEntity, RestoreEntity):
    _attr_icon = "mdi:pause-circle-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "supervision_paused")
        # 0.45.0: an instance named "… HC" gets "… HC supervision paused", not "… HC HC supervision paused"; the
        # unique_id (and so the entity_id already in the registry) stays the same
        if title_has_hc(coordinator.config_entry.title):
            self._attr_translation_key = "supervision_paused_plain"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self.coordinator.restore_paused(last.state == "on")
        else:
            self.coordinator.restore_paused(False)

    @property
    def is_on(self) -> bool:
        return self.coordinator.paused

    async def async_turn_on(self, **kwargs) -> None:
        await self.coordinator.async_set_paused(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        await self.coordinator.async_set_paused(False)
        self.async_write_ha_state()


def title_has_hc(title: str | None) -> bool:
    """The instance's name has "HC" as a word already (e.g. "Boiler HC")."""
    return bool(re.search(r"(^|[^0-9A-Za-z])HC($|[^0-9A-Za-z])", str(title or "")))

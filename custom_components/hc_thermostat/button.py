"""Reset of what the supervisor learned about the house."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory

from .entity import HcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([HcResetLearning(entry.runtime_data)])


class HcResetLearning(HcEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reset_learning")

    async def async_press(self) -> None:
        self.coordinator.supervisor.learner.reset()
        await self.coordinator.async_save()
        await self.coordinator.async_request_refresh()

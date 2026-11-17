"""Reset of what the supervisor learned about the house."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .entity import HcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    c = entry.runtime_data
    extra = [HcAiReportNow(c)] if getattr(c, "ai", None) is not None and c.ai.ai_entity else []  # 0.71.0
    async_add_entities([HcResetLearning(c), HcResetHouse(c), *extra])


class HcResetLearning(HcEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:school-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reset_learning")

    async def async_press(self) -> None:
        self.coordinator.supervisor.learner.reset()
        await self.coordinator.async_save()
        await self.coordinator.async_request_refresh()


class HcResetHouse(HcEntity, ButtonEntity):
    """0.50.0: the house changed (insulation, new windows): the loss factor, the free heat and the time constant are
    learned again from today. The values given by hand stay the starting point."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:home-thermometer-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "reset_house_model")

    async def async_press(self) -> None:
        sup = self.coordinator.supervisor
        sup.heat_need.reset(dt_util.now().date().isoformat())
        sup.tau.reset()
        await self.coordinator.async_save()
        await self.coordinator.async_request_refresh()


class HcAiReportNow(HcEntity, ButtonEntity):
    """0.71.0: make the house's AI analysis of yesterday now."""

    _attr_icon = "mdi:robot-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "ai_report_now")

    async def async_press(self) -> None:
        await self.coordinator.ai.async_run()
        self.coordinator.async_update_listeners()


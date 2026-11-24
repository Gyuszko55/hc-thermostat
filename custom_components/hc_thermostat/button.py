"""Reset of what the supervisor learned about the house."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.util import dt as dt_util

from .entity import HcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    c = entry.runtime_data
    if entry.data.get("role") == "hp_coord":  # 0.77.0: only the life-safety acknowledgement there
        async_add_entities([HcSafetyAck(c)] if getattr(c, "safety", None) is not None else [])
        return
    extra = [HcAiReportNow(c)] if getattr(c, "ai", None) is not None and c.ai.ai_entity else []  # 0.71.0
    if getattr(c, "safety", None) is not None:
        extra.append(HcSafetyAck(c))  # 0.77.0
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
        from homeassistant.exceptions import HomeAssistantError
        from .ai_report import AiLimited
        try:
            await self.coordinator.ai.async_run(manual=True)  # 0.78.2: rate limited
        except AiLimited as err:
            raise HomeAssistantError(str(err)) from err
        self.coordinator.async_update_listeners()



class HcSafetyAck(HcEntity, ButtonEntity):
    """0.77.0: acknowledge the life-safety stop – only with every safety input clear (and read) again."""

    _attr_icon = "mdi:shield-check-outline"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "safety_ack")

    async def async_press(self) -> None:
        user = getattr(getattr(self, "_context", None), "user_id", None) if hasattr(self, "_context") else None
        if not self.coordinator.safety.acknowledge(user or "button"):
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError("A safety input is still in alarm or cannot be read – the stop holds")
        await self.coordinator.async_request_refresh()

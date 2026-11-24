"""0.55.0: the manual offset of a heat pump coordination instance (−8…+8 °C), kept over restarts."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber

from .const import CONF_ROLE
from .entity import HcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    if entry.data.get(CONF_ROLE) != "hp_coord":
        return
    async_add_entities([HcHpOffset(entry.runtime_data)])


class HcHpOffset(HcEntity, RestoreNumber):
    """The correction added to the heat pump's flow target: a unit that makes 38 °C on a 42 °C command needs +4."""

    _attr_native_min_value = -8.0
    _attr_native_max_value = 8.0
    _attr_native_step = 0.5
    _attr_native_unit_of_measurement = "°C"
    _attr_mode = NumberMode.BOX
    _attr_icon = "mdi:plus-minus-variant"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "hp_offset")

    async def async_added_to_hass(self) -> None:
        """0.79.1: one correction. The restored value stays only while the settings form still holds what it held when
        the value was set; a form saved with another value since then wins (and the form opens on the value in use)."""
        await super().async_added_to_hass()
        form = self.coordinator.hp.cfg.hp_offset
        last = await self.async_get_last_number_data()
        value = last.native_value if last is not None and last.native_value is not None else form
        state = await self.async_get_last_state()
        was = (state.attributes.get("form_offset") if state is not None else None)
        if was is not None:
            try:
                if float(was) != float(form):
                    value = form  # the form was saved with a new value: it is the one in use now
            except (TypeError, ValueError):
                pass
        self.coordinator.offset = max(-8.0, min(8.0, float(value)))

    @property
    def extra_state_attributes(self) -> dict:
        c = self.coordinator
        form = c.hp.cfg.hp_offset
        active = c.offset if c.offset is not None else form
        return {"form_offset": form, "source": "entity" if active != form else "form"}

    @property
    def native_value(self) -> float:
        c = self.coordinator
        return c.offset if c.offset is not None else c.hp.cfg.hp_offset

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.offset = max(-8.0, min(8.0, float(value)))
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

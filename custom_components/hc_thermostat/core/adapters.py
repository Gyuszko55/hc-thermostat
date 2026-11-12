"""Adapters for known thermostat integrations (0.42.0, stage 1 of the interoperability work).

HC's external / AC control sends an hvac mode and a target temperature to an existing climate entity. Each
integration behind that entity has its own habits; an adapter knows them:

- its capabilities, always read from the LIVE state attributes (hvac_modes, min_temp, max_temp, target_temp_step,
  preset_modes) – never hard-coded, the same integration differs per device;
- how a target is rounded to the entity's step and clamped to its range (a 1 °C-step air conditioner refuses 22.5);
- whether it really heats now (`hvac_action`; None when the integration does not report it);
- which hvac mode means "heat" for it;
- notes on its own features, for display (its own PID, calibration, window detection …).

The integration stays free to run on its own; HC only writes the mode and the target. Pure Python, no Home
Assistant imports. Stage 2 adds preset mapping and per-function delegation.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

_HEATING = {"heating", "preheating"}
_NOT_HEATING = {"idle", "off", "cooling", "drying", "fan", "defrosting"}


@dataclass(frozen=True)
class Capabilities:
    hvac_modes: tuple = ()
    min_temp: float | None = None
    max_temp: float | None = None
    step: float | None = None
    preset_modes: tuple = ()
    has_action: bool = False


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


class GenericAdapter:
    """Any climate entity: today's behaviour, with the target fitted to the entity's own step and range."""

    key = "generic"
    name = "Generic climate"
    name_hu = "Általános termosztát"
    notes_en: tuple = ()
    notes_hu: tuple = ()

    def capabilities(self, attributes: Mapping[str, Any] | None) -> Capabilities:
        a = attributes or {}
        step = _num(a.get("target_temp_step"))
        return Capabilities(
            hvac_modes=tuple(str(m) for m in (a.get("hvac_modes") or ())),
            min_temp=_num(a.get("min_temp")),
            max_temp=_num(a.get("max_temp")),
            step=step if step is not None and step > 0 else None,
            preset_modes=tuple(str(p) for p in (a.get("preset_modes") or ())),
            has_action="hvac_action" in a and a.get("hvac_action") is not None,
        )

    def fit_target(self, value: float | None, attributes: Mapping[str, Any] | None) -> float | None:
        """Clamp to the entity's range, then round to its step (half up), never outside the range."""
        if value is None:
            return None
        caps = self.capabilities(attributes)
        v = float(value)
        if caps.min_temp is not None:
            v = max(v, caps.min_temp)
        if caps.max_temp is not None:
            v = min(v, caps.max_temp)
        if caps.step:
            v = math.floor(v / caps.step + 0.5 + 1e-9) * caps.step
            if caps.min_temp is not None and v < caps.min_temp - 1e-9:
                v += caps.step
            if caps.max_temp is not None and v > caps.max_temp + 1e-9:
                v -= caps.step
        return round(v, 2)

    def actual_heating(self, attributes: Mapping[str, Any] | None) -> bool | None:
        action = (attributes or {}).get("hvac_action")
        if action is None:
            return None
        action = str(action).lower()
        if action in _HEATING:
            return True
        if action in _NOT_HEATING:
            return False
        return None

    def heat_mode(self, attributes: Mapping[str, Any] | None) -> str:
        """The hvac mode that means "heat" for this entity (heat, else heat_cool / auto when it has no heat)."""
        modes = self.capabilities(attributes).hvac_modes
        if not modes or "heat" in modes:
            return "heat"
        for m in ("heat_cool", "auto"):
            if m in modes:
                return m
        return "heat"

    def describe(self, attributes: Mapping[str, Any] | None) -> dict:
        caps = self.capabilities(attributes)
        return {"adapter": self.key, "name": self.name, "name_hu": self.name_hu,
                "hvac_modes": list(caps.hvac_modes), "min_temp": caps.min_temp, "max_temp": caps.max_temp,
                "step": caps.step, "preset_modes": list(caps.preset_modes), "has_action": caps.has_action,
                "notes_en": list(self.notes_en), "notes_hu": list(self.notes_hu)}


class SmartThermostatAdapter(GenericAdapter):
    """Smart Thermostat (PID) – custom integration `smart_thermostat`: its own PID drives the heater."""

    key = "smart_thermostat"
    name = "Smart Thermostat (PID)"
    name_hu = "Smart Thermostat (PID)"
    notes_en = ("Own PID regulator", "Own presets (not used by HC yet)")
    notes_hu = ("Saját PID-szabályozó", "Saját presetek (a HC még nem használja)")


class BetterThermostatAdapter(GenericAdapter):
    """Better Thermostat – custom integration `better_thermostat`: TRVs calibrated by a room sensor."""

    key = "better_thermostat"
    name = "Better Thermostat"
    name_hu = "Better Thermostat"
    notes_en = ("Own TRV calibration", "Own window detection")
    notes_hu = ("Saját TRV-kalibráció", "Saját ablakérzékelés")


class GreeAdapter(GenericAdapter):
    """Gree air conditioner – core integration `gree`: whole degrees, no hvac_action."""

    key = "gree"
    name = "Gree air conditioner"
    name_hu = "Gree klíma"
    notes_en = ("Air conditioner", "Reports no hvac_action: actual heating unknown")
    notes_hu = ("Klíma", "Nem jelzi, fűt-e éppen (nincs hvac_action)")

    def actual_heating(self, attributes: Mapping[str, Any] | None) -> bool | None:
        return None  # the Gree integration does not report what the unit does


_ADAPTERS = {a.key: a for a in (SmartThermostatAdapter(), BetterThermostatAdapter(), GreeAdapter())}
_GENERIC = GenericAdapter()


def adapter_for(platform: str | None) -> GenericAdapter:
    """The adapter of an integration (the entity registry's platform); the generic one when it is not known."""
    return _ADAPTERS.get(platform or "", _GENERIC)

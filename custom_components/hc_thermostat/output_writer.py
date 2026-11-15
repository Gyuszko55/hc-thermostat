"""0.56.0: writes one target out – a flow target to a number / input_number / climate, or ON/OFF to a switch /
input_boolean / climate – through core/output_guard.py (one writer, no write in shadow, grace after a start,
conflict detection, keep-alive). The value is clamped to the output's own min / max and rounded to its step."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components import persistent_notification as pn

from .core.output_guard import MODES, OutputGuard, effective
from .units import climate_temp_c, from_c, state_value_c, to_c, to_system

_LOGGER = logging.getLogger(__name__)


class OutputWriter:
    def __init__(self, hass, entity_id: str | None, onoff: bool = False, keepalive_s: float = 0.0,
                 confirm_s: float = 60.0) -> None:
        self.hass = hass
        self.entity_id = entity_id or None
        self.onoff = onoff
        self.guard = OutputGuard(tolerance=0.0 if onoff else 0.25, keepalive_s=keepalive_s, confirm_s=confirm_s)
        self.status = "none" if not self.entity_id else "shadow"
        self.error: str | None = None

    @property
    def domain(self) -> str:
        return self.entity_id.split(".", 1)[0] if self.entity_id else ""

    def read(self) -> tuple[float | None, datetime | None]:
        """The output's value now (°C, or 1 / 0) and when it last changed; None when unavailable."""
        state = self.hass.states.get(self.entity_id) if self.entity_id else None
        if state is None or state.state in ("unavailable", "unknown"):
            return None, None
        changed = getattr(state, "last_changed", None)
        if self.domain == "climate":
            if self.onoff:
                return (0.0 if state.state == "off" else 1.0), changed
            # a climate's target changes in its attributes: last_updated is when it last moved
            return climate_temp_c(self.hass, state.attributes, "temperature"), getattr(state, "last_updated", changed)
        if self.onoff:
            if state.state in ("on", "off"):
                return (1.0 if state.state == "on" else 0.0), changed
            return None, None
        return state_value_c(state), changed

    def _number_value(self, state, value_c: float) -> float:
        attrs = state.attributes
        value = from_c(value_c, attrs.get("unit_of_measurement"))
        step = attrs.get("step")
        if isinstance(step, (int, float)) and step > 0:
            value = round(round(value / step) * step, 3)
        lo, hi = attrs.get("min"), attrs.get("max")
        if isinstance(lo, (int, float)):
            value = max(float(lo), value)
        if isinstance(hi, (int, float)):
            value = min(float(hi), value)
        return value

    async def _call(self, want: float) -> None:
        hass, eid, dom = self.hass, self.entity_id, self.domain
        state = hass.states.get(eid)
        if self.onoff:
            if dom == "climate":
                modes = [m for m in (state.attributes.get("hvac_modes") or []) if m != "off"]
                mode = "off" if want < 0.5 else ("heat" if "heat" in modes or not modes else modes[0])
                await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": eid, "hvac_mode": mode}, blocking=True)
            else:
                await hass.services.async_call("homeassistant", "turn_on" if want >= 0.5 else "turn_off", {"entity_id": eid}, blocking=True)
            return
        if dom == "climate":
            value = to_system(hass, want, state.attributes.get("target_temp_step"))
            await hass.services.async_call("climate", "set_temperature", {"entity_id": eid, "temperature": value}, blocking=True)
            return
        await hass.services.async_call(dom, "set_value", {"entity_id": eid, "value": self._number_value(state, want)}, blocking=True)

    async def apply(self, now: datetime, want: float | bool | None, writing: bool, uptime_s: float) -> str:
        """Write `want` when the guard allows it; returns (and keeps) the status."""
        if not self.entity_id:
            self.status = "none"
            return self.status
        if isinstance(want, bool):
            want = 1.0 if want else 0.0
        if not writing:
            self.status = "shadow"
            return self.status
        current, changed = self.read()
        if current is not None and not self.onoff and self.domain != "climate":
            state = self.hass.states.get(self.entity_id)
            # compare with what would really land there (its step and limits), in °C
            landed = self._number_value(state, want) if want is not None else None
            unit = state.attributes.get("unit_of_measurement")
            want_cmp = to_c(landed, unit) if landed is not None else None
        else:
            want_cmp = want
        write, status = self.guard.decide(now, want_cmp, current, changed, uptime_s)
        if write:
            try:
                await self._call(want)
                self.guard.wrote(now, want_cmp)
                self.error = None
            except Exception as err:  # a failed write must not stop the next decision
                _LOGGER.warning("HC could not write %s: %s", self.entity_id, err)
                self.error, status = str(err), "error"
        self.status = status
        return status

    def info(self) -> dict:
        return {"entity": self.entity_id, "status": self.status, "error": self.error, **self.guard.state()}


class WriteControl:
    """The writing mode of a circuit / heat pump coordination instance (0.56.0): shadow, a supervised trial for
    `trial_hours` (it ends by itself: back to shadow, with a notification), or permanent; plus the pause switch."""

    def __init__(self, hass, entry, conf: dict) -> None:
        self.hass, self.entry = hass, entry
        mode = conf.get("mode", "shadow")
        self.mode = mode if mode in MODES else "shadow"
        self.trial_hours = float(conf.get("trial_hours") or 4.0)
        try:
            from datetime import datetime as _dt
            self.trial_start = _dt.fromisoformat(conf["trial_start"]) if conf.get("trial_start") else None
        except (TypeError, ValueError):
            self.trial_start = None
        self.paused = False  # the instance's "writing paused" switch (restored by it)
        self._ending = False
        self._conflicts: set[str] = set()

    def writing(self, now: datetime) -> bool:
        return effective(self.mode, self.trial_start, self.trial_hours, now)[0] and not self.paused

    def trial_end(self, now: datetime):
        return effective(self.mode, self.trial_start, self.trial_hours, now)[1]

    def status(self, now: datetime) -> str:
        if self.mode == "shadow":
            return "shadow"
        if self.mode == "trial" and not effective(self.mode, self.trial_start, self.trial_hours, now)[0]:
            return "trial_over"
        return "paused" if self.paused else self.mode

    async def tick(self, now: datetime) -> None:
        """A trial that ran out goes back to shadow (the entry reloads with the new options) and says so."""
        if self.mode != "trial" or self._ending or self.trial_start is None:
            return
        if effective(self.mode, self.trial_start, self.trial_hours, now)[0]:
            return
        self._ending = True
        title = self.entry.title
        pn.async_create(self.hass, f"{title}: the supervised trial ended after {self.trial_hours:g} h – back in shadow "
                        "mode, nothing is written any more. / A felügyelt próba lejárt – újra árnyék mód, a HC nem ír.",
                        title="HC Thermostat", notification_id=f"hc_trial_{self.entry.entry_id}")
        options = {**self.entry.options, "mode": "shadow", "trial_start": None}
        self.hass.config_entries.async_update_entry(self.entry, options=options)

    def note_conflict(self, writer: "OutputWriter") -> None:
        """One notification when a target gets a second writer; cleared when it gives way."""
        key = writer.entity_id or ""
        if writer.status == "not_accepted" and key not in self._conflicts:
            self._conflicts.add(key)
            pn.async_create(self.hass, f"{self.entry.title}: {key} did not take HC's value ({writer.guard.last_value}; "
                            f"it shows {writer.read()[0]}) after {writer.guard.unconfirmed + 1} writes. HC stops writing "
                            "this value until the value it wants changes – check the device (offline, refused, rounded). / "
                            "Az eszköz nem fogadta el a HC értékét (többszöri írás után sem): a HC nem írja tovább, amíg "
                            "az új cél nem változik – nézd meg az eszközt.",
                            title="HC Thermostat", notification_id=f"hc_conflict_{self.entry.entry_id}_{key}")
        elif writer.status == "conflict" and key not in self._conflicts:
            self._conflicts.add(key)
            pn.async_create(self.hass, f"{self.entry.title}: {key} was changed by someone else "
                            f"({writer.guard.conflict_value}; HC wrote {writer.guard.last_value}). HC stops writing it until "
                            "the value is HC's again – one target, one writer. / Más is írja ezt a célt: a HC nem ír bele, "
                            "amíg az érték újra az övé nem lesz.",
                            title="HC Thermostat", notification_id=f"hc_conflict_{self.entry.entry_id}_{key}")
        elif writer.status not in ("conflict", "not_accepted") and key in self._conflicts:
            self._conflicts.discard(key)
            pn.async_dismiss(self.hass, f"hc_conflict_{self.entry.entry_id}_{key}")

    def info(self, now: datetime) -> dict:
        end = self.trial_end(now)
        return {"write_mode": self.mode, "write_status": self.status(now), "paused": self.paused,
                "trial_end": end.isoformat() if end else None}

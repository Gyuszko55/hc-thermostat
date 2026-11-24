"""0.56.0: writes one target out – a flow target to a number / input_number / climate, or ON/OFF to a switch /
input_boolean / climate – through core/output_guard.py (one writer, no write in shadow, grace after a start,
conflict detection, keep-alive). The value is clamped to the output's own min / max and rounded to its step."""

from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components import persistent_notification as pn
from homeassistant.helpers import issue_registry as ir

from .core.output_guard import MODES, OutputGuard, effective, round_target
from .const import DOMAIN
from .units import CELSIUS, climate_temp_c, from_c, state_value_c, system_unit, to_c

_LOGGER = logging.getLogger(__name__)


class OutputWriter:
    def __init__(self, hass, entity_id: str | None, onoff: bool = False, keepalive_s: float = 0.0,
                 confirm_s: float = 60.0, round_mode: str = "device", restore_s: float = 0.0,
                 restore_tries: int = 3) -> None:
        self.hass = hass
        self.round_mode = round_mode if round_mode in ("device", "half_up", "whole_up") else "device"  # 0.64.0
        self.sent: float | None = None  # 0.64.0: the last value really sent (in the entity's unit)
        self.entity_id = entity_id or None
        self.onoff = onoff
        self.guard = OutputGuard(tolerance=0.0 if onoff else 0.25, keepalive_s=keepalive_s, confirm_s=confirm_s,
                                 restore_after_s=max(0.0, float(restore_s or 0)), restore_tries=max(1, int(restore_tries or 3)))
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
                if state.state == "off":
                    return 0.0, changed
                # 0.73.0: with the supervised restore on, "on" is the heating mode HC switches to (heat, else
                # heat_cool / auto) – a unit put into another mode (LocalTuya: auto instead of heat) differs
                if self.guard.restore_after_s > 0 and state.state != self._heat_mode(state):
                    return 0.5, changed
                return 1.0, changed
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
        step = step if isinstance(step, (int, float)) and step > 0 else 0
        value = round_target(value, step, self.round_mode)  # 0.64.0: the entity's step, or up to 0.5 / 1
        lo, hi = attrs.get("min"), attrs.get("max")
        if isinstance(lo, (int, float)):
            value = max(float(lo), value)
        if isinstance(hi, (int, float)):
            value = min(float(hi), value)
        return value

    def _climate_value(self, state, value_c: float) -> float:
        """0.57.1: a climate target as it will land – in the system unit, on the entity's own step (0.5 °C / 1 °F when
        it has none), within its min_temp / max_temp – so HC writes and compares what the device can hold."""
        attrs, unit = state.attributes, system_unit(self.hass)
        value = value_c if unit == CELSIUS else from_c(value_c, unit)
        step = attrs.get("target_temp_step")
        if not isinstance(step, (int, float)) or step <= 0:
            step = 0.5 if unit == CELSIUS else 1.0
        value = round(round_target(value, step, self.round_mode), 2)  # 0.64.0: or up to 0.5 / 1
        lo, hi = attrs.get("min_temp"), attrs.get("max_temp")
        if isinstance(lo, (int, float)):
            value = max(float(lo), value)
        if isinstance(hi, (int, float)):
            value = min(float(hi), value)
        return value

    @staticmethod
    def _heat_mode(state) -> str | None:
        """0.57.1: the mode an ON request switches a climate to – heat, else heat_cool, else auto; never cool / dry /
        fan_only (None: the climate has no heating mode, nothing is switched)."""
        modes = list(state.attributes.get("hvac_modes") or [])
        if not modes:
            return "heat"
        for mode in ("heat", "heat_cool", "auto"):
            if mode in modes:
                return mode
        return None

    async def _call(self, want: float) -> None:
        hass, eid, dom = self.hass, self.entity_id, self.domain
        state = hass.states.get(eid)
        if self.onoff:
            if dom == "climate":
                mode = "off" if want < 0.5 else self._heat_mode(state)
                if mode is None:
                    raise ValueError(f"{eid} has no heating mode (heat / heat_cool / auto): not switched on")
                await hass.services.async_call("climate", "set_hvac_mode", {"entity_id": eid, "hvac_mode": mode}, blocking=True)
            else:
                await hass.services.async_call("homeassistant", "turn_on" if want >= 0.5 else "turn_off", {"entity_id": eid}, blocking=True)
            return
        if dom == "climate":
            value = self._climate_value(state, want)
            await hass.services.async_call("climate", "set_temperature", {"entity_id": eid, "temperature": value}, blocking=True)
            self.sent = value
            return
        value = self._number_value(state, want)
        await hass.services.async_call(dom, "set_value", {"entity_id": eid, "value": value}, blocking=True)
        self.sent = value

    async def apply(self, now: datetime, want: float | bool | None, writing: bool, uptime_s: float,
                    force: bool = False) -> str:
        """Write `want` when the guard allows it; returns (and keeps) the status.

        0.78.2 (security review H1): `force` – a life-safety stop. Shadow, a trial that ended, paused writing, the grace
        after a start and a conflict / an unaccepted / a given-up value do not hold it back: whenever the output shows
        another value than the stop's, it is written (every step, until it lands). Status "safety"."""
        if not self.entity_id:
            self.status = "none"
            return self.status
        if isinstance(want, bool):
            want = 1.0 if want else 0.0
        if force and want is not None:
            return await self._force(now, want)
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
        elif current is not None and not self.onoff and want is not None:
            # 0.57.1: a climate too – its step and min / max (it was compared and written unrounded before)
            state = self.hass.states.get(self.entity_id)
            landed = self._climate_value(state, want)
            want_cmp = landed if system_unit(self.hass) == CELSIUS else to_c(landed, system_unit(self.hass))
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

    async def _force(self, now: datetime, want: float) -> str:
        current, _ = self.read()
        if current is None:
            self.status = "unavailable"
            return self.status
        state = self.hass.states.get(self.entity_id)
        if self.onoff:
            want_cmp = want
        elif self.domain == "climate":
            landed = self._climate_value(state, want)
            want_cmp = landed if system_unit(self.hass) == CELSIUS else to_c(landed, system_unit(self.hass))
        else:
            want_cmp = to_c(self._number_value(state, want), state.attributes.get("unit_of_measurement"))
        if abs(current - want_cmp) > (0.0 if self.onoff else 0.25):
            try:
                await self._call(want)
                self.guard.wrote(now, want_cmp)
                self.error = None
            except Exception as err:  # the next step tries again
                _LOGGER.warning("HC could not write the safety stop to %s: %s", self.entity_id, err)
                self.error = str(err)
        self.status = "safety"
        return self.status

    def reported(self) -> float | None:
        """0.64.0: the target the output reports back now (°C; None: unavailable / an ON-OFF output)."""
        if not self.entity_id or self.onoff:
            return None
        value, _ = self.read()
        return None if value is None else round(value, 2)

    def info(self) -> dict:
        return {"entity": self.entity_id, "status": self.status, "error": self.error, "sent": self.sent,
                "round": self.round_mode, **self.guard.state()}


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
        """One notification when a target gets a second writer; cleared when it gives way. 0.73.0: a restore that
        failed every try is also a Repairs entry (cleared with it)."""
        key = writer.entity_id or ""
        self._sync_failed(writer)
        if writer.status == "failed" and key not in self._conflicts:
            self._conflicts.add(key)
            g = writer.guard
            pn.async_create(self.hass, f"{self.entry.title}: {key} keeps another value ({writer.read()[0]}) than HC asks "
                            f"for ({g.failed_want}); {g.restore_count} restores did not help. HC stops writing it until the "
                            "value it wants changes or the device shows HC's value again – check the device and its mode. / "
                            f"A(z) {key} nem a HC által kért értéken áll ({writer.read()[0]} a kért {g.failed_want} helyett); "
                            f"{g.restore_count} visszaállítás sem segített. A HC nem írja tovább, amíg a kért érték nem "
                            "változik, vagy az eszköz magától vissza nem áll – nézd meg az eszközt és az üzemmódját.",
                            title="HC Thermostat", notification_id=f"hc_conflict_{self.entry.entry_id}_{key}")
        elif writer.status in ("conflict", "not_accepted") and key not in self._conflicts and getattr(writer.guard, "restore_after_s", 0) > 0:
            # 0.73.0: the first lasting difference – a warning; the restore comes after the set time
            self._conflicts.add(key)
            g = writer.guard
            mins = round(g.restore_after_s / 60)
            pn.async_create(self.hass, f"{self.entry.title}: {key} shows {writer.read()[0]} instead of HC's value "
                            f"({g.last_value}). HC writes its value again in {mins} min (restore {g.restore_count + 1} of "
                            f"{g.restore_tries}); pause writing to keep a change made by hand. / A(z) {key} nem a HC "
                            f"értékén áll ({writer.read()[0]}, kért: {g.last_value}). A HC {mins} perc múlva újra beírja a "
                            f"sajátját ({g.restore_count + 1}/{g.restore_tries}. visszaállítás); ha kézzel állítottad, "
                            "szüneteltesd az írást.",
                            title="HC Thermostat – figyelmeztetés / warning", notification_id=f"hc_conflict_{self.entry.entry_id}_{key}")
        elif writer.status == "not_accepted" and key not in self._conflicts:
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
        elif writer.status not in ("conflict", "not_accepted", "failed") and key in self._conflicts \
                and not (getattr(writer.guard, "restore_count", 0) and not getattr(writer.guard, "failed", False)):  # 0.73.0: kept while restoring
            self._conflicts.discard(key)
            pn.async_dismiss(self.hass, f"hc_conflict_{self.entry.entry_id}_{key}")

    def _sync_failed(self, writer: "OutputWriter") -> None:
        key = writer.entity_id or ""
        issue_id = f"write_failed_{self.entry.entry_id}_{key}"
        failed = writer.status == "failed"
        shown = getattr(self, "_failed_shown", set())
        self._failed_shown = shown
        if failed == (key in shown):
            return
        try:
            if failed:
                shown.add(key)
                ir.async_create_issue(self.hass, DOMAIN, issue_id, is_fixable=False, is_persistent=False,
                                      severity=ir.IssueSeverity.ERROR, translation_key="write_failed",
                                      translation_placeholders={"name": self.entry.title, "entity": key,
                                                                "want": str(writer.guard.failed_want),
                                                                "value": str(writer.read()[0]),
                                                                "tries": str(writer.guard.restore_count)})
            else:
                shown.discard(key)
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
        except Exception:  # the Repairs entry is a report – it must never stop the writing
            _LOGGER.debug("The Repairs entry could not be updated", exc_info=True)

    def info(self, now: datetime) -> dict:
        end = self.trial_end(now)
        return {"write_mode": self.mode, "write_status": self.status(now), "paused": self.paused,
                "trial_end": end.isoformat() if end else None}

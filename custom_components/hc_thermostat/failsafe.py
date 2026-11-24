"""0.78.2: the failsafe of the instances that switch heat besides the room thermostat (security review H2).

The room thermostat (coordinator.py) has switched its relay off after FAILSAFE_AFTER failed decisions in a row since
0.45.0. The central boiler, buffer, mixing circuit and heat pump coordination instances had nothing alike: a step that
raised again and again left the boiler / heat source / heat pump as it was – possibly on – for good. Each of them now
counts its failed steps with a StepFailsafe; the first FAILSAFE_AFTER - 1 failures raise as before (the entities go
unavailable, a passing hiccup changes nothing), from the FAILSAFE_AFTER-th the instance writes its safe state (heat
off, the lowest flow) through its usual output path, and a Repairs entry says so until a step works again.
"""

from __future__ import annotations

import logging

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

FAILSAFE_AFTER = 3  # as the room thermostat's (coordinator.FAILSAFE_AFTER)

_WORDS = {
    "en": "its decision failed {n} times in a row – the heat output is switched off for safety until it works again",
    "hu": "a döntése {n}-szor egymás után hibára futott – a hőtermelő biztonsági okból ki van kapcsolva, amíg újra "
          "nem működik",
}


class StepFailsafe:
    """Counts the failed steps of one coordinator; says when the safe state has to be written."""

    def __init__(self, hass, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.errors = 0
        self._shown = False

    @property
    def active(self) -> bool:
        return self.errors >= FAILSAFE_AFTER

    def failed(self) -> bool:
        """Call from an `except` block: True when the safe state is due, False when the error is to be raised."""
        self.errors += 1
        title = getattr(self.entry, "title", "HC")
        _LOGGER.exception("%s: the decision failed (%d in a row)", title, self.errors)
        if not self.active:
            return False
        if self.errors == FAILSAFE_AFTER:
            _LOGGER.warning("%s: %d failed decisions in a row – the heat output is switched off for safety",
                            title, self.errors)
        self._issue(True)
        return True

    def ok(self) -> None:
        """A step worked: the count starts again and the Repairs entry goes."""
        if self.errors:
            _LOGGER.warning("%s: the decision works again after %d failed step(s)",
                            getattr(self.entry, "title", "HC"), self.errors)
        self.errors = 0
        if self._shown:
            self._issue(False)

    def _issue(self, show: bool) -> None:
        try:
            issue_id = f"failsafe_{self.entry.entry_id}"
            if not show:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
                self._shown = False
                return
            hu = str(getattr(self.hass.config, "language", "") or "").startswith("hu")
            ir.async_create_issue(
                self.hass, DOMAIN, issue_id, is_fixable=False, is_persistent=False,
                severity=ir.IssueSeverity.ERROR, translation_key="sensor_problem",
                translation_placeholders={"name": self.entry.title,
                                          "problems": "- HC: " + _WORDS["hu" if hu else "en"].format(n=self.errors)})
            self._shown = True
        except Exception:  # a report – it must never stop the safe state
            _LOGGER.debug("The failsafe's Repairs entry could not be updated", exc_info=True)

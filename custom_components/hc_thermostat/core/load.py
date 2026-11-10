"""Load limit for several electric zones (0.28.0): the relays of one Home Assistant share a power budget.

Every electric instance with `load_limit_kw` > 0 states its own heater power (`boiler_power_kw`). Before its
relay switches on, it asks the LoadManager (one per Home Assistant) for room under the limit:

- it may switch on when the powers already on plus its own fit under the limit, and no instance that has been
  waiting longer would fit too (first come, first served);
- refused, it stays off and its PWM cycle starts again when it gets the room (so it keeps its full on-time,
  and the zones end up staggered instead of all switching on at the start of the cycle);
- a zone that heats without a pause (demand 100 %) gives its room up at the start of its next cycle when an
  other zone waits for it, so no zone starves;
- switching off is never held back; an instance that stopped reporting (removed, crashed) is forgotten after
  10 minutes, a waiting one after 3.
"""

from __future__ import annotations

from datetime import datetime

STALE_ON_S = 600.0
STALE_WAIT_S = 180.0
_EPS = 1e-6


class LoadManager:
    def __init__(self) -> None:
        self._on: dict[str, tuple[float, datetime]] = {}  # name -> (kW, last report)
        self._wait: dict[str, tuple[float, datetime, datetime]] = {}  # name -> (kW, waiting since, last report)

    def _prune(self, now: datetime) -> None:
        self._on = {n: v for n, v in self._on.items() if (now - v[1]).total_seconds() <= STALE_ON_S}
        self._wait = {n: v for n, v in self._wait.items() if (now - v[2]).total_seconds() <= STALE_WAIT_S}

    def used(self, now: datetime, exclude: str | None = None) -> float:
        self._prune(now)
        return round(sum(kw for n, (kw, _) in self._on.items() if n != exclude), 3)

    def _older_waiter_fits(self, name: str, since: datetime, room: float) -> bool:
        return any(other != name and s < since and kw <= room + _EPS for other, (kw, s, _) in self._wait.items())

    def request(self, name: str, kw: float, limit: float, now: datetime, renew: bool = False) -> bool:
        """May `name` (switch on / stay on with) `kw`? renew: a running zone at the start of a new cycle."""
        others = self.used(now, exclude=name)
        room = limit - others
        if name in self._on:
            if renew and self._older_waiter_fits(name, now, room):
                del self._on[name]  # hand over to the one waiting
                self._wait[name] = (kw, now, now)
                return False
            self._on[name] = (kw, now)
            return True
        since = self._wait.get(name, (kw, now, now))[1]
        self._wait[name] = (kw, since, now)
        if kw > room + _EPS or self._older_waiter_fits(name, since, room):
            return False
        del self._wait[name]
        self._on[name] = (kw, now)
        return True

    def report(self, name: str, on: bool, waiting: bool, now: datetime, kw: float = 0.0) -> None:
        """The relay state after a decision; off releases the room, not waiting drops the place in the queue."""
        if on:
            if name in self._on:
                self._on[name] = (self._on[name][0], now)
            else:  # on without a grant (restored after a restart): count it
                self._on[name] = (kw, now)
            self._wait.pop(name, None)
            return
        self._on.pop(name, None)
        if not waiting:
            self._wait.pop(name, None)

    def release(self, name: str) -> None:
        self._on.pop(name, None)
        self._wait.pop(name, None)

    def snapshot(self, now: datetime) -> dict:
        self._prune(now)
        return {"on": {n: kw for n, (kw, _) in self._on.items()},
                "waiting": [n for n, _ in sorted(self._wait.items(), key=lambda i: i[1][1])]}


class LoadClient:
    """One instance's handle on the shared manager."""

    def __init__(self, manager: LoadManager, name: str, kw: float, limit: float) -> None:
        self.manager, self.name, self.kw, self.limit = manager, name, kw, limit

    def request(self, now: datetime, renew: bool = False) -> bool:
        return self.manager.request(self.name, self.kw, self.limit, now, renew)

    def report(self, on: bool, waiting: bool, now: datetime) -> None:
        self.manager.report(self.name, on, waiting, now, self.kw)

    def details(self, now: datetime) -> dict:
        snap = self.manager.snapshot(now)
        return {"load_used_kw": round(sum(snap["on"].values()), 2), "load_limit_kw": self.limit,
                "load_kw": self.kw, "load_waiting": snap["waiting"]}

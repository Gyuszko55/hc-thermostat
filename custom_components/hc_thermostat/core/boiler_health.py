"""Health of an on/off boiler, read from its relay and its power draw (or a flame sensor).

The Cirkó draws 117-123 W while burning, 105-111 W when only the pump runs, 5-7 W on standby; the limits
are options (`power_idle_w`, `power_burn_w`). Seen as normal: the flame comes 0.5-3.5 minutes after the
relay (the pump runs first), and in a long burn the boiler pauses the flame for a few minutes on its own
when the flow is hot enough.

Electric heat (kind "electric": an electric heater or boiler, a heat pump on a relay) has no flame and often its
own thermostat: drawing nothing with the relay on is normal there, so only the flame-free checks apply (0.23.0).

States, the first that applies:
- no_data: the power (or flame) reading is missing for `health_no_data_min` minutes;
- uncommanded_burn (0.23.0): burning with the relay off – a stuck relay or a hand switch; a combi boiler also
  burns for hot water, so only `health_uncommanded_min` minutes within an hour count (electric:
  `health_uncommanded_electric_min`);
- overheating (0.23.0): the room `health_overheat_margin` above the target and still rising, while heating
  `health_overheat_min` of the last 30 minutes;
- no_response: the relay is on, but almost no power for `health_no_response_min` minutes (not for electric);
- no_flame: the relay is on and the pump runs, but no flame for `health_no_ignition_min` minutes since the
  start, or for `health_flame_lost_min` minutes after it burned (not for electric);
- heating_fault: the supervisor's heating fault (long heating while the house still cools);
- short_cycling: more than `health_max_starts_per_hour` burner starts in the last hour;
- ok.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

STATES = ["ok", "no_data", "uncommanded_burn", "overheating", "no_response", "no_flame", "heating_fault", "short_cycling"]
FLAME_SOURCES = ("onoff_boiler", "modulating_boiler")


def health_kind(source: str | None) -> str:
    """flame for a gas / oil boiler, heat_pump for a heat pump, electric for anything else without a burner."""
    if source == "pellet_boiler":
        return "pellet"  # slow ignition and burn-out after the stop: judged by the power draw, the long limit
    if source == "heat_pump":
        return "heat_pump"  # no flame, and it may run for hot water by itself (0.26.0)
    return "electric" if source and source not in FLAME_SOURCES else "flame"


class BoilerHealth:
    def __init__(self, cfg, kind: str = "flame") -> None:
        self.cfg = cfg
        self.kind = kind
        self.state = "ok"
        self.since: datetime | None = None
        self.starts: deque[datetime] = deque()
        self._relay_on_at: datetime | None = None
        self._burned_this_run = False
        self._flame = False
        self._no_flame_since: datetime | None = None
        self._idle_since: datetime | None = None
        self._missing_since: datetime | None = None
        self.last_ignition_s: float | None = None
        self._burn_start: datetime | None = None
        self.burns: deque[float] = deque(maxlen=20)  # minutes of the last burns
        # the last hour: (time, seconds since the previous update, burning, relay off, room temperature)
        self._samples: deque[tuple[datetime, float, bool, bool, float | None]] = deque()
        self._last_t: datetime | None = None

    def update(self, now: datetime, relay_on: bool | None, power: float | None, flame: bool | None,
               heating_fault: bool, indoor: float | None = None, target: float | None = None, busy: bool = False) -> str:
        """busy: a heat pump defrosts or makes hot water – its own work, not a run without command."""
        cfg = self.cfg
        electric = self.kind in ("electric", "heat_pump", "pellet")
        # what the boiler does now: burn / pump / idle, from the power draw if there is one
        if power is not None:
            if electric:
                mode = "burn" if power >= cfg.power_burn_w else "idle"
            else:
                mode = "burn" if power >= cfg.power_burn_w else "pump" if power >= cfg.power_idle_w else "idle"
        elif flame is not None:
            mode = "burn" if flame else "pump"  # without a power reading "not burning" is all we know
        else:
            mode = None
        if mode is None:
            self._missing_since = self._missing_since or now
        else:
            self._missing_since = None
        burning = mode == "burn"
        if relay_on and self._relay_on_at is None:
            self._relay_on_at, self._burned_this_run = now, False  # a new relay run starts
        if burning and not self._flame and not busy:
            self.starts.append(now)
            self._burn_start = now
            if self._relay_on_at is not None and not self._burned_this_run:
                self.last_ignition_s = round((now - self._relay_on_at).total_seconds())
            self._burned_this_run = True
        if not burning and self._flame and self._burn_start is not None:
            self.burns.append(round((now - self._burn_start).total_seconds() / 60, 1))
        self._flame = burning
        while self.starts and now - self.starts[0] > timedelta(hours=1):
            self.starts.popleft()
        # relay runs
        if relay_on:
            self._no_flame_since = None if burning else (self._no_flame_since or now)
            self._idle_since = (self._idle_since or now) if mode == "idle" else None
        else:
            self._relay_on_at, self._no_flame_since, self._idle_since = None, None, None

        # the last hour: burning with the relay off; the last half hour: heating while the room is too warm
        dt = 0.0 if self._last_t is None else min(max((now - self._last_t).total_seconds(), 0.0), 300.0)
        self._last_t = now
        self._samples.append((now, dt, burning and not busy, relay_on is False, indoor))
        while self._samples and now - self._samples[0][0] > timedelta(hours=1):
            self._samples.popleft()
        # a heat pump makes hot water by itself, like a combi boiler: the longer limit
        limit = cfg.health_uncommanded_electric_min if self.kind == "electric" else cfg.health_uncommanded_min
        uncommanded = relay_on is not None and self.uncommanded_min >= limit
        overheating = False
        if indoor is not None and target is not None and indoor >= target + cfg.health_overheat_margin:
            recent = [x for x in self._samples if now - x[0] <= timedelta(minutes=30)]
            burn_min = sum(x[1] for x in recent if x[2]) / 60
            temps = [x[4] for x in recent if x[4] is not None]
            overheating = burn_min >= cfg.health_overheat_min and bool(temps) and indoor - min(temps) >= 0.2

        minutes = lambda since: (now - since).total_seconds() / 60 if since else 0.0  # noqa: E731
        if self._missing_since and minutes(self._missing_since) >= cfg.health_no_data_min:
            state = "no_data"
        elif uncommanded:
            state = "uncommanded_burn"
        elif overheating:
            state = "overheating"
        elif not electric and relay_on and self._idle_since and minutes(self._idle_since) >= cfg.health_no_response_min:
            state = "no_response"
        elif not electric and relay_on and self._no_flame_since and minutes(self._no_flame_since) >= (
                cfg.health_flame_lost_min if self._burned_this_run else cfg.health_no_ignition_min):
            state = "no_flame"
        elif heating_fault:
            state = "heating_fault"
        elif len(self.starts) > cfg.health_max_starts_per_hour:
            state = "short_cycling"
        else:
            state = "ok"
        if state != self.state:
            self.state, self.since = state, now
        return state

    @property
    def uncommanded_min(self) -> float:
        """Minutes burned with the relay off in the last hour."""
        return sum(x[1] for x in self._samples if x[2] and x[3]) / 60

    @property
    def problem(self) -> bool:
        return self.state not in ("ok",)

    def attributes(self) -> dict:
        return {
            "kind": self.kind,
            "since": self.since.isoformat() if self.since else None,
            "starts_last_hour": len(self.starts),
            "last_ignition_s": self.last_ignition_s,
            "average_burn_min": round(sum(self.burns) / len(self.burns), 1) if self.burns else None,
            "burn_without_relay_min": round(self.uncommanded_min, 1),
        }

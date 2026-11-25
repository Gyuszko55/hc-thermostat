"""One HC instance without Home Assistant: the core's supervisor fed from the sample table, saved to a JSON file.

The inputs are built as the integration's coordinator builds them (coordinator.build_inputs) for what a relay-driven
boiler needs: room and outdoor readings with their plausibility, the outdoor day average, presence, windows and the
zone door, the restart confirmation, the real burner state, the heat delivered and the other source's heat. Not yet:
TRV rooms' demand, managed thermostats / air conditioners, floor and heat pump inputs, prices, life-safety inputs –
an instance that needs them is reported as such (`unsupported`).
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta
import json
import logging
from pathlib import Path
from typing import Any

from hc_core import inputs as in_
from hc_core import states as st_
from hc_core.matrix import floor_system, source_defaults
from hc_core.model import Decision, HcConfig, Inputs, Reading
from hc_core.plausibility import Plausibility
from hc_core.room_model import CONF_LEADING, CONF_ROOM_LIST, general_windows, parse_rooms
from hc_core.supervisor import Supervisor
from hc_core.zone import coupled

_LOGGER = logging.getLogger(__name__)
SAVE_EVERY = timedelta(minutes=10)
UNSUPPORTED_KEYS = ("external_entity", "floor_entity", "demand_entity", "humidity_entity", "power_available_entity",
                    "coil_entity", "return_temp_entity", "safety_entities", "hp_defrost_entity", "hp_dhw_entity")


def make_config(hc: dict[str, Any]) -> HcConfig:
    """The instance's settings as the integration turns them into an HcConfig (coordinator.__init__)."""
    system, source = hc.get("system"), hc.get("heat_source")
    return HcConfig.from_mapping({**source_defaults(system, source), **hc, "floor_system": floor_system(system),
                                  "demand_contact": False})


class Engine:
    def __init__(self, hc: dict[str, Any], table: in_.SampleTable, state_file: str | Path | None,
                 started: datetime) -> None:
        self.conf = dict(hc)
        self.table = table
        self.cfg = make_config(self.conf)
        self.sup = Supervisor(self.cfg)
        self.state_file = Path(state_file) if state_file else None
        self.started = started
        cfg = self.cfg
        self.confirm = in_.RestartConfirm(started, cfg.restart_sensor_wait_s, cfg.restart_settle_s)
        self.outdoor = in_.OutdoorAverage()
        self.plaus_indoor = Plausibility(st_.indoor_floor(cfg.plaus_indoor_min, cfg.frost_temp), cfg.plaus_indoor_max,
                                         cfg.plaus_jump, cfg.plaus_confirm_s)
        self.plaus_outdoor = Plausibility(cfg.plaus_outdoor_min, cfg.plaus_outdoor_max)
        self.extra_samples: deque[tuple[datetime, float]] = deque()
        self.counted_extra = 0.0
        self.last_extra: float | None = None
        self.last_save: datetime | None = None
        self.last: Decision | None = None
        self.last_inputs: Inputs | None = None
        self.unsupported = [k for k in UNSUPPORTED_KEYS if self.conf.get(k)]
        self.specs, self.leading = self._rooms()

    # --- settings -------------------------------------------------------------------------------------------------
    def _rooms(self):
        raw = self.conf.get(CONF_ROOM_LIST)
        if not (isinstance(raw, list) and raw):
            return [], None
        specs = parse_rooms(raw)
        leading = self.conf.get(CONF_LEADING)
        leading = leading if any(s.key == leading for s in specs) else None
        if leading is not None:
            specs = [replace(s, heated=True) if s.key == leading and not s.heated else s for s in specs]
        return specs, leading

    def leading_spec(self):
        return next((s for s in self.specs if s.key == self.leading), None)

    def window_ids(self) -> list[str]:
        if not self.specs:
            return list(self.conf.get("window_entities") or [])
        return general_windows(self.conf.get("window_entities"), self.specs, self.leading)

    def entities(self) -> set[str]:
        """Every entity the settings read – each needs a source."""
        c = self.conf
        ids = {c.get(k) for k in ("indoor_entity", "outdoor_entity", "flame_entity", "reference_entity",
                                   "actuator_entity", "heat_energy_entity", "extra_heat_entity", "zone_temp_entity")}
        for k in ("presence_entities", "zone_door_entities", "window_drop_entities"):
            ids.update(c.get(k) or [])
        ids.update(self.window_ids())
        lead = self.leading_spec()
        if lead is not None:
            ids.update(lead.sensors)
        return {i for i in ids if i}

    # --- state ------------------------------------------------------------------------------------------------------
    def restore(self, data: dict[str, Any]) -> None:
        if not data:
            return
        self.sup.restore(data.get("supervisor") or {})
        self.outdoor = in_.OutdoorAverage(data.get("outdoor") or [])
        self.counted_extra = float(data.get("counted_extra", 0.0))
        self.last_extra = data.get("last_extra")

    def follow_learned(self, learner_state: dict[str, Any]) -> bool:
        """0.1.4: take the integration's learner state (learned values and their running windows) as it is."""
        if not isinstance(learner_state, dict) or not isinstance(learner_state.get("learned"), dict):
            return False
        self.sup.learner.restore(learner_state)
        return True

    def follow_regulator(self, regulator_state: dict[str, Any]) -> bool:
        """0.1.5: take the integration's regulator state (the PID integral). The integral only adds up, so once the
        two sides drifted apart (for a while they ran different core versions) the gap stayed for good: hcd asked
        2-3 points more for the same room and its burn minutes ran 30 % above the integration's."""
        if not isinstance(regulator_state, dict):
            return False
        mine = self.sup.regulator.state()
        if not mine or set(mine) != set(regulator_state):
            return False  # another control or a stateless one: nothing to take
        try:
            self.sup.regulator.restore({k: float(v) for k, v in regulator_state.items()})
        except (TypeError, ValueError):
            return False
        return True

    def state(self) -> dict[str, Any]:
        return {"supervisor": self.sup.state(), "outdoor": self.outdoor.state(), "counted_extra": self.counted_extra,
                "last_extra": self.last_extra}

    def load(self) -> bool:
        if self.state_file is None or not self.state_file.exists():
            return False
        try:
            self.restore(json.loads(self.state_file.read_text(encoding="utf-8")))
            return True
        except (OSError, ValueError) as exc:
            _LOGGER.warning("state file %s unreadable (%s) – starting fresh", self.state_file, exc)
            return False

    def save(self) -> None:
        if self.state_file is None:
            return
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state(), default=str), encoding="utf-8")
        tmp.replace(self.state_file)

    # --- inputs (as coordinator.build_inputs) -------------------------------------------------------------------------
    def _reading(self, entity_id: str | None, now: datetime) -> Reading:
        return in_.reading(self.table, entity_id, now)

    def _indoor(self, now: datetime) -> Reading:
        main = self._reading(self.conf.get("indoor_entity"), now)
        lead = self.leading_spec()
        if lead is None or len(lead.sensors) < 2:
            return main
        group = in_.group_reading(self.table, lead.sensors, now, self.cfg.sensor_max_age_s)
        return main if group is None else group

    def _presence(self):
        pairs = [(e, s.state) for e in self.conf.get("presence_entities") or [] if (s := self.table.get(e)) is not None]
        result, _unknown = st_.presence(pairs, self.conf.get("presence_home"), self.conf.get("presence_vacation"))
        return result

    def _cumulative(self, entity_id: str | None) -> float | None:
        s = self.table.get(entity_id) if entity_id else None
        return in_.finite(s.state) if s is not None else None

    def _heat_energy(self, counts: bool) -> float | None:
        c = self.conf
        main = self._cumulative(c.get("heat_energy_entity"))
        extra = self._cumulative(c.get("extra_heat_entity"))
        if extra is not None:
            if counts and self.last_extra is not None and extra > self.last_extra:
                self.counted_extra += (extra - self.last_extra) * float(c.get("extra_factor", 1.0))
            self.last_extra = extra
        if main is None and extra is None:
            return None
        return (main or 0.0) * float(c.get("energy_factor", 1.0)) + self.counted_extra

    def _other_heat_kw(self, now: datetime) -> float:
        value = self._cumulative(self.conf.get("extra_heat_entity"))
        if value is None:
            return 0.0
        samples = self.extra_samples
        samples.append((now, value))
        while now - samples[0][0] > timedelta(hours=1):
            samples.popleft()
        hours = (now - samples[0][0]).total_seconds() / 3600
        if hours < 0.25 or value < samples[0][1]:
            return 0.0
        return (value - samples[0][1]) * float(self.conf.get("extra_factor", 1.0)) / hours

    def _actual_heating(self) -> bool | None:
        c = self.conf
        entity = c.get("flame_entity") or c.get("reference_entity") or c.get("actuator_entity")
        s = self.table.get(entity) if entity else None
        if s is None or s.state in ("unknown", "unavailable"):
            return None
        if entity.startswith("climate."):
            return (s.attributes or {}).get("hvac_action") == "heating"
        return s.state == "on"

    def build_inputs(self, now: datetime) -> Inputs:
        c, cfg = self.conf, self.cfg
        outdoor = self.plaus_outdoor.check(now, self._reading(c.get("outdoor_entity"), now))
        indoor = self.plaus_indoor.check(now, self._indoor(now))
        doors = c.get("zone_door_entities") or []
        door_open = in_.any_on(self.table, doors)
        zone_temp = self._reading(c.get("zone_temp_entity"), now).fresh(cfg.sensor_max_age_s)
        counts = coupled(door_open, indoor.fresh(cfg.sensor_max_age_s), zone_temp,
                         float(c.get("zone_max_diff", 2.0))) or not doors
        extra_kw = self._other_heat_kw(now)
        lead = self.leading_spec()
        return Inputs(
            now=now,
            indoor=indoor,
            outdoor=outdoor,
            outdoor_avg=self.outdoor.update(outdoor.fresh(cfg.sensor_max_age_s), now),
            presence=self._presence(),
            window_open=in_.any_on(self.table, self.window_ids()) or (door_open and not counts),
            enabled=True,
            uptime_s=(now - self.started).total_seconds(),
            indoor_confirmed=self.confirm.check(self.table, [c.get("indoor_entity"),
                                                            *(lead.sensors if lead is not None else ())], now),
            actual_heating=self._actual_heating(),
            heat_energy_kwh=self._heat_energy(counts),
            other_heat_kw=extra_kw if counts else 0.0,
            drop_temps=tuple((e, self._reading(e, now)) for e in c.get("window_drop_entities") or []),
            yield_margin=0.0,  # the cost advice (other source cheaper) is not read here yet
        )

    # --- one step -------------------------------------------------------------------------------------------------
    def step(self, now: datetime) -> Decision:
        inputs = self.build_inputs(now)
        self.last_inputs = inputs
        decision = self.sup.step(inputs)
        self.last = decision
        if self.last_save is None or now - self.last_save >= SAVE_EVERY:
            self.last_save = now
            try:
                self.save()
            except OSError as exc:
                _LOGGER.warning("state not saved: %s", exc)
        return decision

    def mirror_target(self, preset: str | None, manual_target: float | None, now: datetime) -> bool:
        """Shadow mode: take over a preset / manual target set by hand in Home Assistant. True when it changed."""
        sup = self.sup
        preset = None if preset in (None, "auto", "none") else preset
        changed = False
        if preset != sup.preset and preset != "boost":
            sup.set_preset(preset, now)
            changed = True
        if manual_target != sup.manual_target:
            sup.manual_target = manual_target
            changed = True
        return changed

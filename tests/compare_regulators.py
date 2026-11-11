"""Closed-loop comparison of the TPI and PID regulators (0.41.0): both run the same simulated house (tests/sim.py)
through the same scenarios, each switching the burner itself – unlike the shadow regulator, which only computes
next to the live one. The room sensor reports in 0.1 °C steps, as real ones do. Boost and learning are off, so the
regulators themselves are compared.

Run:  python tests/compare_regulators.py  (prints a Markdown table)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "hc_thermostat"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.model import HcConfig, Inputs, Reading  # noqa: E402
from core.supervisor import Supervisor  # noqa: E402
from sim import START, STEP_S, House  # noqa: E402

BASE = dict(night_start="00:00", night_end="00:00", season_enabled=False, boost_enabled=False,
            learning_enabled=False, cycle_s=900, min_on_s=300, min_off_s=300)
REGULATORS = {
    "TPI": dict(control="tpi"),
    "PID (alap)": dict(control="pid"),
    "PID (Cirkó: Kp 0,5, Ki 0,2/h)": dict(control="pid", pid_kp=0.5, pid_ki_per_hour=0.2),
}


@dataclass
class Result:
    mean_abs: float
    max_over: float
    max_under: float
    burn_min_day: float
    starts_day: float
    reach_min: float | None = None


def simulate(reg: dict, outdoor: float, hours: float, start_indoor: float, target: float,
             window_at_h: float | None = None, measure_from_h: float = 0.0) -> Result:
    cfg = HcConfig.from_mapping({**BASE, **reg, "target_home": target})
    sup, house = Supervisor(cfg), House(indoor=start_indoor, outdoor=outdoor)
    now, last_report, shown, age = START, None, None, 0.0
    errs, burn_s, starts, prev, reach = [], 0.0, 0, False, None
    steps = int(hours * 3600 / STEP_S)
    for i in range(steps):
        t_h = i * STEP_S / 3600
        house.window_open = window_at_h is not None and window_at_h <= t_h < window_at_h + 0.5
        q = round(house.indoor, 1)  # the sensor's 0.1 °C step, reported on a change
        if shown is None or q != shown:
            shown, age = q, 0.0
        else:
            age += STEP_S
        d = sup.step(Inputs(now=now, indoor=Reading(shown, min(age, 600.0)), outdoor=Reading(outdoor, 0.0),
                            window_open=house.window_open))
        house.advance(d.output)
        if reach is None and house.indoor >= target - 0.2:
            reach = i * STEP_S / 60
        if t_h >= measure_from_h:
            errs.append(house.indoor - target)
            if d.output:
                burn_s += STEP_S
            if d.output and not prev:
                starts += 1
        prev = d.output
        now += timedelta(seconds=STEP_S)
    days = (hours - measure_from_h) / 24
    return Result(sum(abs(e) for e in errs) / len(errs), max(errs), -min(errs), burn_s / 60 / days, starts / days, reach)


SCENARIOS = [
    ("Tartás, kint −10 °C", dict(outdoor=-10.0, hours=48, start_indoor=21.0, target=21.0, measure_from_h=24)),
    ("Tartás, kint 0 °C", dict(outdoor=0.0, hours=48, start_indoor=21.0, target=21.0, measure_from_h=24)),
    ("Tartás, kint +10 °C", dict(outdoor=10.0, hours=48, start_indoor=21.0, target=21.0, measure_from_h=24)),
    ("Felfűtés 19 → 21 °C, kint 0 °C", dict(outdoor=0.0, hours=12, start_indoor=19.0, target=21.0)),
    ("Ablaknyitás 30 percre, kint 0 °C", dict(outdoor=0.0, hours=48, start_indoor=21.0, target=21.0,
                                              window_at_h=30.0, measure_from_h=24)),
]


def table() -> str:
    rows = ["| Helyzet | Szabályozó | Átl. eltérés °C | Max. fölötte °C | Max. alatta °C | Égés perc/nap | Indítás/nap | Célig perc |",
            "|---|---|---|---|---|---|---|---|"]
    for name, sc in SCENARIOS:
        for reg_name, reg in REGULATORS.items():
            r = simulate(reg, **sc)
            reach = "–" if r.reach_min is None or sc["start_indoor"] >= sc["target"] else f"{r.reach_min:.0f}"
            rows.append(f"| {name} | {reg_name} | {r.mean_abs:.2f} | {r.max_over:.2f} | {r.max_under:.2f} | "
                        f"{r.burn_min_day:.0f} | {r.starts_day:.0f} | {reach} |")
    return "\n".join(rows)


if __name__ == "__main__":
    print(table())

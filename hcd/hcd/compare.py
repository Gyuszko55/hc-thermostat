"""Shadow comparison: hcd's decision beside the Home Assistant integration's, every step, kept in SQLite."""

from __future__ import annotations

from datetime import datetime, timedelta
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
create table if not exists steps (
  ts text primary key,          -- UTC ISO
  day text,                     -- local date
  hcd_reason text, hcd_output integer, hcd_demand real, hcd_target real, hcd_indoor real,
  ha_reason text, ha_relay integer, ha_demand real, ha_target real, ha_indoor real
);
create index if not exists steps_day on steps(day);
"""


def _num(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ha_side(states: dict[str, dict[str, Any]], compare: dict[str, str]) -> dict[str, Any]:
    """The integration's decision, target, demand and relay from Home Assistant's states."""
    dec = states.get(compare.get("decision") or "") or {}
    cli = states.get(compare.get("climate") or "") or {}
    rel = states.get(compare.get("relay") or "") or {}
    a = cli.get("attributes") or {}
    relay = rel.get("state")
    return {
        "reason": dec.get("state"),
        "relay": None if relay not in ("on", "off") else int(relay == "on"),
        "demand": _num(a.get("demand")),
        "target": _num(a.get("temperature")),
        "indoor": _num(a.get("current_temperature")),
        "preset": a.get("preset_mode"),
        "manual_target": _num(a.get("manual_target")),
    }


class Comparison:
    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)

    def record(self, now_utc: datetime, day: str, decision: Any, ha: dict[str, Any]) -> None:
        self.db.execute(
            "insert or replace into steps values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (now_utc.isoformat(timespec="seconds"), day, getattr(decision.reason, "value", str(decision.reason)),
             int(bool(decision.output)), round(100.0 * float(decision.demand or 0.0), 1), _num(decision.target),
             _num(decision.indoor),
             ha.get("reason"), ha.get("relay"), ha.get("demand"), ha.get("target"), ha.get("indoor")))
        self.db.commit()

    def prune(self, now_utc: datetime, keep_days: int = 30) -> None:
        self.db.execute("delete from steps where ts < ?", ((now_utc - timedelta(days=keep_days)).isoformat(),))
        self.db.commit()

    def day_summary(self, day: str, step_s: float) -> dict[str, Any]:
        """One day: steps, how often the reason and the output agree, and the burn minutes of each side."""
        rows = self.db.execute(
            "select hcd_reason, hcd_output, ha_reason, ha_relay, hcd_target, ha_target from steps where day = ?",
            (day,)).fetchall()
        n = len(rows)
        if not n:
            return {"day": day, "steps": 0}
        both = [r for r in rows if r[2] is not None]
        relay_known = [r for r in rows if r[3] is not None]
        minutes = step_s / 60.0
        hcd_min = sum(r[1] for r in rows) * minutes
        ha_min = sum(r[3] for r in relay_known) * minutes
        return {
            "day": day,
            "steps": n,
            "reason_agree_pct": round(100.0 * sum(r[0] == r[2] for r in both) / len(both), 1) if both else None,
            "output_agree_pct": round(100.0 * sum(r[1] == r[3] for r in relay_known) / len(relay_known), 1)
            if relay_known else None,
            "target_agree_pct": round(100.0 * sum(r[4] is not None and r[5] is not None and abs(r[4] - r[5]) < 0.05
                                                  for r in rows) / n, 1),
            "hcd_burn_min": round(hcd_min, 1),
            "ha_burn_min": round(ha_min, 1),
            "burn_diff_pct": round(100.0 * (hcd_min - ha_min) / ha_min, 1) if ha_min else None,
        }

    def recent(self, limit: int = 60) -> list[dict[str, Any]]:
        cur = self.db.execute("select * from steps order by ts desc limit ?", (limit,))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def disagreements(self, day: str, limit: int = 50) -> list[dict[str, Any]]:
        cur = self.db.execute("select * from steps where day = ? and (hcd_reason != ha_reason or hcd_output != ha_relay)"
                              " order by ts desc limit ?", (day, limit))
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

"""0.89.0: recommendations for laymen – nothing is ever written by itself.

- `profile()` (0.89.0): the settings that differ from what HC recommends for this heat source and system
  (core/matrix.py default_timing / source_defaults, HcConfig). A safety value is only ever recommended in the
  stricter direction.
- `goal_changes()` (0.89.0): goals instead of parameters – "fewer switching", "steadier", "thriftier",
  "as recommended"; which settings change and what to expect from the last days' numbers (a rough estimate).
- `advise()` (0.89.0): advice from the last days' recorder numbers (starts, short runs, cold and overheated hours,
  a thermometer going quiet); each says which number it comes from and where to change it.

Every adoption goes through the settings' "what changes" page (0.88.0) and can be restored.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .matrix import default_timing, electric_floor, source_defaults
from .model import HcConfig

_D = {f: getattr(HcConfig, f) for f in HcConfig.__dataclass_fields__ if hasattr(HcConfig, f)}

TIMING = ("cycle_s", "min_on_s", "min_off_s")
HP_TIMING = {"hp_min_on_s": 1200.0, "hp_min_off_s": 600.0}
SOURCE_KEYS = ("frozen_band", "frozen_after_h", "pre_change_s", "catchup_after_s")
GOALS = ("fewer_switching", "steadier", "thriftier", "recommended")
_FLOOR_TOP = {"electric": 27.0, "water": 29.0}


@dataclass
class Rec:
    key: str
    current: Any
    recommended: Any
    reason: str  # an id of REASONS
    safety: bool = False
    args: dict = field(default_factory=dict)


def effective(conf: Mapping[str, Any]) -> dict[str, Any]:
    """The value of every setting as the instance runs with it: its own, else the heat source's, else HC's."""
    sd = source_defaults(conf.get("system"), conf.get("heat_source"))
    out = dict(_D)
    out.update(sd)
    out.update({k: v for k, v in conf.items() if v is not None})
    return out


def _pwm(conf: Mapping[str, Any]) -> bool:
    return (conf.get("control") or "tpi") in ("tpi", "pid")


def _differs(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) > 1e-6
    except (TypeError, ValueError):
        return a != b


def profile(conf: Mapping[str, Any], both: bool = False) -> list[Rec]:
    """Live 0.89.0: a cycle, run or pause longer than recommended is a choice (fewer switching – the goal of that
    name sets it), so only the shorter side is recommended; `both` (the "as recommended" goal) brings back both."""
    system, source = conf.get("system") or "", conf.get("heat_source")
    eff = effective(conf)
    out: list[Rec] = []
    if _pwm(conf):
        rec = default_timing(system, source)
        for k in TIMING:
            if _differs(eff.get(k), rec[k]) and (both or float(eff.get(k) or 0) < rec[k]):
                out.append(Rec(k, eff.get(k), rec[k], "timing_" + ("longer" if float(eff.get(k) or 0) < rec[k] else "shorter")))
    if eff.get("heat_pump") and (conf.get("control") or "tpi") in ("curve", "onoff"):
        for k, v in HP_TIMING.items():
            if eff.get(k) is not None and float(eff[k]) < v:
                out.append(Rec(k, eff[k], v, "hp_short"))
    sd = source_defaults(system or None, source)
    for k in SOURCE_KEYS:
        if k in sd and _differs(eff.get(k), sd[k]):
            out.append(Rec(k, eff.get(k), sd[k], "floor_slow"))
    # safety values: only ever the stricter direction
    if eff.get("frost_temp") is not None and float(eff["frost_temp"]) < 5.0:
        out.append(Rec("frost_temp", eff["frost_temp"], 7.0, "frost_low", safety=True))
    if "floor_max" in sd:  # a floor system (core/matrix.py source_defaults)
        top = _FLOOR_TOP["electric" if electric_floor(system, source) else "water"]
        cur = float(eff.get("floor_max") or 0.0)
        if cur > top:
            out.append(Rec("floor_max", cur, top, "floor_high", safety=True))
    if "sensor_lost_demand" in sd and float(eff.get("sensor_lost_demand") or 0) > float(sd["sensor_lost_demand"]):
        out.append(Rec("sensor_lost_demand", eff["sensor_lost_demand"], sd["sensor_lost_demand"], "blind_electric", safety=True))
    if "guard_max_on_s" in sd and (not eff.get("guard_max_on_s") or float(eff["guard_max_on_s"]) > float(sd["guard_max_on_s"])):
        out.append(Rec("guard_max_on_s", eff.get("guard_max_on_s") or 0, sd["guard_max_on_s"], "guard_long", safety=True))
    return out


# --- 0.89.0 goals -------------------------------------------------------------------------------------------------

def _round5(seconds: float, up: bool = False) -> float:
    """Whole 5 minutes (whole minutes under 5); `up` rounds up (a longer cycle must really be longer)."""
    step = 300.0 if seconds >= 300 else 60.0
    n = -(-seconds // step) if up else round(seconds / step)
    return float(max(step, n * step))


def goal_changes(goal: str, conf: Mapping[str, Any]) -> dict[str, Any]:
    """The settings a goal changes (new values only where they differ); the targets are never touched."""
    eff = effective(conf)
    system, source = conf.get("system") or "", conf.get("heat_source")
    out: dict[str, Any] = {}
    if goal == "recommended":
        return {r.key: r.recommended for r in profile(conf, both=True)}
    if goal in ("fewer_switching", "steadier") and _pwm(conf):
        rec = default_timing(system, source)
        floor = "catchup_after_s" in source_defaults(system or None, source)
        cap = 7200.0 if floor else 3600.0
        if goal == "fewer_switching":
            want = {"cycle_s": min(cap, _round5(float(eff["cycle_s"]) * 1.5, up=True)),
                    "min_on_s": _round5(max(float(eff["min_on_s"]) * 1.5, rec["min_on_s"]), up=True),
                    "min_off_s": _round5(max(float(eff["min_off_s"]) * 1.5, rec["min_off_s"]), up=True)}
        else:  # shorter cycles, never under half of the recommended (core/readiness.setting_risks)
            want = {"cycle_s": _round5(max(float(eff["cycle_s"]) / 1.5, rec["cycle_s"] * 0.6, 600.0 if not floor else 1800.0)),
                    "min_on_s": _round5(max(float(eff["min_on_s"]) / 1.5, rec["min_on_s"] * 0.6, 120.0)),
                    "min_off_s": _round5(max(float(eff["min_off_s"]) / 1.5, rec["min_off_s"] * 0.6, 120.0))}
        out.update({k: v for k, v in want.items() if _differs(eff.get(k), v)})
    if goal == "thriftier":
        want = {"pre_change_s": max(float(eff.get("pre_change_s") or 0), 3600.0),
                "coast_window_s": max(float(eff.get("coast_window_s") or 0), 2700.0)}
        out.update({k: v for k, v in want.items() if _differs(eff.get(k), v)})
    return out


def expect(goal: str, changes: Mapping[str, Any], conf: Mapping[str, Any], stats: Mapping[str, Any] | None) -> dict:
    """A rough estimate from the last days: starts a day scale with 1 / cycle, the room's swing with √cycle."""
    eff = effective(conf)
    out: dict[str, Any] = {}
    if not stats:
        return out
    starts, dev = stats.get("starts_day"), stats.get("dev_c")
    if "cycle_s" in changes and eff.get("cycle_s"):
        ratio = float(changes["cycle_s"]) / float(eff["cycle_s"])
        if starts is not None:
            out["starts"] = (round(starts), round(starts / ratio))
        if dev is not None:
            out["dev"] = (round(dev, 1), round(dev * ratio ** 0.5, 1))
    if goal == "thriftier" and stats.get("overheated_h_day") is not None:
        out["overheated"] = round(stats["overheated_h_day"], 1)
    return out


# --- 0.89.0 advice ------------------------------------------------------------------------------------------------

def advise(stats: Mapping[str, Any] | None, conf: Mapping[str, Any]) -> list[dict]:
    """Advice from the last days' numbers. `stats`: days, starts_day, short_runs_pct, cold_h_day, overheated_h_day,
    quiet_gaps (the indoor thermometer unavailable for over half an hour), longest_gap_h. Fewer than 2 days: no advice yet."""
    if not stats or (stats.get("days") or 0) < 2:
        return []
    eff = effective(conf)
    pwm = _pwm(conf)
    out = []
    if (conf.get("mode") or "shadow") != "active":
        # shadow mode: HC switches nothing, the starts and the room's warmth are not its doing – only the thermometer
        gaps = stats.get("quiet_gaps")
        return [{"id": "sensor_quiet", "args": {"gaps": int(gaps), "hours": round(stats.get("longest_gap_h") or 0, 1)},
                 "step": "sensors"}] if gaps else []
    starts, short = stats.get("starts_day"), stats.get("short_runs_pct")
    if pwm and starts is not None and starts > 24 and (short or 0) >= 50:
        out.append({"id": "many_short", "args": {"starts": round(starts), "short": round(short or 0),
                                                 "min_on": int(eff["min_on_s"] // 60)}, "goal": "fewer_switching"})
    cold = stats.get("cold_h_day")
    if cold is not None and cold > 2.0:
        out.append({"id": "often_cold", "args": {"hours": round(cold, 1)},
                    "step": "settings" if pwm else "check"})
    hot = stats.get("overheated_h_day")
    if hot is not None and hot > 2.0:
        out.append({"id": "often_hot", "args": {"hours": round(hot, 1)}, "goal": "thriftier"})
    gaps = stats.get("quiet_gaps")
    if gaps:
        out.append({"id": "sensor_quiet", "args": {"gaps": int(gaps), "hours": round(stats.get("longest_gap_h") or 0, 1)},
                    "step": "sensors"})
    return out


REASONS = {
    "hu": {
        "timing_longer": "rövidebb a javasoltnál – több kapcsolás, a kazán/relé többet indul",
        "timing_shorter": "hosszabb a javasoltnál – lassabban reagál, nagyobb ingadozás",
        "hp_short": "a hőszivattyúnak ennél hosszabb menet kell (kompresszorkímélés)",
        "floor_slow": "a padló lassan reagál – a HC padlós alapértéke",
        "frost_low": "5 °C alatt fagyhatnak a csövek – szigorúbb érték",
        "floor_high": "a padló felülete ennél melegebb ne legyen – szigorúbb érték",
        "blind_electric": "elektromos fűtés mérés nélkül ne fűtsön vakon – szigorúbb érték",
        "guard_long": "elektromos fűtésnél a helyi védő állítsa le a túl hosszú menetet – szigorúbb érték",
    },
    "en": {
        "timing_longer": "shorter than recommended – more switching, more boiler / relay starts",
        "timing_shorter": "longer than recommended – reacts slower, larger swings",
        "hp_short": "a heat pump needs longer runs (spares the compressor)",
        "floor_slow": "a floor answers slowly – HC's floor default",
        "frost_low": "below 5 °C pipes may freeze – stricter value",
        "floor_high": "the floor surface should not get warmer – stricter value",
        "blind_electric": "electric heating should not heat blind without a reading – stricter value",
        "guard_long": "with electric heating the local guard should stop an overlong run – stricter value",
    },
}

GOAL_WORDS = {
    "hu": {"fewer_switching": "Kevesebb kapcsolás (kíméli a kazánt és a relét)",
           "steadier": "Egyenletesebb hőmérséklet",
           "thriftier": "Takarékosabb (kevesebb túlfűtés)",
           "recommended": "Vissza a rendszerhez ajánlotthoz"},
    "en": {"fewer_switching": "Fewer switching (spares the boiler and the relay)",
           "steadier": "Steadier temperature",
           "thriftier": "Thriftier (less overheating)",
           "recommended": "Back to what is recommended for the system"},
}

ADVICE = {
    "hu": {
        "many_short": "Sok rövid menet: naponta kb. {starts} indítás, ezek {short} %-a {min_on} percnél alig hosszabb. "
                      "Javaslat: „Mire törekedjen a fűtés?” → Kevesebb kapcsolás.",
        "often_cold": "Gyakran a cél alatt: naponta átlagosan {hours} órát volt 0,3 °C-nál hidegebb a célnál. "
                      "Nézd meg a kazán gombját / a radiátorokat, majd a Szakértői beállításokban a szabályozás erősségét "
                      "és az optimális indítást.",
        "often_hot": "Gyakran túlfűt: naponta átlagosan {hours} órát volt 0,5 °C-nál melegebb a célnál. "
                     "Javaslat: „Mire törekedjen a fűtés?” → Takarékosabb.",
        "sensor_quiet": "A benti hőmérő {gaps} alkalommal elérhetetlen volt fél óránál tovább (a leghosszabb {hours} óra). "
                        "Nézd meg az elemet és a vételt; a Hőmérők és ablakok pontban másik hőmérő is választható.",
        "none": "Az elmúlt napok adatai alapján nincs teendő.",
        "shadow": "Árnyék módban a HC nem kapcsol, ezért a menetekről és a hőmérsékletről még nem ad tanácsot.",
        "few": "Még kevés az adat a tanácsokhoz (legalább 2 nap kell).",
    },
    "en": {
        "many_short": "Many short runs: about {starts} starts a day, {short} % of them barely longer than {min_on} minutes. "
                      "Suggestion: \"What should the heating aim for?\" → Fewer switching.",
        "often_cold": "Often below the target: on average {hours} hours a day more than 0.3 °C under it. Check the "
                      "boiler's dial / the radiators, then the regulation strength and the optimal start in the expert settings.",
        "often_hot": "Often overheating: on average {hours} hours a day more than 0.5 °C above the target. "
                     "Suggestion: \"What should the heating aim for?\" → Thriftier.",
        "sensor_quiet": "The indoor thermometer was unavailable {gaps} times for over half an hour (the longest {hours} hours). Check its "
                        "battery and reception; another thermometer can be chosen under Thermometers and windows.",
        "none": "Nothing to do from the last days' numbers.",
        "shadow": "In shadow mode HC switches nothing, so it gives no advice on the runs and the warmth yet.",
        "few": "Too few numbers for advice yet (at least 2 days are needed).",
    },
}


def advice_text(items: list[dict], language: str = "en", days: float | None = None, shadow: bool = False) -> str:
    w = ADVICE["hu" if language == "hu" else "en"]
    if days is not None and days < 2:
        return w["few"]
    if not items:
        return w["shadow"] if shadow else w["none"]
    hu = language == "hu"

    def num(v):
        return f"{v:g}".replace(".", ",") if hu and isinstance(v, float) else v
    return "\n".join(f"- {w[i['id']].format(**{k: num(v) for k, v in i['args'].items()})}" for i in items)

"""Floor heating helpers: the floor temperature limit by covering and probe position (0.37.0), and the floor
tempering offset (0.35.0).

The limits below are starting points, not a design: EN 1264 allows 29 °C at the floor surface in occupied zones;
wood and laminate makers ask for about 27 °C at the surface. A probe deeper in the screed (between the pipes, or
right above a supply pipe) reads warmer than the surface, so its limit is higher – the values come from field
experience. The user can always override them with `floor_max`. An electric floor always uses the surface column
(its mat or cable lies right under the covering).
"""

from __future__ import annotations

COVERINGS = ("tiles", "laminate", "wood", "vinyl", "carpet")
PROBES = ("surface", "screed", "above_pipe")

FLOOR_LIMITS: dict[str, dict[str, float]] = {
    # surface: in the adhesive / directly under the covering
    "surface": {"tiles": 29.0, "laminate": 27.0, "wood": 27.0, "vinyl": 27.0, "carpet": 27.0},
    # screed: in the screed between the pipes
    "screed": {"tiles": 29.0, "laminate": 33.0, "wood": 33.0, "vinyl": 31.0, "carpet": 33.0},
    # above_pipe: right above a supply pipe
    "above_pipe": {"tiles": 36.0, "laminate": 36.0, "wood": 36.0, "vinyl": 36.0, "carpet": 36.0},
}
ELECTRIC_LIMIT = 27.0  # an electric floor without a covering given
WATER_LIMIT = 29.0  # a water floor without a covering given: the EN 1264 surface limit (as before 0.37.0)

TILES_TEMPER_OFFSET = 2.0  # tiles conduct well: a small offset is felt
OTHER_TEMPER_OFFSET = 3.0  # wood, laminate, vinyl, carpet insulate: the floor below must be warmer
DEFAULT_TEMPER_OFFSET = 2.0  # no covering given


def covering_of(covering: str | None) -> str:
    """The covering, or "" when none is given ("none" from a form counts as none)."""
    return covering if covering in COVERINGS else ""


def floor_limit(floor_max: float, covering: str | None, probe: str | None, electric: bool) -> tuple[float, str]:
    """The floor limit in effect and where it comes from: "manual" (floor_max), "covering" (the table), "electric"
    (an electric floor without a covering) or "water" (a water floor without a covering): 0 never means "no limit"
    – an old instance that never stored a limit kept 29 / 27 °C, and saving its options (now 0) must not drop it."""
    if floor_max and floor_max > 0:
        return float(floor_max), "manual"
    cover = covering_of(covering)
    if cover:
        column = "surface" if electric or probe not in PROBES else probe
        return FLOOR_LIMITS[column][cover], "covering"
    if electric:
        return ELECTRIC_LIMIT, "electric"
    return WATER_LIMIT, "water"


def temper_offset(offset: float, covering: str | None = None) -> float:
    """The tempering offset in effect: the user's value, or by the covering when it is 0."""
    if offset and offset > 0:
        return float(offset)
    cover = covering_of(covering)
    if not cover:
        return DEFAULT_TEMPER_OFFSET
    return TILES_TEMPER_OFFSET if cover == "tiles" else OTHER_TEMPER_OFFSET

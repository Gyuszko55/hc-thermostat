"""An adjoining room with its own heating, for example a terrace behind a door.

It is part of the house only while the door is open and it is about as warm as
inside. Then its heat helps the house. Closed, its heat does not count. Open while
it is cold, the door acts like an open window.
"""

from __future__ import annotations


def coupled(door_open: bool, indoor: float | None, zone_temp: float | None, max_diff: float) -> bool:
    if not door_open or indoor is None or zone_temp is None:
        return False
    return indoor - zone_temp <= max_diff

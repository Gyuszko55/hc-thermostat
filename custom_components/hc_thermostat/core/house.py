"""0.53.0 – one house, several heat sources: which HC instances the info panel draws as one house.

Every HC instance runs on its own (its own source, thermometer and decisions); this only says which ones belong to the
same building, so the info panel shows one house with every room and every source in it instead of a one-room house
per instance. Nothing here switches anything.

Rules, in this order:
1. `house_link` = "own": the instance is a house of its own (it may still be the host of others).
2. `house_link` = an entry id: the instance belongs to that instance's house (if that one is loaded).
3. The same non-empty home name (`home_name`, case-insensitive): one house. Its host is the member with the most rooms.
4. Automatic (`house_link` "auto", the default): a one-room instance (an air conditioner, an oil radiator, a heater…)
   whose room's area is a room or the separate zone of another instance with more rooms belongs to that house – unless
   it is that instance's leading room: two instances led from the same room are alternatives (a shadow trial of the
   same boiler), not two parts of one house.
5. A central boiler / a buffer tank belongs to the house most of its zones belong to.

A chain resolves to its end (A → B → C: A is in C's house); a loop is cut (both stay their own).
"""

from __future__ import annotations

from dataclasses import dataclass, field

AUTO, OWN = "auto", "own"


@dataclass(frozen=True)
class Facts:
    entry_id: str
    title: str = ""
    role: str = "standalone"
    link: str = AUTO  # auto | own | <entry id>
    home_name: str = ""
    rooms: tuple[tuple[str, str | None], ...] = ()  # (room key, area id)
    leading_area: str | None = None
    zone_area: str | None = None  # the separate zone (terrace behind a door) the instance draws
    zone_entries: tuple[str, ...] = ()  # central / buffer: the entry ids of its zones

    @property
    def room_areas(self) -> set[str]:
        return {a for _, a in self.rooms if a}

    @property
    def size(self) -> int:
        return len(self.rooms) + (1 if self.zone_area else 0)


@dataclass
class Link:
    host: str  # the entry id of the house's host (itself for a host or a house of its own)
    area: str | None = None  # the member's area in the host's house
    room: str | None = None  # the host's room key in that area (None: a room the host does not list)
    why: str = ""  # own | named | home_name | area | zones
    members: list[str] = field(default_factory=list)  # for a host: its members, in the given order


def _norm(text: str | None) -> str:
    return " ".join(str(text or "").split()).casefold()


def houses(facts: list[Facts]) -> dict[str, Link]:
    """entry id -> Link for every instance given (order matters only for ties)."""
    by_id = {f.entry_id: f for f in facts}
    order = {f.entry_id: i for i, f in enumerate(facts)}
    parent: dict[str, tuple[str, str]] = {}  # member -> (host, why)

    def bigger(a: str, b: str) -> str:
        fa, fb = by_id[a], by_id[b]
        return a if (fa.size, -order[a]) >= (fb.size, -order[b]) else b

    # 2. named
    for f in facts:
        if f.link not in (AUTO, OWN, "", None) and f.link in by_id and f.link != f.entry_id:
            parent[f.entry_id] = (f.link, "named")
    # 3. home name
    groups: dict[str, list[str]] = {}
    for f in facts:
        if f.link == OWN or f.entry_id in parent or not _norm(f.home_name):
            continue
        groups.setdefault(_norm(f.home_name), []).append(f.entry_id)
    for ids in groups.values():
        if len(ids) < 2:
            continue
        host = ids[0]
        for i in ids[1:]:
            host = bigger(host, i)
        for i in ids:
            if i != host:
                parent[i] = (host, "home_name")
    # 4. automatic by area
    for f in facts:
        if f.link != AUTO or f.entry_id in parent or f.role not in ("standalone", "zone") or len(f.rooms) > 1:
            continue
        area = f.leading_area or (f.rooms[0][1] if f.rooms else None)
        if not area:
            continue
        best = None
        for h in facts:
            if h.entry_id == f.entry_id or h.size < 2 or area == h.leading_area:
                continue
            if area in h.room_areas or area == h.zone_area:
                best = h.entry_id if best is None else bigger(best, h.entry_id)
        if best is not None:
            parent[f.entry_id] = (best, "area")
    # 5. central / buffer: where most of its zones are
    for f in facts:
        if f.link != AUTO or f.entry_id in parent or not f.zone_entries:
            continue
        votes: dict[str, int] = {}
        for z in f.zone_entries:
            if z in by_id:
                h = _resolve(z, parent)
                if h != f.entry_id:
                    votes[h] = votes.get(h, 0) + 1
        if votes:
            parent[f.entry_id] = (max(votes, key=lambda h: (votes[h], -order[h])), "zones")

    out: dict[str, Link] = {}
    for f in facts:
        host = _resolve(f.entry_id, parent)
        if host == f.entry_id:
            out[f.entry_id] = Link(host=f.entry_id, why=OWN)
            continue
        area = f.leading_area or (f.rooms[0][1] if f.rooms else None)
        h = by_id[host]
        room = next((k for k, a in h.rooms if a and a == area), None)
        out[f.entry_id] = Link(host=host, area=area, room=room, why=parent[f.entry_id][1])
    for f in facts:
        link = out[f.entry_id]
        if link.host != f.entry_id:
            out[link.host].members.append(f.entry_id)
    return out


def _resolve(entry_id: str, parent: dict[str, tuple[str, str]]) -> str:
    """The end of the chain; a loop leaves the instance on its own."""
    seen = {entry_id}
    cur = entry_id
    while cur in parent:
        nxt = parent[cur][0]
        if nxt in seen:
            return entry_id
        seen.add(nxt)
        cur = nxt
    return cur

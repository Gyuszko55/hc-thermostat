"""0.78.0: what a body of HC provides to the decision core.

The Home Assistant integration and the standalone service each implement these; the core never imports either.
Only `StateView` is used by the core itself today (see `inputs.py`); the rest describe the contract the standalone
service is built against, so the two bodies stay alike.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .inputs import StateView  # noqa: F401  (re-exported: the source of samples)


class Clock(Protocol):
    """Now, timezone-aware (UTC); the local time zone is the body's own business."""

    def now(self) -> datetime: ...


class Output(Protocol):
    """The heat output: a relay or a guard lease. `set` returns True when the command was taken."""

    async def set(self, on: bool, *, reason: str = "") -> bool: ...


class StateStore(Protocol):
    """Saves and restores an instance's own state (the same dict the Home Assistant store keeps)."""

    async def load(self) -> dict[str, Any] | None: ...

    async def save(self, data: dict[str, Any]) -> None: ...


class Notifier(Protocol):
    """A message to the people of the house (a phone push, an ntfy topic)."""

    async def send(self, title: str, message: str, *, tag: str | None = None) -> None: ...

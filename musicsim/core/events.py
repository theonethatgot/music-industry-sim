"""Append-only event log with provenance links (causes) and logged random draws."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Event:
    id: int
    date: str
    system: str
    type: str
    entities: list[str]
    data: dict
    causes: list[int] = field(default_factory=list)
    draws: list[dict] = field(default_factory=list)
    public: bool = True

    def to_row(self) -> dict:
        return self.__dict__.copy()


class EventLog:
    """Holds events not yet flushed to disk; ids are global and monotonic."""

    def __init__(self, next_id: int = 1):
        self.next_id = next_id
        self.watch: set | None = None          # optional entities whose event types are tallied (QA tooling)
        self.tally: dict[str, int] = {}
        self.pending: list[Event] = []
        # small in-memory index of recent events (for digests); rebuilt from disk on load
        self.recent: list[Event] = []

    def emit(self, date, system: str, type_: str, entities=(), data=None, causes=(),
             draws=None, public: bool = True) -> int:
        ev = Event(
            id=self.next_id,
            date=str(date),
            system=system,
            type=type_,
            entities=list(entities),
            data=data or {},
            causes=list(causes),
            draws=list(draws or []),
            public=public,
        )
        self.next_id += 1
        if self.watch and self.watch.intersection(ev.entities):
            self.tally[type_] = self.tally.get(type_, 0) + 1
        self.pending.append(ev)
        self.recent.append(ev)
        if len(self.recent) > 4000:
            self.recent = self.recent[-3000:]
        return ev.id

    def drain(self) -> list[Event]:
        out, self.pending = self.pending, []
        return out

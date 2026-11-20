"""Physical condition: how much of their ability a tired person brings to a performance."""
from __future__ import annotations


def fitness(world, pid: str | None) -> float:
    p = world.people.get(pid) if pid else None
    if p is None:
        return 1.0
    e = p.wellbeing.get("energy", 0.8)
    return float(0.75 + 0.25 * min(1.0, e / 0.5))

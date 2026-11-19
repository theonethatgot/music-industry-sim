"""Deterministic, hash-derived random streams.

Every draw is a pure function of (seed, key parts). Adding a new entity or system
never shifts any other outcome, and nothing needs to be stored to continue a run.
"""
from __future__ import annotations

import hashlib
import math
import struct
from typing import Sequence

import numpy as np

_TWO_64 = float(2**64)


def _digest(seed: int, parts: Sequence[object]) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    h.update(str(seed).encode())
    for p in parts:
        h.update(b"\x1f")
        h.update(str(p).encode())
    return h.digest()


def uniform(seed: int, *parts: object) -> float:
    """U[0,1) from the key."""
    a, _ = struct.unpack("<QQ", _digest(seed, parts))
    return a / _TWO_64


def normal(seed: int, *parts: object) -> float:
    """Standard normal via Box-Muller on two independent 64-bit halves."""
    a, b = struct.unpack("<QQ", _digest(seed, parts))
    u1 = (a + 1) / (_TWO_64 + 1)
    u2 = b / _TWO_64
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2)


def student_t(seed: int, df: float, *parts: object) -> float:
    """Fat-tailed shock: t-distribution built from deterministic normals."""
    z = normal(seed, *parts, "z")
    k = max(1, int(round(df)))
    chi2 = sum(normal(seed, *parts, "c", i) ** 2 for i in range(k))
    return z / math.sqrt(chi2 / k)


def chance(seed: int, p: float, *parts: object) -> bool:
    return uniform(seed, *parts) < p


def choice(seed: int, options: Sequence, *parts: object):
    if not options:
        raise ValueError("choice from empty sequence")
    return options[int(uniform(seed, *parts) * len(options))]


def weighted_choice(seed: int, options: Sequence, weights: Sequence[float], *parts: object):
    total = float(sum(weights))
    if total <= 0:
        return choice(seed, options, *parts)
    r = uniform(seed, *parts) * total
    acc = 0.0
    for o, w in zip(options, weights):
        acc += w
        if r < acc:
            return o
    return options[-1]


def normal_array(seed: int, n: int, *parts: object) -> np.ndarray:
    """Vector of independent normals (one numpy Generator seeded from the key)."""
    a, b = struct.unpack("<QQ", _digest(seed, parts))
    gen = np.random.Generator(np.random.PCG64([a, b]))
    return gen.standard_normal(n)


class Draws:
    """Collects draws made while resolving one event so they can be logged."""

    def __init__(self, seed: int, *prefix: object):
        self.seed = seed
        self.prefix = prefix
        self.log: list[dict] = []

    def _key(self, parts):
        return (*self.prefix, *parts)

    def uniform(self, label: str, *parts) -> float:
        v = uniform(self.seed, *self._key((label, *parts)))
        self.log.append({"draw": label, "kind": "uniform", "value": round(v, 6)})
        return v

    def normal(self, label: str, *parts) -> float:
        v = normal(self.seed, *self._key((label, *parts)))
        self.log.append({"draw": label, "kind": "normal", "value": round(v, 6)})
        return v

    def student_t(self, label: str, df: float, *parts) -> float:
        v = student_t(self.seed, df, *self._key((label, *parts)))
        self.log.append({"draw": label, "kind": f"t{df:g}", "value": round(v, 6)})
        return v

    def chance(self, label: str, p: float, *parts) -> bool:
        u = uniform(self.seed, *self._key((label, *parts)))
        ok = u < p
        self.log.append({"draw": label, "kind": "chance", "p": round(p, 4), "u": round(u, 6), "result": ok})
        return ok

"""Vectorised per-market listener state for songs and albums.

Each released recording occupies a row of a SongTable for every market where it is
available; each released album a row of an AlbumTable. Daily activity is kept in
ring buffers (one slot per day) long enough for any chart window.
"""
from __future__ import annotations

import numpy as np

BUFFER_DAYS = 35
CHANNELS = ["radio", "video", "tv", "fans", "word_of_mouth", "chart_visibility"]


class _Table:
    float_fields: dict = {}
    int_fields: dict = {}
    bool_fields: dict = {}

    def __init__(self, shapes: dict, capacity: int = 64):
        self.shapes = shapes          # name -> trailing shape tuple
        self.ids: list[str] = []
        self.index: dict[str, int] = {}
        self.n = 0
        self.cap = capacity
        self.arr: dict[str, np.ndarray] = {}
        for name, (shape, dtype) in shapes.items():
            self.arr[name] = np.zeros((capacity, *shape), dtype=dtype)

    def _grow(self):
        new_cap = self.cap * 2
        for name, a in self.arr.items():
            b = np.zeros((new_cap, *a.shape[1:]), dtype=a.dtype)
            b[: self.cap] = a
            self.arr[name] = b
        self.cap = new_cap

    def add(self, rid: str) -> int:
        if rid in self.index:
            return self.index[rid]
        if self.n >= self.cap:
            self._grow()
        i = self.n
        self.ids.append(rid)
        self.index[rid] = i
        self.n += 1
        return i

    def __getattr__(self, name):
        arr = self.__dict__.get("arr")
        if arr is not None and name in arr:
            return arr[name][: self.__dict__["n"]]
        raise AttributeError(name)

    def view(self, name):
        return self.arr[name][: self.n]

    # serialisation ------------------------------------------------------------
    def to_state(self, prefix: str) -> tuple[dict, dict]:
        meta = {"ids": self.ids, "n": self.n}
        arrays = {f"{prefix}.{k}": v[: self.n].copy() for k, v in self.arr.items()}
        return meta, arrays

    def load_state(self, prefix: str, meta: dict, arrays: dict):
        self.ids = list(meta["ids"])
        self.n = int(meta["n"])
        self.index = {r: i for i, r in enumerate(self.ids)}
        self.cap = max(64, self.n * 2)
        for name, (shape, dtype) in self.shapes.items():
            a = np.zeros((self.cap, *shape), dtype=dtype)
            src = arrays.get(f"{prefix}.{name}")
            if src is not None and self.n:
                a[: self.n] = src
            self.arr[name] = a


class SongTable(_Table):
    def __init__(self, G: int, F: int, V: int, D: int, capacity: int = 256):
        B = BUFFER_DAYS
        f, i, b = np.float64, np.int64, np.bool_
        super().__init__({
            "A": ((G,), f),            # share of segment aware of the song
            "C": ((G,), f),            # cumulative impressions per capita
            "BS": ((G,), f),           # cumulative single buyers (share of segment)
            "E": ((G,), f),            # engaged share (derived each day, kept for systems)
            "appeal": ((G,), f),
            "fanvec": ((G,), f),       # act fandom shares (refreshed weekly)
            "hook": ((), f), "depth": ((), f), "talk": ((), f),
            "style": ((D,), f),
            "genre": ((), i),
            "released": ((), i),       # ordinal day of release in this market
            "active": ((), b),
            "commercial": ((), b),     # a commercial single exists
            "vis": ((), f),            # chart/media visibility 0..1
            "radio_tier": ((F,), i),   # 0 none, 1 light .. 4 power
            "radio_share": ((F,), f),  # fraction of the format's stations playing it (regional pickup < 1)
            "radio_weeks": ((F,), i),
            "radio_peak": ((F,), f),   # peak observed research per format
            "radio_promo": ((F,), f),  # label promotion pressure 0..1
            "video_tier": ((V,), i),
            "video_weeks": ((V,), i),
            "video_q": ((), f),        # music video quality (0 = no video)
            "tv_promo": ((), f),
            "u_single": ((G, B), f),   # daily single units by segment
            "aud": ((F, B), f),        # daily airplay audience by format
            "wk_imp": ((len(CHANNELS),), f),      # this week's impressions by channel (persons)
            "last_imp": ((len(CHANNELS),), f),    # last week's
            "peakE": ((), f),          # peak population-weighted engaged share
        }, capacity)


class AlbumTable(_Table):
    def __init__(self, G: int, capacity: int = 128):
        B = BUFFER_DAYS
        f, i, b = np.float64, np.int64, np.bool_
        super().__init__({
            "BA": ((G,), f),           # casual buyers (share of segment)
            "BF": ((G,), f),           # fan buyers (share of segment)
            "interest": ((G,), f),     # remembered interest in the album (decays slowly after its singles fade)
            "fanvec": ((G,), f),
            "value": ((), f),          # perceived album value multiplier
            "released": ((), i),
            "active": ((), b),
            "u_album": ((G, B), f),
        }, capacity)
        self.focus: list[list[str]] = []   # per row: recording ids that drive demand

    def add(self, rid: str) -> int:
        i = super().add(rid)
        while len(self.focus) < self.n:
            self.focus.append([])
        return i

    def to_state(self, prefix):
        meta, arrays = super().to_state(prefix)
        meta["focus"] = self.focus
        return meta, arrays

    def load_state(self, prefix, meta, arrays):
        super().load_state(prefix, meta, arrays)
        self.focus = [list(x) for x in meta.get("focus", [])]

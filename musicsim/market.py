"""Market runtime: turns a market pack (data) into arrays the systems use.

Nothing here is country-specific; every number comes from data/markets/<id>/.
Derived objects are rebuilt from data on load (not saved), so they must be a
pure function of (market data, date).
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from .core import dates
from .core.config import DATA_DIR, load_yaml


@lru_cache(maxsize=None)
def load_genres():
    raw = load_yaml(DATA_DIR / "universal" / "genres.yaml")["genres"]
    ids = list(raw.keys())
    centroids = np.array([raw[g]["centroid"] for g in ids], dtype=float)
    meta = {g: raw[g] for g in ids}
    return ids, centroids, meta


def _vec(mapping: dict, keys: list[str], default=0.0) -> np.ndarray:
    return np.array([float(mapping.get(k, default)) for k in keys], dtype=float)


def step_value(entries: list[dict], d, key="value"):
    """Value from a list of {from: date, ...} entries effective at date d."""
    best = None
    for e in entries:
        f = e.get("from")
        if f is None or dates.parse(f) <= d:
            best = e
    return None if best is None else (best if key is None else best.get(key))


class MarketRuntime:
    def __init__(self, market_id: str):
        self.id = market_id
        self.dir = DATA_DIR / "markets" / market_id
        self.data = load_yaml(self.dir / "market.yaml")
        self.genre_ids, self.centroids, self.genre_meta = load_genres()
        self.K = len(self.genre_ids)
        self.gidx = {g: i for i, g in enumerate(self.genre_ids)}

        seg = self.data["segments"]
        self.seg_ids = list(seg.keys())
        self.G = len(self.seg_ids)
        self.sidx = {s: i for i, s in enumerate(self.seg_ids)}
        self.seg = seg
        self.taste = np.array([_vec(seg[s]["taste"], self.genre_ids) for s in self.seg_ids])
        self.taste /= self.taste.sum(axis=1, keepdims=True)
        self.single_prop = np.array([seg[s]["single_propensity"] for s in self.seg_ids])
        self.album_prop = np.array([seg[s]["album_propensity"] for s in self.seg_ids])
        self.novelty = np.array([seg[s].get("novelty_appetite", 0.5) for s in self.seg_ids])
        self.conformity = np.array([seg[s].get("conformity", 0.5) for s in self.seg_ids])

        c = self.data.get("contacts", {})
        self.contacts = np.array([_vec(c.get(s, {s: 1.0}), self.seg_ids) for s in self.seg_ids])

        r = self.data["radio"]
        self.listen_share = float(r["listen_share_of_day"])
        self.rot_spins = np.array([0.0, r["rotation_spins"]["light"], r["rotation_spins"]["medium"],
                                   r["rotation_spins"]["heavy"], r["rotation_spins"]["power"]])
        self.format_ids = list(r["formats"].keys())
        self.F = len(self.format_ids)
        self.formats = r["formats"]
        self.format_reach = np.array([_vec(r["formats"][f]["reach"], self.seg_ids) for f in self.format_ids])
        self.format_aff = np.array([_vec(r["formats"][f]["genre_affinity"], self.genre_ids) for f in self.format_ids])
        self.playlist = np.array([r["formats"][f]["playlist"] for f in self.format_ids])
        self.reporters = np.array([r["formats"][f].get("reporting_stations", 0) for f in self.format_ids])
        self.fidx = {f: i for i, f in enumerate(self.format_ids)}

        v = self.data["video"]
        self.view_share = float(v["view_share_of_day"])
        self.rot_plays = np.array([0.0, v["rotation_plays"]["light"], v["rotation_plays"]["medium"],
                                   v["rotation_plays"]["heavy"]])
        self.channel_ids = list(v["channels"].keys())
        self.V = len(self.channel_ids)
        self.channels = v["channels"]
        self.channel_reach = np.array([_vec(v["channels"][c]["reach"], self.seg_ids) for c in self.channel_ids])
        self.channel_aff = np.array([_vec(v["channels"][c]["genre_affinity"], self.genre_ids) for c in self.channel_ids])

        t = self.data["television"]
        self.tv_exposures = float(t["exposures_per_performance"])
        self.programs = t["programs"]
        self.outlets = self.data.get("media_outlets", {})
        self.chart_ids = list(self.data.get("charts", []))
        self.methodologies = {cid: load_yaml(self.dir / "methodologies" / f"{cid}.yaml") for cid in self.chart_ids}
        self._cache: dict = {}

    # ----- dated quantities -------------------------------------------------
    # Annual quantities are evaluated at mid-year so the cache is a pure function of the year
    # (never of whichever date happened to ask first).
    def population(self, d) -> np.ndarray:
        key = ("population", d.year)
        if key not in self._cache:
            mid = d.replace(month=7, day=1)
            self._cache[key] = np.array([dates.interp_series(self.seg[s]["population"], mid) * 1e6
                                         for s in self.seg_ids])
        return self._cache[key]

    def daily_budget(self, d) -> np.ndarray:
        key = ("budget", d.year)
        if key not in self._cache:
            mid = d.replace(month=7, day=1)
            per_cap = np.array([dates.interp_series(self.seg[s]["budget_per_capita"], mid) for s in self.seg_ids])
            self._cache[key] = per_cap * self.population(mid) / 365.0
        return self._cache[key]

    def price(self, kind: str, d) -> float:
        return dates.interp_series(self.data["prices"][kind], d)

    def dealer_share(self) -> float:
        return float(self.data["prices"]["dealer_share"])

    def manufacturing(self, kind: str) -> float:
        return float(self.data["prices"]["manufacturing"][kind])

    def mechanical_rate(self, d) -> float:
        return float(step_value(self.data["mechanical_rate"], d) or 0.0)

    def singles_market(self, d) -> float:
        return dates.interp_series(self.data["singles_market"], d)

    def release_weekday(self, d) -> str:
        return step_value(self.data["release_weekday"], d, key="weekday") or "monday"

    def cert_thresholds(self, kind: str, d) -> dict | None:
        return step_value(self.data["certification"][kind], d, key=None)

    def gig_fee(self, d) -> float:
        return dates.interp_series(self.data["live"]["local_gig_fee"], d)

    def channel_valid(self, cid: str, d) -> bool:
        c = self.channels[cid]
        return dates.in_window(d, c.get("valid_from"), c.get("valid_to"))

    def program_valid(self, pid: str, d) -> bool:
        p = self.programs[pid]
        if not dates.in_window(d, p.get("valid_from"), p.get("valid_to")):
            return False
        months = p.get("season_months")
        return months is None or d.month in months

    def genre_available(self, g: str, d) -> bool:
        f = self.genre_meta[g].get("from")
        return f is None or dates.parse(f) <= d

    # ----- derived ------------------------------------------------------------
    def format_audience(self, d) -> np.ndarray:
        """Persons listening to each format on an average day (F,)."""
        return (self.format_reach * self.population(d)).sum(axis=1)

    def taste_match(self, style: np.ndarray, sigma: float) -> np.ndarray:
        """(G,) how well a style-space position matches each segment's taste."""
        d2 = ((self.centroids - style) ** 2).sum(axis=1)
        k = np.exp(-d2 / (2 * sigma * sigma))          # (K,)
        return self.taste @ k

    def genre_of(self, style: np.ndarray) -> str:
        d2 = ((self.centroids - style) ** 2).sum(axis=1)
        return self.genre_ids[int(np.argmin(d2))]

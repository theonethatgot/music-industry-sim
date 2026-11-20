"""The World: all simulation state, plus (de)serialisation and state hashing."""
from __future__ import annotations

import hashlib
import io
import json

import numpy as np

from .core import dates
from .core.config import Config, load_config
from .core.events import EventLog
from .core.ledger import Ledger
from .entities import Act, Composition, Contract, Offer, Org, Person, Recording, Release
from .market import MarketRuntime
from .tables import AlbumTable, SongTable

ENTITY_TYPES = {
    "people": Person, "acts": Act, "orgs": Org, "compositions": Composition,
    "recordings": Recording, "releases": Release, "offers": Offer, "contracts": Contract,
}


class World:
    def __init__(self, seed: int, start, scenario: dict, config: Config):
        self.seed = int(seed)
        self.date = dates.parse(start)
        self.scenario = scenario
        self.config = config
        self.market_ids: list[str] = list(scenario.get("active_markets", [scenario["home_market"]]))
        self.markets: dict[str, MarketRuntime] = {m: MarketRuntime(m) for m in self.market_ids}
        self.people: dict[str, Person] = {}
        self.acts: dict[str, Act] = {}
        self.orgs: dict[str, Org] = {}
        self.compositions: dict[str, Composition] = {}
        self.recordings: dict[str, Recording] = {}
        self.releases: dict[str, Release] = {}
        self.offers: dict[str, Offer] = {}
        self.contracts: dict[str, Contract] = {}
        self.relations: dict[str, dict] = {}       # "a|b" -> {affinity, trust, respect, history}
        self.charts: dict[str, dict] = {}          # chart_id -> state (prev measures, stats, last run)
        self.news: list[dict] = []
        self.facts: list[dict] = []                # canonical narrative facts (validated proposals)
        self.schedule: list[dict] = []             # dated one-off happenings (tv, showcases, ...)
        self.commitments: list[dict] = []          # calendar of the protagonist and NPCs
        self.pending: list[dict] = []              # decisions awaiting the player
        self.interrupts: list[dict] = []           # reasons to stop advancing
        self.player: dict = {}                     # {"person": id, "act": id}
        self.counters: dict[str, int] = {}
        self.pass_no = 0
        self.flags: dict = {"burn_in": False}
        self.ledger = Ledger()
        self.events = EventLog()
        self.chart_log: list[dict] = []            # chart runs not yet flushed to disk
        self.week_log: list[dict] = []             # weekly per-song audit rows not yet flushed
        self.tables: dict[str, SongTable] = {}
        self.albums: dict[str, AlbumTable] = {}
        D = len(config["style_axes"])
        for m, rt in self.markets.items():
            self.tables[m] = SongTable(rt.G, rt.F, rt.V, D)
            self.albums[m] = AlbumTable(rt.G)

    # ------------------------------------------------------------------ ids
    def new_id(self, prefix: str) -> str:
        n = self.counters.get(prefix, 0) + 1
        self.counters[prefix] = n
        return f"{prefix}:n{n:05d}"

    # ------------------------------------------------------------ relations
    def rel(self, a: str, b: str, create: bool = True) -> dict | None:
        key = f"{a}|{b}"
        if key not in self.relations:
            if not create:
                return None
            self.relations[key] = {"affinity": 0.0, "trust": 0.3, "respect": 0.3, "history": []}
        return self.relations[key]

    def remember(self, person_id: str, gist: str, about=(), valence: float = 0.0,
                 salience: float = 0.5, event_id: int | None = None, public: bool = False):
        p = self.people.get(person_id)
        if p is None:
            return
        p.memories.append({"date": dates.iso(self.date), "gist": gist, "about": list(about),
                           "valence": round(valence, 2), "salience": round(salience, 2),
                           "event": event_id, "public": public})
        if len(p.memories) > 60:
            p.memories.sort(key=lambda m: (m["salience"], m["date"]))
            p.memories = p.memories[-50:]
            p.memories.sort(key=lambda m: m["date"])

    def emit(self, system, type_, entities=(), data=None, causes=(), draws=None, public=True) -> int:
        return self.events.emit(dates.iso(self.date), system, type_, entities, data, causes, draws, public)

    def add_news(self, text: str, kind: str, entities=(), tag: str = "reported", importance: float = 0.5,
                 event_id: int | None = None):
        self.news.append({"date": dates.iso(self.date), "text": text, "kind": kind, "entities": list(entities),
                          "tag": tag, "importance": round(importance, 3), "event": event_id})
        if len(self.news) > 600:
            self.news = self.news[-500:]

    @property
    def player_act(self) -> Act | None:
        aid = self.player.get("act")
        return self.acts.get(aid) if aid else None

    # ------------------------------------------------------- serialisation
    def to_state(self) -> tuple[dict, dict]:
        doc = {
            "seed": self.seed, "date": dates.iso(self.date), "scenario": self.scenario,
            "config_tree": self.config.tree, "market_ids": self.market_ids,
            "relations": self.relations, "charts": self.charts, "news": self.news,
            "facts": self.facts, "schedule": self.schedule, "commitments": self.commitments,
            "pending": self.pending, "interrupts": self.interrupts, "player": self.player,
            "counters": self.counters, "pass_no": self.pass_no, "flags": self.flags,
            "ledger": self.ledger.to_dict(), "event_next_id": self.events.next_id,
        }
        for name in ENTITY_TYPES:
            doc[name] = {k: v.to_dict() for k, v in getattr(self, name).items()}
        arrays: dict[str, np.ndarray] = {}
        doc["tables"], doc["albums"] = {}, {}
        for m in self.market_ids:
            meta, arr = self.tables[m].to_state(f"songs.{m}")
            doc["tables"][m] = meta
            arrays.update(arr)
            meta, arr = self.albums[m].to_state(f"albums.{m}")
            doc["albums"][m] = meta
            arrays.update(arr)
        return doc, arrays

    @classmethod
    def from_state(cls, doc: dict, arrays: dict) -> "World":
        cfg = Config(doc["config_tree"])
        w = cls(doc["seed"], doc["date"], doc["scenario"], cfg)
        for name, typ in ENTITY_TYPES.items():
            setattr(w, name, {k: typ.from_dict(v) for k, v in doc[name].items()})
        for key in ("relations", "charts", "news", "facts", "schedule", "commitments", "pending",
                    "interrupts", "player", "counters", "pass_no", "flags"):
            setattr(w, key, doc[key])
        w.ledger = Ledger.from_dict(doc["ledger"])
        w.events = EventLog(doc["event_next_id"])
        for m in w.market_ids:
            w.tables[m].load_state(f"songs.{m}", doc["tables"][m], arrays)
            w.albums[m].load_state(f"albums.{m}", doc["albums"][m], arrays)
        return w

    def outcome_hash(self) -> str:
        """Platform-tolerant fingerprint: like state_hash but with floats rounded to ~6 significant digits.

        NumPy's transcendental functions can differ in the last bit between CPUs/builds, so the exact
        state_hash is only comparable on one platform. This fingerprint compares outcomes across machines
        (it can still differ if a last-bit difference happens to flip a threshold)."""
        doc, arrays = self.to_state()

        def q(x):
            if isinstance(x, float):
                return float(f"{x:.6g}")
            if isinstance(x, dict):
                return {k: q(v) for k, v in x.items()}
            if isinstance(x, list):
                return [q(v) for v in x]
            return x
        h = hashlib.sha256()
        h.update(json.dumps(q(doc), sort_keys=True, default=str).encode())
        for k in sorted(arrays):
            a = arrays[k]
            if a.dtype.kind == "f":
                a = np.array([float(f"{v:.6g}") for v in a.ravel()], dtype=np.float64)
            h.update(k.encode())
            h.update(np.ascontiguousarray(a).tobytes())
        return h.hexdigest()[:20]

    def state_hash(self) -> str:
        doc, arrays = self.to_state()
        h = hashlib.sha256()
        h.update(json.dumps(doc, sort_keys=True, default=str).encode())
        for k in sorted(arrays):
            a = np.ascontiguousarray(arrays[k])
            h.update(k.encode())
            h.update(str(a.dtype).encode())
            h.update(a.tobytes())
        return h.hexdigest()[:20]


def arrays_to_blob(arrays: dict) -> bytes:
    buf = io.BytesIO()
    np.savez_compressed(buf, **arrays)
    return buf.getvalue()


def blob_to_arrays(blob: bytes) -> dict:
    with np.load(io.BytesIO(blob), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def make_config(scenario: dict) -> Config:
    return load_config(list(scenario.get("active_markets", [scenario["home_market"]])),
                       scenario.get("config_overrides"))

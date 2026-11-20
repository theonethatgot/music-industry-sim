"""World entities. Plain dataclasses; every field is JSON-serialisable.

Scales: 0..1 internally (displayed 0..100). Market-indexed arrays are stored as
``{market_id: [value per segment]}``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields


class Serial:
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict):
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})


@dataclass
class Person(Serial):
    id: str
    name: str
    birth_date: str | None = None
    gender: str | None = None
    nationality: str | None = None
    home_city: str | None = None
    historical: bool = False          # real person
    evidence: str = "S"               # A/B/C/S tier of the seeded profile
    roles: list = field(default_factory=list)
    personality: dict = field(default_factory=dict)
    goals: dict = field(default_factory=dict)
    skills: dict = field(default_factory=dict)        # vocal, performance, songwriting...
    style_skill: dict = field(default_factory=dict)   # genre -> 0..1 competence
    wellbeing: dict = field(default_factory=lambda: {"energy": 0.8, "stress": 0.2, "morale": 0.7})
    employer: str | None = None       # org id
    fee: float = 0.0                  # typical fee (producers/writers), nominal USD
    memories: list = field(default_factory=list)
    notes: str = ""
    collective: bool = False          # production teams credited as one


@dataclass
class Act(Serial):
    id: str
    name: str
    kind: str = "solo"                # solo | group | duo | band
    members: list = field(default_factory=list)       # [{person, role, joined, left}]
    home_market: str = ""
    genres: list = field(default_factory=list)
    style: list = field(default_factory=list)         # style-space position
    persona: list = field(default_factory=list)
    historical: bool = False
    evidence: str = "S"
    controller: str = "npc"           # npc | player  (decision source only)
    label: str | None = None
    manager: str | None = None
    contract: str | None = None
    active: bool = True
    stage: str = "aspiring"           # aspiring | rookie | rising | established | star | veteran
    # per-market status (lists indexed by that market's segments)
    recognition: dict = field(default_factory=dict)
    appeal: dict = field(default_factory=dict)
    fandom: dict = field(default_factory=dict)
    # scalar status (industry-observed where suffixed _o)
    singles_power_o: float = 0.1
    album_power_o: float = 0.1
    momentum: float = 0.0
    critical_prestige: float = 0.3
    industry_respect: float = 0.3
    live_buzz: float = 0.0            # local scene buzz (unsigned acts)
    intents: list = field(default_factory=list)       # historical soft intents
    cadence_weeks: int = 40           # typical gap between releases (fictional NPCs)
    last_release: str | None = None
    unrecouped: float = 0.0           # artist royalty account (negative = unrecouped)
    royalties_accrued: float = 0.0
    cert_counts: dict = field(default_factory=dict)
    flags: dict = field(default_factory=dict)


@dataclass
class Org(Serial):
    id: str
    name: str
    kind: str                         # record_company | label_group | radio_format | video_channel
    market: str = ""                  # | tv_program | media_outlet | chart_publisher | ...
    parent: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    historical: bool = True
    evidence: str = "B"
    params: dict = field(default_factory=dict)
    strategy: dict = field(default_factory=dict)
    people: dict = field(default_factory=dict)        # role -> person id
    roster: list = field(default_factory=list)
    state: dict = field(default_factory=dict)         # mutable runtime state (playlists etc.)


@dataclass
class Composition(Serial):
    id: str
    title: str
    writers: list = field(default_factory=list)       # [{person, share}]
    attrs: dict = field(default_factory=dict)         # melody, lyric_craft, structure, hook, depth, singability
    created: str = ""
    status: str = "available"         # available | pitched | assigned | recorded
    pitched_to: list = field(default_factory=list)
    genre: str = ""
    historical: bool = False


@dataclass
class Recording(Serial):
    id: str
    composition: str
    title: str
    act: str
    producers: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)         # production, signature, vocal_delivery, ...
    style: list = field(default_factory=list)
    genre: str = ""
    started: str = ""
    completed: str | None = None
    status: str = "in_production"     # in_production | done | released
    cost: float = 0.0
    payer: str = ""                   # account charged (label recording fund or artist)
    video: dict = field(default_factory=dict)         # {quality, cost, date}
    historical: bool = False
    hist_evidence: float | None = None
    notes: list = field(default_factory=list)
    draws: list = field(default_factory=list)
    reception: dict = field(default_factory=dict)     # market -> logged reception shock
    single_release: str | None = None                 # release id if issued as a single


@dataclass
class Release(Serial):
    id: str
    act: str
    label: str | None
    kind: str                         # single | album
    title: str
    tracks: list = field(default_factory=list)
    focus: list = field(default_factory=list)         # singles that drive album demand
    market: str = ""
    date: str = ""
    status: str = "planned"           # planned | released | cancelled
    commercial: bool = True           # commercially available (singles)
    promo_tier: str = "standard"
    promo_budget: float = 0.0
    priority: float = 0.5             # label priority 0..1 (revised weekly)
    expectation: float = 0.0          # label's expected weekly units at peak (observed belief)
    stock: float = 0.0
    stockout_days: int = 0
    shipped: float = 0.0
    sold: float = 0.0
    revenue_label: float = 0.0
    cert: str = ""
    historical: bool = False
    intent: str | None = None
    weekly: list = field(default_factory=list)        # [{week_end, units}]
    review: dict = field(default_factory=dict)        # the label's A&R verdict when it was green-lit


@dataclass
class Offer(Serial):
    id: str
    kind: str                         # recording_contract | booking | song_pitch | label_proposal | ...
    source: str
    target: str
    terms: dict = field(default_factory=dict)
    created: str = ""
    expires: str = ""
    status: str = "open"              # open | accepted | declined | expired | withdrawn
    rationale: str = ""
    causes: list = field(default_factory=list)


@dataclass
class Contract(Serial):
    id: str
    kind: str
    parties: list
    terms: dict
    start: str
    end: str | None = None
    status: str = "active"

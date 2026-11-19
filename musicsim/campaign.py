"""Campaign builder: assemble a world from scenario + market packs + people data + a character.

Nothing here assumes a particular country, year or protagonist: all of that is data.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np

from .core import dates, rng
from .core.config import DATA_DIR, load_yaml
from .entities import Act, Contract, Org, Person
from .sim import advance
from .world import World, make_config

# ------------------------------------------------------------------ helpers
def _norm_date(s):
    if s is None:
        return None
    s = str(s)
    return s + "-01" if len(s) == 7 else s


def _person(world, pid, name, **kw) -> Person:
    p = Person(id=pid, name=name, **kw)
    world.people[pid] = p
    return p


def _status_vectors(world, market, genres, fame, fandom):
    rt = world.markets[market]
    aff = np.zeros(rt.G)
    for g in genres:
        if g in rt.gidx:
            aff = np.maximum(aff, rt.taste[:, rt.gidx[g]])
    aff = aff / max(1e-9, aff.max()) if aff.max() > 0 else np.ones(rt.G)
    recog = np.clip(fame * (0.45 + 0.55 * aff), 0, 0.99)
    fan = np.clip(0.06 * fandom * aff ** 1.5, 0, 1) * recog
    return recog.round(5).tolist(), [0.62] * rt.G, fan.round(5).tolist()


# ------------------------------------------------------------------ build
def load_scenario(name_or_path: str) -> dict:
    p = DATA_DIR / "scenarios" / f"{name_or_path}.yaml"
    if not p.exists():
        p = Path(name_or_path)
    return load_yaml(p)


def load_character(name_or_path: str) -> dict:
    p = DATA_DIR / "characters" / f"{name_or_path}.yaml"
    if not p.exists():
        p = Path(name_or_path)
    return load_yaml(p)


def build_world(scenario: dict, seed: int, character: dict | None = None, burn_in: bool = True) -> World:
    start = dates.parse(scenario["start_date"])
    weeks = int(scenario.get("burn_in_weeks", 0)) if burn_in else 0
    t0 = start - dt.timedelta(weeks=weeks)
    t0 = t0 - dt.timedelta(days=t0.weekday())          # begin on a Monday
    world = World(seed, t0, scenario, make_config(scenario))
    world.flags["burn_in"] = True
    world.flags["start_date"] = start.isoformat()
    for m in world.market_ids:
        _load_orgs(world, m)
        _load_industry_people(world, m)
        _load_real_acts(world, m)
        _generate_fictional(world, m, int(scenario.get("world", {}).get("fictional_npc_acts", 480)))
    advance(world, (start - t0).days, stop_on_interrupt=False)
    world.flags["burn_in"] = False
    world.interrupts = []
    world.news = [n for n in world.news if n["date"] >= (start - dt.timedelta(days=28)).isoformat()]
    if character is not None:
        add_protagonist(world, scenario, character)
    return world


def _names(world, market):
    return world.markets[market].data["generated"]["names"]


def _gen_name(world, market, *key) -> str:
    n = _names(world, market)
    return f"{rng.choice(world.seed, n['first'], *key, 'f')} {rng.choice(world.seed, n['last'], *key, 'l')}"


def _load_orgs(world, market):
    data = load_yaml(DATA_DIR / "markets" / market / "orgs.yaml")
    for gid, g in data.get("groups", {}).items():
        world.orgs[f"org:{gid}"] = Org(id=f"org:{gid}", name=g["name"], kind="label_group", market=market,
                                       evidence="B", params={"notes": g.get("notes", "")})
    for lid, l in data["labels"].items():
        oid = f"org:{lid}"
        fictional = bool(l.get("fictional"))
        org = Org(id=oid, name=l["name"], kind="record_company", market=market, parent=f"org:{l['group']}",
                  historical=not fictional, evidence="S" if fictional else "B",
                  params={"size": l["size"], "ear": l["ear"], "distributed_by": l.get("distributed_by"),
                          "notes": l.get("notes", "")},
                  strategy={"risk": l["risk"], "focus": l["focus"]})
        world.orgs[oid] = org
        world.ledger.transfer(world.date, "ext:capital", oid, 20e6 * l["size"], "capital", "opening balance")
        # fictional staff: an A&R rep and a house producer per label (clearly generated people)
        key = f"staff:{lid}"
        rep = _person(world, f"person:anr_{lid}", _gen_name(world, market, key, "anr"), roles=["a&r"], employer=oid,
                      personality={"ambition": 0.5 + 0.4 * rng.uniform(world.seed, key, "amb"),
                                   "risk_tolerance": l["risk"], "sociability": 0.7},
                      notes=f"A&R at {l['name']} (generated)")
        org.people["anr"] = rep.id
        hp = _person(world, f"person:producer_{lid}", _gen_name(world, market, key, "prod"),
                     roles=["producer", "songwriter"], employer=oid,
                     skills={"production": 0.55 + 0.15 * l["ear"], "songwriting": 0.55},
                     style_skill={g: 0.8 for g in l["focus"]}, fee=8000,
                     notes=f"staff producer at {l['name']} (generated)")
        org.people["house_producer"] = hp.id


def _load_industry_people(world, market):
    data = load_yaml(DATA_DIR / "people" / market / "industry.yaml")
    acts = {a["id"]: a for a in load_yaml(DATA_DIR / "people" / market / "acts.yaml")["acts"]}
    for pid, p in data.get("producers", {}).items():
        if p.get("act") and acts.get(p["act"], {}).get("kind", "solo") == "solo":
            continue        # solo artist-producers are created with their act
        roles = ["songwriter"] if p.get("writer_only") else ["producer", "songwriter"]
        _person(world, f"person:{pid}", p["name"], historical=True, evidence="C", roles=roles,
                nationality=p.get("nationality", market), skills=dict(p["skills"]), style_skill=dict(p["styles"]),
                fee=float(p.get("fee", 10000)), collective=bool(p.get("collective")))
    for pid, e in data.get("executives", {}).items():
        oid = f"org:{e['employer']}"
        _person(world, f"person:{pid}", e["name"], historical=True, evidence="C", roles=["executive"],
                employer=oid, personality=dict(e.get("personality", {})), notes=e.get("title", ""))
        if oid in world.orgs:
            world.orgs[oid].people["head"] = f"person:{pid}"


def _load_real_acts(world, market):
    data = load_yaml(DATA_DIR / "people" / market / "acts.yaml")
    prod = load_yaml(DATA_DIR / "people" / market / "industry.yaml").get("producers", {})
    for a in data["acts"]:
        aid = f"act:{a['id']}"
        skills = dict(a.get("skills", {}))
        styles = dict(a.get("styles", {g: 0.9 for g in a["genres"]}))
        members = []
        if a.get("person") or a.get("kind", "solo") == "solo":
            pinfo = a.get("person", {})
            pid = f"person:{a['id']}"
            pskills = {k: v for k, v in skills.items()}
            if a["id"] in {k for k, v in prod.items() if v.get("act")}:
                pk = next(v for v in prod.values() if v.get("act") == a["id"])
                pskills.update(pk["skills"])
                styles.update(pk["styles"])
            pskills.setdefault("production", 0.55 if "producers" in str(a.get("intents")) else 0.3)
            pk = next((v for v in prod.values() if v.get("act") == a["id"]), None)
            _person(world, pid, a["name"], historical=True, evidence="C",
                    roles=["performer", "songwriter"] + (["producer"] if pk else []),
                    fee=float(pk.get("fee", 0)) if pk else 0.0,
                    birth_date=_norm_date(pinfo.get("birth_date")), gender=pinfo.get("gender"),
                    home_city=pinfo.get("home_city"), nationality=pinfo.get("nationality", a.get("home_market", market)),
                    skills=pskills, style_skill=styles, personality=dict(a.get("personality", {})))
            members.append({"person": pid, "role": "lead", "joined": None, "left": None})
        else:
            for j, name in enumerate(a.get("members", [])):
                pid = f"person:{a['id']}_{j + 1}"
                sk = {k: (v if j == 0 else max(0.2, v - 0.08)) for k, v in skills.items()}
                existing = next((q for q in world.people.values() if q.historical and q.name == name), None)
                if existing:                    # e.g. a member who is also a producer in the data
                    pid = existing.id
                    existing.roles = sorted(set(existing.roles) | {"performer"})
                    for k, v in sk.items():
                        existing.skills.setdefault(k, v)
                else:
                    _person(world, pid, name, historical=True, evidence="C", roles=["performer"],
                            nationality=a.get("home_market", market), skills=sk, style_skill=styles)
                members.append({"person": pid, "role": "lead" if j == 0 else "member", "joined": None, "left": None})
        st = a.get("status", {})
        recog, app, fan = _status_vectors(world, market, a["genres"], st.get("fame", 0.1), st.get("fandom", 0.05))
        intents = [dict(it, date=_norm_date(it.get("date"))) for it in a.get("intents", [])]
        act = Act(id=aid, name=a["name"], kind=a.get("kind", "solo"), members=members,
                  home_market=a.get("home_market", market), genres=list(a["genres"]), historical=True, evidence="C",
                  label=a.get("label"), stage="established" if st.get("fame", 0) > 0.3 else "rising",
                  recognition={market: recog}, appeal={market: app}, fandom={market: fan},
                  singles_power_o=round(0.05 + 0.6 * st.get("fame", 0.1), 3),
                  album_power_o=round(0.05 + 0.5 * st.get("fandom", 0.05) + 0.25 * st.get("fame", 0.1), 3),
                  critical_prestige=st.get("prestige", 0.3), intents=intents,
                  flags={"visual": skills.get("look", 0.6), "persona_strength": 0.5 + 0.4 * st.get("prestige", 0.3)})
        if act.label is None or f"org:{act.label}" not in world.orgs:
            act.label = None
            act.stage = "aspiring"
            act.live_buzz = 0.0
        world.acts[aid] = act
        if act.label:
            org = world.orgs[f"org:{act.label}"]
            org.roster.append(aid)
            norms = world.markets[market].data.get("royalty_norms", {})
            rate = norms["star"] if st.get("fame", 0) > 0.7 else norms["established"] if st.get("fame", 0) > 0.3 \
                else norms["new_artist"]
            cid = world.new_id("contract")
            world.contracts[cid] = Contract(id=cid, kind="recording_contract", parties=[org.id, aid],
                                            terms={"royalty_rate": rate, "seeded": True}, start=world.date.isoformat())
            act.contract = cid


def _generate_fictional(world, market, n):
    rt = world.markets[market]
    labels = [o for o in sorted(world.orgs.values(), key=lambda o: o.id) if o.kind == "record_company"]
    gen = rt.data["generated"]
    names = gen["names"]
    mix = [(g, w) for g, w in gen["genre_mix"].items() if g in rt.gidx and rt.genre_available(g, world.date)]
    genre_pool, genre_w = zip(*mix)
    for k in range(n):
        key = f"npc{k}"
        u = lambda *p: rng.uniform(world.seed, "gen", key, *p)
        g = rng.weighted_choice(world.seed, genre_pool, genre_w, "gen", key, "genre")
        kind = "solo" if u("kind") < 0.55 else ("group" if g in gen["group_genres"] else "band")
        if kind == "solo":
            name = _gen_name(world, market, "gen", key)
        else:
            name = f"{rng.choice(world.seed, names['band_a'], 'gen', key, 'a')} " \
                   f"{rng.choice(world.seed, names['band_b'], 'gen', key, 'b')}"
        aid = f"act:npc{k:04d}"
        talent = float(np.clip(0.5 + 0.13 * rng.normal(world.seed, "gen", key, "talent"), 0.2, 0.95))
        members = []
        n_members = 1 if kind == "solo" else 2 + int(u("nm") * 3)
        for j in range(n_members):
            pid = f"person:npc{k:04d}_{j + 1}"
            pname = name if kind == "solo" else _gen_name(world, market, "gen", key, j)
            sk = {s: float(np.clip(talent + 0.12 * rng.normal(world.seed, "gen", key, j, s), 0.15, 0.97))
                  for s in ("vocal", "performance", "media", "songwriting", "look")}
            _person(world, pid, pname, roles=["performer"], nationality=market, skills=sk, style_skill={g: 0.85},
                    personality={"ambition": u(j, "amb"), "risk_tolerance": u(j, "risk"),
                                 "artistic_vs_commercial": 2 * u(j, "avc") - 1, "discipline": u(j, "disc")})
            members.append({"person": pid, "role": "lead" if j == 0 else "member", "joined": None, "left": None})
        fame = float(min(0.6, 0.02 * np.exp(2.6 * u("fame"))))     # heavy-tailed starting recognition
        fandom = fame * 0.4 * u("fandom")
        recog, app, fan = _status_vectors(world, market, [g], fame, fandom)
        signed = u("signed") < 0.75
        label = None
        if signed:
            ws = [o.params["size"] * (0.3 + o.strategy["focus"].get(g, 0.1)) for o in labels]
            label = rng.weighted_choice(world.seed, labels, ws, "gen", key, "label").id.split(":", 1)[1]
        cadence = int(28 + 30 * u("cadence"))
        last = (world.date - dt.timedelta(weeks=int(u("last") * cadence))).isoformat()
        act = Act(id=aid, name=name, kind=kind, members=members, home_market=market, genres=[g], historical=False,
                  label=label, stage="established" if fame > 0.3 else "rising" if fame > 0.08 else
                  ("rookie" if label else "aspiring"),
                  recognition={market: recog}, appeal={market: app}, fandom={market: fan},
                  singles_power_o=round(0.05 + 0.6 * fame, 3), album_power_o=round(0.04 + 0.4 * fame, 3),
                  cadence_weeks=cadence, last_release=last, live_buzz=0.0 if label else 0.1 * u("buzz"),
                  flags={"visual": talent, "persona_strength": u("persona"), "demo_quality": talent * 0.8})
        world.acts[aid] = act
        if label:
            org = world.orgs[f"org:{label}"]
            org.roster.append(aid)
            cid = world.new_id("contract")
            world.contracts[cid] = Contract(id=cid, kind="recording_contract", parties=[org.id, aid],
                                            terms={"royalty_rate": 0.11, "seeded": True}, start=world.date.isoformat())
            act.contract = cid
    # generated songwriters and producers for hire (the long tail of the business)
    for k in range(30):
        key = f"writer{k}"
        sw = float(np.clip(0.55 + 0.12 * rng.normal(world.seed, "gen", key), 0.25, 0.92))
        gs = rng.choice(world.seed, list(genre_pool), "gen", key, "g")
        _person(world, f"person:writer{k:03d}", _gen_name(world, market, "gen", key), roles=["songwriter"],
                skills={"songwriting": sw}, style_skill={gs: 0.9}, notes="staff songwriter (generated)")
    for k in range(12):
        key = f"prod{k}"
        ps = float(np.clip(0.6 + 0.1 * rng.normal(world.seed, "gen", key), 0.35, 0.88))
        gs = rng.choice(world.seed, list(genre_pool), "gen", key, "g")
        _person(world, f"person:producer{k:03d}", _gen_name(world, market, "gen", key),
                roles=["producer", "songwriter"],
                skills={"production": ps, "songwriting": ps - 0.1}, style_skill={gs: 0.9, gen["default_genre"]: 0.7},
                fee=float(round(1500 + 25000 * max(0.0, ps - 0.5), -2)), notes="independent producer (generated)")


# ------------------------------------------------------------- protagonist
def add_protagonist(world, scenario, ch: dict):
    market = scenario["home_market"]
    circ = scenario.get("circumstances", {})
    pid = f"person:pc_{ch['id']}"
    aid = f"act:pc_{ch['id']}"
    p = _person(world, pid, ch["name"], birth_date=_norm_date(ch.get("birth_date")), gender=ch.get("gender"),
                nationality=ch.get("nationality", market), home_city=circ.get("city", ch.get("home_city")),
                roles=["performer", "songwriter"], skills=dict(ch["skills"]), style_skill=dict(ch.get("styles", {})),
                personality=dict(ch.get("personality", {})), goals=dict(ch.get("goals", {})),
                notes=ch.get("background", ""))
    recog = [0.0] * world.markets[market].G
    act = Act(id=aid, name=ch.get("act_name", ch["name"]), kind="solo",
              members=[{"person": pid, "role": "lead", "joined": world.date.isoformat(), "left": None}],
              home_market=market, genres=list(ch.get("genres", [world.markets[market].data["generated"]["default_genre"]])), persona=list(ch.get("persona", [])),
              controller="player", stage=scenario.get("career_stage", "aspiring"),
              recognition={market: recog}, appeal={market: [0.5] * len(recog)}, fandom={market: list(recog)},
              singles_power_o=0.05, album_power_o=0.04, live_buzz=0.15,
              flags={"visual": ch["skills"].get("look", 0.6), "persona_strength": 0.5,
                     "demo_quality": circ.get("demo", {}).get("quality", 0.45)})
    world.acts[aid] = act
    world.player = {"person": pid, "act": aid, "market": market}
    world.ledger.transfer(world.date, "ext:capital", pid, float(circ.get("cash", 1000)), "savings", "starting cash")
    if circ.get("day_job"):
        world.flags["day_job"] = dict(circ["day_job"], active=True)
    world.flags["lifestyle"] = circ.get("lifestyle", "modest")
    if circ.get("label") and f"org:{circ['label']}" in world.orgs:
        from .systems.labels import sign
        org = world.orgs[f"org:{circ['label']}"]
        sign(world, org, act, {"type": "recording_contract", "advance": 10000.0, "royalty_rate": 0.10, "firm_albums": 1,
                               "option_albums": 3, "recording_budget_per_album": 40000.0,
                               "video_recoupable_share": 0.5})
    for k, c in enumerate(circ.get("connections", [])):
        cid = f"person:pc_contact{k + 1}"
        key = f"contact{k}"
        name = _gen_name(world, market, key)
        if c["template"] == "local_producer":
            _person(world, cid, name, roles=["producer", "songwriter"], home_city=circ.get("city"),
                    skills={"production": 0.62, "songwriting": 0.6}, style_skill={g: 0.85 for g in act.genres},
                    fee=1200.0, personality={"ambition": 0.7, "loyalty": 0.7, "sociability": 0.6},
                    notes="local producer (generated)")
        else:
            _person(world, cid, name, roles=["booker"], home_city=circ.get("city"),
                    personality={"sociability": 0.8}, notes="club booker (generated)")
        r = world.rel(pid, cid)
        r.update({"affinity": c.get("affinity", 0.3), "trust": c.get("trust", 0.4)})
        r2 = world.rel(cid, pid)
        r2.update({"affinity": c.get("affinity", 0.3), "trust": c.get("trust", 0.4)})
        world.remember(cid, c.get("relation", "knows the protagonist"), [pid], valence=0.3, salience=0.6)
        world.remember(pid, f"{name}: {c.get('relation', '')}", [cid], valence=0.3, salience=0.6)
    for s in circ.get("scheduled", []):
        when = world.date + dt.timedelta(days=int(s.get("in_days", 7)))
        world.schedule.append({"kind": s["kind"], "date": when.isoformat(), "market": market, "act": aid,
                               "venue": s.get("venue"), "note": s.get("note")})
    world.emit("campaign", "protagonist_created", [pid, aid],
               {"name": p.name, "scenario": scenario["id"], "stage": act.stage, "city": circ.get("city")})

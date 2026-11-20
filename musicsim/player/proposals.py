"""Narrator proposals: developments the AI narrator suggests, which the engine validates,
resolves with the same models it uses everywhere, and persists.

Pipeline: schema -> feasibility -> plausibility prior -> resolution (logged roll) -> persistence.
Wording cannot change the odds: resolution only reads world state.
"""
from __future__ import annotations

import datetime as dt
import re

import numpy as np

from ..core import dates
from ..core.rng import Draws
from ..entities import Person

ROLES = ["manager", "songwriter", "producer", "musician", "dancer", "journalist", "dj", "friend", "family",
         "love_interest", "promoter", "stylist", "lawyer", "executive_assistant", "rival_artist"]
OPPORTUNITIES = ["tv_booking", "showcase", "collaboration", "interview", "gig_offer"]
TRAIT_WORDS = {
    "ambitious": ("ambition", 0.85), "lazy": ("discipline", 0.2), "disciplined": ("discipline", 0.85),
    "loyal": ("loyalty", 0.85), "fickle": ("loyalty", 0.2), "reckless": ("risk_tolerance", 0.9),
    "cautious": ("risk_tolerance", 0.2), "warm": ("sociability", 0.85), "cold": ("sociability", 0.2),
    "egotistical": ("ego", 0.9), "humble": ("ego", 0.2), "volatile": ("temperament", 0.9), "calm": ("temperament", 0.2),
    "artsy": ("artistic_vs_commercial", 0.7), "commercial": ("artistic_vs_commercial", -0.7),
}
MAX_NEW_PEOPLE_PER_PASS = 3
NUMERIC_CLAIM = re.compile(r"(\$\s?\d|\d[\d,]*\s*(copies|units|sold|dollars|spins|plays)|#\s?\d|number\s+\d+\s+on)",
                           re.IGNORECASE)

SCHEMA = {
    "introduce_person": {"required": ["name", "role", "context"], "optional": ["traits", "attitude", "affiliation"]},
    "opportunity": {"required": ["kind", "context"], "optional": ["source", "with", "recording_id", "venue"]},
    "relationship_moment": {"required": ["with", "nature", "valence"], "optional": ["private"]},
    "narrative_fact": {"required": ["text"], "optional": ["about"]},
    "creative_brief": {"required": ["concept"], "optional": ["mood", "ambition", "influences"]},
}


def validate(world, prop: dict) -> list[str]:
    if not isinstance(prop, dict) or "type" not in prop:
        return ["each proposal needs a 'type'"]
    t = prop["type"]
    if t not in SCHEMA:
        return [f"unknown proposal type '{t}' (valid: {', '.join(SCHEMA)})"]
    errs = [f"{t}: missing '{k}'" for k in SCHEMA[t]["required"] if k not in prop]
    allowed = set(SCHEMA[t]["required"]) | set(SCHEMA[t]["optional"]) | {"type"}
    errs += [f"{t}: unexpected field '{k}'" for k in prop if k not in allowed]
    if t == "introduce_person" and prop.get("role") not in ROLES:
        errs.append(f"introduce_person: role must be one of {ROLES}")
    if t == "opportunity" and prop.get("kind") not in OPPORTUNITIES:
        errs.append(f"opportunity: kind must be one of {OPPORTUNITIES}")
    if t == "relationship_moment":
        v = prop.get("valence")
        if not isinstance(v, (int, float)) or not -2 <= v <= 2:
            errs.append("relationship_moment: valence must be a number from -2 to 2")
    if t == "creative_brief":
        for k, lo, hi in (("mood", -1, 1), ("ambition", 0, 1)):
            if k in prop and (not isinstance(prop[k], (int, float)) or not lo <= prop[k] <= hi):
                errs.append(f"creative_brief: {k} must be between {lo} and {hi}")
    return errs


def resolve(world, prop: dict, seq: int) -> dict:
    errs = validate(world, prop)
    if errs:
        return {"status": "invalid", "errors": errs}
    return globals()[f"_p_{prop['type']}"](world, prop, Draws(world.seed, "proposal", seq, world.date.isoformat()))


def _pid(world):
    return world.player["person"]


def _known(world, person_id: str) -> bool:
    return f"{_pid(world)}|{person_id}" in world.relations or f"{person_id}|{_pid(world)}" in world.relations


def _p_introduce_person(world, prop, dr):
    created = world.flags.setdefault("pass_new_people", 0)
    if created >= MAX_NEW_PEOPLE_PER_PASS:
        return {"status": "rejected", "reason": "too many new named people in one pass; introduce them later"}
    name = prop["name"].strip()
    if any(p.historical and p.name.lower() == name.lower() for p in world.people.values()):
        return {"status": "rejected", "reason": f"{name} is a real person already simulated in this world; "
                                                 "they can't be invented, only met through events"}
    if any(p.name.lower() == name.lower() for p in world.people.values()):
        return {"status": "rejected", "reason": f"someone named {name} already exists; refer to them by id"}
    role = prop["role"]
    personality = {k: round(0.3 + 0.4 * dr.uniform(k), 3) for k in
                   ("ambition", "discipline", "loyalty", "risk_tolerance", "sociability", "ego", "temperament")}
    for w in prop.get("traits", []) or []:
        if isinstance(w, str) and w.lower() in TRAIT_WORDS:
            k, v = TRAIT_WORDS[w.lower()]
            personality[k] = v
    # professional ability is drawn by the engine (narration cannot declare someone brilliant)
    skills = {}
    base = float(np.clip(0.5 + 0.12 * dr.normal("skill"), 0.2, 0.85))
    if role in ("producer", "songwriter"):
        skills = {"production": base if role == "producer" else 0.2, "songwriting": base}
    elif role in ("musician", "dancer", "rival_artist"):
        skills = {"performance": base, "vocal": base * 0.9}
    elif role == "manager":
        skills = {"management": base, "network": base * 0.9}
    pid = world.new_id("person")
    roles = [role] + (["producer", "songwriter"] if role == "producer" else ["songwriter"] if role == "songwriter" else [])
    fee = round(800 + 6000 * max(0.0, base - 0.4), -2) if role == "producer" else 0.0
    world.people[pid] = Person(id=pid, name=name, roles=roles, personality=personality, skills=skills, fee=fee,
                               home_city=world.people[_pid(world)].home_city,
                               notes=f"introduced in narration: {prop['context']}"[:300])
    att = {"warm": 0.25, "neutral": 0.05, "cool": -0.1, "hostile": -0.3}.get(prop.get("attitude", "neutral"), 0.05)
    for a, b in ((pid, _pid(world)), (_pid(world), pid)):
        r = world.rel(a, b)
        r["affinity"] = att
        r["trust"] = 0.3
    world.remember(pid, f"Met {world.people[_pid(world)].name}: {prop['context']}", [_pid(world)], valence=att,
                   salience=0.5)
    world.remember(_pid(world), f"Met {name} ({role}): {prop['context']}", [pid], valence=att, salience=0.5)
    world.flags["pass_new_people"] = created + 1
    eid = world.emit("narrative", "person_introduced", [pid, _pid(world)], {"name": name, "role": role,
                                                                           "skills": skills}, draws=dr.log)
    return {"status": "accepted", "summary": f"{name} ({role}) now exists in the world as {pid}.", "person": pid,
            "event": eid}


def _p_relationship_moment(world, prop, dr):
    other = prop["with"]
    if other not in world.people:
        return {"status": "rejected", "reason": f"unknown person '{other}'"}
    if not _known(world, other):
        return {"status": "rejected", "reason": "the protagonist doesn't know this person yet; introduce them "
                                                 "through an event or an introduce_person proposal first"}
    v = float(prop["valence"])
    o = world.people[other]
    # the other person's temperament and loyalty shape how much a moment moves them
    sens = 0.5 + 0.5 * o.personality.get("sociability", 0.5)
    delta = round(0.04 * v * sens, 3)
    r1, r2 = world.rel(_pid(world), other), world.rel(other, _pid(world))
    r1["affinity"] = round(float(np.clip(r1["affinity"] + 0.04 * v, -1, 1)), 3)
    r2["affinity"] = round(float(np.clip(r2["affinity"] + delta, -1, 1)), 3)
    if v > 0:
        r2["trust"] = round(min(1.0, r2["trust"] + 0.02 * v), 3)
    else:
        r2["trust"] = round(max(0.0, r2["trust"] + 0.03 * v), 3)
    eid = world.emit("narrative", "relationship_moment", [_pid(world), other],
                     {"nature": prop["nature"][:200], "valence": v, "their_affinity_change": delta},
                     public=not prop.get("private", True))
    r2["history"].append(eid)
    world.remember(other, prop["nature"][:200], [_pid(world)], valence=0.3 * v, salience=0.3 + 0.15 * abs(v), event_id=eid)
    world.remember(_pid(world), prop["nature"][:200], [other], valence=0.3 * v, salience=0.3 + 0.15 * abs(v), event_id=eid)
    return {"status": "accepted", "summary": f"{o.name}'s regard for you changed by {delta:+.3f} "
                                             f"(now {r2['affinity']:+.2f}).", "event": eid}


def _p_narrative_fact(world, prop, dr):
    text = prop["text"].strip()
    if NUMERIC_CLAIM.search(text):
        return {"status": "rejected", "reason": "facts may not assert money, sales, airplay or chart numbers; "
                                                 "those come only from the engine (use a decision instead)"}
    if len(text) > 400:
        return {"status": "rejected", "reason": "keep canonical facts under 400 characters"}
    fact = {"date": world.date.isoformat(), "text": text, "about": list(prop.get("about", []))}
    world.facts.append(fact)
    eid = world.emit("narrative", "fact", fact["about"] or [_pid(world)], {"text": text}, public=False)
    return {"status": "accepted", "summary": "Recorded as canon.", "event": eid}


def _p_creative_brief(world, prop, dr):
    world.flags["brief"] = {"concept": prop["concept"][:300], "mood": float(prop.get("mood", 0.0)),
                            "ambition": float(prop["ambition"]) if "ambition" in prop else None,
                            "influences": prop.get("influences", [])}
    return {"status": "accepted", "summary": "Brief stored; it will shape the next recording session's direction "
                                             "(mood and creative risk), not its quality."}


def _p_opportunity(world, prop, dr):
    kind = prop["kind"]
    act = world.player_act
    m = world.player["market"]
    rt = world.markets[m]
    N = rt.population(world.date)
    recog = np.array(act.recognition.get(m, [0.0] * rt.G))
    fame = float((recog * N).sum() / N.sum())
    if kind == "tv_booking":
        pid = prop.get("source", "")
        pid = pid.split(":", 1)[-1]
        if pid not in rt.programs or not rt.program_valid(pid, world.date):
            return {"status": "rejected", "reason": f"'{prop.get('source')}' is not a TV program airing now; "
                                                     f"valid: {[p for p in rt.programs if rt.program_valid(p, world.date)]}"}
        rec = _current_single(world)
        if rec is None:
            return {"status": "rejected", "reason": "TV bookers book acts with a current single"}
        prog = rt.programs[pid]
        viewers = np.array([prog["viewers"].get(s, 0.0) for s in rt.seg_ids])
        draw = float((recog * viewers * N).sum() / max(1.0, (viewers * N).sum()))
        p = float(np.clip(0.03 + 1.4 * draw + 0.4 * max(0.0, act.momentum) - 0.5 * prog["booking_threshold"], 0.01, 0.9))
        if not dr.chance("booked", p):
            eid = world.emit("narrative", "opportunity_failed", [act.id, f"program:{pid}"], {"kind": kind, "p": round(p, 3)},
                             draws=dr.log)
            return {"status": "rejected", "reason": f"{prog['name']}'s bookers passed (chance was about {p:.0%}).",
                    "event": eid}
        air = world.date + dt.timedelta(days=7 + int(dr.uniform("day") * 14))
        perf = world.people[_pid(world)].skills.get("performance", 0.5)
        impact = float(np.clip(0.55 + 0.8 * perf + 0.12 * dr.normal("stage"), 0.3, 1.6))
        eid = world.emit("television", "tv_booking", [rec.id, act.id, f"program:{pid}"],
                         {"program": prog["name"], "air_date": air.isoformat(), "via": "narrative", "p": round(p, 3),
                          "stage_impact": round(impact, 3)}, draws=dr.log)
        world.schedule.append({"kind": "tv", "date": air.isoformat(), "market": m, "song": rec.id, "act": act.id,
                               "program": pid, "impressions": (viewers * rt.tv_exposures * impact).tolist(),
                               "impact": impact, "event": eid})
        return {"status": "accepted", "summary": f"Booked on {prog['name']} for {air.isoformat()}.", "event": eid}
    if kind == "showcase":
        if act.label:
            return {"status": "rejected", "reason": "you're already signed; showcases are for unsigned acts"}
        p = float(np.clip(0.2 + 0.8 * act.live_buzz, 0.05, 0.9))
        if not dr.chance("arranged", p):
            return {"status": "rejected", "reason": f"couldn't get A&R people to commit (chance about {p:.0%}); "
                                                     "more live buzz would help"}
        when = world.date + dt.timedelta(days=10 + int(dr.uniform("when") * 10))
        world.schedule.append({"kind": "showcase", "date": when.isoformat(), "market": m, "act": act.id,
                               "venue": prop.get("venue", "a showcase"), "note": prop["context"][:200]})
        eid = world.emit("narrative", "showcase_arranged", [act.id], {"date": when.isoformat(), "p": round(p, 3)},
                         draws=dr.log)
        return {"status": "accepted", "summary": f"Showcase set for {when.isoformat()}.", "event": eid}
    if kind == "collaboration":
        other = prop.get("with")
        if other not in world.people:
            return {"status": "rejected", "reason": "collaboration needs 'with': an existing person id"}
        o = world.people[other]
        rel = world.relations.get(f"{other}|{_pid(world)}", {"affinity": 0.0})
        stature = max(o.skills.get("production", 0), o.skills.get("songwriting", 0), o.skills.get("vocal", 0))
        p = float(np.clip(0.25 + 0.5 * rel["affinity"] + 0.8 * (act.singles_power_o - 0.6 * max(0, stature - 0.7))
                          + 0.3 * fame, 0.02, 0.9))
        if not dr.chance("agrees", p):
            return {"status": "rejected", "reason": f"{o.name} declined (chance about {p:.0%})."}
        r = world.rel(other, _pid(world))
        r["affinity"] = round(r["affinity"] + 0.08, 3)
        world.remember(other, f"Agreed to collaborate with {act.name}: {prop['context'][:150]}", [act.id], 0.3, 0.6)
        eid = world.emit("narrative", "collaboration_agreed", [act.id, other], {"context": prop["context"][:200],
                                                                               "p": round(p, 3)}, draws=dr.log)
        return {"status": "accepted", "summary": f"{o.name} agreed to work with you. Use them as cowriter/producer in "
                                                 f"record_song.", "event": eid}
    if kind == "interview":
        p = float(np.clip(0.1 + 1.5 * fame + 0.5 * max(0.0, act.momentum) + (0.2 if _current_single(world) else 0), 0.02, 0.9))
        if not dr.chance("runs", p):
            return {"status": "rejected", "reason": f"no outlet bit (chance about {p:.0%})."}
        media = world.people[_pid(world)].skills.get("media", 0.5)
        lift = 0.01 + 0.03 * media * dr.uniform("lift")
        act.recognition[m] = np.clip(recog + lift * (1 - recog), 0, 1).round(6).tolist()
        eid = world.emit("media", "interview", [act.id], {"context": prop["context"][:200], "recognition_lift": round(lift, 4)},
                         draws=dr.log)
        return {"status": "accepted", "summary": "An interview ran; a little more of the public knows your name.",
                "event": eid}
    if kind == "gig_offer":
        from .wellbeing import resting
        r = resting(world, _pid(world), world.date.isoformat(), world.date.isoformat())
        if r:
            return {"status": "rejected", "reason": f"the protagonist has protected time off until {r['end']}"}
        p = float(np.clip(0.3 + 1.2 * act.live_buzz + fame, 0.05, 0.95))
        if not dr.chance("offer", p):
            return {"status": "rejected", "reason": f"the promoter went with someone else (chance about {p:.0%})."}
        fee = round(rt.gig_fee(world.date) * (3 + 30 * fame + 6 * act.live_buzz), -1)
        world.ledger.transfer(world.date, "ext:venues", _pid(world), fee, "gig_fees", prop["context"][:60])
        act.live_buzz = min(1.0, act.live_buzz + 0.03)
        eid = world.emit("narrative", "gig_played", [act.id], {"fee": fee, "context": prop["context"][:200]}, draws=dr.log)
        return {"status": "accepted", "summary": f"Played the date; paid ${fee:,.0f}.", "event": eid, "fee": fee}
    return {"status": "rejected", "reason": "unhandled"}


def _current_single(world):
    act = world.player_act
    best = None
    for rel in world.releases.values():
        if rel.act == act.id and rel.kind == "single" and rel.status == "released":
            if (world.date - dates.parse(rel.date)).days < 140 and (best is None or rel.date > best.date):
                best = rel
    return world.recordings[best.tracks[0]] if best else None

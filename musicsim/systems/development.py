"""A&R review and artist development: what labels hear in a master, what they do when they pass.

One review function serves every act (protagonist and NPCs alike). It separates *craft*
(melody, structure, production, vocal, arrangement) from *commercial potential* (hook,
singability, signature, accessibility, groove for dance styles, radio-format fit) and weighs them
by the label's own culture. A pass is not the end of the story. For a signed act without a
release, the label holds development meetings, proposes concrete next steps (remix, re-cut
vocal, a different master, new songs from its writers), checks in on a cadence, and eventually
loses patience. Nothing here makes a record better by fiat: remixes and re-cuts are new
recordings whose quality comes from the people, budget and luck, exactly like any other session.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates
from ..core.rng import Draws
from ..entities import Offer

COMP = ("melody", "hook", "structure", "lyric_craft", "depth", "singability")
REC = ("production", "vocal_delivery", "arrangement", "signature", "dance_hook", "accessibility")
WORDS = {
    "melody": ("the melody", "a strong melody"), "hook": ("the hook", "a sticky hook"),
    "structure": ("the song structure", "a well-built song"), "lyric_craft": ("the lyric", "a sharp lyric"),
    "depth": ("staying power", "staying power"), "singability": ("the chorus", "a sing-along chorus"),
    "production": ("the production", "the production"), "vocal_delivery": ("the lead vocal", "the vocal"),
    "arrangement": ("the arrangement", "the arrangement"), "signature": ("a distinctive sound", "a distinctive sound"),
    "dance_hook": ("the groove", "the groove"), "accessibility": ("broad appeal", "broad appeal"),
}
REMEDY = {"production": "remix", "arrangement": "remix", "vocal_delivery": "recut_vocal",
          "melody": "new_song", "hook": "new_song", "structure": "new_song", "lyric_craft": "new_song",
          "singability": "new_song"}


def cfg(world) -> dict:
    return world.config.tree["development"]


# ------------------------------------------------------------------- review
def review_master(world, org, act, rec, context: str) -> dict:
    """The label's (noisy) assessment of a master as a single. Same maths for every act."""
    C = cfg(world)
    rt = world.markets[act.home_market] if act.home_market in world.markets else next(iter(world.markets.values()))
    ear = org.params.get("ear", 0.65) if org else 0.5
    size = org.params.get("size", 0.3) if org else 0.1
    risk = org.strategy.get("risk", 0.5) if org else 0.7
    focus = org.strategy.get("focus", {}) if org else {}
    dr = Draws(world.seed, "anr_review", org.id if org else act.id, rec.id, context)
    comp = world.compositions[rec.composition].attrs
    sigma = world.config["labels.ear_sigma"] * (1.6 - ear)
    obs = {}
    for k in COMP:
        obs[k] = float(np.clip(comp[k] + sigma * dr.normal(k), 0, 1))
    for k in REC:
        obs[k] = float(np.clip(rec.attrs[k] + sigma * dr.normal(k), 0, 1))
    g = rec.genre
    gi = rt.gidx.get(g, 0)
    groove = float(rt.centroids[gi][2])
    radio_fit = float(rt.format_aff[:, gi].max())
    focus_fit = float(focus.get(g, 0.2))
    craft = (0.22 * obs["melody"] + 0.10 * obs["structure"] + 0.08 * obs["lyric_craft"] + 0.22 * obs["production"]
             + 0.25 * obs["vocal_delivery"] + 0.13 * obs["arrangement"])
    dance_w = 0.10 if groove >= 0.7 else 0.03
    wsum = 0.30 + 0.12 + 0.12 + 0.10 + dance_w + 0.16
    commercial = (0.30 * obs["hook"] + 0.12 * obs["singability"] + 0.12 * obs["signature"] + 0.10 * obs["accessibility"]
                  + dance_w * obs["dance_hook"] + 0.16 * radio_fit) / wsum
    w_comm = float(np.clip(C["commercial_weight"] + 0.2 * (risk - 0.5), 0.3, 0.7))
    score = ((1 - w_comm) * craft + w_comm * commercial + C["track_record_weight"] * act.singles_power_o
             + C["focus_weight"] * (focus_fit - 0.5))
    threshold = C["threshold"] + C["size_strictness"] * (size - 1.0) - C["risk_leniency"] * (risk - 0.5)
    approve = score >= threshold
    weak = sorted((k for k in REMEDY if obs[k] < 0.5), key=lambda k: obs[k])[:3]
    strong = sorted((k for k in obs if obs[k] >= 0.68), key=lambda k: -obs[k])[:3]
    fit_notes = []
    if focus_fit < 0.4:
        fit_notes.append(f"{rt.genre_meta[g]['label']} isn't where this label's promotion is strongest")
    if radio_fit < 0.5:
        fit_notes.append("radio formats will be hard to win with this style")
    remedies = []
    for k in weak:
        r = REMEDY[k]
        if r not in remedies:
            remedies.append(r)
    if not approve and not remedies:
        remedies.append("new_song" if commercial < craft else "remix")
    return {"label": org.id if org else None, "recording": rec.id, "context": context,
            "score": round(score, 4), "threshold": round(threshold, 4), "approve": bool(approve),
            "margin": round(score - threshold, 4), "craft": round(craft, 4), "commercial": round(commercial, 4),
            "strengths": [WORDS[k][1] for k in strong], "weaknesses": [WORDS[k][0] for k in weak],
            "fit": fit_notes, "remedies": remedies, "observed": {k: round(v, 3) for k, v in obs.items()},
            "draws": dr.log}


def notes_text(rv: dict) -> str:
    parts = []
    if rv["strengths"]:
        parts.append("likes " + ", ".join(rv["strengths"]))
    if rv["weaknesses"]:
        parts.append("worried about " + ", ".join(rv["weaknesses"]))
    parts += rv["fit"]
    return "; ".join(parts) or "doesn't hear a hit"


def tier_for(rv: dict, act) -> str:
    if rv["margin"] > 0.12 or (rv["margin"] > 0.04 and act.singles_power_o > 0.4):
        return "high"
    return "standard" if rv["margin"] > 0.0 else "low"


# ------------------------------------------------------------- development
def state(world) -> dict:
    return world.flags.setdefault("development", {})


def _org(world, act):
    return world.orgs.get(f"org:{act.label}") if act.label else None


def _released_singles(world, act):
    return [r for r in world.releases.values() if r.act == act.id and r.kind == "single" and r.status == "released"]


def _anchor(world, act) -> dt.date:
    """When the label's patience clock started: last single release, else signing date."""
    rel = _released_singles(world, act)
    if rel:
        return max(dates.parse(r.date) for r in rel)
    c = world.contracts.get(act.contract) if act.contract else None
    return dates.parse(c.start) if c else world.date


def on_rejection(world, org, act, rec, rv: dict, causes=()) -> int:
    """The label passed on a single: give the notes, and set up a development meeting soon."""
    C = cfg(world)
    st = state(world)
    st["rejections"] = st.get("rejections", 0) + 1
    st["last_review"] = {k: rv[k] for k in ("recording", "strengths", "weaknesses", "fit", "remedies", "score",
                                             "threshold")} | {"date": world.date.isoformat(), "title": rec.title}
    dr = Draws(world.seed, "dev_meeting", act.id, rec.id, world.date.isoformat())
    days = C["meeting_after_rejection_days"][0] + int(dr.uniform("when") * (C["meeting_after_rejection_days"][1]
                                                                          - C["meeting_after_rejection_days"][0] + 1))
    when = world.date + dt.timedelta(days=days)
    eid = world.emit("labels", "label_review", [org.id, act.id, rec.id], {
        "title": rec.title, "decision": "pass", **{k: rv[k] for k in ("score", "threshold", "craft", "commercial",
                                                                    "strengths", "weaknesses", "fit", "remedies")},
        "meeting": when.isoformat()}, causes=list(causes), draws=rv["draws"] + dr.log)
    schedule_meeting(world, act, when, "after passing on \"" + rec.title + "\"", eid)
    anr = world.people.get(org.people.get("anr", ""))
    who = f"{anr.name} ({org.name} A&R)" if anr else f"{org.name}'s A&R"
    world.add_news(f"{who} passed on \"{rec.title}\" as a single: {notes_text(rv)}. A development meeting is set "
                   f"for {when.isoformat()}.", "label", [act.id, org.id, rec.id], tag="official", importance=0.85,
                   event_id=eid)
    if anr:
        world.remember(anr.id, f"Passed on \"{rec.title}\" by {act.name}: {notes_text(rv)}.", [act.id], -0.1, 0.6, eid)
    pid = act.members[0]["person"]
    world.remember(pid, f"{org.name} passed on \"{rec.title}\" as a single.", [org.id], -0.4, 0.8, eid)
    p = world.people[pid]
    p.wellbeing["morale"] = round(max(0.0, p.wellbeing.get("morale", 0.7) - 0.1), 3)
    return eid


def schedule_meeting(world, act, when: dt.date, why: str, eid=None):
    st = state(world)
    cur = st.get("meeting")
    if cur and cur >= world.date.isoformat() and cur <= when.isoformat():
        return
    world.schedule = [s for s in world.schedule if not (s["kind"] == "label_meeting" and s.get("act") == act.id)]
    world.schedule.append({"kind": "label_meeting", "date": when.isoformat(), "market": act.home_market, "act": act.id,
                           "venue": f"{world.orgs[f'org:{act.label}'].name} offices", "note": why, "event": eid})
    st["meeting"] = when.isoformat()


def meeting(world, market: str, act, item: dict):
    """Development meeting: the label re-hears unreleased masters and proposes concrete next steps."""
    org = _org(world, act)
    if org is None:
        return
    C = cfg(world)
    st = state(world)
    st["meetings"] = st.get("meetings", 0) + 1
    st["meeting"] = None
    n = st["meetings"]
    masters = [r for r in sorted(world.recordings.values(), key=lambda r: r.id)
               if r.act == act.id and r.status == "done" and not r.single_release]
    reviews = [review_master(world, org, act, r, f"meeting{n}") for r in masters]
    proposals = []
    ok = sorted([rv for rv in reviews if rv["approve"]], key=lambda rv: -rv["margin"])
    if ok:
        rv = ok[0]
        rec = world.recordings[rv["recording"]]
        proposals.append(_proposal(world, org, act, {"action": "release_master", "recording_id": rec.id,
                                                     "title": rec.title, "promo": tier_for(rv, act),
                                                     "label_notes": notes_text(rv)}))
    fund_left = _fund_left(world, act)
    for rv in sorted([rv for rv in reviews if not rv["approve"]], key=lambda rv: -rv["margin"])[:2]:
        rec = world.recordings[rv["recording"]]
        if "remix" in rv["remedies"] and fund_left > 8000:
            prod = _pick_producer(world, org, act, rec, fund_left * C["remix_fund_share"], exclude=rec.producers,
                                  fee_share=C["remix_fee_share"], max_budget=C["remix_max_studio"])
            if prod:
                person, fee, budget = prod
                proposals.append(_proposal(world, org, act, {
                    "action": "remix", "recording_id": rec.id, "title": rec.title, "producer": person.id,
                    "producer_name": person.name, "fee": fee, "budget": budget, "weeks": 3,
                    "label_notes": notes_text(rv), "recoupable": True}))
        if "recut_vocal" in rv["remedies"] and fund_left > 4000:
            prod = _pick_producer(world, org, act, rec, min(12000.0, fund_left * 0.3), exclude=())
            if prod:
                person, fee, budget = prod
                proposals.append(_proposal(world, org, act, {
                    "action": "recut_vocal", "recording_id": rec.id, "title": rec.title, "producer": person.id,
                    "producer_name": person.name, "fee": round(fee * 0.4, -2), "budget": round(min(budget, 5000), -2),
                    "weeks": 1, "label_notes": notes_text(rv), "recoupable": True}))
    if not ok:
        pitched = _label_pitches(world, org, act, C["label_pitches"], f"meeting{n}")
        if pitched:
            proposals.append({"offer_id": None, "action": "new_songs", "songs": pitched})
    nxt = world.date + dt.timedelta(weeks=C["checkin_weeks"])
    st["next_checkin"] = nxt.isoformat()
    eid = world.emit("labels", "development_meeting", [org.id, act.id], {
        "masters_reviewed": [{"title": world.recordings[rv["recording"]].title, "approve": rv["approve"],
                              "score": rv["score"], "threshold": rv["threshold"], "notes": notes_text(rv)}
                             for rv in reviews],
        "proposals": [p.get("action") for p in proposals], "next_checkin": nxt.isoformat(),
        "fund_left": round(fund_left)}, causes=[item.get("event")] if item.get("event") else [],
        draws=[d for rv in reviews for d in rv["draws"]])
    st["last_meeting"] = {"date": world.date.isoformat(), "reviews": [
        {"title": world.recordings[rv["recording"]].title, "verdict": "yes" if rv["approve"] else "no",
         "notes": notes_text(rv)} for rv in reviews], "proposals": proposals, "fund_left": round(fund_left)}
    summary = "; ".join(f"\"{world.recordings[rv['recording']].title}\": {'yes' if rv['approve'] else 'not yet'} "
                        f"({notes_text(rv)})" for rv in reviews) or "no finished masters to hear"
    opts = ", ".join(p.get("action").replace("_", " ") for p in proposals) or "keep writing and recording"
    world.add_news(f"Development meeting at {org.name}: {summary}. On the table: {opts}. Next check-in "
                   f"{nxt.isoformat()}.", "label", [act.id, org.id], tag="official", importance=0.9, event_id=eid)
    world.interrupts.append({"reason": "label_meeting", "event": eid})
    return eid


def _proposal(world, org, act, terms: dict) -> dict:
    oid = world.new_id("offer")
    off = Offer(id=oid, kind="label_proposal", source=org.id, target=act.id, terms=terms,
                created=world.date.isoformat(), expires=(world.date + dt.timedelta(days=30)).isoformat(),
                rationale=terms.get("label_notes", ""))
    world.offers[oid] = off
    world.pending.append({"id": oid, "kind": "label_proposal", "summary": f"{org.name} proposes: "
                          f"{terms['action'].replace('_', ' ')} \"{terms.get('title', '')}\"", "expires": off.expires})
    return {"offer_id": oid, **terms}


def _fund_left(world, act) -> float:
    c = world.contracts.get(act.contract) if act.contract else None
    fund = float(c.terms.get("recording_budget_per_album", 0)) if c else 0.0
    return max(0.0, fund * 1.15 - world.flags.get("recording_fund_used", 0.0))


def _pick_producer(world, org, act, rec, money: float, exclude=(), fee_share: float = 1.0,
                   max_budget: float = 30000.0):
    """The A&R department's producer suggestion: the strongest producer for this style who fits the
    remaining recording fund and is willing (the producer's own acceptance roll)."""
    from .acts import producer_accepts
    genre = rec.genre
    cands = []
    for p in world.people.values():
        if "producer" not in p.roles or p.id in exclude or (p.employer and p.employer != org.id):
            continue
        fee = (p.fee or 3000.0) * fee_share
        budget = min(max_budget, max(6000.0, money - fee))
        if fee + 6000 > money:
            continue
        fit = p.style_skill.get(genre, 0.5)
        cands.append((p.skills.get("production", 0.5) * (0.6 + 0.4 * fit), p.id, p, fee, budget))
    cands.sort(key=lambda c: (-c[0], c[1]))
    for _, pid, p, fee, budget in cands[:6]:
        ok, _, _ = producer_accepts(world, pid, act, fee, f"label_suggest#{rec.id}#{world.date.isoformat()}")
        if ok:
            return p, round(fee, -2), round(budget, -2)
    return None


def _label_pitches(world, org, act, n: int, key: str) -> list[dict]:
    """A&R sends songs from writers it works with (better connected labels reach better writers)."""
    from .acts import _title
    from .creative import write_composition
    size = org.params.get("size", 0.5)
    writers = sorted([p for p in world.people.values() if "songwriter" in p.roles and not p.historical],
                     key=lambda p: (-p.skills.get("songwriting", 0.5), p.id))
    pool = writers[: max(3, int(len(writers) * min(0.8, 0.25 + 0.35 * size)))]
    out = []
    for k in range(n):
        if not pool:
            break
        w = pool[int(Draws(world.seed, "label_pitch", org.id, act.id, key, k).uniform("w") * len(pool))]
        genre = act.genres[0] if act.genres else next(iter(world.markets.values())).data["generated"]["default_genre"]
        comp = write_composition(world, _title(world, f"labelpitch{key}{k}{act.id}"), [w.id], genre,
                                 key=f"labelpitch#{key}#{act.id}#{k}")
        comp.status = "pitched"
        comp.pitched_to = [act.id]
        ear = Draws(world.seed, "pitch_obs", comp.id)
        imp = {a: round(float(np.clip(v + 0.12 * ear.normal(a), 0, 1)), 2) for a, v in comp.attrs.items()}
        oid = world.new_id("offer")
        world.offers[oid] = Offer(id=oid, kind="song_pitch", source=w.id, target=act.id,
                                  terms={"composition": comp.id, "title": comp.title, "genre": genre, "writer": w.name,
                                         "deal": "writer keeps the publishing; earns mechanicals",
                                         "via": org.name, "impression": imp},
                                  created=world.date.isoformat(),
                                  expires=(world.date + dt.timedelta(days=42)).isoformat())
        out.append({"offer_id": oid, "title": comp.title, "writer": w.name})
    return out


def weekly(world, market: str):
    """Label initiative for the protagonist's act (NPC acts run their own release cycles)."""
    act = world.player_act
    if act is None or not act.label or act.home_market != market:
        return
    C = cfg(world)
    st = state(world)
    today = world.date
    org = _org(world, act)
    planned = any(r.act == act.id and r.status == "planned" for r in world.releases.values())
    in_progress = any(r.act == act.id and r.status == "in_production" for r in world.recordings.values())
    anchor = _anchor(world, act)
    idle_days = (today - anchor).days
    meeting_set = st.get("meeting") and st["meeting"] >= today.isoformat()
    if planned:
        return
    # a single still in its promotion run is "moving"
    singles = _released_singles(world, act)
    if singles and (today - max(dates.parse(r.date) for r in singles)).days < 7 * C["single_spacing_weeks"]:
        return
    # routine check-in when nothing is moving
    due = st.get("next_checkin") or (anchor + dt.timedelta(weeks=C["first_checkin_weeks"])).isoformat()
    if not meeting_set and not in_progress and today.isoformat() >= due:
        dr = Draws(world.seed, "dev_checkin", act.id, today.isoformat())
        when = today + dt.timedelta(days=3 + int(dr.uniform("d") * 5))
        schedule_meeting(world, act, when, "routine A&R check-in")
        eid = world.emit("labels", "checkin_scheduled", [org.id, act.id], {"date": when.isoformat(),
                                                                         "idle_days": idle_days}, draws=dr.log)
        world.add_news(f"{org.name}'s A&R department wants to hear where the record is: meeting on "
                       f"{when.isoformat()}.", "label", [act.id, org.id], tag="official", importance=0.6, event_id=eid)
    # patience: a warning, then a possible drop
    patience = C["patience_days"] * (1 + 6 * act.singles_power_o)
    if idle_days >= patience * C["warning_share"] and not st.get("warned_for") == anchor.isoformat():
        st["warned_for"] = anchor.isoformat()
        eid = world.emit("labels", "patience_warning", [org.id, act.id], {"idle_days": idle_days,
                                                                        "patience_days": round(patience)})
        world.add_news(f"{org.name} is losing patience: nothing releasable in {idle_days} days. Without a single "
                       "they can work, the label may not pick up its option.", "label", [act.id, org.id],
                       tag="official", importance=0.9, event_id=eid)
        world.interrupts.append({"reason": "label_warning", "event": eid})
    if idle_days >= patience:
        dr = Draws(world.seed, "dev_drop", act.id, today.isoformat())
        p_drop = float(np.clip(C["drop_hazard_weekly"] * (1.5 - org.strategy.get("risk", 0.5)), 0.01, 0.5))
        if dr.chance("drop", p_drop):
            drop(world, org, act, f"no releasable single in {idle_days} days", dr.log)


def drop(world, org, act, reason: str, draws=()):
    c = world.contracts.get(act.contract) if act.contract else None
    if c:
        c.status = "terminated"
        c.end = world.date.isoformat()
    if act.id in org.roster:
        org.roster.remove(act.id)
    act.label = None
    act.contract = None
    world.schedule = [s for s in world.schedule if not (s["kind"] == "label_meeting" and s.get("act") == act.id)]
    for o in world.offers.values():
        if o.target == act.id and o.kind == "label_proposal" and o.status == "open":
            o.status = "withdrawn"
    eid = world.emit("labels", "dropped", [org.id, act.id], {"reason": reason}, draws=list(draws))
    if world.player.get("act") == act.id:
        world.flags.pop("development", None)
        world.flags["recording_fund_used"] = 0.0
        world.pending = [p for p in world.pending if p.get("kind") != "label_proposal"]
        world.add_news(f"{org.name} has dropped {act.name} ({reason}). The masters stay with the label; the "
                       "unrecouped advance is not owed back.", "label", [act.id, org.id], tag="official",
                       importance=1.0, event_id=eid)
        world.interrupts.append({"reason": "dropped", "event": eid})
    return eid


def npc_patience(world, market: str):
    """Monthly: labels drop signed generated acts that have produced nothing releasable for too long."""
    if world.date.day > 7 or world.date.weekday() != 0:
        return
    C = cfg(world)
    for act in sorted(world.acts.values(), key=lambda a: a.id):
        if act.controller != "npc" or act.historical or not act.label or act.home_market != market:
            continue
        last = dates.parse(act.last_release) if act.last_release else None
        if last is None:
            continue
        idle = (world.date - last).days
        patience = C["patience_days"] * (1 + 6 * act.singles_power_o) * 1.3
        if idle >= patience:
            org = world.orgs[f"org:{act.label}"]
            dr = Draws(world.seed, "npc_drop", act.id, world.date.isoformat())
            if dr.chance("drop", 0.3):
                drop(world, org, act, f"no releasable single in {idle} days", dr.log)
                act.live_buzz = 0.05

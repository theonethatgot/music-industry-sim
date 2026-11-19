"""Record-company behaviour: promotion budgets, opportunity detection, video commissioning,
A&R scouting and contract offers. Labels act on their own observations only."""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates, rng
from ..core.rng import Draws
from ..entities import Contract, Offer
from .demand import window_slots

PROMO_WEEKS = 16


def label_orgs(world, market):
    return [o for o in sorted(world.orgs.values(), key=lambda o: o.id)
            if o.kind == "record_company" and o.market == market]


def week_units(world, market, rel) -> float:
    end_day = world.date.toordinal() - 1
    slots = window_slots(end_day, 7)
    if rel.kind == "single":
        T = world.tables[market]
        tot = 0.0
        for rid in rel.tracks:
            i = T.index.get(rid)
            if i is not None:
                tot += T.view("u_single")[i][:, slots].sum()
        return float(tot)
    AT = world.albums[market]
    i = AT.index.get(rel.id)
    return float(AT.view("u_album")[i][:, slots].sum()) if i is not None else 0.0


def weekly(world, market: str):
    cfg = world.config.tree["labels"]
    rt = world.markets[market]
    T = world.tables[market]
    today = world.date
    for org in label_orgs(world, market):
        lab = org.id.split(":", 1)[1]
        rels = [r for r in world.releases.values() if r.label == lab and r.status == "released"
                and r.market == market and r.kind == "single"
                and (today - dates.parse(r.date)).days < 7 * (PROMO_WEEKS + r.priority * 8)]
        for rel in sorted(rels, key=lambda r: r.id):
            _promote(world, market, org, rel, cfg, rt, T)
    # self-released records: the artist is their own (tiny) label
    selfrel = [r for r in world.releases.values() if r.label is None and r.status == "released"
               and r.market == market and r.kind == "single" and (today - dates.parse(r.date)).days < 7 * PROMO_WEEKS]
    for rel in sorted(selfrel, key=lambda r: r.id):
        _promote(world, market, None, rel, cfg, rt, T)


def _promote(world, market, org, rel, cfg, rt, T):
    rid = rel.tracks[0]
    i = T.index.get(rid)
    if i is None:
        return
    rec = world.recordings[rid]
    act = world.acts[rel.act]
    weeks_out = (world.date - dates.parse(rel.date)).days // 7
    observed = week_units(world, market, rel) * (1 + 0.05 * rng.normal(world.seed, "label_obs", rel.id, world.date.isoformat()))
    airplay = int(T.view("radio_tier")[i].sum())
    expected = max(500.0, rel.expectation * min(1.0, (weeks_out + 1) / 4))
    ratio = (observed + 4000 * airplay) / (expected + 4000 * 3)
    from .release import release_account
    account = org.id if org else release_account(world, rel)
    org_name = org.name if org else act.name
    size = org.params.get("size", 1.0) if org else 0.05
    st = (org.state if org else world.flags).setdefault("ratios", {})
    smooth = 0.5 * st.get(rel.id, ratio) + 0.5 * ratio
    st[rel.id] = round(smooth, 4)
    if weeks_out >= 2 and smooth > cfg["opportunity_up"] and rel.priority < 1.0:
        old = rel.priority
        rel.priority = round(min(1.0, rel.priority + 0.25), 3)
        extra = cfg["promo_by_tier"]["standard"] * 0.5 * size if org else 0.0
        rel.promo_budget += extra
        eid = world.emit("labels", "opportunity_reinvest", [account, rel.id, rel.act],
                         {"observed_week_units": round(observed), "expected": round(expected), "ratio": round(smooth, 2),
                          "priority": [old, rel.priority], "added_budget": round(extra)})
        if org and not rec.video and rt.V and _video_era(world, market):
            commission_video(world, market, rec, org, "standard", causes=[eid])
        if org and (world.player.get("act") == rel.act or act.singles_power_o > 0.3):
            world.add_news(f"{org_name} is stepping up promotion behind {act.name}'s \"{rec.title}\" after a "
                           f"stronger-than-expected response.", "industry", [rel.act, rid, org.id],
                           tag="reported", importance=0.55, event_id=eid)
            if world.player.get("act") == rel.act:
                world.interrupts.append({"reason": "label_reinvests", "event": eid})
    elif weeks_out >= 4 and smooth < cfg["opportunity_down"] and rel.priority > 0.15:
        old = rel.priority
        rel.priority = round(max(0.1, rel.priority - 0.2), 3)
        world.emit("labels", "opportunity_cut", [account, rel.id, rel.act],
                   {"observed_week_units": round(observed), "expected": round(expected), "ratio": round(smooth, 2),
                    "priority": [old, rel.priority]})
    # weekly promotion pressure: money spent with independent promoters / label staff
    spend = rel.promo_budget * cfg["weekly_radio_share"] * (0.5 + rel.priority)
    credit = 5e6 if org else 500.0
    spend = min(spend, max(0.0, world.ledger.balance(account) + credit))
    if spend > 0:
        world.ledger.transfer(world.date, account, "ext:promotion", spend, "promotion", rel.id)
    boost = 0.0
    for b in world.flags.get("promo_boosts", []):
        if b["song"] == rid and b["until"] >= world.date.isoformat():
            boost += b["amount"]
    pressure = min(1.0, spend / 30000.0 + boost)
    g = T.view("genre")[i]
    fits = rt.format_aff[:, g]
    T.view("radio_promo")[i] = np.where(fits >= 0.3, pressure * (0.6 + 0.4 * fits), 0.0)
    T.view("tv_promo")[i] = pressure * 0.8


def _video_era(world, market) -> bool:
    rt = world.markets[market]
    return any(rt.channel_valid(c, world.date) for c in rt.channel_ids)


def commission_video(world, market, rec, org, tier: str, causes=(), payer: str | None = None,
                     cost: float | None = None):
    cfg = world.config.tree["labels"]
    if cost is None:
        cost = cfg["video_cost"][tier] * (org.params.get("size", 1.0) ** 0.5 if org else 1.0)
    dr = Draws(world.seed, "video_make", rec.id)
    q = float(np.clip(0.35 + 0.35 * (1 - np.exp(-cost / 80000)) + 0.1 * dr.normal("q") +
                      0.15 * world.acts[rec.act].flags.get("visual", 0.5), 0.05, 1.0))
    rec.video = {"quality": round(q, 4), "cost": round(cost), "date": world.date.isoformat()}
    acct = payer or (org.id if org else "ext:unknown")
    world.ledger.transfer(world.date, acct, "ext:video_production", cost, "video", rec.id)
    T = world.tables[market]
    i = T.index.get(rec.id)
    if i is not None:
        T.view("video_q")[i] = q
    act = world.acts[rec.act]
    if act.contract and world.contracts.get(act.contract):
        act.unrecouped -= 0.5 * cost          # half of video costs typically recoupable (tier C)
    eid = world.emit("labels", "video_commissioned", [rec.id, rec.act] + ([org.id] if org else []),
                     {"tier": tier, "cost": round(cost), "quality": round(q, 3)}, causes=causes, draws=dr.log)
    return eid


# ------------------------------------------------------------------ A&R ----
def potential_true(world, act) -> float:
    ps = [world.people[m["person"]] for m in act.members if m["person"] in world.people] or []
    if not ps:
        return 0.3
    sk = lambda k: max(p.skills.get(k, 0.4) for p in ps)
    demo = act.flags.get("demo_quality", 0.4)
    return (0.33 * sk("vocal") + 0.2 * sk("performance") + 0.15 * sk("look") + 0.12 * sk("songwriting")
            + 0.12 * demo + 0.08 * min(1.0, act.live_buzz * 2))


def evaluate(world, org, act, context: str, bonus: float = 0.0) -> dict:
    cfg = world.config.tree["labels"]
    ear = org.params.get("ear", 0.65)
    dr = Draws(world.seed, "anr", org.id, act.id, context, world.date.isoformat())
    true = potential_true(world, act) + bonus
    obs = true + dr.normal("ear") * cfg["ear_sigma"] * (1.6 - ear)
    focus = org.strategy.get("focus", {})
    fit = max([focus.get(g, 0.2) for g in act.genres] or [0.2])
    risk = org.strategy.get("risk", 0.5)
    size = org.params.get("size", 1.0)
    value = obs * (0.75 + 0.25 * fit)
    threshold = cfg["offer_threshold"] + 0.08 * (1 - risk) + 0.04 * min(size, 1.5)
    # interest is not commitment: rosters are finite, and a label signs only a few new acts a year
    commit = dr.chance("roster_slot", 0.25 + 0.4 * risk) if value > threshold else False
    return {"label": org.id, "observed_potential": round(obs, 3), "fit": round(fit, 3), "value": round(value, 3),
            "threshold": round(threshold, 3), "impressed": value > threshold, "interested": commit, "draws": dr.log}


def make_offer(world, org, act, ev: dict, causes=()) -> Offer:
    size = org.params.get("size", 1.0)
    obs = ev["observed_potential"]
    rt = next(iter(world.markets.values()))
    norms = rt.data.get("royalty_norms", {})
    terms = {
        "type": "recording_contract",
        "advance": float(round(15000 + 110000 * max(0.0, obs - 0.4) * size, -3)),
        "royalty_rate": round(norms.get("new_artist", 0.10) + (0.01 if obs > 0.72 else 0.0), 3),
        "firm_albums": 1,
        "option_albums": 4,
        "recording_budget_per_album": float(round(70000 + 160000 * size * max(0.2, obs), -3)),
        "video_recoupable_share": 0.5,
        "term": "1 album firm + 4 label options",
    }
    oid = world.new_id("offer")
    off = Offer(id=oid, kind="recording_contract", source=org.id, target=act.id, terms=terms,
                created=world.date.isoformat(), expires=(world.date + dt.timedelta(days=21)).isoformat(),
                rationale=f"A&R rated observed potential {obs:.2f} vs bar {ev['threshold']:.2f}", causes=list(causes))
    world.offers[oid] = off
    eid = world.emit("labels", "offer_made", [org.id, act.id, oid], {"terms": terms, "evaluation": {
        k: v for k, v in ev.items() if k != "draws"}}, causes=causes, draws=ev.get("draws"))
    off.causes.append(eid)
    if world.player.get("act") == act.id:
        world.pending.append({"id": oid, "kind": "offer", "summary": f"{org.name} offers a recording contract",
                              "expires": off.expires})
        world.interrupts.append({"reason": "offer", "offer": oid})
        world.add_news(f"{org.name} has made an offer to sign {act.name}.", "industry", [act.id, org.id],
                       tag="official", importance=0.9, event_id=eid)
    return off


def scout(world, market: str):
    """Periodic A&R sweep over unsigned acts with some local buzz."""
    cfg = world.config.tree["labels"]
    week = world.date.toordinal() // 7
    if week % cfg["scout_interval_weeks"]:
        return
    unsigned = [a for a in sorted(world.acts.values(), key=lambda a: a.id)
                if a.active and not a.label and a.home_market == market and a.live_buzz > 0.08
                and a.controller == "npc"]
    for org in label_orgs(world, market):
        size = org.params.get("size", 1.0)
        if not rng.chance(world.seed, min(0.9, 0.25 * size + 0.1), "scout_active", org.id, week):
            continue
        for act in unsigned:
            if not rng.chance(world.seed, 0.15, "scout_sees", org.id, act.id, week):
                continue
            ev = evaluate(world, org, act, "scouting")
            if ev["interested"]:
                make_offer(world, org, act, ev)


def showcase(world, market: str, act, item: dict):
    """An act performs for invited A&R staff; each attending label evaluates independently."""
    perf = np.mean([world.people[m["person"]].skills.get("performance", 0.5) for m in act.members
                    if m["person"] in world.people] or [0.5])
    dr = Draws(world.seed, "showcase", act.id, item["date"])
    night = float(np.clip(perf + 0.12 * dr.normal("night"), 0, 1))
    attending = []
    for org in label_orgs(world, market):
        focus = org.strategy.get("focus", {})
        fit = max([focus.get(g, 0.1) for g in act.genres] or [0.1])
        p = min(0.6, 0.04 + 0.30 * fit * min(1.0, org.params.get("size", 1.0)))
        if dr.chance(f"attend:{org.id}", p):
            attending.append(org)
    eid = world.emit("labels", "showcase", [act.id] + [o.id for o in attending],
                     {"venue": item.get("venue"), "performance_on_the_night": round(night, 3),
                      "labels_attending": [o.name for o in attending]}, draws=dr.log)
    act.live_buzz = min(1.0, act.live_buzz + 0.1 + 0.2 * night)
    results = []
    for org in attending:
        ev = evaluate(world, org, act, "showcase", bonus=0.12 * (night - 0.5))
        results.append({"label": org.name, "interested": ev["interested"], "impressed": ev["impressed"]})
        rep = org.people.get("anr")
        if rep:
            world.remember(rep, f"Saw {act.name} at a showcase; {'impressed' if ev['impressed'] else 'not convinced'}.",
                           [act.id], valence=0.3 if ev["impressed"] else -0.1, salience=0.4, event_id=eid)
            r = world.rel(rep, act.members[0]["person"])
            r["affinity"] = round(r["affinity"] + (0.1 if ev["impressed"] else 0.0), 3)
            if ev["impressed"] and not ev["interested"] and world.player.get("act") == act.id:
                world.add_news(f"Word is that {org.name}'s A&R liked your set but isn't ready to commit.",
                               "industry", [act.id, org.id], tag="rumour", importance=0.6, event_id=eid)
            r["history"].append(eid)
        if ev["interested"]:
            make_offer(world, org, act, ev, causes=[eid])
        else:
            world.emit("labels", "pass", [org.id, act.id], {"evaluation": {k: v for k, v in ev.items() if k != "draws"}},
                       causes=[eid], draws=ev["draws"], public=False)
    if world.player.get("act") == act.id:
        world.interrupts.append({"reason": "showcase", "event": eid})
        names = ", ".join(o.name for o in attending) or "no label A&R staff"
        world.add_news(f"Showcase at {item.get('venue') or 'the club'}: {names} came to watch "
                       f"(your performance on the night: {['rough', 'shaky', 'solid', 'strong', 'electric'][min(4, int(night * 5))]}).",
                       "showcase", [act.id], tag="official", importance=0.85, event_id=eid)
    return eid, results


def sign(world, org, act, terms: dict, causes=()) -> Contract:
    cid = world.new_id("contract")
    c = Contract(id=cid, kind="recording_contract", parties=[org.id, act.id], terms=terms,
                 start=world.date.isoformat())
    world.contracts[cid] = c
    lab = org.id.split(":", 1)[1]
    act.label = lab
    act.contract = cid
    act.unrecouped = -float(terms.get("advance", 0.0))
    if act.stage == "aspiring":
        act.stage = "rookie"
    org.roster.append(act.id)
    adv = float(terms.get("advance", 0.0))
    members = [m["person"] for m in act.members] or [act.id]
    for p in members:
        world.ledger.transfer(world.date, org.id, p, adv / len(members), "advance", cid)
    eid = world.emit("labels", "signed", [org.id, act.id, cid], {"terms": terms}, causes=causes)
    if world.player.get("act") == act.id or act.historical:
        world.add_news(f"{act.name} signs with {org.name}.", "industry", [act.id, org.id], tag="official",
                       importance=0.8 if world.player.get("act") == act.id else 0.4, event_id=eid)
    return c


def npc_offer_responses(world):
    """Autonomous acts accept the best open offer by their own utility."""
    by_act: dict[str, list[Offer]] = {}
    for off in sorted(world.offers.values(), key=lambda o: o.id):
        if off.status != "open":
            continue
        if dates.parse(off.expires) < world.date:
            off.status = "expired"
            if world.player.get("act") == off.target:
                world.pending = [p for p in world.pending if p.get("id") != off.id]
                world.emit("labels", "offer_expired", [off.source, off.target, off.id], {})
            continue
        act = world.acts.get(off.target)
        if act is None or act.controller != "npc" or off.kind != "recording_contract":
            continue
        by_act.setdefault(act.id, []).append(off)
    for aid, offers in sorted(by_act.items()):
        act = world.acts[aid]
        if act.label:
            continue

        def utility(o):
            org = world.orgs[o.source]
            return o.terms["advance"] / 50000 + org.params.get("size", 1.0) + 3 * o.terms["royalty_rate"]
        best = max(offers, key=lambda o: (utility(o), o.id))
        best.status = "accepted"
        sign(world, world.orgs[best.source], act, best.terms, causes=best.causes)
        for o in offers:
            if o is not best:
                o.status = "declined"

"""Autonomous act behaviour: real artists' soft historical intents, fictional artists'
release cycles, producer hiring and the song market. The protagonist's act is driven by
player commands instead, but every resolution function here is shared."""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates, rng
from ..core.rng import Draws
from ..entities import Release
from .creative import produce_recording, write_composition

LEAD_DAYS = 56   # how far ahead intents are prepared


def release_day(world, market: str, target: dt.date) -> dt.date:
    wd = world.markets[market].release_weekday(target)
    return dates.next_weekday(target, wd)


def producer_accepts(world, producer_id: str, act, fee_offered: float, key: str) -> tuple[bool, float, list]:
    """A producer's own decision to take a job: money vs. the act's standing vs. their own stature."""
    p = world.people.get(producer_id)
    if p is None:
        return False, 0.0, []
    fee = p.fee or 5000.0
    stature = p.skills.get("production", 0.5)
    act_draw = act.singles_power_o + 0.5 * max(0.0, act.momentum) + (0.2 if act.label else 0.0)
    money = min(2.0, fee_offered / max(1.0, fee))
    rel = world.relations.get(f"{producer_id}|{act.members[0]['person']}") if act.members else None
    bond = rel["affinity"] if rel else 0.0
    p_yes = float(np.clip(0.25 + 0.40 * money + 0.6 * act_draw + 0.5 * bond - 0.6 * max(0.0, stature - 0.75), 0.02, 0.97))
    dr = Draws(world.seed, "producer_accepts", producer_id, act.id, key)
    ok = dr.chance("accept", p_yes)
    return ok, p_yes, dr.log


def _resolve_people(world, ids: list[str], act_id: str) -> list[str]:
    out = []
    for x in ids or []:
        if f"person:{x}" in world.people:
            out.append(f"person:{x}")
        elif f"act:{x}" in world.acts and world.acts[f"act:{x}"].members:
            out.append(world.acts[f"act:{x}"].members[0]["person"])
    return out


def _house_producer(world, label: str | None) -> list[str]:
    if label and f"org:{label}" in world.orgs:
        hp = world.orgs[f"org:{label}"].people.get("house_producer")
        if hp:
            return [hp]
    return []


def weekly(world, market: str):
    for act in sorted(world.acts.values(), key=lambda a: a.id):
        if not act.active or act.controller != "npc":
            continue
        if act.historical:
            _historical_intents(world, market, act)
        elif act.label:
            _fictional_cycle(world, market, act)
        else:
            _unsigned(world, act)


# ----------------------------------------------------------- historical ----
def _historical_intents(world, market, act):
    today = world.date
    for k, it in enumerate(act.intents):
        if it.get("state"):
            continue
        when = _intent_date(it)
        if when is None:
            it["state"] = "invalid"
            continue
        if it["kind"] == "signing":
            if today >= when:
                _resolve_signing(world, act, it, k)
            continue
        if (when - today).days > LEAD_DAYS:
            continue
        if when < today - dt.timedelta(days=28):
            it["state"] = "lapsed"           # before the simulated world could prepare it
            continue
        if not act.label:
            it["state"] = "no_label"
            world.emit("history", "intent_dropped", [act.id], {"intent": it.get("title"), "reason": "act unsigned in this world"})
            continue
        dr = Draws(world.seed, "intent", act.id, k)
        p_go = 0.93 - 0.25 * max(0.0, -act.momentum)
        if not dr.chance("happens", p_go):
            it["state"] = "cancelled"
            world.emit("history", "intent_cancelled", [act.id],
                       {"title": it.get("title"), "kind": it["kind"], "p": round(p_go, 3)}, draws=dr.log)
            continue
        slip = int(round(dr.normal("slip") * 9))
        date = release_day(world, market, max(today + dt.timedelta(days=7), when + dt.timedelta(days=slip)))
        if it["kind"] == "single":
            rec = _intent_recording(world, act, it, k, market)
            rel = plan_single(world, market, act, rec, date, tier=_tier_for(act), historical=True,
                              intent=f"{act.id}#{k}")
            it["state"] = "planned"
            it["release"] = rel.id
        elif it["kind"] == "album":
            rel = _plan_album_from_intent(world, market, act, it, k, date)
            it["state"] = "planned"
            it["release"] = rel.id


def _intent_date(it):
    d = it.get("date")
    if d is None:
        return None
    s = str(d)
    if len(s) == 7:
        s += "-01"
    try:
        base = dates.parse(s)
    except ValueError:
        return None
    return base


def _resolve_signing(world, act, it, k):
    from .labels import sign
    org = world.orgs.get(f"org:{it.get('label')}")
    dr = Draws(world.seed, "intent_signing", act.id, k)
    if act.label or org is None:
        it["state"] = "moot"
        return
    if dr.chance("signs", 0.85):
        size = org.params.get("size", 1.0)
        terms = {"type": "recording_contract", "advance": 60000.0 * size, "royalty_rate": 0.11, "firm_albums": 1,
                 "option_albums": 4, "recording_budget_per_album": 200000.0 * size, "video_recoupable_share": 0.5}
        sign(world, org, act, terms)
        act.singles_power_o = max(act.singles_power_o, 0.25)
        it["state"] = "signed"
    else:
        it["state"] = "not_signed"
        world.emit("history", "intent_diverged", [act.id, org.id], {"intent": "signing", "note": it.get("note")},
                   draws=dr.log)


def _intent_recording(world, act, it, k, market=None):
    market = market or next(iter(world.markets))
    # reuse a recording made earlier (e.g. for an album) with the same title
    for rec in world.recordings.values():
        if rec.act == act.id and rec.title == it.get("title") and not rec.single_release:
            return rec
    writers = _resolve_people(world, it.get("writers"), act.id) or [m["person"] for m in act.members[:1]]
    producers = _resolve_people(world, it.get("producers"), act.id) or _house_producer(world, act.label)
    genre = it.get("genre") or (act.genres[0] if act.genres else _default_genre(world, market))
    comp = write_composition(world, it["title"], writers, genre, key=f"{act.id}#{k}", hist=it.get("hist"), historical=True)
    size = world.orgs[f"org:{act.label}"].params.get("size", 1.0) if act.label else 0.5
    rec = produce_recording(world, comp, act.id, producers, genre, budget=40000 + 60000 * size, weeks=4,
                            key=f"{act.id}#{k}", hist=it.get("hist"), controversy=it.get("controversy"),
                            payer=f"org:{act.label}" if act.label else act.id, historical=True)
    rec.status = "done"
    rec.completed = world.date.isoformat()
    return rec


def _plan_album_from_intent(world, market, act, it, k, date):
    tracks = []
    focus = []
    for title in it.get("singles", []):
        rec = next((r for r in world.recordings.values() if r.act == act.id and r.title == title), None)
        if rec is None:
            j, sub = next(((j, x) for j, x in enumerate(act.intents) if x.get("title") == title and x["kind"] == "single"),
                          (None, None))
            if sub is not None:
                rec = _intent_recording(world, act, sub, j, market)
        if rec is not None:
            tracks.append(rec.id)
            focus.append(rec.id)
    n_tracks = int(it.get("tracks", 10))
    genre = act.genres[0] if act.genres else _default_genre(world, market)
    producers = _house_producer(world, act.label)
    writers = [m["person"] for m in act.members[:1]]
    for j in range(max(0, n_tracks - len(tracks))):
        comp = write_composition(world, f"{it['title']} (album track {j + 1})", writers, genre, key=f"{act.id}#{k}#t{j}")
        rec = produce_recording(world, comp, act.id, producers, genre, budget=15000, weeks=2,
                                key=f"{act.id}#{k}#t{j}", payer=f"org:{act.label}")
        rec.status = "done"
        tracks.append(rec.id)
    return plan_album(world, market, act, it["title"], tracks, focus, date, tier=_tier_for(act), historical=True,
                      intent=f"{act.id}#{k}")


def _tier_for(act) -> str:
    return "high" if act.singles_power_o > 0.45 else "standard" if act.singles_power_o > 0.12 else "low"


# ------------------------------------------------------------ planning ----
def plan_single(world, market, act, rec, date, tier="standard", historical=False, intent=None,
                commercial=True, promo_budget=None, payer=None) -> Release:
    cfg = world.config.tree["labels"]
    org = world.orgs.get(f"org:{act.label}") if act.label else None
    size = org.params.get("size", 1.0) if org else 0.0
    rid = world.new_id("rel")
    budget = promo_budget if promo_budget is not None else cfg["promo_by_tier"][tier] * max(0.15, size)
    priority = {"low": 0.3, "standard": 0.5, "high": 0.8}[tier]
    rel = Release(id=rid, act=act.id, label=act.label, kind="single", title=rec.title, tracks=[rec.id], focus=[rec.id],
                  market=market, date=date.isoformat(), promo_tier=tier, promo_budget=round(budget), priority=priority,
                  historical=historical, intent=intent, commercial=commercial)
    world.releases[rid] = rel
    rec.single_release = rid
    if tier in ("standard", "high") and org and not rec.video:
        from .labels import _video_era, commission_video
        if _video_era(world, market):
            commission_video(world, market, rec, org, tier)
    world.emit("release", "single_planned", [rid, act.id, rec.id],
               {"title": rec.title, "date": rel.date, "tier": tier, "promo_budget": rel.promo_budget})
    return rel


def plan_album(world, market, act, title, tracks, focus, date, tier="standard", historical=False, intent=None) -> Release:
    rid = world.new_id("rel")
    priority = {"low": 0.3, "standard": 0.5, "high": 0.8}[tier]
    rel = Release(id=rid, act=act.id, label=act.label, kind="album", title=title, tracks=list(tracks), focus=list(focus),
                  market=market, date=date.isoformat(), promo_tier=tier, priority=priority, historical=historical,
                  intent=intent)
    world.releases[rid] = rel
    world.emit("release", "album_planned", [rid, act.id], {"title": title, "date": rel.date, "tracks": len(tracks)})
    return rel


# ------------------------------------------------------------ fictional ----
def _fictional_cycle(world, market, act):
    today = world.date
    planned = [r for r in world.releases.values() if r.act == act.id and r.status == "planned"]
    if planned:
        return
    marks = [x for x in (act.last_release, act.flags.get("last_attempt")) if x]
    last = dates.parse(max(marks)) if marks else None
    wk = (today - last).days / 7 if last else 999
    jitter = rng.uniform(world.seed, "cadence", act.id, max(marks) if marks else "none")
    if wk < act.cadence_weeks * (0.7 + 0.6 * jitter):
        return
    my_singles = [r for r in world.releases.values() if r.act == act.id and r.kind == "single" and r.status == "released"]
    my_albums = [r for r in world.releases.values() if r.act == act.id and r.kind == "album"]
    # album after a single that did well (or every third single)
    done_since_album = [r for r in my_singles if not my_albums or r.date > max(a.date for a in my_albums)]
    from .charts import main_chart
    stats = main_chart(world, market, "song").get("stats", {})
    hit = any(stats.get(r.tracks[0], {}).get("peak", 999) <= 40 for r in done_since_album)
    charted = any(stats.get(r.tracks[0], {}).get("peak", 999) <= 75 for r in done_since_album)
    if done_since_album and (hit or (charted and len(done_since_album) >= 2)):
        _plan_npc_album(world, market, act, done_since_album)
        return
    key = f"{act.id}#{today.isoformat()}"
    genre = act.genres[0] if act.genres else _default_genre(world, market)
    writers = [m["person"] for m in act.members[:1]] if rng.chance(world.seed, 0.5, "selfwrite", key) else []
    comp = write_composition(world, _title(world, key, market), writers, genre, key=key)
    org = world.orgs[f"org:{act.label}"]
    producers = _house_producer(world, act.label)
    size = org.params.get("size", 1.0)
    rec = produce_recording(world, comp, act.id, producers, genre, budget=15000 + 45000 * size, weeks=3, key=key,
                            payer=org.id)
    rec.status = "done"
    rec.completed = today.isoformat()
    # A&R listens (the same review the protagonist's label uses) and may shelve weak material
    from .development import review_master, tier_for
    rv = review_master(world, org, act, rec, "single")
    act.flags["last_attempt"] = today.isoformat()
    study = world.config.tree["development"].get("study_release_all")
    if not rv["approve"] and not study:
        world.emit("labels", "shelved", [org.id, act.id, rec.id], {"score": rv["score"], "threshold": rv["threshold"]},
                   draws=rv["draws"])
        return
    tier = ("standard" if study else tier_for(rv, act)) if rv["approve"] or study else "low"
    rel = plan_single(world, market, act, rec, release_day(world, market, today + dt.timedelta(days=35)), tier=tier)
    rel.review = {k: rv[k] for k in ("score", "threshold", "approve", "margin", "craft", "commercial")}


def _plan_npc_album(world, market, act, singles):
    today = world.date
    key = f"{act.id}#album#{today.isoformat()}"
    genre = act.genres[0] if act.genres else _default_genre(world, market)
    tracks = [r.tracks[0] for r in singles]
    for j in range(10 - len(tracks)):
        comp = write_composition(world, f"Album track {j + 1}", [], genre, key=f"{key}#{j}")
        rec = produce_recording(world, comp, act.id, _house_producer(world, act.label), genre, budget=10000, weeks=1,
                                key=f"{key}#{j}", payer=f"org:{act.label}")
        rec.status = "done"
        tracks.append(rec.id)
    title = world.recordings[singles[0].tracks[0]].title
    plan_album(world, market, act, title, tracks, [r.tracks[0] for r in singles],
               release_day(world, market, today + dt.timedelta(days=28)), tier=_tier_for(act))
    act.last_release = today.isoformat()


def _unsigned(world, act):
    """Unsigned acts gig locally; buzz drifts with talent and luck."""
    wk = world.date.toordinal() // 7
    perf = np.mean([world.people[m["person"]].skills.get("performance", 0.5) for m in act.members
                    if m["person"] in world.people] or [0.5])
    drift = 0.01 * (perf - 0.45) + 0.02 * rng.normal(world.seed, "buzz", act.id, wk)
    act.live_buzz = float(np.clip(act.live_buzz * 0.98 + drift, 0, 1))


def _default_genre(world, market) -> str:
    return world.markets[market].data["generated"]["default_genre"]


def _title(world, key, market=None):
    market = market or next(iter(world.markets))
    tw = world.markets[market].data["generated"]["title_words"]
    a = rng.choice(world.seed, tw["a"], "title_a", key)
    b = rng.choice(world.seed, tw["b"], "title_b", key)
    pat = rng.choice(world.seed, tw["patterns"], "title_form", key)
    return pat.format(a=a, b=b) if a != b else f"{a} {b}"


# ---------------------------------------------------------- song market ----
def song_market(world, market: str):
    """Every four weeks, songwriters pitch new songs to the protagonist (more if signed or rising)."""
    act = world.player_act
    if act is None or (world.date.toordinal() // 7) % 4:
        return
    writers = [p for p in sorted(world.people.values(), key=lambda p: p.id)
               if "songwriter" in p.roles and not p.historical]
    real = [p for p in sorted(world.people.values(), key=lambda p: p.id)
            if p.historical and p.skills.get("songwriting", 0) > 0.85 and "producer" in p.roles]
    n = 2 + (1 if act.label else 0) + (1 if act.singles_power_o > 0.3 else 0)
    key = world.date.isoformat()
    from ..entities import Offer
    for k in range(n):
        pool = writers
        if real and act.singles_power_o > 0.35 and rng.chance(world.seed, 0.25, "realpitch", key, k):
            pool = real
        if not pool:
            return
        w = rng.choice(world.seed, pool, "pitch_writer", key, k)
        genre = rng.choice(world.seed, act.genres or [_default_genre(world, market)], "pitch_genre", key, k)
        comp = write_composition(world, _title(world, f"pitch{key}{k}", market), [w.id], genre, key=f"pitch#{key}#{k}")
        comp.status = "pitched"
        comp.pitched_to = [act.id]
        noise = {a: round(float(np.clip(v + 0.12 * rng.normal(world.seed, "pitch_obs", comp.id, a), 0, 1)), 2)
                 for a, v in comp.attrs.items()}
        oid = world.new_id("offer")
        world.offers[oid] = Offer(id=oid, kind="song_pitch", source=w.id, target=act.id,
                                  terms={"composition": comp.id, "title": comp.title, "genre": genre,
                                         "writer": w.name, "deal": "writer keeps the publishing; earns mechanicals",
                                         "impression": noise},
                                  created=key, expires=(world.date + dt.timedelta(days=42)).isoformat())
        world.emit("song_market", "song_pitched", [w.id, act.id, comp.id, oid], {"title": comp.title, "genre": genre})

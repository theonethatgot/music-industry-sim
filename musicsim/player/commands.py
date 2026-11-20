"""Player decisions: schema-validated commands that resolve through the same systems NPCs use.

Every command is logged (command log) with the sim date, so a campaign can be replayed
exactly: state = f(scenario, seed, ordered commands).
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates, rng
from ..systems import acts as acts_sys
from ..systems import labels as labels_sys
from ..systems.creative import describe, produce_recording, write_composition

PROMO = ["low", "standard", "high"]
VIDEO = ["none", "low", "standard", "high"]
SKILLS = ["vocal", "performance", "songwriting", "media", "production"]
LIFESTYLE = ["modest", "comfortable", "lavish"]
SELF_PROMO = {"low": 1500, "standard": 4000, "high": 10000}
SELF_VIDEO = {"low": 2500, "standard": 6000, "high": 20000}


def _schema():
    return {
        "accept_offer": {"desc": "Accept an open offer (recording contract, song pitch, booking).",
                         "args": {"offer_id": {"type": "str", "required": True}}},
        "decline_offer": {"desc": "Decline an open offer.", "args": {"offer_id": {"type": "str", "required": True}}},
        "record_song": {"desc": "Book studio time to record a song with a producer. Takes studio_weeks; "
                                "quality comes from the people involved, the budget and time, not the description.",
                        "args": {"title": {"type": "str", "required": False},
                                 "song": {"type": "str", "required": True,
                                          "desc": "a composition id from your songbook, or 'write_own'"},
                                 "cowriter": {"type": "str", "required": False, "desc": "person id"},
                                 "producer": {"type": "str", "required": True, "desc": "person id"},
                                 "genre": {"type": "enum", "required": True, "enum": "genres"},
                                 "studio_weeks": {"type": "int", "required": True, "min": 1, "max": 8},
                                 "budget": {"type": "float", "required": True, "min": 0, "max": 500000,
                                            "desc": "studio, musicians and mixing (USD), excluding the producer's fee"},
                                 "fee_offer": {"type": "float", "required": False, "min": 0,
                                               "desc": "fee offered to the producer (defaults to their usual fee)"},
                                 "ambition": {"type": "float", "required": False, "min": 0, "max": 1},
                                 "mood": {"type": "float", "required": False, "min": -1, "max": 1}}},
        "release_single": {"desc": "Release a finished recording as a single (label approval needed if signed).",
                           "args": {"recording_id": {"type": "str", "required": True},
                                    "date": {"type": "date", "required": False},
                                    "promo": {"type": "enum", "required": True, "enum": PROMO},
                                    "video": {"type": "enum", "required": False, "enum": VIDEO}}},
        "release_album": {"desc": "Release an album of at least 6 finished recordings.",
                          "args": {"title": {"type": "str", "required": True},
                                   "recording_ids": {"type": "list", "required": True},
                                   "date": {"type": "date", "required": False},
                                   "promo": {"type": "enum", "required": False, "enum": PROMO}}},
        "gig": {"desc": "Play local club dates: income, live buzz (which A&R notices) and stagecraft.",
                "args": {"weeks": {"type": "int", "required": True, "min": 1, "max": 12},
                         "nights_per_week": {"type": "int", "required": True, "min": 1, "max": 5}}},
        "train": {"desc": "Lessons or practice to improve a skill.",
                  "args": {"skill": {"type": "enum", "required": True, "enum": SKILLS},
                           "weeks": {"type": "int", "required": True, "min": 1, "max": 12},
                           "spend_per_week": {"type": "float", "required": False, "min": 0, "max": 5000}}},
        "promote": {"desc": "Personal promotion of a released single.",
                    "args": {"recording_id": {"type": "str", "required": True},
                             "kind": {"type": "enum", "required": True, "enum": ["radio_tour", "club_tour", "press_tour"]},
                             "weeks": {"type": "int", "required": True, "min": 1, "max": 6}}},
        "set_day_job": {"desc": "Keep or quit the day job.", "args": {"active": {"type": "bool", "required": True}}},
        "set_lifestyle": {"desc": "Spending level.", "args": {"level": {"type": "enum", "required": True, "enum": LIFESTYLE}}},
        "rest": {"desc": "Protected time off to recover energy. Club dates and lessons inside the window are "
                         "cancelled (and resume afterwards) unless keep_bookings is true.",
                 "args": {"weeks": {"type": "int", "required": True, "min": 1, "max": 8},
                          "keep_bookings": {"type": "bool", "required": False}}},
        "cancel_bookings": {"desc": "Cancel upcoming routine bookings (club dates, lessons) from today.",
                            "args": {"kind": {"type": "enum", "required": True,
                                              "enum": ["gigs", "training", "all_routine"]}}},
        "set_policy": {"desc": "Standing orders for routine work your team handles without asking you.",
                       "args": {"gigs_when_idle": {"type": "int", "required": False, "min": 0, "max": 5,
                                                   "desc": "club nights/week to keep booked when nothing else is on (0 = off)"},
                                "training_when_idle": {"type": "enum", "required": False, "enum": SKILLS + ["none"]},
                                "training_spend_per_week": {"type": "float", "required": False, "min": 0, "max": 2000},
                                "manager_may_book_media": {"type": "bool", "required": False},
                                "manager_may_book_gigs": {"type": "bool", "required": False},
                                "rest_when_exhausted": {"type": "bool", "required": False}}},
        "hire_manager": {"desc": "Offer a manager you know a management deal (they decide whether to take you on).",
                         "args": {"person_id": {"type": "str", "required": True},
                                  "commission": {"type": "float", "required": True, "min": 0.05, "max": 0.25}}},
        "fire_manager": {"desc": "End your management deal.", "args": {}},
    }


SCHEMA = _schema()


# ------------------------------------------------------------ validation
def validate(world, cmd: dict) -> list[str]:
    errs = []
    if not isinstance(cmd, dict) or "command" not in cmd:
        return ["each decision needs a 'command' field"]
    name = cmd["command"]
    if name not in SCHEMA:
        return [f"unknown command '{name}' (valid: {', '.join(SCHEMA)})"]
    args = cmd.get("args", {}) or {}
    if not isinstance(args, dict):
        return [f"{name}: 'args' must be an object"]
    spec = SCHEMA[name]["args"]
    for k in args:
        if k not in spec:
            errs.append(f"{name}: unexpected argument '{k}'")
    for k, s in spec.items():
        if k not in args:
            if s.get("required"):
                errs.append(f"{name}: missing required argument '{k}'")
            continue
        v = args[k]
        t = s["type"]
        ok = True
        if t == "str":
            ok = isinstance(v, str) and v != ""
        elif t == "int":
            ok = isinstance(v, int) and not isinstance(v, bool)
        elif t == "float":
            ok = isinstance(v, (int, float)) and not isinstance(v, bool)
        elif t == "bool":
            ok = isinstance(v, bool)
        elif t == "list":
            ok = isinstance(v, list)
        elif t == "date":
            try:
                dates.parse(v)
            except (ValueError, TypeError):
                ok = False
        elif t == "enum":
            options = s["enum"] if isinstance(s["enum"], list) else list(world.markets[world.player["market"]].genre_ids)
            ok = v in options
            if not ok:
                errs.append(f"{name}: '{k}' must be one of {options}")
                continue
        if not ok:
            errs.append(f"{name}: '{k}' must be of type {t}")
            continue
        if "min" in s and v < s["min"] or "max" in s and v > s["max"]:
            errs.append(f"{name}: '{k}' must be between {s.get('min')} and {s.get('max')}")
    return errs


# --------------------------------------------------------------- helpers
def _act(world):
    return world.player_act


def _pid(world):
    return world.player["person"]


def _market(world):
    return world.player["market"]


def _overlaps(world, start: str, end: str, exclusive_kinds=("radio_tour", "club_tour", "press_tour", "rest")) -> dict | None:
    for c in world.commitments:
        if c.get("who") != _pid(world) or c.get("done") or not c.get("exclusive"):
            continue
        if c["kind"] in exclusive_kinds and not (c["end"] < start or c["start"] > end):
            return c
    return None


def _commit(world, kind, weeks, label, exclusive, **extra):
    start = world.date.isoformat()
    end = (world.date + dt.timedelta(days=7 * weeks - 1)).isoformat()
    c = {"kind": kind, "who": _pid(world), "start": start, "end": end, "label": label, "exclusive": exclusive, **extra}
    world.commitments.append(c)
    return c


def _reject(reason, **kw):
    return {"status": "rejected", "reason": reason, **kw}


def _ok(summary, **kw):
    return {"status": "accepted", "summary": summary, **kw}


# --------------------------------------------------------------- dispatch
def apply(world, cmd: dict) -> dict:
    errs = validate(world, cmd)
    if errs:
        return {"status": "invalid", "errors": errs}
    fn = globals()[f"_cmd_{cmd['command']}"]
    return fn(world, cmd.get("args", {}) or {})


def _cmd_accept_offer(world, a):
    off = world.offers.get(a["offer_id"])
    act = _act(world)
    if off is None or off.target != act.id:
        return _reject("no such offer for you")
    if off.status != "open":
        return _reject(f"offer is {off.status}")
    if off.kind == "recording_contract":
        if act.label:
            return _reject("you are already signed; your contract is exclusive")
        org = world.orgs[off.source]
        off.status = "accepted"
        c = labels_sys.sign(world, org, act, off.terms, causes=off.causes)
        from .delegation import pay_commission
        pay_commission(world, float(off.terms.get("advance", 0.0)), "advance")
        for o in world.offers.values():
            if o.target == act.id and o.kind == "recording_contract" and o.status == "open":
                o.status = "declined"
        world.pending = [p for p in world.pending if p.get("kind") != "offer"]
        rep = org.people.get("anr")
        if rep:
            r = world.rel(rep, _pid(world))
            r["affinity"] = round(r["affinity"] + 0.15, 3)
            world.remember(rep, f"Signed {act.name} to {org.name}.", [act.id], valence=0.5, salience=0.7)
        world.remember(_pid(world), f"Signed a recording contract with {org.name}.", [org.id], valence=0.7, salience=0.9)
        return _ok(f"Signed with {org.name}: ${off.terms['advance']:,.0f} advance, "
                   f"{off.terms['royalty_rate']:.0%} royalty, {off.terms['term']}.", contract=c.id)
    if off.kind == "song_pitch":
        comp = world.compositions[off.terms["composition"]]
        comp.status = "assigned"
        off.status = "accepted"
        world.flags.setdefault("songbook", []).append(comp.id)
        return _ok(f"\"{comp.title}\" by {world.people[off.source].name} is now in your songbook ({comp.id}).",
                   composition=comp.id)
    if off.kind == "label_proposal":
        return _accept_label_proposal(world, off)
    if off.kind == "booking":
        off.status = "accepted"
        world.schedule.append(dict(off.terms["schedule"]))
        return _ok(f"Booked: {off.terms.get('summary', 'appearance')}.")
    return _reject(f"offers of kind {off.kind} cannot be accepted this way")


def _accept_label_proposal(world, off):
    """Act on a label's development proposal. The player decides; the label pays within the
    recording fund (recoupable); results come from the same creative maths as any session."""
    from ..systems.creative import produce_recording
    act = _act(world)
    org = world.orgs[off.source]
    if act.label is None or f"org:{act.label}" != org.id:
        return _reject("that label no longer has you under contract")
    t = off.terms
    rec = world.recordings.get(t.get("recording_id", ""))
    off.status = "accepted"
    world.pending = [p for p in world.pending if p.get("id") != off.id]
    if t["action"] == "release_master":
        if rec is None or rec.single_release or rec.status != "done":
            return _reject("that master is no longer available to release")
        date = _default_release_date(world)
        rel = acts_sys.plan_single(world, _market(world), act, rec, date, tier=t["promo"])
        rel.review = {"via": "development_meeting"}
        return _ok(f"{org.name} will release \"{rec.title}\" on {date.isoformat()} with {t['promo']} promotion.",
                   release=rel.id)
    if t["action"] in ("remix", "recut_vocal"):
        if rec is None:
            return _reject("that master no longer exists")
        busy = [r for r in world.recordings.values() if r.act == act.id and r.status == "in_production"]
        if busy:
            return _reject(f"you are already recording \"{busy[0].title}\"")
        cost = float(t["fee"]) + float(t["budget"])
        world.flags["recording_fund_used"] = world.flags.get("recording_fund_used", 0.0) + cost
        act.unrecouped -= cost
        world.ledger.transfer(world.date, org.id, t["producer"], float(t["fee"]), "producer_fee", rec.title)
        world.ledger.transfer(world.date, org.id, "ext:studios", float(t["budget"]), "studio_costs", rec.title)
        comp = world.compositions[rec.composition]
        key = f"{t['action']}#{rec.id}#{world.date.isoformat()}"
        prev_status = comp.status
        new = produce_recording(world, comp, act.id, [t["producer"]], rec.genre, budget=float(t["budget"]),
                                weeks=int(t["weeks"]), key=key, ambition=rec.attrs.get("ambition"),
                                payer=org.id, notes=list(rec.notes) + [f"{t['action'].replace('_', ' ')} of {rec.id}"])
        comp.status = prev_status
        if t["action"] == "remix":
            new.attrs["vocal_delivery"] = rec.attrs["vocal_delivery"]       # the original vocal performance is kept
            new.title = f"{rec.title} (Remix)"
        else:
            for k in ("production", "arrangement", "signature", "dance_hook", "accessibility"):
                new.attrs[k] = rec.attrs[k]                                  # only the vocal is re-cut
            new.title = f"{rec.title} (New Vocal)"
            new.producers = list(rec.producers) + [t["producer"]]
        new.style = list(rec.style)
        end = world.date + dt.timedelta(days=7 * int(t["weeks"]))
        world.commitments.append({"kind": "recording", "who": _pid(world), "recording": new.id,
                                  "start": world.date.isoformat(), "end": end.isoformat(),
                                  "label": f"{t['action'].replace('_', ' ')} of \"{rec.title}\" with {t['producer_name']}",
                                  "exclusive": False})
        world.emit("labels", "development_session", [org.id, act.id, rec.id, new.id],
                   {"action": t["action"], "producer": t["producer"], "cost": cost})
        return _ok(f"{t['action'].replace('_', ' ').capitalize()} of \"{rec.title}\" with {t['producer_name']} "
                   f"until {end.isoformat()} (${cost:,.0f} from the recording fund, recoupable).", recording=new.id)
    return _reject(f"unknown proposal action {t['action']}")


def _cmd_decline_offer(world, a):
    off = world.offers.get(a["offer_id"])
    if off is None or off.target != _act(world).id or off.status != "open":
        return _reject("no such open offer")
    off.status = "declined"
    world.pending = [p for p in world.pending if p.get("id") != off.id]
    src = world.orgs.get(off.source)
    rep = src.people.get("anr") if src else None
    if rep:
        r = world.rel(rep, _pid(world))
        r["affinity"] = round(r["affinity"] - 0.05, 3)
    world.emit("player", "offer_declined", [off.source, off.target, off.id], {})
    return _ok("Declined.")


def _cmd_record_song(world, a):
    act = _act(world)
    m = _market(world)
    rt = world.markets[m]
    genre = a["genre"]
    if not rt.genre_available(genre, world.date):
        return _reject(f"'{genre}' isn't something anyone is making yet in {world.date.year}")
    prod_id = a["producer"]
    prod = world.people.get(prod_id)
    if prod is None or "producer" not in prod.roles:
        return _reject(f"{prod_id} is not a producer in this world")
    busy = [r for r in world.recordings.values() if r.act == act.id and r.status == "in_production"]
    if busy:
        return _reject(f"you are already recording \"{busy[0].title}\"")
    if a["song"] == "write_own":
        title = a.get("title") or "Untitled"
        writers = [_pid(world)] + ([a["cowriter"]] if a.get("cowriter") in world.people else [])
        comp = None
    else:
        comp = world.compositions.get(a["song"])
        if comp is None or comp.id not in world.flags.get("songbook", []):
            return _reject("that song is not in your songbook (accept a pitch first, or use 'write_own')")
        if comp.status == "recorded":
            return _reject("you have already recorded that song")
        title = comp.title
    fee = float(a.get("fee_offer", prod.fee or 2000))
    key = f"pc#{world.date.isoformat()}#{title}"
    ok, p_yes, draws = acts_sys.producer_accepts(world, prod_id, act, fee, key)
    world.emit("player", "producer_approached", [prod_id, act.id], {"fee_offered": fee, "p_accept": round(p_yes, 3),
                                                                      "accepted": ok}, draws=draws)
    if not ok:
        world.remember(_pid(world), f"{prod.name} passed on producing for you.", [prod_id], valence=-0.3, salience=0.5)
        return _reject(f"{prod.name} passed on the session (chance they'd say yes was about {p_yes:.0%}).")
    budget = float(a["budget"])
    total = fee + budget
    pid = _pid(world)
    if act.label:
        org = world.orgs[f"org:{act.label}"]
        c = world.contracts.get(act.contract)
        fund = float(c.terms.get("recording_budget_per_album", 0)) if c else 0.0
        used = world.flags.get("recording_fund_used", 0.0)
        if used + total > fund * 1.15:
            return _reject(f"{org.name} won't fund it: ${used:,.0f} of the ${fund:,.0f} recording fund is already "
                           f"committed. Lower the budget or wait for the next album cycle.")
        payer = org.id
        world.flags["recording_fund_used"] = used + total
        act.unrecouped -= total
    else:
        if world.ledger.balance(pid) - total < -500:
            return _reject(f"you can't afford ${total:,.0f} (you have ${world.ledger.balance(pid):,.0f})")
        payer = pid
    world.ledger.transfer(world.date, payer, prod_id, fee, "producer_fee", title)
    world.ledger.transfer(world.date, payer, "ext:studios", budget, "studio_costs", title)
    if comp is None:
        comp = write_composition(world, title, writers, genre, key=key)
        world.flags.setdefault("songbook", []).append(comp.id)
    brief = world.flags.pop("brief", {}) or {}
    ambition = a.get("ambition", brief.get("ambition"))
    mood = float(a.get("mood", brief.get("mood", 0.0))) * 0.15
    rec = produce_recording(world, comp, act.id, [prod_id], genre, budget=budget, weeks=a["studio_weeks"], key=key,
                            ambition=ambition, mood_shift=mood, payer=payer,
                            notes=[brief["concept"]] if brief.get("concept") else [])
    end = world.date + dt.timedelta(days=7 * a["studio_weeks"])
    world.commitments.append({"kind": "recording", "who": pid, "recording": rec.id, "start": world.date.isoformat(),
                              "end": end.isoformat(), "label": f"recording \"{title}\" with {prod.name}",
                              "exclusive": False})
    r = world.rel(prod_id, pid)
    r["affinity"] = round(r["affinity"] + 0.05, 3)
    world.remember(prod_id, f"Started recording \"{title}\" with {act.name}.", [act.id], valence=0.2, salience=0.4)
    world.remember(pid, f"Started recording \"{title}\" with {prod.name}.", [prod_id], valence=0.3, salience=0.6)
    return _ok(f"Recording \"{title}\" with {prod.name}: sessions through {end.isoformat()} (fee ${fee:,.0f}, "
               f"budget ${budget:,.0f}); the finished master is in hand the next morning.",
               recording=rec.id)


def _default_release_date(world):
    m = _market(world)
    return acts_sys.release_day(world, m, world.date + dt.timedelta(days=10))


def _cmd_release_single(world, a):
    act = _act(world)
    m = _market(world)
    rec = world.recordings.get(a["recording_id"])
    if rec is None or rec.act != act.id:
        return _reject("no such recording of yours")
    if rec.status != "done":
        return _reject(f"\"{rec.title}\" is {rec.status.replace('_', ' ')}")
    if rec.single_release:
        return _reject("that recording is already scheduled or released as a single")
    date = dates.parse(a["date"]) if a.get("date") else _default_release_date(world)
    if date < world.date + dt.timedelta(days=7):
        return _reject("records need at least a week to be manufactured and shipped")
    date = acts_sys.release_day(world, m, date)
    tier = a["promo"]
    video = a.get("video", "none")
    if act.label:
        from ..systems.development import notes_text, on_rejection, review_master, tier_for
        org = world.orgs[f"org:{act.label}"]
        n = world.flags.setdefault("single_reviews", {}).get(rec.id, 0)
        world.flags["single_reviews"][rec.id] = n + 1
        rv = review_master(world, org, act, rec, f"single_request{n}")
        eid = world.emit("labels", "single_review", [org.id, rec.id, act.id],
                         {k: rv[k] for k in ("score", "threshold", "approve", "craft", "commercial", "strengths",
                                             "weaknesses", "fit")}, draws=rv["draws"])
        if not rv["approve"]:
            on_rejection(world, org, act, rec, rv, causes=[eid])
            meet = (world.flags.get("development") or {}).get("meeting")
            return _reject(f"{org.name} won't release \"{rec.title}\" as a single yet: {notes_text(rv)}. "
                           f"A&R development meeting on {meet}.", review={k: rv[k] for k in (
                               "strengths", "weaknesses", "fit", "remedies")})
        cap = tier_for(rv, act)
        granted = PROMO[min(PROMO.index(tier), PROMO.index(cap))]
        rel = acts_sys.plan_single(world, m, act, rec, date, tier=granted)
        rel.review = {k: rv[k] for k in ("score", "threshold", "approve", "margin", "craft", "commercial")}
        if video != "none" and not rec.video and labels_sys._video_era(world, m):
            labels_sys.commission_video(world, m, rec, org, video if PROMO.index(video) <= PROMO.index(granted) else granted)
        note = "" if granted == tier else f" (the label approved {granted} promotion, not {tier})"
        return _ok(f"{org.name} will release \"{rec.title}\" on {date.isoformat()} with {granted} promotion{note}.",
                   release=rel.id)
    pid = _pid(world)
    cost = SELF_PROMO[tier] + (SELF_VIDEO[video] if video != "none" else 0)
    if world.ledger.balance(pid) - cost < -500:
        return _reject(f"self-releasing with {tier} promotion costs about ${cost:,.0f}; you have "
                       f"${world.ledger.balance(pid):,.0f}")
    rel = acts_sys.plan_single(world, m, act, rec, date, tier=tier, promo_budget=SELF_PROMO[tier])
    if video != "none" and labels_sys._video_era(world, m):
        labels_sys.commission_video(world, m, rec, None, video, payer=pid, cost=SELF_VIDEO[video])
    return _ok(f"Self-releasing \"{rec.title}\" on {date.isoformat()} through independent distribution "
               f"({tier} promotion, ${SELF_PROMO[tier]:,} budget).", release=rel.id)


def _cmd_release_album(world, a):
    act = _act(world)
    m = _market(world)
    recs = [world.recordings.get(r) for r in a["recording_ids"]]
    if any(r is None or r.act != act.id or r.status not in ("done", "released") for r in recs):
        return _reject("every track must be a finished recording of yours")
    if len(recs) < 6:
        return _reject("an album needs at least 6 tracks")
    date = dates.parse(a["date"]) if a.get("date") else acts_sys.release_day(world, m, world.date + dt.timedelta(days=21))
    if date < world.date + dt.timedelta(days=14):
        return _reject("albums need at least two weeks to manufacture and ship")
    focus = [r.id for r in recs if r.single_release]
    tier = a.get("promo", "standard")
    if act.label:
        org = world.orgs[f"org:{act.label}"]
        if not focus:
            return _reject(f"{org.name} won't put out an album without a single leading it.")
    rel = acts_sys.plan_album(world, m, act, a["title"], [r.id for r in recs], focus,
                              acts_sys.release_day(world, m, date), tier=tier)
    if not act.label:
        cost = 0.4 * SELF_PROMO[tier]
        world.ledger.transfer(world.date, _pid(world), "ext:promotion", cost, "album_promotion", rel.id)
    return _ok(f"Album \"{a['title']}\" scheduled for {rel.date} ({len(recs)} tracks).", release=rel.id)


def _cmd_gig(world, a):
    c = _overlaps(world, world.date.isoformat(), (world.date + dt.timedelta(days=7 * a["weeks"])).isoformat())
    if c:
        return _reject(f"conflicts with {c['label']} ({c['start']}..{c['end']})")
    job = world.flags.get("day_job", {})
    if job.get("active") and a["nights_per_week"] > 3:
        return _reject("with your day job you can manage at most 3 nights a week")
    _commit(world, "gigs", a["weeks"], f"club dates, {a['nights_per_week']} nights/week", False,
            nights=a["nights_per_week"])
    return _ok(f"Booked {a['nights_per_week']} nights a week of club dates for {a['weeks']} weeks.")


def _cmd_train(world, a):
    from .wellbeing import resting, window
    start, end = window(world, a["weeks"])
    r = resting(world, _pid(world), start, end)
    if r:
        return _reject(f"you have protected time off {r['start']}..{r['end']}; book lessons after it")
    _commit(world, "training", a["weeks"], f"{a['skill']} training", False, skill=a["skill"],
            spend=float(a.get("spend_per_week", 100.0)))
    return _ok(f"Training {a['skill']} for {a['weeks']} weeks.")


def _cmd_promote(world, a):
    act = _act(world)
    rec = world.recordings.get(a["recording_id"])
    rel = world.releases.get(rec.single_release) if rec and rec.single_release else None
    if rec is None or rec.act != act.id or rel is None or rel.status != "released":
        return _reject("you can only personally promote a released single of yours")
    end = (world.date + dt.timedelta(days=7 * a["weeks"])).isoformat()
    c = _overlaps(world, world.date.isoformat(), end)
    if c:
        return _reject(f"conflicts with {c['label']}")
    payer = f"org:{act.label}" if act.label else _pid(world)
    cost = 900.0 * a["weeks"]
    world.ledger.transfer(world.date, payer, "ext:travel", cost, "promo_travel", rec.id)
    if act.label:
        act.unrecouped -= cost
    amount = {"radio_tour": 0.30, "club_tour": 0.12, "press_tour": 0.08}[a["kind"]]
    world.flags.setdefault("promo_boosts", []).append({"song": rec.id, "until": end, "amount": amount,
                                                       "kind": a["kind"]})
    _commit(world, a["kind"], a["weeks"], f"{a['kind'].replace('_', ' ')} for \"{rec.title}\"", True, song=rec.id)
    return _ok(f"{a['kind'].replace('_', ' ').title()} for \"{rec.title}\" for {a['weeks']} weeks (${cost:,.0f}).")


def _cmd_set_day_job(world, a):
    job = world.flags.get("day_job")
    if not job:
        return _reject("you don't have a day job")
    if a["active"] and not job.get("active"):
        job["since"] = world.date.isoformat()
        job.pop("until", None)
    elif not a["active"] and job.get("active"):
        job["until"] = world.date.isoformat()
    job["active"] = a["active"]
    return _ok("Kept the day job." if a["active"] else "Quit the day job.")


def _cmd_set_lifestyle(world, a):
    world.flags["lifestyle"] = a["level"]
    return _ok(f"Lifestyle set to {a['level']}.")


def _cmd_set_policy(world, a):
    from .delegation import policy
    pol = policy(world)
    pol.update(a)
    return _ok("Standing orders updated: " + ", ".join(f"{k}={v}" for k, v in a.items())
               + ". Existing bookings are kept; use cancel_bookings to cancel them.")


def _cmd_cancel_bookings(world, a):
    from .wellbeing import clear_routine
    kinds = ("gigs", "training") if a["kind"] == "all_routine" else (a["kind"],)
    far = (world.date + dt.timedelta(days=3650)).isoformat()
    out = clear_routine(world, _pid(world), world.date.isoformat(), far, kinds=kinds, reason="cancelled by player")
    if not out["items"]:
        return _reject("nothing of that kind is booked")
    return _ok("Cancelled: " + "; ".join(out["items"]) + ".", cancelled=out)


def _cmd_hire_manager(world, a):
    from .delegation import hire_manager
    return hire_manager(world, a["person_id"], float(a["commission"]))


def _cmd_fire_manager(world, a):
    from .delegation import fire_manager
    return fire_manager(world)


def _cmd_rest(world, a):
    """Protected time off: routine bookings inside the window are cancelled (and resume afterwards)."""
    from .wellbeing import clear_routine, in_studio, window
    start, end = window(world, a["weeks"])
    pid = _pid(world)
    studio = in_studio(world, pid, start, end)
    if studio:
        return _reject(f"you're booked in the studio until {studio['end']} ({studio['label']}); "
                       "book the time off after the session")
    c = _overlaps(world, start, end)
    if c:
        return _reject(f"conflicts with {c['label']} ({c['start']}..{c['end']})")
    keep = a.get("keep_bookings", False)
    cancelled = {"club_nights": 0, "lesson_days": 0, "items": []} if keep else clear_routine(world, pid, start, end)
    _commit(world, "rest", a["weeks"], "time off", True)
    world.emit("schedule", "rest_booked", [pid], {"start": start, "end": end, "cancelled": cancelled["items"]})
    job = (world.flags.get("day_job") or {}).get("active")
    note = []
    if cancelled["items"]:
        note.append("cancelled " + "; ".join(cancelled["items"]))
    if job:
        note.append("the day job continues")
    return _ok(f"Time off {start} to {end}" + (f" ({'; '.join(note)})" if note else "") + ".",
               cancelled=cancelled)


# ---------------------------------------------------------- weekly effects
def weekly_player(world, market):
    """Monday: account for the week that just elapsed, then let the team handle routine work."""
    pid = world.player.get("person")
    if not pid or world.player.get("market") != market:
        return
    from .wellbeing import account_week
    account_week(world, market)
    wb = world.people[pid].wellbeing
    today = world.date.isoformat()
    if wb["energy"] < 0.2 and not world.flags.get("exhaustion_warned"):
        world.flags["exhaustion_warned"] = True
        world.add_news("You are exhausted; your voice and stage energy are suffering.", "wellbeing", [pid],
                       tag="official", importance=0.7)
        world.interrupts.append({"reason": "exhaustion"})
    elif wb["energy"] > 0.4:
        world.flags["exhaustion_warned"] = False
    world.flags["promo_boosts"] = [b for b in world.flags.get("promo_boosts", []) if b["until"] >= today]
    from .delegation import weekly as team_weekly
    team_weekly(world, market)


def describe_recording_for_player(world, rec) -> dict:
    """What the protagonist's team hears in a finished recording (observed, not true values)."""
    noise = {}
    for k in ("hook", "melody", "depth", "production", "vocal_delivery", "signature", "dance_hook", "ambition",
              "singability"):
        src = world.compositions[rec.composition].attrs if k in world.compositions[rec.composition].attrs else rec.attrs
        noise[k] = float(np.clip(src[k] + 0.08 * rng.normal(world.seed, "team_ear", rec.id, k), 0, 1))
    return {"impression": describe(world, rec, observed=noise),
            "team_rating": {k: round(v * 100) for k, v in noise.items()}}

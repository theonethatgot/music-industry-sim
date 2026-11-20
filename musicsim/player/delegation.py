"""Delegation: routine work the protagonist's team does without asking, under standing orders.

Major decisions always come back to the player (contracts, releases, recording sessions, career
changes, big spending). Routine work (keeping club dates booked, lessons, rest when exhausted, a
manager chasing press and gigs) runs every week through the same resolution code as everything
else, and is reported in the next packet.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates
from ..core.rng import Draws
from ..entities import Contract

DEFAULT_POLICY = {
    "gigs_when_idle": 2,
    "training_when_idle": "none",
    "training_spend_per_week": 75.0,
    "manager_may_book_media": True,
    "manager_may_book_gigs": True,
    "rest_when_exhausted": True,
}
ALWAYS_ASK = [
    "signing or ending contracts (label, management, publishing)",
    "recording sessions (song, producer, budget)",
    "releases (which song, when, how much promotion)",
    "career changes (image, genre, label, city)",
    "spending more than about $2,000 of your own money",
    "public statements and anything that could become news",
]


def policy(world) -> dict:
    pol = world.flags.setdefault("policy", dict(DEFAULT_POLICY))
    for k, v in DEFAULT_POLICY.items():
        pol.setdefault(k, v)
    return pol


def manager(world) -> dict | None:
    return world.flags.get("manager")


def _pid(world):
    return world.player["person"]


def _news(world, text, importance=0.45, entities=(), eid=None):
    world.add_news(text, "team", [world.player["act"], *entities], tag="official", importance=importance, event_id=eid)


# ---------------------------------------------------------------- manager
def hire_manager(world, person_id: str, commission: float) -> dict:
    from ..player.commands import _ok, _reject
    if manager(world):
        return _reject("you already have a manager; fire_manager first")
    m = world.people.get(person_id)
    if m is None or "manager" not in m.roles:
        return _reject(f"{person_id} is not a manager in this world")
    pid = _pid(world)
    if f"{person_id}|{pid}" not in world.relations and f"{pid}|{person_id}" not in world.relations:
        return _reject(f"you don't know {m.name} yet")
    act = world.player_act
    vocal = world.people[pid].skills.get("vocal", 0.5)
    prospects = act.singles_power_o + 0.5 * act.live_buzz + (0.3 if act.label else 0.0) + 0.3 * (vocal - 0.5)
    bond = world.rel(person_id, pid)["affinity"]
    money = commission / 0.15
    p = float(np.clip(0.15 + 0.35 * money + 0.8 * prospects + 0.4 * bond, 0.03, 0.95))
    dr = Draws(world.seed, "hire_manager", person_id, world.date.isoformat())
    yes = dr.chance("accepts", p)
    eid = world.emit("team", "manager_offer", [person_id, act.id], {"commission": commission, "p": round(p, 3),
                                                                  "accepted": yes}, draws=dr.log)
    if not yes:
        world.remember(person_id, f"Turned down managing {act.name}.", [act.id], valence=-0.1, salience=0.4)
        return _reject(f"{m.name} isn't ready to take you on at {commission:.0%} (chance was about {p:.0%}).")
    cid = world.new_id("contract")
    world.contracts[cid] = Contract(id=cid, kind="management", parties=[person_id, act.id],
                                    terms={"commission": commission, "scope": "all entertainment income except "
                                                                             "recording funds"},
                                    start=world.date.isoformat())
    world.flags["manager"] = {"person": person_id, "commission": commission, "since": world.date.isoformat(),
                              "contract": cid}
    act.manager = person_id
    r = world.rel(person_id, pid)
    r["affinity"] = round(r["affinity"] + 0.1, 3)
    r["history"].append(eid)
    world.remember(person_id, f"Took on {act.name} as a management client.", [act.id], valence=0.5, salience=0.8)
    world.remember(pid, f"{m.name} became your manager ({commission:.0%}).", [person_id], valence=0.5, salience=0.8)
    return _ok(f"{m.name} is now your manager at {commission:.0%} commission.", contract=cid)


def fire_manager(world) -> dict:
    from ..player.commands import _ok, _reject
    mg = manager(world)
    if not mg:
        return _reject("you don't have a manager")
    m = world.people[mg["person"]]
    world.contracts[mg["contract"]].status = "terminated"
    world.contracts[mg["contract"]].end = world.date.isoformat()
    r = world.rel(m.id, _pid(world))
    r["affinity"] = round(r["affinity"] - 0.3, 3)
    world.remember(m.id, f"Was let go as {world.player_act.name}'s manager.", [world.player["act"]], valence=-0.6,
                   salience=0.8)
    world.flags.pop("manager")
    world.player_act.manager = None
    world.emit("team", "manager_fired", [m.id, world.player["act"]], {})
    return _ok(f"You parted ways with {m.name}.")


def pay_commission(world, gross: float, memo: str):
    mg = manager(world)
    if mg and gross > 0:
        world.ledger.transfer(world.date, _pid(world), mg["person"], gross * mg["commission"], "management_commission",
                              memo)


# ---------------------------------------------------------------- weekly
def _busy(world, start: str, end: str, kinds) -> bool:
    pid = _pid(world)
    return any(c.get("who") == pid and not c.get("done") and c["kind"] in kinds
               and not (c["end"] < start or c["start"] > end) for c in world.commitments)


def _current_single(world):
    from .proposals import _current_single as cs
    return cs(world)


def weekly(world, market: str):
    from . import commands as cmds
    from . import proposals as props
    pol = policy(world)
    pid = _pid(world)
    p = world.people[pid]
    act = world.player_act
    today = world.date.isoformat()
    soon = (world.date + dt.timedelta(days=27)).isoformat()
    wb = p.wellbeing
    # rest when exhausted: book genuinely protected time off (after any studio session already under way)
    from .wellbeing import clear_routine, in_studio, resting
    threshold = world.config.tree["wellbeing"]["exhausted_below"]
    if pol["rest_when_exhausted"] and wb.get("energy", 1) < threshold \
            and not resting(world, pid, today, (world.date + dt.timedelta(days=6)).isoformat()):
        start = world.date
        studio = in_studio(world, pid, today, (world.date + dt.timedelta(days=13)).isoformat())
        if studio:
            start = dates.parse(studio["end"]) + dt.timedelta(days=1)
        end = start + dt.timedelta(days=6)
        if not _busy(world, start.isoformat(), end.isoformat(), ("radio_tour", "club_tour", "press_tour")):
            cancelled = clear_routine(world, pid, start.isoformat(), end.isoformat(), reason="auto rest")
            world.commitments.append({"kind": "rest", "who": pid, "start": start.isoformat(), "end": end.isoformat(),
                                      "label": "time off (standing orders)", "exclusive": True})
            eid = world.emit("team", "auto_rest", [act.id], {"energy": wb["energy"], "start": start.isoformat(),
                                                             "end": end.isoformat(), "cancelled": cancelled["items"]})
            what = (" and cancelled " + "; ".join(cancelled["items"])) if cancelled["items"] else ""
            after = f" once the studio session ends on {studio['end']}" if studio else ""
            job = (world.flags.get("day_job") or {}).get("active")
            _news(world, f"Standing orders: you're running on empty, so your team booked time off "
                         f"{start.isoformat()} to {end.isoformat()}{after}{what}"
                         + (" (the day job continues)" if job else "") + ".", 0.6, eid=eid)
    # keep club dates booked
    n = int(pol["gigs_when_idle"])
    if n and not _busy(world, today, soon, ("gigs", "radio_tour", "club_tour", "press_tour", "rest")):
        if world.flags.get("day_job", {}).get("active"):
            n = min(n, 3)
        res = cmds._cmd_gig(world, {"weeks": 4, "nights_per_week": n})
        if res["status"] == "accepted":
            eid = world.emit("team", "auto_gigs", [act.id], {"nights_per_week": n, "weeks": 4})
            _news(world, f"Standing orders: {n} club nights a week booked for the next four weeks.", 0.35, eid=eid)
    # keep lessons going
    skill = pol["training_when_idle"]
    if skill and skill != "none" and not _busy(world, today, today, ("training",)):
        cmds._cmd_train(world, {"skill": skill, "weeks": 4, "spend_per_week": float(pol["training_spend_per_week"])})
        world.emit("team", "auto_training", [act.id], {"skill": skill})
    # the manager works the phones
    mg = manager(world)
    if mg:
        m = world.people[mg["person"]]
        skill_m = m.skills.get("management", 0.5)
        dr = Draws(world.seed, "manager_week", m.id, today)
        single = _current_single(world)
        if single is not None:
            world.flags.setdefault("tv_push", {})[single.id] = round(0.25 * skill_m, 3)
        if pol["manager_may_book_media"] and single is not None and dr.chance("tries_media", 0.1 + 0.3 * skill_m):
            res = props._p_opportunity(world, {"kind": "interview", "context": f"arranged by {m.name}"},
                                       Draws(world.seed, "manager_media", m.id, today))
            if res["status"] == "accepted":
                _news(world, f"{m.name} landed you press coverage. {res['summary']}", 0.5, [m.id], res.get("event"))
        protected = resting(world, pid, today, (world.date + dt.timedelta(days=6)).isoformat())
        if protected and pol["manager_may_book_gigs"]:
            world.emit("team", "manager_held_off", [m.id, act.id], {"reason": "protected time off"}, public=False)
        if pol["manager_may_book_gigs"] and not protected and dr.chance("tries_gig", 0.08 + 0.25 * skill_m):
            res = props._p_opportunity(world, {"kind": "gig_offer", "context": f"a bigger date found by {m.name}"},
                                       Draws(world.seed, "manager_gig", m.id, today))
            if res["status"] == "accepted":
                pay_commission(world, float(res.get("fee", 0)), "manager-booked gig")
                _news(world, f"{m.name} booked a better-paid show. {res['summary']}", 0.5, [m.id], res.get("event"))
        if act.label and single is None:
            _manager_pushes_label(world, m, act, skill_m, dr)
        if not act.label and act.live_buzz > 0.25 and dr.chance("tries_showcase", 0.05 + 0.15 * skill_m):
            if not any(s["kind"] == "showcase" and s["date"] >= today for s in world.schedule):
                res = props._p_opportunity(world, {"kind": "showcase", "context": f"set up by {m.name}"},
                                           Draws(world.seed, "manager_showcase", m.id, today))
                if res["status"] == "accepted":
                    _news(world, f"{m.name} set up a label showcase. {res['summary']}", 0.7, [m.id], res.get("event"))
    world.flags["advice"] = advice(world)


def _manager_pushes_label(world, m, act, skill_m, dr):
    """A manager with a signed client and no single out works the label: asks for a meeting, or
    brings songs from their own network. They don't spend the client's money or the label's."""
    from ..systems import development as dev
    st = dev.state(world)
    today = world.date
    planned = any(r.act == act.id and r.status == "planned" for r in world.releases.values())
    if planned:
        return
    meeting = st.get("meeting")
    soon = (today + dt.timedelta(days=10)).isoformat()
    org = world.orgs[f"org:{act.label}"]
    stalled = (today - dev._anchor(world, act)).days >= 42
    if stalled and (not meeting or meeting > soon) and dr.chance("presses_label", 0.10 + 0.30 * skill_m):
        when = today + dt.timedelta(days=4 + int(dr.uniform("when") * 4))
        dev.schedule_meeting(world, act, when, f"requested by {m.name}")
        eid = world.emit("team", "manager_presses_label", [m.id, act.id, org.id], {"meeting": when.isoformat()})
        _news(world, f"{m.name} pressed {org.name} for a sit-down about the single; A&R agreed to meet on "
                     f"{when.isoformat()}.", 0.6, [m.id, org.id], eid)
    elif stalled and dr.chance("brings_song", 0.05 + 0.15 * skill_m):
        pitched = dev._label_pitches(world, org, act, 1, f"manager{today.isoformat()}")
        for x in pitched:
            world.offers[x["offer_id"]].terms["via"] = m.name
        if pitched:
            eid = world.emit("team", "manager_brings_song", [m.id, act.id], {"songs": pitched})
            _news(world, f"{m.name} brought in a song from their network: \"{pitched[0]['title']}\" by "
                         f"{pitched[0]['writer']}.", 0.5, [m.id], eid)


def advice(world) -> list[str]:
    """What the protagonist's people are saying (derived from state; the narrator voices it)."""
    act = world.player_act
    pid = _pid(world)
    p = world.people[pid]
    out = []
    mine = [r for r in world.recordings.values() if r.act == act.id]
    done = [r for r in mine if r.status == "done" and not r.single_release]
    released = [r for r in world.releases.values() if r.act == act.id and r.status == "released"]
    contact = next((world.people[k.split("|")[1]].name for k, v in world.relations.items()
                    if k.startswith(pid + "|") and "producer" in world.people.get(k.split("|")[1], p).roles), None)
    if not act.label and not mine:
        if act.flags.get("demo_quality") is not None:
            out.append(f"{contact or 'Your friends'}: the old demo tape is rough; a properly recorded song would give "
                       "labels and radio more to hear.")
        else:
            out.append(f"{contact or 'Your friends'}: a properly recorded demo would give labels something to hear.")
    if not act.label and act.live_buzz < 0.2:
        out.append("Club bookers: more regular nights would build a local following that A&R people notice.")
    book = [c for c in world.flags.get("songbook", []) if world.compositions[c].status != "recorded"]
    if book:
        out.append(f"You have {len(book)} unrecorded song(s) in your songbook.")
    if done and act.label:
        out.append(f"Your label is waiting to hear which finished recording should be the single ({len(done)} ready).")
    if act.label and released and not any(r.kind == "album" for r in world.releases.values() if r.act == act.id):
        last = max(dates.parse(r.date) for r in released)
        if (world.date - last).days > 70:
            out.append("Your A&R contact is asking when there will be enough songs for an album.")
    cash = world.ledger.balance(pid)
    if cash < 300:
        out.append(f"Money is tight: ${cash:,.0f} in the bank.")
    if p.wellbeing.get("energy", 1) < 0.35:
        out.append("You're running on empty; people around you can see it.")
    for o in world.offers.values():
        if o.target == act.id and o.status == "open" and o.kind != "song_pitch":
            days = (dates.parse(o.expires) - world.date).days
            if days <= 10:
                out.append(f"The {o.kind.replace('_', ' ')} offer {o.id} expires in {days} days.")
    if not manager(world) and (act.label or act.live_buzz > 0.3):
        out.append("People keep asking who manages you.")
    return out[:7]

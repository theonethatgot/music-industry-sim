"""Wellbeing and routine-work accounting over the week that has just elapsed.

Earlier versions applied a commitment's effects only if it was still active on the Monday of the
weekly tick. A one-week rest booked on a Monday ended the following Sunday, so its benefit was
never counted. Now every Monday the engine walks the seven days that have just passed and applies
what actually happened on each day (rest, day job, club nights, lessons, studio, tours), whether
or not the commitment has since ended. Energy and stress relax toward a target set by that day's
workload, so recovery is gradual, explainable and testable.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import rng
from ..systems.condition import fitness

ROUTINE = ("gigs", "training")
TOURS = ("radio_tour", "club_tour", "press_tour")


def cfg(world) -> dict:
    return world.config.tree["wellbeing"]


def commitments_on(world, pid: str, day: str) -> list[dict]:
    """Every commitment that covered `day`, including ones that have since finished."""
    return [c for c in world.commitments if c.get("who") == pid and c["start"] <= day <= c["end"]
            and not c.get("cancelled")]


def day_profile(world, pid: str, day: str) -> dict:
    """What a given day consisted of, and the workload it put on the person."""
    k = cfg(world)["load"]
    cs = commitments_on(world, pid, day)
    kinds = {c["kind"] for c in cs}
    resting = "rest" in kinds
    load = 0.0
    parts = []
    job = world.flags.get("day_job") or {}
    on = day >= job.get("since", "0000") and (job.get("active") or day < job.get("until", "0000"))
    if job and on:
        load += k["day_job"]
        parts.append("day job")
    for c in cs:
        if c["kind"] == "gigs":
            load += k["gig_night"] * c["nights"]
            parts.append("club dates")
        elif c["kind"] == "training":
            load += k["training"]
            parts.append("lessons")
        elif c["kind"] == "recording":
            load += k["recording"]
            parts.append("studio")
        elif c["kind"] in TOURS:
            load += k["tour"]
            parts.append(c["kind"].replace("_", " "))
    return {"day": day, "load": load, "resting": resting, "parts": parts, "commitments": cs}


def account_week(world, market: str) -> dict:
    """Apply the elapsed week (the 7 days before today) to the protagonist. Returns a summary."""
    pid = world.player["person"]
    p = world.people[pid]
    act = world.player_act
    rt = world.markets[market]
    W = cfg(world)
    since = world.flags.get("wellbeing_from")
    wb = p.wellbeing
    e0, s0 = wb.get("energy", 0.8), wb.get("stress", 0.2)
    e, s = e0, s0
    rest_days = 0
    nights = 0.0
    lesson_days = {}
    worked = set()
    cash = world.ledger.balance(pid)
    for k in range(7, 0, -1):
        day = (world.date - dt.timedelta(days=k)).isoformat()
        if since and day < since:
            continue
        prof = day_profile(world, pid, day)
        if prof["resting"]:
            rest_days += 1
            target_e = W["rest_target"] - prof["load"]
            rate_e = W["rest_rate"]
        else:
            target_e = W["base_target"] - prof["load"] - W["overload_penalty"] * max(0.0, prof["load"] - W["overload_above"])
            rate_e = W["relax_rate"]
        target_s = W["stress_base"] + W["stress_load"] * max(0.0, prof["load"] - W["stress_free_load"])
        if cash < 0:
            target_s += W["stress_debt"]
        if prof["resting"]:
            target_s -= W["stress_rest_relief"]
        e += rate_e * (float(np.clip(target_e, 0.05, 1.0)) - e)
        s += W["stress_rate"] * (float(np.clip(target_s, 0.0, 1.0)) - s)
        worked.update(prof["parts"])
        for c in prof["commitments"]:
            if c["kind"] == "gigs":
                nights += c["nights"] / 7.0
            elif c["kind"] == "training":
                lesson_days[c["skill"]] = lesson_days.get(c["skill"], [0, c.get("spend", 0.0)])
                lesson_days[c["skill"]][0] += 1
    wb["energy"] = round(float(np.clip(e, 0.05, 1.0)), 3)
    wb["stress"] = round(float(np.clip(s, 0.0, 1.0)), 3)
    # routine work that actually happened last week ------------------------------------------
    today = world.date.isoformat()
    if nights > 0:
        rec = np.array(act.recognition.get(market, [0.0] * rt.G))
        fee = rt.gig_fee(world.date) * (1 + 4 * float(rec.mean()) + 2 * act.live_buzz)
        pay = fee * nights * fitness(world, pid)
        world.ledger.transfer(world.date, "ext:venues", pid, pay, "gig_fees", "club dates")
        from .delegation import pay_commission
        pay_commission(world, pay, "club dates")
        perf = p.skills.get("performance", 0.5)
        shock = rng.normal(world.seed, "gig_week", pid, today)
        act.live_buzz = float(np.clip(act.live_buzz + 0.006 * nights * (perf * fitness(world, pid) + 0.2 * shock), 0, 1))
        p.skills["performance"] = round(min(0.99, perf + 0.0015 * nights * (1 - perf)), 4)
    for skill, (days, spend) in sorted(lesson_days.items()):
        cur = p.skills.get(skill, 0.3)
        gain = 0.004 * (days / 7.0) * (1 - cur) * (1 + spend / 300) ** 0.5
        p.skills[skill] = round(min(0.99, cur + gain), 4)
        world.ledger.transfer(world.date, pid, "ext:coaches", spend * days / 7.0, "training", skill)
    summary = {"week_to": (world.date - dt.timedelta(days=1)).isoformat(), "energy": [round(e0, 3), wb["energy"]],
               "stress": [round(s0, 3), wb["stress"]], "rest_days": rest_days, "club_nights": round(nights, 1),
               "lesson_days": {k: v[0] for k, v in lesson_days.items()}, "activities": sorted(worked)}
    world.flags["last_week"] = summary
    if rest_days:
        log = world.flags.setdefault("rest_log", [])
        log.append([summary["week_to"], rest_days, summary["energy"][0], summary["energy"][1]])
        del log[:-52]
        eid = world.emit("wellbeing", "rest_week", [pid], summary)
        job = (world.flags.get("day_job") or {}).get("active")
        change = "recovered" if wb["energy"] > e0 + 0.02 else "barely recovered" if wb["energy"] >= e0 else "kept sliding"
        world.add_news(f"Time off ({rest_days} days): you {change}; energy {word(e0)} → {word(wb['energy'])}, "
                       f"stress {word(s0)} → {word(wb['stress'])}"
                       + (" (the day job kept going, which limited the rest)" if job else "") + ".",
                       "wellbeing", [pid], tag="official", importance=0.55, event_id=eid)
    return summary


def word(v: float) -> str:
    return ("very low", "low", "moderate", "high", "very high")[min(4, max(0, int(v * 5)))]


# ------------------------------------------------------------------ scheduling
def window(world, weeks: int, start: dt.date | None = None) -> tuple[str, str]:
    s = start or world.date
    return s.isoformat(), (s + dt.timedelta(days=7 * weeks - 1)).isoformat()


def clear_routine(world, pid: str, start: str, end: str, kinds=ROUTINE, reason: str = "rest") -> dict:
    """Cancel the parts of routine bookings that fall inside [start, end]; resume them afterwards.

    Returns what was cancelled so the caller can report it truthfully. Cancelled club nights
    cost a little goodwill with bookers and some local buzz."""
    out = {"club_nights": 0.0, "lesson_days": 0, "items": []}
    keep = []
    d0, d1 = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    for c in world.commitments:
        if c.get("who") != pid or c.get("done") or c.get("cancelled") or c["kind"] not in kinds \
                or c["end"] < start or c["start"] > end:
            keep.append(c)
            continue
        cs, ce = dt.date.fromisoformat(c["start"]), dt.date.fromisoformat(c["end"])
        lo, hi = max(cs, d0), min(ce, d1)
        days = (hi - lo).days + 1
        if c["kind"] == "gigs":
            out["club_nights"] += c["nights"] * days / 7.0
        else:
            out["lesson_days"] += days
        out["items"].append(f"{c['label']} ({lo.isoformat()}..{hi.isoformat()})")
        if cs < d0:
            keep.append(dict(c, end=(d0 - dt.timedelta(days=1)).isoformat()))
        if ce > d1:
            keep.append(dict(c, start=(d1 + dt.timedelta(days=1)).isoformat()))
    world.commitments = keep
    if out["club_nights"]:
        act = world.player_act
        act.live_buzz = float(max(0.0, act.live_buzz - 0.003 * out["club_nights"]))
        for k, r in world.relations.items():
            other = k.split("|")[0]
            if k.endswith("|" + pid) and "booker" in world.people.get(other, world.people[pid]).roles:
                r["affinity"] = round(r["affinity"] - min(0.05, 0.01 * out["club_nights"]), 3)
    if out["items"]:
        world.emit("schedule", "bookings_cancelled", [pid], {"reason": reason, **out})
    out["club_nights"] = round(out["club_nights"], 1)
    return out


def resting(world, pid: str, start: str, end: str) -> dict | None:
    for c in world.commitments:
        if c.get("who") == pid and c["kind"] == "rest" and not c.get("cancelled") \
                and not (c["end"] < start or c["start"] > end):
            return c
    return None


def in_studio(world, pid: str, start: str, end: str) -> dict | None:
    for c in world.commitments:
        if c.get("who") == pid and c["kind"] == "recording" and not c.get("done") \
                and not (c["end"] < start or c["start"] > end):
            return c
    return None

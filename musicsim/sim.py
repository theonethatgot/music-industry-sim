"""Simulation clock: the fixed daily and weekly order of systems."""
from __future__ import annotations

import datetime as dt

from .core import dates
from .systems import acts, careers, charts, demand, development, finance, gatekeepers, labels, release


def step_day(world):
    d = world.date
    for m in world.market_ids:
        if d.weekday() == 0:
            weekly(world, m)
        for rel in sorted(world.releases.values(), key=lambda r: r.id):
            if rel.status == "planned" and rel.market == m and dates.parse(rel.date) <= d:
                if world.acts[rel.act].active:
                    release.place_release(world, rel)
                else:
                    rel.status = "cancelled"
        _scheduled(world, m)
        demand.daily_step(world, m)
    _commitments(world)
    world.date = d + dt.timedelta(days=1)


def weekly(world, m):
    charts.compile_week(world, m)
    units = finance.weekly(world, m)
    release.weekly_restock(world, m, units)
    careers.weekly(world, m)
    careers.certifications(world, m)
    labels.weekly(world, m)
    labels.scout(world, m)
    labels.npc_offer_responses(world)
    acts.weekly(world, m)
    development.npc_patience(world, m)
    acts.song_market(world, m)
    gatekeepers.radio_week(world, m)
    gatekeepers.video_week(world, m)
    gatekeepers.tv_week(world, m)
    release.roll_week_audit(world, m, (world.date - dt.timedelta(days=1)).isoformat())
    from .player import commands
    commands.weekly_player(world, m)
    development.weekly(world, m)


def _scheduled(world, market):
    today = world.date.isoformat()
    for item in list(world.schedule):
        if item["date"] != today or item.get("market", market) != market or item.get("done"):
            continue
        if item["kind"] == "tv" and item.get("act") == world.player.get("act"):
            world.interrupts.append({"reason": "tv_performance", "program": item.get("program")})
            item["done"] = True
            continue
        if item["kind"] == "label_meeting":
            act = world.acts.get(item["act"])
            if act and act.label:
                development.meeting(world, market, act, item)
            item["done"] = True
            continue
        if item["kind"] == "showcase":
            act = world.acts.get(item["act"])
            if act and not act.label:
                labels.showcase(world, market, act, item)
            item["done"] = True


def _commitments(world):
    today = world.date.isoformat()
    for c in world.commitments:
        if c.get("done") or c["end"] > today:
            continue
        c["done"] = True
        if c["kind"] == "recording":
            rec = world.recordings.get(c["recording"])
            if rec and rec.status == "in_production":
                rec.status = "done"
                rec.completed = today
                eid = world.emit("creative", "recording_completed", [rec.id, rec.act], {"title": rec.title})
                if world.player.get("act") == rec.act:
                    world.interrupts.append({"reason": "recording_done", "recording": rec.id})
                    world.add_news(f"Finished recording \"{rec.title}\".", "studio", [rec.id, rec.act],
                                   tag="official", importance=0.7, event_id=eid)
    world.commitments = [c for c in world.commitments if not c.get("done") or c["end"] >= (
        world.date - dt.timedelta(days=60)).isoformat()]


def advance(world, days: int, stop_on_interrupt: bool = True, min_days: int = 1) -> dict:
    """Advance up to `days`, stopping early (after min_days) at an interrupt."""
    start = world.date
    world.interrupts = []
    n = 0
    while n < days:
        step_day(world)
        n += 1
        if stop_on_interrupt and world.interrupts and n >= min_days:
            break
    return {"from": start.isoformat(), "to": world.date.isoformat(), "days": n,
            "interrupts": list(world.interrupts)}

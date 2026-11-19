"""Releases: putting products into a market, shipping stock, reorders."""
from __future__ import annotations

import numpy as np

from ..core import dates
from ..tables import CHANNELS
from .creative import craft_score
from .demand import draw_reception, song_appeal


def expected_weekly_units(world, rel) -> float:
    """The label's (observed) belief about peak weekly units, used for pressing and promotion."""
    act = world.acts[rel.act]
    if rel.label is None:      # self-release: a few local shops and mail order
        return (300 + 8000 * act.singles_power_o) * (0.5 + rel.priority) * (3 if rel.kind == "album" else 1)
    if rel.kind == "single":
        return 4000 + 140000 * act.singles_power_o * (0.5 + rel.priority)
    return 8000 + 380000 * act.album_power_o * (0.5 + rel.priority)


def place_release(world, rel) -> None:
    """Make a planned release live in its market (called on its release date)."""
    market = rel.market
    rt = world.markets[market]
    T = world.tables[market]
    AT = world.albums[market]
    act = world.acts[rel.act]
    day = world.date.toordinal()
    fan = np.array(act.fandom.get(market, [0.0] * rt.G))
    rel.status = "released"
    rel.date = dates.iso(world.date)
    act.last_release = rel.date
    rel.expectation = round(expected_weekly_units(world, rel), 1)
    wk = world.config["consumption.initial_ship_weeks"]
    first = rel.expectation * wk
    if rel.kind == "album":
        first += fan.dot(rt.population(world.date)) * world.config["consumption.fan_album_buy"] * 0.8
    _ship(world, rel, first)
    if rel.kind == "single":
        for rid in rel.tracks:
            rec = world.recordings[rid]
            rec.status = "released"
            rec.single_release = rel.id
            i = T.add(rid)
            draw_reception(world, market, rec)
            T.view("appeal")[i] = song_appeal(world, market, rec, act)
            comp = world.compositions[rec.composition]
            T.view("hook")[i] = comp.attrs["hook"]
            T.view("depth")[i] = comp.attrs["depth"]
            T.view("talk")[i] = (world.config["listener.talk_base"] + 0.3 * rec.attrs["signature"]
                                 + 0.3 * rec.attrs["controversy"] + 0.2 * rec.attrs["dance_hook"]
                                 + 0.2 * comp.attrs["singability"])
            T.view("style")[i] = rec.style
            T.view("genre")[i] = rt.gidx.get(rec.genre, 0)
            T.view("released")[i] = day
            T.view("active")[i] = True
            T.view("commercial")[i] = rel.commercial
            T.view("fanvec")[i] = fan
            T.view("video_q")[i] = rec.video.get("quality", 0.0) if rec.video else 0.0
    else:
        a = AT.add(rel.id)
        AT.focus[a] = list(rel.focus)
        crafts = [craft_score(world, world.recordings[t]) for t in rel.tracks if t in world.recordings]
        AT.view("value")[a] = 0.7 + 0.6 * (sum(crafts) / max(1, len(crafts)))
        AT.view("released")[a] = day
        AT.view("active")[a] = True
        AT.view("fanvec")[a] = fan
        # album tracks stay available to be issued as singles later (status "released" means
        # "released as a single"); the album link lives in the album's track list
    eid = world.emit("release", "released", [rel.id, rel.act, *(rel.tracks[:3])],
                     {"title": rel.title, "kind": rel.kind, "label": rel.label, "market": market,
                      "expectation_weekly": rel.expectation, "initial_shipment": round(first),
                      "priority": rel.priority, "promo_tier": rel.promo_tier})
    from . import media
    media.on_release(world, rel, eid)
    if world.player.get("act") == rel.act:
        world.interrupts.append({"reason": "release_out", "release": rel.id})


def _ship(world, rel, units: float):
    units = max(0.0, float(units))
    rel.stock += units
    rel.shipped += units
    rt = world.markets[rel.market]
    if units > 0:
        cost = units * rt.manufacturing("album" if rel.kind == "album" else "single")
        world.ledger.transfer(world.date, release_account(world, rel), "ext:manufacturing", cost, "manufacturing", rel.id)


def release_account(world, rel) -> str:
    """Who pays for and receives the label share of a release: the label, or the self-releasing act's lead."""
    if rel.label:
        return f"org:{rel.label}"
    act = world.acts[rel.act]
    return act.members[0]["person"] if act.members else act.id


def weekly_restock(world, market: str, week_units: dict):
    """Reorders: keep about `reorder_weeks` of current demand in the channel."""
    wks = world.config["consumption.reorder_weeks"]
    for rid in sorted(week_units):
        rel = world.releases[rid]
        need = week_units[rid] * wks - rel.stock
        if rel.stockout_days:
            need *= 1.15
        if need > 50:
            _ship(world, rel, need)
        rel.stockout_days = 0


def roll_week_audit(world, market: str, week_end: str):
    """Move this week's channel impressions into the audit log and reset the counters."""
    T = world.tables[market]
    if not T.n:
        return
    wk = T.view("wk_imp")
    rows = np.nonzero(wk.sum(axis=1) > 0)[0]
    for i in rows:
        sid = T.ids[i]
        world.week_log.append({"song": sid, "market": market, "week_end": week_end, "data": {
            "impressions": {CHANNELS[c]: round(float(wk[i, c])) for c in range(len(CHANNELS))},
            "aware_pop": round(float((T.view("A")[i] * world.markets[market].population(world.date)).sum())),
            "engaged_pop": round(float((T.view("E")[i] * world.markets[market].population(world.date)).sum())),
            "radio_tiers": dict(zip(world.markets[market].format_ids, map(int, T.view("radio_tier")[i]))),
            "video_tiers": dict(zip(world.markets[market].channel_ids, map(int, T.view("video_tier")[i]))),
            "promo": [round(float(x), 3) for x in T.view("radio_promo")[i]],
        }})
    T.view("last_imp")[:] = wk
    wk[:] = 0.0

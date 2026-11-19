"""Media: news items from canonical events, and critics' reviews (separate from commercial appeal)."""
from __future__ import annotations

import numpy as np

from ..core import rng
from .creative import describe


def _fame(world, act, market) -> float:
    rt = world.markets[market]
    recog = np.array(act.recognition.get(market, [0.0] * rt.G))
    N = rt.population(world.date)
    return float((recog * N).sum() / N.sum())


def on_release(world, rel, eid):
    act = world.acts[rel.act]
    fame = _fame(world, act, rel.market)
    is_player = world.player.get("act") == rel.act
    if is_player or fame > 0.4 or (act.historical and fame > 0.1):
        label = world.orgs.get(f"org:{rel.label}") if rel.label else None
        lab = f" on {label.name}" if label else ""
        kind = "album" if rel.kind == "album" else "single"
        world.add_news(f"New {kind}: {act.name} - \"{rel.title}\"{lab}.", "release", [rel.id, rel.act],
                       tag="official", importance=0.3 + 0.5 * fame + (0.3 if is_player else 0), event_id=eid)
    if rel.kind == "album" and (fame > 0.15 or is_player):
        review(world, rel, eid)


def review(world, rel, cause_eid):
    rt = world.markets[rel.market]
    tracks = [world.recordings[t] for t in rel.tracks if t in world.recordings]
    if not tracks:
        return
    for oid, o in sorted(rt.outlets.items()):
        if o.get("kind") != "critic":
            continue
        taste = o.get("taste", {})
        vals = []
        for rec in tracks:
            comp = world.compositions[rec.composition].attrs
            a = {**comp, **rec.attrs}
            v = sum(w * a.get(k, 0.5) for k, w in taste.items()) / max(1e-9, sum(taste.values()))
            v += o.get("genre_bias", {}).get(rec.genre, 0.0)
            vals.append(v)
        coherence = 1 - float(np.std([r.style[0] for r in tracks])) if len(tracks) > 1 else 0.8
        shock = rng.normal(world.seed, "review", oid, rel.id)
        score = float(np.clip(0.75 * np.mean(vals) + 0.15 * coherence + 0.08 * shock + 0.05, 0, 1))
        stars = max(1.0, min(5.0, round((1 + 4 * score) * 2) / 2))
        lead = tracks[0]
        tags = describe(world, lead)[:3]
        eid = world.emit("media", "review", [rel.id, rel.act, f"outlet:{oid}"],
                         {"outlet": o["name"], "stars": stars, "score": round(score, 3), "descriptors": tags},
                         causes=[cause_eid], draws=[{"draw": "critic", "value": round(shock, 4)}])
        act = world.acts[rel.act]
        act.critical_prestige = round(0.8 * act.critical_prestige + 0.2 * score, 4)
        world.add_news(f"{o['name']} reviews {act.name}'s \"{rel.title}\": {stars:g}/5 stars "
                       f"({'; '.join(tags)}).", "review", [rel.id, rel.act], tag="official",
                       importance=0.3 + (0.4 if world.player.get('act') == rel.act else 0), event_id=eid)


def on_chart(world, cid, run, eid):
    entries = run["entries"]
    if not entries:
        return
    st = world.charts[cid]
    main = st.get("main")
    top = entries[0]
    if top["last"] != 1:
        world.add_news(f"{top['artist']} - \"{top['title']}\" is the new #1 on the {run['name']} "
                       f"(chart dated {run['issue_date']}).", "chart", [top["subject"], top["act"]],
                       tag="official", importance=0.8 if main else 0.45, event_id=eid)
    debuts = [e for e in entries if e["last"] is None and e["weeks"] == 1]
    if debuts and main:
        d = min(debuts, key=lambda e: e["rank"])
        if d["rank"] <= 40:
            world.add_news(f"Hot shot debut on the {run['name']}: {d['artist']} - \"{d['title']}\" enters at "
                           f"#{d['rank']}.", "chart", [d["subject"], d["act"]], tag="official",
                           importance=0.5, event_id=eid)
    pa = world.player.get("act")
    for e in entries:
        if e["act"] == pa:
            move = ("new entry" if e["last"] is None else
                    f"up from #{e['last']}" if e["rank"] < e["last"] else
                    f"down from #{e['last']}" if e["rank"] > e["last"] else "holding")
            world.add_news(f"\"{e['title']}\" is #{e['rank']} on the {run['name']} ({move}; peak #{e['peak']}, "
                           f"{e['weeks']} wk).", "chart", [e["subject"], pa], tag="official", importance=0.9,
                           event_id=eid)
            if e["last"] is None:
                world.interrupts.append({"reason": "chart_entry", "chart": cid, "subject": e["subject"]})

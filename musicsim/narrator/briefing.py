"""Engine-generated context for the narrator: the industry landscape, the protagonist's team, and
why time stopped where it did. Everything here is read from world state; nothing is hand-written."""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates
from ..systems.charts import methodology_for

STOP_REASONS = {
    "offer": "an offer arrived that needs the player's answer",
    "showcase": "the showcase happened",
    "recording_done": "a recording session finished",
    "release_out": "a release came out",
    "chart_entry": "a record entered a chart",
    "top_40": "a record reached the Top 40",
    "top_10": "a record reached the Top 10",
    "number_one": "a record reached #1",
    "tv_booking": "a TV booking came through",
    "tv_performance": "a TV performance airs today",
    "label_reinvests": "the label decided to push harder behind a record",
    "certified": "a release was certified",
    "debt": "money trouble",
    "exhaustion": "exhaustion",
    "label_meeting": "a development meeting with the label",
    "label_warning": "the label warned that it is losing patience",
    "dropped": "the label dropped the act",
}


def _fame(world, act, market):
    rt = world.markets[market]
    N = rt.population(world.date)
    return float((np.array(act.recognition.get(market, [0.0] * rt.G)) * N).sum() / N.sum())


def _words(v, scale=("very low", "low", "moderate", "high", "very high")):
    return scale[min(4, max(0, int(v * 5)))]


def _current(world, act, kind, days=150):
    best = None
    for rel in world.releases.values():
        if rel.act == act.id and rel.kind == kind and rel.status == "released":
            if (world.date - dates.parse(rel.date)).days <= days and (best is None or rel.date > best.date):
                best = rel
    return best


def _chart_pos(world, market, subject):
    out = {}
    for cid, st in world.charts.items():
        if st.get("market") != market:
            continue
        for e in st.get("last_entries", []):
            if e["subject"] == subject:
                out[st.get("name", cid)] = e["rank"]
    return out


def landscape(world, market: str) -> dict:
    rt = world.markets[market]
    d = world.date
    N = rt.population(d)
    acts = [a for a in world.acts.values() if a.controller == "npc" and a.active]
    stars = sorted([a for a in acts if a.historical], key=lambda a: (-_fame(world, a, market), a.id))[:18]

    def act_row(a):
        single = _current(world, a, "single")
        album = _current(world, a, "album", 400)
        nxt = min((r for r in world.releases.values() if r.act == a.id and r.status == "planned"
                   and r.date <= (d + dt.timedelta(days=42)).isoformat()), key=lambda r: r.date, default=None)
        lab = world.orgs.get(f"org:{a.label}") if a.label else None
        row = {"name": a.name, "real": a.historical, "label": lab.name if lab else "unsigned", "genres": a.genres,
               "public_recognition_pct": round(_fame(world, a, market) * 100, 1), "stage": a.stage,
               "momentum": _words(max(0.0, min(1.0, 0.5 + a.momentum / 2)),
                                  ("collapsing", "cooling", "steady", "hot", "red-hot"))}
        if single:
            row["current_single"] = {"title": single.title, "released": single.date,
                                     "charts": _chart_pos(world, market, single.tracks[0])}
        if album:
            row["current_album"] = {"title": album.title, "released": album.date, "certified": album.cert or None,
                                    "charts": _chart_pos(world, market, album.id)}
        if nxt:
            row["announced"] = {"title": nxt.title, "kind": nxt.kind, "date": nxt.date}
        return row

    rising = sorted([a for a in acts if 0.02 < _fame(world, a, market) < 0.35],
                    key=lambda a: (-a.momentum, a.id))[:6]
    groups = {}
    for o in sorted(world.orgs.values(), key=lambda o: (-o.params.get("size", 0), o.id)):
        if o.kind != "record_company" or o.market != market:
            continue
        parent = world.orgs.get(o.parent)
        roster = sorted([world.acts[x] for x in o.roster if x in world.acts and world.acts[x].historical],
                        key=lambda a: -_fame(world, a, market))
        head = world.people.get(o.people.get("head", ""))
        groups.setdefault(parent.name if parent else "independent", []).append({
            "label": o.name, "fictional": not o.historical,
            "size": _words(min(1.0, o.params.get("size", 0.5) / 1.5), ("tiny", "small", "mid-size", "major", "flagship")),
            "strengths": sorted(o.strategy["focus"], key=lambda g: -o.strategy["focus"][g])[:3],
            "appetite_for_risk": _words(o.strategy.get("risk", 0.5)),
            "head": head.name if head else None,
            "notable_artists": [a.name for a in roster[:5]]})
    audiences = []
    for i, s in enumerate(rt.seg_ids):
        seg = rt.seg[s]
        fav = sorted(seg["taste"], key=lambda g: -seg["taste"][g])[:3]
        radio = sorted(rt.format_ids, key=lambda f: -rt.format_reach[rt.fidx[f], i])[:2]
        audiences.append({"segment": seg["label"], "people_millions": round(N[i] / 1e6, 1),
                          "music_spend_per_person_per_year": round(dates.interp_series(seg["budget_per_capita"], d)),
                          "favourite_styles": [rt.genre_meta[g]["label"] for g in fav],
                          "listens_to": [rt.formats[f]["name"] for f in radio if rt.format_reach[rt.fidx[f], i] > 0.05],
                          "buys_singles": _words(seg["single_propensity"] / 0.12),
                          "buys_albums": _words(seg["album_propensity"] / 0.4)})
    tv = [{"program": p["name"], "performance_slots_per_week": p["slots_per_week"],
           "hard_to_book": _words(p["booking_threshold"] / 0.7, ("easy", "fairly easy", "moderate", "hard", "very hard")),
           "audience": sorted(p["viewers"], key=lambda s: -p["viewers"][s])[:2]}
          for pid, p in sorted(rt.programs.items()) if rt.program_valid(pid, d)]
    charts = []
    for cid in rt.chart_ids:
        v = methodology_for(rt.methodologies[cid], d)
        if v:
            st = world.charts.get(cid, {})
            top = st.get("last_run", {}).get("top", [])
            charts.append({"chart": st.get("name", cid), "method": v.get("note") or v["id"],
                           "number_one": f"{top[0]['artist']} — {top[0]['title']}" if top else None})
    return {
        "as_of": d.isoformat(),
        "biggest_real_artists_right_now": [act_row(a) for a in stars],
        "acts_on_the_rise": [act_row(a) for a in rising],
        "record_companies": groups,
        "audiences": audiences,
        "radio_formats": [{"format": rt.formats[f]["name"], "current_playlist_size": int(rt.playlist[i])}
                          for i, f in enumerate(rt.format_ids)],
        "music_video_channels": [rt.channels[c]["name"] for c in rt.channel_ids if rt.channel_valid(c, d)],
        "tv_music_bookings": tv,
        "charts_in_force": charts,
        "market": {"typical_album_price": round(rt.price("album", d), 2),
                   "typical_single_price": round(rt.price("single", d), 2),
                   "singles_market": _words(rt.singles_market(d) / 1.1),
                   "release_day": rt.release_weekday(d),
                   "songwriter_mechanical_rate_per_song": rt.mechanical_rate(d),
                   "certification": f"{rt.data['certification']['body']} (based on {rt.data['certification']['basis']})"},
        "evidence_note": ("Real artists, labels, institutions and dates come from the engine's historical data "
                          "(tier A/B). Their statistics are engine estimates, and everything after the campaign start "
                          "is simulated. Acts marked real=false are generated and fictional."),
    }


def team(world, since: str) -> dict:
    from ..player.delegation import ALWAYS_ASK, manager, policy
    mg = manager(world)
    m = world.people.get(mg["person"]) if mg else None
    delegated = [n["text"] for n in world.news if n["date"] >= since and n["kind"] == "team"]
    return {"manager": {"name": m.name, "person_id": m.id, "commission": mg["commission"], "since": mg["since"]}
            if m else None,
            "standing_orders": policy(world),
            "always_comes_back_to_you": ALWAYS_ASK,
            "handled_for_you_this_pass": delegated,
            "what_people_are_telling_you": world.flags.get("advice", [])}


def pacing(world, since: str, interrupts: list) -> dict:
    days = (world.date - dates.parse(since)).days
    reasons = []
    for i in interrupts:
        r = STOP_REASONS.get(i.get("reason"), i.get("reason"))
        if r not in reasons:
            reasons.append(r)
    return {"days_covered": days, "stopped_because": reasons or ["the requested time passed quietly"],
            "guidance": ("Give the moments that stopped the clock full scenes. Summarise routine stretches in a few "
                         "evocative paragraphs. Choose the next 'advance' from what the protagonist is doing: "
                         "'next' runs until something needs attention (at most about 3 months); a few days for "
                         "intense periods; weeks or months for routine.")}

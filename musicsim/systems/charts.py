"""Chart engine: computes rankings from MEASURED activity using dated methodology data.

A chart exists only inside its methodology's validity windows. The same simulated
consumption measured by different methods (store rank reports vs point-of-sale
tracking) produces different chart dynamics.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates, rng
from .demand import album_units, song_audience, song_units

TIER_POINTS = np.array([0.0, 1.0, 2.0, 3.0, 4.0])


def main_chart(world, market: str, subject: str) -> dict:
    """State of the market's main chart for a subject (song/album), or {}."""
    for st in world.charts.values():
        if st.get("market") == market and st.get("subject") == subject and st.get("main"):
            return st
    return {}


def methodology_for(meth: dict, d):
    for v in meth["versions"]:
        lo, hi = v["valid"]
        if dates.in_window(d, lo, hi):
            return v
    return None


def chart_name(meth: dict, d) -> str:
    name = meth["id"]
    for n in meth.get("names", []):
        if dates.parse(n["from"]) <= d:
            name = n["name"]
    return name


def compile_week(world, market: str):
    """Compile every weekly chart whose tracking week ended yesterday."""
    rt = world.markets[market]
    end = world.date - dt.timedelta(days=1)
    first_song = next((c for c in rt.chart_ids if rt.methodologies[c]["subject"] == "song"), None)
    first_album = next((c for c in rt.chart_ids if rt.methodologies[c]["subject"] == "album"), None)
    for cid in rt.chart_ids:
        meth = rt.methodologies[cid]
        if meth.get("period", "weekly") != "weekly":
            continue
        if dates.WEEKDAYS[end.weekday()] != meth.get("window_end", "sunday"):
            continue
        version = methodology_for(meth, end)
        if version is None:
            continue
        _compile(world, market, cid, meth, version, end, main=cid in (first_song, first_album))


def _compile(world, market, cid, meth, version, end, main):
    rt = world.markets[market]
    T = world.tables[market]
    AT = world.albums[market]
    subject = meth["subject"]
    end_day = end.toordinal()
    days = 7
    seg_scope = meth.get("scope_segments")
    seg_idx = [rt.sidx[s] for s in seg_scope] if seg_scope else None
    st = world.charts.setdefault(cid, {"market": market, "subject": subject, "size": meth["size"], "main": main,
                                       "prev": {}, "stats": {}, "last_entries": []})
    st["main"] = main
    table = T if subject == "song" else AT
    if table.n == 0:
        return
    ids = table.ids
    elig = np.ones(table.n, dtype=bool)
    if subject == "song":
        elig &= T.released <= end_day
        if version.get("eligibility", {}).get("commercial_single"):
            elig &= T.commercial
        genres = meth.get("eligibility_genres")
        if genres:
            gset = {rt.gidx[g] for g in genres if g in rt.gidx}
            elig &= np.isin(T.genre, list(gset))
    else:
        elig &= AT.released <= end_day
    measures: dict[str, np.ndarray] = {}
    comps: dict[str, np.ndarray] = {}
    for inp, spec in version["inputs"].items():
        if inp == "sales":
            raw = (song_units if subject == "song" else album_units)(world, market, end_day, days, seg_idx)
            m = raw * spec.get("coverage", 1.0)
        elif inp == "airplay":
            fidx = [rt.fidx[f] for f in spec["formats"]]
            if version["measurement"] == "rank_report":
                m = (TIER_POINTS[T.radio_tier[:, fidx]] * T.radio_share[:, fidx] * rt.reporters[fidx]).sum(axis=1)
            else:
                m = song_audience(world, market, end_day, days, fidx)
        else:
            continue
        noise = np.array([rng.normal(world.seed, "chart", cid, inp, ids[i], end.isoformat()) for i in range(table.n)])
        m = np.maximum(0.0, m * (1 + spec.get("noise", 0.0) * noise))
        if version["measurement"] == "rank_report":
            inertia = version.get("inertia", 0.0)
            prev = st["prev"].get(inp, {})
            pv = np.array([prev.get(ids[i], 0.0) for i in range(table.n)])
            m = inertia * pv + (1 - inertia) * m
            st["prev"][inp] = {ids[i]: round(float(m[i]), 3) for i in range(table.n) if m[i] > 0.01}
        measures[inp] = m * elig
    score = np.zeros(table.n)
    for inp, m in measures.items():
        spec = version["inputs"][inp]
        if version["measurement"] == "rank_report":
            L = spec.get("list_length", meth["size"])
            order = np.argsort(-m, kind="stable")
            pts = np.zeros(table.n)
            for r, i in enumerate(order[:L]):
                if m[i] <= 0:
                    break
                pts[i] = (1 - r / L) ** 1.2
            comps[inp] = pts
            score += spec["weight"] * pts
        else:
            comps[inp] = m / spec["ref"]
            score += spec["weight"] * m / spec["ref"]
    # deterministic tie-break on id order
    order = sorted([i for i in range(table.n) if score[i] > 1e-6], key=lambda i: (-score[i], ids[i]))
    order = order[: meth["size"]]
    stats = st["stats"]
    entries = []
    for rank, i in enumerate(order, start=1):
        sid = ids[i]
        s = stats.setdefault(sid, {"peak": rank, "weeks": 0, "last": None, "debut": end.isoformat()})
        last = s["last"]
        s["weeks"] += 1
        s["peak"] = min(s["peak"], rank)
        if subject == "song":
            rec = world.recordings[sid]
            title, act_id = rec.title, rec.act
        else:
            rel = world.releases[sid]
            title, act_id = rel.title, rel.act
        entries.append({
            "rank": rank, "last": last, "peak": s["peak"], "weeks": s["weeks"], "subject": sid, "title": title,
            "act": act_id, "artist": world.acts[act_id].name, "score": round(float(score[i]), 5),
            "measured": {k: round(float(v[i]), 1) for k, v in measures.items()},
            "points": {k: round(float(v[i]), 4) for k, v in comps.items()},
        })
    on_chart = {e["subject"] for e in entries}
    for sid, s in stats.items():
        if sid in on_chart:
            s["last"] = next(e["rank"] for e in entries if e["subject"] == sid)
        else:
            s["last"] = None
    st["last_entries"] = [{"rank": e["rank"], "subject": e["subject"]} for e in entries]
    st["week_end"] = end.isoformat()
    issue = end + dt.timedelta(days=meth.get("issue_offset_days", 0))
    name = chart_name(meth, end)
    st["name"] = name
    st["methodology"] = version["id"]
    run = {"chart": cid, "week_end": end.isoformat(), "issue_date": issue.isoformat(), "name": name,
           "methodology": version["id"], "entries": entries}
    world.chart_log.append(run)
    st["last_run"] = {"week_end": run["week_end"], "issue_date": run["issue_date"], "name": name,
                      "methodology": version["id"], "top": entries[:40]}
    eid = world.emit("charts", "chart_published", [cid], {
        "name": name, "week_end": end.isoformat(), "issue_date": issue.isoformat(), "methodology": version["id"],
        "number_one": entries[0]["title"] + " - " + entries[0]["artist"] if entries else None,
        "entries": len(entries)})
    if main and subject == "song":
        T.view("vis")[:] = 0.0
        for e in entries:
            # only the upper reaches of a chart reach the general public (countdowns, news, word of mouth)
            T.view("vis")[T.index[e["subject"]]] = max(0.0, (41 - e["rank"]) / 40) ** 3
    from . import media
    media.on_chart(world, cid, run, eid)

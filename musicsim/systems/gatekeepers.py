"""Gatekeepers who decide exposure from their own observations: radio programmers,
music-video channel programmers and TV bookers. Weekly decisions, every add/drop and
booking is logged with its score components."""
from __future__ import annotations

import datetime as dt

import numpy as np

from ..core import dates, rng

TIER_NAMES = {0: "-", 1: "light", 2: "medium", 3: "heavy", 4: "power"}


def _chart_prominence(world, market: str) -> dict[str, float]:
    """Song id -> 0..1 prominence from the most recent published singles charts."""
    out: dict[str, float] = {}
    for cid, st in world.charts.items():
        if st.get("market") != market or st.get("subject") != "song":
            continue
        weight = 1.0 if st.get("main") else 0.6
        size = st.get("size", 100)
        for e in st.get("last_entries", []):
            p = weight * max(0.0, (size + 1 - e["rank"]) / size) ** 1.5
            out[e["subject"]] = max(out.get(e["subject"], 0.0), p)
    return out


def radio_week(world, market: str):
    cfg = world.config.tree["radio"]
    rt = world.markets[market]
    T = world.tables[market]
    if not T.n:
        return
    d = world.date
    day = d.toordinal()
    N = rt.population(d)
    prom = _chart_prominence(world, market)
    rows = np.nonzero(T.active & (T.released <= day))[0]
    E = T.view("E")
    tiers = T.view("radio_tier")
    weeks = T.view("radio_weeks")
    peak = T.view("radio_peak")
    for f, fid in enumerate(rt.format_ids):
        reach = rt.format_reach[f] * N
        aud_total = reach.sum()
        scored = []
        for i in rows:
            sid = T.ids[i]
            rec = world.recordings[sid]
            act = world.acts[rec.act]
            fit = rt.format_aff[f, T.view("genre")[i]]
            if fit < 0.05:
                continue
            research_true = float((E[i] * reach).sum() / aud_total)
            noise = rng.normal(world.seed, "radio", fid, sid, d.isoformat())
            research = max(0.0, research_true * (1 + 0.25 * noise))
            other = [tiers[i, g] for g in range(rt.F) if g != f]
            crossover = max(other) / 4.0 if other else 0.0
            signal = max(prom.get(sid, 0.0), 0.5 * crossover)
            promo = T.view("radio_promo")[i, f]
            score = (cfg["w_fit"] * fit + cfg["w_research"] * min(1.0, research * 4)
                     + cfg["w_promo"] * promo + cfg["w_signal"] * signal
                     + cfg["w_act"] * act.singles_power_o
                     + cfg["noise"] * rng.normal(world.seed, "radio_taste", fid, sid, d.isoformat()))
            on = tiers[i, f] > 0
            # burn: research falling well below its peak after a while on the playlist
            burn = on and weeks[i, f] >= cfg["min_weeks_before_drop"] and peak[i, f] > 0.02 \
                and research < cfg["burn_drop"] * peak[i, f]
            # current -> recurrent: programmers retire long-running songs from current rotation
            burn = burn or (on and weeks[i, f] >= cfg["recurrent_after_weeks"]
                            and research < 0.85 * peak[i, f]) or (on and weeks[i, f] >= cfg["max_current_weeks"])
            age_weeks = (day - T.view("released")[i]) / 7
            stale = (not on) and (age_weeks > 26 or weeks[i, f] >= cfg["recurrent_after_weeks"])
            scored.append((score, i, on, burn, stale, research, fit, promo, signal))
        keep = [s for s in scored if s[2] and not s[3] and s[0] >= cfg["drop_threshold"]]
        drops = [s for s in scored if s[2] and (s[3] or s[0] < cfg["drop_threshold"])]
        cands = sorted([s for s in scored if not s[2] and not s[4] and s[0] >= cfg["add_threshold"]],
                       key=lambda s: (-s[0], T.ids[s[1]]))
        cap = int(rt.playlist[f])
        room = max(0, cap - len(keep))
        adds = cands[: min(room, cfg["max_adds_per_week"])]
        playlist = sorted(keep + adds, key=lambda s: (-s[0], T.ids[s[1]]))
        if len(playlist) > cap:
            for s in playlist[cap:]:
                drops.append(s)
            playlist = playlist[:cap]
        share = T.view("radio_share")
        national = {s[1] for s in playlist}
        for s in drops:
            i = s[1]
            if share[i, f] >= 0.99:
                _log_radio(world, market, fid, "radio_drop", s, burn=s[3])
            tiers[i, f] = 0
            share[i, f] = 0.0
        for rank, s in enumerate(playlist):
            i = s[1]
            new_tier = 4 if rank < 7 else 3 if rank < 16 else 2 if rank < 27 else 1
            if tiers[i, f] == 0 or share[i, f] < 0.99:
                _log_radio(world, market, fid, "radio_add", s, tier=new_tier)
            tiers[i, f] = new_tier
            share[i, f] = 1.0
            weeks[i, f] += 1
            peak[i, f] = max(peak[i, f], s[5])
        # regional pickup: below the national bar, a minority of stations may still play a record
        reg_bar = cfg["add_threshold"] - cfg["regional_margin"]
        for s in scored:
            i = s[1]
            if i in national or s[3] or s[4]:
                if i not in national and share[i, f] < 0.99 and tiers[i, f] > 0:
                    tiers[i, f] = 0
                    share[i, f] = 0.0
                continue
            if s[0] >= reg_bar:
                target = float(np.clip(0.03 + 0.6 * (s[0] - reg_bar), 0.03, cfg["regional_max_share"]))
                was = tiers[i, f] > 0
                share[i, f] = target if not was else 0.5 * share[i, f] + 0.5 * target
                tiers[i, f] = 1
                weeks[i, f] += 1
                peak[i, f] = max(peak[i, f], s[5])
                if not was:
                    _log_radio(world, market, fid, "radio_regional_add", s, tier=1, share=share[i, f])
            elif tiers[i, f] > 0 and share[i, f] < 0.99:
                tiers[i, f] = 0
                share[i, f] = 0.0


def _log_radio(world, market, fid, kind, s, tier=None, burn=False, share=None):
    T = world.tables[market]
    sid = T.ids[s[1]]
    rec = world.recordings[sid]
    data = {"format": fid, "score": round(s[0], 3), "fit": round(float(s[6]), 3),
            "research_observed": round(s[5], 4), "promo": round(float(s[7]), 3), "signal": round(s[8], 3)}
    if tier:
        data["tier"] = TIER_NAMES[tier]
    if burn:
        data["reason"] = "listener burn"
    if share is not None:
        data["station_share"] = round(float(share), 3)
    eid = world.emit("radio", kind, [sid, rec.act], data, public=True)
    if world.player.get("act") == rec.act:
        rt = world.markets[market]
        name = rt.formats[fid]["name"]
        if kind == "radio_regional_add":
            text = (f"A handful of {name} stations (about {share:.0%} of the format) started playing "
                    f"\"{rec.title}\".")
        else:
            verb = "added" if kind == "radio_add" else "dropped"
            text = f"{name} programmers nationally {verb} \"{rec.title}\"" + \
                   (f" ({TIER_NAMES[tier]} rotation)" if tier else "") + "."
        world.add_news(text, "radio", [sid, rec.act], tag="official", importance=0.6, event_id=eid)


def video_week(world, market: str):
    cfg = world.config.tree["video"]
    rt = world.markets[market]
    T = world.tables[market]
    if not T.n:
        return
    d = world.date
    day = d.toordinal()
    prom = _chart_prominence(world, market)
    rows = np.nonzero(T.active & (T.released <= day) & (T.view("video_q") > 0))[0]
    tiers = T.view("video_tier")
    weeks = T.view("video_weeks")
    for v, cid in enumerate(rt.channel_ids):
        if not rt.channel_valid(cid, d):
            continue
        scored = []
        for i in rows:
            sid = T.ids[i]
            rec = world.recordings[sid]
            act = world.acts[rec.act]
            fit = rt.channel_aff[v, T.view("genre")[i]]
            if fit < 0.05:
                continue
            score = (cfg["w_quality"] * T.view("video_q")[i] + cfg["w_fit"] * fit
                     + cfg["w_signal"] * prom.get(sid, 0.0) + cfg["w_act"] * act.singles_power_o
                     + cfg["w_promo"] * T.view("radio_promo")[i].max()
                     + cfg["noise"] * rng.normal(world.seed, "video", cid, sid, d.isoformat()))
            on = tiers[i, v] > 0
            expired = on and weeks[i, v] >= cfg["drop_after_weeks"] and prom.get(sid, 0) < 0.3
            scored.append((score, i, on, expired, fit))
        keep = [s for s in scored if s[2] and not s[3]]
        cands = sorted([s for s in scored if not s[2] and s[0] >= cfg["add_threshold"]],
                       key=lambda s: (-s[0], T.ids[s[1]]))
        cap = int(rt.channels[cid]["playlist"])
        playlist = sorted(keep + cands[: max(0, cap - len(keep))], key=lambda s: (-s[0], T.ids[s[1]]))[:cap]
        on_ids = {s[1] for s in playlist}
        for s in scored:
            if s[2] and s[1] not in on_ids:
                tiers[s[1], v] = 0
                weeks[s[1], v] = 0
        for rank, s in enumerate(playlist):
            i = s[1]
            new = 3 if rank < 10 else 2 if rank < 25 else 1
            if tiers[i, v] == 0:
                sid = T.ids[i]
                rec = world.recordings[sid]
                eid = world.emit("video", "video_add", [sid, rec.act],
                                 {"channel": cid, "score": round(s[0], 3), "fit": round(float(s[4]), 3),
                                  "video_quality": round(float(T.view("video_q")[i]), 3)})
                if world.player.get("act") == rec.act:
                    world.add_news(f"{rt.channels[cid]['name']} put the \"{rec.title}\" video into rotation.",
                                   "video", [sid, rec.act], tag="official", importance=0.6, event_id=eid)
            tiers[i, v] = new
            weeks[i, v] += 1


def tv_week(world, market: str):
    """Book performances for the coming week."""
    rt = world.markets[market]
    T = world.tables[market]
    if not T.n:
        return
    d = world.date
    day = d.toordinal()
    N = rt.population(d)
    prom = _chart_prominence(world, market)
    rows = [i for i in np.nonzero(T.active & (T.released <= day))[0] if day - T.view("released")[i] < 120]
    booked_acts: set[str] = set()
    for pid in sorted(rt.programs):
        if not rt.program_valid(pid, d):
            continue
        prog = rt.programs[pid]
        viewers = np.array([prog["viewers"].get(s, 0.0) for s in rt.seg_ids])
        vpop = viewers * N
        scored = []
        for i in rows:
            sid = T.ids[i]
            rec = world.recordings[sid]
            act = world.acts[rec.act]
            if rec.act in booked_acts:
                continue
            g = rt.genre_ids[T.view("genre")[i]]
            fit = prog["genre_affinity"].get(g, 0.0)
            if fit < 0.1:
                continue
            recog = np.array(act.recognition.get(market, [0.0] * rt.G))
            draw_power = float((recog * vpop).sum() / max(1.0, vpop.sum()))
            push = world.flags.get("tv_push", {}).get(sid, 0.0)      # a manager working the bookers
            score = (0.9 * draw_power + 0.8 * prom.get(sid, 0.0) + 0.25 * max(0.0, act.momentum)
                     + 0.35 * T.view("tv_promo")[i] + 0.15 * fit + push
                     + 0.10 * rng.normal(world.seed, "tv", pid, sid, d.isoformat()))
            scored.append((score, sid, rec.act, draw_power, fit))
        scored.sort(key=lambda s: (-s[0], s[1]))
        slots = int(prog["slots_per_week"])
        for s in [x for x in scored if x[0] >= prog["booking_threshold"]][:slots]:
            score, sid, aid, draw_power, fit = s
            act = world.acts[aid]
            perf = np.mean([world.people[m["person"]].skills.get("performance", 0.5)
                            for m in act.members if m["person"] in world.people] or [0.5])
            shock = rng.normal(world.seed, "tv_stage", pid, sid, d.isoformat())
            impact = float(np.clip(0.55 + 0.8 * perf + 0.12 * shock, 0.3, 1.6))
            air = d + dt.timedelta(days=int(rng.uniform(world.seed, "tv_day", pid, sid, d.isoformat()) * 6) + 1)
            imp = (viewers * rt.tv_exposures * impact).tolist()
            eid = world.emit("television", "tv_booking", [sid, aid, f"program:{pid}"],
                             {"program": prog["name"], "air_date": air.isoformat(), "score": round(score, 3),
                              "audience_draw": round(draw_power, 3), "stage_impact": round(impact, 3)},
                             draws=[{"draw": "stage", "value": round(shock, 4)}])
            world.schedule.append({"kind": "tv", "date": air.isoformat(), "market": market, "song": sid,
                                   "act": aid, "program": pid, "impressions": imp, "impact": impact, "event": eid})
            booked_acts.add(aid)
            if act.recognition.get(market):
                recog = np.array(act.recognition[market])
                act.recognition[market] = (1 - (1 - recog) * (1 - 0.6 * viewers * impact)).round(6).tolist()
            if world.player.get("act") == aid:
                world.add_news(f"Booked to perform \"{world.recordings[sid].title}\" on {prog['name']} ({air.isoformat()}).",
                               "tv", [sid, aid], tag="official", importance=0.7, event_id=eid)
                world.interrupts.append({"reason": "tv_booking", "event": eid})
            elif score > 1.0:
                world.add_news(f"{act.name} will perform on {prog['name']}.", "tv", [aid], importance=0.3, event_id=eid)
    # prune past schedule items
    world.schedule = [s for s in world.schedule if dates.parse(s["date"]) >= d - dt.timedelta(days=1)]

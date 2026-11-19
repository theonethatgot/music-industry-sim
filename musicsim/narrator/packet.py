"""Narrator packets: what the protagonist can know, rich enough for immersive scenes.

The JSON is authoritative for the engine; the Markdown is the same content written for the
narrator (ChatGPT), plus the rules and the validated return format.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np

from ..core import dates
from ..player import commands as cmds
from ..player import proposals as props
from ..systems.charts import main_chart

PACKET_VERSION = 1


def _words(v: float, scale=("very low", "low", "moderate", "high", "very high")) -> str:
    return scale[min(4, max(0, int(v * 5)))]


def _aff(v: float) -> str:
    return ("hostile" if v < -0.4 else "cool" if v < -0.1 else "neutral" if v < 0.15 else "friendly" if v < 0.45
            else "close")


def _person_traits(p) -> list[str]:
    t = []
    pers = p.personality
    for k, hi, lo in (("ambition", "driven", "unhurried"), ("sociability", "outgoing", "reserved"),
                      ("ego", "proud", "modest"), ("risk_tolerance", "risk-taking", "cautious"),
                      ("discipline", "disciplined", "loose"), ("temperament", "volatile", "even-tempered"),
                      ("loyalty", "loyal", "transactional")):
        if k in pers:
            if pers[k] >= 0.7:
                t.append(hi)
            elif pers[k] <= 0.3:
                t.append(lo)
    avc = pers.get("artistic_vs_commercial")
    if avc is not None:
        t.append("artistically minded" if avc > 0.35 else "commercially minded" if avc < -0.35 else "")
    return [x for x in t if x]


def _fame(world, act, market):
    rt = world.markets[market]
    N = rt.population(world.date)
    rec = np.array(act.recognition.get(market, [0.0] * rt.G))
    return float((rec * N).sum() / N.sum()), {rt.seg[s]["label"]: round(float(rec[i]) * 100, 1)
                                               for i, s in enumerate(rt.seg_ids)}


def build(world, store, campaign_id: str, since: str | None) -> dict:
    m = world.player["market"]
    rt = world.markets[m]
    pid = world.player["person"]
    p = world.people[pid]
    act = world.player_act
    today = world.date.isoformat()
    since = since or (world.date - dt.timedelta(days=14)).isoformat()
    world.pass_no += 1
    pass_id = f"{campaign_id}-{world.pass_no:04d}"
    world.flags["pass_new_people"] = 0
    fame, by_seg = _fame(world, act, m)
    age = None
    if p.birth_date:
        b = dates.parse(p.birth_date)
        age = world.date.year - b.year - ((world.date.month, world.date.day) < (b.month, b.day))
    label = world.orgs.get(f"org:{act.label}") if act.label else None
    contract = world.contracts.get(act.contract) if act.contract else None

    protagonist = {
        "person_id": pid, "act_id": act.id, "name": p.name, "act_name": act.name, "age": age,
        "city": p.home_city, "background": p.notes, "genres": act.genres, "persona": act.persona,
        "career_stage": act.stage,
        "abilities_as_your_team_sees_them": {k: round(v * 100) for k, v in sorted(p.skills.items())},
        "wellbeing": {k: _words(v) for k, v in p.wellbeing.items()},
        "public_recognition_pct": round(fame * 100, 2),
        "recognition_by_audience_pct": by_seg,
        "local_live_buzz": _words(act.live_buzz),
        "industry_view": {"singles_track_record": _words(act.singles_power_o), "momentum": round(act.momentum, 2),
                          "critical_standing": _words(act.critical_prestige)},
        "label": label.name if label else None,
        "contract": ({"label": label.name, "terms": contract.terms, "since": contract.start,
                      "royalty_account_estimate": round(act.unrecouped, 2),
                      "recoupment_note": "negative = still unrecouped; royalties are paid only after recoupment"}
                     if contract and label else None),
    }
    L = world.ledger
    journal = [j for j in L.journal if pid in (j["from"], j["to"]) and j["date"] >= since]
    inc = sum(j["amount"] for j in journal if j["to"] == pid)
    out = sum(j["amount"] for j in journal if j["from"] == pid)
    finances = {"cash": L.balance(pid), "period_income": round(inc, 2), "period_spending": round(out, 2),
                "day_job": world.flags.get("day_job"), "lifestyle": world.flags.get("lifestyle"),
                "recent": [{k: j[k] for k in ("date", "amount", "category", "memo")} | {"in": j["to"] == pid}
                           for j in journal[-12:]]}

    calendar = sorted(
        [{"date": c["start"], "until": c["end"], "what": c["label"], "kind": c["kind"]}
         for c in world.commitments if c.get("who") == pid and c["end"] >= today and not c.get("done")] +
        [{"date": s["date"], "what": (world.markets[m].programs[s["program"]]["name"] + " performance")
          if s["kind"] == "tv" else (f"{s['kind']} at {s['venue']}" if s.get("venue") else s["kind"])
          + (f" — {s['note']}" if s.get("note") else ""), "kind": s["kind"]}
         for s in world.schedule if s.get("act") == act.id and s["date"] >= today and not s.get("done")],
        key=lambda x: x["date"])

    # creative inventory -------------------------------------------------------------
    songbook = []
    for cid in world.flags.get("songbook", []):
        c = world.compositions[cid]
        if c.status == "recorded":
            continue
        pitch = next((o for o in world.offers.values() if o.terms.get("composition") == cid), None)
        songbook.append({"composition_id": cid, "title": c.title, "genre": c.genre,
                         "writers": [world.people[w["person"]].name for w in c.writers if w["person"] in world.people],
                         "your_impression": pitch.terms.get("impression") if pitch else None})
    recordings = []
    for rec in sorted((r for r in world.recordings.values() if r.act == act.id), key=lambda r: r.started):
        entry = {"recording_id": rec.id, "title": rec.title, "genre": rec.genre, "status": rec.status,
                 "producers": [world.people[x].name for x in rec.producers if x in world.people],
                 "started": rec.started, "completed": rec.completed, "has_video": bool(rec.video),
                 "single_release": rec.single_release, "brief": rec.notes}
        if rec.status in ("done", "released"):
            entry.update(cmds.describe_recording_for_player(world, rec))
        recordings.append(entry)
    releases = []
    T = world.tables[m]
    s_stats = main_chart(world, m, "song").get("stats", {})
    a_stats = main_chart(world, m, "album").get("stats", {})
    for rel in sorted((r for r in world.releases.values() if r.act == act.id), key=lambda r: r.date):
        e = {"release_id": rel.id, "title": rel.title, "kind": rel.kind, "date": rel.date, "status": rel.status,
             "label": world.orgs[f"org:{rel.label}"].name if rel.label else "self-released",
             "promotion": rel.promo_tier, "label_priority": _words(rel.priority)}
        if rel.status == "released":
            e["shipped_reported"] = int(round(rel.shipped, -2))
            e["certification"] = rel.cert or None
            if rel.label is None:
                e["units_sold"] = int(rel.sold)
            st = (s_stats.get(rel.tracks[0]) if rel.kind == "single" else a_stats.get(rel.id)) or {}
            e["main_chart"] = {"peak": st.get("peak"), "weeks": st.get("weeks"), "current": st.get("last")}
            if rel.kind == "single":
                i = T.index.get(rel.tracks[0])
                if i is not None:
                    e["radio"] = {rt.formats[f]["name"]: ["-", "light", "medium", "heavy", "power"][int(t)]
                                  for f, t in zip(rt.format_ids, T.view("radio_tier")[i]) if t}
                    e["video"] = {rt.channels[c]["name"]: ["-", "light", "medium", "heavy"][int(t)]
                                  for c, t in zip(rt.channel_ids, T.view("video_tier")[i]) if t}
        releases.append(e)

    # world ------------------------------------------------------------------------------
    charts = {}
    for cid in rt.chart_ids:
        st = world.charts.get(cid)
        if not st or not st.get("last_run"):
            continue
        run = st["last_run"]
        n = 20 if st.get("main") else 10
        top = [{"rank": e["rank"], "last": e["last"], "artist": e["artist"], "title": e["title"],
                "weeks": e["weeks"], "peak": e["peak"]} for e in run["top"][:n]]
        mine = [{"rank": e["rank"], "last": e["last"], "title": e["title"], "weeks": e["weeks"], "peak": e["peak"]}
                for e in run["top"] if e["act"] == act.id]
        full = store.chart_run(cid, run["week_end"]) if store else None
        if full:
            mine = [{"rank": e["rank"], "last": e["last"], "title": e["title"], "weeks": e["weeks"], "peak": e["peak"]}
                    for e in full["entries"] if e["act"] == act.id]
        charts[cid] = {"name": run["name"], "chart_dated": run["issue_date"], "tracking_week_ending": run["week_end"],
                       "method": run["methodology"], "top": top, "your_entries": mine}
    recent = [n for n in world.news if n["date"] >= since]
    own = [n for n in recent if act.id in n["entities"] or n["kind"] == "team"]
    rest = sorted([n for n in recent if n not in own], key=lambda n: (-n["importance"], n["date"]))
    news = sorted(own[-30:] + rest[: world.config["narrator.max_news_items"]], key=lambda n: n["date"])
    upcoming = []
    for rel in sorted(world.releases.values(), key=lambda r: r.date):
        if rel.status == "planned" and rel.act != act.id and rel.date <= (world.date + dt.timedelta(days=28)).isoformat():
            a = world.acts[rel.act]
            f, _ = _fame(world, a, m)
            if f > 0.2:
                upcoming.append({"date": rel.date, "artist": a.name, "title": rel.title, "kind": rel.kind,
                                 "note": "announced"})

    # people -------------------------------------------------------------------------------
    people = []
    rels = [(k.split("|")[1], v) for k, v in world.relations.items() if k.startswith(pid + "|")]
    seen = set()
    for other, r in sorted(rels, key=lambda x: -abs(x[1]["affinity"]) - 0.1 * len(x[1]["history"])):
        o = world.people.get(other)
        if o is None or other in seen:
            continue
        seen.add(other)
        back = world.relations.get(f"{other}|{pid}", {})
        people.append({"person_id": other, "name": o.name, "roles": o.roles,
                       "works_for": world.orgs[o.employer].name if o.employer in world.orgs else None,
                       "real_person": o.historical, "traits": _person_traits(o),
                       "your_feeling": _aff(r["affinity"]), "their_feeling_toward_you": _aff(back.get("affinity", 0)),
                       "their_trust": _words(back.get("trust", 0.3)),
                       "their_recent_memories_for_characterisation": [x["gist"] for x in o.memories[-4:]],
                       "notes": o.notes})
    if label:
        for role in ("head", "anr"):
            q = label.people.get(role)
            if q and q not in seen and q in world.people:
                o = world.people[q]
                people.append({"person_id": q, "name": o.name, "roles": o.roles, "works_for": label.name,
                               "real_person": o.historical, "traits": _person_traits(o),
                               "your_feeling": "neutral", "their_feeling_toward_you": "neutral",
                               "notes": o.notes})

    # decisions ---------------------------------------------------------------------------------
    offers = []
    for o in sorted(world.offers.values(), key=lambda o: o.id):
        if o.target != act.id or o.status != "open":
            continue
        src = world.orgs.get(o.source) or world.people.get(o.source)
        terms = {k: v for k, v in o.terms.items() if k != "impression"}
        entry = {"offer_id": o.id, "kind": o.kind, "from": src.name if src else o.source, "terms": terms,
                 "expires": o.expires}
        if o.kind == "song_pitch":
            entry["your_impression_0_1"] = o.terms.get("impression")
        offers.append(entry)
    producers = []
    for q in sorted(world.people.values(), key=lambda q: (-q.skills.get("production", 0), q.id)):
        if "producer" not in q.roles or q.employer:
            continue
        known = f"{pid}|{q.id}" in world.relations
        producers.append({"person_id": q.id, "name": q.name, "usual_fee": q.fee, "real_person": q.historical,
                          "reputation": _words(q.skills.get("production", 0.5)),
                          "styles": sorted(q.style_skill, key=lambda g: -q.style_skill[g])[:3], "you_know_them": known})
    budget = max(5000.0, 2 * world.ledger.balance(pid)) if not act.label else 1e9
    known = [x for x in producers if x["you_know_them"]]
    affordable = [x for x in producers if not x["you_know_them"] and x["usual_fee"] <= budget][:8]
    famous = [x for x in producers if not x["you_know_them"] and x not in affordable][:8]
    producers = known + affordable + famous
    if label and label.people.get("house_producer"):
        hp = world.people[label.people["house_producer"]]
        producers.insert(0, {"person_id": hp.id, "name": hp.name, "usual_fee": hp.fee, "real_person": False,
                             "reputation": _words(hp.skills.get("production", 0.5)), "styles": list(hp.style_skill)[:3],
                             "you_know_them": True, "note": f"staff producer at {label.name}"})

    pending = [x for x in world.pending if any(o["offer_id"] == x.get("id") for o in offers)]
    genres = [g for g in rt.genre_ids if rt.genre_available(g, world.date)]
    from . import briefing
    from ..player.delegation import advice
    world.flags["advice"] = advice(world)
    last_brief = world.flags.get("last_briefing")
    with_brief = last_brief is None or (world.date - dates.parse(last_brief)).days >= 91
    if with_brief:
        world.flags["last_briefing"] = today
    packet = {
        "packet_version": PACKET_VERSION, "pass_id": pass_id, "campaign": campaign_id,
        "scenario": world.scenario.get("title"), "date": today, "covers": {"from": since, "to": today},
        "protagonist": protagonist, "finances": finances, "calendar": calendar,
        "songbook": songbook, "recordings": recordings, "releases": releases,
        "pacing": briefing.pacing(world, since, world.interrupts) if world.pass_no > 1 else {
            "days_covered": 0, "stopped_because": ["the campaign begins"],
            "guidance": briefing.pacing(world, since, [])["guidance"]},
        "team": briefing.team(world, since),
        "industry_landscape": briefing.landscape(world, m) if with_brief else None,
        "charts": charts, "news": [{k: n[k] for k in ("date", "text", "kind", "tag")} for n in news],
        "upcoming_releases_announced": upcoming[:10],
        "people": people[:14],
        "canon_facts": world.facts[-15:],
        "open_offers": offers, "pending_decisions": pending,
        "producers_for_hire": producers,
        "genres_available": genres,
        "commands": {k: v for k, v in cmds.SCHEMA.items()},
        "proposal_types": props.SCHEMA,
        "constraints": [
            "Never state a number (sales, money, chart position, airplay) that is not in this packet.",
            "Never decide outcomes: offers, bookings, signings, reviews and chart results come from the engine.",
            "Anything with consequences (a new named industry person, an opportunity, a relationship change, "
            "a scandal, a purchase) must be returned as a proposal or decision, not narrated as done.",
            "Real people may appear and speak in character, but do not invent serious scandals, illnesses or "
            "traumatic events for them.",
            "The protagonist does not know other people's private memories; those are for characterisation only.",
        ],
    }
    return packet


# ------------------------------------------------------------------ markdown
def to_markdown(pk: dict) -> str:
    P = pk["protagonist"]
    out = []
    w = out.append
    w(f"# {pk['scenario']} — pass {pk['pass_id']}")
    if pk["pacing"]["days_covered"]:
        w(f"**In-world date:** {pk['date']} (this pass covers {pk['covers']['from']} to {pk['covers']['to']})\n")
    else:
        w(f"**In-world date:** {pk['date']}: the story begins (news below covers the two weeks before)\n")
    w("> You are the narrator of a music-industry career simulation. The engine below is authoritative: use its "
      "facts, numbers and people; write immersive scenes, dialogue and atmosphere around them; and return the "
      "player's decisions plus any proposed developments in the JSON format at the end. The full rules are in "
      "`docs/narrator_contract.md` (paste once per conversation).\n")
    w("## The protagonist")
    w(f"- **{P['name']}** ({P['age']}), performing as **{P['act_name']}** — {P['career_stage']}, based in {P['city']}.")
    w(f"- Background: {P['background']}")
    w(f"- Genres: {', '.join(P['genres'])}; persona: {', '.join(P['persona']) or '—'}")
    w("- Abilities as your team rates them (0–100): " +
      ", ".join(f"{k} {v}" for k, v in P["abilities_as_your_team_sees_them"].items()))
    w("- Wellbeing: " + ", ".join(f"{k} {v}" for k, v in P["wellbeing"].items()))
    w(f"- Public recognition: {P['public_recognition_pct']}% of the music-buying public; local live buzz: "
      f"{P['local_live_buzz']}.")
    w(f"- Industry view: singles track record {P['industry_view']['singles_track_record']}, momentum "
      f"{P['industry_view']['momentum']}, critical standing {P['industry_view']['critical_standing']}.")
    if P["contract"]:
        c = P["contract"]
        t = c["terms"]
        w(f"- Signed to **{c['label']}** since {c['since']}: advance ${t.get('advance', 0):,.0f}, royalty "
          f"{t.get('royalty_rate', 0):.0%}, recording fund ${t.get('recording_budget_per_album', 0):,.0f}/album. "
          f"Royalty account (estimate): ${c['royalty_account_estimate']:,.0f} ({c['recoupment_note']}).")
    else:
        w("- **Unsigned.**")
    pc = pk["pacing"]
    w(f"\n## Pacing\nThis pass covers {pc['days_covered']} days. The clock stopped because: "
      + "; ".join(pc["stopped_because"]) + f". {pc['guidance']}")
    tm = pk["team"]
    w("\n## Your team and standing orders")
    w("- Manager: " + (f"**{tm['manager']['name']}** `{tm['manager']['person_id']}` ({tm['manager']['commission']:.0%} "
                      f"commission since {tm['manager']['since']})" if tm["manager"] else "none"))
    w("- Standing orders: " + ", ".join(f"{k}={v}" for k, v in tm["standing_orders"].items()))
    w("- Always comes back to the player: " + "; ".join(tm["always_comes_back_to_you"]))
    for x in tm["handled_for_you_this_pass"]:
        w(f"- Handled for you: {x}")
    for x in tm["what_people_are_telling_you"]:
        w(f"- What people are telling you: {x}")
    F = pk["finances"]
    w(f"\n## Money\nCash: **${F['cash']:,.2f}** · this period: +${F['period_income']:,.0f} / −${F['period_spending']:,.0f}"
      f" · lifestyle: {F['lifestyle']}" + (f" · day job: {F['day_job']['title']} "
                                          f"({'active' if F['day_job'].get('active') else 'quit'})" if F['day_job'] else ""))
    if pk["calendar"]:
        w("\n## Calendar")
        for c in pk["calendar"]:
            w(f"- {c['date']}{' → ' + c['until'] if c.get('until') and c['until'] != c['date'] else ''}: {c['what']}")
    w("\n## What happened (news and events the protagonist knows about)")
    for n in pk["news"] or [{"date": pk["date"], "text": "A quiet stretch.", "tag": "official"}]:
        w(f"- {n['date']} [{n['tag']}] {n['text']}")
    if pk["recordings"] or pk["songbook"]:
        w("\n## Music")
        for s in pk["songbook"]:
            imp = s.get("your_impression")
            w(f"- Songbook: \"{s['title']}\" ({s['genre']}, by {', '.join(s['writers']) or 'you'}) "
              f"`{s['composition_id']}`" + (f" — your read: hook {round(imp['hook']*100)}, melody "
                                            f"{round(imp['melody']*100)}" if imp else ""))
        for r in pk["recordings"]:
            line = f"- Recording \"{r['title']}\" `{r['recording_id']}` ({r['genre']}, prod. {', '.join(r['producers'])}): {r['status']}"
            if r.get("impression"):
                line += f" — your team hears: {'; '.join(r['impression'])}"
            w(line)
    if pk["releases"]:
        w("\n## Releases")
        for r in pk["releases"]:
            line = f"- \"{r['title']}\" ({r['kind']}, {r['label']}, {r['date']}): {r['status']}"
            if r["status"] == "released":
                mc = r.get("main_chart", {})
                line += (f"; shipped ~{r['shipped_reported']:,}" + (f"; certified {r['certification']}" if r.get("certification") else "")
                         + (f"; sold {r['units_sold']:,}" if r.get("units_sold") is not None else "")
                         + (f"; main chart peak #{mc['peak']} ({mc['weeks']} wk, now {'#' + str(mc['current']) if mc['current'] else 'off'})" if mc.get("peak") else "; not on the main chart"))
                if r.get("radio"):
                    line += "; radio: " + ", ".join(f"{k} {v}" for k, v in r["radio"].items())
                if r.get("video"):
                    line += "; video: " + ", ".join(f"{k} {v}" for k, v in r["video"].items())
            w(line)
    w("\n## Charts")
    for cid, c in pk["charts"].items():
        w(f"\n**{c['name']}** — chart dated {c['chart_dated']} (method: {c['method']})")
        for e in c["top"]:
            mv = "NEW" if e["last"] is None else ("=" if e["last"] == e["rank"] else
                                                  ("▲" if e["last"] > e["rank"] else "▼") + str(e["last"]))
            w(f"{e['rank']:>3}. {e['artist']} — {e['title']} ({mv}, {e['weeks']} wk)")
        if c["your_entries"]:
            for e in c["your_entries"]:
                w(f"  ★ You: #{e['rank']} \"{e['title']}\" ({e['weeks']} wk, peak #{e['peak']})")
    L = pk.get("industry_landscape")
    if L:
        w(f"\n## The industry right now (engine briefing as of {L['as_of']})")
        w(f"_{L['evidence_note']}_\n")
        w("**Biggest real artists:**")
        for a in L["biggest_real_artists_right_now"]:
            bits = [f"{a['label']}", "/".join(a["genres"]), f"recognised by {a['public_recognition_pct']}%",
                    f"momentum {a['momentum']}"]
            if a.get("current_single"):
                cs = a["current_single"]
                pos = ", ".join(f"#{v} {k}" for k, v in cs["charts"].items())
                bits.append(f"single \"{cs['title']}\"" + (f" ({pos})" if pos else ""))
            if a.get("current_album"):
                ca = a["current_album"]
                pos = ", ".join(f"#{v} {k}" for k, v in ca["charts"].items())
                bits.append(f"album \"{ca['title']}\"" + (f" ({pos})" if pos else "")
                            + (f" [{ca['certified']}]" if ca.get("certified") else ""))
            if a.get("announced"):
                bits.append(f"next: {a['announced']['kind']} \"{a['announced']['title']}\" on {a['announced']['date']}")
            w(f"- **{a['name']}** — " + "; ".join(bits))
        w("\n**On the rise:** " + "; ".join(f"{a['name']} ({'real' if a['real'] else 'fictional'}, {a['label']}, "
                                             f"{'/'.join(a['genres'])})" for a in L["acts_on_the_rise"]))
        w("\n**Record companies:**")
        for grp, labs in L["record_companies"].items():
            w(f"- *{grp}*: " + "; ".join(
                f"{x['label']}{' (fictional)' if x['fictional'] else ''} — {x['size']}, strong in {', '.join(x['strengths'])}"
                + (f", run by {x['head']}" if x["head"] else "")
                + (f", roster incl. {', '.join(x['notable_artists'])}" if x["notable_artists"] else "") for x in labs))
        w("\n**Audiences:**")
        for a in L["audiences"]:
            w(f"- {a['segment']}: {a['people_millions']}M people, ~${a['music_spend_per_person_per_year']}/yr on music; "
              f"loves {', '.join(a['favourite_styles'])}; listens to {', '.join(a['listens_to']) or 'little radio'}; "
              f"singles buying {a['buys_singles']}, album buying {a['buys_albums']}")
        w("\n**Media gatekeepers:** radio formats — " + "; ".join(
            f"{r['format']} (playlist ~{r['current_playlist_size']})" for r in L["radio_formats"])
          + ". Video channels — " + ", ".join(L["music_video_channels"]) + ". TV music bookings — "
          + "; ".join(f"{t['program']} ({t['performance_slots_per_week']}/wk, {t['hard_to_book']} to book)"
                      for t in L["tv_music_bookings"]) + ".")
        w("\n**Charts in force:** " + "; ".join(f"{c['chart']} [{c['method']}]" for c in L["charts_in_force"]))
        mk = L["market"]
        w(f"\n**Market:** albums ~${mk['typical_album_price']}, singles ~${mk['typical_single_price']} (singles market "
          f"{mk['singles_market']}); new releases on {mk['release_day']}s; songwriter mechanical rate "
          f"${mk['songwriter_mechanical_rate_per_song']} per song per copy; certification by {mk['certification']}.")
    if pk["upcoming_releases_announced"]:
        w("\n## Announced releases from notable artists")
        for u in pk["upcoming_releases_announced"]:
            w(f"- {u['date']}: {u['artist']} — \"{u['title']}\" ({u['kind']})")
    if pk["people"]:
        w("\n## People in the protagonist's life (for characterisation)")
        for q in pk["people"]:
            w(f"- **{q['name']}** `{q['person_id']}` — {', '.join(q['roles'])}"
              + (f" at {q['works_for']}" if q.get("works_for") else "") + (" (real person)" if q["real_person"] else "")
              + f"; traits: {', '.join(q['traits']) or '—'}; toward you: {q.get('their_feeling_toward_you')}"
              + (f"; recent: {' / '.join(q['their_recent_memories_for_characterisation'])}"
                 if q.get("their_recent_memories_for_characterisation") else ""))
    if pk["canon_facts"]:
        w("\n## Established canon")
        for f in pk["canon_facts"]:
            w(f"- {f['date']}: {f['text']}")
    w("\n## Decisions available")
    if pk["open_offers"]:
        for o in pk["open_offers"]:
            w(f"- OFFER `{o['offer_id']}` ({o['kind']}) from {o['from']}, expires {o['expires']}: "
              + json.dumps(o["terms"]))
    w("- Producers you could approach: " + "; ".join(
        f"{x['name']} `{x['person_id']}` ({x['reputation']}, usual fee ${x['usual_fee']:,.0f}"
        f"{', ' + x['note'] if x.get('note') else ''})" for x in pk["producers_for_hire"][:12]))
    w("- Commands: " + "; ".join(f"`{k}` — {v['desc']}" for k, v in pk["commands"].items()))
    w("\n## Rules for the narrator")
    for c in pk["constraints"]:
        w(f"- {c}")
    w("\n## Return format (paste back into the engine with `musicsim play`)")
    w("Return exactly one fenced ```json block with this shape; decisions are the player's choices (ask the player "
      "before committing to contracts, releases or major creative choices); proposals are developments you suggest "
      "that the engine will accept or reject:")
    example = {"pass_id": pk["pass_id"], "decisions": [
        {"command": "record_song", "args": {"song": "write_own", "title": "Example Title", "producer": "person:…",
                                            "genre": pk["genres_available"][0], "studio_weeks": 3,
                                            "budget": 4000}}],
        "proposals": [{"type": "relationship_moment", "with": "person:…", "nature": "…", "valence": 1},
                      {"type": "introduce_person", "name": "…", "role": "manager", "context": "…",
                       "traits": ["ambitious"]}],
        "advance": "next"}
    w("```json\n" + json.dumps(example, indent=2) + "\n```")
    w("`advance` (optional): \"next\" runs until something needs the player (at most ~3 months); or a duration "
      "such as 3d, 2w, 2m. Leave it out if the player still has a decision to make.")
    w("\n## Authoritative engine data (JSON)")
    w("_Ids, numbers and state the engine will hold you to. News, charts and the industry briefing above are "
      "authoritative as written; the complete packet is also saved as JSON next to this file._")
    keep = ("pass_id", "date", "protagonist", "finances", "calendar", "team", "songbook", "recordings", "releases",
            "people", "canon_facts", "open_offers", "producers_for_hire", "genres_available")
    w("```json\n" + json.dumps({k: pk[k] for k in keep}, indent=1, default=str) + "\n```")
    return "\n".join(out) + "\n"

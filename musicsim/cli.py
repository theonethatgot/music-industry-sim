"""Command-line front end.

  python -m musicsim new <dir> [--scenario us_1988_aspiring] [--seed 7] [--character <name|path>]
  python -m musicsim packet <dir>                 # print path of the current narrator packet
  python -m musicsim play <dir> <file|->          # submit decisions/proposals (JSON or a narrator reply)
  python -m musicsim check <dir> <file|->         # validate a submission without applying it
  python -m musicsim advance <dir> [next|3d|2w|2m] # move time (stops early when something needs you)
  python -m musicsim briefing <dir>               # write an industry briefing (JSON) for the current date
  python -m musicsim status <dir>
  python -m musicsim charts <dir> [chart_id] [--n 40]
  python -m musicsim why <dir> <song|release id>  # provenance: weekly exposure, decisions, draws
  python -m musicsim replay <dir>                 # verify determinism from the command log
  python -m musicsim scenarios
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .campaign_io import Campaign, parse_submission_text, validate_submission
from .core.config import DATA_DIR, load_yaml


def _read(src: str) -> str:
    return sys.stdin.read() if src == "-" else Path(src).read_text(encoding="utf-8")


def cmd_new(a):
    c = Campaign.create(a.dir, a.scenario, a.seed, a.character)
    print(f"Created campaign at {a.dir} ({c.world.scenario.get('title')}); world date {c.world.date}.")
    print(f"Narrator packet: {c.packet_path()}")
    print("Next: paste docs/narrator_contract.md, then this packet, into ChatGPT. Save its reply and run:\n"
          f"  python -m musicsim play {a.dir} reply.txt")
    c.close()


def cmd_packet(a):
    c = Campaign.open(a.dir)
    print(c.packet_path())
    c.close()


def cmd_check(a):
    c = Campaign.open(a.dir)
    try:
        payload = parse_submission_text(_read(a.file))
    except (ValueError, json.JSONDecodeError) as e:
        print(f"invalid: {e}")
        return 2
    errs = validate_submission(c.world, payload, c.last_packet())
    print("valid" if not errs else "invalid:\n  " + "\n  ".join(errs))
    c.close()
    return 0 if not errs else 2


def cmd_play(a):
    c = Campaign.open(a.dir)
    try:
        payload = parse_submission_text(_read(a.file))
    except (ValueError, json.JSONDecodeError) as e:
        print(f"invalid submission: {e}")
        return 2
    rep = c.submit(payload)
    if rep.get("status") == "invalid":
        print("Submission rejected:\n  " + "\n  ".join(rep["errors"]))
        return 2
    for d in rep["decisions"]:
        print(f"[decision] {d['command']}: {d['status']} — {d.get('summary') or d.get('reason') or d.get('errors')}")
    for p in rep["proposals"]:
        print(f"[proposal] {p['type']}: {p['status']} — {p.get('summary') or p.get('reason') or p.get('errors')}")
    if rep.get("advance"):
        ad = rep["advance"]
        print(f"[time] {ad['from']} → {ad['to']} ({ad['days']} days)"
              + (f"; stopped for: {', '.join(i['reason'] for i in ad['interrupts'])}" if ad["interrupts"] else ""))
    print(f"Next narrator packet: {rep['packet']}")
    c.close()
    return 0


def cmd_advance(a):
    c = Campaign.open(a.dir)
    res = c.advance(a.duration)
    print(f"{res['from']} → {res['to']} ({res['days']} days)"
          + (f"; stopped for: {', '.join(i['reason'] for i in res['interrupts'])}" if res["interrupts"] else ""))
    print(f"Next narrator packet: {res['packet']}")
    c.close()


def cmd_status(a):
    c = Campaign.open(a.dir)
    pk = c.last_packet()
    P = pk["protagonist"]
    print(f"{pk['date']}  {P['name']} ({P['career_stage']}) — label: {P['label'] or 'unsigned'} — "
          f"cash ${pk['finances']['cash']:,.0f} — recognition {P['public_recognition_pct']}%")
    for r in pk["releases"]:
        mc = r.get("main_chart") or {}
        print(f"  {r['kind']:6s} {r['title'][:32]:32s} {r['status']:9s} shipped {r.get('shipped_reported', 0):>9,} "
              f"peak {mc.get('peak') or '-'}")
    for o in pk["open_offers"]:
        print(f"  OFFER {o['offer_id']} {o['kind']} from {o['from']} (expires {o['expires']})")
    c.close()


def cmd_charts(a):
    c = Campaign.open(a.dir)
    rt = c.world.markets[c.world.player["market"]]
    cid = a.chart or rt.chart_ids[0]
    run = c.store.chart_run(cid)
    if not run:
        print("no chart yet")
        return 1
    print(f"{run['name']} — chart dated {run['issue_date']} (tracking week ending {run['week_end']}; {run['methodology']})")
    for e in run["entries"][: a.n]:
        mv = "NEW" if e["last"] is None else e["last"]
        star = " ★" if e["act"] == c.world.player["act"] else ""
        print(f"{e['rank']:>3} ({mv!s:>3}) {e['artist'][:28]:28s} {e['title'][:34]:34s} wk {e['weeks']:>2} pk {e['peak']:>3}"
              f"  {json.dumps(e['measured'])}{star}")
    c.close()


def cmd_why(a):
    c = Campaign.open(a.dir)
    w = c.world
    sid = a.subject
    if sid in w.releases and w.releases[sid].kind == "single":
        sid = w.releases[sid].tracks[0]
    rec = w.recordings.get(sid)
    if rec:
        comp = w.compositions[rec.composition]
        print(f"\"{rec.title}\" by {w.acts[rec.act].name} ({rec.genre})")
        print(f"  writers: {[w.people[x['person']].name for x in comp.writers if x['person'] in w.people]}; "
              f"producers: {[w.people[x].name for x in rec.producers if x in w.people]}")
        print(f"  composition (true): {comp.attrs}")
        print(f"  recording (true):   {rec.attrs}")
        print(f"  reception shock: {rec.reception}  history evidence: {rec.hist_evidence}")
        for row in c.store.song_weeks(sid):
            imp = {k: f"{v / 1e6:.1f}M" for k, v in row["impressions"].items() if v}
            print(f"  week to {row['week_end']}: aware {row['aware_pop'] / 1e6:.1f}M engaged {row['engaged_pop'] / 1e6:.2f}M "
                  f"radio {row['radio_tiers']} video {row['video_tiers']} impressions {imp}")
    for ev in reversed(c.store.events_for(a.subject, limit=40)):
        print(f"  [{ev['date']}] {ev['system']}.{ev['type']} {json.dumps(ev['data'])[:160]}"
              + (f" draws={ev['draws']}" if ev["draws"] else ""))
    c.close()


def cmd_briefing(a):
    from .narrator.briefing import landscape
    c = Campaign.open(a.dir)
    data = landscape(c.world, c.world.player["market"])
    out = Path(a.dir) / "packets" / f"briefing_{c.world.date.isoformat()}.json"
    out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(out)
    c.close()


def cmd_migrate(a):
    res = Campaign.migrate(a.dir, a.note or "")
    print(json.dumps(res, indent=1))


def cmd_replay(a):
    c = Campaign.open(a.dir)
    res = c.replay()
    print(json.dumps(res, indent=1))
    c.close()
    return 0 if res["ok"] else 1


def cmd_scenarios(a):
    for p in sorted((DATA_DIR / "scenarios").glob("*.yaml")):
        s = load_yaml(p)
        print(f"{s['id']:28s} {s['start_date']}  {s.get('title', '')}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="musicsim", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new"); p.add_argument("dir"); p.add_argument("--scenario", default="us_1988_aspiring")
    p.add_argument("--seed", type=int, default=1); p.add_argument("--character"); p.set_defaults(fn=cmd_new)
    p = sp.add_parser("packet"); p.add_argument("dir"); p.set_defaults(fn=cmd_packet)
    p = sp.add_parser("play"); p.add_argument("dir"); p.add_argument("file"); p.set_defaults(fn=cmd_play)
    p = sp.add_parser("check"); p.add_argument("dir"); p.add_argument("file"); p.set_defaults(fn=cmd_check)
    p = sp.add_parser("advance"); p.add_argument("dir"); p.add_argument("duration", nargs="?"); p.set_defaults(fn=cmd_advance)
    p = sp.add_parser("status"); p.add_argument("dir"); p.set_defaults(fn=cmd_status)
    p = sp.add_parser("charts"); p.add_argument("dir"); p.add_argument("chart", nargs="?")
    p.add_argument("--n", type=int, default=40); p.set_defaults(fn=cmd_charts)
    p = sp.add_parser("why"); p.add_argument("dir"); p.add_argument("subject"); p.set_defaults(fn=cmd_why)
    p = sp.add_parser("replay"); p.add_argument("dir"); p.set_defaults(fn=cmd_replay)
    p = sp.add_parser("briefing"); p.add_argument("dir"); p.set_defaults(fn=cmd_briefing)
    p = sp.add_parser("migrate"); p.add_argument("dir"); p.add_argument("--note"); p.set_defaults(fn=cmd_migrate)
    p = sp.add_parser("scenarios"); p.set_defaults(fn=cmd_scenarios)
    a = ap.parse_args(argv)
    return a.fn(a) or 0

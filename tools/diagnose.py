"""Quick calibration diagnostics: run a scenario headless and print chart-level statistics.

usage: python tools/diagnose.py [scenario] [seed] [weeks_after_start]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from musicsim.campaign import build_world, load_scenario  # noqa: E402
from musicsim.sim import advance  # noqa: E402


def main():
    scen = sys.argv[1] if len(sys.argv) > 1 else "us_1988_aspiring"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    weeks = int(sys.argv[3]) if len(sys.argv) > 3 else 26
    t = time.time()
    sc = load_scenario(scen)
    w = build_world(sc, seed, None)
    advance(w, weeks * 7, stop_on_interrupt=False)
    print(f"{scen} seed={seed} -> {w.date}  ({time.time() - t:.1f}s)  songs={w.tables['US'].n} albums={w.albums['US'].n}")
    runs = {}
    for r in w.chart_log:
        runs.setdefault(r["chart"], []).append(r)
    for cid in ["hot100", "top_albums", "black_singles"]:
        rs = runs.get(cid, [])[-26:]
        if not rs:
            continue
        print(f"\n== {rs[-1]['name']} ({rs[-1]['methodology']}), last {len(rs)} weeks")
        for rank in (1, 5, 10, 40, 100, 200):
            vals = [r["entries"][rank - 1]["measured"].get("sales", 0) for r in rs if len(r["entries"]) >= rank]
            if vals:
                print(f"  rank {rank:3d}: measured sales median {np.median(vals):10,.0f}  (max {max(vals):10,.0f})")
        debuts = [e["rank"] for r in rs for e in r["entries"] if e["weeks"] == 1]
        print(f"  debuts/week {len(debuts) / len(rs):.1f}; median debut rank {np.median(debuts) if debuts else 0:.0f}")
        ones = [r["entries"][0]["title"] + " - " + r["entries"][0]["artist"] for r in rs]
        print("  #1s:", sorted(set(ones), key=ones.index))
        last = rs[-1]["entries"][:10]
        for e in last:
            print(f"   {e['rank']:3d} ({str(e['last']):>4s}) {e['artist'][:28]:28s} {e['title'][:30]:30s} wk{e['weeks']:2d} {e['measured']}")
    print("\nreal-act share of Hot 100 entries (last run):",
          round(sum(1 for e in runs['hot100'][-1]['entries'] if w.acts[e['act']].historical) / 100, 2))


if __name__ == "__main__":
    main()

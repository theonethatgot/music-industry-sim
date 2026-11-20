"""A&R review calibration.

Part A: Monte Carlo of the review over synthetic masters (label size, genre fit, career stage,
        writer/producer skill, budget): approval rates, and whether hooky-but-rough records are
        systematically undervalued.
Part B: whole-world runs over several seeds in study mode (every generated single is released at
        standard promotion whatever the verdict): does the label's verdict predict outcomes?

usage: python tools/label_calibration.py [seeds=4] [weeks=40] [samples=3000]
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from musicsim.campaign import build_world, load_scenario  # noqa: E402
from musicsim.core import rng  # noqa: E402
from musicsim.entities import Act, Person  # noqa: E402
from musicsim.sim import advance  # noqa: E402
from musicsim.systems.charts import main_chart  # noqa: E402
from musicsim.systems.creative import produce_recording, write_composition  # noqa: E402
from musicsim.systems.development import review_master  # noqa: E402


def part_a(samples: int) -> dict:
    sc = copy.deepcopy(load_scenario("us_1988_aspiring"))
    sc["burn_in_weeks"] = 0
    sc["world"]["fictional_npc_acts"] = 0
    w = build_world(sc, 5, None)
    rt = w.markets["US"]
    labels = [o for o in w.orgs.values() if o.kind == "record_company"]
    genres = [g for g in rt.genre_ids if rt.genre_available(g, w.date)]
    rows = []
    for k in range(samples):
        u = lambda *p: rng.uniform(7, "calA", k, *p)
        org = labels[int(u("label") * len(labels))]
        g = genres[int(u("genre") * len(genres))]
        power = [0.05, 0.3, 0.6][int(u("stage") * 3)]
        wp = Person(id=f"person:cw{k}", name="w", roles=["songwriter"],
                    skills={"songwriting": float(np.clip(0.55 + 0.13 * rng.normal(7, "calA", k, "ws"), 0.2, 0.95))},
                    style_skill={g: 0.8})
        pp = Person(id=f"person:cp{k}", name="p", roles=["producer"],
                    skills={"production": float(np.clip(0.62 + 0.12 * rng.normal(7, "calA", k, "ps"), 0.25, 0.97))},
                    style_skill={g: 0.8})
        sp = Person(id=f"person:cs{k}", name="s", roles=["performer"],
                    skills={"vocal": float(np.clip(0.65 + 0.12 * rng.normal(7, "calA", k, "vs"), 0.3, 0.98)),
                            "performance": 0.6}, style_skill={g: 0.8})
        for p in (wp, pp, sp):
            w.people[p.id] = p
        act = Act(id=f"act:c{k}", name="c", members=[{"person": sp.id, "role": "lead"}], home_market="US", genres=[g],
                  label=org.id.split(":")[1], singles_power_o=power)
        w.acts[act.id] = act
        budget = [5000, 15000, 40000][int(u("budget") * 3)]
        comp = write_composition(w, "t", [wp.id], g, key=f"calA{k}")
        rec = produce_recording(w, comp, act.id, [pp.id], g, budget=budget, weeks=3, key=f"calA{k}")
        rv = review_master(w, org, act, rec, "calA")
        rows.append({"size": org.params["size"], "fit": org.strategy["focus"].get(g, 0.2), "power": power,
                     "budget": budget, "approve": rv["approve"], "score": rv["score"], "craft": rv["craft"],
                     "commercial": rv["commercial"], "hook": comp.attrs["hook"], "true_craft": None})
        w.events.drain()
    a = np.array([r["approve"] for r in rows])
    hook = np.array([r["hook"] for r in rows])
    craft = np.array([r["craft"] for r in rows])
    out = {"n": len(rows), "approval_rate": round(a.mean(), 3)}
    for name, key, bins in (("by_label_size", "size", [0, 0.45, 0.95, 9]), ("by_genre_fit", "fit", [0, 0.45, 0.85, 9]),
                            ("by_track_record", "power", [0, 0.1, 0.4, 9]), ("by_budget", "budget", [0, 10000, 30000, 1e9])):
        v = np.array([r[key] for r in rows])
        out[name] = {f"{lo:g}-{hi:g}": round(float(a[(v >= lo) & (v < hi)].mean()), 3)
                     for lo, hi in zip(bins, bins[1:]) if ((v >= lo) & (v < hi)).any()}
    hq = np.quantile(hook, [1 / 3, 2 / 3])
    cq = np.quantile(craft, [1 / 3, 2 / 3])
    grid = {}
    for hn, hm in (("hook_low", hook < hq[0]), ("hook_high", hook >= hq[1])):
        for cn, cm in (("craft_low", craft < cq[0]), ("craft_high", craft >= cq[1])):
            m = hm & cm
            grid[f"{hn}/{cn}"] = {"n": int(m.sum()), "approval": round(float(a[m].mean()), 3) if m.any() else None}
    out["hook_x_craft"] = grid
    return out


def part_b(seeds: int, weeks: int) -> dict:
    recs = []
    for seed in range(1, seeds + 1):
        sc = copy.deepcopy(load_scenario("us_1988_aspiring"))
        sc["config_overrides"] = {"development": {"study_release_all": True}}
        w = build_world(sc, seed, None)
        start = w.date.isoformat()
        advance(w, weeks * 7, stop_on_interrupt=False)
        stats = main_chart(w, "US", "song")["stats"]
        for rel in w.releases.values():
            if rel.kind != "single" or not rel.review or rel.date < start or rel.status != "released":
                continue
            if (w.date - __import__("datetime").date.fromisoformat(rel.date)).days < 120:
                continue
            peak = stats.get(rel.tracks[0], {}).get("peak")
            recs.append({"seed": seed, "approve": rel.review["approve"], "score": rel.review["score"],
                         "margin": rel.review["margin"], "craft": rel.review["craft"],
                         "commercial": rel.review["commercial"], "sold": rel.sold, "peak": peak})
    a = np.array([r["approve"] for r in recs])
    sold = np.array([r["sold"] for r in recs]) + 1
    peak = np.array([r["peak"] or 999 for r in recs])
    lg = np.log(sold)

    def grp(m):
        return {"n": int(m.sum()), "median_units": int(np.median(sold[m])) if m.any() else None,
                "top40_rate": round(float((peak[m] <= 40).mean()), 3) if m.any() else None,
                "top10_rate": round(float((peak[m] <= 10).mean()), 3) if m.any() else None,
                "charted_rate": round(float((peak[m] <= 100).mean()), 3) if m.any() else None}
    X = np.column_stack([np.ones(len(recs)), [r["craft"] for r in recs], [r["commercial"] for r in recs]])
    coef = np.linalg.lstsq(X, lg, rcond=None)[0]
    score = np.array([r["score"] for r in recs])
    return {"singles": len(recs), "approval_rate": round(float(a.mean()), 3),
            "approved": grp(a), "vetoed_but_released_for_study": grp(~a),
            "corr_score_log_units": round(float(np.corrcoef(score, lg)[0, 1]), 3),
            "log_units_regression": {"craft": round(float(coef[1]), 2), "commercial": round(float(coef[2]), 2)},
            "vetoed_that_reached_top40": int(((~a) & (peak <= 40)).sum()),
            "approved_that_missed_hot100": int((a & (peak > 100)).sum())}


if __name__ == "__main__":
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    weeks = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    samples = int(sys.argv[3]) if len(sys.argv) > 3 else 3000
    print(json.dumps({"part_a_review_monte_carlo": part_a(samples),
                      "part_b_world_outcomes": part_b(seeds, weeks)}, indent=1))

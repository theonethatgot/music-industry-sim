"""Multi-seed first-year career-continuity checks with scripted players.

Strategies:
  engaged    - takes the best contract, records and submits singles, accepts label development proposals
  passive    - never decides anything (the world must still move; the protagonist may legitimately stall)
  overworked - day job + five club nights + lessons, with rest_when_exhausted (recovery loop)

For each run it reports gaps between passes, exhaustion streaks, rest outcomes, label behaviour and
results. The point is coherence (no frozen protagonist, no recovery no-ops), not success.

usage: python tools/career_continuity.py [engaged_seeds=10] [other_seeds=4] [weeks=52] [--json out.json]
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from musicsim.campaign import build_world, load_character, load_scenario  # noqa: E402
from musicsim.campaign_io import Campaign, advance_days, apply_submission  # noqa: E402
from musicsim.narrator import packet as packet_mod  # noqa: E402
from musicsim.sim import advance as sim_advance  # noqa: E402


class FastCampaign:
    """The same play loop as Campaign (packets, submissions, advances) without writing snapshots to disk.
    Used for throughput; persistence and replay are verified separately with the real Campaign."""

    def __init__(self, seed):
        sc = load_scenario("us_1988_aspiring")
        self.world = build_world(sc, seed, load_character(sc["protagonist"]["character"]))
        self.seq = 0
        self._pk = packet_mod.build(self.world, None, "fast", None)

    def last_packet(self):
        return self._pk

    def submit(self, payload):
        self.seq += 1
        apply_submission(self.world, payload, self.seq * 100)
        adv = sim_advance(self.world, advance_days(payload.get("advance")), stop_on_interrupt=True)
        self.world.events.drain()
        self._pk = packet_mod.build(self.world, None, "fast", self._pk["date"])
        return {"advance": adv}

    def close(self):
        pass


def engaged(pk, mem):
    d = []
    offers = pk["open_offers"]
    contracts = [o for o in offers if o["kind"] == "recording_contract"]
    if contracts and not pk["protagonist"]["label"]:
        best = max(contracts, key=lambda o: (o["terms"]["advance"], o["offer_id"]))
        return [{"command": "accept_offer", "args": {"offer_id": best["offer_id"]}}]
    props = [o for o in offers if o["kind"] == "label_proposal"]
    for action in ("release_master", "remix", "recut_vocal"):
        pick = [o for o in props if o["terms"]["action"] == action]
        if pick:
            d.append({"command": "accept_offer", "args": {"offer_id": pick[0]["offer_id"]}})
            return d
    pitches = sorted([o for o in offers if o["kind"] == "song_pitch"],
                     key=lambda o: -(o["your_impression_0_1"]["hook"] + o["your_impression_0_1"]["melody"]))
    for o in pitches[:1]:
        if o["your_impression_0_1"]["hook"] + o["your_impression_0_1"]["melody"] > 1.15:
            d.append({"command": "accept_offer", "args": {"offer_id": o["offer_id"]}})
    recs = pk["recordings"]
    busy = any(r["status"] == "in_production" for r in recs)
    planned = any(r["status"] == "planned" for r in pk["releases"])
    ready = [r for r in recs if r["status"] == "done" and not r["single_release"]
             and r["recording_id"] not in mem["tried"]]
    signed = bool(pk["protagonist"]["label"])
    if ready and not planned and (signed or len(recs) >= 1) and (signed or mem.get("self_release")):
        best = max(ready, key=lambda r: sum(r["team_rating"].values()))
        mem["tried"].add(best["recording_id"])
        d.append({"command": "release_single", "args": {"recording_id": best["recording_id"], "promo": "standard",
                                                       "video": "standard" if signed else "none"}})
    elif not busy and len([r for r in recs if r["status"] == "done" and not r["single_release"]]) < 2:
        book = pk["songbook"]
        song = book[0]["composition_id"] if book else "write_own"
        if signed:
            prods = pk["producers_for_hire"]
            prod = next((p for p in prods if p.get("note", "").startswith("staff producer")), prods[0])
            d.append({"command": "record_song", "args": {"song": song, "title": f"Song {len(recs) + 1}",
                                                         "producer": prod["person_id"], "genre": "rnb",
                                                         "studio_weeks": 3, "budget": 12000}})
        elif pk["finances"]["cash"] > 900:
            d.append({"command": "record_song", "args": {"song": song, "title": f"Demo {len(recs) + 1}",
                                                         "producer": "person:pc_contact1", "genre": "rnb",
                                                         "studio_weeks": 2, "budget": 300}})
    if not signed and len(recs) >= 2 and pk["date"] > mem["start_plus_6m"]:
        mem["self_release"] = True
    return d


def passive(pk, mem):
    return []


def overworked(pk, mem):
    """Day job + max club nights + lessons + back-to-back studio sessions."""
    d = []
    if not mem.get("set"):
        mem["set"] = True
        d.append({"command": "set_policy", "args": {"gigs_when_idle": 5, "training_when_idle": "vocal",
                                                    "rest_when_exhausted": True}})
    busy = any(r["status"] == "in_production" for r in pk["recordings"])
    if not busy and pk["finances"]["cash"] > 700:
        d.append({"command": "record_song", "args": {"song": "write_own", "title": f"Session {len(pk['recordings'])}",
                                                     "producer": "person:pc_contact1", "genre": "rnb",
                                                     "studio_weeks": 2, "budget": 200}})
    return d


def recovering(pk, mem):
    """Starts exhausted (as in the Danielle playtest) with the day job and club nights; relies on standing orders."""
    if not mem.get("set"):
        mem["set"] = True
        return [{"command": "set_policy", "args": {"gigs_when_idle": 2, "rest_when_exhausted": True}}]
    return []


STRATEGIES = {"engaged": engaged, "passive": passive, "overworked": overworked, "recovering": recovering}


def run(strategy: str, seed: int, weeks: int, tmp: Path) -> dict:
    path = tmp / f"{strategy}_{seed}" / "session"
    real = seed in (1, 1988) and strategy == "engaged" and weeks <= 30
    c = Campaign.create(path, "us_1988_aspiring", seed) if real else FastCampaign(seed)
    w = c.world
    w.events.watch = {w.player["act"], w.player["person"]}
    start = w.date
    stop = (start + dt.timedelta(weeks=weeks)).isoformat()
    mem = {"tried": set(), "start_plus_6m": (start + dt.timedelta(weeks=26)).isoformat()}
    fn = STRATEGIES[strategy]
    if strategy == "recovering":       # harness fixture: start from Danielle-like exhaustion
        wb = w.people[w.player["person"]].wellbeing
        wb["energy"], wb["stress"] = 0.08, 0.7
    gaps, signed_gaps, low_days, low_streak, streak = [], [], 0, 0, 0
    passes = 0
    signed_on = None
    while c.last_packet()["date"] < stop and passes < 200:
        pk = c.last_packet()
        decisions = fn(pk, mem)
        rep = c.submit({"pass_id": pk["pass_id"], "decisions": decisions, "advance": "next"})
        if rep.get("status") == "invalid":
            raise RuntimeError(rep)
        passes += 1
        adv = rep["advance"]
        gaps.append(adv["days"])
        if w.player_act.label:
            signed_on = signed_on or w.date.isoformat()
            signed_gaps.append(adv["days"])
        e = w.people[w.player["person"]].wellbeing["energy"]
        if e < 0.2:
            low_days += adv["days"]
            streak += adv["days"]
            low_streak = max(low_streak, streak)
        else:
            streak = 0
    act = w.player_act
    rel = [r for r in w.releases.values() if r.act == act.id]
    released = sorted([r for r in rel if r.status == "released"], key=lambda r: r.date)
    stats = {}
    for st in w.charts.values():
        if st.get("main") and st.get("subject") == "song":
            stats = st["stats"]
    peaks = [stats.get(r.tracks[0], {}).get("peak") for r in released if r.kind == "single"]
    peaks = [p for p in peaks if p]
    kinds = dict(w.events.tally)
    rest_reports = w.flags.get("rest_log", [])
    out = {
        "strategy": strategy, "seed": seed, "passes": passes, "end": w.date.isoformat(),
        "max_gap_days": max(gaps or [0]), "max_signed_gap_days": max(signed_gaps or [0]),
        "very_low_energy_days": low_days, "longest_very_low_streak_days": low_streak,
        "final_energy": round(w.people[w.player["person"]].wellbeing["energy"], 2),
        "auto_rests": kinds.get("auto_rest", 0), "rest_weeks_reported": len(rest_reports),
        "rest_without_recovery": sum(1 for r in rest_reports if r[3] <= r[2]),
        "mean_energy_gain_per_rest_week": round(sum(r[3] - r[2] for r in rest_reports) / max(1, len(rest_reports)), 3),
        "signed": signed_on, "label": act.label,
        "singles_requested_rejected": kinds.get("label_review", 0),
        "development_meetings": kinds.get("development_meeting", 0),
        "label_proposals": sum(1 for o in w.offers.values() if o.target == act.id and o.kind == "label_proposal"),
        "manager_initiatives": kinds.get("manager_presses_label", 0) + kinds.get("manager_brings_song", 0),
        "patience_warnings": kinds.get("patience_warning", 0), "dropped": kinds.get("dropped", 0),
        "first_release": released[0].date if released else None, "releases": len(released),
        "best_hot100_peak": min(peaks) if peaks else None,
        "recognition_pct": c.last_packet()["protagonist"]["public_recognition_pct"],
        "cash": round(w.ledger.balance(w.player["person"])), "royalty_account": round(act.unrecouped),
    }
    replay = c.replay() if real else None
    if replay is not None:
        out["replay_ok"] = replay["ok"]
    c.close()
    return out


def _job(args):
    strat, seed, weeks = args
    tmp = Path(tempfile.mkdtemp(prefix="continuity_"))
    try:
        return run(strat, seed, weeks, tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    flags_with_values = {"--json", "--workers"}
    args, skip = [], False
    for a in sys.argv[1:]:
        if skip:
            skip = False
            continue
        if a in flags_with_values:
            skip = True
            continue
        if not a.startswith("--"):
            args.append(a)
    n_eng = int(args[0]) if len(args) > 0 else 10
    n_other = int(args[1]) if len(args) > 1 else 4
    weeks = int(args[2]) if len(args) > 2 else 52
    out_json = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    plan = [("engaged", s) for s in [1988] + list(range(1, n_eng + 1))]
    if "--replay-check" in sys.argv:
        plan = [("engaged", 1988), ("engaged", 1)]
        weeks = min(weeks, 26)
    plan += [(k, s) for k in ("passive", "overworked", "recovering") for s in range(1, n_other + 1)]
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 1
    from multiprocessing import Pool
    with Pool(workers) as pool:
        rows = []
        for r in pool.imap_unordered(_job, [(s, seed, weeks) for s, seed in plan]):
            rows.append(r)
            print(json.dumps(r), flush=True)
    rows.sort(key=lambda r: (r["strategy"], r["seed"]))
    if out_json:
        Path(out_json).write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()

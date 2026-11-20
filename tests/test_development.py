"""P1/P2 regressions: a label pass leads to follow-up, not an inert stall; the player keeps authority."""
from musicsim.campaign_io import Campaign
from musicsim.player import commands as cmds
from musicsim.sim import advance
from musicsim.systems import development as dev
from musicsim.systems import labels as labels_sys
from tests.conftest import small_scenario


def _signed(tmp_path, seed=5, over=None):
    sc = small_scenario()
    if over:
        sc["config_overrides"] = over
    c = Campaign.create(tmp_path / "camp", sc, seed)
    w = c.world
    org = w.orgs["org:arista"]
    labels_sys.sign(w, org, w.player_act, {"type": "recording_contract", "advance": 30000.0, "royalty_rate": 0.11,
                                           "firm_albums": 1, "option_albums": 4,
                                           "recording_budget_per_album": 150000.0, "term": "test"})
    return c, w, org


def _master(w, title, hook, production, vocal=0.6, melody=0.6):
    """A finished master with chosen strengths and weaknesses (a test fixture, not a gameplay path)."""
    from musicsim.systems.creative import produce_recording, write_composition
    comp = write_composition(w, title, [w.player["person"]], "rnb", key=title)
    comp.attrs.update({"hook": hook, "melody": melody, "singability": hook, "structure": 0.6})
    rec = produce_recording(w, comp, w.player["act"], ["person:pc_contact1"], "rnb", budget=5000, weeks=2, key=title)
    rec.attrs.update({"production": production, "arrangement": production, "vocal_delivery": vocal})
    rec.status = "done"
    return rec


def test_rejected_single_schedules_development_meeting_and_stops_long_advance(tmp_path):
    c, w, org = _signed(tmp_path)
    rec = _master(w, "Weak Song", hook=0.2, production=0.2, vocal=0.3, melody=0.25)
    res = cmds.apply(w, {"command": "release_single", "args": {"recording_id": rec.id, "promo": "high"}})
    assert res["status"] == "rejected"
    assert res["review"]["weaknesses"]                       # intelligible A&R notes, from what the engine knows
    meet = w.flags["development"]["meeting"]
    out = advance(w, 84, stop_on_interrupt=True)            # "next" no longer swallows 84 days
    assert out["days"] <= 12 and any(i["reason"] == "label_meeting" for i in out["interrupts"])
    assert out["to"] > meet
    last = w.flags["development"]["last_meeting"]
    assert last["reviews"] and last["proposals"]             # concrete next steps (remix / re-cut / new songs)
    c.close()


def test_no_inert_stretch_while_signed_and_player_keeps_approval(tmp_path):
    """Six months of 'next' with no decisions: the label keeps checking in, but never acts for the player."""
    c, w, org = _signed(tmp_path)
    _master(w, "Rough One", hook=0.3, production=0.3, vocal=0.4)
    gaps, longest = [], 0
    for _ in range(12):
        out = advance(w, 84, stop_on_interrupt=True)
        gaps.append(out["days"])
        if w.date.isoformat() > "1989-03-10":
            break
    longest = max(gaps)
    assert longest <= 70, gaps
    mine = [r for r in w.releases.values() if r.act == w.player["act"]]
    sessions = [r for r in w.recordings.values() if r.act == w.player["act"] and "Remix" in r.title]
    assert not mine and not sessions                         # proposals wait for the player's decision
    assert any(o.kind == "label_proposal" or o.kind == "song_pitch" for o in w.offers.values()
               if o.target == w.player["act"])
    c.close()


def test_remix_path_then_release_decision(tmp_path):
    c, w, org = _signed(tmp_path)
    rec = _master(w, "Hooky Rough", hook=0.85, production=0.15, vocal=0.6, melody=0.7)
    res = cmds.apply(w, {"command": "release_single", "args": {"recording_id": rec.id, "promo": "standard"}})
    if res["status"] == "accepted":
        return                                              # the label liked it as-is: also a legitimate outcome
    advance(w, 30, stop_on_interrupt=True)
    props = [o for o in w.offers.values() if o.kind == "label_proposal" and o.status == "open"]
    remix = [o for o in props if o.terms["action"] == "remix"]
    assert remix, [o.terms["action"] for o in props]
    fund_before = w.flags.get("recording_fund_used", 0.0)
    r = cmds.apply(w, {"command": "accept_offer", "args": {"offer_id": remix[0].id}})
    assert r["status"] == "accepted" and w.flags["recording_fund_used"] > fund_before
    new = w.recordings[r["recording"]]
    advance(w, 7 * 3 + 2, stop_on_interrupt=False)
    assert new.status == "done" and new.title.endswith("(Remix)")
    assert new.attrs["vocal_delivery"] == rec.attrs["vocal_delivery"]   # the original vocal is kept
    out = cmds.apply(w, {"command": "release_single", "args": {"recording_id": new.id, "promo": "standard"}})
    assert out["status"] in ("accepted", "rejected")         # a real decision, not a guaranteed approval
    c.close()


def test_strong_master_can_be_approved(tmp_path):
    c, w, org = _signed(tmp_path)
    rec = _master(w, "Strong Song", hook=0.9, production=0.85, vocal=0.85, melody=0.85)
    res = cmds.apply(w, {"command": "release_single", "args": {"recording_id": rec.id, "promo": "standard"}})
    assert res["status"] == "accepted"
    c.close()


def test_manager_takes_initiative_for_stalled_signed_client(tmp_path):
    c, w, org = _signed(tmp_path)
    pid = c.last_packet()["pass_id"]
    r = c.submit({"pass_id": pid, "proposals": [{"type": "introduce_person", "name": "Sam Ortiz", "role": "manager",
                                                 "context": "industry veteran", "attitude": "warm"}]})
    mid = r["proposals"][0]["person"]
    w.people[mid].skills["management"] = 0.95
    w.relations[f"{mid}|{w.player['person']}"]["affinity"] = 0.8
    assert cmds.apply(w, {"command": "hire_manager", "args": {"person_id": mid, "commission": 0.2}})["status"] == "accepted"
    cash = w.ledger.balance(w.player["person"])
    advance(w, 7 * 20, stop_on_interrupt=False)
    acts = [e for e in w.events.recent if e.type in ("manager_presses_label", "manager_brings_song")]
    assert acts
    # no client money spent on their initiative (commission on income is the only flow to the manager)
    assert not [j for j in w.ledger.journal if j["to"] == mid and j["category"] != "management_commission"]
    assert w.ledger.balance(w.player["person"]) <= cash + 1e6
    c.close()


def test_label_patience_warning_then_possible_drop(tmp_path):
    c, w, org = _signed(tmp_path, over={"development": {"patience_days": 60, "drop_hazard_weekly": 0.5}})
    _master(w, "Rough", hook=0.2, production=0.2)
    reasons = []
    for _ in range(8):
        out = advance(w, 84, stop_on_interrupt=True)
        reasons += [i["reason"] for i in out["interrupts"]]
        if w.player_act.label is None:
            break
    assert "label_warning" in reasons and "dropped" in reasons
    assert w.player_act.label is None and w.player_act.contract is None
    c.close()


def test_npc_acts_face_the_same_review(tmp_path):
    c = Campaign.create(tmp_path / "camp", small_scenario(), 5)
    advance(c.world, 56, stop_on_interrupt=False)
    reviewed = [r for r in c.world.releases.values() if r.review and not r.historical]
    assert reviewed and all("score" in r.review for r in reviewed)
    shelved = [e for e in c.world.events.recent if e.type == "shelved"]
    assert shelved                                          # labels pass on NPC material too
    c.close()


def test_review_values_commercial_signals_not_just_craft(tmp_path):
    c, w, org = _signed(tmp_path)
    act = w.player_act
    hooky = _master(w, "Hooky", hook=0.9, production=0.4, vocal=0.55, melody=0.6)
    flat = _master(w, "Flat", hook=0.2, production=0.4, vocal=0.55, melody=0.6)
    a = dev.review_master(w, org, act, hooky, "t")
    b = dev.review_master(w, org, act, flat, "t")
    assert a["commercial"] > b["commercial"] and a["score"] > b["score"]
    c.close()


def test_label_spaces_singles(tmp_path):
    c, w, org = _signed(tmp_path)
    a = _master(w, "First", hook=0.9, production=0.85, vocal=0.85, melody=0.85)
    b = _master(w, "Second", hook=0.9, production=0.85, vocal=0.85, melody=0.85)
    r1 = cmds.apply(w, {"command": "release_single", "args": {"recording_id": a.id, "promo": "standard"}})
    r2 = cmds.apply(w, {"command": "release_single", "args": {"recording_id": b.id, "promo": "standard"}})
    assert r1["status"] == r2["status"] == "accepted"
    d1, d2 = (w.releases[r["release"]].date for r in (r1, r2))
    import datetime as dt
    assert (dt.date.fromisoformat(d2) - dt.date.fromisoformat(d1)).days >= 7 * 11 - 6
    assert "doesn't compete" in r2["summary"]
    c.close()

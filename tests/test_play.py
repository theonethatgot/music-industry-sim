"""The playable loop: packets out, validated decisions/proposals in, replay from the command log."""
import json

from musicsim.campaign_io import Campaign, parse_submission_text, validate_submission
from tests.conftest import small_scenario


def _campaign(tmp_path, seed=5):
    return Campaign.create(tmp_path / "camp", small_scenario(), seed)


def test_packet_is_rich_and_has_return_format(tmp_path):
    c = _campaign(tmp_path)
    pk = c.last_packet()
    for key in ("protagonist", "finances", "charts", "news", "people", "producers_for_hire", "commands", "constraints"):
        assert key in pk
    md = c.packet_path().read_text()
    assert "Return format" in md and "```json" in md and pk["pass_id"] in md
    c.close()


def test_submission_validation(tmp_path):
    c = _campaign(tmp_path)
    w = c.world
    bad = {"pass_id": "nope", "decisions": [{"command": "fly_to_moon"}],
           "proposals": [{"type": "relationship_moment", "with": "x", "nature": "y", "valence": 7}]}
    errs = validate_submission(w, bad, c.last_packet())
    assert any("pass_id" in e for e in errs)
    assert any("unknown command" in e for e in errs)
    assert any("valence" in e for e in errs)
    text = "Some narration...\n```json\n" + json.dumps({"pass_id": c.last_packet()["pass_id"]}) + "\n```\n"
    assert parse_submission_text(text)["pass_id"] == c.last_packet()["pass_id"]
    c.close()


def test_play_loop_and_replay(tmp_path):
    c = _campaign(tmp_path)
    pid = c.last_packet()["pass_id"]
    rep = c.submit({"pass_id": pid, "decisions": [
        {"command": "record_song", "args": {"song": "write_own", "title": "Test Song", "producer": "person:pc_contact1",
                                            "genre": "rnb", "studio_weeks": 1, "budget": 300}},
        {"command": "gig", "args": {"weeks": 2, "nights_per_week": 2}}],
        "proposals": [
            {"type": "introduce_person", "name": "Test Manager", "role": "manager", "context": "met at a gig"},
            {"type": "narrative_fact", "text": "The demo sold 10,000 copies."},
            {"type": "narrative_fact", "text": "She always wears her grandmother's ring on stage."}],
        "advance": "2w"})
    assert rep["proposals"][1]["status"] == "rejected"          # invented numbers are refused
    assert rep["proposals"][2]["status"] == "accepted"
    assert any(p.name == "Test Manager" for p in c.world.people.values())
    c.advance("1w")
    res = c.replay()
    assert res["ok"], res
    c.close()
    reopened = Campaign.open(tmp_path / "camp")
    assert reopened.world.state_hash() == reopened.store.commands()[-1]["state_hash"]
    reopened.close()


def test_real_people_cannot_be_invented(tmp_path):
    c = _campaign(tmp_path)
    pid = c.last_packet()["pass_id"]
    rep = c.submit({"pass_id": pid, "proposals": [
        {"type": "introduce_person", "name": "Whitney Houston", "role": "friend", "context": "bumped into her"}]})
    assert rep["proposals"][0]["status"] == "rejected"
    c.close()


def test_world_evolves_without_the_player(tmp_path):
    """The industry keeps releasing, charting and signing when the protagonist does nothing."""
    c = _campaign(tmp_path)
    w = c.world
    before_rel = sum(1 for r in w.releases.values() if r.status == "released")
    before_top = w.charts["hot100"]["last_run"]["top"][0]["subject"] if "hot100" in w.charts else None
    c.advance("8w")
    c.advance("8w")
    after_rel = sum(1 for r in w.releases.values() if r.status == "released")
    assert after_rel > before_rel + 10
    assert w.charts["hot100"]["last_run"]["top"][0]["subject"] != before_top or after_rel > before_rel
    c.close()


def test_standing_orders_and_next_pacing(tmp_path):
    c = _campaign(tmp_path)
    pid = c.last_packet()["pass_id"]
    rep = c.submit({"pass_id": pid, "decisions": [
        {"command": "set_policy", "args": {"gigs_when_idle": 3, "training_when_idle": "vocal"}}], "advance": "next"})
    assert rep["decisions"][0]["status"] == "accepted"
    adv = rep["advance"]
    assert adv["days"] <= 84
    kinds = {x["kind"] for x in c.world.commitments}
    assert "gigs" in kinds and "training" in kinds          # booked by the team, not the player
    pk = c.last_packet()
    assert pk["team"]["standing_orders"]["gigs_when_idle"] == 3
    assert pk["pacing"]["days_covered"] == adv["days"]
    c.close()

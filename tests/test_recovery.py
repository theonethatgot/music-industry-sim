"""P0/P1 regressions from the Danielle playtest: recovery accounting and protected time off."""
import datetime as dt

from musicsim.campaign_io import Campaign
from musicsim.player import commands as cmds
from musicsim.player import proposals as props
from musicsim.core.rng import Draws
from musicsim.sim import advance
from tests.conftest import small_scenario


def _world(tmp_path, seed=5):
    c = Campaign.create(tmp_path / "camp", small_scenario(), seed)
    return c, c.world


def _energy(w):
    return w.people[w.player["person"]].wellbeing["energy"]


def _exhaust(w, e=0.1, s=0.7):
    wb = w.people[w.player["person"]].wellbeing
    wb["energy"], wb["stress"] = e, s


def _to_monday(w):
    while w.date.weekday() != 0:
        advance(w, 1, stop_on_interrupt=False)


def test_auto_rest_actually_restores_energy_over_three_weeks(tmp_path):
    c, w = _world(tmp_path)
    _to_monday(w)
    _exhaust(w)
    cmds.apply(w, {"command": "set_policy", "args": {"rest_when_exhausted": True, "gigs_when_idle": 2}})
    series = [_energy(w)]
    for _ in range(3):
        advance(w, 7, stop_on_interrupt=False)
        series.append(_energy(w))
    # week 1: the Monday tick notices exhaustion and books the rest; week 2: the rest is credited
    assert series[2] > series[0] + 0.25 and series[-1] > series[0] + 0.25, series
    assert all(b >= a for a, b in zip(series, series[1:])), series
    # every "time off" report corresponds to measured recovery, never a no-op claim
    rest_news = [n for n in w.news if n["kind"] == "wellbeing" and n["text"].startswith("Time off")]
    assert rest_news and all("kept sliding" not in n["text"] for n in rest_news)
    c.close()


def test_day_job_limits_recovery_explainably(tmp_path):
    results = {}
    for job in (True, False):
        c, w = _world(tmp_path / str(job))
        _to_monday(w)
        _exhaust(w)
        cmds.apply(w, {"command": "set_day_job", "args": {"active": job}})
        cmds.apply(w, {"command": "set_policy", "args": {"gigs_when_idle": 0, "rest_when_exhausted": False}})
        assert cmds.apply(w, {"command": "rest", "args": {"weeks": 2}})["status"] == "accepted"
        advance(w, 14, stop_on_interrupt=False)
        results[job] = _energy(w)
        c.close()
    assert results[False] > results[True] > 0.1, results


def test_rest_cancels_overlapping_club_dates_and_lessons_and_they_resume(tmp_path):
    c, w = _world(tmp_path)
    _to_monday(w)
    cmds.apply(w, {"command": "set_policy", "args": {"gigs_when_idle": 0}})
    assert cmds.apply(w, {"command": "gig", "args": {"weeks": 4, "nights_per_week": 2}})["status"] == "accepted"
    assert cmds.apply(w, {"command": "train", "args": {"skill": "vocal", "weeks": 4}})["status"] == "accepted"
    advance(w, 7, stop_on_interrupt=False)
    res = cmds.apply(w, {"command": "rest", "args": {"weeks": 1}})
    assert res["status"] == "accepted" and "cancelled" in res["summary"]
    start, end = w.date.isoformat(), (w.date + dt.timedelta(days=6)).isoformat()
    pid = w.player["person"]
    during = [x for x in w.commitments if x["who"] == pid and x["kind"] in ("gigs", "training")
              and not (x["end"] < start or x["start"] > end)]
    assert not during                                         # nothing routine left inside the rest window
    after = [x for x in w.commitments if x["who"] == pid and x["kind"] == "gigs" and x["start"] > end]
    assert after                                              # club dates resume after the break
    advance(w, 1, stop_on_interrupt=False)                    # Monday tick pays for the week *before* the rest
    fees_before = w.ledger.flows.get(f"ext:venues|{pid}|gig_fees", 0.0)
    advance(w, 7, stop_on_interrupt=False)                    # next Monday accounts the rest week: no club income
    assert w.ledger.flows.get(f"ext:venues|{pid}|gig_fees", 0.0) == fees_before
    c.close()


def test_rest_refused_during_studio_session_and_training_refused_during_rest(tmp_path):
    c, w = _world(tmp_path)
    r = cmds.apply(w, {"command": "record_song", "args": {"song": "write_own", "title": "T", "producer": "person:pc_contact1",
                                                         "genre": "rnb", "studio_weeks": 2, "budget": 300}})
    if r["status"] == "accepted":
        assert cmds.apply(w, {"command": "rest", "args": {"weeks": 1}})["status"] == "rejected"
        advance(w, 15, stop_on_interrupt=False)
    assert cmds.apply(w, {"command": "rest", "args": {"weeks": 2}})["status"] == "accepted"
    assert cmds.apply(w, {"command": "train", "args": {"skill": "vocal", "weeks": 1}})["status"] == "rejected"
    assert cmds.apply(w, {"command": "gig", "args": {"weeks": 1, "nights_per_week": 1}})["status"] == "rejected"
    res = props._p_opportunity(w, {"kind": "gig_offer", "context": "test"}, Draws(1, "t"))
    assert res["status"] == "rejected" and "time off" in res["reason"]
    c.close()


def test_manager_never_books_shows_during_protected_rest(tmp_path):
    c, w = _world(tmp_path)
    pid = c.last_packet()["pass_id"]
    r = c.submit({"pass_id": pid, "proposals": [{"type": "introduce_person", "name": "Pat Quinn", "role": "manager",
                                                 "context": "an old friend", "attitude": "warm"}]})
    mid = r["proposals"][0]["person"]
    w.people[mid].skills["management"] = 0.95
    w.relations[f"{mid}|{w.player['person']}"]["affinity"] = 0.8
    hire = cmds.apply(w, {"command": "hire_manager", "args": {"person_id": mid, "commission": 0.2}})
    assert hire["status"] == "accepted", hire
    _to_monday(w)
    cmds.apply(w, {"command": "set_policy", "args": {"gigs_when_idle": 0}})
    assert cmds.apply(w, {"command": "rest", "args": {"weeks": 6}})["status"] == "accepted"
    start, end = w.date.isoformat(), (w.date + dt.timedelta(days=41)).isoformat()
    advance(w, 42, stop_on_interrupt=False)
    played = [e for e in w.events.recent if e.type == "gig_played" and start <= e.date <= end]
    assert not played
    c.close()


def test_cancel_bookings_and_policy_wording(tmp_path):
    c, w = _world(tmp_path)
    cmds.apply(w, {"command": "train", "args": {"skill": "vocal", "weeks": 4}})
    res = cmds.apply(w, {"command": "set_policy", "args": {"training_when_idle": "none"}})
    assert "Existing bookings are kept" in res["summary"]
    assert cmds.apply(w, {"command": "cancel_bookings", "args": {"kind": "training"}})["status"] == "accepted"
    assert not [x for x in w.commitments if x["kind"] == "training" and x["end"] >= w.date.isoformat()]
    c.close()

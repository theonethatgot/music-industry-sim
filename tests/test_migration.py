"""Saves from an earlier engine are refused, then continued only by explicit snapshot-forward migration."""
import json

import pytest

from musicsim.campaign_io import Campaign, EngineVersionError
from musicsim.world import World, arrays_to_blob, blob_to_arrays
from tests.conftest import small_scenario


def _as_old_save(path):
    """Make a save look like one written by engine 0.1 (old version stamp, old config tree)."""
    c = Campaign.open(path)
    date, h, doc, blob = c.store.read_snapshot()
    for k in ("wellbeing", "development"):
        doc["config_tree"].pop(k, None)
    doc["flags"].pop("wellbeing_from", None)
    c.store.write_snapshot(date, h, doc, blob)
    c.store.set_meta("engine_version", "0.1.0")
    c.store.commit()
    c.close()


def test_old_save_is_refused_then_migrated_with_history_preserved(tmp_path):
    p = tmp_path / "old"
    c = Campaign.create(p, small_scenario(), 5)
    c.advance("2w")
    before = [(e["seq"], e["kind"], e["state_hash"]) for e in c.store.commands()]
    c.close()
    _as_old_save(p)
    with pytest.raises(EngineVersionError):
        Campaign.open(p)
    res = Campaign.migrate(p, "test migration")
    assert res["status"] == "migrated" and res["from"] == "0.1.0"
    c = Campaign.open(p)
    after = [(e["seq"], e["kind"], e["state_hash"]) for e in c.store.commands()]
    assert after[: len(before)] == before                     # earlier history untouched
    assert after[len(before)][1] == "migrate"
    assert c.world.flags["migrations"][0]["from"] == "0.1.0"
    c.submit({"pass_id": c.last_packet()["pass_id"], "decisions": [], "advance": "next"})
    rep = c.replay()
    assert rep["ok"] and "migration checkpoint" in rep["verified_from"], rep
    c.close()


def test_outcome_hash_survives_round_trip(tmp_path):
    c = Campaign.create(tmp_path / "x", small_scenario(), 5)
    doc, arrays = c.world.to_state()
    w2 = World.from_state(json.loads(json.dumps(doc, default=str)), blob_to_arrays(arrays_to_blob(arrays)))
    assert w2.outcome_hash() == c.world.outcome_hash()
    c.close()

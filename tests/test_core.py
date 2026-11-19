"""Determinism, persistence, money and RNG properties."""
import datetime as dt

from musicsim.campaign import build_world, load_character
from musicsim.core import rng
from musicsim.sim import advance
from musicsim.world import World, arrays_to_blob, blob_to_arrays


def test_rng_is_pure_and_keyed():
    assert rng.uniform(1, "a", 2) == rng.uniform(1, "a", 2)
    assert rng.uniform(1, "a", 2) != rng.uniform(1, "a", 3)
    assert rng.uniform(1, "a", 2) != rng.uniform(2, "a", 2)
    xs = [rng.normal(5, "n", i) for i in range(4000)]
    mean = sum(xs) / len(xs)
    var = sum((x - mean) ** 2 for x in xs) / len(xs)
    assert abs(mean) < 0.06 and 0.9 < var < 1.1


def test_same_seed_same_world(scenario):
    ch = load_character(scenario["protagonist"]["character"])
    a = build_world(scenario, 3, ch)
    b = build_world(scenario, 3, ch)
    assert a.state_hash() == b.state_hash()
    advance(a, 21, stop_on_interrupt=False)
    advance(b, 21, stop_on_interrupt=False)
    assert a.state_hash() == b.state_hash()


def test_different_seed_different_world(scenario):
    ch = load_character(scenario["protagonist"]["character"])
    assert build_world(scenario, 3, ch).state_hash() != build_world(scenario, 4, ch).state_hash()


def test_save_load_continue_equals_uninterrupted(world):
    other = World.from_state(*_roundtrip(world))
    assert other.state_hash() == world.state_hash()
    advance(world, 30, stop_on_interrupt=False)
    advance(other, 12, stop_on_interrupt=False)
    other = World.from_state(*_roundtrip(other))
    advance(other, 18, stop_on_interrupt=False)
    assert other.date == world.date
    assert other.state_hash() == world.state_hash()


def _roundtrip(w):
    import json
    doc, arrays = w.to_state()
    return json.loads(json.dumps(doc, default=str)), blob_to_arrays(arrays_to_blob(arrays))


def test_money_is_conserved(world):
    advance(world, 35, stop_on_interrupt=False)
    assert abs(world.ledger.total()) < 1.0      # every transfer is balanced


def test_clock_runs_daily(world):
    d0 = world.date
    advance(world, 9, stop_on_interrupt=False)
    assert world.date == d0 + dt.timedelta(days=9)

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from musicsim.campaign import build_world, load_character, load_scenario  # noqa: E402


def small_scenario(name="us_1988_aspiring", burn_in=6, npcs=60, **over):
    sc = copy.deepcopy(load_scenario(name))
    sc["burn_in_weeks"] = burn_in
    sc.setdefault("world", {})["fictional_npc_acts"] = npcs
    sc.update(over)
    return sc


@pytest.fixture(scope="session")
def scenario():
    return small_scenario()


@pytest.fixture
def world(scenario):
    return build_world(scenario, 11, load_character(scenario["protagonist"]["character"]))

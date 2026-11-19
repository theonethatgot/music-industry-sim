"""Market rules: era-gated methodologies, neutrality of engine code, separation of signals."""
import datetime as dt
import re
from pathlib import Path

import numpy as np

from musicsim.market import MarketRuntime
from musicsim.sim import advance
from musicsim.systems.charts import chart_name, methodology_for

ROOT = Path(__file__).resolve().parents[1] / "musicsim"


def test_methodologies_only_exist_in_their_windows():
    rt = MarketRuntime("US")
    hot = rt.methodologies["hot100"]
    assert methodology_for(hot, dt.date(1988, 9, 4))["id"] == "rank_reports"
    assert methodology_for(hot, dt.date(1991, 11, 30))["id"] == "bds_soundscan"
    albums = rt.methodologies["top_albums"]
    assert methodology_for(albums, dt.date(1991, 5, 24))["id"] == "rank_reports"
    assert methodology_for(albums, dt.date(1991, 5, 25))["id"] == "soundscan"
    rap = rt.methodologies["rap_singles"]
    assert methodology_for(rap, dt.date(1988, 12, 31)) is None
    assert chart_name(rt.methodologies["black_singles"], dt.date(1990, 11, 3)) == "Hot R&B Singles"


def test_no_chart_published_before_it_existed(world):
    advance(world, 28, stop_on_interrupt=False)
    for run in world.chart_log:
        meth = world.markets["US"].methodologies[run["chart"]]
        assert methodology_for(meth, dt.date.fromisoformat(run["week_end"])) is not None
    assert "rap_singles" not in {r["chart"] for r in world.chart_log}   # 1988: chart doesn't exist yet


FORBIDDEN = [r"[\"'](US|KR|GB|JP|UK)[\"']", r"Billboard", r"hot100|top_albums|black_singles", r"Korea", r"SoundScan",
             r"[\"'](rnb|pop|hip_hop|dance_pop|rock|soul_ballad)[\"']", r"\b19[5-9]\d-\d\d", r"\b20[0-2]\d-\d\d"]


def test_engine_code_is_market_neutral():
    """Countries, institutions, chart ids, genres and dates belong in data, never in engine code."""
    offenders = []
    for p in ROOT.rglob("*.py"):
        for n, line in enumerate(p.read_text().splitlines(), 1):
            code = line.split("#", 1)[0]
            if p.name == "packet.py" and "example" in code:
                continue
            for pat in FORBIDDEN:
                if re.search(pat, code):
                    offenders.append(f"{p.name}:{n}: {line.strip()[:90]}")
    assert not offenders, "\n".join(offenders)


def test_outcome_systems_do_not_know_who_is_the_player():
    """Fairness: demand, creative and chart maths never branch on the protagonist."""
    for name in ("demand.py", "creative.py", "charts.py"):
        text = (ROOT / "systems" / name).read_text()
        code = "\n".join(line for line in text.splitlines() if "media." not in line)
        assert "player" not in code, name


def test_album_and_song_popularity_are_separate(world):
    advance(world, 56, stop_on_interrupt=False)
    T, AT = world.tables["US"], world.albums["US"]
    assert T.n > 20 and AT.n > 3
    # the albums are driven by fans + engaged listeners, not a fixed ratio of single sales
    ratios = []
    for rel in world.releases.values():
        if rel.kind == "album" and rel.status == "released" and rel.focus:
            single = [world.releases[world.recordings[f].single_release] for f in rel.focus
                      if world.recordings[f].single_release in world.releases]
            s = sum(x.sold for x in single)
            if s > 1000 and rel.sold > 100:
                ratios.append(rel.sold / s)
    if len(ratios) >= 3:
        assert np.std(np.log(ratios)) > 0.2

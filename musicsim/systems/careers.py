"""Career/status updates from named drivers: recognition, appeal, fandom, observed power,
momentum (outcomes vs. expectations), certifications and career stage."""
from __future__ import annotations

import numpy as np

from .charts import main_chart
from .labels import week_units


def possessive(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


def weekly(world, market: str):
    cfg = world.config.tree["careers"]
    rt = world.markets[market]
    T = world.tables[market]
    AT = world.albums[market]
    N = rt.population(world.date)
    songs_by_act: dict[str, list[int]] = {}
    if T.n:
        for i in np.nonzero(T.active)[0]:
            songs_by_act.setdefault(world.recordings[T.ids[i]].act, []).append(i)
    zeros = [0.0] * rt.G
    for act in sorted(world.acts.values(), key=lambda a: a.id):
        rec = np.array(act.recognition.get(market, zeros)) * cfg["recognition_decay"]
        app = np.array(act.appeal.get(market, [0.5] * rt.G))
        fan = np.array(act.fandom.get(market, zeros))
        rows = songs_by_act.get(act.id, [])
        if rows:
            A = T.view("A")[rows]
            E = T.view("E")[rows]
            # recognition = knowing the act by name: driven by awareness of its current songs,
            # remembered (slowly decaying) between releases; never compounding week over week
            x = T.view("C")[rows] / np.maximum(A, 1e-9)
            familiar = A * (1 - np.exp(-x / 12.0))           # heard it enough times to know whose it is
            # many listeners know a hit without knowing who sings it
            rec = np.maximum(rec, 1 - np.prod(1 - 0.45 * familiar, axis=0))
            liking = np.where(A > 0.02, E / np.maximum(A, 1e-9), -1.0)
            best = liking.max(axis=0)
            app = np.where(best >= 0, 0.9 * app + 0.1 * np.clip(best * 1.2, 0, 1), app)
            conv = cfg["fan_conversion"] * E.sum(axis=0) * (0.5 + act.flags.get("persona_strength", 0.5))
            fan = fan + conv * np.clip(rec - fan, 0, 1)
        fan = np.minimum(fan * (1 - cfg["fan_churn"]), rec)
        act.recognition[market] = np.round(rec, 6).tolist()
        act.appeal[market] = np.round(app, 6).tolist()
        act.fandom[market] = np.round(fan, 6).tolist()
    _observed_power(world, market)
    # refresh act-dependent parts of song appeal and fan vectors
    if T.n:
        from .demand import song_appeal
        for i in np.nonzero(T.active)[0]:
            r = world.recordings[T.ids[i]]
            act = world.acts[r.act]
            T.view("appeal")[i] = song_appeal(world, market, r, act)
            T.view("fanvec")[i] = act.fandom.get(market, zeros)
    if AT.n:
        for a in np.nonzero(AT.active)[0]:
            rel = world.releases[AT.ids[a]]
            AT.view("fanvec")[a] = np.maximum(AT.view("fanvec")[a], world.acts[rel.act].fandom.get(market, zeros))
    _stages(world, market, N)


def _observed_power(world, market):
    """The industry's belief about an act's pull, learned from measured results (not true values)."""
    cfg = world.config.tree["careers"]
    lr = cfg["power_learning"]
    hl = cfg["momentum_halflife_weeks"]
    decay = 0.5 ** (1 / hl)
    singles = main_chart(world, market, "song")
    s_stats = singles.get("stats", {})
    for rel in sorted(world.releases.values(), key=lambda r: r.id):
        if rel.status != "released" or rel.market != market:
            continue
        act = world.acts[rel.act]
        units = week_units(world, market, rel)
        rel.weekly.append({"week_end": (world.date.fromordinal(world.date.toordinal() - 1)).isoformat(),
                           "units": round(units)})
        if len(rel.weekly) > 80:
            rel.weekly = rel.weekly[-80:]
        weeks = len(rel.weekly)
        if weeks > 30:
            continue
        if rel.kind == "single":
            peak_rank = s_stats.get(rel.tracks[0], {}).get("peak")
            obs = 0.0 if peak_rank is None else max(0.0, (101 - peak_rank) / 100) ** 1.3
            if weeks >= 4:
                act.singles_power_o = round(act.singles_power_o + lr * (obs - act.singles_power_o) / 4, 4)
            surprise = (units - rel.expectation * 0.6) / max(rel.expectation, 2000)
        else:
            obs = min(1.0, units / 250000)
            if weeks >= 2:
                act.album_power_o = round(act.album_power_o + lr * (obs - act.album_power_o) / 3, 4)
            surprise = (units - rel.expectation * 0.6) / max(rel.expectation, 5000)
        if weeks <= 12:
            act.momentum = round(float(np.clip(act.momentum * decay + (1 - decay) * surprise, -1, 3)), 4)
    for act in world.acts.values():
        if not any(r.act == act.id and r.status == "released" and len(r.weekly) <= 12 for r in world.releases.values()):
            act.momentum = round(act.momentum * decay, 4)


def _stages(world, market, N):
    for act in world.acts.values():
        rec = np.array(act.recognition.get(market, [0.0] * len(N)))
        fame = float((rec * N).sum() / N.sum())
        old = act.stage
        if act.stage == "aspiring" and act.label:
            act.stage = "rookie"
        if fame > 0.55:
            act.stage = "star"
        elif fame > 0.3 and act.stage in ("aspiring", "rookie", "rising"):
            act.stage = "established"
        elif fame > 0.08 and act.stage in ("aspiring", "rookie"):
            act.stage = "rising"
        if act.stage != old:
            eid = world.emit("careers", "stage_change", [act.id], {"from": old, "to": act.stage, "fame": round(fame, 3)})
            if world.player.get("act") == act.id:
                world.add_news(f"{act.name} is now regarded as {act.stage.replace('_', ' ')} in the industry.",
                               "career", [act.id], tag="reported", importance=0.7, event_id=eid)


def certifications(world, market: str):
    rt = world.markets[market]
    for rel in sorted(world.releases.values(), key=lambda r: r.id):
        if rel.status != "released" or rel.market != market:
            continue
        th = rt.cert_thresholds("album" if rel.kind == "album" else "single", world.date)
        if not th:
            continue
        level = ""
        if rel.shipped >= th["platinum"]:
            mult = int(rel.shipped // th["platinum"])
            level = "platinum" if mult == 1 or not th.get("multi", True) else f"{mult}x platinum"
        elif rel.shipped >= th["gold"]:
            level = "gold"
        if level and level != rel.cert:
            rel.cert = level
            act = world.acts[rel.act]
            body = rt.data["certification"]["body"]
            eid = world.emit("certification", "certified", [rel.id, rel.act],
                             {"body": body, "level": level, "basis": rt.data["certification"]["basis"],
                              "shipped": round(rel.shipped)})
            mine = world.player.get("act") == rel.act
            if mine or act.singles_power_o > 0.3 or act.historical:
                world.add_news(f"{body}: {possessive(act.name)} \"{rel.title}\" ({rel.kind}) certified {level}.",
                               "certification", [rel.id, rel.act], tag="official",
                               importance=0.9 if mine else 0.35, event_id=eid)

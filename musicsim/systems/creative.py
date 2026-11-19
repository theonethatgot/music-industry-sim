"""Creative production: songs come from the people who make them, not from prose.

Composition attributes depend on the writers; recording attributes on producers,
performers, budget, time and creative risk. The same functions serve real and
fictional acts and the protagonist (no caller identity enters the maths).
"""
from __future__ import annotations

import math

import numpy as np

from ..core import dates
from ..core.rng import Draws
from ..entities import Composition, Recording



def _clip(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def skill(world, pid: str | None, name: str, genre: str | None = None, default: float = 0.5) -> float:
    p = world.people.get(pid) if pid else None
    if p is None:
        return default
    base = float(p.skills.get(name, default))
    if genre is None:
        return base
    st = p.style_skill.get(genre)
    fluency = float(st) if st is not None else 0.55
    return base * (0.6 + 0.4 * fluency)


def write_composition(world, title: str, writers: list[str], genre: str, key: str,
                      hist: float | None = None, historical: bool = False) -> Composition:
    cfg = world.config
    dr = Draws(world.seed, "creative", "composition", key)
    sw = [skill(world, w, "songwriting", genre, 0.5) for w in writers] or [0.52]
    base = max(sw) * 0.7 + (sum(sw) / len(sw)) * 0.3          # best writer leads; collaborators help
    sigma = cfg["creative.noise"]
    nudge = 0.0
    if hist is not None:
        nudge = cfg["creative.history_evidence_weight"] * (hist - 0.5) * 0.6
    attrs = {
        "melody": _clip(base + nudge + sigma * dr.normal("melody")),
        "lyric_craft": _clip(base * 0.95 + sigma * dr.normal("lyric")),
        "structure": _clip(base + sigma * dr.normal("structure")),
        "hook": _clip(0.75 * base + 0.25 * dr.uniform("hook_luck") + nudge + sigma * dr.normal("hook")),
        "depth": _clip(0.65 * base + 0.35 * dr.uniform("depth_luck") + 0.5 * nudge + sigma * dr.normal("depth")),
        "singability": _clip(0.5 * base + 0.5 * dr.uniform("sing") + sigma * dr.normal("singability")),
    }
    cid = world.new_id("comp")
    comp = Composition(id=cid, title=title, writers=[{"person": w, "share": round(1 / max(1, len(writers)), 4)}
                                                       for w in writers],
                       attrs={k: round(v, 4) for k, v in attrs.items()}, created=dates.iso(world.date),
                       genre=genre, historical=historical)
    world.compositions[cid] = comp
    world.emit("creative", "composition_written", [cid, *writers],
               {"title": title, "genre": genre, "attrs": comp.attrs, "history_nudge": round(nudge, 4)},
               draws=dr.log, public=False)
    return comp


def produce_recording(world, comp: Composition, act_id: str, producers: list[str], genre: str,
                      budget: float, weeks: int, key: str, ambition: float | None = None,
                      mood_shift: float = 0.0, hist: float | None = None, controversy: float | None = None,
                      payer: str = "", historical: bool = False, notes: list | None = None) -> Recording:
    cfg = world.config
    rt = next(iter(world.markets.values()))
    act = world.acts[act_id]
    dr = Draws(world.seed, "creative", "recording", key)
    lead = act.members[0]["person"] if act.members else None
    if ambition is None:
        avc = world.people[lead].personality.get("artistic_vs_commercial", 0.0) if lead in world.people else 0.0
        ambition = _clip(0.35 + 0.3 * avc)
    ps = [skill(world, p, "production", genre, 0.55) for p in producers] or [0.5]
    prod = max(ps) * 0.75 + (sum(ps) / len(ps)) * 0.25
    budget_factor = 1 - math.exp(-max(0.0, budget) / cfg["creative.budget_ref"])
    time_factor = 1 - math.exp(-max(1, weeks) / 3.0)
    sigma = cfg["creative.noise"] * (1 + cfg["creative.ambition_variance"] * ambition * 5)
    nudge = cfg["creative.history_evidence_weight"] * (hist - 0.5) * 0.4 if hist is not None else 0.0
    vocal = skill(world, lead, "vocal", genre, 0.5)
    perf = sum(skill(world, m["person"], "performance", None, 0.5) for m in act.members) / max(1, len(act.members))
    attrs = {
        "production": _clip(prod * (0.62 + 0.23 * budget_factor + 0.15 * time_factor) + nudge + sigma * dr.normal("production")),
        "vocal_delivery": _clip(vocal * (0.8 + 0.2 * prod) + 0.5 * nudge + sigma * dr.normal("vocal")),
        "arrangement": _clip(0.75 * prod + 0.25 * comp.attrs["structure"] + sigma * dr.normal("arrangement")),
        "signature": _clip(0.25 + 0.35 * dr.uniform("signature_luck") + 0.3 * ambition + 0.1 * prod + sigma * dr.normal("signature")),
        "ambition": _clip(ambition),
        "accessibility": _clip(0.72 - 0.35 * ambition + (0.12 if rt.genre_meta.get(genre, {}).get("mainstream") else 0.0) + sigma * dr.normal("access")),
        "dance_hook": 0.0,
        "controversy": 0.0,
    }
    centroid = rt.centroids[rt.gidx[genre]]
    offset = np.array([dr.normal("style", i) for i in range(len(centroid))]) * 0.05
    style = np.clip(centroid + offset, 0, 1)
    style[1] = float(np.clip(style[1] + mood_shift, 0, 1))        # mood axis
    attrs["dance_hook"] = _clip(style[2] * (0.5 + 0.5 * perf) + 0.1 * dr.normal("dance"))
    attrs["controversy"] = _clip(controversy if controversy is not None else style[7] * 0.6 + 0.1 * dr.uniform("contro"))
    rid = world.new_id("rec")
    rec = Recording(id=rid, composition=comp.id, title=comp.title, act=act_id, producers=list(producers),
                    attrs={k: round(v, 4) for k, v in attrs.items()}, style=[round(float(x), 4) for x in style],
                    genre=genre, started=dates.iso(world.date), cost=round(budget, 2), payer=payer,
                    historical=historical, hist_evidence=hist, notes=list(notes or []), draws=dr.log)
    world.recordings[rid] = rec
    comp.status = "recorded"
    world.emit("creative", "recording_made", [rid, act_id, comp.id, *producers],
               {"title": comp.title, "genre": genre, "budget": budget, "weeks": weeks, "ambition": round(ambition, 3),
                "attrs": rec.attrs, "history_nudge": round(nudge, 4)}, draws=dr.log, public=False)
    return rec


def craft_score(world, rec: Recording) -> float:
    c = world.compositions[rec.composition].attrs
    a = rec.attrs
    return (0.22 * c["melody"] + 0.10 * c["structure"] + 0.08 * c["lyric_craft"] + 0.22 * a["production"]
            + 0.25 * a["vocal_delivery"] + 0.13 * a["arrangement"])


def describe(world, rec: Recording, observed: dict | None = None) -> list[str]:
    """Descriptive tags for narration, from (possibly observed) attributes."""
    c = dict(world.compositions[rec.composition].attrs)
    a = dict(rec.attrs)
    if observed:
        c.update({k: v for k, v in observed.items() if k in c})
        a.update({k: v for k, v in observed.items() if k in a})
    tags = []

    def band(v, hi, mid, lo):
        return hi if v >= 0.72 else (mid if v >= 0.5 else lo)

    tags.append(band(c["hook"], "an immediate, sticky hook", "a decent hook that takes a few listens",
                     "no obvious hook"))
    tags.append(band(c["melody"], "a strong melody", "a serviceable melody", "a weak melody"))
    tags.append(band(c["depth"], "grows on repeat listens", "moderately durable", "may wear out fast"))
    tags.append(band(a["production"], "polished, radio-ready production", "solid production",
                     "thin or dated-sounding production"))
    tags.append(band(a["vocal_delivery"], "a commanding vocal", "a capable vocal", "an uncertain vocal"))
    if a["signature"] >= 0.7:
        tags.append("a distinctive sound that stands out")
    elif a["signature"] < 0.4:
        tags.append("sounds like a lot of what's on the radio")
    if a["dance_hook"] >= 0.65:
        tags.append("built for the dance floor")
    if a["ambition"] >= 0.65:
        tags.append("an ambitious, risky arrangement")
    if c["singability"] >= 0.7:
        tags.append("an easy sing-along chorus")
    return tags

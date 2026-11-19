"""Money: the per-unit revenue waterfall, artist royalty accounts and recoupment,
mechanical royalties to writers, label overhead and personal finances.
Label revenue is not artist income: royalties only reach an artist once recouped."""
from __future__ import annotations

from .labels import week_units
from .release import release_account


def weekly(world, market: str) -> dict:
    """Book last week's sales. Returns {release_id: units} for restocking."""
    rt = world.markets[market]
    d = world.date
    L = world.ledger
    units_by_rel: dict[str, float] = {}
    mech_rate = rt.mechanical_rate(d)
    norms = rt.data.get("royalty_norms", {})
    for rel in sorted(world.releases.values(), key=lambda r: r.id):
        if rel.status != "released" or rel.market != market:
            continue
        u = week_units(world, market, rel)
        if u <= 0:
            continue
        units_by_rel[rel.id] = u
        kind = "album" if rel.kind == "album" else "single"
        price = rt.price(kind, d)
        consumer = u * price
        label_gross = consumer * rt.dealer_share()
        payee = release_account(world, rel)
        L.transfer(d, "ext:consumers", "ext:retail", consumer - label_gross, "retail_margin", rel.id)
        L.transfer(d, "ext:consumers", payee, label_gross, "sales", rel.id)
        rel.revenue_label += label_gross
        # mechanicals: per track per unit, half to writers, half to publishers (simplified)
        n_tracks = len(rel.tracks) if kind == "album" else 1
        act = world.acts[rel.act]
        for tid in rel.tracks[:n_tracks]:
            rec = world.recordings.get(tid)
            if rec is None:
                continue
            comp = world.compositions[rec.composition]
            controlled = any(w["person"] in {m["person"] for m in act.members} for w in comp.writers)
            rate = mech_rate * (0.75 if controlled and kind == "album" else 1.0)
            total = u * rate
            if not comp.writers:
                L.transfer(d, payee, "ext:publishers", total, "mechanicals", rel.id)
                continue
            for w in comp.writers:
                share = total * float(w["share"])
                L.transfer(d, payee, w["person"], share * 0.5, "mechanicals_writer", rel.id)
                L.transfer(d, payee, "ext:publishers", share * 0.5, "mechanicals_publisher", rel.id)
        # artist royalty accrues to the recoupment account (no cash yet)
        if rel.label and act.contract and act.contract in world.contracts:
            c = world.contracts[act.contract]
            rate = float(c.terms.get("royalty_rate", norms.get("new_artist", 0.1)))
            royalty = consumer * rate * norms.get("deduction_factor", 0.8)
            act.unrecouped += royalty
            act.royalties_accrued += royalty
    _label_overheads(world, market)
    _statements(world)
    _people(world)
    return units_by_rel


def _label_overheads(world, market):
    for org in sorted(world.orgs.values(), key=lambda o: o.id):
        if org.kind == "record_company" and org.market == market:
            world.ledger.transfer(world.date, org.id, "ext:overhead", 45000 * org.params.get("size", 1.0),
                                  "overhead", "")


def _statements(world):
    """Semi-annual royalty statements: recouped acts are paid what they've earned beyond costs."""
    interval = world.config["finance.statement_interval_weeks"]
    week = world.date.toordinal() // 7
    if week % interval:
        return
    for act in sorted(world.acts.values(), key=lambda a: a.id):
        if act.unrecouped > 1 and act.label:
            amount = act.unrecouped
            members = [m["person"] for m in act.members] or [act.id]
            for p in members:
                world.ledger.transfer(world.date, f"org:{act.label}", p, amount / len(members), "royalties", act.id)
            act.unrecouped = 0.0
            eid = world.emit("finance", "royalty_statement", [act.id, f"org:{act.label}"],
                             {"paid": round(amount, 2)}, public=False)
            if world.player.get("act") == act.id:
                world.add_news(f"Royalty statement: {act.name} is recouped and receives ${amount:,.0f}.", "finance",
                               [act.id], tag="official", importance=0.8, event_id=eid)
        elif act.label and world.player.get("act") == act.id:
            world.emit("finance", "royalty_statement", [act.id], {"paid": 0, "unrecouped": round(act.unrecouped, 2)},
                       public=False)


def _people(world):
    """Protagonist's weekly personal economy (NPC personal finance is not simulated yet)."""
    pid = world.player.get("person")
    if not pid:
        return
    L = world.ledger
    job = world.flags.get("day_job")
    if job and job.get("active"):
        L.transfer(world.date, "ext:employers", pid, job["weekly_income"], "wages", job["title"])
    style = world.flags.get("lifestyle", "modest")
    cost = world.config.tree["finance"]["living_cost_week"].get(style, 220)
    L.transfer(world.date, pid, "ext:living_costs", cost, "living_costs", style)
    if L.balance(pid) < -2000 and not world.flags.get("debt_warned"):
        world.flags["debt_warned"] = True
        world.add_news("You are more than $2,000 in debt; creditors and family are getting anxious.", "finance",
                       [pid], tag="official", importance=0.8)
        world.interrupts.append({"reason": "debt"})

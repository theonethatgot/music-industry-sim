"""Double-entry ledger. Money moves only by balanced transfers between accounts.

External accounts (prefix ``ext:``) are the explicit sources and sinks of the
economy (consumers, retail, manufacturing, studios, promotion services, tax),
which makes a conservation test possible.
"""
from __future__ import annotations

from collections import defaultdict


class Ledger:
    def __init__(self):
        self.balances: dict[str, float] = defaultdict(float)
        # aggregated flows: (from, to, category) -> amount, plus a bounded journal
        self.flows: dict[str, float] = defaultdict(float)
        self.journal: list[dict] = []

    def transfer(self, date, frm: str, to: str, amount: float, category: str, memo: str = "",
                 currency: str = "USD") -> None:
        if amount < 0:
            frm, to, amount = to, frm, -amount
        if amount == 0:
            return
        amount = round(float(amount), 2)
        self.balances[frm] -= amount
        self.balances[to] += amount
        self.flows[f"{frm}|{to}|{category}"] += amount
        self.journal.append({"date": str(date), "from": frm, "to": to, "amount": amount,
                             "category": category, "memo": memo, "currency": currency})
        if len(self.journal) > 5000:
            self.journal = self.journal[-4000:]

    def balance(self, account: str) -> float:
        return round(self.balances.get(account, 0.0), 2)

    def total(self) -> float:
        return round(sum(self.balances.values()), 2)

    def to_dict(self) -> dict:
        return {"balances": dict(sorted(self.balances.items())),
                "flows": dict(sorted(self.flows.items())),
                "journal": self.journal}

    @classmethod
    def from_dict(cls, d: dict) -> "Ledger":
        led = cls()
        led.balances.update(d.get("balances", {}))
        led.flows.update(d.get("flows", {}))
        led.journal = list(d.get("journal", []))
        return led

"""Layered YAML configuration: universal -> market -> scenario overrides."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import yaml

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def _plain(obj):
    """YAML dates become ISO strings so all loaded data is JSON-serialisable and hash-stable."""
    import datetime as _dt
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    return obj


def load_yaml(path: Path | str):
    with open(path, encoding="utf-8") as f:
        return _plain(yaml.safe_load(f))


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def stable_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


class Config:
    """Read-only parameter tree with dotted access helpers."""

    def __init__(self, tree: dict):
        self.tree = tree
        self.hash = stable_hash(tree)

    def get(self, dotted: str, default=None):
        node = self.tree
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, dotted: str):
        v = self.get(dotted, KeyError)
        if v is KeyError:
            raise KeyError(dotted)
        return v


def load_config(market_ids: list[str], overrides: dict | None = None) -> Config:
    tree = load_yaml(DATA_DIR / "universal" / "defaults.yaml")
    for m in market_ids:
        p = DATA_DIR / "markets" / m / "params.yaml"
        if p.exists():
            tree = deep_merge(tree, {"markets": {m: load_yaml(p)}})
    if overrides:
        tree = deep_merge(tree, overrides)
    return Config(tree)

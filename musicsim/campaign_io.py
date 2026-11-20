"""Campaign persistence and the play loop: create, submit, advance, packet, replay.

A campaign directory holds campaign.sqlite (snapshot + logs) and packets/pass_NNNN.{md,json}.
Every state-changing step is a logged command, so state = f(scenario, seed, commands).
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from .campaign import build_world, load_character, load_scenario
from .core import dates
from .core.config import DATA_DIR, stable_hash
from .core.store import Store
from .narrator import packet as packet_mod
from .player import commands as cmds
from .player import proposals as props
from .sim import advance as sim_advance
from .world import World, arrays_to_blob, blob_to_arrays, make_config

DEFAULT_ADVANCE_DAYS = 28
ENGINE_VERSION = __import__("musicsim").__version__


class EngineVersionError(RuntimeError):
    pass


def _minor(v: str) -> str:
    return ".".join(str(v).split(".")[:2])
NEXT_EVENT_CAP_DAYS = 84          # "next": run until something needs the player, at most ~3 months


def advance_days(spec: str | None) -> int:
    if spec in (None, "", "next", "until_event"):
        return NEXT_EVENT_CAP_DAYS
    return dates.parse_duration(spec)


def data_version() -> str:
    files = sorted(p for p in DATA_DIR.rglob("*.yaml"))
    return stable_hash({str(p.relative_to(DATA_DIR)): p.read_text(encoding="utf-8") for p in files})


class Campaign:
    def __init__(self, path: Path | str, store: Store, world: World):
        self.path = Path(path)
        self.store = store
        self.world = world

    @property
    def id(self) -> str:
        return self.path.name

    # ------------------------------------------------------------ lifecycle
    @classmethod
    def create(cls, path, scenario_name, seed: int, character: str | None = None) -> "Campaign":
        """scenario_name: a preset name/path, or an already-loaded scenario dict."""
        path = Path(path)
        if (path / "campaign.sqlite").exists():
            raise FileExistsError(f"{path} already holds a campaign")
        scenario = scenario_name if isinstance(scenario_name, dict) else load_scenario(scenario_name)
        ch_name = character or scenario.get("protagonist", {}).get("character")
        ch = load_character(ch_name)
        store = Store(path / "campaign.sqlite")
        world = build_world(scenario, seed, ch)
        store.set_meta("scenario", scenario)
        store.set_meta("character", ch)
        store.set_meta("seed", seed)
        store.set_meta("data_version", data_version())
        store.set_meta("engine_version", ENGINE_VERSION)
        import numpy
        import platform
        store.set_meta("runtime", {"python": platform.python_version(), "numpy": numpy.__version__,
                                   "machine": platform.machine()})
        c = cls(path, store, world)
        c.make_packet()
        c._log("create", {"scenario": scenario.get("id"), "seed": seed, "character": ch.get("id")}, {})
        return c

    @classmethod
    def open(cls, path) -> "Campaign":
        path = Path(path)
        store = Store(path / "campaign.sqlite")
        saved = store.get_meta("engine_version", "0.1.0")
        if _minor(saved) != _minor(ENGINE_VERSION):
            store.close()
            raise EngineVersionError(
                f"{path} was saved by engine {saved}; this is engine {ENGINE_VERSION}. Its history stays valid on "
                f"engine {saved}. To continue it here, run `python -m musicsim migrate {path}` "
                "(see docs/MIGRATION.md), or start a new campaign.")
        _, _, doc, blob = store.read_snapshot()
        world = World.from_state(doc, blob_to_arrays(blob))
        return cls(path, store, world)

    @classmethod
    def migrate(cls, path, note: str = "") -> dict:
        """Snapshot-forward migration: continue an older campaign on this engine from its latest state.

        Everything up to the migration point stays canon exactly as it happened (the old commands,
        events, charts and packets are untouched). From the migration point the world runs on this
        engine's rules and parameters. A checkpoint of the migrated state is stored so that replay
        can verify every later command; earlier commands remain verifiable on the original engine."""
        path = Path(path)
        store = Store(path / "campaign.sqlite")
        saved = store.get_meta("engine_version", "0.1.0")
        if _minor(saved) == _minor(ENGINE_VERSION):
            store.close()
            return {"status": "noop", "reason": f"already on engine {saved}"}
        date, old_hash, doc, blob = store.read_snapshot()
        old_cfg = stable_hash(doc.get("config_tree", {}))
        scenario = store.get_meta("scenario")
        doc["config_tree"] = make_config(scenario).tree
        flags = doc.setdefault("flags", {})
        flags.setdefault("wellbeing_from", date)
        seq = len(store.commands())
        flags.setdefault("migrations", []).append({"from": saved, "to": ENGINE_VERSION, "date": date, "seq": seq,
                                                   "old_state_hash": old_hash, "old_config_hash": old_cfg,
                                                   "note": note})
        _backfill_development(store, doc)
        world = World.from_state(doc, blob_to_arrays(blob))
        c = cls(path, store, world)
        doc2, arrays = world.to_state()
        h = world.state_hash()
        blob2 = arrays_to_blob(arrays)
        store.write_snapshot(world.date.isoformat(), h, doc2, blob2)
        store.write_checkpoint(seq, ENGINE_VERSION, world.date.isoformat(), h, doc2, blob2)
        history = store.get_meta("engine_history", [{"version": saved, "from_seq": 0}])
        history.append({"version": ENGINE_VERSION, "from_seq": seq, "date": date})
        store.set_meta("engine_history", history)
        store.set_meta("engine_version", ENGINE_VERSION)
        store.append_command(seq, date, "migrate", {"from": saved, "to": ENGINE_VERSION, "note": note},
                             {"old_state_hash": old_hash, "old_config_hash": old_cfg}, h)
        store.commit()
        c.close()
        return {"status": "migrated", "from": saved, "to": ENGINE_VERSION, "at_seq": seq, "date": date,
                "old_state_hash": old_hash, "new_state_hash": h}

    def close(self):
        self.store.close()

    # ------------------------------------------------------------ persistence
    def _flush(self):
        w = self.world
        self.store.append_events(w.events.drain())
        if w.chart_log:
            self.store.append_chart_runs(w.chart_log)
            w.chart_log = []
        if w.week_log:
            self.store.append_song_weeks(w.week_log)
            w.week_log = []

    def _save(self) -> str:
        self._flush()
        doc, arrays = self.world.to_state()
        h = self.world.state_hash()
        self.store.write_snapshot(self.world.date.isoformat(), h, doc, arrays_to_blob(arrays))
        self.store.commit()
        return h

    def _log(self, kind: str, payload: dict, result: dict):
        h = self._save()
        seq = len(self.store.commands())
        self.store.append_command(seq, self.world.date.isoformat(), kind, payload, result, h)
        self.store.commit()
        return h

    # ------------------------------------------------------------ play
    def last_packet(self) -> dict | None:
        return self.store.read_pass()

    def make_packet(self) -> dict:
        prev = self.store.read_pass()
        since = prev["date"] if prev else None
        self._flush()
        pk = packet_mod.build(self.world, self.store, self.id, since)
        self.store.write_pass(self.world.pass_no, pk["date"], pk)
        d = self.path / "packets"
        d.mkdir(parents=True, exist_ok=True)
        stem = f"pass_{self.world.pass_no:04d}"
        (d / f"{stem}.md").write_text(packet_mod.to_markdown(pk), encoding="utf-8")
        (d / f"{stem}.json").write_text(json.dumps(pk, indent=1, default=str), encoding="utf-8")
        self._save()
        return pk

    def packet_path(self) -> Path:
        return self.path / "packets" / f"pass_{self.world.pass_no:04d}.md"

    def submit(self, payload: dict, check_pass: bool = True) -> dict:
        """Apply decisions and proposals, optionally advance time, and produce the next packet."""
        report = {"decisions": [], "proposals": [], "advance": None}
        errs = validate_submission(self.world, payload, self.last_packet() if check_pass else None)
        if errs:
            return {"status": "invalid", "errors": errs}
        base = len(self.store.commands()) * 100
        dec, pro = apply_submission(self.world, payload, base)
        report["decisions"], report["proposals"] = dec, pro
        adv = payload.get("advance")
        if adv:
            report["advance"] = self._advance(advance_days(adv))
        self._log("submit", payload, report)
        report["packet"] = str(self.make_packet_logged())
        return report

    def _advance(self, days: int) -> dict:
        res = sim_advance(self.world, days, stop_on_interrupt=True)
        return res

    def advance(self, duration: str | None) -> dict:
        spec = duration or "next"
        res = self._advance(advance_days(spec))
        self._log("advance", {"duration": spec}, res)
        res["packet"] = str(self.make_packet_logged())
        return res

    def make_packet_logged(self) -> Path:
        self.make_packet()
        self._log("packet", {}, {"pass_no": self.world.pass_no})
        return self.packet_path()

    # ------------------------------------------------------------ replay
    def replay(self) -> dict:
        """Rebuild the campaign from scenario + seed + command log and compare state hashes."""
        scenario = self.store.get_meta("scenario")
        ch = self.store.get_meta("character")
        seed = self.store.get_meta("seed")
        log = self.store.commands()
        migrations = [e for e in log if e["kind"] == "migrate"]
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / "replay.sqlite")
            verified_from = "scenario + seed"
            if migrations:
                m = migrations[-1]
                cp = self.store.read_checkpoint(m["seq"])
                world = World.from_state(cp["doc"], blob_to_arrays(cp["arrays"]))
                prev = self.store.read_pass(world.pass_no)
                if prev:
                    store.write_pass(world.pass_no, prev["date"], prev)
                log = [e for e in log if e["seq"] > m["seq"]]
                verified_from = f"migration checkpoint at command {m['seq']} (engine {m['payload']['to']})"
            else:
                world = build_world(scenario, seed, ch)
            c = Campaign(Path(tmp) / self.id, store, world)
            c.path = Path(tmp) / self.id
            mismatches = []
            checked = 0
            for entry in log:
                kind, payload = entry["kind"], entry["payload"]
                if kind == "create":
                    c.make_packet()
                elif kind == "submit":
                    apply_submission(world, payload, entry["seq"] * 100)
                    if payload.get("advance"):
                        sim_advance(world, advance_days(payload["advance"]), stop_on_interrupt=True)
                elif kind == "advance":
                    sim_advance(world, advance_days(payload["duration"]), stop_on_interrupt=True)
                elif kind == "packet":
                    c.make_packet()
                c._flush()
                h = world.state_hash()
                checked += 1
                if h != entry["state_hash"]:
                    mismatches.append({"seq": entry["seq"], "kind": kind, "expected": entry["state_hash"], "got": h})
                    break
            store.close()
        return {"commands": len(log), "checked": checked, "ok": not mismatches, "mismatches": mismatches,
                "verified_from": verified_from, "outcome_hash": self.world.outcome_hash()}


def _backfill_development(store, doc):
    """Carry the label's memory of earlier single reviews into the migrated state (from the event log)."""
    act = doc.get("player", {}).get("act")
    if not act or "development" in doc["flags"]:
        return
    revs = [e for e in store.events_for(act, limit=500) if e["type"] == "single_review"]
    passed = [e for e in revs if e["data"].get("approve") is False or
              ("observed_quality" in e["data"] and e["data"]["observed_quality"] < 0.45)]
    if not passed:
        return
    last = max(passed, key=lambda e: e["id"])
    rid = next((x for x in last["entities"] if x.startswith("rec:")), None)
    title = doc["recordings"].get(rid, {}).get("title", rid)
    doc["flags"]["development"] = {"rejections": len(passed), "last_review": {
        "recording": rid, "title": title, "date": last["date"], "strengths": [], "weaknesses": [],
        "fit": ["(reviewed by the earlier engine, which recorded only an overall score)"], "remedies": [],
        "score": last["data"].get("observed_quality"), "threshold": 0.45}}


def apply_submission(world, payload: dict, base: int):
    """Creative briefs first (they shape this pass's sessions), then decisions, then other proposals."""
    proposals = list(enumerate(payload.get("proposals", []) or []))
    briefs = [(k, p) for k, p in proposals if p.get("type") == "creative_brief"]
    others = [(k, p) for k, p in proposals if p.get("type") != "creative_brief"]
    pro = {}
    for k, p in briefs:
        pro[k] = {"type": p.get("type"), **props.resolve(world, p, base + k)}
    dec = []
    for d in payload.get("decisions", []) or []:
        res = cmds.apply(world, d)
        dec.append({"command": d.get("command"), **res})
        world.emit("player", "decision", [world.player["act"]], {"command": d.get("command"), "args": d.get("args"),
                                                                 "result": res.get("status"),
                                                                 "detail": res.get("summary") or res.get("reason")})
    for k, p in others:
        pro[k] = {"type": p.get("type"), **props.resolve(world, p, base + k)}
    return dec, [pro[k] for k in sorted(pro)]


def validate_submission(world, payload, last_packet) -> list[str]:
    errs = []
    if not isinstance(payload, dict):
        return ["submission must be a JSON object"]
    allowed = {"pass_id", "decisions", "proposals", "advance", "notes"}
    errs += [f"unexpected top-level field '{k}'" for k in payload if k not in allowed]
    if last_packet is not None and payload.get("pass_id") != last_packet.get("pass_id"):
        errs.append(f"pass_id {payload.get('pass_id')!r} does not match the current pass "
                    f"{last_packet.get('pass_id')!r} (stale or missing)")
    for d in payload.get("decisions", []) or []:
        errs += cmds.validate(world, d)
    for p in payload.get("proposals", []) or []:
        errs += props.validate(world, p)
    if payload.get("advance"):
        try:
            advance_days(payload["advance"])
        except ValueError as e:
            errs.append(f"advance: {e} (or use \"next\")")
    return errs


_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def parse_submission_text(text: str) -> dict:
    """Accept raw JSON or a narrator reply containing a fenced ```json block (the last one wins)."""
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)
    blocks = _FENCE.findall(text)
    if not blocks:
        raise ValueError("no JSON object or ```json block found")
    return json.loads(blocks[-1])

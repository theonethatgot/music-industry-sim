"""Checkpointed GitHub Actions bridge for the Danielle career playtest.

The ordered JSON turn files are the canonical save.  GitHub Actions caches a
rebuildable SQLite checkpoint for speed; never rely on cache retention for
permanent storage.  Restore only checkpoints whose engine fingerprint, turn
prefix, SQLite checksum and snapshot hash all match.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import time
from pathlib import Path

from musicsim.campaign_io import Campaign, data_version

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "gameplay" / "danielle"
TURNS = BASE / "turns"
OUT = BASE / "output"
CACHE = ROOT / ".bridge_cache"
SAVE = CACHE / "session1"
DB = SAVE / "campaign.sqlite"
MANIFEST = CACHE / "manifest.json"
SCENARIO = "us_1988_aspiring"
SEED = 1988
ORIGINAL_SESSION_HASH = "e3076df5dc16af509ffb"
ORIGINAL_DATA_VERSION = "3763906a35ea9667"
CHECKPOINT_SCHEMA = 2
FULL_REPLAY_INTERVAL = 5
TURN_NAME = re.compile(r"^[0-9]{4}\.json$")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def engine_fingerprint() -> str:
    files = [*sorted((ROOT / "musicsim").rglob("*.py")),
             *sorted((ROOT / "data").rglob("*.yaml")),
             ROOT / "bridge" / "requirements-lock.txt"]
    h = hashlib.sha256()
    for path in files:
        h.update(str(path.relative_to(ROOT)).encode())
        h.update(bytes.fromhex(digest(path)))
    return h.hexdigest()


def turns() -> tuple[list[Path], list[str]]:
    paths = sorted(TURNS.glob("*.json"))
    bad = [p.name for p in TURNS.iterdir()
           if p.is_file() and not TURN_NAME.fullmatch(p.name)]
    if bad:
        raise ValueError(f"Unexpected turn filenames: {bad}")
    for i, path in enumerate(paths, 1):
        if path.name != f"{i:04d}.json":
            raise ValueError(f"Turn files must be sequential: expected {i:04d}.json, got {path.name}")
    return paths, [digest(p) for p in paths]


def sqlite_ok() -> bool:
    if not DB.is_file():
        return False
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as connection:
        return connection.execute("PRAGMA quick_check").fetchone() == ("ok",)


def restore_checkpoint(input_hashes: list[str], fingerprint: str):
    if not MANIFEST.is_file() or not DB.is_file():
        return None
    try:
        meta = json.loads(MANIFEST.read_text(encoding="utf-8"))
        n = meta["turn_count"]
        if (meta.get("schema") != CHECKPOINT_SCHEMA
                or meta.get("engine_fingerprint") != fingerprint
                or not isinstance(n, int) or n < 0 or n > len(input_hashes)
                or meta.get("input_hashes") != input_hashes[:n]
                or digest(DB) != meta.get("sqlite_sha256")
                or not sqlite_ok()):
            return None
        camp = Campaign.open(SAVE)
        try:
            if (camp.store.get_meta("seed") != SEED
                    or camp.store.get_meta("data_version") != ORIGINAL_DATA_VERSION
                    or camp.world.state_hash() != meta["state_hash"]
                    or camp.last_packet()["pass_id"] != meta["pass_id"]
                    or len(camp.store.commands()) != 1 + 2 * n):
                camp.close()
                return None
            return camp, meta
        except Exception:
            camp.close()
            raise
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError) as exc:
        print(f"Checkpoint rejected ({type(exc).__name__}); rebuilding from canonical turns.", flush=True)
        return None


def create_from_seed():
    if SAVE.exists():
        shutil.rmtree(SAVE)
    MANIFEST.unlink(missing_ok=True)
    camp = Campaign.create(SAVE, SCENARIO, SEED)
    original = json.loads(
        (ROOT / "playtests" / "session1" / "packets" / "pass_0001.json").read_text(encoding="utf-8")
    )
    if camp.last_packet() != original:
        camp.close()
        raise ValueError("Starting narrator packet differs from the original authoritative playtest")
    if data_version() != ORIGINAL_DATA_VERSION:
        camp.close()
        raise ValueError("Historical data changed: do not silently rewrite Danielle's campaign")
    return camp


def main() -> None:
    start = time.perf_counter()
    paths, input_hashes = turns()
    fingerprint = engine_fingerprint()
    restored = restore_checkpoint(input_hashes, fingerprint)
    if restored is None:
        camp = create_from_seed()
        old_count = 0
        previous_results = []
        start_hash = camp.world.state_hash()
        last_replay_turn = -1
        last_replay = None
        mode = "full_rebuild"
    else:
        camp, meta = restored
        old_count = meta["turn_count"]
        previous_results = list(meta["turn_results"])
        start_hash = meta["start_hash"]
        last_replay_turn = meta.get("last_full_replay_turn", -1)
        last_replay = meta.get("last_full_replay")
        mode = "checkpoint_resume"
        print(f"Restored verified checkpoint at turn {old_count}; applying {len(paths) - old_count} new turn(s).", flush=True)

    results = previous_results
    try:
        for path in paths[old_count:]:
            payload = json.loads(path.read_text(encoding="utf-8"))
            report = camp.submit(payload)
            if report.get("status") == "invalid":
                raise ValueError(f"{path.name}: rejected submission: {report['errors']}")
            unexpected = [item for item in report["decisions"]
                          if item.get("status") not in ("accepted", "rejected")]
            unexpected += [item for item in report["proposals"]
                           if item.get("status") not in ("accepted", "rejected")]
            if unexpected:
                raise ValueError(f"{path.name}: unexpected command result: {unexpected}")
            report["packet"] = Path(report["packet"]).name
            results.append({"turn": path.name, "report": report})

        full_replay = mode == "full_rebuild" or len(paths) - last_replay_turn >= FULL_REPLAY_INTERVAL
        if full_replay:
            check = camp.replay()
            if not check.get("ok"):
                raise RuntimeError(f"Full deterministic replay failed: {check}")
            last_replay = check
            last_replay_turn = len(paths)
            print(f"Full replay passed for {check['checked']} logged commands.", flush=True)

        packet = camp.packet_path().read_text(encoding="utf-8")
        state_hash = camp.world.state_hash()
        pass_id = camp.last_packet()["pass_id"]
        current_date = camp.world.date.isoformat()
        if not sqlite_ok():
            raise RuntimeError("SQLite quick_check failed")
        status = {
            "campaign": "session1",
            "scenario": SCENARIO,
            "seed": SEED,
            "start_hash": start_hash,
            "original_session_hash": ORIGINAL_SESSION_HASH,
            "data_version": camp.store.get_meta("data_version"),
            "turn_count": len(paths),
            "in_world_date": current_date,
            "pass_id": pass_id,
            "state_hash": state_hash,
            "replay": last_replay,
            "verification": {
                "mode": mode,
                "resumed_after_turn": old_count,
                "new_turns_applied": len(paths) - old_count,
                "full_replay_performed": full_replay,
                "last_full_replay_turn": last_replay_turn,
                "sqlite_quick_check": "ok",
                "elapsed_seconds": round(time.perf_counter() - start, 2),
            },
            "turn_results": results,
        }
    finally:
        camp.close()

    # Cache is disposable; canonical turn inputs and the output packet remain in Git.
    CACHE.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "schema": CHECKPOINT_SCHEMA,
        "engine_fingerprint": fingerprint,
        "input_hashes": input_hashes,
        "turn_count": len(paths),
        "start_hash": start_hash,
        "pass_id": pass_id,
        "state_hash": state_hash,
        "sqlite_sha256": digest(DB),
        "last_full_replay_turn": last_replay_turn,
        "last_full_replay": last_replay,
        "turn_results": results,
    }
    MANIFEST.write_text(json.dumps(checkpoint, indent=2) + "\n", encoding="utf-8")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest_packet.md").write_text(packet, encoding="utf-8")
    (OUT / "status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    print(f"{mode}: turn {len(paths)}, {pass_id} at {current_date}; "
          f"full replay this run={full_replay}; elapsed={status['verification']['elapsed_seconds']}s", flush=True)


if __name__ == "__main__":
    main()

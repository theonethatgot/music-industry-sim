"""Deterministic, isolated GitHub Actions bridge for Danielle's music campaign.

The canonical save is the ordered JSON input in gameplay/danielle/turns/.
Each workflow job recreates the exact world from seed 1988 and replays those
inputs. SQLite remains temporary; the newest narrator packet is committed.
"""
from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

from musicsim.campaign_io import Campaign

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "gameplay" / "danielle"
TURNS = BASE / "turns"
OUT = BASE / "output"
SCENARIO = "us_1988_aspiring"
SEED = 1988
EXPECTED_START_HASH = "e3076df5dc16af509ffb"
NAME_PATTERN = re.compile(r"^[0-9]{4}\.json$")


def main() -> None:
    paths = sorted(TURNS.glob("*.json"))
    bad = [p.name for p in TURNS.iterdir() if p.is_file() and not NAME_PATTERN.fullmatch(p.name)]
    if bad:
        raise ValueError(f"Invalid turn filenames: {bad}")
    for index, path in enumerate(paths, 1):
        if path.name != f"{index:04d}.json":
            raise ValueError(f"Turn inputs must be consecutively numbered: expected {index:04d}.json, got {path.name}")

    with tempfile.TemporaryDirectory() as temp:
        camp = Campaign.create(Path(temp) / "session1", SCENARIO, SEED)
        try:
            initial_hash = camp.world.state_hash()
            if initial_hash != EXPECTED_START_HASH:
                original = json.loads((ROOT / "playtests/session1/packets/pass_0001.json").read_text(encoding="utf-8"))
                regenerated = camp.last_packet()
                changed = [key for key in sorted(set(original) | set(regenerated)) if original.get(key) != regenerated.get(key)]
                print(f"Original data version: 3763906a35ea9667; regenerated: {camp.store.get_meta('data_version')}", flush=True)
                print(f"Initial packet sections that differ: {changed}", flush=True)
                for key in changed[:6]:
                    old, new = original.get(key), regenerated.get(key)
                    if isinstance(old, dict) and isinstance(new, dict):
                        subkeys = [k for k in set(old) | set(new) if old.get(k) != new.get(k)]
                        print(f"Section {key} different subkeys: {subkeys[:20]}", flush=True)
                    else:
                        print(f"Section {key}: old={str(old)[:160]} new={str(new)[:160]}", flush=True)
                raise ValueError(f"Engine/data mismatch: initial hash {initial_hash} != {EXPECTED_START_HASH}; do not overwrite the campaign")
            results = []
            for path in paths:
                payload = json.loads(path.read_text(encoding="utf-8"))
                report = camp.submit(payload)
                if report.get("status") == "invalid":
                    raise ValueError(f"{path.name}: submission rejected: {report['errors']}")
                rejected = [item for item in report["decisions"] if item.get("status") not in ("accepted",)]
                if rejected:
                    raise ValueError(f"{path.name}: decision did not complete: {rejected}")
                results.append({"turn": path.name, "report": report})
            replay = camp.replay()
            if not replay.get("ok"):
                raise RuntimeError(f"Deterministic replay mismatch: {replay}")
            packet = camp.packet_path().read_text(encoding="utf-8")
            state_hash = camp.world.state_hash()
            status = {
                "campaign": "session1",
                "scenario": SCENARIO,
                "seed": SEED,
                "start_hash": initial_hash,
                "data_version": camp.store.get_meta("data_version"),
                "turn_count": len(paths),
                "in_world_date": camp.world.date.isoformat(),
                "pass_id": camp.last_packet()["pass_id"],
                "state_hash": state_hash,
                "replay": replay,
                "turn_results": results,
            }
        finally:
            camp.close()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest_packet.md").write_text(packet, encoding="utf-8")
    (OUT / "status.json").write_text(json.dumps(status, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Validated {len(paths)} turns; {status['pass_id']} at {status['in_world_date']}; replay OK")


if __name__ == "__main__":
    main()

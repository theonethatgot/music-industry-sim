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
ORIGINAL_SESSION_HASH = "e3076df5dc16af509ffb"
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
            original = json.loads((ROOT / "playtests/session1/packets/pass_0001.json").read_text(encoding="utf-8"))
            if camp.last_packet() != original:
                raise ValueError("Regenerated starting packet differs from the saved authoritative session1 packet")
            if camp.store.get_meta("data_version") != "3763906a35ea9667":
                raise ValueError("Historical data version has changed; do not rewrite campaign history")
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
                "original_session_hash": ORIGINAL_SESSION_HASH,
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

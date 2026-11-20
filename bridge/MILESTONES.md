# Danielle playtest: milestone-mode operating rules

## Campaign authority

The canonical save is the ordered JSON turn history in `gameplay/danielle/turns/`, starting at `0001.json`. Never rewrite previous turns. The latest narrator packet is `gameplay/danielle/output/latest_packet.md`; current verification data is in `gameplay/danielle/output/status.json`.

The SQLite database in `.bridge_cache/` is a **disposable performance checkpoint**, not permanent storage. A checkpoint must match the exact engine version, input-command prefix, SQLite checksum, snapshot state hash, packet ID, and expected number of log entries. Otherwise the bridge rebuilds from seed 1988 and the JSON turn history. GitHub Actions caches can be evicted at any time.

The runner pins Python's hash seed and its dependency versions. A cold rebuild performs full deterministic replay. Subsequent checkpoint-based turns perform an additional full replay after every five new turns; interim runs validate the saved SQLite snapshot instead. The status report must distinguish the two.

## Milestone pacing

Advance to the next **consequential** event, not the next arbitrary calendar day: a finished master, label decision, offer deadline, release, chart debut, or commercial review. When nothing major is imminent, use `advance: "2w"`, `"3w"`, `"4w"`, or `"next"` so the engine can interrupt at relevant developments.

Use short 1–3-day advances only for an imminent deadline or another exceptional reason. Bundle routine, already-authorized actions into one command submission rather than requiring separate ChatGPT turns for each rehearsal or booking.

The engine decides financial, chart, and industry outcomes. Never automatically sign contracts, spend large budgets, choose releases, or accept consequential offers without authorization. Never skip an unresolved player decision. Narrate meaningful stretches in coherent scenes rather than a mechanical diary of every week.

## Initial test-cycle exit condition

Continue through Danielle's debut-single production, label approval, release, and first credible commercial reception. Then stop for a focused playtest findings report.

Known engineering issues to report separately to Claude: weeks of automatic rest have not visibly improved energy; rest and gig obligations overlap; changing standing policies does not cancel prior bookings; recording completion triggered after the scheduled final day. Do not silently change the engine on the gameplay branch to conceal them.

## Operational limitations

GitHub Actions has cold-start delays and is not an always-on server. Cache expiry only affects speed; the committed command history is the durable save. A failed run must be diagnosed from its job log, not treated as completed.

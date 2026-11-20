# Danielle playtest: milestone-mode operating rules

## Campaign authority

The canonical save is the ordered JSON turn history in `gameplay/danielle/turns/`, starting at `0001.json`. Never rewrite previous turns. The latest narrator packet is `gameplay/danielle/output/latest_packet.md`; current verification data is in `gameplay/danielle/output/status.json`.

The SQLite database in `.bridge_cache/` is a **disposable performance checkpoint**, not permanent storage. A checkpoint must match the exact engine version, input-command prefix, SQLite checksum, snapshot state hash, packet ID, and expected number of log entries. Otherwise the bridge rebuilds from seed 1988 and the JSON turn history. GitHub Actions caches can be evicted at any time.

The runner pins Python's hash seed and its dependency versions. A cold rebuild performs full deterministic replay. Subsequent checkpoint-based turns perform an additional full replay after every five new turns; interim runs validate the saved SQLite snapshot instead. The status report must distinguish the two.

## Playtest pacing: long, substantive passes

This phase is a **systems playtest**, not a chapter-by-chapter roleplay. Aim for a **single user-facing report spanning approximately 2–4 simulated months**, or longer when the artist's career has no consequential decisions. A major recording/release/promotion/chart cycle can constitute a single pass.

Distinguish **internal engine steps** from the **player-facing pass**. The engine may interrupt after a few days or weeks for recording completion, exhaustion or other events. When no player approval is necessary, process these stops internally and continue rather than printing a new full reply after each one. Bundle routine decisions into the established delegation policies and follow through autonomously when authorized. Never invent outcomes or silently skip an actual consequential decision.

Use `advance: "next"` (up to the engine cap) or `"8w"` / `"12w"` when appropriate. If the engine stops early, continue with the next valid command after examining the returned packet. **Do not bypass** label approvals, unapproved spending, contracts, release selections or other matters reserved for the player. If a material approval is required, end the report there with a specific recommendation instead of padding out fictional time.

Avoid wasteful micro-passes for a rehearsal, recording finishing one day late, or a routine workweek. The playtest must move through months of genuine career development and **commercial outcomes**, not consume the user's time proving the workflow works.

## Playtest presentation: concise and diagnostic

While in test mode, **do not produce theatrical roleplay scenes, dramatic reconstructed conversations, stock imagery, decorated cards, repeated status grids, sprawling chart tables, or redundant JSON blocks**. Those belong to immersive gameplay after testing. Speak plainly to the player as a simulation tester.

For each long pass, report only:
1. **Dates covered / substantive milestones** — contractual, creative, promotional and commercial actions/results, from the verified engine packet.
2. **Concrete outcomes** — recording strengths/weaknesses, label decisions, promotion, audience response, charts, sales/royalties and finances where provided; say explicitly when unknown.
3. **Engineering observations** — reproducible bugs, weird outcomes or balance concerns; separate genuinely observed problems from hypotheses; avoid claiming a simulated result is proof of a design failure.
4. **Next major decision** — one consolidated recommendation or ask only when consequential authorization is required.

Keep a normal pass to about **150–350 words** unless substantial verified developments warrant more. Prefer compact paragraphs and at most one small table if it genuinely helps. No manufactured cheerleading about the bridge; mention successful checkpoint/replay only briefly, and distinguish a validated checkpoint from a fresh full replay.

If the player explicitly switches back to immersive roleplay, reinstate detailed scenes and lived-in dialogue under the narrator contract. Until then, **testing mode overrides storytelling presentation**, but not engine truth or player control.

## Initial test-cycle exit condition

Continue through Danielle's debut-single production, label approval, release, and first credible commercial reception. Then stop for a focused playtest findings report.

Known engineering issues to report separately to Claude: weeks of automatic rest have not visibly improved energy; rest and gig obligations overlap; changing standing policies does not cancel prior bookings; recording completion triggered after the scheduled final day. Do not silently change the engine on the gameplay branch to conceal them.

## Operational limitations

GitHub Actions has cold-start delays and is not an always-on server. Cache expiry only affects speed; the committed command history is the durable save. A failed run must be diagnosed from its job log, not treated as completed.

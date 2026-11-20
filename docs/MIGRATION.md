# Save compatibility and migration (engine 0.1 → 0.4)

## What changed
Engine 0.4 fixes the Danielle playtest issues: weekly wellbeing and routine-work accounting, protected
rest, the A&R review (craft **and** commercial potential), label development meetings and patience,
manager follow-up, and regional-vs-national radio bookkeeping. These change outcomes. Replaying an
0.1 command history on 0.4 produces a **different** world. For example, replaying Danielle's turns
0001–0014 diverges at the showcase in turn 1 because she is no longer exhausted, Sire's offer never
appears, and later turns refer to ids that don't exist.

So 0.1 saves are **not** silently re-simulated. `Campaign.open` refuses a save stamped with another
minor version and points to the options below.

## Options for an existing campaign

1. **Keep it on engine 0.1 (default).** The canonical history (e.g. `gameplay/danielle/turns/*.json`) stays
   valid on the engine it was played with: commit `882454c`, data version `3763906a35ea9667`. The
   checkpoint bridge already pins this through its engine fingerprint and data-version checks, and will
   (correctly) refuse to rebuild on 0.4.
2. **Snapshot-forward migration (continue the same story on 0.4).**
   `python -m musicsim migrate <campaign> --note "…"`
   - Loads the campaign's **latest** snapshot. Nothing before it is re-simulated or rewritten. Commands,
     events, charts and packets stay exactly as they happened, so every past outcome remains canon (for
     Danielle, Sire's rejection of "Wild Dance" on 1988-12-15 and the 84 quiet days to 1989-03-09).
   - Replaces the saved parameter tree with 0.4's (recorded: old config hash, old state hash).
   - Backfills the label's memory of earlier single rejections from the event log, so the new development
     system knows about them.
   - Stores a **checkpoint** of the migrated state and appends a `migrate` command. `replay` then verifies
     every later command from that checkpoint. Commands before it remain verifiable only on engine 0.1.
   - Records the change in the meta `engine_history` and in `world.flags.migrations`.
3. **Start a new validation campaign on 0.4** (recommended for evaluating the new rules from day one).

## Recommended plan for Danielle
- Don't touch `chatgpt/danielle-playtest` turns 0001–0014 or their checkpoint. They remain the 0.1 record.
- If the story should continue under 0.4: rebuild the 0.1 save from turns 0001–0014 on engine 0.1
  (commit `882454c`), copy it, run `migrate` on the copy, then continue with turn 0015 onwards against the
  migrated copy. The bridge needs a matching update: an explicit migration step after turn 14, and the
  engine fingerprint/data-version checks split into "0.1 prefix" and "0.4 continuation". That bridge
  change belongs on the gameplay branch and is not made here.
- Verified in this engineering pass: migrating the rebuilt 1989-03-09 save and continuing works. Replay
  from the migration checkpoint matches (see `docs/QA_REPORT_v0.4.md`).

## Reproducibility notes
- Python hash seeding is **not** a factor. Campaign creation gives the same state hash under different
  `PYTHONHASHSEED` values and working directories.
- The exact `state_hash` is bitwise and depends on NumPy's floating-point results, which can differ in
  the last bit across CPUs and NumPy builds (vectorised `exp`/`log`). That explains why the GitHub runner's
  start hash differed from the original session's while the packets were identical. Pin NumPy (the bridge
  does) and replay on the same platform for exact verification. Engine 0.4 records the runtime (Python,
  NumPy, machine) in campaign meta and offers `World.outcome_hash()`, a fingerprint with floats rounded to
  ~6 significant digits, for cross-machine comparison.

# QA report — engine 0.4 (Danielle Reyes playtest fixes)

Handoff: `chatgpt/danielle-playtest:playtests/DANIELLE_ENGINE_FIX_HANDOFF_1988_1989.md`.
Engineering branch: `claude/vibrant-clarke-hrzk96`. Gameplay history was not modified.

## 1. Reproduction (engine 0.1, commit 882454c)

Turns 0001–0014 rebuilt from the canonical turn files (seed 1988, NumPy 2.4.6 as pinned by the bridge,
and 2.5.3) reproduce every reported result. Sire signs on 1988-10-04 and three masters are finished.
"Wild Dance" is rejected on 1988-12-15. The same submission advances 84 days to 1989-03-09 with no
interrupts. Energy is "very low" from late September onwards.

**Hash mismatch.** This isn't Python hash seeding: campaign creation gives `e3076df…` under every
`PYTHONHASHSEED` and working directory tried, on both NumPy 2.4.6 and 2.5.3. The runner's `d858ca…`
comes from last-bit floating-point differences between CPUs and NumPy builds (vectorised
transcendental functions); turn outcomes were identical. Mitigations: runtime fingerprint in campaign
meta, and `World.outcome_hash()` for cross-machine comparison (§6).

## 2. Root causes and fixes

| Item | Root cause (confirmed) | Fix | Tests |
|---|---|---|---|
| P0 rest doesn't restore energy | Monday tick read only commitments active on Monday, so a rest booked on a Monday had ended (`done`) by the next tick and was never credited. The day-job load still applied, so energy kept falling. | `player/wellbeing.py` accounts for the **week just elapsed, day by day**, including finished commitments. Energy and stress relax toward a target set by that day's workload (day job, club nights, lessons, studio, tours, nonlinear overload; rest days have a higher target and rate). Rest news reports the measured change. Exhaustion lowers stage and vocal fitness. | `test_recovery.py`: 3-week recovery, day job on vs off, no no-op rest reports |
| P1 rest doesn't clear the calendar | `_cmd_rest` checked only exclusive commitments, and the news claimed "cleared the calendar" regardless | Rest is **protected time off**. Club dates and lessons inside it are cancelled and resume afterwards, at a small cost in booker goodwill and buzz. Rest is refused during a studio session; auto-rest is booked after it instead. Lessons, club dates, manager-booked shows and narrator gig offers are refused during rest. `cancel_bookings` command. `set_policy` says existing bookings are kept. News states exactly what was cancelled. | cancellation and resume; no gig income for the rest week; refusals; manager never books during rest; cancel and policy wording |
| P1 84-day silent stall after a veto | A rejection raised no interrupt or follow-up. Labels only managed already-released singles. Managers had nothing to do for a signed client with no single. | `systems/development.py`. On a pass: A&R notes (strengths, worries, fit, suggested remedy) and a **development meeting** 6–11 days later that stops the advance. At the meeting the label re-hears all unreleased masters and proposes a release, **remix** (named producer, fee and studio from the recording fund, recoupable), **re-cut vocal**, or songs from its writers. Proposals are `offer:` ids the player must accept. Further check-ins every 8 weeks while nothing moves; none while a single is in its run. Patience warning, then a possible drop (generated NPC acts face the same). Managers press stalled labels for meetings and bring songs, spending nobody's money. | `test_development.py`: meeting within 12 days, no stretch over 70 days, proposals never auto-executed, remix → real session → new release decision, strong master approved, manager initiative, warning → drop, NPCs reviewed |
| P2 hook/commercial blind spot | `craft_score` ignored hook, signature, singability, groove and format fit | One review for **every** act: observed craft + commercial potential (weighted by label culture), label genre focus, track record; label-size strictness and risk leniency | `test_review_values_commercial_signals_not_just_craft`, `test_npc_acts_face_the_same_review` |
| P2 completion dates | (by design) | Session summaries say "sessions through D; the finished master is in hand the next morning" | — |

Further realism fixes found while testing:
- **Radio bookkeeping.** A record held regionally was counted as nationally playlisted, causing a weekly
  add/drop cycle.
- **Label spacing.** Labels now space an act's singles about 11 weeks apart.
- **Scouting.** A&R scouting now includes the protagonist; selling independent records get noticed.
- **Distribution.** Self-released records have limited independent distribution.
- **Generated field: 480 → 1,400 acts.** With 480 the world released only ~116 singles a year and almost
  every single charted (39% Top-10). See §4.

## 3. A&R review calibration (`tools/label_calibration.py`)

**Part A** samples 3,000 synthetic masters across labels, genres, career stages, writer and producer
skill, and budgets.

| | Approval |
|---|---|
| Overall | 70% |
| New acts / mid-career / established | 51% / 72% / 85% |
| Small / mid / big labels | 78% / 68% / 61% |
| Off-focus / in-focus / core genre | 64% / 83% / 93% |
| Hook low + craft low | 36% |
| Hook low + craft high | 75% |
| Hook **high** + craft **low** | 71% (was undervalued before the commercial weighting) |
| Hook high + craft high | 95% |

**Part B** runs whole worlds (2 seeds × 36 weeks, 1,400 acts, 806 singles) in study mode: every
generated single is released at standard promotion, whatever the verdict.

| | Approved (n=494) | Vetoed but released (n=312) |
|---|---|---|
| Median units | 129k | 53k |
| Reached Top 40 | 24.7% | 9.3% |
| Reached Top 10 | 9.9% | 2.2% |
| Charted at all | 47% | 22% |

The verdict is informative but not a promise. 29 vetoed records still reached the Top 40, and 260
approved records missed the Hot 100. In outcomes, commercial potential predicts sales far more than
craft does (log-units regression coefficients 5.1 vs 0.7), which supports the handoff's hypothesis.
Parameters: `development.threshold 0.575`, `commercial_weight 0.68`.

## 4. Multi-seed career continuity (`tools/career_continuity.py`, 52 weeks)

31 first-year careers on the default 1988 scenario with scripted players:
- **Engaged** (13 seeds incl. 1988): takes contracts, records, submits singles, accepts label proposals.
- **Passive** (6): never decides.
- **Overworked** (6): day job, max club nights, lessons, back-to-back sessions.
- **Recovering** (6): starts at Danielle-like exhaustion and relies on standing orders.

| Check | Result |
|---|---|
| Longest gap between player-facing events while **signed** | 21–70 days (median 45); **no 84-day empty block** in any engaged run |
| Development meetings / label passes / proposals (engaged) | Present in 9/13 runs (meetings 0–3; passes 0–2 per run) |
| Recovery from exhaustion (recovering) | All 6 recover in one protected week: +0.40 energy, very-low streak ≤ 1 day, **0 rests without recovery** |
| Overworked | Settles at energy 0.26 ("low"), just above the 0.25 auto-rest threshold; chronic tiredness without collapse (see §7) |
| Passive | The world moves (showcase offers arrive); the protagonist stays unsigned because they never answer. Unsigned and idle, gaps reach 84 days, the `next` cap. |
| Engaged outcomes | Signed in 13/13 (within 2–16 weeks). Best Hot 100 peak per career: 2, 3, 4, 4, 5, 9, 14, 18, 19, 24, 30, 46, 53 (no #1s). Recognition 25–71%. Royalty accounts from −$281k to +$105k. |
| Seed 1988 regression (engaged bot, engine 0.4) | Signs with Sire 1988-11-21, first single 1989-02-27, best peak #3 |
| Real save path | Seeds 1988 and 1 run through `Campaign` with full persistence for 26 weeks; `replay` OK on both |

## 5. Danielle: migration and continuation (§2 of the handoff, items 3 and 5)

The engine-0.1 save was rebuilt from turns 0001–0014 (to 1989-03-09) and migrated with
`python -m musicsim migrate`. History is untouched: Sire's 1988-12-15 pass and the 84 days remain canon.
The rejection was backfilled into the label's memory. A scripted continuation on 0.4 then went:

| Date | Event |
|---|---|
| 03-13 | Recovery is credited ("very low → low; the day job limited the rest"). Sire's A&R calls a check-in. |
| 03-17 | Development meeting. Sire re-hears all three masters: now yes to "Wild Dance", not yet to the other two (notes given). It proposes releasing "Wild Dance" and a Terry Lewis remix of "If You Want Me" ($47k from the fund, recoupable). |
| 04-03 | "Wild Dance" is released after the player approves. It builds through regional pickup to **#54** on the Hot 100 and #37 on Hot Black Singles over 9 weeks: modest, not a hit. |
| 04-25 | The remix is finished. The player submits it, and the label schedules it for 06-20 so it doesn't compete with "Wild Dance". |

Replay from the migration checkpoint verifies all 14 subsequent commands.
Replaying turns 0001–0014 directly on 0.4 diverges at turn 1 (the showcase plays out differently once
recovery works), which is why snapshot-forward migration is the only safe way to continue. See
`docs/MIGRATION.md`.

## 6. Reproducibility and saves

- 34 tests pass, including determinism, save → load → continue equivalence, replay, migration refusal
  and migration, and outcome-hash round trip.
- The transient `interrupts` list is excluded from state hashes. It depends on where `advance` calls start
  and end, and the save-load test caught it.
- **Breaking change:** engine 0.4 refuses 0.1 saves (`EngineVersionError`) and changes data, so the
  bridge's data-version guard will (correctly) refuse to rebuild Danielle on 0.4. Continue via migration
  or keep that campaign on 0.1. Migrated campaigns keep their original world population (480 generated
  acts); new campaigns get 1,400.

## 7. Open items (not fixed in this pass)

1. **First-year success is still generous** for a strong engaged player: 6/13 reach the Top 10. Per-single
   rates now look reasonable (≈10% Top 10 for approved singles), but labels let a new act put out ~5
   singles in its first year, and the protagonist is above-average talent. Next: album-cycle pacing
   (2–3 singles per year for new acts), label option pickups, and longer-run calibration against
   historical newcomer outcomes.
2. **Real-artist coverage:** with 1,400 generated acts, real artists are ~12% of Hot 100 entries. This
   is now the main fidelity gap (development priority #1).
3. **Unsigned idle stretches** can still run the full 84-day `next` window when the player does nothing
   and has no manager. Consider a monthly "state of things" interrupt or a lower cap for unsigned acts.
4. **Overwork equilibrium** sits just above the auto-rest threshold. Decide whether chronic "low" energy
   should erode skills, health or relationships, or trigger rest earlier.
5. **Bridge update** for migrated campaigns (gameplay branch; not changed here).

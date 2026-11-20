# Claude engineering handoff — Danielle Reyes 1988–89 playtest

**Prepared:** November 20, 2026  
**Reproduction branch:** `chatgpt/danielle-playtest` in `theonethatgot/music-industry-sim`  
**Scenario / seed:** `us_1988_aspiring` / `1988`  
**Canonical reproduction:** `gameplay/danielle/turns/0001.json` through `0014.json`, in order  
**Latest in-world state:** March 9, 1989; `session1-0015`  
**Engine data version:** `3763906a35ea9667`  
**Status and authoritative narrator packet:** `gameplay/danielle/output/status.json`, `latest_packet.md`  
**Purpose:** Repair autonomous career continuity and wellbeing, not guarantee a hit or bypass ordinary industry gatekeepers.

## Executive finding

Danielle signed a Sire Records deal on October 4, 1988 ($43k advance, 11% royalty, one firm album + four label options). By December 15 she had completed three Sire-funded masters. The third, *Wild Dance*, received a favorable **player-team** listening assessment (immediate sticky hook, memorable signature, repeat appeal, but thin production). In turn `0014.json`, the player requested a high-promotion/standard-video single release. Sire **rejected** the recording for single release. The same submission advanced the world by the engine's `next` cap of **84 days**, from December 15, 1988 to March 9, 1989, with **zero interrupts and no release**. Danielle remained at effectively 0% national recognition and -$85,900 unrecouped; her energy remained very low and stress rose to high despite **12 auto-rest notices** during that period.

This is a useful failure case, not a request to guarantee success. The engine should remain able to reject releases, fail creatively, lose money and delay careers—but signed artists, managers and labels need plausible responses to those decisions rather than inert 84-day stretches.

## Confirmed P0: weekly automatic rest does not restore energy

**Observed:** See `gameplay/danielle/output/latest_packet.md` for 1988-12-19 through 1989-03-06: one `Standing orders: you took a week off to recover; your team cleared the calendar` notice nearly every Monday, yet energy remains `very low`; stress becomes `high`. Earlier recovery attempts had the same issue.

**Code-level cause (high confidence):**
- `musicsim/sim.py:step_day` invokes `weekly(world,m)` on Monday, then `_commitments(world)` afterward. `_commitments` marks commitments done on their end date.
- `musicsim/player/commands.py:weekly_player` calculates energy **before** calling `team_weekly` (the delegation system).
- `musicsim/player/delegation.py:weekly` notices exhaustion and only then calls `_cmd_rest`, which creates a rest commitment with end date six days after the current Monday (`_commit` sets `end = start + 7*weeks - 1`).
- Next Monday, the prior week's rest commitment is already `done`; it does not appear in `weekly_player`'s list of active commitments. Thus its `load -= 0.25` benefit is never applied. Meanwhile the active day job contributes `load += 0.12`, so `energy += 0.06 - 0.12` continues to decline.

**Required fix:** Define a coherent accounting interval. Count completed activities from the **week just elapsed**, or grant recovery on actual days of rest / completion; avoid applying benefits to commitments that begin only after the weekly update. Ensure day-job interaction and truly protected time off are modeled consistently.

**Acceptance tests:**
1. With low energy and `rest_when_exhausted=True`, three successive seven-day rest periods **increase** energy (subject to documented stress/load constraints) rather than pinning it at minimum.
2. Repeat with the day job active, with it inactive, and with gigs overlapping; recovery should have explainable and testable differences.
3. No repeated `auto_rest` news claims when zero actual recovery was applied.
4. Seed-1988 command replay stays deterministic.

## Confirmed P1: rest claims to clear the schedule but does not actually clear non-exclusive work

**Observed:** Earlier `session1-0004` through `session1-0005` packets listed a rest week while booked gigs/training remained; Linda booked and completed a $540 show on October 3 during a period marked as time off.

**Code-level cause:**
- `musicsim/player/commands.py:_cmd_rest` calls `_overlaps` but its default conflict set is `(radio_tour, club_tour, press_tour, rest)` restricted to `exclusive` commitments. Ordinary `gigs` and `training` are not dealt with.
- `musicsim/player/delegation.py:weekly` unconditionally reports that the team `cleared the calendar` if rest was accepted, even though the other commitments remain.
- Manager gig offers are not universally checked against an active rest commitment. Whether a small date during recuperation is permissible should be an explicit policy/decision, not a contradictory claim.

**Required fix:** Add scheduling/cancellation/rescheduling with explicit consequences and refunds where appropriate, prevent incompatible gig/training bookings, and make the news wording match the actual calendar.

**Acceptance tests:** Scheduled gigs and training + auto-rest -> either genuine cancellations/rescheduling, or a clear refusal/partial-rest outcome. No overlapping exclusivity claims; no unapproved manager gig on protected rest.

## Confirmed P1: label veto permits a silent 84-day signed-artist stall

**Reproduction:**
1. Rebuild campaign from turns `0001`–`0013` on pinned seed and data.
2. Submit `gameplay/danielle/turns/0014.json` with `release_single` for `rec:n02276`, `promo=high`, `video=standard`, `advance=next`.
3. Observe `decisions[0].status=rejected`, reason: `Sire Records doesn't hear a single in "Wild Dance" and won't release it as one.`
4. Observe advance `1988-12-15 -> 1989-03-09`, `days=84`, `interrupts=[]`; no debut release and no active label/management response in the packet.

**Code-level cause:**
- `musicsim/player/commands.py:_cmd_release_single` scores the master and returns `_reject` when observed quality < `0.45`; it emits a `single_review` event but **does not raise an interrupt** or schedule any A&R feedback, turnaround, alternate single meeting, or development deadline.
- `musicsim/campaign_io.py:Campaign.submit` processes a rejected command, then still executes the supplied advance; `musicsim/sim.py:advance` only stops on `world.interrupts`, which the veto does not create.
- `musicsim/player/delegation.py:weekly` gives managers media/TV pushes chiefly when a `_current_single` exists and gigs only if allowed; it has no meaningful stateful response to a signed client's unresolved debut-release blocker.
- `musicsim/systems/labels.py:weekly` handles promotion for **already released** singles. There is no equivalent cadence for a signed, unreleased player act undergoing A&R development.

**Required fix (do not rubber-stamp rejected songs):**
- A veto must return substantive, intelligible A&R notes (e.g., melody/production/genre fit based on what the engine actually knows), and must become a `label_review` or `development_meeting` interrupt *before* an arbitrary long advance.
- A signed player's label and manager should have autonomous but non-forced follow-up: review other available masters, suggest attainable reworking/remix or songwriting/producer options, set a reasonable next check-in, or escalate real creative disagreement. Preserve the player’s final authority over release and major spending.
- Require release-deadline/album-option consequences when the label stalls; don't automatically guarantee production progress or intervene every week.
- If a consequential command is rejected, evaluate whether it should stop that same long advance with an actionable result rather than swallowing 84 days.

**Acceptance tests:** Rejected debut single -> prompt A&R follow-up / concrete action within a bounded interval, not repeated 84-day empty blocks; managers and labels act independently but don't invent successful recordings or spend unapproved funds. Both refusal and eventual success paths remain possible.

## P2 design audit: disagreement between favorable song narrative and label score

`Wild Dance` had a visibly good team-reported hook and distinctive character but Sire rejected it. This by itself **is not a bug**: the recording was also described as having thin/dated production and only capable vocals.

However `musicsim/systems/creative.py:craft_score` uses `melody (.22), structure (.10), lyric_craft (.08), production (.22), vocal_delivery (.25), arrangement (.13)`. It does **not** score the hook, signature, dance hook, singability, genre/format fit, or listener-response potential. `_cmd_release_single` uses this craft score plus A&R noise and `0.2 * singles_power_o`, and hard-gates at `0.45`.

**Requested assessment:** Run cohort/Monte Carlo calibration across label sizes, genres and experience levels. Analyze the distribution of vetoes for promising but imperfect records and whether hooky/danceable crossover tracks are systematically undervalued. Consider distinct commercial fit and artistic craft signals, tolerance for singles that are intentionally imperfect, and label-specific taste/marketing strategies. Avoid simply lowering the threshold until everything is approved.

**Acceptance tests:** A convincing range of label decisions and eventual performance outcomes; favorable listening reports are informative but not promises; cross-genre successes and flops remain possible.

## P2: policy changes don't cancel booked work, and completion dates are confusing

- In `session1-0003`, setting `training_when_idle=none` stopped future training bookings but left training scheduled through October 2. This may be by design; if so distinguish a standing policy change from cancellation and expose a cancellation or rescheduling command when justified.
- `Say You Mean It` was scheduled until October 31 but marked finished only when the simulated day `1988-10-31` executed, producing a packet dated November 1. `musicsim/sim.py:step_day` increments `world.date` only after `_commitments`; this is internally consistent but should be explained by the packet or adjusted for intuitive completion timestamps.

## Bridge validation and reproducibility

The checkpoint bridge is on the isolated gameplay branch, `bridge/run_campaign.py`; source of truth is the immutable turn JSON history. For the latest March 9 state, `output/status.json` reports valid cached SQLite snapshot, matching source/code/turn prefix, and no new full replay during this latest turn. The **most recent full deterministic replay** in the published status was turn 10 (21 engine log commands); full replay is configured every five additional new turns and will run at turn 15. Do **not** report the March 9 state as having undergone a fresh full replay.

The original `playtests/session1` starting-state hash from another process did not match regenerated hashes; the opening narrator packet and historical data version were identical. `PYTHONHASHSEED=0` stabilizes the workflow, but investigate any hidden dependence on Python process hashing before claiming engine-wide reproducibility.

The gameplay branch should **not** become the engineering branch, and old gameplay turns must not be rewritten. Implement fixes and QA on Claude's engineering branch, then either start a new validation campaign or explicitly migrate/test checkpoint compatibility. Preserve outcomes in existing canon; do not silently retcon release results.

## Desired handback from Claude

1. Root-cause fixes and automated unit/integration tests for the P0/P1 items above.
2. A reproducible low-energy recovery test over 4–12 weeks, including rest conflicting with work.
3. A rejected-single -> label response -> revised creative/release decision test over 3–6 months.
4. Calibration study of approval rates **and** commercial outcomes across multiple seeds, with the original seed-1988 path as a regression case.
5. Evidence of manager and label autonomous initiative while preserving player contract/recording/release approval rights.
6. Replay/checkpoint reproducibility checks, and clear notes on any changes that would invalidate previously generated saves.

**Success criterion:** the first-year career loop is coherent and player-centered even when no song is a hit, no song is approved, or the artist needs months of recovery. Failures should create plausible decisions and consequences, not a permanently frozen protagonist.

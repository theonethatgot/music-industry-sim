# Engine v0.4 against the Creative Vision Charter

Source: `chatgpt/danielle-playtest:docs/CREATIVE_VISION_CHARTER.md` (20 Nov 2026).
Scope: an evaluation and a staged plan. No engine changes are made by this document. The v0.4 fixes
(recovery, protected rest, development meetings, unified A&R review, migration, 34 tests) are kept.

## 1. Summary

Most of the charter fits the existing architecture. The engine already holds the numbers, memory and
causes, and ChatGPT already writes the experience. The main conflicts are not in the simulation maths.
They are in **what the player sees of the world** and in **how much the interface makes the narrator
and player work like administrators**:

1. The perceived industry is mostly synthetic (real artists are ~15% of the Top 40).
2. The interface requires operational detail (producer ids, budgets, studio weeks, one session per
   song), stops for every minor milestone, and rejects narrator canon too eagerly.
3. Album and comeback cycles are not first-class, so play degrades into "record_song → score".
4. A few v0.4 shortcuts lean toward the "constraint instead of cause" pattern the charter warns about.

## 2. Measured facts behind this evaluation

| Probe (US 1988, 3 seeds, 30 weeks) | Result |
|---|---|
| Real-artist share of Hot 100 **top 10** | 14–19% |
| Real-artist share of **top 40** | 14–16% |
| Distinct real acts seen in the top 10 over 30 weeks | 7–9 |
| Exceptional single (elite artist, excellent master, flagship label, high promotion) | Peak **#1, #1, #15**; 2.0M / 2.2M / 0.36M units. Upside reachable, not guaranteed. |
| Recognition after that one mega-hit | 42–44%. **One song can never make an artist known to more than ~45% of the public** (the recognition formula). Multiple hits can go higher. |

## 3. Where v0.4 conflicts with the charter

Ranked by experiential impact. "Engine" means it needs Python work. "Narrator" means ChatGPT can
already handle it with only contract or packet guidance.

| # | Charter principle | Current v0.4 behaviour | Conflict | Fix lives in |
|---|---|---|---|---|
| C1 | Real history is the recognizable backbone (§3, P0) | ~47 real acts / ~150 release intents vs 1,400 generated acts; real ~15% of the Top 40 | **Major.** The world the player perceives is synthetic. | Engine (data) |
| C2 | Avoid generic AI-ish titles (§4) | Generated titles and names come from word salad ("Velvet", "Electric", "Midnight", "Savage Avenue") and fill the charts | **Major.** It's exactly the pattern the charter names. | Engine (data) + fewer named fictional acts |
| C3 | Don't make the player run studio calendars or fees (§2, §6) | `record_song` requires producer id, budget, studio weeks and genre, one song at a time; albums need ≥6 separate sessions | **Major.** It forces administration and the score loop. | Engine (interface) |
| C4 | Natural flow of ordinary steps between major decisions (P0) | Every chart entry, release, finished session or TV booking stops time and needs a new submission | **Medium–major.** It produces repeated "proceed" prompts. | Engine (pacing) |
| C5 | Simple hooks for narrator canon; visible provenance layers A–D (P0) | `narrative_fact` rejects any `#n`, money or sales mention (even quoting the packet); at most 3 new people per pass; fixed role list; five opportunity kinds; one invalid item rejects the **whole** submission | **Medium.** Over-restrictive; the narrator loses freedom and the player loses turns. | Engine (small) + contract |
| C6 | Management brings developed proposals; "proceed as recommended" (§2, §6) | Advice is plain text; only label development meetings create actionable proposals | **Medium.** Teams don't propose plans the player can approve in one line. | Engine (small–medium) |
| C7 | Contracts are a source of negotiation, not a stop sign (§2); avoid blunt veto gates (§2) | A&R review is approve/reject at a threshold; meetings soften it, but there's no lobbying or leverage band | **Medium.** | Engine (small) |
| C8 | Don't fix success rates with fixed release limits (P1) | v0.4 added a hard ~11-week single-spacing rule for labels | **Direct conflict.** It should be a label preference the artist can push against, not a rule. Root-cause fixes (competition) were also made and should stay. | Engine (small) |
| C9 | No arbitrary "new artist" ceiling (§3, test 3) | No hard ceiling on charts or sales; one-song recognition saturates at ~45% | **Minor**, but should be revisited (cultural-moment songs). | Engine (tuning) |
| C10 | Achievements lived: awards, music-show wins (§5) | TV performances exist; no awards bodies; no ranking-show wins (US has none; needed for KR) | **Gap** for KR and awards. ChatGPT can narrate real awards as context today. | Engine (P1) |
| C11 | Persistence: discography, credits, concepts, artwork refs (P1, test 6) | Releases, recordings, credits and chart stats persist; no album concept, track sequencing, artwork reference or decision trail | **Gap.** | Engine (small) |
| C12 | Organic world news, not forced bulletins (§3) | Packets list many "New album: <generated act>" items | **Minor.** Noise. | Engine (packet filter) |
| C13 | Personal life is selective texture (§7) | The engine keeps only light relationships and memories | **Aligned.** Keep it that way. | — |
| C14 | Real people: no fabricated private claims (§2–3) | Real-person policy plus rejection of invented real people | **Aligned.** Contract wording can add "dramatisation, not documented speech". | Narrator |

Already aligned and to keep: engine-owned numbers and outcomes; real artists compete without protected
ranks (soft intents with a bounded history weight); causes exposed (`why`, A&R notes, radio adds with
components); era-correct charts; delegation of routine work; protected rest; label/manager follow-up;
deterministic, replayable saves; migration rather than silent retcon.

## 4. What ChatGPT already handles (no Python needed)

- Scenes, dialogue, atmosphere, backstage encounters, watching real acts perform, rehearsal and encore texture.
- Period-credible song and album titles and concepts (with research), sleeve notes, press voice.
- Integrating player-supplied cover art into release presentation. Python only needs to store a reference.
- Personal life, friendships and rivalries as selective texture.
- Real public historical events and context (researched, chronologically valid), framed as layer A.
- Dramatising awards nights and TV tapings around engine results. Where Python doesn't model an outcome,
  the narrator proposes it as canon and it is recorded as layer D.

## 5. Staged plan (small first)

### Stage 1: interface and presentation alignment (low cost, about 1–2 sessions; no data import)
1. **Provenance layers in packets and contract.** Tag every item A (historical reference), B (engine
   result), C (narrator dramatisation) or D (recorded canon, with status `recorded` or `pending`).
2. **Generic canon hook.** One `canon` proposal with `kind` (creative_decision, achievement,
   relationship, asset, plan, other), free text, optional structured fields, `status: pending|recorded`.
   Allow quoting numbers that come from the packet; reject only invented consequential numbers. Open the
   role list ("other" with a description); raise the new-people limit.
3. **Partial acceptance.** Apply valid items and report invalid ones, instead of rejecting the whole reply.
4. **Team defaults.** `record_song` (and album work) accepts intent only ("record it with Carla" or "team's
   choice"). The team fills in producer, budget and schedule from the recording fund and context, and
   reports its choices.
5. **Two-tier pacing.** Milestones (chart moves, release out, session done) are collected and narrated,
   not stopped for. Only *decisions* and major moments stop time. New `advance: "next_decision"`.
6. **Packet hygiene.** Drop generic fictional bulletins; highlight real competitors and the protagonist's
   context; include the reasons behind decisions.
7. **Replace the single-spacing rule** with a label preference: the label proposes a date, and the artist
   can insist (spending goodwill or leverage).
8. **Period-credible fictional naming** from market data (pattern lists per era and language), plus fewer
   *named* fictional acts in what the player sees.

### Stage 2: historical coverage (P0 data; staged and cached, not one giant import)
1. Import real US singles for 1986–1992 from year-end and top-ten lists (title, artist, label where
   known, approximate dates, peak as tier-B *evidence*) into soft intents. Add catalogue albums.
2. Rebalance the field: **real acts supply most of the top of the charts at the start**; generated acts
   fill the long tail. Keep the total release volume, and therefore the competition, from the v0.4 fix.
3. Context calendars: award ceremonies, TV programmes and notable venues with capacities (tier B), so
   the narrator can stage period-correct events.

### Stage 3: creative and release cycles (P1)
1. **Album/comeback projects** as first-class objects: concept, audience, track list and sequencing,
   collaborators, artwork reference, promotion plan. The team executes the sessions; each song is still
   an individually simulated recording.
2. **Team plans with "proceed as recommended"**: manager and label propose a plan; one approval executes
   the routine parts and leaves key artistic choices to the player.
3. **Lobbying band** around the A&R verdict (leverage, relationships, manager skill, goodwill cost).
4. Awards (voting-body models) and, for Korea, music-show rankings and wins.
5. A **career record** export: discography, credits, peaks, cumulative sales, contracts, decisions, artwork refs.

### Stage 4: Korea late-1990s pack on the same core.

## 6. Acceptance criteria (player-facing first; plus the existing determinism and calibration suites)

| Charter test | Pass condition |
|---|---|
| US 1988–89 recognizable world | At the campaign start, **≥ 60% of the Hot 100 top 10 and ≥ 45% of the top 40** are real acts; over the first year, real acts hold ≥ 50% of top-10 weeks; ≥ 25 distinct real acts appear in the top 40. The v0.4 competition levels are kept (Top-10 rate per released single within ±30% of v0.4). |
| Real stars aren't protected | Across 20 seeds, historical #1s are #1 in 20–80% of runs, and the protagonist can displace any of them in at least one seed. |
| Extraordinary upside | An elite act with an exceptional record reaches #1 in ≥ 50% of seeds, and recognition can exceed 60% after a single cultural-moment hit, without any new-artist cap. |
| Credible disappointment | The existing v0.4 continuity checks still pass (no inert 84-day blocks; recovery works). |
| Low administration | A first album can be made with **≤ 3 player decisions** (concept and lead single, approve plan, release) under "proceed as recommended". The team reports its choices. |
| Natural flow | ≤ 1 stop per 30 days in routine stretches; every stop is a decision or a major moment. |
| Narrator freedom | Quoting packet numbers in canon is accepted; invented consequential numbers are refused; one bad item doesn't void a reply. |
| Period-credible fiction | No generated title or act name in packets comes from the v0.4 word lists; fictional names come from era/market pattern data. |
| Persistence | After a 3-year run: concepts, exact title spellings, track lists, credits, artwork references, peaks, cumulative sales, contract terms and the decision trail are all retrievable from one career-record export. |
| Determinism | Replay and save → load → continue tests stay green; migration from v0.4 is documented. |

## 7. Things deliberately not planned

Automated dialogue, private-life AI, friendship or romance mechanics, an approval gate for every routine
action, and large invented catalogues (charter P2).

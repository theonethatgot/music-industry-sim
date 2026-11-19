# Music Industry Simulator — Technical Design (v0.2, pre-code)

A universal, historically grounded, international music-industry world simulation
(1980–2026). You can start a campaign in any supported country and date, as any
kind of artist in any circumstances, and live through that era against a populated,
autonomous industry that includes real historical artists, labels and institutions.

The Python engine owns every consequential fact. An AI narrator (initially ChatGPT,
used manually) turns engine output into immersive story and can *propose*
developments, which the engine validates, resolves and records.

**What changed in v0.2.** v0.1 implicitly privileged late-1990s South Korea and a
specific protagonist. v0.2 makes the engine country-, era-, genre- and
protagonist-neutral (§2, §3). It makes the US a first-class market from the start,
treats real artists as full autonomous agents (§6), adds cross-market careers (§7)
and validates the core with two equal scenarios, US late-1980s/early-1990s and South
Korea late-1990s, built on the same engine (§14).

**Conventions**
- `T` = hidden true value; `O` = an observation of it (noisy, biased, dated).
- **Evidence tiers** for all data (§11.1): `A` verified primary source · `B` sourced
  estimate · `C` model estimate · `S` simulated.
- *(verify)* marks historical facts still awaiting primary-source confirmation. Such facts
  live in data files with their tier, never in code.

**Implementation status (v0.3, first playable slice).** The universal core, the US market pack
(1986–1993 data window), the manual narrator loop and exact replay are implemented; see README
for the implemented-vs-planned table. Decisions taken during implementation:
- Narrator integration is part of the first playable milestone (not a late phase): every pass
  produces a Markdown packet with embedded authoritative JSON and accepts validated decisions
  and proposals back (§13).
- Radio adoption is two-level: national playlists plus *regional pickup* by a minority of a
  format's stations, so unknown acts can break out without national adds (§9.3).
- Song awareness ("heard it") and artist recognition ("knows who sings it") are separate; only the
  upper reaches of a chart create general-public visibility (§8).
- History informs priors with a bounded weight (`creative.history_evidence_weight`); historical
  chart peaks are never targets (§6, §15).
- Market packs are declarative first, but genuinely distinct institutions may get specialised
  market modules behind core interfaces rather than being forced into one abstraction (§2.1).

---

## Table of contents
1. Design principles → engineering rules
2. Layered architecture: universal core, market packs, era data, scenarios
3. Campaigns: creating any start
4. World-state schema
5. Creative model: songs as creative products
6. Real historical participants as autonomous agents
7. Cross-market careers and international structure
8. Hit formation and consumption
9. Industry systems
10. Economics
11. Historical data, evidence and acquisition
12. Chart and ranking engine
13. Narrator–engine interface
14. Validation scenarios
15. Calibration, reports and testing
16. Phased roadmap
17. Compatibility with the acting engine
18. Failure modes from previous roleplays → structural fixes
19. Decisions needed before Phase 0 code

---

## 1. Design principles → engineering rules

| Principle | Engineering rule |
|---|---|
| **Universal engine** | Core and system code contain no country codes, years, genre names, chart names, institution names or people. Everything specific lives in market packs, era data and scenarios (§2). A lint test enforces this (§15.6). |
| **Engine owns the truth** | Sales, streams, airplay, positions, money, contracts, relationships, calendars and canonical events exist only in engine state. The narrator reads packets and submits proposals. |
| **The player is an NPC with a human controller** | Player-controlled and autonomous artists go through identical code paths. No outcome function receives `is_player`. A fairness test enforces this. |
| **Real people are full agents** | Real artists have careers, catalogues, contracts, teams, identities, goals and decision-making, not static popularity ratings (§6). |
| **No ceilings, no floors** | Nothing caps anyone's success relative to history, and nothing guarantees it. Fat tails are calibrated so unprecedented success is rare but reachable through causes. |
| **History as prior, not script** | History supplies initial state, structural conditions and soft future intentions. All outcomes after the start date are simulated. |
| **No future knowledge** | Decisions use only observations dated at or before "now". |
| **Era- and country-correct institutions** | Charts, formats, media, awards, certifications and contract norms are dated data objects per market. They exist only within their validity windows. |
| **Separate signals stay separate** | Physical album sales, singles sales, downloads, streams, airplay, TV exposure, public recognition, fandom activity and ranking-show results are distinct variables linked by explicit mechanisms. |
| **No single quality or popularity score** | Songs have creative attribute vectors and artists have status vectors. Appeal is per audience segment, and critical and commercial reception are separate. |
| **Imperfect information** | Every organisation decides from its own observations. |
| **Configurable** | Coefficients live in versioned YAML, layered by universal → market → era → scenario. |
| **Reproducible** | `state(t) = f(scenario, data_version, config_version, seed, ordered_command_log)`. |
| **Manageable depth** | Level-of-detail simulation: markets the campaign touches run at full detail, the rest run coarsely, and detail is promoted on demand (§2.5). |

---

## 2. Layered architecture

### 2.1 Four layers
```
┌─────────────────────────────────────────────────────────────────────┐
│ Scenario / campaign  start date, markets, protagonist, circumstances │  data/scenarios, saves
├─────────────────────────────────────────────────────────────────────┤
│ Era data             dated tables & events: prices, formats, media   │  data/markets/<cc>/eras
│                      audiences, institutions' validity, real people  │
├─────────────────────────────────────────────────────────────────────┤
│ Market packs         institutions & rules instantiated from generic  │  data/markets/<cc>/ (+ optional
│                      archetypes; plug-in hooks only where data can't │  engine/markets/<cc>/hooks.py)
├─────────────────────────────────────────────────────────────────────┤
│ Universal core       entities, creative model, listener dynamics,    │  engine/
│                      agents, contracts, ledger, charts-from-spec...  │
└─────────────────────────────────────────────────────────────────────┘
```
The rule is to **prefer data over code**. A market pack is mostly declarative: which
institution archetypes exist, with what parameters and validity dates. Python hooks
are allowed only for genuinely unusual mechanics that the generic archetypes cannot
express, and they must implement a core interface.

### 2.2 Generic institution archetypes (core)
Markets instantiate these. They never subclass the engine for a whole country.

| Archetype | Parameters (examples) | Instances (illustrative) |
|---|---|---|
| `RecordCompany` | structure (major group/label/imprint/indie), A&R capacity, distribution, strategy | Major groups and indies in any market |
| `IntegratedAgency` | training, production, management and publishing under one roof; contract norms | Korean and Japanese entertainment agencies |
| `Management` | commission, roster capacity, network | US/UK managers |
| `Publisher`, `CollectionSociety` | splits, rates, payout lag | ASCAP/BMI, PRS, KOMCA, JASRAC |
| `Distributor`, `RetailChannel` | reach, terms, panel membership | Chains, indies, department stores, online retail |
| `RadioStation` | format, audience by segment, playlist size, research method | US formats (CHR, Urban, AC...), national broadcasters |
| `TVProgram` | kind (music performance, ranking show, variety, awards), slots, booking policy, optional ranking | Network TV appearances, broadcast music shows |
| `MusicVideoChannel` | rotation tiers, audience, programming policy | Music-TV channels where and when they existed |
| `MediaOutlet` | readership, taste, sensationalism | Trades, tabloids, critics' magazines, fanzines |
| `ChartPublisher` + `Methodology` | measurement inputs, formula, windows, rules (§12) | Any chart or ranking show |
| `CertificationBody` | thresholds by date, shipment vs sales basis | RIAA, BPI, RIAJ... |
| `AwardsBody` | voting model, categories by year | Grammys, BRITs, year-end broadcaster awards... |
| `Promoter`, `Venue` | capacity, city tier, terms | Tours, festivals, events |
| `Platform` | download/stream/recommendation behaviour | Digital eras |
| `Brand` | endorsement budget, image preferences | Endorsements/CFs |
| `RegulatoryRule` | content restrictions, quotas, foreign-content limits, censorship | Broadcast standards, import rules |

### 2.3 Repository layout
```
music-industry-sim/
  engine/
    core/          # clock, rng, events/provenance, state, commands, ledger, observe,
                   # memory, config layering (universal→market→era→scenario), lod
    models/        # Person, Act, Composition, Recording, Release, Product, Org, ...
    archetypes/    # generic institution behaviours (§2.2)
    systems/       # culture, creative, anr, release, promotion, exposure, demand,
                   # retail, digital, live, fandom, reception, charts, awards, careers,
                   # groups, contracts, finance, agents, opportunities, international,
                   # news, history
    markets/<cc>/hooks.py   # optional, rare
    narrator/      # factpacket, proposals, checker
    campaign/      # builder, validation, character import/export
  data/
    universal/     # style space, segment templates, default coefficients
    markets/<cc>/  # institutions.yaml, methodologies/, eras/, audiences/, contracts/
    people/        # real people/acts (tiered), catalogues, intents
    characters/    # saved player characters (portable, optional)
    scenarios/     # campaign presets (examples, not special-cased)
    reference/     # calibration targets
    raw/           # pipeline cache (gitignored)
  pipeline/        # staged, restartable data collection
  cli/  api/  tools/  tests/  docs/
```

### 2.4 Time model
- **Date resolution: one day.** Consumption and exposure are simulated daily with
  vectorised maths. Any tracking window, release weekday or broadcast day is therefore
  exact. Release-day conventions are market/era data, e.g. US Tuesday releases from
  1989 and the global Friday release day from July 2015 *(verify per market)*.
- **Decision cadence: weekly** for agents, plus event-driven decisions (offers, deadlines, crises).
- **Scheduled-event queue** for releases, broadcasts, chart publications, expiries, ceremonies and sessions.
- **Narrative pacing is independent of ticks:** `advance 3d | 2w | 4m | until <event>`,
  stopping at interrupts (decisions needing approval, major events, salient opportunities).

### 2.5 Level of detail (keeps the world manageable)
| LOD | Applies to | Simulation |
|---|---|---|
| **Full** | Markets where the campaign is active, and acts competing there | Daily listener dynamics per segment, all institutions, all agents |
| **Coarse** | Other supported markets | Weekly aggregate demand per act/release from a reduced model; key institutions only |
| **Statistical** | Unsupported markets | Era tables for export income/recognition; no individual institutions |

Promotion from coarse to full is seamless: coarse state stores enough (recognition, fandom,
catalogue strength) to initialise full state. Cross-market careers (§7) trigger promotion.

### 2.6 Determinism and persistence
- RNG streams: `rng(seed, system, entity_id, purpose, date)`. Iteration in sorted-ID order.
- Save = SQLite snapshot + event log (with `causes[]` provenance) + command log +
  proposal log + config hash + data version. `inspect why <fact>` walks provenance.
- Replay test: snapshot + commands → identical state hash.

---

## 3. Campaigns: creating any start

### 3.1 Campaign builder
A campaign is created from choices, validated against the data available for that date and place:
```yaml
campaign:
  start_date: 1986-09-01
  home_market: US
  active_markets: [US]              # full LOD; others coarse automatically
  protagonist:
    source: new                     # new | saved_character | existing_npc
    character: null                 # e.g. data/characters/<name>.yaml when importing
    identity: {name, birth_date, gender, origin_city, languages, background}
    abilities: preset|custom        # vocal, songwriting, performance... (§4.2)
    artistic_identity: {style_position or genre tags, persona}
    act: {kind: solo|group, members?: [...], name}
  career_stage: aspiring | trainee | unsigned_local | indie_signed | major_signed
                | established | veteran | comeback
  circumstances:
    location: Los Angeles           # city → local scenes, venues, cost of living
    affiliations: []                # label/agency/manager if any (must exist at date)
    contracts: generated|custom     # typical terms for stage & market
    finances: {cash, debts}
    connections: []                 # people the protagonist already knows
    catalogue: []                   # prior releases for established starts
    reputation: {...}               # optional overrides for established starts
  world:
    seed: 41
    structural_history: on
    contingent_history: intents     # real careers as soft intents (§6.3)
    real_person_policy: default
    divergence_from: start_date     # or import an existing divergent world
  player_policy: default            # approval/delegation (§13.6)
```
**Validation:** institutions, formats and people named in the config must exist at the
start date. Unsupported markets can be a home market only once their pack reaches full
LOD readiness. Established-artist starts get a **back-filled history** (prior releases,
relationships, fandom) consistent with the stage chosen.

### 3.2 Characters are portable data
A protagonist is a saved character file (identity, abilities, history, relationships by
reference). Any character, including one imported from an earlier roleplay, can be
dropped into a compatible campaign or started fresh. No character is built in.

### 3.3 Scenario presets
Presets are just saved campaign configs, for example:
`us_1986_aspiring_singer`, `us_1991_rnb_newcomer`, `uk_1995_britpop_or_pop_act`,
`kr_1998_agency_soloist`, `us_2003_hip_hop_artist`. They carry no special-case code.

### 3.4 Player roles
The architecture defines a **role** as a control surface over the same world:
`artist` (solo/member/trainee) first; later `songwriter`, `producer`, `manager`,
`label_executive`. A role defines the commands available, the information sources
attached and the default delegation policy. The world simulation is identical across roles.

---

## 4. World-state schema

Scales 0–100 unless noted; every seeded value stores its evidence tier and confidence.

### 4.1 Shared base (kept compatible with the acting engine, §17)
```
Person   id, names {native, romanised, stage[]}, birth_date, gender, nationality,
         languages {lang: fluency}, home_city, is_historical, evidence,
         roles {performer, songwriter, producer, manager, executive, a&r, ...},
         personality {ambition, risk_tolerance, artistic_vs_commercial, loyalty,
                      temperament, discipline, ego, sociability, resilience},
         goals {money, fame, artistry, stability, power, approval, freedom},
         wellbeing (T) {energy, health, stress, morale}, account, calendar, memories
Org      id, archetype (§2.2), market, parent, people, account, strategy params
Relationship  affinity, trust, respect, favour_balance, rivalry, history[]
Memory   owner, about[], event_id, gist, valence, salience (decays/refreshes), public|private
Commitment, Contract (typed terms, §10)
```

### 4.2 Music professional profile (per Person)
| Field | T/O | Meaning |
|---|---|---|
| `vocal` | T | `{technique, tone_distinctiveness, range, stamina, live_stability, style_fluency}` |
| `performance` | T | `{stage_presence, dance, live_band_leadership, crowd_work}` |
| `media_skill` | T | interviews, talk/variety, radio, controversy handling |
| `visual_market_value` | T | market's current valuation of image. Era/market/gender curves model industry bias, not a judgement. |
| `songwriting` | T | `{melody, lyrics, structure, hook_craft}` + `style_skill(style region)` |
| `production` | T | `{arrangement, sound_design, mixing, vocal_direction}` + style skill |
| `musicianship` | T | instruments, theory |
| `craft_growth` | T | learning rate |
| `artistic_identity` | T | style position, persona tags |
| `reputation_professional` | O | reliability as rumoured |
| `scandal_hazard` | T | per policy (§11.7) |

### 4.3 Act
```
Act  id, name, kind {solo, group, duo, band, unit, project, collective}, origin market
     members [{person, role, joined, left, reason}]
     identity: style position, genre tags, persona/image, target segments
     affiliations: label(s) per market, management/agency, publisher
     status (§4.4), fandoms per market (§4.5), catalogue, contracts
     lifecycle (derived): pre-debut … rookie … rising … established … peak … veteran
                          … hiatus … disbanded … legacy
```

### 4.4 Status vector (per act per market; key persons too)
`recognition[segment]`, `public_appeal[segment]`, `fandom` (object), `singles_power`,
`album_power`, `live_demand[city tier]`, `endorsement_value`, `leverage`,
`critical_prestige`, `industry_respect`, `momentum` (recency-weighted surprise),
`sustainability` (fatigue, saturation, churn, internal tension).
The industry sees `O` versions (Bayesian beliefs from attributed results), so acts can be
over- or under-rated, and international reach is simply status in other markets.

### 4.5 Fandom (per act per market)
Size by tier (core/active/casual), segment mix, loyalty, intensity, organisation level,
purchase propensities (albums, multiple copies, merch, tickets), mobilisation capacity,
morale, rivalries, member-specific attachment. **Mobilisation tools are era/market data**:
fan clubs and mail-order, request lines, street teams and mixtapes, broadcast attendance
and coloured-balloon cultures, voting apps and streaming campaigns. The underlying fan
psychology is shared.

### 4.6 Creative works
```
Composition  writers[share], publishers[share], language, composition attributes (§5.1)
Recording    composition, performers, producers, engineers, sessions, cost,
             recording attributes, version {original, remix, radio edit, extended,
             translated, live, acoustic}
Release      act, label per market, kind {album, EP/mini, single, maxi/12", repackage,
             compilation, soundtrack, mixtape}, tracklist, focus tracks per market,
             release dates per market, artwork concept
Product      release × format × market: {LP, cassette, CD, 7", 12", cassingle, CD single,
             VHS/DVD, digital album, digital track, ringtone, stream}, list/dealer price,
             unit cost, editions; formats exist only where era data allows
Campaign     promotion cycle per release per market: budget lines, focus track by week,
             bookings, videos, radio promo, tour support, status
```

### 4.7 Markets and audiences
```
Market       population by Segment, music spend per segment, inflation, currency, FX,
             format adoption curves, media diet (TV, radio by format, music-TV, internet),
             concert-going, karaoke, regional/city structure, foreign-music openness,
             language(s), release conventions, institutions (from pack), regulation
Segment      templates (age × gender × region/urbanicity × taste cluster); taste clusters
             are market/era data. In US 1980s data, for example, Black urban audiences
             and suburban pop audiences have different radio diets, which is what made
             crossover a real mechanism.
Taste state  per segment: distribution over style space, novelty appetite, openness,
             drift velocity
```

### 4.8 Media, retail, charts, observations, opportunities
As defined by the archetypes (§2.2). Inventory tracks pressed, shipped, in-store, sold and
returned. **Shipments, sales, reported figures and claimed figures are four separate numbers.**
Charts: `ChartDefinition → Methodology versions → ChartRun → ChartEntry`.
Observations: `{subject, observer, value, sigma, bias, source, date, expires}`.
Opportunities: `{kind, source, target, terms, expiry, preconditions, originator, salience}`.

---

## 5. Creative model: songs as creative products

### 5.1 Attribute vector (true values, observed with noise by everyone)
| Level | Attribute | Effect |
|---|---|---|
| Composition | `melody`, `lyric_craft`, `structure` | craft; durability |
| Composition | `hook_strength` | first-listen liking; radio/TV impact |
| Composition | `depth` | grower vs burner: liking growth with repetition, fatigue resistance |
| Composition | `singability` | karaoke, crowd participation, word of mouth |
| Recording | `production_quality` | polish **relative to era norms** |
| Recording | `sonic_signature` | distinctiveness; novelty |
| Recording | `vocal_delivery`, `arrangement_fit` | performance and production serving the song |
| Both | `style_position`, `genre tags` | where it sits culturally |
| Both | `accessibility`, `ambition`, `identity_fit`, `controversy` | breadth, critical appeal, fit, talkability/risk |
| Performance | `dance_hook`, `stage_concept` | TV/live impact, dance crazes |
| Visual | `video_quality`, `visual_concept` | music-video-era exposure and image |

There is **no overall quality score.**

### 5.2 Style space and genres
A continuous style space of about 8–12 configurable axes: energy, valence, rhythmic feel,
electronic↔acoustic, raw↔polished, vocal↔beat centricity, harmonic complexity, lyrical
register, local↔international idiom. **Genre tags are data:** time-varying regions of the
space, defined per market. "Dance" in 1987 US, 1995 UK and 1998 Korea are different
regions. Genre emergence (new jack swing, house, gangsta rap, Britpop, idol pop, trap...)
appears as new regions gaining audience, fed by the culture system (§5.3) and seeded by
era data as *currents* (influences and technologies), never as predetermined hits.

### 5.3 Culture and taste dynamics
Bandwagon drift toward successful styles, saturation reducing novelty, exogenous currents
(technology, imports, scenes), generational turnover and cross-segment crossover.
These interact to produce trends, backlash and movements endogenously.

### 5.4 Appeal (per song × segment × market)
```
appeal = taste_match(style) · craft(melody, structure, production_rel_era, delivery, arrangement)
       · novelty(sonic_signature, saturation, novelty_appetite)
       · accessibility(openness) · act_term(public_appeal, identity_fit, image)
       · language/foreignness(market openness, era) · exp(ε_reception)   # Student-t, logged
```
Segment weights are data. A teen-pop segment weights the act and image heavily, an adult
segment weights vocal and melody, and a hip-hop core segment weights authenticity and
identity fit.

### 5.5 Creative production
Attributes come from the people and the process: writer/producer skill in the style
region, chemistry, time and budget (diminishing returns), studio technology of the era,
performer skill, and creative risk (higher ambition means higher variance). There is a
**song market**: writers and producers pitch, labels commission, A&R ears (noisy) choose,
and top songs go to acts with leverage. Artists can write their own songs.
Narrator or player briefs set the intent; the engine computes the result; the narrator
describes it consistently. Revisions (more time, a new producer, a remix) move attributes
within bounded, costed ranges.

---

## 6. Real historical participants as autonomous agents

### 6.1 What a real artist is in the engine
A real artist (e.g. a major mid-1980s US star) is a full `Person` + `Act` with:
- **Catalogue:** prior releases with compositions, recordings and estimated attributes,
  and their **current listener state** at the start date (warm start, §6.4).
- **Status vector and fandoms** per market, fitted to their history (§6.2).
- **Affiliations and contracts:** label (as of the start date), management, publishing,
  estimated contract positions (album commitments remaining, leverage).
- **Team and relationships:** producers, writers, executives, peers, rivals. Edges are
  seeded from documented collaborations.
- **Identity and goals:** artistic direction, personality, ambitions (tier C estimates with rationale).
- **Agent behaviour:** they decide on releases, collaborations, touring, image changes,
  label moves and rest like any NPC, through the same utility models.
- **Intents:** future historical releases and moves as soft priors (§6.3).

### 6.2 Estimating hidden attributes: inverse calibration
Rather than hand-assigning numbers, hidden attributes are **fitted**:
1. Collect the artist's pre-start track record (tier A/B): chart runs, certifications,
   reviews, awards, touring scale.
2. Choose attribute values (song attributes of past releases, fandom, recognition) such
   that simulating those past releases under that era's rules reproduces the observed
   record in distribution (approximate Bayesian computation or likelihood-free fitting).
3. Store the posterior mean, an uncertainty band and `confidence`. The full posterior
   allows seed-to-seed variation.
4. Plausibility checks flag implausible fits (e.g. a cult act fitted with mass recognition)
   for the calibration report (§15.3). You review reports, not stat sheets.

### 6.3 Contingent history: soft intents
- **Release intents:** real releases appear as projects around their real dates, with the
  real team as high-prior participants and real compositions with estimated attributes.
  Whether, when and how well they happen is simulated. If a collaborator is busy, signed
  elsewhere or estranged in-sim, the project adapts.
- **Debut pipeline:** future real artists enter around their real emergence, with
  estimated profiles. Who signs them and whether they break is simulated.
- **Organisational intents:** label foundings, mergers and executive moves are pressures
  conditioned on simulated finances.
- **Divergence propagation:** later intents read simulated state. Acts that grew bigger
  get bigger opportunities; acts that faded lose intent priors.
- `tools/divergence_report` quantifies drift from history.

### 6.4 Warm start
A campaign starting mid-history needs a living present: songs mid-run on radio, albums
selling, tours underway. The engine initialises the listener states of recent releases
so the first simulated weeks reproduce the published charts and airplay of the weeks
**before** the start date (tier A targets), then runs freely. A test checks continuity
between the last real weeks and the first simulated weeks.

### 6.5 Competing with real stars
There are no protected positions. A fictional artist with an exceptional record, strong
appeal and major support competes directly for the same radio slots, TV bookings, wallets
and chart positions. Real stars can misfire, delay, switch direction or exceed their history.

---

## 7. Cross-market careers and international structure

Cross-market expansion is a **process with costs, gatekeepers and uncertainty**, not a multiplier.

### 7.1 How a release reaches another market
- **Routes:** a major group's local affiliate, a licensing deal with a local label, an
  import-only release (small reach), a local signing, or later global digital availability.
  Era data defines which routes exist.
- **Local priority:** the local affiliate or licensee decides budget and priority from its
  own observations (local trials, imports, buzz). An overseas star can still be a low
  priority locally.
- **Localisation:** local-language versions, local producers or writers, image adaptation,
  edits for local regulation.
- **Presence:** local promotion requires calendar time (travel, TV, radio tours), so
  markets compete for the artist's schedule.
- **Audience fit:** appeal is computed with the local market's segment tastes,
  foreign-music openness, language factors and cultural proximity, so the same song can
  land differently.
- **Spillover:** recognition leaks across markets only through modelled channels:
  international media, shared music-TV, diaspora segments and touring. These are weak and
  explicit.

### 7.2 International charts and institutions
Each market runs its own institutions (§12). Global aggregates exist only when they
historically existed.

### 7.3 Coarse simulation of other markets
Under coarse LOD, foreign markets still produce weekly demand for imported or licensed
releases, which generates income and recognition. When a campaign moves into a market,
it is promoted to full LOD.

---

## 8. Hit formation and consumption

Runs daily, per song × market (full LOD) × segment.

### 8.1 Listener state
`Unaware → Exposed → Familiar → Engaged → Fatigued`. Liking follows a mere-exposure curve
shaped by `hook_strength` (early liking) and `depth` (late peak, fatigue resistance).
Fatigue is per listener, so over-rotation burns songs out.

### 8.2 Exposure channels
Radio (spins × station audience by segment × daypart), TV performances (viewership × slot ×
stage impact), talk/variety (artist recognition more than song familiarity), music-video
rotation, soundtracks and ads, ambient/public play, word of mouth, fandom evangelism,
chart and media visibility, clubs/DJs and mixtapes (era/genre data), and streaming platforms
and algorithms in later eras. Which channels exist, and their reach by segment, is market/era data.

### 8.3 Non-linear hit dynamics
1. Contagion with thresholds (word of mouth ∝ engaged share^α × talkability), which produces sleepers and breakouts.
2. Social proof from chart/media prominence (bounded, segment-dependent conformity).
3. Gatekeeper cascades: radio adds and TV bookings follow *observed* momentum.
4. Label reinvestment via the opportunity detector (§9.9).
5. Cultural moments: crossing general-population thresholds triggers parodies, dance crazes
   and news, lifting the act's whole catalogue.
6. **Crossover:** songs spread between segments via shared channels (e.g. from a format serving
   one audience to a mass-pop format), gated by programmers' observations. This is a key mechanism
   in US R&B/hip-hop history and is fully endogenous.
7. Competition through shared pools: airplay slots, TV slots, attention, wallets.
8. Fat-tailed reception shocks amplified by contagion.

### 8.4 Fandom formation
Engaged listeners convert to fans via the act's appeal, identity distinctiveness and
exposure to *personality* (interviews, TV, fan events), and move up and down the tiers
over time. Member-specific attachment enables solo spin-offs and lineup reactions.

### 8.5 Consumption outputs (separate)
| Output | Driven by |
|---|---|
| Album purchases | core/active fans + casual conversion from engaged listeners of focus tracks at `conv[market, era, segment]` (data), album value, price, stock, shared wallet |
| Singles purchases | engaged listeners × `singles_market_strength[market, era]` × availability (singles formats exist only per era data) |
| Airplay | programmer decisions; an exposure input and a measured chart input |
| Requests/votes | engaged + mobilisation tools available in that era/market |
| Karaoke, clubs | singability/danceability × venue culture data |
| Downloads, ringtones, streams | digital adoption × engaged × price/piracy × platform (later eras) |
| Tickets, merch | fandom tiers + recognition × appeal + live reputation |
| Recognition | exposure to the act |

**Shared wallet:** each segment's music budget (era/macro data) is contested by all desired
products, so blockbuster weeks and recessions matter.

### 8.6 Album vs singles separation
Song popularity lives in listener state. Album sales come from fandom plus market/era-specific
conversion. In some market/eras hits were mostly owned via albums; in others singles or downloads
captured that demand. A ubiquitous song can coexist with modest album sales, and a fandom act can
lead album charts with little general recognition.

### 8.7 Retail, supply, reported numbers
Pressing from forecasts, stock-outs, returns. `sell_in ≠ sell_through ≠ reported ≠ claimed`.

### 8.8 Critical reception
Outlets with taste profiles and biases (genre snobbery, rockism, idol scepticism, nationalism:
all data). They weight ambition, signature, lyrics, depth and album coherence. This is separate from
commercial appeal.

---

## 9. Industry systems

### 9.1 Record companies and agencies
Organisational structure comes from market pack norms (separate label/management/publishing,
or integrated agencies). `RecordCompanyAI` has finances, roster, A&R staff with
style-specific ears, strategy (risk, style focus, budget bands, exploitation aggressiveness,
artist-treatment norms), a pipeline and gatekeeper relationships. It allocates budgets across
its roster by expected value **under its own beliefs**, avoiding calendar collisions with
strong competitors. Corporate groups own multiple labels with internal competition for priority.

### 9.2 Broadcasting and TV
TV programs book from scarce slots by status, momentum, relationships, politics and rules.
Stage impact = performance skills × dance hook × concept × live stability × shock. Ranking
shows use methodologies (§12). Regulation (content standards, bans) is data.

### 9.3 Radio
A programmer AI per station (or per cluster, at coarse LOD) adds songs when
`format_fit + observed research + label promotion + sales/chart signals + relationships
+ requests − playlist competition` clears a threshold. Songs move through rotation tiers
and are dropped on observed burn. Independent promotion and payola-style influence are optional,
era-gated mechanics with detection risk (off by default).

### 9.4 Music video
Commissioning decisions (budget → `video_quality`), channel programming committees with
rotation tiers, audience reach by segment, and era-dependent channel gatekeeping.

### 9.5 Media and news
Coverage from canonical events, weighted by newsworthiness and outlet taste; rumours can be
false. Coverage feeds recognition, sentiment and observations.

### 9.6 Live, events, endorsements
Promoters offer dates from observed demand; tour routing has calendar and cost; opening slots
on bigger tours are opportunities. Events/private gigs where markets have them. Brands choose
endorsers by value and image fit.

### 9.7 Awards
Voting-body models (juries with tastes, member voting, sales components, fan votes), with
categories and eligibility windows by year.

### 9.8 Careers, groups, trainees
Skill growth and decay; wellbeing and burnout; ageing valuation curves as data. Training systems
(where markets have them) with evaluations, debut selection and dropouts. Group dynamics:
popularity disparity, line and pay distribution, relationships, solo ambitions, disputes, splits,
reunions, and disbandment hazards around contract horizons.

### 9.9 Agents and the opportunity detector
- **Utility-based agents** for people and organisations, acting every week regardless of the player.
- **Opportunity detector:** each week, organisations compare observed signals with expectations.
  On positive surprise they generate and rank actions (extend the campaign, add a single, a remix
  for another format, a second video, more TV, a soundtrack/ad tie-in, a foreign release, a tour,
  a repackage). They fund those within budget. On negative surprise they cut losses.
- **Rivalries** among acts, labels and fandoms influence timing, booking politics and mobilisation.

### 9.10 Personal life
Tracked insofar as it affects the career and narrative; hazards per real-person policy (§11.7).

---

## 10. Economics

All money goes through a double-entry, multi-currency ledger with historical FX and inflation
(data). **Label revenue ≠ artist income.**

### 10.1 Contract kinds (typed; norms are market/era data)
| Contract | Key terms |
|---|---|
| Recording | royalty basis and rate (era-specific: retail, wholesale/PPD), deductions (packaging, free goods, new-media), advance, recoupables (recording, part of video, tour support), commitment + options, territory, term, controlled-composition clauses |
| Integrated agency | term, revenue splits by income type, cost deduction before split, training-cost recoupment, penalties |
| Management | commission, term, sunset |
| Publishing/songwriter | splits, publisher share, advance, admin/co-pub, society membership |
| Producer | fee + points; beat/track sales |
| Licensing (cross-market) | territory, royalty to licensor, marketing commitments, term |
| Live, endorsement, distribution | guarantees vs splits; fees, exclusivity, morality clauses; distribution fee |

### 10.2 Waterfall per unit sold
Consumer price → retail margin → distributor fee → label receipts → mechanicals to publishers
(statutory/negotiated by market/era) → artist royalty to recoupment account → manufacturing,
marketing, overhead → label profit. The artist is paid only once recouped.

### 10.3 Other income
Performance royalties (societies, with payout lags), broadcast fees, live, merch, endorsements,
soundtracks, licensing abroad, catalogue over decades.

### 10.4 Organisation P&L and corporate dynamics
Label distress, roster cuts, sales and mergers arise from simulated finances, with historical
consolidation as probabilistic pressure.

### 10.5 Personal finance
Gross → commissions/splits → taxes (data) → lifestyle (tiers, creep) → savings, debts, investments.

---

## 11. Historical data, evidence and acquisition

### 11.1 Evidence tiers
| Tier | Meaning | Shown as history? |
|---|---|---|
| A | Primary/authoritative (published chart runs, statutory rates, dated institutional changes) | Yes |
| B | Sourced estimate (reported sales, industry-report market sizes) | Yes, as "reported" |
| C | Model estimate (fitted attributes, §6.2) | No, internal |
| S | Simulated (anything after start) | In-world only |

### 11.2 Research ledger
`data/research_ledger.csv` holds each claim with scope, value, tier, sources and status
(`open | verified | disputed`). Disputed values become ranges for calibration.

### 11.3 Staged, cached, restartable pipeline
Stages `discover → fetch → parse → normalise → reconcile → tier → export`. Each is idempotent,
checkpointed, rate-limited and keyed by source+query+version, with raw responses cached.
Entity resolution handles romanisation, stage names and group vs member credits, with manual override files.
**Sources:** open data first (MusicBrainz, Discogs dumps, Wikidata); reference lists as pointers
to primaries; official archives where terms allow (chart publishers, certification databases,
industry reports); press archives for tier B. Terms of use are recorded per source; nothing is
bulk-scraped against terms.

### 11.4 Progressive datasets (never blocking the engine)
Each market/era starts with a **representative dataset**: enough real acts, releases and
institutions to make the competitive field credible. Generated fictional NPCs fill the long
tail, clearly labelled. Datasets expand by era window over time.

### 11.5 Structural history (data, per market)
Technology (CD, MP3/P2P, downloads, ringtones, streaming), macro (recessions, financial crises,
pandemic), regulation, media launches. These are environmental conditions, not outcomes.

### 11.6 Real-person policy
Professional outcomes are simulated for everyone. Scandals, health, crime and private-life
events are off by default for real people; configurable per campaign.

---

## 12. Chart and ranking engine

### 12.1 Methodology objects (data)
Every chart, ranking show, certification and sales-based award is a versioned methodology:
```yaml
id: us.billboard.hot100            # illustrative; values are research targets
versions:
  - valid: [1958-08-04, 1991-11-29]
    inputs: [store_rank_reports, station_playlist_reports]
    measurement: {type: rank_report_panel, noise: high, manipulable: true}
  - valid: [1991-11-30, ...]       # BDS airplay + SoundScan sales (verify end)
    inputs: [airplay_audience, sales_panel]
    eligibility: {commercial_single_required: true}   # until rule change (verify date)
  - ...                            # downloads from 2005-02-12; streaming later (verify)
```
A methodology defines: inputs (measured, never true values), formula and weights, tracking
window, publication lag, eligibility, special rules (recurrent rules, retirement after N wins,
holiday freezes), size and subject (song/release/act).

### 12.2 Guarantees
- Charts are computed only within validity windows and in markets where they exist (tested).
- The same consumption measured differently produces different chart dynamics: rank-report
  eras give slower climbs, while point-of-sale tracking gives higher debuts. This is
  emergent, and it is a calibration check.

### 12.3 Measurement layer
`measured = true activity × panel coverage(channel, era) × reporting noise + manipulation`.
Rank-report eras simulate store and station reports with bias. Manipulation channels (bulk
buying, report inflation, vote mobilisation) are explicit, era-gated and detectable.

### 12.4 Initial methodology research targets (all *(verify)*; Phase 1 needs US and KR only)
| Market | Institutions |
|---|---|
| US | Billboard Hot 100 and Top Pop Albums/Billboard 200 (SoundScan albums from 1991-05-25, Hot 100 BDS+SoundScan from 1991-11-30, downloads from 2005-02-12); Hot Black Singles (renamed Hot R&B Singles in Oct 1990; R&B/Hip-Hop naming from Dec 1999); Black/R&B albums; rap, AC and rock charts; airplay charts; RIAA certifications with dated thresholds; Grammys, AMAs, Soul Train awards; MTV and BET programming |
| KR | Monthly album sales charts published by industry associations (RIAK/MIAK, ~1998–2008; sources conflict on dates); broadcast music shows with ranking systems and retirement rules (KBS, SBS, MBC programs and their validity windows); year-end awards; Hanteo; later digital charts (Melon, Gaon → Circle) |
| UK `[later]` | Official Singles/Albums Charts by compiler era; downloads 2005; streaming 2014/2015; BPI certifications; BRITs; music press |
| JP `[later]` | Oricon weekly charts; Billboard Japan; RIAJ certifications |

---

## 13. Narrator–engine interface

### 13.1 Roles
The engine is authoritative for numbers, rankings, money, contracts, calendars, canonical
events and NPC decisions. The narrator is creative: scenes, dialogue, atmosphere, media voice
and inner life, plus **proposals** for new people, opportunities, relationship moments and
creative briefs.

### 13.2 Manual loop (until the API)
1. The player sets decisions and standing orders, then runs `play`.
2. The engine advances until an interrupt and writes `pass_NNNN.md` (human-pasteable, with an embedded JSON block).
3. The player pastes the pass, plus the narrator contract (`docs/narrator_contract.md`) on first use, into ChatGPT.
4. ChatGPT writes the narrative plus a fenced `proposals` JSON block.
5. The player runs `submit`: the engine validates and resolves the proposals, and the results appear in the next pass.

Later, an HTTP API (OpenAPI for ChatGPT Actions, and/or MCP) automates steps 3–5.

### 13.3 Fact packet
Header (campaign, period covered, location, protagonist snapshot); digest of canonical events
with plain-language causes; scene hooks; pending decisions with engine-computed trade-offs;
dossiers of relevant people (personality, goals, relationship, salient memories); industry
context (published charts, competitor activity, gossip with official/reported/rumour tags);
quotable numbers with provenance; creative descriptors of new recordings; constraints.
It contains only what the protagonist could know. Estimates carry their uncertainty.

### 13.4 Narrator latitude
- **May invent freely:** texture, minor dialogue, background people without consequences.
- **Must propose:** anything consequential (new named industry people, offers,
  collaborations, relationship shifts, scandals, creative choices, money, bookings).
- **Must never state:** numbers or outcomes not in the packet, or private information
  the protagonist could not know.

### 13.5 Proposal pipeline
The pipeline runs schema → feasibility → plausibility prior → resolution → persistence:
- **Feasibility** checks existence, availability, budget, era-possibility and acquaintance.
- **Plausibility prior** uses the same agent utility models as everything else.
- **Resolution** accepts, modifies or rejects; any random roll is logged.
- **Persistence** records canonical events and memories.

Results and reasons come back in the next packet. Wording cannot raise odds.

### 13.6 Approval and delegation
`PlayerPolicy` standing orders: always ask for contracts, releases, major creative commitments,
career redirections, public statements, lineup changes and large spending. Delegate routine
bookings, interviews and minor deals to the team AI within the stated preferences, and report
them in the digest.

### 13.7 Consistency checker
Flags numbers, rankings, outcomes and new named people in the narration that are not in the
packet or proposals (basic in Phase 1, full with the API).

---

## 14. Validation scenarios

Both scenarios are **data-only** campaign presets on the same engine. Neither is special-cased.

### 14.1 Scenario A — United States, late 1980s → early 1990s (first-class)
- **Window:** data covering ~1985–1993, so starts in 1986 or 1991 both work. The default test
  run starts in 1988–89 so that the 1991 Billboard measurement change happens mid-campaign.
- **Protagonist:** fictional emerging pop/R&B singer (configurable), aspiring or newly signed.
- **Field:** ~80–120 real acts across pop, R&B/soul, new jack swing, hip-hop, dance, rock and
  AC, with catalogues, labels, teams and intents. Major label groups and key independents.
  Generated NPCs fill the long tail.
- **Systems exercised:** US recording contracts and recoupment; singles and album promotion;
  radio formats and crossover; independent promotion (optional); music video channels;
  retail with rank-report vs point-of-sale measurement; touring and opening slots; RIAA
  certifications; awards; competition for airplay, TV and wallets.

### 14.2 Scenario B — South Korea, late 1990s
- **Window:** data covering ~1996–2001.
- **Protagonist:** fictional emerging artist under an integrated agency (configurable).
  Importing an earlier roleplay character is optional and not required.
- **Field:** ~40–60 real acts across idol pop, ballad, dance, hip-hop/R&B, rock and trot;
  major agencies; broadcasters' music programs; generated NPCs.
- **Systems exercised:** integrated agency contracts and training; physical album economics;
  broadcast music-show booking and ranking rules; fandom organisation and mobilisation;
  monthly association sales reporting; events and endorsements income; the 1997–98 financial
  crisis as structural history.

### 14.3 What the pair proves
They test different organisational models, media gatekeepers, measurement systems, audience
structures and fan cultures through one core. Market-specific code in core systems is a test failure.

---

## 15. Calibration, reports and testing

### 15.1 Targets (distributions, not individual outcomes)
- **US:** debut-rank distributions before/after 1991; weeks-at-#1 distributions; climb speeds;
  album sales tail; certification counts per year; label market shares; crossover frequency
  (R&B → pop); new-act breakthrough rates.
- **KR:** monthly top-album sales distribution; annual top-50 shape; very-large-seller counts;
  agency shares; group survival curves.
- **Cross-cutting:** hit lifetimes, song-vs-album divergence frequency, sleepers, superstar
  misfires, newcomer #1 frequency, trend turnover.

### 15.2 Methods
Batch runs over seeds; loss functions (quantile/KS); coordinate search, then Bayesian
optimisation with held-out years; historical coverage test (real outcomes inside the simulated
10–90% band ~80% of the time); sensitivity analysis; emergence checks; warm-start continuity.

### 15.3 Calibration reports (what you review)
`tools/calibration_report --scenario <id>` produces a readable report:
- Simulated vs historical distributions per target, with pass/fail against tolerance.
- **Real-artist plausibility:** for each major real act, the distribution of simulated
  outcomes over N seeds with no player, compared with their real record. For example:
  "Act X reaches #1 album in 64% of seeds (real: yes); median certification 4× vs real 6×."
- Flags for implausible fitted attributes and the largest sources of uncertainty.
- Divergence summary: how often history repeats versus changes.

### 15.4 Divergence sanity
Real historical #1s should be likely but not guaranteed. 100% means the model is scripted;
~0% means it is miscalibrated.

### 15.5 No ceilings test
An exceptional synthetic newcomer release must, over many seeds, exceed the era's historical
maximum at a small, non-zero rate.

### 15.6 Test suite
Unit; property (money conservation, no negative inventory, no overlapping mandatory
commitments, all draws logged, provenance for every published number); **neutrality lint** (no
country/year/genre/institution literals in core/system code); **scenario matrix** (every test
runs on both validation scenarios); era-gating; no-future-knowledge; determinism/replay; fairness
(protagonist ↔ identical NPC); album/song separation; warm-start continuity; golden-seed regression.

---

## 16. Phased roadmap

Each phase ends runnable, tested and with an updated implemented-vs-planned table.

**Phase 0: Universal foundations**
Core (clock, RNG, events/provenance, ledger, config layering, observation, memory, LOD
framework, save/replay), archetype interfaces, campaign builder skeleton, data pipeline
skeleton and research ledger, shared-core contract document.
*Done when:* a synthetic two-market dummy world runs deterministically for years and replays exactly.

**Phase 1: Universal engine + two validation scenarios (the first playable prototype)**
- 1a: Core systems (creative model, listener dynamics, agents, labels, radio/TV archetypes,
  retail and measurement, chart engine, contracts and ledger, narrator loop v1), developed
  against **Scenario A (US)** data.
- 1b: **Scenario B (KR)** data pack (integrated agency, ranking shows, monthly reporting) on the
  unchanged core. Any core change required here is a generalisation, not a special case.
- Calibration reports v1 for both.
*Done when:* both scenarios are playable through multiple release cycles with a configurable
protagonist, real artists act autonomously, every number is traceable, and neutrality and
scenario-matrix tests pass.

**Phase 2: Living industry depth**
Richer agents and goals, writer/producer careers, label finances and corporate dynamics, media and
rumours, relationship/memory depth, group dynamics, touring.

**Phase 3: Cross-market careers and economics completeness**
Licensing and affiliates, localisation, foreign promotion, coarse-to-full LOD promotion, full
royalty waterfalls, publishing and societies, awards voting bodies.

**Phase 4: Era and market expansion**
US 2000s (hip-hop deals, radio, the digital transition), UK mid-1990s, Japan, then later eras
through 2026. Each expansion is data plus, at most, archetype parameters.

**Phase 5: Narrator API**
HTTP/OpenAPI (ChatGPT Actions) and/or MCP, full consistency checker, multi-campaign sessions.

**Phase 6: More professions + shared core with the acting engine**
Songwriter, producer, manager and label-executive roles; extraction of the shared core package.

---

## 17. Compatibility with the acting engine

The projects are developed in parallel and must not disrupt each other.
- No cross-repo imports now. Both follow a **shared core contract** (`docs/core_contract.md`,
  written in Phase 0):
  - IDs `"<kind>:<id>"`; ISO dates; a daily clock with weekly decision ticks.
  - Hash-based RNG streams.
  - Event schema with namespaced types (`music.*`, `film.*`) and `causes[]`.
  - Double-entry multi-currency ledger.
  - Observation, Relationship and Memory schemas.
  - Narrator packet and proposal envelopes.
- Contract changes are proposed in both repos before adoption.
- **Later:** extract `simcore`, with music and film as industry modules over one world, where a
  Person can be both singer and actor and calendars, fame and relationships are shared.

---

## 18. Failure modes from previous roleplays → structural fixes

| Previous failure | Structural fix |
|---|---|
| Fictional songs repeatedly entering at the same low positions | Positions emerge from a competitive pool with heterogeneous creative attributes, exposure and fandom; debut-distribution regression test |
| Mechanical climbs independent of promotion/response | Ranks come from measured consumption driven by exposure and liking dynamics |
| Historical stars permanently in historical positions | Soft intents with simulated outcomes; divergence sanity test |
| Success artificially limited | No caps; fat tails; no-ceiling and fairness tests |
| Labels not exploiting opportunities | Opportunity detector and portfolio AI |
| Album and singles popularity conflated | Separate demand channels with market/era conversion; separation test |
| Numbers changing without cause | Event log with causes; `inspect why` |
| Modern methodology applied to the past | Date-gated methodology objects; era-gating test |
| All music equally effective | Creative attribute vectors, segment appeal, separate criticism |
| Engine built around one artist or market | Neutrality lint; data-only scenarios; two-market scenario matrix |

---

## 19. Decisions needed before Phase 0 code

1. **Scenario A default start:** 1988–89 (so the 1991 measurement change happens in play) is
   recommended for testing; 1986 and 1991 starts will also be supported by the same data. OK?
2. **Real-person policy:** keep the default (§11.6)?
3. **Calibration tolerance:** e.g. key simulated distributions within ±25% of reference quantiles?
4. **Packet format for the manual loop:** Markdown with an embedded JSON block (recommended)?
5. **Technology:** Python 3.11+, numpy, SQLite, PyYAML, pytest; later FastAPI. OK?

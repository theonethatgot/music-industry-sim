# Music Industry Simulator — Technical Design (v0.1, pre-code)

A persistent, historically grounded, autonomous music-industry career simulation
(1980–2026, multi-country). The Python engine owns every consequential fact; an AI
narrator (initially ChatGPT, used manually) turns engine output into immersive
story and can *propose* developments, which the engine validates, resolves and records.

This document covers the architecture, world-state schema, simulation systems,
narrator–engine interface, data acquisition, chart calculation, calibration and
phased roadmap. Nothing here is implemented yet.

**Conventions**
- `[P0]`…`[P7]`: the phase in which a feature is planned (§12).
- `T` = hidden true value. `O` = an observation of it (noisy, biased, dated; §3.12).
- **Evidence tiers** for every data value and parameter (§9.1):
  `A` verified from a primary/authoritative source · `B` sourced estimate ·
  `C` model estimate (documented rubric) · `S` simulated (never presented as history).
- Historical facts in this document that still need primary-source verification are
  marked *(verify)*. Nothing marked *(verify)* may be hard-coded as tier `A`.

---

## Table of contents
1. Design principles → engineering rules
2. Architecture, time, determinism, persistence, campaigns
3. World-state schema
4. Creative model: songs as creative products
5. Hit formation and consumption
6. Industry systems (labels, media, retail, live, awards, careers, NPC behaviour)
7. Economics
8. Chart and ranking engine
9. Historical data, evidence and acquisition
10. Narrator–engine interface
11. Calibration and testing
12. Phased roadmap (first test: South Korea late 1990s; second: US early 1990s)
13. Compatibility with the acting engine
14. Failure modes from previous roleplays → structural fixes
15. Decisions needed before Phase 0 code

---

## 1. Design principles → engineering rules

| Principle | Engineering rule |
|---|---|
| **Engine owns the truth** | Sales, streams, airplay, chart positions, money, contracts, relationships, calendars and canonical events exist only in engine state. The narrator reads a fact packet and submits proposals; it can never write state directly. |
| **The player is an NPC with a human controller** | Player and NPC artists go through identical code paths. No outcome function receives `is_player`. A statistical fairness test enforces this (§11.5). Player control differs only in *who makes the decisions*, never in how decisions resolve. |
| **No ceilings, no floors** | No rule caps an act's sales, chart position or fame relative to historical stars. No rule guarantees success either. Fat-tailed outcomes are calibrated so unprecedented success is rare but reachable through causes. |
| **Causal randomness** | Randomness enters only as logged shocks on top of causes (reception, a viral moment, a stage mistake, an illness). Every number has a provenance chain (`why <fact>`). |
| **History as prior, not script** | Real artists, labels, releases and industry structures seed the world and its future *intentions*. Every outcome after the start date is simulated, so real stars can over- or under-perform history. |
| **No future knowledge** | NPC decisions use only observations dated at or before "now". Structural history (e.g. the MP3) arrives as an event; nobody anticipates it. A lint test forbids decision code from reading the history-intent tables (§11.5). |
| **Era- and country-correct measurement** | Charts, music shows and certifications are versioned *methodology objects* with validity dates per country. A chart cannot exist outside its validity window (§8). |
| **Separate signals stay separate** | Physical sales, singles purchases, downloads, streams, airplay, TV exposure, karaoke, public recognition, fandom activity and music-show results are distinct state variables. They influence each other through explicit, logged mechanisms, never by aliasing. |
| **No single quality score** | Songs carry a creative attribute vector; appeal is computed per audience segment; critical and commercial reception are separate processes (§4). |
| **No single popularity score** | Artist status is a vector of recognition, fandom, singles power, album power, live demand, leverage, prestige, reach and momentum (§3.4). |
| **Imperfect information** | Labels, programmers, media and the player decide from observations (A&R ears, call-out research, shipments, charts, gossip). This produces believable misjudgements. |
| **Configurable, not hard-coded** | All coefficients live in versioned YAML, per era and country where needed. Code holds structure only. |
| **Reproducible** | `state(t) = f(scenario, data_version, config_version, seed, ordered_command_log)`. |

---

## 2. Architecture

### 2.1 Repository layout
```
music-industry-sim/
  engine/
    core/                 # mirrors the acting engine's core (§13); no cross-repo imports
      clock.py            # dates, daily/weekly scheduling, event queue
      rng.py              # named deterministic RNG streams
      events.py           # append-only event log + provenance
      state.py            # WorldState, registries, indexes
      commands.py         # command & proposal schemas, validation pipeline
      ledger.py           # double-entry accounts, multi-currency
      observe.py          # observation layer (who knows what, with what noise)
      config.py           # YAML loading, era/country interpolation, hashing
      memory.py           # relationship edges + episodic memories
    models/               # dataclasses: Person, Act, Composition, Recording, Release...
    markets/              # country rule packs (one sub-package per country)
      base.py             # MarketRules interface
      kr/  us/  uk/  jp/  # formats, media, retail, charts, awards, contract norms
    systems/              # one module per simulation process (§4–§7)
      culture.py  creative.py  anr.py  release.py  promotion.py  media.py
      exposure.py  demand.py  retail.py  digital.py  live.py  fandom.py
      reception.py  charts.py  awards.py  careers.py  groups.py  contracts.py
      finance.py  labels_ai.py  npc_ai.py  news.py  history.py  opportunities.py
    narrator/
      factpacket.py       # builds narrator packets (§10)
      proposals.py        # validates/resolves narrator proposals
      checker.py          # number/claim consistency checker
  data/
    raw/                  # cached downloads (gitignored), keyed by source+hash
    curated/              # tiered CSV/YAML with source references (committed)
    reference/            # calibration targets (historical distributions)
    scenarios/            # campaign definitions (start date, country, protagonist)
  config/
    default.yaml  eras/  countries/
  pipeline/               # staged, restartable data collection (§9)
  cli/                    # play loop for manual narrator exchange
  api/                    # [P6] HTTP/OpenAPI wrapper (ChatGPT Actions / MCP)
  tools/                  # batch runs, calibration, replay, inspect, divergence report
  tests/
```

### 2.2 Time model
- **Date resolution: one day.** Consumption (listening, purchases, airplay,
  TV exposure) is simulated **daily** with vectorised maths. That makes every chart
  tracking window, release weekday and broadcast day exact, without special cases
  for the many different chart weeks around the world.
- **Decision cadence: weekly.** Labels, programmers, managers and other NPCs make
  decisions once per simulated week, plus event-driven decisions such as offers,
  deadlines and crises.
- **Scheduled-event queue:** a priority queue keyed by `(date, seq)` carries releases,
  broadcasts, chart publications, contract expiries, award ceremonies and recording sessions.
- **Narrative pacing is independent of the tick.** The player advances by
  `advance 3d | 2w | 4m | until <event>`. The engine stops early at an **interrupt**:
  a decision needing player approval (§10.6), a major event, or an opportunity
  above a salience threshold. One narrative pass can cover a day of a
  music-show taping or four quiet months in the studio.

### 2.3 Determinism and RNG
- Each draw uses `rng(seed, system, entity_id, purpose, date)`, a hash-derived
  stream. Adding an NPC or a system never shifts other outcomes.
- Entities are always iterated in sorted-ID order. There are no parallel
  reductions in the canonical path.
- Every draw is logged with its inputs in the event log.

### 2.4 Persistence and audit
- **Save = SQLite snapshot + event log + command log + proposal log + config hash
  + data version.**
- Event rows: `{event_id, date, system, type, entities, inputs_digest, draws, outputs, causes[]}`.
  `causes[]` links to upstream events, which gives the provenance graph.
- `tools/inspect why <fact>` walks that graph. For example, `why song:812.kr.miak.1999-03.rank`
  shows the monthly sales, the main days behind them, and the exposure sources behind those days.
- **Replay test:** snapshot + command log must reproduce the saved state hash.

### 2.5 Campaigns and worlds
A **campaign** is an independent world: `{scenario, seed, data_version,
config_version, saves/, logs/}`. Scenarios are data files, not code:
```yaml
# data/scenarios/kr_1997_debut.yaml (example; the protagonist is data, not hard-coded)
id: kr_1997_debut
start_date: 1997-03-01
markets_active: [KR]            # full simulation
markets_background: [JP, US]    # coarse simulation (export, influence)
protagonist:
  kind: new_person              # or: existing_person (play a real/fictional NPC)
  template: data/scenarios/protagonists/bae_yeora.yaml
  start_role: trainee           # trainee | soloist | group_member | producer | ...
  affiliations: [org:kr.dsp]
structural_history: on          # technology, macro, policy events
contingent_history: intents     # real releases/debuts as soft intents (§9.5)
real_person_policy: default     # §9.7
```
Several campaigns can coexist, each with its own save directory and divergent history.

---

## 3. World-state schema

Scales are 0–100 unless noted. Vectors are keyed dicts. Every attribute is stored
with its evidence tier, and with `estimation_confidence` when seeded from history.

### 3.1 Shared base entities (kept compatible with the acting engine, §13)
```
Person
  id ("person:<slug-or-uuid>"), names {native, romanised, stage[]}, birth_date,
  gender, nationality, languages {lang: fluency}, is_historical, evidence
  roles: set{performer, songwriter, producer, manager, executive, a&r, ...}
  personality: ambition, risk_tolerance, artistic_vs_commercial (−1..1), loyalty,
               temperament, discipline, ego, sociability, resilience
  goals: weighted {money, fame, artistry, stability, power, approval, freedom}
  wellbeing (T): energy, health, stress, morale (burnout and illness hazards)
  finances → Account; calendar → Commitment[]; memories → Memory[]
Org
  id, kind {label, imprint, agency, management, publisher, distributor, broadcaster,
            radio_station, tv_program, retailer, platform, promoter, venue,
            media_outlet, chart_publisher, awards_body, trade_body, brand},
  country, parent_org, people (roles), finances → Account, strategy (AI params)
Relationship (directed edge person/org → person/org)
  affinity (−100..100), trust, respect, debt_of_favour, rivalry, history[event_id]
Memory (episodic, for continuity and narration)
  owner, about[], event_id, date, gist (short structured text), valence,
  salience (decays; refreshed when recalled or reinforced), public|private
Commitment: owner, kind, start, end, location, org, mandatory, conflicts_with[]
Contract (generic envelope; terms are typed per contract kind, §7)
```

### 3.2 Music professional profiles (attached to Person)
| Field | T/O | Meaning |
|---|---|---|
| `vocal` | T | vector `{technique, tone_distinctiveness, range, stamina, live_stability}` |
| `dance_performance` | T | choreography execution, stage power |
| `stage_presence` | T | charisma in performance; drives TV and live impact |
| `variety_skill` | T | talk/variety/radio-host ability (critical in KR/JP promotion) |
| `visual_market_value` | T | how *the market* currently values the person's image. It follows configurable era/country/gender curves; this models industry bias and is not a judgement. |
| `songwriting` | T | vector `{melody, lyrics, structure, hook_craft}` + `style_skill` over the style space |
| `production` | T | `{arrangement, sound_design, mixing, vocal_direction}` + style skill |
| `musicianship` | T | instruments, theory (affects self-sufficiency and credibility) |
| `craft_growth` | T | learning rate; grows with training, work and strong collaborators |
| `artistic_identity` | T | position in style space + persona tags (§4.2) |
| `reputation_professional` | O | reliability, as rumoured in the industry |
| `scandal_hazard` | T | disabled for real living people by default (§9.7) |

### 3.3 Act (the performing entity)
Real careers distinguish the *person* from the *act*: a soloist is an Act with one
member, and groups have membership histories.
```
Act
  id, name, kind {solo, group, unit, duo, project, band}, country_of_origin
  members: [{person_id, role {main_vocal, rapper, dancer, leader, visual, instrumentalist...},
             joined, left, reason}]
  concept/brand: style position, persona tags, image (e.g. "innocent", "tough",
                 "girl-next-door", "artist-auteur"), target segments
  label_id, management_id, contracts[]
  status vector → §3.4;  fandom → §3.5;  catalogue → releases[]
  lifecycle stage: pre-debut | rookie | rising | established | peak | veteran
                   | hiatus | disbanded | legacy   (descriptive, derived from status)
```

### 3.4 Status vector (per act, per market, and for key persons)
These are kept separate on purpose. Each is updated by named mechanisms (§6.8).

| Component | Definition | Main drivers |
|---|---|---|
| `recognition[market][segment]` | share of population who know the act by name/face | TV, radio, hits, endorsements, news |
| `public_appeal[market][segment]` | mean liking among recognisers | songs' appeal, image, scandals |
| `fandom` | object (§3.5) | conversion of liking into identity |
| `singles_power` | expected song-level audience pull (O: industry belief) | track record of song reach |
| `album_power` | expected album purchase pull | fandom × collectability × casual conversion |
| `live_demand` | ticket/event demand by city tier | fandom, recognition, live reputation |
| `endorsement_value` | CF/brand value | recognition × image fit × scandal risk |
| `leverage` | bargaining power with labels/broadcasters | O-ish: perceived outside options |
| `critical_prestige` | critics' running assessment | reception of releases (§5.9) |
| `industry_respect` | peers, producers, PDs | professionalism, craft, relationships |
| `reach[region]` | international recognition | exports, licensing, touring abroad |
| `momentum` | recency-weighted *surprise* (outcomes vs expectations) | beating or missing expectations |
| `sustainability` | risk indicators: fatigue, over-exposure, fandom churn, members' contract horizon | schedule, saturation, internal tension |

The industry never sees true values. Labels and media act on `O` versions
(for example `singles_power_O` is a Bayesian estimate from attributed results), so
an act can be under- or over-rated.

### 3.5 Fandom (per act per market)
```
Fandom
  size_by_tier {core, active, casual}        # people
  segment_mix                                # age/gender/region composition
  loyalty (churn hazard), intensity distribution
  organisation: {official_club, membership, colour/symbol, leaders, chapters}
  purchase_propensity {album, multiple_copies, merch, tickets}
  mobilisation {voting, requests, attendance, chart_activity} (era-dependent tools)
  morale (reacts to treatment, scandals, hiatus, member changes)
  rivalries {fandom_id: intensity}            # fan wars; affects mobilisation
  identity_attachment {act, members[]}        # member-specific fandom → solo spin-offs
```
In late-1990s Korea, organised fan clubs, coloured balloons and attendance at
broadcasts were real mobilisation tools *(verify details per act)*. In streaming eras
the tools become streaming campaigns and voting apps. The **tools are era-gated**;
the fandom psychology is shared.

### 3.6 Creative works (separated deliberately)
```
Composition (the song as written; publishing lives here)
  id, title, writers [{person_id, share}], publishers [{org_id, share}],
  language, creative attributes (§4.1, composition-level), created_date, demo_quality
Recording (a specific performance/production of a composition)
  id, composition_id, performers [act/person], producers[], engineers[],
  session dates, cost, creative attributes (§4.1, recording-level), version {original,
  remix, live, acoustic, translated}
Release (a commercial package)
  id, act_id, label_id, kind {album, mini_album/EP, single, repackage, compilation,
  OST, special}, tracklist [recording_id], focus_tracks (lead/follow-up singles),
  markets, release_dates {market: date}, cover/visual concept, price tier
Product (SKU per format, per market)
  release_id, format {LP, cassette, CD, CD_single, cassingle, 7", 12", VHS/DVD,
  digital_album, digital_track, ringtone, ...}, list_price, dealer_price,
  pressing/manufacturing cost, editions (photobook, limited, version A/B)
Campaign (a promotion cycle around a release)
  release_id, start, planned_end, budget lines, focus_track per week,
  bookings[], MV[], marketing actions[], status
```

### 3.7 Markets
```
Market (country)
  population by Segment (age band × gender × urban/rural/region × taste cluster)
  music_spend per segment (era table, inflation-adjusted, macro shocks)
  format_adoption curves (share of segment able/willing to buy each format)
  media diet per segment: TV hours by channel, radio listening by format/station,
                          music-TV access, internet/platform adoption
  karaoke/noraebang usage, concert-going, travel/region weights
  price tables, currency, inflation, exchange rates
  rule pack → markets/<cc>/ (charts, awards, contract norms, release weekday,
               retail structure, broadcasting regulation)
Segment taste state (§4.3): position in style space, novelty appetite, openness
               to foreign/other-language music, genre affinities, drift velocity
```

### 3.8 Media and channels
```
Broadcaster/Program: schedule (weekday/time), audience by segment (era), slots per
  episode, booking policy (status thresholds, PD relationships, label politics,
  quota rules), ranking system (§8) if any, live/pre-recorded, stage quality factor
RadioStation: format, audience by segment, playlist size, rotation categories
  (power/medium/light/recurrent), programmer person, research method, ad climate
MusicTV/Platform: rotation tiers (MTV-era), later playlists/recommendation (§5.6)
MediaOutlet: kind {newspaper, sports daily, magazine, trade, online, critic},
  readership by segment, editorial taste, sensationalism, relationships
```

### 3.9 Retail and distribution
```
Distributor: reach by channel, terms (distribution fee), credit risk
RetailChannel: record shops (chain/indie), department stores, street stalls,
  later online retail/platforms; stock policy; reports to which chart panels
Inventory per Product: pressed, shipped (sell-in), in-store, sold (sell-through),
  returned, reorder lead time
```
**Shipments, sales, reported figures and claimed figures are four different
numbers** (§5.8). Korean and other labels historically announced shipment or
claimed figures *(verify by period)*. The engine records each one separately.

### 3.10 Charts and rankings
```
ChartDefinition: id, country, publisher, name, methodology versions[] (§8)
ChartRun: chart_id, methodology_version, period (tracking window), publish_date
ChartEntry: run_id, rank, subject (release/recording/act), score, components{},
  last_rank, peak, weeks_on, flags {debut, re-entry, retired, ...}
```

### 3.11 Opportunities and events
```
Opportunity: id, kind {booking, collaboration, OST, CF, feature, overseas_release,
  tour_support, label_offer, song_pitch, variety_show, ...}, source (org/person),
  target, terms, expiry, preconditions, originator {npc|narrator|player}, salience
WorldEvent: canonical event (release, win, scandal, signing, disbandment...);
  public|private; narrative tags; causes[]
```

### 3.12 Observation layer
```
Observation: subject (entity.attr), observer (person/org/"public"), value,
  sigma, bias, source {official, chart, shipment_report, A&R_listen, call-out,
  trade_press, gossip, fan_estimate, own_books}, date, expires
```
The player sees public observations plus those of their own team. Their quality
depends on that team's skill and relationships. NPC organisations decide on their
own observations only.

---

## 4. Creative model: songs as creative products

### 4.1 Creative attribute vector
Attributes are **true values** set at creation and observed with noise by everyone,
including the player's own team.

| Level | Attribute | Effect |
|---|---|---|
| Composition | `melody`, `lyric_craft`, `structure` | base craft; durability |
| Composition | `hook_strength` | speed of first-listen liking; radio/TV impact |
| Composition | `depth` | grower vs burner: liking growth with repetition and fatigue resistance |
| Composition | `singability` | karaoke uptake, crowd participation, word of mouth |
| Recording | `production_quality` | polish relative to era norms (era-relative!) |
| Recording | `sonic_signature` | distinctiveness of sound; drives novelty |
| Recording | `vocal_delivery` | performance emotion/technique as recorded |
| Recording | `arrangement_fit` | how well production serves the song |
| Both | `style_position` | coordinates in style space (§4.2) |
| Both | `accessibility` | how little prior taste the song requires |
| Both | `ambition` | experimental reach (critics often reward it; casual audiences may not) |
| Both | `identity_fit` | fit between song and act's established identity |
| Both | `controversy` | talkability and risk (censorship/broadcast bans by country/era) |
| Performance | `choreography_hook`, `stage_concept` | TV/live impact and imitation (dance crazes) |
| Visual | `mv_quality`, `concept_visual` | MV-era exposure and image formation |

There is **no overall quality score.** Appeal (§4.4) and critical reception (§5.9)
are separate functions that weight different attributes.

### 4.2 Style space
Music is placed in a continuous **style space**: about 8–12 configurable
dimensions such as tempo/energy, valence, rhythmic emphasis (dance vs ballad),
electronic vs acoustic, rawness vs polish, vocal-vs-beat centricity, Western-vs-local
idiom, and lyrical seriousness. It also carries **genre tags** (ballad, dance-pop,
hip-hop, R&B, rock, trot, idol pop, techno, city pop, Britpop...). Genre tags are
labels over regions of the space, and their meaning is era- and country-dependent.
Example: Korean "dance" in 1997 and US "dance" in 1997 are different regions.

### 4.3 Culture and taste dynamics
Each segment has a taste distribution over style space plus a `novelty_appetite`.
- **Bandwagon drift:** successful styles pull segment tastes toward themselves
  (weighted by exposure share). This creates trends endogenously.
- **Saturation:** local density of recent releases in style space lowers novelty for
  similar songs, so trends exhaust themselves and leave room for the next one.
- **Exogenous currents** (structural history, tier B): foreign influence (e.g. US
  hip-hop's influence on 1990s Korean pop), technology (sampling, Auto-Tune),
  regulation. These enter as *slow drift forces*, not as outcomes for specific songs.
- **Generational turnover:** cohorts age through segments, keeping the tastes they formed young.

### 4.4 Appeal (per song, per segment, per market)
```
appeal_g = taste_match_g(style_position)                 # kernel over style distance
         · craft_g(melody, structure, production_rel_era, vocal_delivery, arrangement)
         · novelty_term_g(sonic_signature, saturation, novelty_appetite_g)
         · accessibility_term_g(accessibility, openness_g)
         · act_term_g(public_appeal of act, identity_fit, visual concept)
         · language/foreignness term (market openness by era)
         · exp(ε_reception)                               # logged, fat-tailed (Student-t)
```
The weights per segment are config, and segments weigh things differently. For example,
teen idol fandom segments put heavy weight on `act_term`, while adult ballad listeners
weight `melody` and `vocal_delivery`.

### 4.5 How creative attributes are produced (creative production system)
Song attributes come from **who made them, under what conditions**, never from
how a narrator describes them.
```
attribute = f(writer/producer skills in this style region,
              collaborator chemistry (relationship + style compatibility),
              time & budget (diminishing returns), studio era tech,
              performer skills (vocal, delivery), brief constraints,
              creative risk taken (variance ↑ with ambition), shock)
```
- **Song market:** writers and producers create compositions continuously and pitch them.
  Labels buy or commission them, A&R ears (observations) choose among them, and
  top writers sell their best songs to the acts with most leverage. A player artist can
  also write their own songs (skill-limited, with identity and royalty benefits).
- **Creative briefs:** the player or narrator proposes a brief (concept, style target,
  producer, schedule, budget). The engine produces the attributes. The narrator then
  describes the recorded result *consistently with them*: for example, "the chorus is
  instantly catchy but the verses feel thin" if `hook` is high and `depth` low.
- **Revision loop:** extra recording time, a different producer or a re-mix can move
  attributes within bounded, costed ranges. That makes creative decisions meaningful.

---

## 5. Hit formation and consumption

This is the heart of the engine. It runs **daily, per song, per market, per segment**.

### 5.1 Listener state model (per song × segment)
```
 Unaware ─(exposure)→ Exposed ─(repeat exposure)→ Familiar ─(liking > θ)→ Engaged
                        │                            │                      │
                        └─ no interest               └─ indifferent         └─→ Fatigued
```
- **Liking evolves with exposure count** (mere-exposure curve). Initial liking is
  driven by `hook_strength`. Peak and decay are driven by `depth`: growers start
  slower but peak higher and later, while burners peak fast and fatigue fast.
- **Engaged listeners** generate demand: requests, purchases, karaoke, streams,
  word of mouth, and conversion to fandom of the act.
- **Fatigue** rises with over-exposure. It is per listener, so heavy rotation kills
  songs as it does in reality.

### 5.2 Exposure channels (daily impressions per segment)
| Channel | Impressions | Notes |
|---|---|---|
| Radio | Σ stations spins × audience_g × daypart | Programmers decide adds and rotation (§6.3) |
| Music TV shows | viewership_g × slot quality × stage_impact | Booking is scarce and political (§6.2) |
| Variety/talk TV | viewership_g × personality airtime | Builds act recognition more than song familiarity |
| Music video TV | rotation tier × channel reach | MTV-era US/UK; KR cable music channels from mid-1990s *(verify)* |
| Drama/film OST, CF tie-ins | show/ad audience × song prominence | Strong in KR/JP |
| Retail/public play | store/street play, noraebang catalogue presence | Ambient familiarity |
| Word of mouth | contacts × engaged share × talkability | Non-linear contagion (§5.3) |
| Fandom evangelism | core/active fans × mobilisation | Front-loaded; mostly reaches the fans' peers |
| Chart & media visibility | published rank prominence, news mentions | Social proof feedback loop |
| Streaming/algorithmic `[P5]` | playlist reach, recommendation | Platform agents with their own logic |

### 5.3 Non-linear hit dynamics
1. **Contagion with thresholds:** WOM rate ∝ `engaged_share^α` (α>1 near tipping) ×
   `talkability`. Songs below the critical mass fade, while songs above it accelerate.
   This is the source of sleepers and breakouts.
2. **Social proof:** chart prominence and "everyone's talking about it" coverage raise
   fence-sitters' liking (bounded). The effect is stronger in conformist segments.
3. **Gatekeeper cascades:** radio adds and TV bookings depend on *observed* momentum
   (requests, sales, call-out), so early organic momentum recruits gatekeepers,
   which brings more exposure.
4. **Label reinvestment:** the opportunity detector (§6.10) sees momentum above
   expectation and increases spend, extends the cycle, or pushes a follow-up.
5. **Cultural moment:** if a song's recognition crosses a high share of the *general*
   population, it becomes a reference point (parodies, dance crazes, news). Talkability
   and act recognition jump, which lifts other songs by the act.
6. **Competition:** exposure slots, radio playlists, TV slots, attention and wallets are
   **shared pools**. A crowded release week matters.
7. **Fat tails:** reception shocks are Student-t, and contagion amplifies them.
   Calibrated on hit-size distributions (§11).

### 5.4 Fandom formation
Engaged listeners convert to casual fans at a rate driven by `act_term`, identity
distinctiveness, member appeal and exposure to *personality* (variety/talk shows,
fan meetings), not only to songs. Fans move up the tiers (casual → active → core)
through sustained engagement and community, and churn through hiatus, scandal,
mistreatment and ageing out. Member-specific attachment is tracked, which enables
realistic solo spin-offs and fan reactions to lineup changes.

### 5.5 Consumption outputs (separate, per day)
| Output | Driven by |
|---|---|
| Album purchases (per format) | core fans (release-day spike, multiple copies), active fans, **casual conversion from engaged listeners of the album's songs** (era/market `conv` factor), perceived album value (track strength, collectability), price, availability (stock), shared wallet |
| Single purchases | engaged listeners × `single_market_strength[era, market]` × availability. UK/US singles markets existed; KR 1990s had little physical singles market *(verify)*, so song demand flows into albums there |
| Airplay | programmer decisions (§6.3); this is an exposure input, also measured for charts |
| Requests/votes | engaged + fandom mobilisation (radio requests, ARS phone votes, later apps) |
| Karaoke | singability × engaged × noraebang catalogue availability (lag for catalogue updates) |
| Downloads/ringtones `[P5]` | digital adoption × engaged × price × piracy pressure |
| Streams `[P5]` | engaged × listening frequency (depth-driven replay) × platform reach |
| Recognition change | exposures to the act (not just to songs) |

**Shared wallet:** each segment has a music budget per period (era/macro table).
Desired purchases across all products compete for it through a constrained choice
model. A blockbuster release can therefore suppress other sales that week, and an
economic crisis (e.g. Korea's 1997–98 financial crisis, tier B) shrinks wallets.

### 5.6 Album vs single separation (explicit)
- A song's popularity is in listener state. An album's sales come from the fandom plus
  casual conversion from engaged listeners of **its focus tracks**, at
  `conv[era, market, segment]`. That rate is high where buying the album was the
  main way to own a hit song, and lower where singles or downloads were available.
- So a ubiquitous song can coexist with modest album sales (low fandom, burner single)
  and a fandom act can top album charts with little general recognition. The
  engine never derives one from the other by a fixed ratio.

### 5.7 Live and events demand
Ticket demand comes from fandom tiers + recognition × appeal + live reputation, by city.
Event bookings (KR university festivals, corporate/local events, overseas showcases)
come from recognition and current-hit familiarity. These can be a major income source
(§7) *(verify KR 1990s event-fee norms)*.

### 5.8 Retail, supply and reported numbers
- Labels decide pressing quantities from their *forecast* (observations). Underpressing
  causes stock-outs and lost or delayed sales; overpressing causes returns.
- `sell_in` (shipments) ≠ `sell_through` (sales) ≠ `reported` (panel-measured) ≠ `claimed`
  (label press release). Labels may inflate claims depending on era norms and their
  personality. Media and fans quote claims; the engine knows the truth.

### 5.9 Critical reception (separate process)
Critics and outlets each have a taste profile. Critics weight `ambition`, `sonic_signature`,
`lyric_craft`, `depth` and coherence across an album. They also have biases (genre
snobbery, nationalism, idol scepticism in some eras). The outputs are reviews, a critical
consensus, `critical_prestige` updates and award-jury inputs. Commercial appeal and critical
reception are correlated only through shared attributes, so an acclaimed commercial flop and
an unacclaimed smash both arise naturally.

---

## 6. Industry systems

### 6.1 Labels and agencies (organisational model)
Country rule packs define the organisational norms. In US/UK, labels, management,
publishing and agents are separate. In KR, integrated entertainment agencies handle
training, production, management and often publishing, with distribution through
third parties *(verify per company and period)*.
```
LabelAI
  finances (cash, credit), overhead, roster, A&R staff (ears = taste accuracy by style)
  strategy: risk appetite, style focus, roster size target, budget bands,
            exploitation aggressiveness, artist-treatment norms
  pipeline: trainees, demos, projects in production, release calendar
  relationships: broadcasters/PDs, programmers, retailers, distributors, writers
```
Labels allocate budgets across their roster to maximise **expected value under their own
beliefs**, with portfolio diversification and calendar-avoidance of big competitors.

### 6.2 Broadcasting and music shows
- Music shows have a fixed number of performance slots per episode. Bookings are
  decided by the program's PD AI: act status (O), current momentum, label relationship,
  diversity rules, scandals and broadcaster politics.
- Stage impact = `performance skills × choreography_hook × stage_concept × live_stability × shock`.
  A great stage raises recognition and liking, and a bad live stage can hurt.
- Ranking systems and their rules (e.g. retirement after N wins) are methodology
  objects (§8). Wins are public events that feed visibility and fandom morale.
- Broadcast bans/censorship rules per country and era (lyrics, language, conduct) *(verify)*.

### 6.3 Radio
Programmer AI per station: add a song when
`score = format_fit + observed_callout + label_pressure + chart/sales signal + relationship
+ request volume − playlist competition` exceeds a threshold. Songs move between rotation
tiers and are dropped when "burn" (fatigue observed in research) rises. Illicit influence
(payola-style practices) is an optional, era-gated mechanic with detection risk *(config;
off by default)*.

### 6.4 Media and news
Outlets generate coverage from canonical events, weighted by newsworthiness and outlet taste.
Coverage is exposure (recognition), sentiment (appeal) and observations (claims, rumours).
Rumours can be false; the engine knows which ones are.

### 6.5 Retail
See §5.8. Retail panels determine what charts can see (§8.3).

### 6.6 Live, events, endorsements
Promoters offer shows from observed demand. Brand AIs pick endorsers by
`endorsement_value` per budget. Contracts include morality clauses where era-appropriate.

### 6.7 Awards
Award bodies are voting systems with methodology versions: sales-based components,
juries with taste profiles, broadcaster-affiliated year-end ceremonies, fan votes. Real
award institutions exist only in their real date ranges, with era-specific categories.

### 6.8 Careers, skills, status updates
- Skills grow with training, work and mentors, and decay slowly when idle. Wellbeing
  falls with overwork; burnout and illness hazards rise.
- Status components update from their named drivers (§3.4). `momentum` = recency-weighted
  `(observed outcome − prior expectation)`.
- Ageing: market valuations follow config curves by era, country and gender (industry
  bias, not judgement). Skills and prestige can keep rising.

### 6.9 Groups, trainees, lineups
- **Trainees:** training curricula, monthly evaluations (observations), debut-team
  selection by the agency AI, dropouts, transfers.
- **Group dynamics:** member popularity disparity, line distribution, pay distribution,
  personal relationships and individual goals. These generate tension, solo
  activities, unit splits, departures, contract disputes and disbandment hazards,
  especially near contract expiry. Real first-generation K-pop groups had high disbandment
  rates around contract renewals *(verify)*. This is a hazard model, not a script.
- **Lineup changes:** fandom identity attachment determines how fans respond.

### 6.10 NPC decision-making and opportunity detection
- **Utility-based agents** (people and orgs): choose among feasible actions by expected
  utility under their goals, risk attitudes and *observations*, with bounded rationality
  (noise, habit, loyalty). Everyone acts every week whether or not the player is involved.
- **Opportunity detector** (labels, managers, media, brands): each week, compare observed
  signals against expectations. When `momentum_O` exceeds a threshold, generate candidate
  actions: extend the cycle, fund a second MV, push a follow-up single, repackage, book
  more TV, an OST or CF tie-in, an overseas release, a tour. Rank them by expected value
  and execute those within budget. This structurally fixes "labels that don't exploit
  obvious opportunities".
- **Rivalries:** acts, labels and fandoms track rivals. Rivalry influences release timing,
  booking politics and fan mobilisation.

### 6.11 Personal life (bounded)
Relationships, health, family and housing are tracked to the extent they affect the career
and the narrative. Events are drawn from hazards for fictional people. For real living
people the policy in §9.7 applies.

---

## 7. Economics

All money flows through the double-entry ledger, with currency per market and
historical exchange rates (tier A/B tables). **Label revenue ≠ artist income.**

### 7.1 Contract kinds (typed terms; country norms in rule packs)
| Contract | Key terms |
|---|---|
| Recording (US/UK style) | royalty % (of retail/PPD by era), packaging/free-goods deductions, advance, recoupable costs (recording, % of video, tour support), album commitment + options, territory, term |
| Exclusive agency (KR style) | term (long terms common historically; later standard contracts *(verify dates)*), revenue split by income type, cost deduction before split, training-cost recoupment, penalty clauses |
| Publishing / songwriter | splits, publisher share, advance, admin/co-pub, collection-society membership (KOMCA, ASCAP/BMI/SESAC, PRS/MCPS, JASRAC) |
| Producer | fee + points; beat/track sale (KR) |
| Management (non-KR) | commission % of gross, sunset clause |
| Live | guarantee vs door split, promoter costs |
| Endorsement | fee, exclusivity, morality clause, term |
| Distribution | fee %, advances to the label |

### 7.2 Revenue waterfall per Product sale
```
consumer price → retailer margin → distributor fee → label gross
label gross → mechanical royalty (publishers → writers, by statutory/negotiated rate per era)
            → artist royalty (accrues to the artist's recoupment account)
            → manufacturing, marketing, overhead → label profit
artist account: royalties − recoupable costs → paid only once recouped (or never)
```
Mechanical, performance and neighbouring-right rates are **era tables per country** (tier A
where statutory, e.g. the US statutory mechanical rate history; collected in Phase 0).

### 7.3 Other income streams
Performance royalties (radio/TV/public play, via societies, paid quarterly or annually with lag),
broadcast appearance fees, event fees, tours, merchandise, endorsements, OST fees, variety
appearances, overseas licensing, catalogue income over decades.

### 7.4 Organisation P&L
Labels: revenue − A&R/recording − manufacturing − marketing − artist/publisher costs − overhead
− interest. Distressed labels cut rosters or get sold. Healthy labels expand. Mergers are
probabilistic pressures driven by simulated finances.

### 7.5 Personal finance
Gross income → agency/management split or commission → taxes (era tables) → lifestyle
expenses (tiered, with lifestyle creep) → savings/debts/investments (simple).

---

## 8. Chart and ranking engine

### 8.1 Model
Every chart, music show ranking, certification and award with a sales component is a
**`Methodology` object**, versioned by date:
```yaml
id: kr.miak.album_monthly            # illustrative; all values pending Phase 0 research
publisher: org:kr.riak_miak
valid: [1998-08, 2008-09]            # (verify start/end; sources conflict)
period: calendar_month
publish_lag_days: 10                 # (verify)
subject: release
inputs:
  - measure: units_reported           # reported by labels/distributors
    source: label_reports
    measurement: {coverage: 1.0, reporting_bias: label_personality, audit: weak}
score: units_reported
eligibility: {formats: [CD, cassette], domestic_release: true}
size: 50
```
```yaml
id: us.billboard.hot100
versions:
  - valid: [1958-08-04, 1991-11-29]      # (verify)
    inputs: [store_rank_reports, station_playlist_reports]
    measurement: {type: rank_report_panel, panel_size: era_table, noise: high,
                  manipulable: true}
  - valid: [1991-11-30, 1998-12-04]      # (verify) BDS airplay + SoundScan sales
    inputs: [airplay_audience (BDS), sales (SoundScan panel)]
    eligibility: {requires_commercial_single: true}
  - valid: [1998-12-05, ...]             # airplay-only songs eligible (verify)
  - ...                                  # downloads (2005), streaming (2012–13) (verify)
```
The engine computes each chart from **measured** data (§8.3), never from true values.

### 8.2 Engine guarantees
- A chart is computed only within its `valid` window, and only in countries where the
  scenario activates it. A test asserts this for every run (§11.5).
- Tracking windows, release weekdays and publication lags come from the methodology,
  together with chart rules (recurrent rules, retirement rules, eligibility, chart freezes
  at holidays).
- The same simulated consumption can produce **different** charts with different
  dynamics. For example, a pre-1991 US panel with rank reports yields slow climbs, while
  SoundScan yields high debuts. This is emergent from measurement, and it is a
  calibration check (§11).

### 8.3 Measurement layer
`measured = true activity × panel coverage(channel, era) × reporting noise + manipulation`
- Panel coverage differs by retailer type, region and era (e.g. early sales panels
  under-represented some store types *(verify)*).
- Pre-tracking-era rank reports: stores report ranks, not units. The publisher
  converts these to points, so the engine simulates store reports from local sales plus bias.
- Manipulation channels (bulk buying, report inflation, vote mobilisation) are explicit,
  era-gated and detectable, with consequences.

### 8.4 Initial methodology registry (to research in Phase 0; all *(verify)*)
| Market | Chart / ranking | Notes for research |
|---|---|---|
| KR | RIAK/MIAK monthly album chart | Monthly top-50 with sales figures from ~Aug 1998 to ~2008 (sources conflict on the exact span) |
| KR | KBS *Gayo Top 10* (1981–1998) → *Music Bank* (from June 1998) | Chart format, weights and retirement rule; Music Bank's chart had periods of abandonment (e.g. 2001–2007) |
| KR | SBS *Inkigayo* (1991–93; revived 1998) | "Mutizen" ranking; chart format removed ~2003 |
| KR | MBC *Music Camp* (1998–2005) | Whether and how it ranked songs in 1998–2002 |
| KR | Radio and print charts, Hanteo (founding date unconfirmed) | Existence and reach by year |
| KR | Golden Disc Awards, Seoul Music Awards, broadcaster year-end *gayo daejeon* awards | Criteria by year |
| KR | Digital: Melon (2004–), Gaon (2010) → Circle (2022) | `[P5]` |
| US | Billboard Hot 100, Billboard 200, genre and airplay charts | SoundScan (1991), BDS, airplay-only eligibility (1998), downloads (2005), streaming (2012–13), album-equivalent units (2014) |
| UK | Official Singles/Albums Charts | Compilers (Gallup 1983–, Millward Brown 1994–), downloads 2005, streaming 2014/2015, Friday release 2015 |
| JP | Oricon weekly singles/albums (1968–) | Billboard Japan Hot 100 (2008–), streaming-era changes |
| All | Certifications (RIAA, BPI, RIAJ; KR none in 1990s?) | Thresholds by date; shipment-based vs sales-based |

---

## 9. Historical data, evidence and acquisition

### 9.1 Evidence tiers
| Tier | Meaning | Example | May be shown as historical fact? |
|---|---|---|---|
| A | Primary/authoritative | Chart run published by publisher; statutory rate; release date with label source | Yes |
| B | Sourced estimate | Reported sales from press; market size from industry report | Yes, with "reported" wording |
| C | Model estimate | A real artist's `vocal` = 78 from the rubric | No, internal only |
| S | Simulated | Anything after the scenario start | Shown as in-world fact, never as history |

Each curated record stores `{value, tier, sources[], retrieved, notes, confidence}`.

### 9.2 Research ledger
`data/curated/research_ledger.csv` holds every claim the engine relies on: claim, scope,
value, tier, sources and status (`open | verified | disputed`). Conflicting sources are
kept side by side, and calibration can treat a disputed value as a range.

### 9.3 Staged, cached, restartable pipeline
```
pipeline/
  stages: discover → fetch → parse → normalise → reconcile → tier → export
  each stage: idempotent, checkpointed (manifest.json), resumable, rate-limited,
              keyed by (source, query, version); raw responses cached in data/raw/
  reconcile: entity resolution across sources (romanisation variants, stage names,
             group vs member credits) with manual override files
```
**Source priorities:** open data and APIs first (MusicBrainz, Discogs data dumps,
Wikidata). Then reference lists (Wikipedia chart and number-one lists, used as
pointers to primary sources). Then official archives (Official Charts, RIAA/BPI
certification databases, KOCCA/IFPI reports, publishers' archives) where their terms
allow. Then press archives for tier B facts. Source terms of use are recorded per
source, and nothing is bulk-scraped where terms forbid it.

**The engine never waits on the full discography.** The world needs only the
*representative dataset* for the active scenario. Missing real data is filled with
generated NPCs, clearly labelled as fictional.

### 9.4 Representative dataset for the first test (KR, ~1996–2001)
- ~40–60 real acts across idol pop, ballad, dance, hip-hop/R&B, rock/indie and trot,
  with members, labels, release histories and tier-C attribute estimates.
- ~15 real organisations: major agencies (SM, DSP, the companies that became YG and
  JYP, and others), distributors, the three broadcasters' music shows, key radio programs,
  MIAK/RIAK, awards bodies.
- MIAK monthly charts for the available months (tier A/B calibration target).
- Market tables: population by segment, music spend, formats (cassette vs CD
  share), price tables, macro shock (1997–98 financial crisis), media diet.
- Generated fictional NPC acts, writers and producers to fill the long tail.

### 9.5 Historical intents (the contingent past)
- **Release intents:** real releases become soft intents. Around the real date, the
  real act and team are high-prior participants, and their real songs exist as
  compositions with estimated attributes. *Whether* the release happens, when, how
  good the final recording is and how it performs are simulated.
- **Debut pipeline:** real future artists enter around their real trainee or debut age,
  with estimated profiles. Their agency and debut happen if the simulated world allows it.
- **Organisational intents:** founding, mergers and closures are pressures conditioned
  on simulated finances.
- **Divergence propagation:** downstream intents read the simulated state. If a group
  disbanded early in-sim, their historical comeback intent is dropped. If an act became
  far bigger, their intents scale up.
- `tools/divergence_report` shows how far the world has drifted.

### 9.6 Structural history (default ON, per country)
Technology (CD adoption, MP3/P2P, ringtones, iTunes, streaming services), macroeconomics
(the 1997 Asian financial crisis, the 2008 crisis, the 2020 pandemic), regulation
(broadcast censorship, copyright law changes), media launches (cable music channels, MTV).
These are environment conditions with tier A/B dates, not outcomes.

### 9.7 Real-person policy
Professional outcomes (sales, charts, wins, signings, disbandments) are simulated for
everyone. Scandals, health events, crimes and private-life events are **off by default
for real people** and apply to fictional people. Configurable per campaign.

---

## 10. Narrator–engine interface

### 10.1 Roles
| Engine (authoritative) | Narrator (creative, non-authoritative) |
|---|---|
| Numbers, rankings, money, contracts, calendars | Scenes, dialogue, atmosphere, media voice, inner life |
| Canonical events and their causes | Interpretation and dramatisation of those events |
| Validation and resolution of proposals | **Proposals**: new people, opportunities, relationship moments, creative briefs |
| NPC decisions | NPC *voice*, consistent with personality and memories |

### 10.2 A narrative pass (manual loop, P1)
```
1. Player: decisions + standing preferences  →  cli: `play act <command file>`
2. Engine: advance until interrupt           →  writes pass_0042.json + pass_0042.md
3. Player pastes pass_0042.md into ChatGPT (with the narrator contract, §10.7)
4. ChatGPT writes the narrative + a fenced ```proposals``` JSON block
5. Player pastes the proposals block back    →  cli: `submit proposals_0042.json`
6. Engine validates/resolves, records outcomes, and they appear in the next packet
```
`[P6]` replaces steps 3–5 with an HTTP API (OpenAPI spec for ChatGPT Actions, and/or MCP).

### 10.3 Fact packet (narrator-facing, player-visible only)
```
header: campaign, date range covered, location, protagonist snapshot
digest: canonical events since last pass (ordered, with causes in plain language)
scenes: suggested scene hooks with participants and stakes (recording session,
        taping, negotiation, fan meeting, rivalry moment)
decisions_pending: options with engine-computed trade-offs and deadlines
people: dossiers of relevant NPCs (personality, goals, relationship to protagonist,
        salient memories, current situation known to the protagonist)
industry: published charts/rankings (as published), competitor activity, gossip
          (each item tagged: official | reported | rumour, with confidence)
numbers: every quotable number with {value, label, provenance tag, quotable: true|false}
creative: realised attributes of new recordings translated into descriptive tags
          ("immediate hook, thin verses, vocally demanding bridge")
constraints: what the narrator must not contradict or invent (see 10.4)
```
Hidden true values never appear. "Your manager estimates first-week sales at
80–120k" is an observation with its uncertainty.

### 10.4 Narrator latitude
- **May invent freely:** sensory detail, minor dialogue, non-consequential background
  people, weather, outfits, emotions, media tone.
- **Must propose (engine resolves):** anything with consequences, such as a new named
  industry person, an offer, a collaboration, a relationship change beyond flavour, a
  scandal, a creative decision, money, a booking, a public statement with impact.
- **Must never state:** numbers not in the packet, chart positions, outcomes of pending
  resolutions, other people's private information the protagonist could not know.

### 10.5 Proposal protocol
```json
{"proposals": [
  {"type": "introduce_person", "role": "composer", "traits": {...},
   "context": "met at the studio through Producer Kim"},
  {"type": "opportunity", "kind": "OST", "source": "org:kr.kbs.drama_dept",
   "rationale": "drama PD saw the Music Bank stage"},
  {"type": "relationship_moment", "between": ["person:p", "person:x"],
   "nature": "confided about burnout", "intended_effect": "trust+"},
  {"type": "creative_brief", "release": "...", "concept": "...", "producer": "..."},
  {"type": "player_action", "action": "decline_variety_show", "args": {...}}
]}
```
Resolution pipeline: **schema → feasibility** (exists? available? within capability/
budget? era-possible? does the protagonist know them?) → **plausibility prior** (how
likely in-world, using the same NPC utility models) → **resolution** (accept/modify/reject;
probabilistic resolution logged with a seed) → **persistence** (canonical event + memories)
→ **feedback** in the next packet with reasons. Narrator proposals cannot raise their own
odds by wording. Resolution uses state only.

### 10.6 Approval and delegation
`PlayerPolicy` (editable standing orders):
- **Always ask:** contracts and renewals, release decisions (date, lead single, concept),
  major creative commitments, career redirections, public statements, lineup changes,
  large spending.
- **Delegate with preferences:** routine bookings, interviews, schedule packing level,
  minor endorsements under thresholds, rehearsal intensity.
Delegated choices are made by the protagonist's team AI (manager/agency), constrained by
the policy, and reported in the digest.

### 10.7 Narrator contract (shipped as a document)
`docs/narrator_contract.md`: a reusable instruction block for ChatGPT that explains packet
fields, the latitude rules, the proposal format and the style expectations: substantial
immersive passes, flexible pacing, rich context.

### 10.8 Consistency checker `[P1 basic, P6 full]`
Parses narration for numbers, rankings, named outcomes and new named people. It flags
anything not in the packet or not proposed. In manual mode, the player can run `check
narrative.txt` before submitting proposals.

---

## 11. Calibration and testing

### 11.1 What "realistic" means here
Calibrate **distributions and relationships**, not individual outcomes:
- KR: monthly #1 album sales distribution 1998–2002 (MIAK), annual top-50 shape, number
  of very large sellers per year, format split, label market shares, hits per act per
  year, rookie breakthrough rates, group survival curves.
- US (second test): Billboard 200 debut-rank distributions before/after SoundScan, weeks
  at #1 distribution, Hot 100 climb speeds by era, album sales tail shape, label shares.
- Cross-cutting: hit lifetimes, song-vs-album popularity divergence frequency, sleeper hit
  frequency, superstar slump frequency, newcomer #1 frequency.

### 11.2 Methods
1. **Batch runs:** `tools/batch.py --scenario kr_1997 --seeds 200 --years 4`.
2. **Loss function:** quantile errors and KS distances against reference distributions, weighted.
3. **Parameter search:** coordinate search, then Bayesian optimisation; hold out years
   (fit 1998–2000, validate 2001–2002).
4. **Historical coverage test:** seed real releases with historical inputs and simulate them
   N times. The real outcome should fall inside the simulated 10–90% band about 80% of the time.
5. **Sensitivity analysis:** ±20% per parameter, ranking which parameters matter most for
   the data effort.
6. **Emergence checks:** frequencies of sleeper hits, breakouts from unknowns, superstar
   misfires, trend turnover, label crises and disbandments per simulated year. Each should
   be near history, and none should be forced.

### 11.3 Divergence sanity
Across seeds, real historical #1s should be *likely but not guaranteed*. If a historical
#1 is #1 in 100% of seeds, the model is scripted; if in ~0%, it is miscalibrated.

### 11.4 No artificial floors and ceilings (test)
Inject an exceptional synthetic release (top-percentile attributes, strong label,
favourable timing) for a newcomer. Over many seeds, the outcome distribution must include
results exceeding the era's historical maximum at a small but non-zero rate.

### 11.5 Test suite
- **Unit:** formulas with fixed inputs.
- **Property:** money conservation; no negative inventory; no overlapping mandatory
  commitments; every random draw logged; every published number has provenance.
- **Era-gating:** no chart, award, format or platform exists outside its validity dates/country.
- **No future knowledge:** a static check that decision modules do not import intent tables,
  plus a runtime guard on observation dates.
- **Determinism/replay:** same inputs → same state hash; replay equals snapshot.
- **Fairness:** the same scenario with the protagonist swapped for an identical NPC gives
  statistically identical outcome distributions.
- **Separation:** album sales and song popularity are not perfectly correlated across a
  batch (regression test against aliasing).
- **Regression:** golden-seed metrics; config diffs show metric diffs.

---

## 12. Phased roadmap

Each phase ends with something runnable, passing tests and an updated
"implemented vs planned" table in the README.

**Phase 0: Foundations (no gameplay)**
- Core: clock, RNG streams, event log with provenance, ledger, config, observation
  layer, memory, SQLite save/replay. Mirrors the acting engine's core contract (§13).
- Data pipeline skeleton (stages, cache, manifests) + research ledger.
- Research: KR 1996–2001 methodology registry entries, market tables, the representative act list.
- *Done when:* a dummy world advances 4 years daily/weekly deterministically,
  save → load → replay hashes match, and the pipeline resumes after interruption.

**Phase 1: First test — South Korea, 1997–2000 vertical slice**
- KR rule pack: formats (cassette/CD), retail and distribution, MIAK monthly chart,
  2–3 broadcast music shows with era-appropriate ranking rules, key radio, year-end awards
  (simplified), agency contract norms.
- Creative model (§4), hit formation (§5) with shared pools, fandom with era tools,
  label AI with opportunity detection, PD/programmer AIs.
- ~40–60 real acts + generated NPCs; trainee/rookie/established stages; groups with
  lineup and contract hazards (simplified).
- Economics: agency contract splits, recoupment, event and CF income, personal finance.
- Narrator loop v1: fact packets, proposals, approval policy, basic checker.
- Calibration v1 against MIAK distributions.
- *Playable test:* a configurable protagonist (e.g. the Bae Yeora scenario) goes from
  trainee/debut through at least two release cycles, competing against a world that
  acts independently. Every chart position and sale is traceable.

**Phase 2: Second test — United States, ~1990–1993**
- US rule pack with the **Billboard methodology change inside the scenario** (rank-report
  era → SoundScan/BDS), radio formats, MTV, US contract norms, RIAA certifications.
- *Done when:* KR and US campaigns run on the same engine without market-specific code in
  core systems, and the debut-rank shift around 1991 emerges from measurement alone.

**Phase 3: Living industry depth**
Richer NPC goals, careers of writers/producers, label finances (distress, mergers),
media ecosystem and rumours, relationship/memory depth, group dynamics, touring.

**Phase 4: Economics and awards completeness**
Full royalty waterfalls per country/era, publishing and collection societies, award
voting bodies, international licensing and exports between active markets.

**Phase 5: Era expansion and new markets**
Digital eras (KR digital/ringtones/Melon; US downloads/streaming), UK and Japan rule
packs, platform agents, the 2010s–2026 global streaming market.

**Phase 6: Narrator API**
HTTP API with OpenAPI spec (ChatGPT Actions) and/or MCP server; full consistency checker;
session management for multiple campaigns.

**Phase 7: More professions + shared core with the acting engine**
Playable producer, songwriter, manager and label executive (each a different control
surface over the same world). Extract the shared core package (§13) when both engines
have stabilised.

---

## 13. Compatibility with the acting engine

The two projects are developed in parallel and **must not disrupt each other**.
- **No cross-repo imports now.** The music engine keeps its own `engine/core/`, written to a
  *shared core contract* that both repos follow:
  - IDs: `"<kind>:<slug-or-uuid>"`; dates as ISO days; weekly ticks with a daily clock.
  - RNG: `rng(seed, system, entity_id, purpose, date)` hash streams.
  - Event schema: `{event_id, date, system, type, entities, inputs_digest, draws, outputs, causes}`,
    with namespaced types (`music.*`, `film.*`).
  - Ledger: double-entry, multi-currency, era inflation index.
  - Observation and Relationship/Memory schemas as in §3.1/§3.12.
  - Narrator packet envelope `{header, digest, scenes, decisions_pending, people, numbers,
    constraints}` and the proposal envelope (§10).
- `docs/core_contract.md` (written in P0) records the contract. Changes are proposed in
  both repos before either adopts them.
- **Later merge:** extract `simcore` as a package both repos depend on. The music and film
  domains become plug-in "industry modules" over one world, where a `Person` can be both
  singer and actor (very common in KR and JP), and calendars, fame and relationships are shared.

---

## 14. Failure modes from previous roleplays → structural fixes

| Previous failure | Structural fix in this design |
|---|---|
| Fictional songs repeatedly entering at the same low positions | Positions emerge from a competitive pool with heterogeneous creative attributes, exposure and fandom; regression test on debut-position distributions (§11) |
| Mechanical chart climbs independent of promotion/response | Rank is computed from measured consumption, which comes from listener state driven by exposure and liking dynamics (§5) |
| Historical stars permanently in historical positions | Real releases are soft intents with simulated outcomes; divergence sanity test (§11.3) |
| Success artificially limited "for realism" | No caps; fat tails; no-ceiling test (§11.4); fairness test (§11.5) |
| Labels not exploiting obvious opportunities | Opportunity detector and label portfolio AI (§6.10) |
| Album popularity conflated with singles popularity | Separate demand channels and era/market conversion (§5.5–5.6); separation test |
| Numbers changing without identifiable cause | Event log with causes and `inspect why` (§2.4) |
| Modern chart methods applied to historical periods | Versioned, date-gated methodologies; era-gating test (§8, §11.5) |
| All music equally effective | Creative attribute vector, segment appeal, separate critical reception (§4, §5.9) |

---

## 15. Decisions needed before Phase 0 code

1. **First scenario start:** Bae Yeora as a DSP trainee in early 1997 (pre-debut, so the
   1997–98 crisis and the arrival of MIAK charts happen during play), or debut-ready in 1998?
2. **Bae Yeora's existing details:** please share her profile and any canon from your
   ChatGPT campaign (debut date, songs, members of her team). Should Phase 1 reproduce her
   canon as the starting state, or restart her career fresh in the engine?
3. **Real-person policy:** keep the default (§9.7)?
4. **Seed estimates:** should I draft tier-C attribute estimates for the ~50 real acts for
   your review, or do you want to supply or adjust them?
5. **Interface preference:** for the manual loop, do you prefer the packet as Markdown (easy
   to paste) with an embedded JSON block, or pure JSON plus a separate narrator contract?
6. **Calibration tolerance:** e.g. simulated monthly #1 sales quantiles within ±25% of MIAK
   reference for slice sign-off?
7. **Technology:** Python 3.11+, numpy, SQLite, PyYAML, pytest. Later FastAPI for P6. OK?

# Creative vision charter — Historical music career roleplay with a simulation engine

**Owner:** Player's creative direction, gathered in conversation with ChatGPT on 20 November 2026  
**Audience:** Claude (engine developer), ChatGPT (narrator/gameplay operator)  
**Status:** Product vision and experience criteria, **not** an instruction to rewrite the engine or the existing Danielle save  
**Context:** First-generation K-pop soloist Bae Yeora at DSP Entertainment was the enjoyable prototype; Danielle Reyes in the 1988 US industry was an engine playtest.

## 1. What we are building — and what we are not

The goal is **an immersive, interactive, alternate-history recording-artist career** inside a historically recognizable, independently evolving music industry. The player creates an artist and makes meaningful artistic, career, relationship and financial choices. ChatGPT portrays the people, places, performances, creative process and wider culture, with substantial initiative and period-specific knowledge. Python supplies **consistent calculations, uncertainty and memory**: recordings, relative appeal, promotion, sales, charts, airplay, awards where modeled, skills, contracts, discography, money, and other persistent consequential state.

**Do not replace the roleplay with an engine-operated management dashboard.** The user already enjoyed rich ChatGPT-led music-career stories; the Python project began primarily to remove ChatGPT's reluctance to assign plausible success/sales and its difficulty maintaining long-run numbers and continuity.

Success means the player feels *they are a singer living in that real music industry*, not a producer of JSON commands, a record-company administrator, or a spectator reading engine reports.

**The key product insight:** The engine should **liberate** a capable narrator from inventing consequential numbers and remembering every balance, **not** prevent the narrator from inventing vivid, coherent situations and dialogue that fall outside explicit mechanics.

## 2. Roles, authority and the truth boundary

### The player — meaningful artistic control
- The player creates the artist and controls major creative direction: repertoire choices, sound, key collaborators, concepts, lead singles, comeback/album strategy, image when significant, major performances, major deals and consequential personal decisions, **to the extent the in-world contract allows**.
- Contractual limits are meaningful sources of influence, negotiation and occasional conflict, **not an excuse to stop offering artistic choices**. An artist can lobby, propose revisions, disagree and gain leverage over time.
- Player can delegate ordinary work and say "proceed as recommended"; this should authorize routine execution of a coherent plan, **not** convert into approval of arbitrary expensive contracts, surprise releases, or strategic changes.
- The player **does not want** to manually arrange studio calendars, negotiate small fees, submit media bookings, choose every rehearsal, or manage work like a real-life office job.

### ChatGPT — immersive narrator, director of scenes, gameplay orchestrator
- Proactively portrays and advances the world: management pitches developed comeback concepts, A&R discusses real creative alternatives, producers disagree naturally, performers meet backstage, music-show lineups are populated, the media and audience react, competitors have independent agendas.
- Uses researched historical context and its own creativity to make world scenes **richer than the engine packet**, not only read the packet verbatim.
- May dramatize **ordinary conversations, plausible small encounters, atmosphere, creative pitches, interpersonal nuances and other unmodeled narrative detail** without requiring a dedicated Python subsystem for each. Avoid portraying dramatization as documented private speech by real people.
- **Must not silently invent or contradict consequential engine-authoritative results**: actual sales/peaks, royalties, signed agreements, released records, large spend, long-term mechanical reputation changes, material legal outcomes or durable alterations to established canon. Where consequential narrative developments arise, persist them through an appropriately simple canon or state interface (and check acceptance), or mark them as pending rather than asserting they already happened.
- Avoid robotic, repeatable, AI-sounding dialogue and manufactured plot devices. Historical people should have distinct, contextual portrayals without claims to know their undocumented private motives. Fictional characters can have distinct motives, flaws, disagreements and lives beyond the protagonist.

### Python — mathematical backbone and continuity ledger
- Generate/calibrate relative song appeal, music craft, producer impact, promotion effectiveness, broadcast/chart/sales outcomes, label commercial decisions, finances and persistent career state.
- Track master recordings, original compositions, releases, market and chart history, historical vs alternate outcomes, changing skills, relationships **where significant**, collaborators, contract rights and account balances.
- Preserve consequential choices and facts with lightweight, flexible interfaces. The engine **does not need to simulate every conversation, backstage encounter, creative disagreement, friendship or press reaction** to allow ChatGPT to narrate it.
- Expose meaningful *causes*, not just verdicts: why a label passed, why radio picked up a single, what promotional support did, and the uncertainties of a team’s assessment. Avoid premature numerical certainty or blunt arbitrary veto gates.
- Provide enough historical-world context to orient the narrator, rather than only a stream of synthetic chart entries.

**Useful model:** (A) verified historical public events and context; (B) authoritative, recalculated alternate-history commercial/contract/financial state; (C) narrator-originated prose and smaller scenes; (D) recorded consequential narrative canon, with provenance. These layers cooperate without being mistaken for one another.

## 3. Historical authenticity is the *setting*, never an outcome ceiling

The player specifically enjoyed a Korean soloist interacting with **real contemporaries**: watching Fin.K.L perform on music shows, appearing on charts against actual historical groups, performing at real concert venues, and living through recognizable promotions, debuts, award shows and entertainment news.

- Real artists, groups, songs, companies, television/music programmes, venues, award events and major industry developments should form the **recognizable backbone** of a selected place and year.
- Add fictional groups, producers, managers and rivals where useful; they can have completely imagined triumphs, failures and controversies. **Do not let large synthetic populations drown out the historical field**.
- In v0.4's QA report, real artists account for approximately **12% of Hot 100 entries** after expanding to 1,400 generated acts. That is a major **experiential fidelity gap** even if it helps statistical chart scarcity. Don't fix it simply by shrinking the competitive field again; improve historical coverage and realistic competition together.
- Publicly known real-world debuts, releases, controversies, scandals, industry shifts and public events may be introduced **when historically established and chronologically available**. Research the actual record rather than fabricate damaging allegations, secret relationships, private motives, or misconduct about real people.
- Real historical artists' **competitive outcomes are mutable** in this alternate timeline: a fictional protagonist can take their #1, outsell them, dominate music-show trophies, or experience a career larger than a real superstar **if causal inputs and the simulated market response support it**. Historical peaks are benchmarks and initial conditions, **not protected reservations**.
- An artist's success should not be artificially capped because the player used the words "realistic" or "plausible." Nor should a protagonist receive guaranteed wins. **Causality over conservatism and wish-fulfillment.**
- Competing artists should continue independently. Their actual historical public events, real competitive releases, shifting fortunes and fictional competitor developments should appear **organically** in the narrative rather than as forced weekly news bulletins.
- For time-dependent locations, programmes, chart methodologies and award rules, use period-appropriate sources and acknowledge unclear details. The engine's chart is an alternate-history simulation, not necessarily a certified reproduction of actual Billboard/Music Bank/Inkigayo archival rankings.

## 4. Creating music is part of gameplay, not just a quality roll

The player particularly enjoyed creating **original fictional albums and songs inspired by the music and cultural styles of the chosen year**. The songs did not need to reproduce actual historical tracks.

- Creative development begins with distinctive *ideas*: album identity, audience, song themes, songwriting possibilities, arrangement/production choices, visuals, possible collaborators and sequencing.
- Management and creatives should proactively bring **developed**, period-credible proposals; the player chooses the consequential artistic direction while the team executes logistics.
- ChatGPT should validate invented titles and concepts against **actual naming conventions, themes and aesthetics from contemporary songs**, especially language- and market-specific patterns. Avoid recurring generic AI-ish titles such as "Velvet Hour" and "Electric Nights" without an artistic reason. The objective is organic period credibility, **not** preventing innovation or experimentation.
- Original music may borrow **period trends and techniques** but should retain its own identity; do not pass off copied lyrics, copyrighted melodies or real unreleased songs as original.
- Song outcomes should reflect songcraft, singing, fit, collaborators, resources, promotion, momentum, listeners, competition and luck. The narrator's colorful description is not a magic command guaranteeing a hit.
- Allow the player to share **album art**. ChatGPT should integrate the actual supplied artwork into immersive sleeve/press/release coverage, and the canon/discography should retain an accessible asset reference and descriptive metadata if supported, **without requiring Python to generate the artwork**.
- The creative arc of an album or comeback deserves multiple substantial moments when warranted—song selection, production, track list, final packaging, promotional strategy, release, performances, reception—rather than a repetitive "record_song → score → record_song" loop.

## 5. Achievements should be lived, not merely printed

The player particularly valued:
- Performing on actual historical music programmes and alongside recognizable real contemporaries.
- Watching real acts perform; anticipation and competition of **music-show wins**; award shows, encore stages, rehearsals, public reception and backstage context.
- Seeing their artist on historical-looking charts **alongside recognizable competitors**.
- Playing credible real-world venues with culturally appropriate capacities and reputations.
- Supplying their own cover art and seeing an album launch narrated in period-specific terms, including credible contemporary **sales reporting, rankings and commercial reception**.
- Planning, negotiating creative direction, and completing real-feeling albums/comebacks.

**Engine job:** Determine and preserve relevant commercial and outcome facts when it models them.  
**Narrator job:** Present those facts **as an experienced career**—the television stage, fellow performers, buildup, first-place announcement, encore, press reaction, awards night, industry ripple effects. Don't flatten a first win into "won music show: +1."

Not every week needs a long scene. Slow down for real creative milestones and surprises; compress genuinely routine intervals. Rich gameplay is not tied to fixed three-month turns, while testing reports may appropriately be concise.

## 6. Autonomy without administrative tedium

- Producers, label staff, managers and broadcasters should exhibit ongoing professional initiative, especially between releases. They pitch, disagree, negotiate, find songs, suggest collaborations, handle promotion and act on sensible delegated tasks.
- People should have **differentiated motives**, independent projects, varied styles of communication and changing views. Do not give every manager the same cautious voice or every producer the same temper.
- Important conflicts arise from genuine competing interests; do not insert repetitive disputes just to prove a world is "realistic."
- Real contractual control matters. Present tradeoffs and routes to influence decisions without making the player personally complete tedious operational workflows.
- The player can allow the team to do ordinary work without an approval prompt after every recording, rehearsal, meeting, show or calendar change.

## 7. Personal life is supporting texture, not the main plot

The player enjoys **some** industry friendships, rivalries, staff relationships, private struggles and ordinary life, but reports that personal scenes become repetitive and characters begin sounding alike. Keep them **selective, organic, distinctive and consequential only when earned**. The career, creative process and wider music industry remain the primary narrative focus.

Do not automatically produce a romance, friendship crisis or emotional confrontation every simulated month. People may be friendly, neutral, distant or uninterested; not every encounter is a subplot.

## 8. How to prioritize engine development after v0.4

Claude's `docs/QA_REPORT_v0.4.md` reports successful repair of rest/scheduling/development stalls, improved A&R review, save migration support and 34 passing tests. **Preserve those fixes**. The next direction must be informed by the vision above rather than expanding mechanics indiscriminately.

Recommended priorities:

**P0 — A recognizable real-artist competitive world**
- Improve historical artist/release coverage and chronological anchoring across the target markets/eras used for gameplay; for the 1988 US playtest, address the ~12% historical-artist share of Hot 100 entries.
- Keep ample competition and uncertainty; avoid chart inflation without flooding the player's perceived industry with anonymous generated musicians.
- Make historical artists compete dynamically with the player and NPCs; don't freeze canonical chart ranks or turn real stars into unassailable NPCs.
- Produce useful historical context for the narrator (release calendar, contemporary activity, venue/programme references, public news with confidence/provenance where feasible).

**P0 — A narrator-friendly, non-restrictive interface**
- Provide compact, trustworthy world packets for charts, releases, accounting and canon, alongside **reasons** for decisions and relevant historical context.
- Provide simple hooks for recording consequential narrator-originated facts or developments in persistent state, without demanding a new subsystem for every scene.
- Make discrepancies visible: "recorded by engine," "historical real-world reference," "narrative dramatization," "proposed but awaiting approval."
- Allow a natural flow of multiple ordinary steps between major player decisions; don't insist on repeated empty "proceed" prompts.

**P1 — More authentic creative/release cycles**
- Give managers and labels room to develop album and comeback proposals, producer/songwriter options, marketing approaches and professional disagreements.
- Avoid fixed mandatory annual release limits as a shortcut to fixing high success rates. **First inspect root causes**: song distribution, label attention, radio slots, audience competition, marketing budgets, pacing, year-to-year momentum. Realistic constraints may naturally reduce frequency; unusual, well-supported release schedules should remain possible.
- Make the foundation support meaningful releases and music-show/award outcomes where appropriate, without demanding that Python script their scenes.

**P1 — Better persistence and presentation affordances**
- Track enduring relationships, discography, album cycles, recording credits, release dates, contracts/royalties, major achievements and references to supplied artwork.
- Provide enough information to present compelling historical-style sales/chart/music-show summaries rather than raw scores.

**P2 — Extensions only when clear experiential benefit is proven**
- Complex private-life AI, elaborate automated dialogue graphs, exhaustive NPC friendship/romance mechanics, routine administrative approval gates, and massive invented artist catalogues are not priorities unless user testing shows direct value.

## 9. Test the desired *experience* as well as the math

A statistical pass alone cannot certify that the experience is fun or historically immersive. Use both quantitative QA and a human-in-the-loop narrator acceptance suite:

1. **1998–2001 DSP K-pop soloist:** The player develops an original Korean album with titles checked against the period; their contemporary music-show lineup visibly includes actual groups such as Fin.K.L, and the venue/show is period-appropriate. The engine supplies commercial results; ChatGPT renders a believable comeback and potential win or loss without predetermination. The user can supply cover art and see it integrated into the release presentation.
2. **1988–1989 US singer:** The player competes against recognizable historical artists and songs on the charts without the engine protecting their historical ranking. Fictional acts exist but don't overwhelm the context. Plausible commercial outcomes range from flop to major crossover; the label and manager behave proactively but major approvals remain with the player.
3. **Extraordinary upside:** Build a high-quality act with strong repertoire, unusual promotional reach and favorable word of mouth. Verify that Beyoncé-/BTS-scale *relative* impact is not mathematically forbidden by historical rank or an arbitrary "new artist" ceiling. This is a **capability test, not a guarantee** that a given seed produces superstar success.
4. **Credible disappointment:** A distinctive song can underperform; label can reject a release; manager can disagree; a low-energy artist can recover while schedules and finances remain coherent. The story should still offer meaningful professional developments instead of an inert 84-day block.
5. **Delegation and voice:** The player says "proceed as recommended"; the manager proactively coordinates routine work, suggests consequential choices and leaves the character's key artistic decisions intact. Fictional staff have identifiable personalities, while dramatizations of real performers are handled without false claims of documentary truth.
6. **Persistence:** After many in-world years, the saved canon preserves album art references, actual chosen concepts, title spellings, track lists, collaborators, chart peaks, cumulative sales, contract terms, significant relationships and the trail of major artistic decisions.
7. **Presentation:** A professional immersion pass includes authentic historical industry context and lived-in performances rather than merely translating a JSON packet into prose. Testing/QA mode can be concise, **but that is not the target gameplay experience**.

## 10. What Claude should do next

1. **Acknowledge this product charter and identify any engine design choices that directly conflict with it.** Prioritize conflicts rather than proposing every conceivable new feature.
2. Give a **small, staged technical plan**: immediate low-cost changes to historical coverage and narrator interfaces, then medium-term work. Note where ChatGPT already handles a feature without new Python code.
3. Keep v0.4's tested bug fixes; do not silently modify Danielle's 0.1 save or merge engineering work into the gameplay branch without a deliberate migration.
4. Provide **specific acceptance criteria** tied to player-facing experiences, alongside determinism and chart/financial calibration tests.
5. **Do not over-engineer.** The goal is not to make Python write dialogue, reconstruct every emotional beat, or impose industry-normal outcomes. The goal is to support a **rich, free, historically grounded, causally credible ChatGPT-led career**.

### One-line guiding standard

> **Python is the reliable mathematics and memory; ChatGPT is the living music-industry experience; the player is the artist. Realism must explain extraordinary outcomes, not prevent them.**

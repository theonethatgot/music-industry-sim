# Music Industry Simulator

A universal, historically grounded (1980–2026, multi-country) music-industry world simulation.
The Python engine owns every consequential fact: sales, charts, airplay, money, contracts,
relationships and calendars. An AI narrator (ChatGPT, used manually for now) turns engine output
into immersive story and returns the player's decisions and proposed developments in a validated
format.

Developed alongside the acting engine
([hollywood-box-office](https://github.com/theonethatgot/hollywood-box-office)). The two follow a
shared core contract ([docs/core_contract.md](docs/core_contract.md)) so they can merge later
without disrupting each other.

## Status: first playable vertical slice (US, 1986–1993 data window)

| Area | Implemented now | Planned next |
|---|---|---|
| Core | Daily clock, weekly decisions, hash-based RNG, event log with provenance, double-entry ledger, layered YAML config, SQLite snapshot + command log, exact replay | Batch/multi-seed tooling |
| World | ~47 real US acts with soft historical intents, ~45 real producers and executives, 33 labels, 480 generated acts, writers and producers | Data pipeline expansion; inverse-calibrated real-artist attributes |
| Creative | Composition/recording attribute vectors from the people, budget and time; creative briefs; descriptive tags | Album sequencing, remixes |
| Hit formation | Daily listener dynamics per audience segment (reach-limited awareness, mere-exposure liking, fatigue, word of mouth, social proof), shared wallet, retail stock | Taste drift, saturation |
| Gatekeepers | Radio formats (national playlists + regional pickup, current → recurrent), MTV/BET/VH1 rotation, TV bookings | Independent promoters, station-level detail |
| Industry AI | Label promotion budgets, opportunity detector (reinvest/cut), video commissioning, A&R scouting and showcases, offers, NPC signings, real-artist intents (release/slip/cancel), fictional release cycles | Group dynamics, label finances and mergers, touring |
| Charts | Data-defined, era-gated methodologies: Hot 100, Top Pop Albums / Billboard 200, Hot Black / R&B Singles and Albums, AC, Album Rock, Hot Rap Singles; rank-report vs SoundScan/BDS measurement | Year-end charts, recurrent rules after 1991 |
| Economics | Retail/dealer split, mechanicals, artist royalty account and recoupment, statements, advances, recording funds, living costs, gigs | Publishing deals, touring, merch, endorsements |
| Narrator | Rich Markdown packet with embedded authoritative JSON, engine industry briefing, pacing ("next" = until something needs you), team/standing orders, validated decisions and proposals, number-claim rejection, real-person protection | HTTP/OpenAPI or MCP connection |
| Delegation | Standing orders (club nights, lessons, rest), hireable managers who chase press, gigs, TV and showcases on commission | Richer team roles (lawyer, publicist, agent) |
| Markets | US pack | Korean late-1990s pack on the same core (next milestone), then UK and Japan |

See [DESIGN.md](DESIGN.md) for the full design and [docs/calibration_v1.md](docs/calibration_v1.md)
for the current calibration snapshot and known gaps.

## Playtest

The first ChatGPT-narrated session package is in [docs/PLAYTEST.md](docs/PLAYTEST.md) (US, autumn 1988,
seed 1988, `playtests/session1/`).

## Development priorities (after the playtest feedback)

1. Expand real historical artist and release coverage well beyond the current ~22% of Hot 100 entries
   (staged, cached pipeline; no single huge import).
2. Restore historically relevant catalogue albums (pre-warm-start releases with ongoing sales).
3. Multi-seed calibration reports, including deliberately extraordinary, ordinary and unsuccessful
   career paths (no hidden ceilings, no guaranteed success).
4. Audit record labels' signing, marketing and producer-spending decisions for financial and commercial
   plausibility (budgets vs. revenues, recoupment, roster economics).
5. Verify the industry keeps evolving independently when the player does nothing (a test exists; a
   longer-horizon report is planned).
6. Then: the Korean late-1990s market pack on the same core.

## Requirements
Python 3.11+, `numpy`, `PyYAML`; `pytest` for tests (`pip install -r requirements.txt`).

## Playing

```bash
python -m musicsim scenarios                                     # list campaign presets
python -m musicsim new campaigns/danielle --scenario us_1988_aspiring --seed 7
#   -> writes campaigns/danielle/packets/pass_0001.md
```

1. Paste [docs/narrator_contract.md](docs/narrator_contract.md) into a new ChatGPT conversation (once).
2. Paste the latest `packets/pass_NNNN.md`. ChatGPT writes the scene and ends with a ```json block.
3. Save ChatGPT's reply (or just the JSON) to a file, then:

```bash
python -m musicsim check campaigns/danielle reply.txt   # validate without applying
python -m musicsim play  campaigns/danielle reply.txt   # apply decisions/proposals, advance, new packet
```

Other commands:

```bash
python -m musicsim status  campaigns/danielle
python -m musicsim advance campaigns/danielle next      # until something needs you (or 3d, 2w, 2m)
python -m musicsim briefing campaigns/danielle          # engine-generated industry briefing
python -m musicsim charts  campaigns/danielle hot100 --n 40
python -m musicsim why     campaigns/danielle rec:n01876 # provenance: true attributes, weekly exposure, decisions, draws
python -m musicsim replay  campaigns/danielle           # rebuild from the command log and verify hashes
```

A campaign is a folder: `campaign.sqlite` (snapshot, command, event, chart and audit logs) plus
`packets/`. Copying the folder copies the campaign. Campaign presets are data
(`data/scenarios/*.yaml`), and protagonists are portable character files (`data/characters/*.yaml`).

## Layout

```
musicsim/
  core/        rng, dates, events, ledger, config, store (SQLite)
  systems/     creative, demand (listener dynamics), release, gatekeepers (radio/video/TV),
               charts, labels, acts (NPC behaviour + intents), careers, finance, media
  player/      commands (player decisions), proposals (narrator developments)
  narrator/    packet builder (Markdown + JSON)
  campaign.py  world builder from scenario + market pack + people data + character
  campaign_io.py  persistence, play loop, replay
data/
  universal/   style space, genres, default coefficients
  markets/US/  market pack: audiences, formats, channels, TV, prices, certification, chart methodologies, labels
  people/US/   real acts (with soft intents), producers, executives (evidence-tiered)
  scenarios/   campaign presets      characters/  portable protagonists
tools/diagnose.py   calibration diagnostics
tests/              determinism, replay, save/load, money conservation, era-gating, neutrality, play loop
```

## Principles enforced by tests
- Same scenario, seed and commands produce the same world, and save → load → continue equals an uninterrupted run.
- Engine code contains no country, chart, genre or date literals; those live in data.
- Demand, creative and chart maths never branch on who the player is.
- Charts exist only inside their historical methodology windows.
- Narration can't assert numbers or invent real people.

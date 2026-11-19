# Shared core contract (music engine ↔ acting engine)

The music simulator (`music-industry-sim`) and the acting simulator (`hollywood-box-office`) are
developed separately and must not depend on each other's code yet. Both follow this contract so
that a later merge into one world (`simcore` + industry modules) is mechanical.

| Concern | Contract | Music engine implementation |
|---|---|---|
| IDs | `"<kind>:<id>"` strings, unique per world | `person:…`, `act:…`, `org:…`, `rec:…`, `rel:…`, `comp:…`, `offer:…`, `contract:…` |
| Time | ISO dates; simulation at daily resolution; weekly decision ticks (Monday) | `musicsim/sim.py` |
| Randomness | Pure hash streams `rng(seed, system, entity, purpose, date)`; never stateful generators | `musicsim/core/rng.py` |
| Events | Append-only `{id, date, system, type, entities, data, causes[], draws[], public}`; types namespaced (`music.*` / `film.*` when merged) | `musicsim/core/events.py` |
| Money | Double-entry ledger, entity ids as account names, `ext:*` for external sources and sinks; currency per entry | `musicsim/core/ledger.py` |
| People | `Person` with roles, personality, goals, skills, wellbeing, memories; a person may hold roles in both industries | `musicsim/entities.py` |
| Relationships | Directed edges `a|b → {affinity, trust, respect, history[event ids]}` | `World.rel` |
| Memory | `{date, gist, about[], valence, salience, event, public}` per person | `World.remember` |
| Observations | Decisions use observed (noisy) values; true values never reach the narrator | per system |
| Narrator I/O | Packet envelope `{pass_id, date, protagonist, digest/news, people, decisions, constraints}`; return `{pass_id, decisions[], proposals[], advance}` | `musicsim/narrator/`, `musicsim/player/` |
| Persistence | Snapshot + command log; `state = f(scenario, data_version, seed, commands)`; replay must reproduce hashes | `musicsim/campaign_io.py` |

Change process: propose a contract change in both repositories before either adopts it.

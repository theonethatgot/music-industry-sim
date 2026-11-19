# Calibration snapshot v1 (US, late 1988 – early 1989)

Run with `python tools/diagnose.py us_1988_aspiring 7 26` (no protagonist; 26 weeks after a 66-week
warm start). The numbers below are **measured** chart inputs as the pre-1991 methodology sees them:
about 55% store coverage for sales, with noise and week-to-week inertia. True sales are higher.

| Statistic (median over 26 weeks) | Simulated | Rough reference (to verify) | Status |
|---|---|---|---|
| Hot 100 #1, measured weekly singles sales | ~57k (max ~120k) | true #1 weeks ~80–150k | plausible |
| Hot 100 #40 measured sales | ~2.6k | — | plausible |
| New Hot 100 entries per week | ~4.7 | ~6–7 | slightly low |
| Median Hot 100 debut rank (rank-report era) | ~80 | 60s–90s typical before 1991 | good |
| Distinct #1 singles in 26 weeks | ~11 | ~10–13 | good |
| Top Pop Albums #1 measured weekly sales | ~190k | ~150–400k | plausible |
| Median album debut rank (rank reports) | ~18 | — | plausible |
| Median album debut rank after SoundScan (1991 scenario) | ~7 | high debuts after May 1991 | emergent, good |
| Share of Hot 100 entries by real artists | ~22% | ~100% in reality | **dataset gap** |

## Known gaps (next calibration work)
- **Real-artist coverage.** The bundled dataset has about 47 real acts and 150 release intents.
  Generated acts fill the remaining ~78% of chart slots. Expanding real coverage with the staged
  pipeline (MusicBrainz, Discogs dumps, chart archives as pointers) is the main fidelity lever.
- **Catalogue albums** from before the warm-start window are missing, so the album chart leans
  towards new releases.
- **Pre-tracking measurement** is approximated with noise plus inertia on rank reports. Store-panel
  composition biases aren't modelled yet.
- **Historical coverage test** (do real outcomes fall inside the simulated 10–90% band about 80% of
  the time?) needs multi-seed batch tooling. That's planned next. Single-seed runs already show real
  #1s appearing sometimes, but not always (e.g. "Straight Up" reaching #2 in one seed).

Tolerance guideline (agreed): about ±25% on selected aggregate statistics. Individual historical
chart outcomes are deliberately **not** calibration targets.

# Music Industry Simulator

A universal, historically grounded (1980–2026, multi-country) music-industry world
simulation: start any campaign in any supported country and era. The Python engine owns every consequential fact (sales, charts, money,
contracts, relationships, calendars). An AI narrator turns engine output into story
and can propose developments that the engine validates and records.

Developed alongside the acting engine
([hollywood-box-office](https://github.com/theonethatgot/hollywood-box-office)); the two
follow a shared core contract so they can merge later without disrupting each other.

- `DESIGN.md`: technical design (architecture, world-state schema, simulation systems,
  narrator–engine interface, data acquisition, chart engine, calibration, roadmap)

Status: design stage (v0.2). No engine code yet. The engine is country-, era- and protagonist-neutral; it is validated first on two data-only scenarios: United States late 1980s–early 1990s, and South Korea late 1990s.

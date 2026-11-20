# First-session playtest: US, autumn 1988

> Engine 0.4 note: this package was generated on engine 0.1. A save made then must be migrated before it
> can continue on 0.4 (see `docs/MIGRATION.md`); `playtests/session1` regenerated today would differ.

The goal is to judge whether this feels like an immersive, autonomous, causally believable music
career, not just reproducible statistics. Nothing about the career is pre-arranged. The seed was
fixed (1988) before the campaign was generated, and the start is the default scenario.

## What's in the package

| File | Purpose |
|---|---|
| `docs/narrator_contract.md` | Paste into ChatGPT **once**, at the start of the conversation |
| `playtests/session1/packets/pass_0001.md` | The real first pass, straight from the saved campaign (paste second) |
| `playtests/session1/SESSION.md` | How the campaign was created, with its fingerprint |
| this file | Workflow, latitude, pacing, delegation, starting world, what to look for |

## 1. Workflow

**Option A: let Claude run the engine (easiest; nothing to install).**
1. Open a new ChatGPT conversation. Paste `docs/narrator_contract.md`, then `pass_0001.md`.
2. Play: talk to ChatGPT, make your choices, and let it write.
3. When ChatGPT ends a reply with its JSON block, copy the **whole reply** and paste it to Claude in
   this session with "play this". Claude runs `python -m musicsim play playtests/session1 -`
   and gives you the engine's results plus the next packet.
4. Paste the next packet into ChatGPT, and so on.

**Option B: run it yourself.** You need Python 3.11+ and `pip install -r requirements.txt`.

```bash
git clone https://github.com/theonethatgot/music-industry-sim && cd music-industry-sim
git checkout claude/vibrant-clarke-hrzk96
python -m musicsim new playtests/session1 --scenario us_1988_aspiring --seed 1988   # recreates the exact campaign
#   (if you already have playtests/session1/campaign.sqlite, skip this)

python -m musicsim check playtests/session1 reply.txt   # optional: validate ChatGPT's reply first
python -m musicsim play  playtests/session1 reply.txt   # apply it; prints results + next packet path
#   or paste straight in:  python -m musicsim play playtests/session1 -   (then paste, then Ctrl-D)
```

Useful extras:

```bash
python -m musicsim status   playtests/session1            # one-line career summary, open offers
python -m musicsim advance  playtests/session1 next       # move time without decisions (until something happens)
python -m musicsim charts   playtests/session1 hot100     # full chart; also top_albums, black_singles, black_albums, ac, album_rock
python -m musicsim why      playtests/session1 rec:…      # why a record did what it did (true quality, exposure, decisions, dice)
python -m musicsim briefing playtests/session1            # fresh industry briefing (JSON) for today
python -m musicsim replay   playtests/session1            # proof the campaign rebuilds exactly from its log
```

If the engine rejects a reply (a wrong id, a stale pass), nothing is applied and it tells you why.
Ask ChatGPT to correct the JSON, or fix it by hand.

## 2. What the narrator may develop vs. what the engine resolves

| ChatGPT develops freely | Proposed by ChatGPT, resolved by the engine | Engine only |
|---|---|---|
| Scenes, atmosphere, era detail | New named people who will matter (`introduce_person`; the engine draws their ability) | All numbers: sales, charts, airplay, money, fees |
| Dialogue for everyone in the packet, in character | Opportunities: TV booking, showcase, collaboration, interview, gig (`opportunity`; the engine rolls the odds) | Offers, signings, label promotion decisions, reviews |
| The protagonist's inner life | Relationship shifts (`relationship_moment`; the effect depends on the other person) | What real artists and labels do |
| Background people with no consequences | Lasting story details (`narrative_fact`; no numbers allowed) | How good a song or performance is |
| Interpretation, gossip colour, industry atmosphere | Creative direction for the next session (`creative_brief`: direction, not quality) | Who exists in the industry; all real people |

Real people appear when the engine puts them in the protagonist's path, and they speak in character.
ChatGPT must not invent scandals, illnesses or traumatic events for them, or put a real person in
the story who isn't in the packet.

## 3. Pacing

The engine simulates every day, but a pass ends only when the requested time is up or **something
needs the player**: an offer, the showcase, a finished recording, a release, a chart entry, Top 40,
Top 10 or #1, a TV booking or performance day, a certification, the label pushing harder, money
trouble, exhaustion, and (engine 0.4) a label development meeting, a label patience warning, or being
dropped. Each packet's *Pacing* section says how many days passed and why it stopped.
ChatGPT should give that moment a full scene and summarise the routine before it.

`"advance": "next"` (the usual choice) runs until the next such moment, at most about three months.
Use `"3d"` or `"1w"` when you want to play day by day, or `"2m"` for a deliberate quiet stretch.
Leave `advance` out when you still have a decision to make. The world keeps moving in all cases.

## 4. Delegation

Standing orders (shown in every packet, changed with `set_policy`) let the team handle routine work:
keeping club nights booked (default 2 nights a week when nothing else is on), optional lessons, a
week off when exhausted. With a manager (`hire_manager` for someone you know; ChatGPT can introduce
one with `introduce_person`), they also chase press, better-paid shows, TV bookers and showcases on
commission. All of it runs through the same engine rules and appears under *Handled for you*.

These always come back to you: contracts, recording sessions, releases, career changes, spending
over about $2,000, and public statements.

## 5. The starting world (engine output for this seed)

From `pass_0001.md` (1988-09-05). The packet's *The industry right now* section has the full briefing.
- **Charts:** Michael Jackson's "Another Part of Me", Bobby McFerrin's "Don't Worry, Be Happy" and Rick
  Astley sit in the Hot 100 top 10. *Faith* and *Appetite for Destruction* are top-5 albums. Whitney
  Houston's "One Moment in Time", Public Enemy and Guy are on Hot Black Singles. The charts are compiled
  from store and station rank reports, as they were before SoundScan.
- **Biggest real artists:** George Michael, Michael Jackson, Whitney Houston, Phil Collins, Madonna,
  Prince, Gloria Estefan, New Kids on the Block, Debbie Gibson, Bon Jovi, Janet Jackson, U2.
  Upcoming in this world: Bon Jovi's *New Jersey*, U2's "Desire", Michael Jackson's "Smooth
  Criminal", George Michael's "Kissing a Fool", plus a Hollywood showcase for you.
- **Record companies:** CBS/Sony (Columbia under Tommy Mottola; Epic; Def Jam), WEA (Warner Bros.,
  Atlantic, Elektra, Geffen, Sire), BMG (Arista under Clive Davis, RCA, Jive), MCA (MCA, Motown, Uptown),
  PolyGram (A&M, Mercury, Island, Wing), Capitol-EMI, and independents (Virgin, Priority, Tommy Boy, …).
- **Audiences:** eight segments (mainstream and Black/urban teens, young adults, rock-oriented young
  adults, adults, the hip-hop core), each with its own tastes, radio habits and buying behaviour.
  Singles are still a strong market in 1988. Albums cost about $11.
- **Your situation:** Danielle Reyes, 21, unsigned, Los Angeles. Strong voice (team rating 80),
  developing songwriter, $1,800 in the bank, a day job, a rough old demo tape, a close producer friend
  (Carla Holloway) and a club booker (Michelle Hayes). The showcase is on **1988-09-17**: a booker has
  invited A&R staff from several labels. Who comes and what they think is decided on the night.

## 6. Known limitations (so you can judge the experience fairly)

- **Generated acts:** about three-quarters of chart entries are generated (fictional) artists,
  because the bundled real dataset is small (~47 acts). Real stars hold many top positions, but the
  field around them is fictional. ChatGPT should treat those artists as real people of this world.
- **Calibration:** blockbuster album totals run somewhat above history (*Faith* at about 12M by
  autumn 1988), and some pop records chart higher on Hot Black Singles than they did. Both are
  calibration items.
- **Not modelled yet:** touring beyond club dates, publishing deals, group dynamics, label finances,
  endorsements. ChatGPT can narrate around them, but they have no mechanical effect yet.

## 7. What to look for (feedback checklist)

1. **Immersion:** do the packets give ChatGPT enough people, texture and stakes for rich scenes?
2. **Autonomy:** does the industry feel alive around you (other artists' records, label moves, charts)?
3. **Causality:** when something happens to your records, does the explanation make sense?
   (`why` shows the chain.)
4. **Agency:** do your decisions matter, and are the important ones the ones you're asked about?
5. **Pacing:** do passes stop at the right moments? Is anything skipped that deserved a scene?
6. **Narrator discipline:** does ChatGPT stay inside the numbers and outcomes, or drift?
7. **Friction:** where does the copy-paste loop get in the way?

# Playtest session 1

- Created with: `python -m musicsim new playtests/session1 --scenario us_1988_aspiring --seed 1988`
- Seed chosen before generation; default scenario; no edits to the outcome.
- Start state hash: `e3076df5dc16af509ffb` (command 0, `create`, 1988-09-05)
- Data version: `3763906a35ea9667`
- First packet: `packets/pass_0001.md` (paste after `docs/narrator_contract.md`)

`campaign.sqlite` (about 30 MB) is not committed. Running the command above on this branch
recreates the identical campaign; `python -m musicsim replay playtests/session1` verifies it.
Later packets from the session will be added here as the playtest proceeds.

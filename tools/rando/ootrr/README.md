# Logic copied from the other randomizers of this remake

Used by `tools/rando/dungeon_logic.py` to work out what each dungeon check needs. Copied 2026-11-21 with the owner's
go-ahead; nothing here is run by the game or the seed tool at Play.

- `oot_rando/`: the logic engine and world of **OotrR** by Mozencaz (https://github.com/Mozencaz/OotrR, release 0.7.2,
  commit 331aa36), MIT, `LICENSE`. Its world is the Archipelago OoT world, MIT,
  `oot_rando/logic/world/LICENSE-archipelago-oot.txt`, with OotrR's remake layer (`remake.json`).
- `ootrando/`: the dungeon region files, helpers, the remake-to-N64 location pins (`locations.json`) and the vanilla
  item table of **ootrr** by ootrando / REALAZK (https://github.com/ootrando/ootrr, release v0.8.2, commit 0fa64f4;
  refreshed 2026-11-22 to REALAZK/ootrr commit a253c9a, its dungeons "checked against remake actors"),
  GPL-3.0, `ootrando/LICENSE`. Its 0.8.2 "massive logic overhaul" rewrote the dungeons for the remake's layout.
  The owner's caution (2026-11-17): this project may hold code translated from the N64 randomizer; its claims are
  leads, checked in our files and in play.

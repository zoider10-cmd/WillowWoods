"""Test pins with dungeon items on Gold Skulltulas and in pots (asked 2026-11-26, tools/rando/rando_seed.py pin_item,
pin_spot, pin_swaps; host/hos_main.c oot_dungeon_owner, oot_dungeon_item): no game data.

- a pin's spot is the one whose position is the pin's text whole, before the ones it only starts ("Gold Skulltula"
  beside "Gold Skulltula, night #1");
- a map or compass pinned may be told its dungeon ("Item_Dungeon_Map@DodongoCavern"): it is no bound group (there are
  several alike: pinned so, all of them went to that one spot and the seed failed), but traded in after the shuffle
  with a spot given one, which takes the pinned spot's item; a gating item there is refused;
- the game's side: dungeon_items.txt's owner is found for a pot too (its hash is the check's .broken, not .key), and a
  dungeon item that is not a chest's add is its dungeon's when the tracker has just found its check (the pot broken, the
  Skulltula nearest). Seen without a window: two pots' map and key set DodongoCavern's IsGetMap and WaterTemple's
  SmallKeyNum, their windows naming them.

    python -I -B tests/test_rando_pin_dungeon_items.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    S = seed
    check(S.pin_item("Item_Dungeon_Map@DodongoCavern") == (S.MAP, "DodongoCavern") and
          S.pin_item("Item_Dungeon_SmallKey@WaterTemple#1") == ("Item_Dungeon_SmallKey@WaterTemple#1", None) and
          S.pin_item("Item_Hammer") == ("Item_Hammer", None), "a pin's item is not read as the shuffle names it")
    # spots: hash -> [area, item, a dungeon's, why it stays, kind, position]
    spots = {1: ["KakarikoVillage", "TOKEN", False, None, "skulltula", "Gold Skulltula"],
             2: ["KakarikoVillage", "TOKEN", False, None, "skulltula", "Gold Skulltula, night #1"],
             3: ["Market", "junk", False, None, "pot", "Pot #2"],
             4: ["DodongoCavern", S.MAP, True, None, "Obj_TBox_A_02", "(1, 2, 3)"],
             5: ["Market", "junk", False, None, "pot", "Pot #3"]}
    check(S.pin_spot(spots, "KakarikoVillage", "Gold Skulltula") == 1 and S.pin_spot(spots, "KakarikoVillage", "Gold Skulltula, night") == 2,
          "a pin's spot is not its whole position first, then its start")
    pins = [("Market", "Pot #2", "Item_Dungeon_Map@DodongoCavern"), ("KakarikoVillage", "Gold Skulltula", "Item_Dungeon_SmallKey@ForestTemple#1")]
    groups = S.pin_groups(spots, pins)
    check(groups == [(frozenset({"Item_Dungeon_SmallKey@ForestTemple#1"}), frozenset({1}))],
          "a pinned map is a bound group (all the maps would go to its one spot), or a key is not: %r" % groups)
    check(S.pin_owners(spots, pins) == {3: "DodongoCavern"}, "a pinned map is not told its dungeon")
    gives = {3: "TBox_Rupee_Red", 4: S.MAP, 5: "junk"}
    S.pin_swaps(spots, gives, pins)
    check(gives[3] == S.MAP and gives[4] == "TBox_Rupee_Red", "a pinned map is not traded in after the shuffle: %r" % gives)
    gives = {3: sorted(S.PROGRESSION)[0], 4: S.MAP}
    try:
        S.pin_swaps(spots, gives, pins)
        check(False, "a pinned map's spot holding a gating item is traded")
    except SystemExit as e:
        check("the logic placed" in str(e), "a pinned map's spot holding a gating item is not refused: %s" % e)
    script = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("holds = {h: v for h, v in holds.items() if h not in pinned_spots}" in script and
          "any(not skulltula_holds(i, PROGRESSION) and h not in pinned_all for h, i in skull_drops.items())" in script and
          "any(not skulltula_holds(i, PROGRESSION) and h not in pinned_all for h, i in pot_drops.items())" in script and
          "gives.get(h) or skull_drops.get(h) or pot_drops.get(h)) for h in sorted(owners)" in script and
          'not str(spots[h][4]).startswith("Obj_TBox") and h not in pinned_all for h in owners' in script,
          "a pinned Skulltula's or pot's dungeon item is still refused somewhere, or not written to dungeon_items.txt")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    check("oot_checks[i].key == key || (oot_checks[i].pot && oot_checks[i].broken == key)" in host,
          "a pot's dungeon item is not told its dungeon (its hash is .broken)")
    check("oot_dungeon_check = best, oot_dungeon_check_at = hos_now_ns();" in host and
          "if (oot_dungeon_recent(name)) nearest = 0" in host and "const int from_check = oot_dungeon_recent(name);" in host,
          "a dungeon item that is not a chest's add is not its check's dungeon's")
    print("PASS: test pins: dungeon items on Gold Skulltulas and in pots")


if __name__ == "__main__":
    main()

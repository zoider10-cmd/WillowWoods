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
          "drop_ok = lambda h, i: skulltula_holds(i, PROGRESSION) or h in pinned_all or" in script and
          "any(not drop_ok(h, i) for h, i in skull_drops.items())" in script and
          "any(not drop_ok(h, i) for h, i in pot_drops.items())" in script and
          "gives.get(h) or skull_drops.get(h) or pot_drops.get(h)) for h in sorted(owners)" in script and
          'not drop_holds(spots[h][4], placement) and h not in pinned_all for h in owners' in script,
          "a pinned Skulltula's or pot's dungeon item is still refused somewhere, or not written to dungeon_items.txt")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    check("oot_checks[i].key == key || (oot_checks[i].pot && oot_checks[i].broken == key)" in host,
          "a pot's dungeon item is not told its dungeon (its hash is .broken)")
    check("oot_dungeon_check = best, oot_dungeon_check_at = hos_now_ns();" in host and
          "if (oot_dungeon_recent(name)) nearest = 0" in host and "const int from_check = oot_dungeon_recent(name);" in host,
          "a dungeon item that is not a chest's add is not its check's dungeon's")
    check("if (away < (chest ? OOT_DUNGEON_NEAR : OOT_CHECK_NEAR) && away < best)" in host and
          "if (!chest && oot_checks[i].done == 1) continue;" in host,
          "a Skulltula's dungeon item's window is looked for within a chest's 4 m (the owner's test: 8 m away, not named)")
    # a pot's dungeon item: a pick-up of its dungeon's own, its rows' ActorName its own (the get scene's words by it)
    import collections
    row = ("dict", collections.OrderedDict([("ActorName", ("string", "Item_Dungeon_SmallKey")), ("__RowId", ("string", "Item_Dungeon_SmallKey"))]))
    table = S.byml_build(("array", [row]), 7)
    out, _ = S.byml_parse(S.pot_fall_rows(table, {"Item_Dungeon_SmallKey_WaterTemple_Fall": ("Item_Dungeon_SmallKey", "Item_Dungeon_SmallKey_WaterTemple"),
                                                  "Other_Fall": "Item_Dungeon_SmallKey"}))
    names = {r[1]["__RowId"][1]: r[1]["ActorName"][1] for r in out[1]}
    check(names.get("Item_Dungeon_SmallKey_WaterTemple_Fall") == "Item_Dungeon_SmallKey_WaterTemple" and names.get("Other_Fall") == "Item_Dungeon_SmallKey",
          "a dungeon's own pick-up's row does not name it, or another fall's row is changed: %r" % names)
    check(S.DUNGEON_PICKUP % ("Item_Dungeon_SmallKey", "WaterTemple") == "Item_Dungeon_SmallKey_WaterTemple" and
          "fall_of(drop, owners.get(h) if drop in DUNGEON_ITEMS else None)" in script and "pot_rows_more[fall] = (item, key) if folder else item" in script,
          "a pot's dungeon item is not a pick-up of its dungeon's own, named as the seed's words are")
    check("if (oot_dungeon_pickup(name, oot_pickup_folder, sizeof oot_pickup_folder))" in host and
          "if (oot_pickup_folder[0]) {" in host and "if (oot_pickup_folder[0] && strcmp(oot_checks[i].owner, oot_pickup_folder))" in host,
          "the game's side does not count a dungeon's own pick-up for its dungeon, or marks another pot for it")
    # a Gold Skulltula's dungeon item: a drop of its dungeon's own too, with the dropped items' death (asked 2026-11-26)
    check("if item in DUNGEON_ITEMS and owners.get(h) and drops[h] == item:" in script and
          "drops[h] = DUNGEON_PICKUP % (item, owners[h])" in script and "death=rupee[POT_FALL_DEATH]" in script and
          "pot_fall_rows(table, {k: (i, k) for k, i in skull_dungeon.items()})" in script and
          "pot_fall_parts = {}, set(skull_dungeon_parts)" in script,
          "a Gold Skulltula's dungeon item is not a drop of its dungeon's own, its rows, its death or its size entries")
    pouch = S.byml_build(("dict", collections.OrderedDict((("PouchActor", ("string", S.ACTOR_REF % "Item_K")),))), 7)
    actor_k = S.byml_build(("dict", collections.OrderedDict((("Components", ("dict", collections.OrderedDict((
        ("PouchContentRef", ("string", "?Work/Component/PouchContentParam/K.game__component__PouchContentParam.gyml")),)))),))), 7)
    pack = S.sarc_write(collections.OrderedDict(((S.ACTOR_FILE % "Item_K", actor_k),
                                                  ("Component/PouchContentParam/K.game__component__PouchContentParam.bgyml", pouch))))
    made = S.sarc_read(S.dungeon_pickup_pack("Item_K", pack, "Item_K_WaterTemple", death=b"dies as a rupee"))
    own = S.byml_parse(made[S.ACTOR_FILE % "Item_K_WaterTemple"])[0][1]
    comps = dict(own["Components"][1])
    check(own["$parent"][1] == S.ACTOR_REF % "Item_K" and comps.get("DeathRef") == ("string", "?" + S.POT_FALL_DEATH) and
          made[S.POT_FALL_DEATH] == b"dies as a rupee" and
          S.byml_parse(made[S.OWN_POUCH % "Item_K_WaterTemple"])[0][1]["PouchActor"][1] == S.ACTOR_REF % "Item_K_WaterTemple",
          "a dungeon's own pick-up is not made from the item, naming itself, dying as a rupee: %r" % comps)
    check('} else if (oot_dungeon_pickup(name, oot_pickup_folder, sizeof oot_pickup_folder)) {' in host,
          "the game's side does not count a Gold Skulltula's drop of a dungeon's own for its dungeon")
    # a seed made with pins, rewritten after the pin file changed or went: said (it comes back another seed)
    stamp = "placement 35 seed 1 chests 3\nfixes 105 hints 1 pins %r\n" % (pins,)
    check(S.pins_gone(stamp, []) and S.pins_gone(stamp, pins[:1]) and not S.pins_gone(stamp, pins) and
          not S.pins_gone("placement 35 seed 1\nfixes 105\n", []) and not S.pins_gone(None, pins) and
          'if pins_gone(open(stamp_path, encoding="utf-8").read(), read_pins()):' in script,
          "a rewrite of a seed made with other test pins is not told apart, or not said")
    print("PASS: test pins: dungeon items on Gold Skulltulas and in pots")


if __name__ == "__main__":
    main()

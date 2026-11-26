"""Dungeon items on Gold Skulltulas and in pots in real seeds (asked 2026-11-26, placement 36, DUNGEON_DROPS_FROM;
tools/rando/rando_seed.py drop_holds, place's `even`, main's `loose` block and drop_ok): no game data.

- from placement 36 a Gold Skulltula's and a pot's spot may hold the dungeon items that are "Anywhere", as a chest may;
  a seed of an earlier placement keeps them in chests (its items are written again as they were);
- not a gift, a shelf, a scrub or a Piece of Heart lying in the world;
- a small key is placed by the logic where its spot's rule is met without it, a drop's spot as a chest's;
- the maps, compasses and Boss Keys go to any spot that may hold them, each as likely as another (`even`): left to the
  filling, the Skulltulas and pots, which choose first, took nearly all of them.

    python -I -B tests/test_rando_dungeon_drops.py
"""
import collections
import importlib.util
import random
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
    check(S.PLACEMENT >= S.DUNGEON_DROPS_FROM == 36, "placement 36 is not the dungeon items' on Gold Skulltulas and in pots")
    check(S.drop_holds("Obj_TBox_A_01", 35) and S.drop_holds("Obj_TBox_A_01", 36), "a chest does not hold a dungeon item that is anywhere")
    check(S.drop_holds("skulltula", 36) and S.drop_holds("pot", 36), "a Gold Skulltula or a pot holds none from placement 36")
    check(not S.drop_holds("skulltula", 35) and not S.drop_holds("pot", 35), "a seed of placement 35 would move its dungeon items to drops")
    check(not any(S.drop_holds(k, 36) for k in ("piece", "gift", "shop", "scrub", "song")),
          "a gift, a shelf, a scrub or a lying piece holds a dungeon item: their adds name no dungeon")

    # place(): 6 chests, 3 Skulltulas, 3 pots; a map that is anywhere (plain), a small key that gates (the logic's)
    key = "Item_Dungeon_SmallKey@WaterTemple#1"
    gating = S.PROGRESSION
    S.PROGRESSION = gating | {key}
    try:
        spots = collections.OrderedDict()
        for k in range(6):
            spots[k] = ("Field", S.MAP if k == 0 else key if k == 1 else "TBox_Rupee_Blue", False, None)
        for k in range(6, 12):
            spots[k] = ("Field", "TBox_DekuNutBundle", None, None)
        loose = frozenset((S.MAP, key))
        drop_may = frozenset(("TBox_DekuNutBundle",)) | loose
        holds = {k: drop_may for k in range(6, 12)}
        needs = {k: frozenset() for k in spots}
        needs[7] = frozenset((key,))   # (a pot behind that key's door: never the key's own place)
        where_map, where_key = collections.Counter(), collections.Counter()
        for n in range(300):
            gives, _, spheres = S.place(random.Random(n), spots, 3, 2, needs, holds=holds, loose=loose, even=loose - S.PROGRESSION)
            check(collections.Counter(gives.values()) == collections.Counter(s[1] for s in spots.values()), "an item was lost or made")
            check(all(gives[k] in holds[k] for k in holds), "a drop's spot was given what it may not hold: %r" % gives)
            where_map[next(k for k in gives if gives[k] == S.MAP)] += 1
            where_key[next(k for k in gives if gives[k] == key)] += 1
        check(where_key[7] == 0, "a small key lies behind its own door")
        check(sum(where_key[k] for k in range(6, 12)) > 60 and sum(where_key[k] for k in range(6)) > 60,
              "a small key is not placed on drops and in chests alike: %r" % where_key)
        check(all(where_map[k] > 5 for k in range(12)) and 90 < sum(where_map[k] for k in range(6)) < 210,
              "a map that is anywhere is not as likely in one spot as another: %r" % sorted(where_map.items()))
        # (without `even`, as before placement 36's change: the drops' spots, which choose first, take the map nearly always)
        old = collections.Counter()
        for n in range(100):
            gives, _, _ = S.place(random.Random(n), spots, 3, 2, needs, holds=holds, loose=loose)
            old[next(k for k in gives if gives[k] == S.MAP) >= 6] += 1
        check(old[True] > 80, "the test's reason is gone: the filling alone spreads a map evenly now (%r)" % old)
    finally:
        S.PROGRESSION = gating

    # (placement 37, POT_KEYLESS_FROM) a pot needs no small key as the actor it borrows its rule from needs none, when that
    # actor is of the pot's own dungeon room: not one of another room, of no room, or one that needs keys
    placed = {"a": [(1, (0, 0, 0), 3), (10, (1, 0, 0), 3), (11, (2, 0, 0), 4), (2, (9, 0, 0), 5), (12, (9, 1, 0), 5)],
              "b": [(3, (0, 0, 0), None), (13, (1, 0, 0), None)]}
    free = frozenset((1, 3))   # (2: behind a locked door)
    sources = {10: 1, 11: 1, 12: 2, 13: 3}
    check(S.pots_keyless(free, sources, placed) == frozenset((10,)),
          "a pot's 'needs no key' is not borrowed from its own room's keyless actor alone: %r" % sorted(S.pots_keyless(free, sources, placed)))
    script = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check(S.PLACEMENT >= S.POT_KEYLESS_FROM == 37 and "if placement >= POT_KEYLESS_FROM:" in script and
          "free = free | pots_free" in script, "placement 37 is not the pots' own 'needs no key', or an earlier seed takes it")
    check("if not drop_holds(s[4], placement):" in script and
          "if s[4] in DROP_KINDS and h not in JUNK_ONLY:" in script and "holds[h] = frozenset(holds[h]) | loose" in script,
          "main does not let the dungeon items that are anywhere onto a Gold Skulltula's or a pot's spot")
    check("even=loose - PROGRESSION if placement >= DUNGEON_DROPS_FROM else frozenset())" in script,
          "the maps, compasses and Boss Keys are not spread evenly from placement 36, or are for an earlier seed")
    check("placement >= DUNGEON_DROPS_FROM and i in DUNGEON_ITEMS and h in owners" in script,
          "a drop's dungeon item is not asked to be told its dungeon (the pick-up of its dungeon's own is made by it)")
    print("PASS: dungeon items on Gold Skulltulas and in pots (placement 36)")


if __name__ == "__main__":
    main()

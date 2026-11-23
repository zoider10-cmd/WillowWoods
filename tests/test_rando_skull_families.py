"""Bug 114 (the owner's run 2026-11-23): the Slingshot, the Bow and the Golden Gauntlets dropped by Gold Skulltulas
could not be taken: with Progressive items the game's side renames a drop to the family's next, which is no pick-up.
From placement SKULL_FAMILY_FROM no Skulltula drops an item of a family with Progressive items, nor a magic tier with
Magic; seeds made before keep theirs. No game files.

python -I -B tests/test_rando_skull_families.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def main():
    check(seed.PLACEMENT >= seed.SKULL_FAMILY_FROM, "new seeds are not made from SKULL_FAMILY_FROM")
    fam = seed.skull_families(seed.SKULL_FAMILY_FROM, True, True)
    for item in ("Item_Range_SlingShot", "Item_Range_Bow", "Item_Gauntlet_Gold", "Item_BombBag_Small", "Item_Hookshot",
                 "Item_FairyBless_MPDouble"):
        check(not seed.skulltula_holds(item, seed.PROGRESSION, fam), "%s may still be a Skulltula's drop" % item)
    check(seed.skulltula_holds("Item_Boomerang", seed.PROGRESSION, fam), "the Boomerang (no family) is no longer a drop")
    check(seed.skull_families(seed.SKULL_FAMILY_FROM - 1, True, True) == frozenset(), "a seed made before changes")
    check(not seed.skull_families(seed.SKULL_FAMILY_FROM, False, False), "without Progressive items or Magic, families are kept out")
    check(seed.skulltula_holds("Item_Range_Bow", seed.PROGRESSION, seed.skull_families(seed.SKULL_FAMILY_FROM, False, False)),
          "without Progressive items the Bow is no longer a drop")
    src = open(seed.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check(main_src.count("skull_families(placement, a.progressive, a.magic)") == 2,
          "the placing and its last check do not both use the seed's families")
    print("FAIL" if failed else "PASS: no Gold Skulltula drops an item of a family with Progressive items")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

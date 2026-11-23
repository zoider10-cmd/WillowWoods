"""Bug 116 (the owner's seed, 2026-11-23): a Gossip Stone said "the Fairy Bless MPDouble", the item's file name. Every item
a hint can name has words of its own (HINT_WORDS or ITEM_WORDS), the game's own name for it. No game files.

python -I -B tests/test_rando_hint_names.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

NAMED = {"Item_FairyBless_MPDouble": "the gift of doubled magic", "Item_FairyBless_MP": "the gift of improved spin",
         "Item_FairyBless_DefenseDouble": "the gift of halved damage", "Item_DinFire": "Din's Fire",
         "Item_Arrow_Fire": "the Fire Arrows", "Item_AgonyStone": "the Echo Gem", "Item_Stone_Forest": "the Kokiri Emerald",
         "Item_Medal_Shadow": "the Shadow Medallion", "Item_BombBag_Medium": "a Bigger Bomb Bag"}


def main():
    failed = False
    for item, words in NAMED.items():
        if seed.hint_item(item) != words:
            failed = True
            print("FAIL: %s is %r in a hint, not %r" % (item, seed.hint_item(item), words))
    pool = set(seed.REWARD_ITEMS) | set(seed.SKULLTULA_MORE) | set(seed.PROGRESSION) | {g.item for g in seed.GIFTS}
    for item in sorted(i for i in pool if isinstance(i, str)):
        if "_" in item and seed.hint_item(item) == "the " + seed.spaced(item) and seed.spaced(item).count(" ") >= 2:
            failed = True
            print("FAIL: %s has no words of its own in a hint (%r)" % (item, seed.hint_item(item)))
    print("FAIL" if failed else "PASS: hints name items by their own names")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

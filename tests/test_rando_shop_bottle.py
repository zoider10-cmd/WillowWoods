"""Bug 113 (the owner's run 2026-11-23): the Goron shop would not sell a shelf's Empty Bottle without an empty bottle.
The shops' flow sorts the item picked by its pouch name, and the Empty Bottle (Item_Bottle) is of a bottle's contents'
kind (5): shop_bottle_flow puts a question of Shop_SelectItemName == Item_Bottle before kind 5 of both questions (the
sale's check and the sale itself), its answer 0 going the way of every other item. Checked by source; the flow itself by
the seed tool's write. No game files.

python -I -B tests/test_rando_shop_bottle.py
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
    src = open(seed.__file__, encoding="utf-8").read()
    check(seed.SHOP_BOTTLE == "Item_Bottle" and seed.SHOP_FLOW == "Event/EventFlow/DisplayShop.bfevfl.zs", "SHOP_BOTTLE or SHOP_FLOW changed")
    body = src[src.index("def shop_bottle_flow(raw):"):src.index("def tower_anchor(data):")]
    check('"PouchSystemActor.EventQueryIsAnyBottleEmpty"' in body and '"Npc_EventStarter.EventQueryHavePlayedGetEventAtShop"' in body,
          "shop_bottle_flow does not find both questions of the item's kind (the sale's check and the sale)")
    check("(0, hits[0].data.cases[0].v), (1, hits[0].data.cases[5].v)" in body and "hits[0].data.cases[5].v = e" in body,
          "the Empty Bottle does not go the way of kind 0, or the others not their own kind 5 way")
    check('startswith("Willow")' in body, "a flow changed already is not refused")
    main_src = src[src.index("\ndef main():"):]
    check("gift_files[SHOP_FLOW] = shop_bottle_flow(was)" in main_src and "gift_sizes[SHOP_FLOW[:-3]]" in main_src and
          main_src.index("shop_bottle_flow(was)") < main_src.index("    # ---- the size table ----"),
          "the shops' flow is not written (with its size) before the size table")
    check(seed.FIXES_VERSION >= 71, "FIXES_VERSION not past 70: a seed written before keeps the old flow")
    print("FAIL" if failed else "PASS: a shelf's Empty Bottle is sold without an empty bottle")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

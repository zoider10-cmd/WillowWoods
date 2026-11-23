"""Lake Hylia lab's diving game is a check (placement 27, asked 2026-11-23: "i dont think the lake hylia lab diving
game is on the tracker or randomized"): the scientist hands over a Piece of Heart (Npc_Hylia_045_Child's
NpcCommon_HandOver_NpcToPlayer_NoDisplay, as the dog lady and the cucco lady do), made a gift of the shuffle (GIFTS),
with Go there beside him (GIFT_PLACES) and the other logic's rule "LH Lab Dive" (the Golden Scale; its Iron Boots way
is a trick, off: the owner found the boots don't count). Game-free: read from the seed tool and its table."""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402
import overworld_logic as O  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def main():
    gift = next((g for g in S.GIFTS if g.key == "lab_dive"), None)
    check(gift is not None, "the lab's diving game is not a gift of the shuffle")
    if gift:
        check(gift.flow == "Npc_Hylia_045_Child" and gift.olds == ("Obj_Heart_Piece",) and gift.item == "Obj_Heart_Piece",
              "the lab's gift does not take the scientist's Piece of Heart: %r" % (gift,))
        check(gift.area == "HyruleField", "the lab's gift is not counted in Lake Hylia's folder (HyruleField)")
        check(gift.need == S.EVERYTHING, "without the table the lab's gift does not ask for everything")
    check(S.GIFTS_FROM.get("lab_dive") == 27 <= S.PLACEMENT, "seeds before placement 27 would take the lab's gift")
    check(S.GIFT_PLACES.get("lab_dive", ("",))[0] == "CA", "Go there has no place for the lab's gift (either age)")
    check(S.OVERWORLD_GIFTS.get("lab_dive") == "LH Lab Dive" and "LH Lab Dive" in O.NAMED,
          "the lab's gift does not take the other logic's LH Lab Dive rule")
    table = json.load(open(os.path.join(ROOT, "tools", "rando", S.OVERWORLD_RULES_FILE), encoding="utf-8"))["variants"]
    for k, v in sorted(table.items()):
        ways = v["named"].get("LH Lab Dive")
        check(ways is not None, "%s: the table has no LH Lab Dive" % k)
        if ways is not None:
            check(all(way.get("Progressive Scale", 0) >= 2 for way in ways) and not any("Iron Boots" in way for way in ways),
                  "%s: LH Lab Dive is not the Golden Scale's alone: %r" % (k, ways))
    # (the Golden Scale a gating item with Quest rewards from 27, so the rule keeps it; the Tracker's letters "GS")
    seed = open(os.path.join(ROOT, "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    check(S.GOLD_SCALE == "Item_Scale_Gold" and S.GOLD_SCALE_FROM == 27 and S.CHECK_CODES.get(S.GOLD_SCALE) == "GS",
          "the Golden Scale is no gating item of placement 27, or has no Tracker letters")
    check("| ({GOLD_SCALE} if placement >= GOLD_SCALE_FROM else frozenset())" in seed, "Quest rewards does not make the Golden Scale a gating item")
    check(S.overworld_rule([{"Progressive Scale": 2}], frozenset((S.GOLD_SCALE,))) == frozenset((S.GOLD_SCALE,)),
          "the lab's rule drops the Golden Scale even when it is a gating item")
    menu = open(os.path.join(ROOT, "gpu", "vk", "vk_menu.cpp"), encoding="utf-8").read()
    check('{"GS", "Golden Scale", {"Golden Scale"}},' in menu, "the Tracker tab does not know GS")
    print("FAIL" if failed else "PASS: Lake Hylia lab's diving game is a check")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

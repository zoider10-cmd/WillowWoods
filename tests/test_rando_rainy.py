"""A check that is there only for a while holds junk only (placement 27, bug 131, the owner's word 2026-11-23): the
chest on Kakariko's windmill in the rainy village (KakarikoVillage_Adult_Alternative, from the Nocturne scene until the
Shadow Temple is done) can be lost for good, so the seed puts only rupees or ammo there (RAINY_ONLY, junk_holds), never
an item the logic needs, a token, a heart or a song. Game-free: place() is run on made-up spots."""
import os
import random
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def main():
    seed = open(os.path.join(ROOT, "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    check(S.PLACEMENT >= S.RAINY_FROM == 27, "the placement was not raised for the rainy village's check")
    check(0xb588e3f93990af69 in S.RAINY_ONLY, "the rainy windmill chest (#1) is not a check there only for a while")
    check(0xa58e4896b72a2f2a not in S.RAINY_ONLY, "the normal village's windmill chest (#2) was made junk-only too")
    check(set(S.RAINY_ONLY) < set(S.JUNK_ONLY) and 0x561cbe4b374f3739 in S.JUNK_ONLY and 0xff8a367dbd828c94 not in S.JUNK_ONLY,
          "Gerudo Valley grotto's child chest (never reachable) is not junk only, or the adult's is")
    for item in ("TBox_Rupee_Red", "TBox_Rupee_Blue", "TBox_ArrowBundle_Medium", "Item_BombBundle_Small", "TBox_DekuNutBundle"):
        check(S.junk_holds(item), "%s is not junk" % item)
    for item in sorted(S.PROGRESSION) + [S.TOKEN, "Obj_Heart_Piece", "Obj_Heart_Container", "Item_Melody_ShadowNocturne", "Item_Bottle",
                                         "Item_FairyBless_MPDouble", "Item_Wallet_Large"]:
        check(not S.junk_holds(item), "%s counts as junk" % item)
    check("holds.update((h, junk) for h in JUNK_ONLY if h in spots)" in seed and "if placement >= RAINY_FROM:" in seed,
          "the seed does not give the rainy check its junk-only holds")

    # (place(): over many seeds, with the logic, the rainy chest gets only junk)
    rainy = S.RAINY_ONLY[0]
    gating = sorted(S.PROGRESSION)
    junk_items = ["TBox_Rupee_Red", "TBox_Rupee_Blue", "TBox_ArrowBundle_Medium"]
    others = ["Obj_Heart_Piece", "Item_Bottle"]
    spots = {}
    for k, item in enumerate(gating + junk_items + others):
        spots[0x1000 + k] = ("Kakariko Village", item, None, None)
    spots[rainy] = ("Kakariko Village", "TBox_Rupee_Purple", None, None)
    needs = {h: frozenset() for h in spots}
    every = {s[1] for s in spots.values()}
    holds = {rainy: frozenset(i for i in every if S.junk_holds(i))}
    got = set()
    for n in range(60):
        gives, _, _ = S.place(random.Random(n), spots, 3, 1, needs=needs, holds=holds)
        got.add(gives[rainy])
    check(got and all(S.junk_holds(i) for i in got), "the rainy chest was given %s" % sorted(i for i in got if not S.junk_holds(i)))
    print("FAIL" if failed else "PASS: a check there only for a while holds junk only")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

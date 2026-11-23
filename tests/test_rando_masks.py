"""Bug 120 (the owner's run 2026-11-23, their choice: every mask from the start): the Forest Stage's two checks were "in
logic" with no mask, and the masks came only by the mask salesman's trade. Every seed makes the first part of each
HappyMaskShop_HasMask_<mask> formula always true (masks_open, checked by source; seen on the game's list in a scratch seed); from MASKS_FROM the
two checks ask for the way to the shop (the Market, and Zelda's Letter where Kakariko's gate is not Open and the letter
is shuffled). No game files.

python -I -B tests/test_rando_masks.py
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
    check(len(seed.MASK_EXPS) == 8 and "HappyMaskShop_HasMask_Truth" in seed.MASK_EXPS and "HappyMaskShop_HasMask_Skull" in seed.MASK_EXPS,
          "not the eight masks' formulas")
    check(seed.PLACEMENT >= seed.MASKS_FROM and seed.MASK_GIFTS == ("forest_stage_skull", "forest_stage_truth"), "the rules are not new seeds'")
    src = open(seed.__file__, encoding="utf-8").read()
    body = src[src.index("def masks_open(data, names=MASK_EXPS):"):src.index("def ainb_exp_swap(")]
    check("use = [(0, flag), (0, flag), (5,), (4,)]" in body and "[steps[u] for u in use] + [v for _, v in own[1:]]" in body,
          "the formula's first part is not made always true with the rest kept")
    check("first[0] == 10 or first == (0, murmur3(b\"Npc_Hylia_Soldier_003_GateOpen\"))" in body, "a formula not as the game has it is not refused")
    main_src = src[src.index("\ndef main():"):]
    check("new = masks_open(new)" in main_src and main_src.index("new = always_exp(") < main_src.index("new = masks_open(new)"),
          "the list of flags is not given the masks after ALWAYS_EXP")
    check("if gifts[h].key in MASK_GIFTS and placement >= MASKS_FROM:" in main_src and "made = mask_need(made)" in main_src,
          "the Forest Stage's checks do not ask for the way to the masks")
    need = main_src[main_src.index("    def mask_need(made):"):]
    need = need[:need.index("\n    for h, s in spots.items():")]
    check('OVERWORLD_SHOPS["general"]' in need and "frozenset((LETTER,))" in need and "a.gate_open" in need,
          "the way to the shop is not the Market's and the gate's")
    check(seed.FIXES_VERSION >= 74, "FIXES_VERSION not past 73")
    print("FAIL" if failed else "PASS: every mask from the Happy Mask Shop, and the Forest Stage asks for the way to it")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

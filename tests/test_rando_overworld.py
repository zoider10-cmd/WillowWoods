"""Each overworld check by its own rule (placement 23, asked 2026-11-21: Kakariko's child Gold Skulltulas asked for the
Slingshot; a young Link with the forest and Kakariko's gate open had few checks in logic): the table beside the seed tool
(tools/rando/overworld_logic.py), its ways in our items (overworld_rule), a weapon asked of a child's Skulltula, the
gate's setting on the stamp, Bombchu Bowling a child's alone; and the launcher's New seed with "Use this save" starting
the save over. The table is made from the other randomizers' logic (no game file): read here; the seed needs the game."""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def read(*p):
    return open(os.path.join(ROOT, *p), encoding="utf-8").read()


def main():
    seed = read("tools", "rando", "rando_seed.py")
    check(S.PLACEMENT >= S.OVERWORLD_FROM == 23, "the placement was not raised for the overworld's rules")
    table = json.load(open(os.path.join(ROOT, "tools", "rando", S.OVERWORLD_RULES_FILE), encoding="utf-8"))["variants"]
    want = {"%s,%s,%d" % (f, g, d) for f in ("open", "closed_deku", "closed") for g in ("open", "zelda") for d in (0, 1)}
    check(set(table) == want, "the table has not every variant of the settings: %s" % sorted(want - set(table)))
    check(S.overworld_variant(True, True, True, True) == "open,open,1" and S.overworld_variant(False, True, False, False) == "closed_deku,zelda,0"
          and S.overworld_variant(True, False, False, True) == "closed,zelda,1", "the seed's settings pick the wrong table")
    named = set(S.OVERWORLD_GIFTS.values()) | set(S.OVERWORLD_SHOPS.values())
    check(all(named <= set(v["named"]) for v in table.values()), "a gift or a shop the seed takes by name is not in the table")
    check("bombchu" not in S.OVERWORLD_SHOPS, "the Bombchu Shop (open from the start here) asks for what the other logic does")
    # (the ways in our items: one not shuffled is held; sticks bought are the sword; a child's Skulltula a weapon)
    prog = frozenset((S.S, S.SL, S.BB, S.BM))
    got = S.overworld_rule([{"Slingshot": 1}, {"Bomb Bag": 1, "Iron Boots": 1}], prog)
    check(got == S.either([{S.SL}, {S.BB}]), "a way is not turned into our items, or an item not shuffled is not held: %r" % (got,))
    check(S.overworld_rule([{}], prog, child_skulltula=True) == frozenset((S.S,)), "a child's Gold Skulltula asks for no weapon")
    check(S.overworld_rule([{"Boomerang": 1}], prog, child_skulltula=True) == frozenset((S.BM,)), "a weapon in the way is not enough")
    check(S.overworld_rule([{"Buy Deku Stick (1)": 1}], prog) == frozenset((S.S,)), "sticks bought are not the sword (the sticks step's)")
    song = "Item_Melody_ZeldaLullaby"
    check(S.overworld_rule([{"Zeldas Lullaby": 1}], prog, {song: frozenset((S.SL,))}) == frozenset((S.SL,)),
          "a song not shuffled does not ask for its lesson's rule")
    # (Kakariko's gate Open: on the stamp, and the table's; the bowling a child's)
    check('a.gate_open = ini["rando_letter"] == 2' in seed and '(" gate open" if a.gate_open else "")' in seed, "Kakariko's gate Open is not the seed's")
    check(S.BOWLING_FREE == ("bowling_bag", "bowling_heart") and "gifts.update((h, g._replace(need=CHILD)) for h, g in list(gifts.items()) if g.key in BOWLING_FREE)" in seed,
          "Bombchu Bowling still asks for bombs")
    # (the launcher: New seed's "Use this save" starts the save over once the seed is made, its new seed kept)
    launcher = read("launcher", "Launcher.cs")
    check("public static string StartOver(string dir, string saveFolder, string name, bool keepSeed = false)" in launcher and
          "if (saveFolder == Rando && !keepSeed)" in launcher and "SaveSlots.StartOver(dir, SaveCopies.Folders[Mode], n, true)" in launcher and
          "startOver = answer == 1;" in launcher, "New seed's Use this save keeps the save's old progress")
    print("FAIL" if failed else "PASS: each overworld check by its own rule")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

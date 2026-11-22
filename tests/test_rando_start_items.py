"""Starting items (rando_start_items, asked 2026-11-21): the codes read from the options line, the rules taking them as
held, the game side's file, the launcher's list matching the seed tool's, and the game's side giving each one Link
lacks. The pool's change (one of each but the songs out) needs the game's files: not run here."""
import os
import re
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
    check(S.start_codes(" sl, KS,zz,ZL ") == ["KS", "SL", "ZL"], "the options line's codes are not read in the table's order, unknown ones left out")
    held = S.start_held(["SL", "LS"])
    check(S.SL in held and S.LONG in held and "Item_Hookshot" in held, "the Longshot to start does not hold the Hookshot too")
    got = S.start_need(S.either([{S.SL}, {S.BB, S.BM}]), held)
    check(got == S.NONE, "a way left with nothing does not make the check ask for nothing: %r" % (got,))
    check(S.start_need(frozenset((S.SL, S.BB)), held) == frozenset((S.BB,)), "a held item is still asked for")
    check(S.start_lines(["BW", "ZL"]) == ["Weapon_Range_Bow Item_Arrow_Normal 30", "Item_Quiver_Small", "Item_Melody_ZeldaLullaby"],
          "the game side's lines are not the item, its ammo on the first")
    names = set(re.findall(r'OOT_ITEM\("[^"]*", "(\w+)"', read("gpu", "vk", "oot_cheat_items.h")))
    check(all(n in names for _, given, _ in S.START_ITEMS.values() for n in given), "a starting item is not one the game side can give")
    launcher = read("launcher", "Launcher.cs")
    codes = re.findall(r'new\[\] \{ "([A-Z]{2})", "[^"]+" \}', launcher[launcher.index("class StartItemsForm"):launcher.index("public string Codes;")])
    check(codes == list(S.START_ITEMS), "the launcher's Starting items are not the seed tool's, in its order: %r" % (codes,))
    check('lines.Add("rando_start_items=" + startItems);' in launcher, "New seed's window does not keep the starting items with the seed")
    seed = read("tools", "rando", "rando_seed.py")
    check('(" start " + ",".join(a.start) if a.start else "")' in seed and "needs = {h: start_need(n, start_held(a.start)) for h, n in needs.items()}" in seed
          and "spots[h][1] = START_JUNK" in seed, "the starting items are not on the stamp, held by the rules, or out of the pool")
    # (Deku Sticks and Nuts, 2026-11-21: supplies, none out of the pool; with Skip cutscenes their first box is marked seen)
    check(S.START_SUPPLIES == {"DK", "DN"} and "if item in SONG_ITEMS or c in START_SUPPLIES:" in seed and
          S.START_PICKUPS == {"DK": "HavePlayedGetEvent.Item_DekuStick", "DN": "HavePlayedGetEvent.Item_DekuNut"} and
          "**({START_PICKUPS[c]: True for c in a.start if c in START_PICKUPS} if a.skip_cutscenes else {})" in seed,
          "starting sticks or nuts take an item out of the pool, or their first pick-up's box is still shown")
    host = read("host", "hos_main.c")
    check("if (oot_check_count > 0) oot_start_items(c, oot_checks_seed);" in host and '"mods/rando-seed/start_items.txt"' in host
          and "if (oot_start_held(c, names[s])) continue;" in host, "the game's side does not give the starting items Link lacks")
    print("FAIL" if failed else "PASS: starting items")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

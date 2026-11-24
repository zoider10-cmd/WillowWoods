"""Three time savers from the other randomizer (OOTRR's qol, taken 2026-11-22): Any fish wins, Faster Skull Kid game, Skip
the tower escape. Each a setting that moves no item (its word on the stamp's second line), off by default; the flows'
changes are qol_flow's and the tower's anchor tower_anchor's, which stop with nothing written on a flow not as known.
Checked by source and constants (the flows themselves by the seed tool's write). No game files.

python -I -B tests/test_rando_time_savers.py
"""
import os
import re
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
    for key, attr, word, which, flow in (("rando_any_fish", "any_fish", " any fish", "fish", "FISH_FLOW"),
                                          ("rando_skull_kid_fast", "skull_kid_fast", " skull kid fast", "skull kid", "SKULL_KID_FLOW"),
                                          ("rando_skip_tower", "skip_tower", " tower skipped", "tower", "GANON_FLOW")):
        check('"%s": 0' % key in src and 'a.%s = ini["%s"] != 0' % (attr, key) in src, "%s is not read from the options" % key)
        check('(a.%s, "%s")' % (attr, word) in src, "%s is not on the stamp's second line (moves no item)" % key)
        check('(a.%s, %s, "%s")' % (attr, flow, which) in src, "%s's flow is not changed with it on" % key)
        check(which in src[src.index("def qol_flow(raw, which):"):src.index("def tower_anchor(data):")], "qol_flow has no %s" % which)
    check("for saver_on, rel, saver in" in src and src.index("for saver_on, rel, saver in") < src.index("    # ---- the size table ----"),
          "the time savers are not written before the size table")
    check("changed[TOWER_ANCHOR_FILE] = tower_anchor(data)" in src and "sizes[TOWER_ANCHOR_FILE[:-3]]" in src,
          "the tower's preloading anchor is not changed with the escape skipped, or its size is not given to the table")
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    order = re.findall(r"^    X\(([A-Z_]+),", header, re.M)
    at = order.index("ANY_FISH") if "ANY_FISH" in order else -1
    check(at >= 0 and order[at:at + 3] == ["ANY_FISH", "SKULL_KID_FAST", "SKIP_TOWER"] and order.index("FAIRY_PRICES") == at + 3,
          "the three are not the rows after the ones before them, the Great Fairy prices after (a seed ID's order)")
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    check(all('new object[] { "%s",' % k in launcher for k in ("rando_any_fish", "rando_skull_kid_fast", "rando_skip_tower")) and
          '"rando_free_scarecrow", "rando_any_fish", "rando_skull_kid_fast", "rando_skip_tower"' in
          launcher[launcher.index('Title = "QUALITY OF LIFE"'):][:launcher[launcher.index('Title = "QUALITY OF LIFE"'):].index("} },")],
          "the launcher has no rows for them in Quality of life")
    # (v0.1.4's bug, 2026-11-23: the time savers' stamp loop was `for on, word in ...`, which overwrote main's `on`, the
    #  randomizer's own: with Skip the tower escape off, every seed was "randomizer off". No loop in main may take one of
    #  main's own names. An earlier one took `which`, the chests' setting)
    main_src = src[src.index("\ndef main():"):]
    kept = {"on", "which", "seed", "keys_mode", "placement", "a", "game", "mod", "romfs", "logic", "gives", "spots", "needs",
            "stamp", "rest", "changed", "sizes", "gift_files", "gift_sizes"}
    taken = set()
    for m in re.finditer(r"^\s*for ([\w, ()]+?) in ", main_src, re.M):
        taken |= {n.strip("() ") for n in m.group(1).split(",")} & kept
    check(not taken, "a loop in main takes main's own name(s) %s: the value after the loop is the loop's last" % sorted(taken))
    print("FAIL" if failed else "PASS: Any fish wins, Faster Skull Kid game and Skip the tower escape")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

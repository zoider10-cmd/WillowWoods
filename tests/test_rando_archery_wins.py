"""Archery games won whatever the score (rando_archery_wins, asked 2026-11-23, share/todo.md): a Quality of life setting,
off by default, that moves no item (its word on the stamp's second line). With it on, qol_flow sends every score of the
shooting galleries' result talk (MiniGame_HitTarget, MiniGame_Score 0 to 10) the prize's way, and the horseback archery's
"at least 1400" question (Minigame_HorsebackArchery, ARCHERY_TOP) its "yes" way, both prizes. Checked by source and
constants (the flows themselves by the seed tool's write, which stops on a flow not as known). No game files.

python -I -B tests/test_rando_archery_wins.py
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
    check('"rando_archery_wins": 0' in src and 'a.archery_wins = ini["rando_archery_wins"] != 0' in src,
          "rando_archery_wins is not read from the options, off by default")
    check('(a.archery_wins, " archery won")' in src, "it is not on the stamp's second line (moves no item)")
    check('(a.archery_wins, GALLERY_FLOW, "gallery")' in src and '(a.archery_wins, HORSE_ARCHERY_FLOW, "horse")' in src,
          "the two flows are not changed with it on")
    check(getattr(seed, "GALLERY_FLOW", "").endswith("/MiniGame_HitTarget.bfevfl.zs") and
          getattr(seed, "HORSE_ARCHERY_FLOW", "").endswith("/Minigame_HorsebackArchery.bfevfl.zs"), "the flows' files")
    check(getattr(seed, "ARCHERY_TOP", None) == 1400, "the horseback archery's top score is not 1400 (the remake's)")
    body = src[src.index("def qol_flow(raw, which):"):src.index("def tower_anchor(data):")]
    for which in ("gallery", "horse"):
        check('which == "%s"' % which in body, "qol_flow has no %s" % which)
    gallery = body[body.index('which == "gallery"'):body.index('which == "horse"')]
    check("for k in range(10):" in gallery and "set_case(hits[0], k, win)" in gallery and "len(hits) != 1" in gallery,
          "the galleries' scores 0 to 9 do not all go the 10's way, or a flow not as known is not stopped")
    horse = body[body.index('which == "horse"'):]
    check("set_case(hits[0], 0, case(hits[0], 1))" in horse and "len(hits) != 1" in horse,
          "the horseback archery's 'under 1400' does not go its 'at least' way")
    check(src.index("(a.archery_wins, GALLERY_FLOW") < src.index("    # ---- the size table ----"),
          "the flows are not written before the size table")
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    order = re.findall(r"^    X\(([A-Z_]+),", header, re.M)
    check("ARCHERY_WINS" in order and order.index("ARCHERY_WINS") > order.index("FAIRY_PRICES"),
          "the setting is not a row after the ones before it (a seed ID's order)")
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    check('new object[] { "rando_archery_wins", "Archery games won", new[] { "Off", "On" }, new[] { 0, 1 },' in launcher,
          "the launcher has no Off / On row for it")
    no_item = launcher[launcher.index("NoItemKeys = new HashSet<string>"):launcher.index("static bool MovesNoItem")]
    check('"rando_archery_wins"' in no_item, "the launcher does not count it as moving no item")
    qol = launcher[launcher.index('Title = "QUALITY OF LIFE"'):]
    check('"rando_archery_wins"' in qol[:qol.index("} },")], "it is not in the launcher's Quality of life section")
    print("FAIL" if failed else "PASS: Archery games won whatever the score")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

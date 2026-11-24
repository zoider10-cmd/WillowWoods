"""A check's place on the Tracker's maps (asked 2026-11-24): a grotto's chest lies at the grotto's own place, so its dot is put
at the grotto's way in (tools/rando/rando_seed.py CHECK_PLACE), and the line's last field, where Go there puts Link, keeps
the chest's own place. Game-free: check_lines on made-up checks."""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    h = 0xcda7447b91ab4dba
    assert h in S.CHECK_PLACE, "Kokiri Forest's Song of Storms grotto chest has no place of its way in"
    lines = [l for l in S.check_lines([("KokiriForest", (-70.8, 103.6, -63.4), "CA", frozenset(), "Chest (green rupee)", h, "TBox_Rupee_Red"),
                                       ("KokiriForest", (1.0, 2.0, 3.0), "CA", frozenset(), "Chest", 0x1234, "X")], []) if not l.startswith("#")]
    grotto = next(l.split("|") for l in lines if "cda7447b91ab4dba" in l)
    assert grotto[4] == "%.1f %.1f %.1f" % S.CHECK_PLACE[h], "the dot is not at the grotto's way in: %s" % grotto[4]
    assert grotto[8] == "-70.8 103.6 -63.4", "Go there does not keep the chest's own place: %r" % grotto[8:]
    other = next(l.split("|") for l in lines if "0000000000001234" in l)
    assert other[4] == "1.0 2.0 3.0" and len(other) == 8, "another check's place was changed"
    print("PASS: a grotto chest's dot at its way in")
    return 0


if __name__ == "__main__":
    sys.exit(main())

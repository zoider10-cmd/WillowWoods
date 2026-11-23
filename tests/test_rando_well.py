"""Bug 121 (the owner's run 2026-11-23): every Bottom of the Well check asked for Zelda's Lullaby, the way in being ADULT.
From placement WELL_FROM, with the songs shuffled, the well's way in is a young Link out of the forest, the Song of
Storms and the ocarina; each check's own ways ask for the rest. No game files.

python -I -B tests/test_rando_well.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def main():
    check(S.PLACEMENT >= S.WELL_FROM == 26 and S.WELL == "BottomOfTheWell", "new seeds are not made from WELL_FROM")
    real = S._DUNGEON_TABLE[:] if hasattr(S, "_DUNGEON_TABLE") else None
    S._DUNGEON_TABLE[:] = [{1: ([{}], None), 2: ([{"Zeldas Lullaby": 1}], None)}]
    try:
        prog = frozenset(S.PROGRESSION) | {"Item_Melody_ShadowNocturne", S.STORMS, S.OCARINA, S.ZL}
        free = S.dungeon_rule(1, S.WELL, prog, well_child=True)
        check(free == S.CHILD | {S.STORMS, S.OCARINA}, "a check with no ways of its own asks for %r" % (free,))
        check(S.ZL not in free, "Zelda's Lullaby still asked for at the way in")
        check(S.ZL in S.dungeon_rule(2, S.WELL, prog, well_child=True), "a check whose way needs Zelda's Lullaby lost it")
        check(S.dungeon_rule(1, S.WELL, prog) == S.ADULT, "a seed made before WELL_FROM changes")
        nosongs = frozenset(S.PROGRESSION) - {"Item_Melody_ShadowNocturne"}
        check(S.dungeon_rule(1, S.WELL, nosongs, well_child=True) == S.ADULT, "without the songs shuffled the windmill's lesson is not asked")
    finally:
        S._DUNGEON_TABLE[:] = real
    src = open(S.__file__, encoding="utf-8").read()
    check("placement >= DUNGEON_AGES_FROM, placement >= WELL_FROM) if dungeon_on else None" in src, "the seed doesn't pass WELL_FROM")
    print("FAIL" if failed else "PASS: the Bottom of the Well by the Song of Storms, not Zelda's Lullaby")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

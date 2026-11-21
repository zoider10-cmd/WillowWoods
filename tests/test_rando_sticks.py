"""Deku Sticks in the Kokiri Sword's place (placement 20, tools/rando/rando_seed.py STICKS_FROM, stick_need): with the Deku
Tree and the forest's way out open, a rule's sword may be a child's way to Goron City's stick pots instead. Read from
the seed tool's own functions: no game files."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def ways(n):
    return set(n) if isinstance(n, S.Either) else {n}


def main():
    # (the letter not shuffled, or the gate open: Goron City is a child's, the sword is not asked for)
    check(S.stick_need(S.CHILD, False) == frozenset((S.SL,)), "with the letter not shuffled the sword is still asked for")
    # (the letter shuffled: the sword, or the letter, or bombs, the ways up the mountain)
    made = S.stick_need(S.CHILD, True)
    check(ways(made) == {S.CHILD, frozenset((S.SL, S.LETTER)), frozenset((S.SL, S.BB))},
          "with the letter shuffled the sword is not the sword, the letter or bombs: %r" % (made,))
    check(S.LETTER_BOLERO in set().union(*ways(S.stick_need(S.CHILD, True, True))), "the Bolero is not a way with the songs shuffled")
    # (a way with bombs already: the sword simply goes)
    check(S.stick_need(S.ADULT, True) == S.ADULT - {S.S}, "a way with bombs still asks for the sword")
    check(S.stick_need(frozenset((S.BOW,)), True) == frozenset((S.BOW,)), "a way without the sword was changed")
    check(S.PLACEMENT >= S.STICKS_FROM == 20, "the change is not placement 20's")
    script = open(os.path.join(HERE, "..", "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    check("sticks = placement >= STICKS_FROM and a.open_deku and a.open_forest" in script and
          "needs = {h: each(stick_need, n, a.letter, bolero) for h, n in needs.items()}" in script and
          "skull_asks = lambda h, at=None: each(stick_need, skull_sword(h, at), a.letter, bolero)" in script,
          "the chests', gifts', Skulltulas' and pieces' rules are not given the sticks, or not only with both ways open")
    print("FAIL" if failed else "PASS: Deku Sticks for the Kokiri Sword")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""The fussy spots are filled whenever they can be (2026-11-26, share/better-ways-2026-11-26.md G; tools/rando/rando_seed.py
holds_match, place): no game data.

A spot of `holds` (a Gold Skulltula, a pot, a lying piece, a shelf...) takes only some items. Whether the items left could
fill them all was counted taking their kinds as nested, and the filling gave each the first item it may hold: with kinds
that overlap without one being inside the other (since a Skulltula and a pot may hold dungeon items a piece may not), a
later spot could be left with nothing though another sharing fills them all. Seen 2026-11-26: the owner's settings with
Pots off, seed 5004, "a Gold Skulltula or a Piece of Heart has nothing left that it may hold. Nothing written."

- holds_match says exactly whether all can be filled, and how (against trying every way, on small cases);
- place fills them by it when first-come leaves one with nothing; a seed first-come fills is as it was.

    python -I -B tests/test_rando_holds_match.py
"""
import collections
import importlib.util
import itertools
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def every_way(kinds, items):
    spots = [k for k, n in kinds.items() for _ in range(n)]
    if len(spots) > len(items):
        return False
    return any(all(i in k for i, k in zip(way, spots)) for way in set(itertools.permutations(items, len(spots))))


def main():
    rng = random.Random(7)
    for n in range(1500):
        names = "abcde"[:rng.randint(1, 5)]
        kinds = collections.Counter()
        for _ in range(rng.randint(1, 4)):
            kinds[frozenset(rng.sample(names, rng.randint(1, len(names))))] += rng.randint(1, 2)
        items = [rng.choice(names) for _ in range(rng.randint(1, 7))]
        got = S.holds_match(kinds, items)
        check((got is not None) == every_way(kinds, items), "holds_match is wrong for %r and %r: %r" % (dict(kinds), items, got))
        if got is not None:
            used = collections.Counter()
            for kind, given in got.items():
                check(sum(given.values()) == kinds[kind] and all(i in kind for i in given), "a kind's spots are not each given an item it holds: %r" % (got,))
                used.update(given)
            check(all(used[i] <= items.count(i) for i in used), "an item is given more often than it is there: %r" % (got,))
    # the nested count let this through, and it cannot be filled: three spots, two items between them
    a, b, c = frozenset("xy"), frozenset("yz"), frozenset("xz")
    check(S.holds_match({a: 1, b: 1, c: 1}, ["x", "y", "w", "w"]) is None, "three spots are filled with two items")

    # place, no logic: a Skulltula holds x or y, a pot x or q; one x and one y. First-come gives the Skulltula the x
    # when it comes first, and the pot nothing
    spots = collections.OrderedDict(((1, ("Field", "x", False, None)), (2, ("Field", "y", False, None)),
                                     (3, ("Field", "r", None, None)), (4, ("Field", "r", None, None))))
    holds = {3: frozenset("xy"), 4: frozenset("xq")}
    for n in range(60):
        try:
            gives, _, _ = S.place(random.Random(n), spots, 3, 2, None, holds=holds)
        except ValueError as e:
            check(False, "place leaves a spot with nothing though all can be filled (seed %d): %s" % (n, e))
        check(gives[3] == "y" and gives[4] == "x" and sorted(gives.values()) == ["r", "r", "x", "y"], "the spots are not filled by what they hold: %r" % gives)
    # and one that cannot be filled says so
    try:
        S.place(random.Random(1), spots, 3, 2, None, holds={3: frozenset("x"), 4: frozenset("x")})
        check(False, "two spots that hold only the one x are filled")
    except ValueError as e:
        check("nothing left that it may hold" in str(e), "the wrong word for spots that cannot be filled: %s" % e)
    print("PASS: the fussy spots are filled whenever they can be")


if __name__ == "__main__":
    main()

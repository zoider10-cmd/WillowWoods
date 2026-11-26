"""An overworld pot with no rule of its own asks what its area asks of its age (bugs 151 and 154, the owner's run
2026-11-26, placement 38, POT_AREA_FROM; tools/rando/rando_seed.py area_sources, rule_weight, actor_ages, with_way): no
game data.

The nearest ruled actor was its guide: 32 pots only an adult has asked for nothing or the Boomerang alone (a young
Link's Tracker had them in logic, and the shuffle could put an adult's way's item in them), and Kakariko's pots on the
ground asked for the Boomerang, the watchtower Gold Skulltula's.

- a pot takes the easiest ruled actor of its folder of map files that its age has: a pot only an adult has, one only an
  adult has (from the whole overworld when its folder has none); another pot, one a child has;
- a dungeon's pot is left to the nearest of its room;
- a pot only an adult has asks for the way to an adult too (with_way), whatever its rule.

    python -I -B tests/test_rando_pot_area_rules.py
"""
import importlib.util
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


def main():
    f = frozenset
    check(S.PLACEMENT >= S.POT_AREA_FROM == 38, "placement 38 is not the pots' area rules")
    check(S.rule_weight(f()) < S.rule_weight(f("a")) < S.rule_weight(S.Either([f("ab"), f("abc")])) < S.rule_weight(f("abc")) < S.rule_weight(None),
          "the easiest rule is not the one asking for least")
    kak, kok = "Banc/Kakariko/Kakariko_%s.bcett.byml.zs", "Banc/Kokiri/Kokiri_%s.bcett.byml.zs"
    placed = {kak % "Child_Static": [(1, (0, 0, 0), None), (2, (5, 0, 0), None), (10, (5, 0, 1), None)],     # 1 a chest, 2 the tower's Skulltula
              kak % "Adult_Static": [(1, (0, 0, 0), None), (3, (9, 0, 0), None), (4, (9, 0, 9), None), (11, (0, 0, 1), None)],
              kak % "Adult_Dynamic": [(12, (50, 0, 50), None)],
              kok % "Adult_Dynamic": [(13, (0, 0, 0), None), (5, (0, 0, 1), None)], kok % "Child_Static": [(5, (0, 0, 1), None)],
              "Banc/WaterTemple/WaterTemple_Static.bcett.byml.zs": [(14, (0, 0, 0), 2), (6, (0, 0, 1), 2)]}
    ages = S.actor_ages(placed)
    check(ages[1] == "CA" and ages[2] == "C" and ages[3] == "A" and ages[14] == "CA", "an actor's ages are not its map files': %r" % ages)
    adult, harder = f(("Time", "Ocarina")), f(("Time", "Ocarina", "Hookshot"))
    rules = {1: f(), 2: f(("Boomerang",)), 3: harder, 4: adult, 5: f(), 6: f(("Iron",))}
    pots = {10: ["KakarikoVillage", (5, 0, 1), kak % "Child_Static"], 11: ["KakarikoVillage", (0, 0, 1), kak % "Adult_Static"],
            12: ["KakarikoVillage", (50, 0, 50), kak % "Adult_Dynamic"], 13: ["KokiriForest", (0, 0, 0), kok % "Adult_Dynamic"],
            14: ["WaterTemple", (0, 0, 0), "Banc/WaterTemple/WaterTemple_Static.bcett.byml.zs"]}
    got = S.area_sources(pots, placed, rules, skip=("WaterTemple",))
    check(got.get(10) == 1, "a child's pot beside the Skulltula takes its rule, not its area's easiest: %r" % got)
    check(got.get(11) == 4 and got.get(12) == 4, "a pot only an adult has takes a rule a child's actor has (the chest beside it): %r" % got)
    check(5 in rules and got.get(13) == 4, "a pot only an adult has, in a folder with no actor only an adult has, takes a child's: %r" % got)
    check(14 not in got, "a dungeon's pot is taken from its room's nearest")
    check(S.area_sources({1: ["KakarikoVillage", (0, 0, 0), kak % "Child_Static"]}, placed, rules) == {}, "a pot with a rule of its own is given another's")
    # the way to an adult, asked for too
    way = S.Either([f(("Time", "Lullaby")), f(("Time", "Sun"))])
    check(S.with_way(f(), way) == way and S.with_way(None, way) is None and S.with_way(f(("Boomerang",)), None) == f(("Boomerang",)),
          "a rule with the way to an adult is not that way where it asked for nothing, or everything is made less")
    both = S.with_way(S.Either([f(("Bombs",)), f(("Scale",))]), f(("Time",)))
    check(set(both) == {f(("Bombs", "Time")), f(("Scale", "Time"))}, "each way of a rule does not ask for the way to an adult: %r" % (both,))
    check(all(n.startswith(("Kak ", "LH Adult", "GC Rolling Goron as Adult")) for n in S.ADULT_NAMED), "a check that is not an adult's alone stands for the way to an adult")
    print("PASS: an overworld pot asks what its area asks of its age")


if __name__ == "__main__":
    main()

"""The tunics by the game's hot rooms and deep water (placement 17, TUNIC_WATER_FROM): the Zora Tunic wherever the Iron
Boots sink Link, and Zora's Fountain's checks above its water asking for neither (tools/rando/rando_seed.py quest_need,
TUNIC_DRY). Read from the seed tool's own functions: no game files."""
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


def main():
    q = S.quest_need
    lab = S.ADULT | {S.IRON}   # (Lake Hylia's lab tank Gold Skulltula: the boots alone, in Hyrule Field's area)
    check(S.ZT not in q(lab, "HyruleField", True) and S.ZT in q(lab, "HyruleField", True, True),
          "a check that sinks Link with the Iron Boots does not ask for the Zora Tunic from placement 17, or did before")
    check(S.ZT not in q(S.ADULT, "HyruleField", True, True), "a dry check asks for the Zora Tunic")
    # (Zora's Fountain: before 17 every adult check asked for the tunic; from 17 only the one under its water)
    check(S.ZT in q(S.ADULT, "ZoraFountain", True) and S.ZT not in q(S.ADULT, "ZoraFountain", True, True),
          "Zora's Fountain's checks above the water ask for the Zora Tunic from 17, or not before")
    check(S.ZT in q(S.ADULT | {S.IRON}, "ZoraFountain", True, True), "Zora's Fountain's Piece of Heart under the water asks for no tunic")
    check(set(S.TUNIC_DRY) == {0xd0ee852c5e8a8bea, 0xac2e26b5ec7da3a2} and all(v == S.ADULT for v in S.TUNIC_DRY.values()),
          "the fountain's chest and Piece of Heart above the water do not ask for an adult alone")
    # (the heat: unchanged, the crater and the Fire Temple)
    check(S.GT in q(S.ADULT, "DeathMountainCrater", True, True) and S.GT in q(S.ADULT, "FireTemple", True, True) and
          S.ZT in q(S.ADULT, "WaterTemple", True, True), "the crater, the Fire Temple or the Water Temple no longer ask for their tunic")
    check(S.PLACEMENT >= S.TUNIC_WATER_FROM == 17, "the change is not placement 17's")
    script = open(os.path.join(HERE, "..", "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    check(script.count(", placement >= 12, deep)") == 4 and "deep = a.quests and placement >= TUNIC_WATER_FROM" in script and
          "needs = {h: TUNIC_DRY.get(h, n) for h, n in needs.items()}" in script and
          "TUNIC_DRY[h] if deep and h in TUNIC_DRY else heart_rule(h, lying[h][0])" in script,
          "the chests', Skulltulas' and pieces' rules are not given the deep water's tunic by placement")
    print("FAIL" if failed else "PASS: the tunics by hot rooms and deep water")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

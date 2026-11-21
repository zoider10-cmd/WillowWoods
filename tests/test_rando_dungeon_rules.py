"""Each dungeon check by its own rule (placement 21, tools/rando/rando_seed.py DUNGEON_RULES_FROM, dungeon_rule, fit_rule;
the table tools/rando/dungeon_rules.json made by tools/rando/dungeon_logic.py from tools/rando/ootrr). Read from the
seed tool's own functions and the table: no game files."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def ways(n):
    return set(n) if isinstance(n, S.Either) else {n}


def main():
    table = json.load(open(os.path.join(ROOT, "tools", "rando", "dungeon_rules.json"), encoding="utf-8"))
    check(len(table["by_actor"]) >= 150 and all(isinstance(e["ways"], list) and e["ways"] for e in table["by_actor"].values()),
          "the table holds too few dungeon actors, or one without a way")
    known = set(S.DUNGEON_AP_ITEMS)
    used = {(k, v) for e in table["by_actor"].values() for w in e["ways"] for k, v in w.items()}
    check(used <= known, "the table names an item the seed tool can't turn into its own: %r" % sorted(used - known)[:5])
    # ---- a rule from a way: its dungeon's way in and the way's items the seed gates; the others held ----
    S._DUNGEON_TABLE[:] = [{7: [{"Bow": 1}, {"Progressive Hookshot": 2, "Dins Fire": 1, "Magic Meter": 1}]}]
    try:
        prog = frozenset(S.PROGRESSION) | {S.LONG}
        made = S.dungeon_rule(7, "ForestTemple", prog, frozenset((S.DIN,)))
        check(made == S.ADULT | {S.BOW}, "a way with Din's Fire, shuffled and no gating item, is kept beside one without it: %r" % (made,))
        made = S.dungeon_rule(7, "ForestTemple", prog | {S.DIN}, frozenset((S.DIN,)))
        check(ways(made) == {S.ADULT | {S.BOW}, S.ADULT | {S.LONG, S.DIN}}, "a gating Din's Fire's way is not one of the rule's ways: %r" % (made,))
        made = S.dungeon_rule(7, "ForestTemple", frozenset((S.BOW,)), frozenset())
        check(S.ADULT | {S.BOW} in ways(made) and S.ADULT in ways(made), "an item the seed doesn't shuffle is asked for: %r" % (made,))
        check(S.dungeon_rule(8, "ForestTemple", prog) is None and S.dungeon_rule(7, "KokiriForest", prog) is None,
              "a check the table doesn't know, or one out of the dungeons, is given a dungeon's rule")
        made = S.dungeon_rule(7, "SpiritTemple", prog | {"Item_Melody_ShadowNocturne", "Item_Melody_SpiritRequiem"})
        check(S.ADULT | {S.BOW, "Item_Melody_SpiritRequiem"} in ways(made) and S.DESERT | {S.BOW} in ways(made),
              "with the songs shuffled the Spirit Temple is not reached by the Requiem as well as across the desert")
    finally:
        S._DUNGEON_TABLE[:] = []
    # ---- no more ways than the tracker reads ----
    many = S.Either([frozenset(S.CHECK_CODES) - {item} for item in list(S.CHECK_CODES)[:8]])
    check(len("/".join(S.rule_text(w) for w in S.fit_rule(many))) <= S.CHECK_NEED, "a trimmed rule is longer than the tracker reads")
    check(S.fit_rule(frozenset((S.BOW,))) == frozenset((S.BOW,)), "a plain rule is changed by the trim")
    # ---- the setting's steps ----
    script = open(os.path.join(ROOT, "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    check(S.PLACEMENT >= S.DUNGEON_RULES_FROM == 21 and "dungeon_on = placement >= DUNGEON_RULES_FROM and bool(dungeon_table())" in script and
          "needs = {h: own_rule(h, s[0], lambda s=s: rule(s[0], s[6])) for h, s in spots.items()}" in script and
          "skull_rule = lambda h, area: own_rule(h, area, lambda:" in script and "own_rule(h, pieces[h][0], lambda:" in script,
          "the chests', Skulltulas' and pieces' rules are not their own from placement 21")
    check("PROGRESSION = PROGRESSION | DUNGEON_GATES" in script and S.CHECK_CODES.get(S.DIN) == "DF" and
          '{"DF", "Din\'s Fire", {"Din\'s Fire"}},' in open(os.path.join(ROOT, "gpu", "vk", "vk_menu.cpp"), encoding="utf-8").read(),
          "Din's Fire is not a gating item with the fairies shuffled, or the tracker has no letters for it")
    print("FAIL" if failed else "PASS: each dungeon check by its own rule")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

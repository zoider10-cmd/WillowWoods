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
    S._DUNGEON_TABLE[:] = [{7: ([{"Bow": 1}, {"Progressive Hookshot": 2, "Dins Fire": 1, "Magic Meter": 1}], None),
                            9: ([{"Boomerang": 1}], {"child": [{"Boomerang": 1}], "adult": [], "both": [{"Boomerang": 1}]}),
                            10: ([{"Bow": 1}], {"child": [], "adult": [{"Bow": 1}], "both": [{"Bow": 1}]})}]
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
        # (the Spirit Temple by age: a child's check by the Requiem alone, an adult's across the desert or by the Requiem)
        req = "Item_Melody_SpiritRequiem"
        made = S.dungeon_rule(9, "SpiritTemple", prog | {req})
        check(S.CHILD | {S.BM, req} in ways(made) and not any(S.ADULT <= w for w in ways(made) if S.BM in w and len(w) <= 4),
              "a child's Spirit Temple check is not reached by the Requiem without being an adult: %r" % (made,))
        made = S.dungeon_rule(10, "SpiritTemple", prog | {req})
        check(S.DESERT | {S.BOW} in ways(made) and S.ADULT | {S.BOW, req} in ways(made) and S.CHILD | {S.BOW, req} not in ways(made),
              "an adult's Spirit Temple check is not across the desert or by the Requiem as an adult: %r" % (made,))
        made = S.dungeon_rule(9, "SpiritTemple", prog)
        check(all(S.DESERT <= w for w in ways(made)), "without the songs shuffled a child's check does not wait for the desert crossed (the Requiem's lesson)")
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
          "skull_rule = lambda h, area: own_rule(h, area, lambda:" in script and "own_rule(h, lying[h][0], lambda:" in script,
          "the chests', Skulltulas' and pieces' rules are not their own from placement 21")
    check("PROGRESSION = PROGRESSION | DUNGEON_GATES" in script and S.CHECK_CODES.get(S.DIN) == "DF" and
          '{"DF", "Din\'s Fire", {"Din\'s Fire"}},' in open(os.path.join(ROOT, "gpu", "vk", "vk_menu.cpp"), encoding="utf-8").read(),
          "Din's Fire is not a gating item with the fairies shuffled, or the tracker has no letters for it")
    # (placement 25, 2026-11-22: the newer dungeons' table for new seeds, the old one kept for seeds made before; both, with
    #  the overworld's, copied into a built game folder: before, make_game.py left them out and a player's seed asked as
    #  before placement 21)
    newer = json.load(open(os.path.join(ROOT, "tools", "rando", S.DUNGEON_RULES2_FILE), encoding="utf-8"))
    used2 = {(k, v) for e in newer["by_actor"].values() for w in e["ways"] for k, v in w.items()}
    check(S.DUNGEON_RULES2_FROM == 25 and S.PLACEMENT >= 25 and len(newer["by_actor"]) >= len(table["by_actor"]) and used2 <= known,
          "the newer dungeons' table is missing, holds fewer actors, or names an item the seed tool doesn't know")
    check(S.dungeon_table_for(24) == S.DUNGEON_RULES_FILE and S.dungeon_table_for(25) == S.DUNGEON_RULES2_FILE,
          "a seed made before placement 25 does not keep the old table, or a new one does not take the newer")
    make = open(os.path.join(ROOT, "nx2", "make_game.py"), encoding="utf-8").read()
    check('"dungeon_rules.json", "dungeon_rules_25.json", "overworld_rules.json"' in make,
          "a built game folder gets no logic tables: its seeds ask as before placement 21")
    check('shutil.copytree(evfl, os.path.join(out, "rando", "evfl")' in make,
          "a built game folder gets no evfl library: hints, Epona by her song and the quests' order stop the seed")
    print("FAIL" if failed else "PASS: each dungeon check by its own rule")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

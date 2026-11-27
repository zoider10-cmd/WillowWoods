"""The check rules' file: what a check asks for, said in a line of words (tools/rando/rando_seed.py USER_RULES_FILES;
asked 2026-11-26, bugs 155 and 157). No game data.

Where the remake differs from the rules the randomizer came with, a check asked for too little or too much, and each such
bug waited for a table run of over ten minutes an area. A line "<area> | <check> | add: <words>" (or "only:") in
check_rules.txt (the tools') or my_check_rules.txt (the player's own, in the game folder's rando) says it. Checked:
- a file's lines are read: add and only, "," and "and" and "or", adult and child and nothing, the Tracker's item names
  (every one the Tracker's logic names), a note after "#" but not "Pot #3"; a line it cannot read is said and left out;
- a check is found by its area and name as the list has them, one without a name of its own by its place;
- its rule: add puts the words with each way it had, only in their place; adult is the way to an adult;
- the Tracker lists it for the age its lines say;
- the file that comes with the tools reads without a fault and has bugs 155 and 157; the build copies it; a seed keeps
  the lines it was made with, and the same seed written again takes those.

    python -I -B tests/test_rando_check_rules.py
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

SAMPLE = """# a note
Kakariko Village | Piece of Heart | add: adult, Hookshot   # bug 155
Goron City | Chest (purple rupee) #1 | add: Hookshot
Hyrule Field | Gold Skulltula at -40 158 201 | only: Kokiri Sword or Fairy Slingshot and Bomb Bag or adult
Market | Pot #3 | ONLY: nothing
Lost Woods | A scrub | add: child
Zora's River | #845ba51dc18c855e | add: Silver Gauntlets
Nowhere | X | add: Spoon
a line that is none
Somewhere | Y | take: Hookshot
"""
TABLE_WORDS = {"Progressive Hookshot": "HOOK", "Kokiri Sword": "SWORD", "Slingshot": "SLING", "Bomb Bag": "BOMBS", "Progressive Strength Upgrade": "LIFT"}


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    rules, wrong = S.user_rules_parse(SAMPLE, "f")
    check(len(rules) == 6 and len(wrong) == 3 and "Spoon" in wrong[0] and "f line 8" in wrong[0] and "f line 9" in wrong[1] and "f line 10" in wrong[2],
          "the lines read, or the faults said: %r %r" % (rules, wrong))
    heart, chest, skull, pot, scrub, cave = rules
    check((heart.area, heart.name, heart.only, heart.ways, heart.ages) == ("Kakariko Village", "Piece of Heart", False, [({"Progressive Hookshot": 1}, True)], "A"),
          "an adult's line: %r" % (heart,))
    check(chest.name == "Chest (purple rupee) #1" and chest.ways == [({"Progressive Hookshot": 1}, False)] and chest.ages is None,
          "a check's number is taken for a note: %r" % (chest,))
    check(skull.only and skull.ways == [({"Kokiri Sword": 1}, False), ({"Slingshot": 1, "Bomb Bag": 1}, False), ({}, True)] and skull.ages == "CA",
          "ways and ages: %r" % (skull,))
    check(pot.only and pot.ways == [({}, False)] and pot.ages is None, "nothing: %r" % (pot,))
    check(scrub.ages == "C" and scrub.ways == [({}, False)], "a child's: %r" % (scrub,))
    check(cave.name == "#845ba51dc18c855e" and cave.ways == [({"Progressive Strength Upgrade": 2}, False)], "a check by its hash: %r" % (cave,))
    # (every item the Tracker's logic names can be written)
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    table = menu[menu.index("constexpr LogicItem kLogicItems[] = {"):]
    table = table[:table.index("\n};")]
    named = re.findall(r'\{"[A-Z0-9]+", "([^"]+)", \{', table)
    check(len(named) >= 25, "the Tracker's item names were not read: %r" % (named,))
    unknown = [n for n in named if n.lower() not in S.USER_ITEMS and "Wallet" not in n and "token" not in n.lower()]
    check(not unknown, "items the Tracker names that a line cannot: %r" % (unknown,))
    known = dict(S.DUNGEON_AP_ITEMS)
    known.update(S.OVERWORLD_AP_ITEMS)
    check(all(v in known for v in S.USER_ITEMS.values()), "a word names an item the tables don't have: %r" % ([k for k, v in S.USER_ITEMS.items() if v not in known],))
    # ---- a check is found by its area and name, or its place ----
    names = S.user_names(["# the header|a|b|c|d|e|f",
                          "Kakariko Village|Piece of Heart|KakarikoVillage|CA|-44.1 108.0 112.0|-|f8c7601da7dd887e|Item",
                          "Goron City|Chest (purple rupee) #1|GoronCity|CA|-52.2 94.8 26.3|BM|97e2ec1944316626|Item",
                          "Hyrule Field|Gold Skulltula|HyruleField|CA|-39.6 158.2 200.7|-|04be4a8ff29f2099|Item",
                          "Hyrule Field|Gold Skulltula|HyruleField|CA|70.5 167.4 263.8|-|1e38e8d23596eecf|Item",
                          "Market|A shelf|Market|C|1.0 2.0 3.0|-|-|Item"])
    found, lost = S.user_rules_found(rules, names)
    check(set(found) == {0xf8c7601da7dd887e, 0x97e2ec1944316626, 0x04be4a8ff29f2099, 0x845ba51dc18c855e} and len(lost) == 2 and "Pot #3" in lost[0],
          "the checks found: %r, not found: %r" % (found, lost))
    check(S.user_rule_key("Hyrule  FIELD", "gold skulltula", (-0.4, 158.2, 200.7)) == ("hyrule field", "gold skulltula at 0 158 201"), "a place of minus nought")
    # ---- a check's rule with its lines ----
    made = lambda ways: S.either([frozenset(TABLE_WORDS[k] for k in w) for w in ways])
    adult = S.either([frozenset(("TIME", "OCARINA")), frozenset(("DOOR",))])
    two = S.either([frozenset(("A",)), frozenset(("B",))])
    got = S.user_need(two, found[0x97e2ec1944316626], made, adult)
    check(set(got) == {frozenset(("A", "HOOK")), frozenset(("B", "HOOK"))}, "add: each way with the words: %r" % (got,))
    got = S.user_need(S.NONE, found[0xf8c7601da7dd887e], made, adult)
    check(set(got) == {frozenset(("HOOK", "TIME", "OCARINA")), frozenset(("HOOK", "DOOR"))}, "adult: the way to an adult too: %r" % (got,))
    got = S.user_need(two, found[0x04be4a8ff29f2099], made, adult)
    check(set(got) == {frozenset(("SWORD",)), frozenset(("SLING", "BOMBS")), frozenset(("TIME", "OCARINA")), frozenset(("DOOR",))}, "only: in its place: %r" % (got,))
    nothing = S.user_rules_found(S.user_rules_parse("a | b | only: nothing")[0], {("a", "b"): 1})[0][1]
    check(S.user_need(two, nothing, made, adult) == S.NONE, "only: nothing")
    check(S.user_need(None, found[0x97e2ec1944316626], made, adult) is None, "a check that asked for everything asks for less")
    check(S.user_need(S.NONE, found[0xf8c7601da7dd887e], made, None) == frozenset(("HOOK",)), "no way to an adult known: the items alone")
    # ---- the Tracker's ages ----
    check(S.user_ages("CA", found[0xf8c7601da7dd887e]) == "A" and S.user_ages("CA", found[0x97e2ec1944316626]) == "CA" and S.user_ages("A", None) == "A",
          "a check's ages by its lines")
    # ---- the tools' own file, the build, the seed ----
    text = (ROOT / "tools" / "rando" / S.USER_RULES_FILES[0]).read_text(encoding="utf-8")
    shipped, faults = S.user_rules_parse(text)
    check(not faults and [(r.area, r.name) for r in shipped][:3] == [("Kakariko Village", "Piece of Heart"), ("Goron City", "Chest (green rupee)"), ("Goron City", "Chest (purple rupee) #1")],
          "the tools' file: %r %r" % (faults, shipped))
    check(S.user_rules_parse(S.USER_RULES_MINE) == ([], []), "the player's file starts with a rule, or a fault")
    make = (ROOT / "nx2" / "make_game.py").read_text(encoding="utf-8")
    check('"check_rules.txt"):' in make, "the build does not copy the tools' check rules beside the seed tool")
    src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("if same_seed:\n            with open(os.path.join(mod, USER_RULES_USED), encoding=\"utf-8\") as f:" in src and
          "f.write(user_text)" in src, "a seed does not keep the lines it was made with, or the same seed written again does not take them")
    check("skull_asks = lambda h, at=None: user_rule(h, skull_before(h, at))" in src and "needs[h] = user_rule(h, needs[h])" in src and
          "if USER_AGAIN:" in src, "the rules do not reach every kind of check, or a first seed is not made again with its checks found")
    print("PASS: the check rules' file")


if __name__ == "__main__":
    main()

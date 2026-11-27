"""Dodongo's Cavern's way in is the Bomb Bag or the Goron's Bracelet, not both (tools/rando/rando_seed.py
FLOWER_ENTRY_FROM, placement 40; bug 158, the owner's run 2026-11-26). No game data.

"Every check asks for the Bomb Bag; much of it can be done with the Goron's Bracelet." The checks' own ways said so
already (the dungeons' table); the way in asked for bombs, the Quest rewards' step named the bracelet on every way and
Open forest exit's step bombs again. The remake's wall at the door is a bomb flower's: the bracelet lifts it, and Link's
own bombs open it too. Checked, on the dungeons' table as a seed reads it, through the steps a seed takes
(dungeon_rule, quest_need, forest_open):
- at placement 39 every way of every check of the cavern names the Bomb Bag and the bracelet (the bug);
- at placement 40 a check with a flower's way (the Compass chest, the Bomb Bag's chest) has a way without the Bomb Bag
  and a way without the bracelet, no way names both where one does, and no way says less than nothing (none is empty
  with the forest shut);
- the checks whose every way is bombs in the table (the two chests behind walls, King Dodongo) still ask for the Bomb
  Bag on every way, and not for the bracelet;
- no check of the cavern asks for more than before: whoever met an old way meets a new one;
- without Quest rewards (the bracelet no gating item) the rules are the ones of placement 39;
- the other dungeons' rules are the same at both placements;
- main sets the switch from the seed's placement, and PLACEMENT is past it.

    python -I -B tests/test_rando_flower_entry.py
"""
import importlib.util
import json
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


def ways(rule):
    return [frozenset(w) for w in rule] if isinstance(rule, S.Either) else [frozenset(rule)]


table = json.loads((ROOT / "tools" / "rando" / S.DUNGEON_RULES2_FILE).read_text(encoding="utf-8"))["by_actor"]
actors = {int(k): v for k, v in table.items()}
cavern = {h: v for h, v in actors.items() if v["folder"] == "DodongoCavern"}
check(len(cavern) >= 15, "the table has %d actors of the cavern" % len(cavern))
named = lambda name: next(h for h, v in cavern.items() if v["names"] == [name])
QUESTS = S.PROGRESSION | S.QUEST_GATES
BB, BR = S.BB, S.BR


def rules(placement, progression, quests=True, forest=False):
    """{actor: its rule} for every dungeon actor, through a seed's steps"""
    S.dungeon_table_for(placement)
    S.flower_entry_for(placement)
    out = {}
    for h, v in actors.items():
        rule = S.dungeon_rule(h, v["folder"], progression)
        if rule is None:
            continue
        if quests:
            rule = S.each(S.quest_need, rule, v["folder"], True, False)
        if forest:
            rule = S.each(S.forest_open, rule, v["folder"])
        out[h] = rule
    return out


for forest in (False, True):
    old, new = rules(39, QUESTS, forest=forest), rules(40, QUESTS, forest=forest)
    # the bug, as it was
    for h in cavern:
        check(all(BB in w and BR in w for w in ways(old[h])), "placement 39: %s did not ask for both (the test's premise)" % cavern[h]["names"])
    # a flower's way
    for name in ("Dodongos Cavern Compass Chest", "Dodongos Cavern Bomb Bag Chest", "Dodongos Cavern Map Chest"):
        w = ways(new[named(name)])
        check(any(BB not in x for x in w) and any(BR not in x for x in w), "%s: no way without the Bomb Bag, or none without the bracelet: %r" % (name, w))
    # bombs on every way of the table: still bombs, and no bracelet
    always = [h for h, v in cavern.items() if all("Bomb Bag" in way for way in v["ways"])]
    check({cavern[h]["names"][0] for h in always} >= {"Dodongos Cavern Lobby Bombable Chest", "Dodongos Cavern Staircase Top Bombable Chest",
                                                      "Dodongos Cavern King Dodongo Heart"}, "the table's bombs-only checks changed")
    for h in always:
        check(all(BB in w and BR not in w for w in ways(new[h])), "%s: not bombs on every way, or the bracelet too: %r" % (cavern[h]["names"], ways(new[h])))
    for h in cavern:
        w = ways(new[h])
        check(all(x & {BB, BR} for x in w), "%s: a way with neither the Bomb Bag nor the bracelet: %r" % (cavern[h]["names"], w))
        check(not any(a < b for a in w for b in w), "%s: a way that holds another whole: %r" % (cavern[h]["names"], w))
        # never more than before: every old way (which had both) is met by holding it, so some new way is within it
        for was in ways(old[h]):
            check(any(x <= was for x in w), "%s: asks for more than before (%r, was %r)" % (cavern[h]["names"], w, was))
        if not forest:
            check(all(x >= S.CHILD for x in w), "%s: a way without the forest's way out: %r" % (cavern[h]["names"], w))
    # the other dungeons: as they were
    for h, v in actors.items():
        if h in old and v["folder"] != "DodongoCavern":
            check(old[h] == new[h], "%s (%s) changed" % (v["names"], v["folder"]))

# without Quest rewards: as before
old, new = rules(39, S.PROGRESSION, quests=False), rules(40, S.PROGRESSION, quests=False)
check(old == new, "without Quest rewards the rules changed")
old, new = rules(39, S.PROGRESSION, quests=False, forest=True), rules(40, S.PROGRESSION, quests=False, forest=True)
check(old == new, "without Quest rewards, Open forest exit: the rules changed")

# the steps alone
S.flower_entry_for(39)
check(S.quest_need(S.CHILD | {BB}, "DodongoCavern") == S.CHILD | {BB, BR} and S.forest_open(S.CHILD | {BR}, "DodongoCavern") == frozenset({BR, BB}), "placement 39's steps changed")
S.flower_entry_for(40)
check(S.quest_need(S.CHILD | {BB}, "DodongoCavern") == S.CHILD | {BB} and S.quest_need(S.CHILD, "DodongoCavern") == S.CHILD | {BR},
      "quest_need: bombs' way is given the bracelet, or a way with neither is not")
check(S.forest_open(S.CHILD | {BR}, "DodongoCavern") == frozenset({BR}) and S.forest_open(S.CHILD, "DodongoCavern") == frozenset({BB}),
      "forest_open: the bracelet's way is given bombs, or a way with neither is not")
check(S.quest_need(S.CHILD, "GoronCity") == S.CHILD and S.forest_open(S.CHILD | {BB}, "GoronCity") == frozenset({BB}), "another area's steps changed")
S.flower_entry_for(0)

src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
main = src[src.index("\ndef main():"):]
check("flower_entry_for(placement)" in main and main.index("flower_entry_for(placement)") < main.index("def own_rule("), "main does not set the switch before the rules")
check(S.PLACEMENT >= S.FLOWER_ENTRY_FROM == 40, "PLACEMENT is not past FLOWER_ENTRY_FROM")
print("ok: Dodongo's Cavern's way in is bombs or the bracelet (%d actors)" % len(cavern))

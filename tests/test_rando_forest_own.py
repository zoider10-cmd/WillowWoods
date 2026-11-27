"""With Open forest exit a dungeon check keeps the Slingshot or the sword its own way asks for (tools/rando/rando_seed.py
OWN_KEPT_FROM, placement 41; bug 163, found reading the rules 2026-11-27). No game data.

forest_open takes the forest's way out (the sword and the Slingshot) off a rule that holds both. On a dungeon check's
whole rule it could not tell the way out from a Slingshot the check itself asks for: Dodongo's Cavern's Bomb Bag chest
("the bracelet and the Slingshot" in the table: the eye switches) read "the bracelet". From placement 41 the step is
done on the way in alone, inside dungeon_rule, and main does not do it again. Checked, on the dungeons' table:
- the old way (the step on the whole rule) loses the Bomb Bag chest's Slingshot: the bug, as it was;
- the new way (dungeon_rule's forest) keeps it on the bracelet's way, and no way of the chest is the bracelet alone;
- every check of the cavern whose every table way names the Slingshot or the sword still names one on every way;
- no way in keeps the forest's way out: a cavern way without an own Slingshot has none (Open forest exit still works);
- a rule with everything in it (Ganon's Castle's way in) is the same either way;
- without the setting (forest off) dungeon_rule gives what it gave;
- main asks dungeon_rule for it from OWN_KEPT_FROM with Open forest exit only, and skips its own step on those checks.

    python -I -B tests/test_rando_forest_own.py
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
named = lambda name: next(h for h, v in cavern.items() if v["names"] == [name])
P = S.PROGRESSION | S.QUEST_GATES
S.dungeon_table_for(41)
S.flower_entry_for(41)
SL, SW, BR, BB = S.SL, S.S, S.BR, S.BB


def old(h, area):
    return S.each(S.forest_open, S.each(S.quest_need, S.dungeon_rule(h, area, P), area, True, False), area)


def new(h, area):
    return S.each(S.quest_need, S.dungeon_rule(h, area, P, forest=True), area, True, False)


chest = named("Dodongos Cavern Bomb Bag Chest")
check(any("Slingshot" in w and "Bomb Bag" not in w for w in cavern[chest]["ways"]), "the table's Bomb Bag chest has no Slingshot way without bombs (the test's premise)")
check(frozenset({BR}) in ways(old(chest, "DodongoCavern")), "the old way keeps the chest's Slingshot (the test's premise): %r" % ways(old(chest, "DodongoCavern")))
got = ways(new(chest, "DodongoCavern"))
check(frozenset({BR, SL}) in got and frozenset({BR}) not in got, "the Bomb Bag chest: %r" % got)

own = {"Slingshot": SL, "Kokiri Sword": SW}
for h, v in cavern.items():
    got = ways(new(h, "DodongoCavern"))
    if all(any(n in w for n in own) for w in v["ways"]):
        check(all(x & {SL, SW} for x in got), "%s: every table way has the Slingshot or the sword, a rule's way has neither: %r" % (v["names"], got))
    if not any(n in w for w in v["ways"] for n in own):
        check(not any(x & {SL, SW} for x in got), "%s: no table way has the Slingshot or the sword, the rule has (the way out kept): %r" % (v["names"], got))
    check(all(x & {BB, BR} for x in got), "%s: a way with neither bombs nor the bracelet: %r" % (v["names"], got))

castle = next(h for h, v in actors.items() if v["folder"] == "InsideGanonCastle")
check(old(castle, "InsideGanonCastle") == new(castle, "InsideGanonCastle"), "Ganon's Castle's rule changed")
for h, v in actors.items():   # (forest off: as it was)
    check(S.dungeon_rule(h, v["folder"], P) == S.dungeon_rule(h, v["folder"], P, forest=False), "forest=False is not the default")
S.flower_entry_for(0)

src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
main = src[src.index("\ndef main():"):]
check("own_kept = placement >= OWN_KEPT_FROM and bool(a.open_forest)" in main, "main's switch")
check("placement >= BOTTLE_ENTRY_FROM, own_kept) if dungeon_on else None" in main and "if own_kept:\n                opened.add(h)" in main,
      "main does not ask dungeon_rule for it, or does not note the check")
check("need if h in opened else each(forest_open, need, area)" in main, "main's step is done again on a check that has it")
check(main.count("forest(n, spots[h][0], h)") == 1 and main.count("forest(need, area, h)") == 2 and "forest(need, area)" not in main,
      "a call of main's step without the check")
check(S.PLACEMENT >= S.OWN_KEPT_FROM == 41, "PLACEMENT is not past OWN_KEPT_FROM")
print("ok: a dungeon check's own Slingshot stays with Open forest exit")

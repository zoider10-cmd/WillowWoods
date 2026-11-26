"""A bean-soil Gold Skulltula asks for a bottle (bug 84, tools/rando/rando_seed.py soil_need, placement 13): no game data.

The owner's run 2026-11-19: the Tracker had "Gold Skulltula, bean soil (child)" in logic with no bottle. Such a Skulltula
comes out only for a bottle's bugs, and with Quest rewards the bottles are shuffled gifts no rule asked for. Checked:
- soil_need adds the bottle to each way of a rule, only for a soil Skulltula and only where the bottles are gating items;
- placement 13 is BOTTLE_FROM; the seed makes the bottle a gating item from it when a gift gives one, and asks the soil
  Skulltulas' rules through soil_need with the map's soil mark;
- the Tracker has the bottle's letters, read from the Inventory's Empty Bottle row.

    python -I -B tests/test_rando_soil_bottle.py
"""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    S = seed
    check(S.soil_need(S.CHILD, True, True) == S.CHILD | {S.BOTTLE}, "a soil Skulltula does not ask for a bottle")
    check(S.soil_need(S.CHILD, False, True) == S.CHILD and S.soil_need(S.CHILD, True, False) == S.CHILD,
          "a Skulltula asks for a bottle off soil, or where the bottles are not gating items")
    ways = S.either([S.CHILD, S.ADULT])
    made = S.soil_need(ways, True, True)
    check(isinstance(made, S.Either) and all(S.BOTTLE in way for way in made), "a way of a rule of two lacks the bottle")
    check(S.PLACEMENT >= S.BOTTLE_FROM == 13, "placement 13 is not the bottle's")
    script = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("if placement >= BOTTLE_FROM and any(g.item == BOTTLE for g in gifts.values()):" in script and
          "PROGRESSION = PROGRESSION | {BOTTLE}" in script, "the bottle is not a gating item where a gift gives one")
    check('soil_need(skull_rule(h, area), about.get(h, {}).get("soil"), bottles)' in script and
          "bottles = BOTTLE in PROGRESSION" in script, "the Skulltulas' rules are not asked through soil_need with the soil mark")
    # (bug 140, the owner's run 2026-11-25: Kokiri Forest's soil Skulltula in logic again with no bottle. From placement 23
    #  an overworld Skulltula's rule is its table's (over_rule), whose ways for the soil ones name no bottle)
    check(S.PLACEMENT >= S.SOIL_OVER_FROM == 35, "placement 35 is not the table rules' bottle")
    over = script[script.index("        def skull_over(h, at=None):"):]
    over = over[:over.index("        def heart_over(h):")]
    check('made = soil_need(made, about.get(h, {}).get("soil"), bottles)' in over and "placement >= SOIL_OVER_FROM" in over,
          "an overworld Skulltula's table rule is not asked through soil_need")
    check("tneeds = {h: tracked(h, tracked_soil(h, n), ending_of.get(h))" in script and
          "fit_rule(tracked_soil(h, skull_need(h)))" in script and
          "each(lambda way: frozenset(way) | {BOTTLE}, n) if n is not None and about.get(h, {}).get(\"soil\") else n" in script,
          "the Tracker's file does not ask for a bottle at every soil Skulltula")
    line = S.check_lines([], [("KokiriForest", (8.2, 112.6, -23.3), "C", S.soil_need(S.either([frozenset((S.BM,)), frozenset((S.BB,))]), True, True),
                               "Gold Skulltula, bean soil", 0x858f5000ad57b2cc, S.TOKEN)])
    check(any("BM,BO/BB,BO" in l or "BO,BM" in l or ("BO" in l.split("|")[5] and "/" in l.split("|")[5]) for l in line),
          "a soil Skulltula's ways on the Tracker lack the bottle: %s" % line)
    check(S.CHECK_CODES.get(S.BOTTLE) == "BO", "the Tracker has no letters for the bottle")
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    check('{"BO", "a bottle", {"Empty Bottle"}},' in menu, "the Tracker's menu does not read the bottle's letters")
    print("PASS: a bean-soil Gold Skulltula asks for a bottle")


if __name__ == "__main__":
    main()

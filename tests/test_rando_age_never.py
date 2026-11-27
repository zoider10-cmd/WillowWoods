"""Checks an age can never get are no checks (tools/rando/rando_seed.py AGE_NEVER, the owner's run 2026-11-26). No game data.

Zora's Fountain's hidden cave lies under three silver boulders, an adult's alone to lift. Its two pots are in both ages'
maps: the child's two were checks a young Link's Tracker had in logic for good ("these 2 checks exist but are never
accessible by child Link"), and the adult's two did not ask for the Silver Gauntlets. Checked:
- from placement AGE_NEVER_FROM the child's two are no checks, and before it they are (an installed seed keeps its checks);
- the adult's two take the rule of the cave's own Gold Skulltula, when they take part, from that placement on;
- the tables rule that Skulltula with the Silver Gauntlets, and the place where every pot of a map is taken asks first.

    python -I -B tests/test_rando_age_never.py
"""
import importlib.util
import json
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
    child = (0xc41bbedc31e2bc36, 0xf9f8b45ebb2cb157)   # (Zora's Fountain's Pot #6 and #8 of the owner's seed, the child's)
    adult = (0xabf02ae0410c5863, 0x9a9f28c6d8ce0d45)   # (its Pot #5 and #7, the adult's, at the same places)
    skull = 0x845ba51dc18c855e                         # (the cave's Gold Skulltula)
    first = seed.AGE_NEVER_FROM
    check(seed.PLACEMENT >= first, "the placement is before the one that takes the pots out")
    for h in child:
        check(h in seed.AGE_NEVER and not seed.pot_takes_part(h, first) and not seed.pot_takes_part(h, seed.PLACEMENT),
              "a pot a child can never get is a check")
        check(seed.pot_takes_part(h, first - 1), "a seed of before lost a check")
    for h in adult:
        check(seed.pot_takes_part(h, first) and h not in seed.AGE_NEVER and seed.RULE_FIXED.get(h) == skull, "the adult's pot is no check, or does not ask as the cave's Skulltula")
    check(seed.pot_takes_part(0x1234, first), "another pot is no check")
    pots = {adult[0]: ["ZoraFountain", (88.2, 103.7, 45.5), "Banc/ZoraFountain/ZoraFountain_Adult_Dynamic.bcett.byml.zs"], 0x1234: ["Market", (0, 0, 0), "x"]}
    check(seed.rules_fixed({0x1234: 0x99, adult[0]: 0x77}, pots, first) == {0x1234: 0x99, adult[0]: skull}, "the adult's pot keeps its area's rule")
    check(seed.rules_fixed({adult[0]: 0x77}, pots, first - 1) == {adult[0]: 0x77}, "a seed of before asks otherwise")
    check(adult[1] not in seed.rules_fixed({}, pots, first), "a pot that does not take part is given a rule")
    # (the Skulltula's rule in the tables: every way asks for the Silver Gauntlets)
    table = json.loads((ROOT / "tools" / "rando" / "overworld_rules.json").read_text(encoding="utf-8"))
    found = 0
    for variant in (table.get("variants") or {"": table}).values():
        row = (variant.get("by_actor") or {}).get(str(skull))
        if row:
            found += 1
            check("ZF GS Hidden Cave" in row.get("names", ()) and row.get("ways") and
                  all(way.get("Progressive Strength Upgrade", 0) >= 2 for way in row["ways"]), "the cave's Skulltula's rule: %s" % json.dumps(row)[:300])
    check(found, "the tables do not rule the cave's Gold Skulltula")
    # (the owner, the same day: Gerudo Valley's far side and the Haunted Wasteland are no child's; the cave's Skulltula an adult's)
    valley, valley_chest = (0x801e8f572111c0a2, 0xb6e63585e5882561, 0x0d243035ec83ec5e, 0xcf2e0e3d96f5fb1c), 0x561cbe4b374f3739
    waste = (0x699e0e61241674cf, 0x3e1ef169d1d1c1ed, 0x266ec45f7f3b6e25, 0xd2ee747a35fff650)
    for h in valley + waste:
        check(not seed.pot_takes_part(h, first) and seed.pot_takes_part(h, first - 1), "a pot of Gerudo Valley's far side or the Wasteland's child's map is a check")
    check(valley_chest in seed.JUNK_ONLY and not seed.check_listed(valley_chest, first) and seed.check_listed(valley_chest, first - 1),
          "Gerudo Valley's child's chest of the far side is on the Tracker, or may hold more than junk")
    check(seed.check_listed(0x1234, first), "another chest is not on the Tracker")
    check(seed.ages_fixed(skull, "CA", first) == "A" and seed.ages_fixed(skull, "CA", first - 1) == "CA" and seed.ages_fixed(0x1234, "CA", first) == "CA",
          "the cave's Skulltula is not an adult's on the Tracker")
    src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("for h in gives if h not in gifts and check_listed(h, placement)]," in src and
          "ages_fixed(h, check_ages(maps[h]), placement), user_found.get(h)), tneeds.get(h) or fit_rule(tracked_soil(h, skull_need(h)))" in src,
          "the Tracker's list is written without asking")
    check("rel.split(\"/\")[1] not in POTS_LEFT_OUT) and pot_takes_part(h, placement):" in src and
          "rules_fixed(RULE_AS, pots, placement)" in src, "the pots are not asked whether they take part, or the fixed rules are not put in")
    print("PASS: checks an age can never get")


if __name__ == "__main__":
    main()

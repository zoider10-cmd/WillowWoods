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
    src = (ROOT / "tools" / "rando" / "rando_seed.py").read_text(encoding="utf-8")
    check("rel.split(\"/\")[1] not in POTS_LEFT_OUT) and pot_takes_part(h, placement):" in src and
          "rules_fixed(RULE_AS, pots, placement)" in src, "the pots are not asked whether they take part, or the fixed rules are not put in")
    print("PASS: checks an age can never get")


if __name__ == "__main__":
    main()

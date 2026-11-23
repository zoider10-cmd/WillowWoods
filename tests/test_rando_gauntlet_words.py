"""The owner's run 2026-11-23: a chest's Golden Gauntlets showed no model: the chest showed the pouch's spelling
(Armor_Adult_Gauntlet_Gold), the only one with "You got" words, and it has no model. Every seed copies those words to
the items' own spellings (COPY_WORDS, fixes 75), and the game's side no longer swaps the gauntlets (oot_show_as).
No game files.

python -I -B tests/test_rando_gauntlet_words.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def main():
    check(seed.COPY_WORDS == {"Item_Gauntlet_Goron": "Armor_Child_Gauntlet_Goron", "Item_Gauntlet_Silver": "Armor_Adult_Gauntlet_Silver",
                              "Item_Gauntlet_Gold": "Armor_Adult_Gauntlet_Gold"}, "not the three gauntlets' spellings")
    src = open(seed.__file__, encoding="utf-8").read()
    body = src[src.index("def first_bag_words(data, english):"):]
    body = body[:body.index("\n\n\n")]
    check("for item, spelling in COPY_WORDS.items():" in body and "msbt_add(data, item + suffix," in body, "the words are not copied")
    check(seed.FIXES_VERSION >= 75, "FIXES_VERSION not past 74")
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    table = host[host.index("static const char *const oot_show_as[][2] = {"):]
    table = table[:table.index("};")]
    check('"Item_Gauntlet_' not in table.replace("Item_Gauntlet_* spellings", ""), "the game's side still shows a gauntlet by the pouch's spelling")
    print("FAIL" if failed else "PASS: the gauntlets shown and named by their own spellings")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

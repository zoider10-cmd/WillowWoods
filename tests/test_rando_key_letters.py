"""The Tracker counts the keys (2026-11-24, after Small keys and Boss Keys: Anywhere): a rule's "K<n>" asks for all the
moving small keys of DUNGEON_FOLDERS[n], "B<n>" its Boss Key (tools/rando/rando_seed.py key_codes); a boss's Heart
Container and its ending name its Boss Key in the Tracker's rules only (tneeds, tracked); the Tracker tab holds a letter
when every check giving that key (mods/rando-seed/dungeon_items.txt) is collected (gpu/vk/vk_menu.cpp
tracker_key_held). Game-free: made-up rules, and the sources.

python -I -B tests/test_rando_key_letters.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    forest, fire = S.DUNGEON_FOLDERS.index("ForestTemple"), S.DUNGEON_FOLDERS.index("FireTemple")
    way = frozenset((S.BOW, S.SMALL_KEY + "@ForestTemple#1", S.SMALL_KEY + "@ForestTemple#2", S.boss_key_tag("FireTemple")))
    assert S.key_codes(way) == sorted(["K%d" % forest, "B%d" % fire]), S.key_codes(way)
    assert S.rule_text(way) == "BW,B%d,K%d" % (fire, forest), S.rule_text(way)
    assert S.key_codes(frozenset((S.BOW,))) == [] and S.rule_text(frozenset()) == "-"
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert "tneeds = {h: tracked(h, n, ending_of.get(h)) for h, n in needs.items()}" in main_src
    assert "tracked(h, needs.get(h) or heart_asks(h), bosses.get(h))" in main_src and "tneeds.get(h) or skull_need(h)" in main_src
    assert "check_ages(maps[h]), tneeds[h], named(\"Chest\"" in main_src, "the chests' lines do not take the Tracker's rules"
    menu = open(os.path.join(ROOT, "gpu", "vk", "vk_menu.cpp"), encoding="utf-8").read()
    start = menu.index("constexpr const char* kKeyDungeons[] = {")
    names = menu[start:menu.index("};", start)]
    assert [n for n in S.DUNGEON_FOLDERS if '"%s"' % n in names] == list(S.DUNGEON_FOLDERS) and names.count('"') == 2 * len(S.DUNGEON_FOLDERS), \
        "the Tracker's dungeons are not the seed tool's, in its order"
    assert "if (tracker_key_held(atoi(p + 1), p[0] == 'B', missing)) continue;" in menu
    assert '"dungeon_items.txt"' in menu and "tracker_key_owner[i] = (signed char)n, tracker_key_boss[i] = boss;" in menu
    print("PASS: the Tracker counts each dungeon's keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Boss Keys: Anywhere (rando_boss_keys, asked 2026-11-23; share/dungeon-items-plan.md stage 2): a dungeon's Boss Key
can be in any chest whose rule its own boss's rule covers (boss_key_fits), told its dungeon in DUNGEON_ITEMS_FILE as a
map is (host/hos_main.c oot_dungeon_item sets DungeonInfo.<folder>.IsGetBossKey). And Lake Hylia's chest that is there
only once the Water Temple is done asks for that temple's ending (AFTER_WATER, placement 29: the Water Temple's Boss Key
went there in a test seed). Game-free: made-up rules, and the sources.

python -I -B tests/test_rando_boss_keys.py
"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    cap = frozenset((S.BB, S.BOW))
    assert S.boss_key_fits(frozenset((S.BB,)), cap) and S.boss_key_fits(frozenset(), cap)
    assert not S.boss_key_fits(frozenset((S.HAM,)), cap), "a chest that asks for more than the boss took a Boss Key"
    assert S.boss_key_fits(S.either([frozenset((S.HAM,)), frozenset((S.BOW,))]), cap), "one way of a chest's rule within is enough"
    assert not S.boss_key_fits(None, cap) and S.boss_key_fits(None, None) and S.boss_key_fits(frozenset((S.HAM,)), None)
    assert S.boss_key_tag("ForestTemple") == "Item_Dungeon_BossKey@ForestTemple"
    assert S.AFTER_WATER == (0xec3f782c547551a1,) and S.AFTER_WATER_FROM == 29 and S.PLACEMENT >= 29
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert 'a.boss_keys = ini["rando_boss_keys"] == 1' in main_src and '(" boss keys 1" if a.boss_keys else "")' in main_src
    assert "s[1] = boss_tags[h] = boss_key_tag(s[0])" in main_src and "loose = loose | frozenset(boss_tags.values())" in main_src
    assert "unfit = frozenset(t for t, cap in caps.items() if not boss_key_fits(needs.get(h), cap))" in main_src
    assert main_src.index("owners[h] = gives[h].split(\"@\")[1]") < main_src.index("before = collections.Counter(spots[h][1] for h in gives)"), \
        "the tags are not taken off before the items are read"
    assert "if placement >= AFTER_WATER_FROM:" in main_src and 'water = frozenset(boss_need("WaterTemple"))' in main_src
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    assert '!strcmp(name, "Item_Dungeon_BossKey") ? "IsGetBossKey"' in host
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    assert 'X(BOSS_KEYS, "Boss Keys", "rando_boss_keys",' in header
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    assert '"rando_boss_keys", "Boss Keys", new[] { "With the keys", "Anywhere" }' in launcher
    print("PASS: Boss Keys anywhere, each where its boss's rule reaches")
    return 0


if __name__ == "__main__":
    sys.exit(main())

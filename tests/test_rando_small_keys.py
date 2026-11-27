"""Small keys: Anywhere (Dungeon keys' third choice, rando_keys 2; asked 2026-11-23; share/dungeon-items-plan.md stage 3):
each dungeon's small keys in chests that take part are items of the shuffle of their own (key_tags), a dungeon check not
reached without keys (tools/rando/dungeon_keyless.py, KEYLESS_FILE) asks for all of them, a dungeon's keys go only
where its ending's rule and its own keys reach, and each is told its dungeon in DUNGEON_ITEMS_FILE (the game's side
raises DungeonInfo.<folder>.SmallKeyNum, host/hos_main.c oot_dungeon_item). Game-free: made-up spots, the table, the
sources.

python -I -B tests/test_rando_small_keys.py
"""
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    key, box = S.SMALL_KEY, "Obj_TBox_A_01"
    spots = {5: ["ForestTemple", key, True, None, box], 3: ["ForestTemple", key, True, None, box],
             9: ["ForestTemple", key, True, "an event's chest", box],   # (stays: the game's key, not the shuffle's)
             7: ["KokiriForest", key, False, None, box],                # (not a dungeon's: the treasure game's, as it were)
             8: ["FireTemple", key, True, None, "Obj_Pot"],             # (not a chest)
             2: ["FireTemple", key, True, None, box], 4: ["FireTemple", "TBox_Rupee_Red", True, None, box]}
    tags = S.key_tags(spots)
    assert tags == {2: key + "@FireTemple#1", 3: key + "@ForestTemple#1", 5: key + "@ForestTemple#2"}, tags
    assert S.key_tags(spots, which=1) == {}, "with Chests: Overworld a dungeon's chests stay, and their keys"
    table = json.load(open(os.path.join(ROOT, "tools", "rando", S.KEYLESS_FILE), encoding="utf-8"))
    assert len(table["keyless"]) > 100 and len(table["keyed"]) > 80 and not set(table["keyless"]) & set(table["keyed"])
    assert S.keyless_actors() == frozenset(table["keyless"])
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert "small_tags = key_tags(spots, which) if keys_mode == 2 else {}" in main_src
    assert "if area in key_sets and h not in free:" in main_src, "a check behind a locked door does not ask for its dungeon's keys"
    assert "caps[t] = frozenset(boss_need(d)) | key_sets[d] if d in BOSS_HEARTS else None" in main_src
    assert "PROGRESSION = PROGRESSION | frozenset(small_tags.values())" in main_src
    assert 'rest = " seed %d chests %d keys %d major %d logic %d%s%s\\n" % (seed, which, keys_mode,' in main_src, "Anywhere is not on the stamp"
    keys_at = main_src.index("    if keys_mode == 2:   # (Small keys: Anywhere: the Boss Keys and the maps")
    assert main_src.index('a.boss_keys = ini["rando_boss_keys"] == 1') < keys_at, "the Boss Keys' own setting is read after"
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    assert '!strcmp(name, "Item_Dungeon_SmallKey") ? "SmallKeyNum"' in host and "ok = ok && oot_gamedata_int(c, oot_flag_hash(flag), &n, 1);" in host
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    assert '{ "rando_keys", 2 }, { "rando_songs", 3 } };' not in launcher, "Anywhere is still held off in the launcher"
    print("PASS: small keys anywhere, counted for their own dungeon")
    return 0


if __name__ == "__main__":
    sys.exit(main())

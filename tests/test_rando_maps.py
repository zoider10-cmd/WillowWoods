"""Maps and compasses (rando_maps, asked 2026-11-23; share/dungeon-items-plan.md stage 1): With the keys (as before),
Anywhere (any chest; the seed writes each one's dungeon in DUNGEON_ITEMS_FILE and the game's side sets that dungeon's
save flag at a chest's add in another place, host/hos_main.c oot_dungeon_item), From the start (every dungeon's
IsGetMap/IsGetCompass start set, their chests hold rupees). Seen without a window 2026-11-24: Kokiri Forest's chest gave
the Shadow Temple's compass, "DungeonInfo.ShadowTemple.IsGetCompass set". Game-free: made-up spots, and the sources.

python -I -B tests/test_rando_maps.py
"""
import os
import random
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as S  # noqa: E402


def main():
    spots = {1: ["ForestTemple", S.MAP], 2: ["FireTemple", S.MAP], 3: ["ForestTemple", S.COMPASS], 4: ["KokiriForest", "TBox_Rupee_Red"],
             5: ["HyruleField", "TBox_Rupee_Blue"]}
    gives = {1: "TBox_Rupee_Red", 2: S.COMPASS, 3: S.MAP, 4: S.MAP, 5: "TBox_Rupee_Blue"}
    owners = S.dungeon_owners(random.Random(1), spots, gives, S.MAPS_LOOSE)
    assert set(owners) == {2, 3, 4}, owners
    assert sorted(owners[h] for h in (3, 4)) == ["FireTemple", "ForestTemple"] and owners[2] == "ForestTemple", owners
    try:
        S.dungeon_owners(random.Random(1), spots, {**gives, 5: S.MAP}, S.MAPS_LOOSE)
        raise AssertionError("a map more than there were was not refused")
    except ValueError:
        pass
    assert len(S.DUNGEON_FOLDERS) == 12 and len(S.MAPS_START) == 24 and all(v is True for v in S.MAPS_START.values())
    assert set(S.MAPS_START_JUNK) == set(S.MAPS_LOOSE) and all(i.startswith("TBox_Rupee_") for i in S.MAPS_START_JUNK.values())
    src = open(S.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    assert '"rando_maps": 0' in src and 'a.maps = ini["rando_maps"] if ini["rando_maps"] in (0, 1, 2) else 0' in main_src
    assert '(" maps %d" % a.maps if a.maps else "")' in main_src, "the setting is not on the stamp (it moves items)"
    assert "**(MAPS_START if a.maps == 2 else {})" in main_src and "spots[h][1] = MAPS_START_JUNK[spots[h][1]]" in main_src
    assert "loose = MAPS_LOOSE if a.maps == 1 else frozenset()" in main_src and "holds[h] = frozenset(holds.get(h, every)) - loose" in main_src
    assert main_src.index("DUNGEON_ITEMS_FILE") < main_src.index("with open(os.path.join(mod, CHECKS)")
    host = open(os.path.join(ROOT, "host", "hos_main.c"), encoding="utf-8").read()
    assert 'snprintf(flag, sizeof flag, "DungeonInfo.%s.%s", owner, field);' in host and '"mods/rando-seed/dungeon_items.txt"' in host
    assert "if (oot_dungeon_item(c, name)) return 1;" in host and "if (!owner[0] || oot_banc_in_folder(oot_link_map, owner)) return 0;" in host
    header = open(os.path.join(ROOT, "gpu", "vk", "oot_rando.h"), encoding="utf-8").read()
    assert 'X(MAPS, "Maps and compasses", "rando_maps",' in header and '"With the keys", "Anywhere", "From the start")' in header
    launcher = open(os.path.join(ROOT, "launcher", "Launcher.cs"), encoding="utf-8").read()
    assert '"rando_maps", "Maps and compasses", new[] { "With the keys", "Anywhere", "From the start" }' in launcher
    print("PASS: maps and compasses with the keys, anywhere or from the start")
    return 0


if __name__ == "__main__":
    sys.exit(main())

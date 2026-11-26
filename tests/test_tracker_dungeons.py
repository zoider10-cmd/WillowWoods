"""The Tracker's Dungeon items row (asked 2026-11-26; gpu/vk/vk_menu.cpp dungeon_panel, host/hos_main.c): no game data.

Each dungeon's small keys in hand of its total, and whether its map, compass and Boss Key are found. Checked:
- the game side reads each dungeon's DungeonInfo.<dungeon>.SmallKeyNum, IsGetMap, IsGetCompass and IsGetBossKey with the
  inventory's counts and sends them (OOT_DUNGEON_BASE + d: the keys | 256 map | 512 compass | 1024 Boss Key, -1 no save);
- the ids are their own, after the Health bars' and before the Damage numbers';
- the dungeons are in the same order on both sides, and the seed tool's (tools/rando/rando_seed.py DUNGEON_FOLDERS);
- the menu keeps the values, has the row before the areas, and draws its panel (and words in a narrow window).

    python -I -B tests/test_tracker_dungeons.py
"""
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402

spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    header = (ROOT / "gpu" / "vk" / "oot_cheat_items.h").read_text(encoding="utf-8")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    base = int(re.search(r"#define OOT_DUNGEON_BASE (\d+)", header).group(1))
    count = int(re.search(r"#define OOT_DUNGEON_COUNT (\d+)", header).group(1))
    others = [int(n) for n in re.findall(r"#define OOT_\w+ (\d+)", header) if 4000 <= int(n) < 4096 and int(n) not in (base, count)]
    health_kind = int(re.search(r"#define OOT_HEALTH_KIND (\d+)", header).group(1))
    slots = int(re.search(r"#define OOT_HEALTH_SLOTS (\d+)", header).group(1))
    check(base >= health_kind + slots and not any(base <= n < base + count for n in others), "the dungeons' ids are another's")
    names = re.search(r'#define OOT_DUNGEONS ((?:"\w+",?\s*\\?\s*)+)', header).group(1)
    check(re.findall(r'"(\w+)"', names) == list(seed.DUNGEON_FOLDERS) and count == len(seed.DUNGEON_FOLDERS),
          "the dungeons are not the seed tool's, in its order")
    keys = re.search(r"const char\* kKeyDungeons\[\] = \{([^}]*)\}", menu).group(1)
    check(re.findall(r'"(\w+)"', keys) == list(seed.DUNGEON_FOLDERS), "the menu's dungeons are in another order")
    check('snprintf(flag, sizeof flag, "DungeonInfo.%s.SmallKeyNum", dungeons[d]);' in host and
          '{"IsGetMap", "IsGetCompass", "IsGetBossKey"}' in host and "if (oot_gamedata_bool(c, oot_flag_hash(flag), &got) && got) value |= 256 << k;" in host
          and "rx_option_set(OOT_DUNGEON_BASE + d, value);" in host, "the game side does not send each dungeon's keys and items")
    check("if (dungeon_state[id - OOT_DUNGEON_BASE].exchange(value, std::memory_order_relaxed) != value" in menu,
          "the menu does not keep the dungeons' values")
    check("constexpr int kTrackerDungeonRow = 4;" in menu and 'snprintf(tracker_name[kTrackerDungeonRow], sizeof tracker_name[0], "Dungeon items");' in menu
          and "if (row == kTrackerDungeonRow && tracker_check_count) return dungeon_says();" in menu, "the Tracker has no Dungeon items row")
    check("const float top = hh + 18 * s, end = dungeon_panel(c, hx0, hx1, top, bar_top - 12 * s);" in menu and
          "dungeon_row ? (narrow ? dungeon_help.c_str() : kTrackerDungeonHelp) :" in menu, "the row's panel or its words are not drawn")
    panel = block(menu, "float dungeon_panel(ui::Ctx& c, float x0, float x1, float y0, float y_max) {")
    check('snprintf(keys, sizeof keys, "%d of %d", state & 255, kDungeonKeys[d]);' in panel and "(state & (256 << k))" in panel,
          "the panel does not show the keys in hand of the total, or the three items")
    for table in ("kDungeonKeys", "kDungeonMaps", "kDungeonBossKey", "kDungeonTitles"):
        row = re.search(table + r"\[OOT_DUNGEON_COUNT\] = \{([^}]*)\}", menu)
        check(row and len([v for v in row.group(1).split(",") if v.strip()]) == count, "%s is not one a dungeon" % table)
    print("PASS: the Tracker's Dungeon items row")


if __name__ == "__main__":
    main()

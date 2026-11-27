"""The Tracker's Dungeon items row (asked 2026-11-26; gpu/vk/vk_menu.cpp dungeon_panel, host/hos_main.c): no game data.

Each dungeon's small keys in hand of its total, and whether its map, compass and Boss Key are found. Checked:
- the game side reads each dungeon's DungeonInfo.<dungeon>.SmallKeyNum, IsGetMap, IsGetCompass and IsGetBossKey with the
  inventory's counts and sends them (OOT_DUNGEON_BASE + d: the keys | 256 map | 512 compass | 1024 Boss Key, -1 no save);
- the ids are their own, after the Health bars' and before the Damage numbers';
- the dungeons are in the same order on both sides, and the seed tool's (tools/rando/rando_seed.py DUNGEON_FOLDERS);
- the menu keeps the values, has the row before the areas, and draws its panel (and words in a narrow window);
- the row counts only what a dungeon has (bug 159: Maps and compasses: From the start sets the map's and the compass's
  flag of the Training Ground and Ganon's Castle too, which have neither, and the row said "27 of 26 items"): the row's
  words are compiled and run on the owner's save's flags, and the panel draws a dash for an item a dungeon has not.

    python -I -B tests/test_tracker_dungeons.py [--cxx g++]
"""
import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from srccut import block   # noqa: E402

spec = importlib.util.spec_from_file_location("rando_seed", ROOT / "tools" / "rando" / "rando_seed.py")
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


RUN_ALL_ARGS = ["--cxx", "{cxx}"]
FIXTURE = r"""
#include <atomic>
#include <cstdio>
#include <string>
#define OOT_DUNGEON_COUNT 12
std::atomic<int> dungeon_state[OOT_DUNGEON_COUNT];
// TABLES
// SAYS
int main() {
    // (the owner's save of 2026-11-26, Maps and compasses: From the start: every dungeon's map and compass flag set, the
    //  Forest, Water and Spirit Temples' Boss Keys, a key of the Fire and Water Temples and the Training Ground, two of the
    //  Spirit Temple's)
    const int keys[OOT_DUNGEON_COUNT] = {0, 0, 0, 0, 0, 1, 0, 1, 0, 2, 1, 0};
    const bool boss[OOT_DUNGEON_COUNT] = {false, false, false, false, true, false, false, true, false, true, false, false};
    for (int d = 0; d < OOT_DUNGEON_COUNT; d++) dungeon_state[d] = keys[d] | 256 | 512 | (boss[d] ? 1024 : 0);
    puts(dungeon_says().c_str());
    for (int d = 0; d < OOT_DUNGEON_COUNT; d++) dungeon_state[d] = 256 | 512 | 1024;   // (every flag there is)
    puts(dungeon_says().c_str());
    for (int d = 0; d < OOT_DUNGEON_COUNT; d++) dungeon_state[d] = -1;
    puts(dungeon_says().c_str());
    return 0;
}
"""


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
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
    check("constexpr int kTrackerDungeonRow = 4;" in menu and '"Gossip Stones", "Dungeon items", "In logic now", "Doors and bosses"};' in menu
          and "if (row == kTrackerDungeonRow && tracker_check_count) return dungeon_says();" in menu, "the Tracker has no Dungeon items row")
    check("const float top = hh + 18 * s, end = dungeon_panel(c, hx0, hx1, top, bar_top - 12 * s);" in menu and
          "dungeon_row ? (narrow ? dungeon_help.c_str() : kTrackerDungeonHelp) :" in menu, "the row's panel or its words are not drawn")
    panel = block(menu, "float dungeon_panel(ui::Ctx& c, float x0, float x1, float y0, float y_max) {")
    check('snprintf(keys, sizeof keys, "%d of %d", state & 255, kDungeonKeys[d]);' in panel and "(state & (256 << k))" in panel,
          "the panel does not show the keys in hand of the total, or the three items")
    for table in ("kDungeonKeys", "kDungeonMaps", "kDungeonBossKey", "kDungeonTitles"):
        row = re.search(table + r"\[OOT_DUNGEON_COUNT\] = \{([^}]*)\}", menu)
        check(row and len([v for v in row.group(1).split(",") if v.strip()]) == count, "%s is not one a dungeon" % table)
    # ---- bug 159: only what a dungeon has is counted, and drawn ----
    check(count == 12, "the fixture's save is of 12 dungeons")
    tables = "\n".join(m.group(0) for m in re.finditer(
        r"^constexpr (?:int|bool) (?:kDungeon\w+\[OOT_DUNGEON_COUNT\]|dungeon_has\()[^\n]*", menu, re.M))
    fixture = FIXTURE.replace("// TABLES", tables).replace("// SAYS", block(menu, "std::string dungeon_says() {"))
    with tempfile.TemporaryDirectory(prefix="tracker-dungeons-") as tmp:
        cpp, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-unused-const-variable", str(cpp), "-o", str(exe)], check=True)
        # (llvm-mingw's programs want its libc++.dll, which is beside the compiler and not on PATH)
        beside = os.path.dirname(shutil.which(a.cxx) or "")
        env = dict(os.environ, PATH=beside + os.pathsep + os.environ.get("PATH", ""))
        said = subprocess.run([str(exe)], check=True, capture_output=True, text=True, env=env).stdout.splitlines()
    check(said == ["5 keys in hand, 23 of 26 items", "0 keys in hand, 26 of 26 items", "Load a save to see them"],
          "the row's words count an item a dungeon has not: %r" % said)
    check("mark(col[k + 1], my, dungeon_has(d, k) ? (got ? 1 : 0) : -1);" in panel,
          "the panel does not draw a dash for an item the dungeon has not, whatever its flag says")
    print("PASS: the Tracker's Dungeon items row")


if __name__ == "__main__":
    main()

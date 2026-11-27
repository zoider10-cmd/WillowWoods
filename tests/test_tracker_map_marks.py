"""The Tracker's maps: what each mark is and what is shown (asked 2026-11-26, share/todo.md's "Tracker map: ways to
improve it", the four small ones; gpu/vk/vk_menu.cpp). No game data.

Measured on the owner's seed: the Market's 87 dots, 82 touching another; Kakariko's 42 adult and 16 child checks drawn
together; the Haunted Wasteland's 8 pots in 9 x 2 m. So:
- the area map shows the checks of Link's age, as the minimap does (tracker_of_age), and the one stepped to whatever its age;
- stepped to a check in a crowd, the view closes in on it (tracker_zoom_half), the whole area small in the corner;
- a mark's shape says what the check is (tracker_kind_mark: a chest, a Gold Skulltula, a pot, anything else), with a legend;
- the help line says where the check is from Link (tracker_from_link), and a check well above or below him has an up or a
  down mark on both maps (Link's height: OOT_LINK_Y from the game side).
The four functions are compiled and run; the rest is read from the sources.

    python -I -B tests/test_tracker_map_marks.py [--cxx g++]
"""
import argparse
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

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
FIXTURE = r"""
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
// CONSTANTS
// FUNCTIONS
int failed = 0;
void check(bool ok, const char* what) { if (!ok) printf("FAIL: %s\n", what), failed = 1; }
int main() {
    // ---- a mark by the check's name (the names of tools/rando/rando_seed.py's checks.txt) ----
    check(tracker_kind_mark("Chest (red rupee), room 5") == 1 && tracker_kind_mark("Big chest (Bomb Bag), room 13") == 1, "a chest's mark");
    check(tracker_kind_mark("Gold Skulltula") == 2 && tracker_kind_mark("Gold Skulltula, night, Lon Lon Ranch") == 2, "a Gold Skulltula's mark");
    check(tracker_kind_mark("Pot #3") == 3 && tracker_kind_mark("Pot #1 (adult)") == 3, "a pot's mark");
    check(tracker_kind_mark("Impa's lesson: Zelda's Lullaby") == 0 && tracker_kind_mark("Piece of Heart") == 0 &&
          tracker_kind_mark("The Great Fairy of Hyrule Castle") == 0, "anything else's mark");
    // ---- the checks of Link's age ----
    check(tracker_of_age("C", 0) && !tracker_of_age("A", 0) && tracker_of_age("CA", 0), "the child's checks");
    check(tracker_of_age("A", 1) && !tracker_of_age("C", 1) && tracker_of_age("CA", 1), "the adult's checks");
    check(tracker_of_age("C", -1) && tracker_of_age("A", -1), "every check when his age is not known");
    // ---- where a check is from Link: x east, z south (north is up on the maps), y up ----
    check(tracker_from_link(0, 0, -42) == "42 m north", tracker_from_link(0, 0, -42).c_str());
    check(tracker_from_link(30, 0, -30) == "42 m north-east", tracker_from_link(30, 0, -30).c_str());
    check(tracker_from_link(10, 0, 0) == "10 m east", tracker_from_link(10, 0, 0).c_str());
    check(tracker_from_link(0, 0, 7) == "7 m south", tracker_from_link(0, 0, 7).c_str());
    check(tracker_from_link(-20, 0, 20) == "28 m south-west", tracker_from_link(-20, 0, 20).c_str());
    check(tracker_from_link(-9, 0, 0) == "9 m west", tracker_from_link(-9, 0, 0).c_str());
    check(tracker_from_link(-5, 0, -5) == "7 m north-west", tracker_from_link(-5, 0, -5).c_str());
    check(tracker_from_link(0, 8, -42) == "42 m north, above" && tracker_from_link(0, -8, -42) == "42 m north, below", "above and below");
    check(tracker_from_link(0, 2, -42) == "42 m north", "a step up is the same level");
    check(tracker_from_link(1, 0, 1) == "right here" && tracker_from_link(1, 9, 0) == "right here, above", "within 2 m");
    // ---- the view around the check stepped to ----
    {   // (the Market's guard house: 21 other pots within 8 m, the rest of the area up to 150 m away, half of it 96 m)
        std::vector<float> away;
        for (int i = 0; i < 21; i++) away.push_back(1.0f + i * 0.35f);
        for (int i = 0; i < 65; i++) away.push_back(40.0f + i * 1.7f);
        const float half = tracker_zoom_half(away, 96);
        check(half >= 8 && half < 12, "a crowd's view is not a few metres around it");
    }
    {   // (a check on its own: its eighth neighbour is most of the area away: the whole area)
        std::vector<float> away = {60, 70, 75, 80, 82, 90, 95, 99, 120};
        check(tracker_zoom_half(away, 100) == 100, "a lone check's view is not the whole area");
    }
    check(tracker_zoom_half({}, 50) == 50, "an area of one check is not shown whole");
    check(tracker_zoom_half({0.5f, 0.7f}, 50) == 8, "the view is narrower than its least");
    check(tracker_zoom_half({20, 30}, 100) == 37.5f, "fewer neighbours than asked for: not out to the farthest");
    if (!failed) puts("ok");
    return failed;
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
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    header = (ROOT / "gpu" / "vk" / "oot_cheat_items.h").read_text(encoding="utf-8")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    constants = "\n".join(m.group(0) for m in re.finditer(r"^constexpr (?:int|float) kMap(?:Level|ZoomNear|ZoomMin) = [^\n]*", menu, re.M))
    functions = "\n".join(block(menu, marker) for marker in (
        "int tracker_kind_mark(const char* kind) {", "bool tracker_of_age(const char* ages, int age) {",
        "std::string tracker_from_link(float dx, float dy, float dz) {", "float tracker_zoom_half(std::vector<float> away, float half_all) {"))
    fixture = FIXTURE.replace("// CONSTANTS", constants).replace("// FUNCTIONS", functions)
    with tempfile.TemporaryDirectory(prefix="tracker-marks-") as tmp:
        cpp, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture.exe"
        cpp.write_text(fixture, encoding="utf-8")
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(exe)], check=True)
        # (llvm-mingw's programs want its libc++.dll, which is beside the compiler and not on PATH)
        beside = os.path.dirname(shutil.which(a.cxx) or "")
        env = dict(os.environ, PATH=beside + os.pathsep + os.environ.get("PATH", ""))
        ran = subprocess.run([str(exe)], capture_output=True, text=True, env=env)
    check(ran.returncode == 0 and ran.stdout.strip() == "ok", "the maps' functions:\n" + ran.stdout + ran.stderr)

    # ---- the area map uses them ----
    area = block(menu, "void tracker_area_map(ui::Ctx& c, float x0, float x1, float y0, float y1, int row) {")
    check("return !strcmp(k.area, tracker_name[row]) && (&k == picked || tracker_of_age(k.ages, age));" in area,
          "the area map does not show the checks of Link's age, and the one stepped to")
    check("const float half = picked ? tracker_zoom_half(away, half_all) : half_all;" in area and "if (zoomed) {" in area,
          "the area map does not close in on the check stepped to, or has no picture of the whole area then")
    check("tracker_mark(c.d, at, tracker_kind_mark(k.kind), state, up > kMapLevel ? 1 : up < -kMapLevel ? -1 : 0, s);" in area,
          "a check's mark is not its kind's shape, or has no up or down mark")
    check('{{1, "chest"}, {2, "Skulltula"}, {3, "pot"}, {0, "other"}}' in area, "the area map does not say what the shapes are")
    # ---- the help line, and the minimap ----
    hint = block(menu, "std::string tracker_hint(int row) {")
    check('"From Link: " + tracker_from_link(k->pos[0] - lx / 100.0f, ly != INT_MIN ? k->pos[1] - ly / 100.0f : 0, k->pos[2] - lz / 100.0f)' in hint
          and "if (k && here && !strcmp(here, k->area) && lx != INT_MIN && lz != INT_MIN)" in hint,
          "the help line does not say where the check is from Link, when he is in its area")
    mini = block(menu, "void draw_minimap_checks(ui::Ctx& c) {")
    check("if (!tracker_of_age(k.ages, age)) continue;" in mini and "if (const int lift = up > kMapLevel ? 1 : up < -kMapLevel ? -1 : 0) {" in mini,
          "the minimap does not keep to Link's age, or has no up and down marks")
    # ---- Link's height reaches the menu ----
    ids = {n: int(v) for n, v in re.findall(r"#define (OOT_LINK_\w+) (\d+)", header)}
    others = [int(v) for n, v in re.findall(r"#define (OOT_\w+) (\d+)", header) if not n.startswith("OOT_LINK_")]
    check(ids.get("OOT_LINK_Y") == ids["OOT_LINK_X"] + 3 and ids["OOT_LINK_Y"] not in others, "OOT_LINK_Y is not the fourth of Link's ids, or is another's")
    check("std::atomic<int> link_place[4] = {INT_MIN, INT_MIN, 0, INT_MIN};" in menu and
          "if (id == OOT_LINK_X || id == OOT_LINK_Z || id == OOT_LINK_YAW || id == OOT_LINK_Y) {" in menu and
          "link_place[id - OOT_LINK_X].store(value, std::memory_order_relaxed);" in menu, "the menu does not keep Link's height")
    check("rx_option_set(OOT_LINK_Y, (int)lrintf(oot_link_place[1] * 100));" in host, "the game side does not send Link's height")
    print("PASS: the Tracker's maps' marks")


if __name__ == "__main__":
    main()

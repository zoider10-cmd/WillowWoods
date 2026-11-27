"""The Tracker tab's junk marks (gpu/vk/vk_menu.cpp tracker_junk): a check the player marks as not worth going for.

The real tracker_check_shown, tracker_row_checks, tracker_row_check, tracker_junk_flip, tracker_says and tracker_press are
cut out of vk_menu.cpp with the junk record's own code (tracker_junk_read, tracker_junk_write) and compiled over stub
checks and a stub game folder (the fixture's own). Checked:

- a check marked junk (the junk press on an area's row stepped to it) leaves the area's "checks left" and "in logic"
  counts, and the whole game's "collected" count does not take it for collected; the row stepped to it says so;
- the Show row's Left lists hide it, and a row stepped to a check they hide now moves on rather than past its checks;
- pressed again, it counts again;
- rando/junk.txt is "seed <stamp>" then the junk checks' places, one a line, as rando/collected.txt is; it reads back
  the same marks for that seed and none for another seed, and the first row's Forget (confirmed twice) empties it;
- the press is J on the keyboard (its place in menu_tick's keys is kTrackerJunkPress) and the Switch's Y as bound on a
  controller (menu_keys::extra), and the prompts show it.

    python -I -B tests/test_tracker_junk.py [--cxx g++]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # (tests/srccut.py: python -I leaves this folder off the path)
from srccut import block, between   # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''#include "gpu/vk/vk_menu_keys.h"
#include <algorithm>
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <string>
#include <system_error>
#include <vector>
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); std::exit(1); } } while (0)
using ULONGLONG = unsigned long long;
// CONSTANTS
// TRACKER_CHECK
;
char tracker_name[kTrackerRows][48];
char tracker_value[kTrackerRows][72];
TrackerCheck tracker_checks[kTrackerChecks];
int tracker_check_count = 0;
std::atomic<signed char> tracker_done[kTrackerChecks];
int tracker_pick[kTrackerRows];
ULONGLONG tracker_forget_asked = 0, tracker_home_asked = 0;
std::atomic<int> cheat_action{0};
std::atomic<bool> open_now{true};
static int logic[kTrackerChecks];   // (each check's tracker_in_logic: 1 in logic, 0 not)
int tracker_in_logic(const TrackerCheck& k, std::string* = nullptr) { return logic[&k - tracker_checks]; }
static std::string folder;   // (the game folder: the fixture's own, with its separator)
std::string game_folder_path() { return folder; }
static ULONGLONG now_ms = 100000;
ULONGLONG GetTickCount64() { return now_ms; }
bool cheats_on() { return false; }
void logf(const char*, ...) {}
const char* tracker_here_area() { return nullptr; }
// (the Gossip Stones' row and the hints' marks: no hints here; what the story holds back: nothing)
std::atomic<int> tracker_on{1};
std::vector<std::string> tracker_stone_lines;
int tracker_stone_total = 0;
void tracker_stones_load(const std::string&, bool) {}
int tracker_area_hint(const char*) { return 0; }
std::string tracker_after(const TrackerCheck&) { return std::string(); }
std::string dungeon_says() { return std::string(); }   // (the Dungeon items row's words: not this check's)
std::string doors_says() { return std::string(); }   // (nor the Doors and bosses row's)
static int window_opens = 0;   // (the Tracker window row: how often the window was asked for)
bool tracker_window_open() { return ++window_opens == 1; }
ULONGLONG tracker_window_asked = 0;
bool tracker_window_started = false;
// (the groups of the areas' rows: tracker_load lays them out, this check by hand)
char tracker_kind[kTrackerRows];
bool tracker_folded[kTrackerRows];
bool tracker_done_open = false;
int tracker_count = 0;
// JUNK
// SHOW
std::vector<int> tracker_near;
// FUNCTIONS
static std::string file_text(const std::string& path) {
    std::string text;
    if (FILE* f = std::fopen(path.c_str(), "r")) {   // (text, as it is written: a line's end is \n on every OS)
        char buf[256];
        size_t n;
        while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
        std::fclose(f);
    }
    return text;
}
static void put(int i, const char* area, const char* kind, int done, int in) {
    std::snprintf(tracker_checks[i].area, sizeof tracker_checks[i].area, "%s", area);
    std::snprintf(tracker_checks[i].kind, sizeof tracker_checks[i].kind, "%s", kind);
    std::snprintf(tracker_checks[i].ages, sizeof tracker_checks[i].ages, "CA");
    tracker_done[i].store((signed char)done);
    logic[i] = in;
}
static bool press_on(int row, int which) {
    bool press[kTrackerJunkPress + 1] = {}, changed = false;
    press[which] = true;
    tracker_press(row, press, changed);
    return changed;
}
int main(int argc, char** argv) {
    CHECK(argc == 2);
    folder = std::string(argv[1]) + "/";
    const char* names[] = {"The whole game", "Show", "Return home", "Gossip Stones", "Dungeon items", "In logic now", "Doors and bosses",
                           "Tracker window", "Market", "Kokiri Forest"};
    static_assert(kTrackerStoneRow == 3 && kTrackerDungeonRow == 4 && kTrackerNowRow == 5 && kTrackerDoorRow == 6 && kTrackerWindowRow == 7 && kTrackerFirstArea == 8,
                  "the rows before the areas are not these");
    for (int r = 0; r < 10; r++) std::snprintf(tracker_name[r], sizeof tracker_name[r], "%s", names[r]);
    const int market = kTrackerFirstArea;
    put(0, "Market", "Chest A", 0, 1);
    put(1, "Market", "Chest B", 0, 1);
    put(2, "Market", "Chest C", 1, 0);   // (collected)
    put(3, "Kokiri Forest", "Chest D", 0, 0);
    tracker_check_count = 4;
    tracker_junk_stamp = "seed-one";
    CHECK(tracker_says(market) == "2 checks left, 2 in logic");
    CHECK(tracker_says(0) == "1 of 4 collected, 2 in logic now");

    // (the junk press on the row stepped to its second check: it is junk, and the record is written)
    tracker_pick[market] = 2;
    CHECK(press_on(market, kTrackerJunkPress) && tracker_junk[1] && !tracker_junk[0]);
    CHECK(tracker_says(market) == "2 of 3: Chest B: junk");
    tracker_pick[market] = 0;
    CHECK(tracker_says(market) == "1 check left, 1 in logic, 1 junk");
    CHECK(tracker_says(0) == "1 of 4 collected, 1 junk, 1 in logic now");
    const std::string path = tracker_junk_path();
    CHECK(file_text(path) == "seed seed-one\n1\n");

    // (the Left lists hide it; showing all, it is there)
    tracker_show = kTrackerShowLeft;
    CHECK(!tracker_check_shown(1) && tracker_check_shown(0) && tracker_row_checks(market) == 1);
    tracker_show = kTrackerShowReachable;
    CHECK(!tracker_check_shown(1) && tracker_row_checks(market) == 1);
    tracker_show = kTrackerShowAll;
    CHECK(tracker_check_shown(1) && tracker_row_checks(market) == 3);

    // (the record read back: this seed's marks; another seed's record is not taken)
    tracker_junk[1] = false;
    tracker_junk_read(path, "seed-one", tracker_check_count);
    CHECK(tracker_junk[1] && !tracker_junk[0] && !tracker_junk[2] && !tracker_junk[3]);
    tracker_junk_read(path, "seed-two", tracker_check_count);
    CHECK(!tracker_junk[1]);
    tracker_junk_read(path, "seed-one", 1);   // (a place past the seed's checks is not taken)
    CHECK(!tracker_junk[1]);
    tracker_junk_read(path, "seed-one", tracker_check_count);
    CHECK(tracker_junk[1]);

    // (pressed again: it counts again, and the record says none)
    tracker_pick[market] = 2;
    CHECK(press_on(market, kTrackerJunkPress) && !tracker_junk[1]);
    CHECK(file_text(path) == "seed seed-one\n");
    tracker_pick[market] = 0;
    CHECK(tracker_says(market) == "2 checks left, 2 in logic");

    // (junk under a Left list: the row moves on to the next it shows, never past its checks)
    tracker_show = kTrackerShowLeft;
    tracker_pick[market] = 2;   // (Chest B: the second it shows, C being collected)
    CHECK(press_on(market, kTrackerJunkPress) && tracker_junk[1] && tracker_pick[market] == 1);
    CHECK(tracker_row_check(market, tracker_pick[market]) == &tracker_checks[0]);
    CHECK(press_on(market, kTrackerJunkPress) && tracker_junk[0] && tracker_pick[market] == 0);
    CHECK(!press_on(market, kTrackerJunkPress));   // (the row's own words: nothing to mark)
    tracker_show = kTrackerShowAll;
    CHECK(tracker_says(market) == "All collected, 2 junk");
    CHECK(file_text(path) == "seed seed-one\n0\n1\n");

    // (the first row's Forget, confirmed twice: the junk marks go with the record of what is collected)
    CHECK(press_on(0, 7) && tracker_junk[0] && cheat_action.load() == 0);
    now_ms += 1000;
    CHECK(press_on(0, 7) && !tracker_junk[0] && !tracker_junk[1] && cheat_action.load() == kTrackerForgetAction);
    CHECK(file_text(path) == "seed seed-one\n");

    // (the controller's button: Y where it is bound, if neither confirm nor back is on it; else the paste button)
    using namespace mkwvk::menu_keys;
    CHECK(extra(kWest, kEast, kSouth) == kWest && extra(kNorth, kSouth, kEast) == kNorth);
    CHECK(extra(-1, kEast, kSouth) == paste(kEast, kSouth) && extra(kEast, kEast, kSouth) == paste(kEast, kSouth));
    CHECK(extra(9, kSouth, kEast) == paste(kSouth, kEast));

    // (asked 2026-11-27, the In logic now row: the whole game's checks left and in logic, in tracker_near's order, each
    //  said with its area; a junk one is not among them)
    put(3, "Kokiri Forest", "Chest D", 0, 1);
    tracker_near = {3, 2, 1, 0};
    CHECK(tracker_row_checks(kTrackerNowRow) == 3 && tracker_row_check(kTrackerNowRow, 1) == &tracker_checks[3]);
    CHECK(tracker_row_check(kTrackerNowRow, 2) == &tracker_checks[1] && !tracker_row_check(kTrackerNowRow, 4));
    CHECK(tracker_says(kTrackerNowRow) == "3 checks, nearest first");
    tracker_pick[kTrackerNowRow] = 1;
    CHECK(tracker_says(kTrackerNowRow) == "1 of 3: Kokiri Forest: Chest D: in logic");
    CHECK(press_on(kTrackerNowRow, kTrackerJunkPress) && tracker_junk[3] && tracker_row_checks(kTrackerNowRow) == 2);
    CHECK(press_on(kTrackerNowRow, 4) && tracker_pick[kTrackerNowRow] == 2);   // (Right: the next)
    tracker_pick[kTrackerNowRow] = 0;
    put(0, "Market", "Chest A", 0, 0), put(1, "Market", "Chest B", 0, 0);
    CHECK(tracker_says(kTrackerNowRow) == "Nothing in logic right now");

    // (the Tracker window row: confirm asks for the window, and the row says for a moment how that went)
    CHECK(tracker_says(kTrackerWindowRow) == "Open it beside the game");
    CHECK(press_on(kTrackerWindowRow, 7) && window_opens == 1 && tracker_says(kTrackerWindowRow) == "Opened");
    CHECK(!press_on(kTrackerWindowRow, 4) && window_opens == 1);   // (Right: nothing)
    CHECK(press_on(kTrackerWindowRow, 7) && tracker_says(kTrackerWindowRow) == "The launcher could not be started");
    now_ms += 60000;
    CHECK(tracker_says(kTrackerWindowRow) == "Open it beside the game");

    // (asked 2026-11-27, the groups: a title is hidden with every row of its group; the areas with nothing left are folded
    //  under Finished areas, shut until confirmed, and that row is not there under a Left list)
    const int first = kTrackerFirstArea;
    const char* grouped[] = {"Overworld", "Market", "Finished areas", "Kokiri Forest"};
    for (int r = 0; r < 4; r++) std::snprintf(tracker_name[first + r], sizeof tracker_name[0], "%s", grouped[r]);
    tracker_kind[first] = 'H', tracker_kind[first + 2] = 'D', tracker_folded[first + 3] = true, tracker_count = first + 4;
    CHECK(!tracker_row_hidden(first) && !tracker_row_hidden(first + 1) && !tracker_row_hidden(first + 2) && tracker_row_hidden(first + 3));
    CHECK(tracker_says(first + 2) == "1 area, hidden");
    CHECK(press_on(first + 2, 7) && tracker_done_open && !tracker_row_hidden(first + 3));
    CHECK(tracker_says(first + 2) == "1 area, shown below");
    CHECK(press_on(first + 2, 3) && !tracker_done_open && tracker_row_hidden(first + 3));   // (Left shuts it)
    tracker_show = kTrackerShowLeft;
    put(0, "Market", "Chest A", 1, 0), put(1, "Market", "Chest B", 1, 0);   // (the Market's all collected: nothing to list)
    CHECK(tracker_row_hidden(first + 1) && tracker_row_hidden(first) && tracker_row_hidden(first + 2));
    tracker_show = kTrackerShowAll;
    CHECK(!tracker_row_hidden(first + 1) && !tracker_row_hidden(first));
    std::printf("PASS: a junk check leaves the counts and the Left lists, and rando/junk.txt round-trips\n");
    return 0;
}
'''


def check(ok, what):
    if not ok:
        raise SystemExit("FAIL: " + what)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    menu = (ROOT / "gpu/vk/vk_menu.cpp").read_text(encoding="utf-8")
    constants = "\n".join(m.group(0) for m in re.finditer(r"^constexpr (?:int|ULONGLONG) (kTracker\w+) = \d+;", menu, re.M)
                          if m.group(1) != "kTrackerJunkPress")
    junk = between(menu, "bool tracker_junk[kTrackerChecks];", "// What the tab shows (the first row's Left and Right)")
    show = between(menu, "enum { kTrackerShowAll", "std::atomic<int> tracker_here{-1};")
    functions = "\n".join(block(menu, marker) for marker in (
        "bool tracker_check_shown(int i) {", "bool tracker_check_now(int i) {", "int tracker_row_checks(int row, bool any = false) {",
        "const TrackerCheck* tracker_row_check(int row, int n) {", "bool tracker_row_hidden(int row) {", "bool tracker_junk_flip(int row) {",
        "std::string tracker_says(int row) {", "void tracker_press(int row, const bool* press, bool& changed) {"))
    fixture = (FIXTURE.replace("// CONSTANTS", constants).replace("// TRACKER_CHECK", block(menu, "struct TrackerCheck {"))
               .replace("// JUNK", junk).replace("// SHOW", show).replace("// FUNCTIONS", functions))
    with tempfile.TemporaryDirectory(prefix="tracker-junk-") as tmp:
        cpp, exe = Path(tmp) / "fixture.cpp", Path(tmp) / "fixture"
        cpp.write_text(fixture, encoding="utf-8")
        game = Path(tmp) / "game"
        game.mkdir()
        # (_CRT_SECURE_NO_WARNINGS: the MSVC CRT's fopen deprecation, as the game's own Windows build passes)
        subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-Wno-format-truncation", "-D_CRT_SECURE_NO_WARNINGS",
                        "-iquote", str(ROOT), str(cpp), "-o", str(exe)], check=True)
        subprocess.run([str(exe), str(game)], check=True)

    # ---- the keys: J in menu_tick's keys at kTrackerJunkPress, Y on a controller, and the prompt ----
    tick = block(menu, "void menu_tick() {")
    keys = between(tick, "static const int keys[K_N] = {", "};")
    keys = re.sub(r"//[^\n]*", "", keys[keys.index("{") + 1:])
    entries = [k.strip() for k in keys.split(",") if k.strip()]
    press_at = int(re.search(r"constexpr int kTrackerJunkPress = (\d+);", menu).group(1))
    k_n = int(re.search(r"enum \{ K_N = (\d+) \};", tick).group(1))
    check(len(entries) == k_n and press_at < k_n and entries[press_at] == "'J'",
          "J is not the key at kTrackerJunkPress in menu_tick's keys: %r" % entries)
    check("pad_junk = menu_keys::extra(host && host->binding ? host->binding(HOS_BIND_PAD, HOS_SW_Y, 0) : -1, pad_confirm, pad_back);" in tick and
          "press[kTrackerJunkPress] |= pad(pad_junk);" in tick and "press[kTrackerJunkPress] |= p == pad_junk;" in tick,
          "the controller's Y does not mark junk, or RX_VK_MENU_SCRIPT's pad presses do not reach it")
    check('prompt_list[prompts_n++] = {ui::kExtra, tracker_junk[k - tracker_checks] ? "Not junk" : "Junk", "J"};' in menu and
          "c.extra_dot = menu_keys::dot(pad_junk);" in menu,
          "the Tracker's prompts do not show the junk button")
    # ---- the record is read with the seed's checks, and the panel draws a junk check its own way ----
    load = block(menu, "void tracker_load(bool shown) {")
    check("if (checks) tracker_junk_read(tracker_junk_path(), stamp, checks);" in load and
          "const std::string stamp = on && checks ? tracker_seed_stamp() : std::string();" in load,
          "the junk record is not read with the seed's checks")
    check('return game_folder_path() + "rando\\\\junk.txt";' in junk and 'mods\\\\rando-seed\\\\rando_stamp.txt' in junk,
          "the junk record is not rando\\junk.txt beside collected.txt, or the stamp is not the seed's")
    panel = block(menu, "float tracker_panel(")
    check("got ? 2 : tracker_junk[i] ? 3 : tracker_in_logic(tracker_checks[i])" in panel and
          "if (l.state == 3) c.d->AddLine(" in panel and '{3, "junk"}' in panel,
          "the panel does not draw a junk check struck through, or the legend does not say what it is")
    print("PASS: the Tracker's junk marks")


if __name__ == "__main__":
    main()

"""The Item wheel row (Willow Woods, asked 2026-11-23; ported from ProjectReLink 0.7.9.2's item wheel, GPL-3.0-or-later):
holding R shows the game's item line as a wheel of 8 slots a page (host/oot_wheel.c steers the hidden line and puts the item
chosen on ZR, gpu/vk/vk_wheel.cpp draws the wheel, vk_framegen.cpp lays it over the scene blurred). Read from the sources and
the wheel's pages laid out by host/oot_wheel.c's own code, compiled here with stubs: no game files.

python -I -B tests/test_item_wheel.py [--cc clang]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # (tests/srccut.py: python -I leaves this folder off the path)
from srccut import block, between   # noqa: E402

RUN_ALL_ARGS = ["--cc", "clang"]

ROOT = Path(__file__).resolve().parents[1]
failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def read(*p):
    return (ROOT.joinpath(*p)).read_text(encoding="utf-8")


def wiring():
    state = read("gpu", "vk", "oot_wheel_state.h")
    m = re.search(r"enum \{ HOS_OPT_ITEM_WHEEL = (\d+), HOS_OPT_CYCLE_ITEMS = (\d+) \};", state)
    check(m is not None, "the Item wheel and Cycle items rows have no option ids")
    if m:
        api = read("gpu", "vk", "vk_api.h")
        taken = set()
        for body in re.findall(r"enum \{([^}]*)\}", api):   # (each enum's names: = n, or one more than the name before)
            n = -1
            for part in body.split(","):
                v = re.search(r"=\s*(\d+)", part)
                if not part.strip():
                    continue
                n = int(v.group(1)) if v else n + 1
                if part.strip().startswith("HOS_OPT_"):
                    taken.add(n)
        for k in (1, 2):
            check(int(m.group(k)) not in taken, "option id %s is one of vk_api.h's HOS_OPT_ ids" % m.group(k))
    menu_h = read("gpu", "vk", "vk_menu.h")
    check(re.search(r"int item_wheel = 0;", menu_h) is not None, "the Item wheel row is not off by default")
    check(re.search(r"int cycle_items = 0;", menu_h) is not None, "the Cycle items row is not off by default")
    menu = read("gpu", "vk", "vk_menu.cpp")
    check('{TAB_GAMEPLAY, "Item wheel", &opts.item_wheel, 0, 1, 1, tx_onoff,' in menu, "the Gameplay tab has no Item wheel row")
    replay = read("gpu", "vk", "vk_replay.cpp")
    check("if (id == HOS_OPT_ITEM_WHEEL) return opts.item_wheel != 0;" in replay, "the game side is not told the row's value")
    check("if (tex) framegen_wheel_backdrop(r.cmd, tex->image, tex->format, sw, sh, crop);" in replay,
          "the present does not lay the wheel over the game's picture")
    draw = read("gpu", "vk", "vk_draw.cpp")
    check(draw.count("wheel_scene_note(cmd, s, p, true)") == 3 and "wheel_scene_note(cmd, s, p, false);" in draw,
          "the scene before the HUD (the wheel's backdrop) is not copied after every gameplay upscale")
    backend = read("host", "rx_backend.c")
    check("if (index == MKWVK_WHEEL_QUERY) return (const char *)hos_wheel_state();" in backend and "host_mic_name, hos_mic_select" in backend,
          "the renderer cannot ask the host for the wheel's state")
    hid = read("host", "nn_hid.c")
    check("if (connected) buttons = hos_wheel_input(buttons, stick);" in hid, "the controller's input does not go through the wheel")
    tick = block(read("host", "oot_menu.c"), "void hos_oot_menu_tick(Ctx *c, uint64_t screen) {\n    if (!screen) return;")
    check("if (hos_wheel_menu_tick(c, screen)) return;" in tick, "the menu screens' update does not call the wheel's")
    make = read("nx2", "make_game.py")
    check(all(s in make for s in ('"wheel_assets.py", "--icons"', '"wheel_names.py", "--out"', '"wheel_sounds.py", "--out"')),
          "a build does not make the wheel's icons, names and sounds")
    wheel = read("host", "oot_wheel.c")
    check("ProjectReLink" in wheel and "GPL-3.0-or-later" in wheel, "the port does not say where it came from")
    check("return forced >= 0 ? forced : rx_option(HOS_OPT_ITEM_WHEEL, 0) != 0;" in wheel, "the wheel is not the row's (off by default)")


FIXTURE_HEAD = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "oot_wheel_state.h"
#define MAX_PATH 260
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
static void hos_log(const char *f, ...) { (void)f; }
static unsigned hos_game_path_a(char *b, unsigned n) { (void)b, (void)n; return 0; }
static int wheel_trace(void) { return 0; }
'''

FIXTURE_MAIN = r'''
static void have(const char *const *names) {
    item_n = 0;
    for (; *names; names++) items_add(*names);
}
static const char *at_name(const int at[LAYOUT_MAX], int page, int slot) {
    const int i = at[page * MKWVK_WHEEL_SLOTS + slot];
    return i < 0 ? "" : item_names[i];
}
int main(void) {
    int at[LAYOUT_MAX];
    PageInfo info[PAGES_MAX];
    layout_defaults();
    /* (an adult with the Longshot, the bow, bombs, two bottles of milk and an item no page names) */
    static const char *const adult[] = {"Item_Longshot", "Weapon_Range_Bow", "Item_Bomb", "Item_Bottle_Milk",
                                        "Item_Bottle_Milk#2", "Item_Boomerang", NULL};
    have(adult);
    const int pages = wheel_layout(&layouts[1], 0, at, info);
    CHECK(pages == 4);   /* (the adult's three pages, then the others') */
    CHECK(!strcmp(at_name(at, 0, 0), "Item_Longshot"));     /* (the Longshot in the Hookshot's slot, at the top) */
    CHECK(!strcmp(at_name(at, 0, 7), "Weapon_Range_Bow"));
    CHECK(!strcmp(at_name(at, 0, 2), "Item_Bomb"));
    CHECK(!strcmp(at_name(at, 0, 1), ""));                   /* (the Fire Arrow's slot, not had: empty) */
    /* (the bottles fill the bottle slots from the left over the top: 6, then 7, then 0) */
    CHECK(!strncmp(at_name(at, 2, 6), "Item_Bottle_Milk", 16) && !strncmp(at_name(at, 2, 7), "Item_Bottle_Milk", 16));
    CHECK(info[3].kind == PAGE_OTHERS && !strcmp(at_name(at, 3, 0), "Item_Boomerang"));
    /* (while an item is held a new page follows) */
    CHECK(wheel_layout(&layouts[1], 1, at, info) == 5 && info[4].kind == PAGE_NEW);
    /* (a move: the Boomerang put in the Fire Arrow's empty slot) */
    wheel_layout(&layouts[1], 1, at, info);
    layout_move(&layouts[1], at, info, 5, 3 * MKWVK_WHEEL_SLOTS + 0, 0 * MKWVK_WHEEL_SLOTS + 1);
    CHECK(!strcmp(layouts[1].slot[0][1], "Item_Boomerang"));
    CHECK(wheel_layout(&layouts[1], 0, at, info) == 3 && !strcmp(at_name(at, 0, 1), "Item_Boomerang"));
    /* (the survey: the nearest stop that loads a place not known, -1 when all are) */
    CHECK(survey_stop(0, 12, 0x3f) == 2);        /* (place 6 unknown: a stop 4 before it) */
    CHECK(survey_stop(5, 12, 0xfff) == -1);
    CHECK(survey_stop(5, 12, 0xfff & ~(1u << 3)) == 5);   /* (in the window but not loaded: the cursor itself) */
    printf("PASS: the wheel's pages, a move and the survey\n");
    return 0;
}
'''


def fixture():
    src = read("host", "oot_wheel.c")
    parts = [
        block(src, "static void plain_name(const char *name, char *out, size_t cap) {"),
        between(src, "static char item_names[MKWVK_WHEEL_MAX][48];", "static int row_length(uint64_t node) {"),
        block(src, "static void items_add(const char *name) {"),
        between(src, "#define LAYOUT_PAGES 8", "/* The survey: the row loads only"),
        block(src, "static int survey_stop(int cursor, int count, uint32_t known) {"),
    ]
    return FIXTURE_HEAD + "\n".join(parts) + FIXTURE_MAIN


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="clang")
    a = p.parse_args()
    wiring()
    with tempfile.TemporaryDirectory(prefix="item-wheel-") as tmp:
        c = Path(tmp) / "fixture.c"
        exe = Path(tmp) / "fixture.exe"
        c.write_text(fixture(), encoding="utf-8")
        r = subprocess.run([a.cc, "-std=c11", "-Wall", "-Wno-unused-function", "-I", str(ROOT / "gpu" / "vk"), str(c), "-o", str(exe)],
                           capture_output=True, text=True)
        if r.returncode:
            print(r.stderr)
            check(False, "the wheel's layout code does not compile on its own")
        else:
            r = subprocess.run([str(exe)], capture_output=True, text=True)
            print(r.stdout.strip() or r.stderr.strip())
            check(r.returncode == 0, "the wheel's pages are not laid out as they should be")
    if failed:
        sys.exit(1)
    print("PASS: the Item wheel row is wired in, off by default")


if __name__ == "__main__":
    main()

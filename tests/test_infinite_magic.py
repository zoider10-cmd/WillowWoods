"""Infinite magic, the Debug tab's row (asked 2026-11-23, share/todo.md): no game data.

host/hos_main.c oot_infinite_magic is compiled alone against a fake magic meter and pouch:
- with the row on, a meter below its top gets one large magic jar (the game's own fill, as oot_magic_fill_tick's), at
  most one every OOT_MAGIC_KEEP_EVERY updates; a full meter, no meter (MPMax 0), an event playing or a found magic's fill
  running get nothing;
- with the row off, nothing; HOS_OOT_INFINITE_MAGIC=1 or 0 (a test's) wins over the row.
And by source: it is called with the player's other cheats each update; the menu has the row as a debug tool (an On / Off
toggle, cheat 12, in the Player group), answers HOS_OPT_CHEAT_MAGIC with menu_infinite_magic, which is 0 while the
debug tools are off.

    python -I -B tests/test_infinite_magic.py [--cc gcc]
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # (tests/srccut.py: python -I leaves this folder off the path)
from srccut import block, between   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
typedef struct { uint64_t x[32]; } Ctx;
enum { HOS_OPT_CHEAT_MAGIC = 37 };
#define OOT_MPMAX_HASH 0x12d63a97u
#define OOT_MP_HASH 0x76b18200u
static int row, event, fill_frames, jars, mp, mpmax;
static int oot_magic_fill_frames;
int rx_option(int id, int otherwise) { return id == HOS_OPT_CHEAT_MAGIC ? row : otherwise; }
static void hos_log(const char *f, ...) { (void)f; }
static int oot_event_playing(Ctx *c) { (void)c; return event; }
static int oot_gamedata_live_int(Ctx *c, uint32_t hash, int32_t *value, int set, int *live) {
    (void)c, (void)set, (void)live;
    if (hash == OOT_MPMAX_HASH) return *value = mpmax, 1;
    if (hash == OOT_MP_HASH) return *value = mp, 1;
    return 0;
}
static int oot_pouch_change(Ctx *c, const char *name, int n) {
    (void)c;
    CHECK(!strcmp(name, "Tbox_MagicJar_Large") && n == 1);
    jars++;
    mp = mp + 120 > mpmax ? mpmax : mp + 120;
    return 0;
}
@FN@
static int run(int frames) {
    Ctx c;
    memset(&c, 0, sizeof c);
    jars = 0;
    oot_magic_fill_frames = fill_frames;
    for (int i = 0; i < frames; i++) oot_infinite_magic(&c);
    return jars;
}
int main(void) {
    row = 1, mpmax = 480, mp = 0;
    CHECK(run(OOT_MAGIC_KEEP_EVERY - 1) <= 1);
    CHECK(run(OOT_MAGIC_KEEP_EVERY * 10) >= 3 && mp == 480);   /* (filled, a jar at a time) */
    CHECK(run(OOT_MAGIC_KEEP_EVERY * 10) == 0);                 /* (full: nothing) */
    mp = 400;
    CHECK(run(OOT_MAGIC_KEEP_EVERY * 2) == 1 && mp == 480);
    mpmax = 0, mp = 0;
    CHECK(run(OOT_MAGIC_KEEP_EVERY * 4) == 0);                  /* (no meter) */
    mpmax = 240, mp = 0, event = 1;
    CHECK(run(OOT_MAGIC_KEEP_EVERY * 4) == 0);                  /* (an event plays) */
    event = 0;
    fill_frames = 100;
    CHECK(run(OOT_MAGIC_KEEP_EVERY * 4) == 0);                  /* (a found magic's fill runs) */
    fill_frames = 0;
    row = 0;
    CHECK(run(OOT_MAGIC_KEEP_EVERY * 4) == 0);                  /* (the row off) */
    printf("PASS: infinite magic keeps the meter full with the Debug tab's row on\n");
    return 0;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    fn = ("#define OOT_MAGIC_KEEP_EVERY %s\n" % re.search(r"#define OOT_MAGIC_KEEP_EVERY (\d+)", host).group(1) +
          block(host, "int hos_oot_infinite_magic(void) {") + "\n" + block(host, "static void oot_infinite_magic(Ctx *c) {"))
    tick = between(host, "    oot_magic_fill_tick(c);   /* (a magic found", "\n    {")
    if "oot_infinite_magic(c);" not in tick:
        raise SystemExit("hos_main.c: oot_infinite_magic is not called each update with the found magic's fill")
    api = (ROOT / "gpu" / "vk" / "vk_api.h").read_text(encoding="utf-8")
    if not re.search(r"enum \{ HOS_OPT_CHEAT_HEARTS = 32,[^}]*HOS_OPT_CHEAT_SPEED, HOS_OPT_CHEAT_MAGIC \};", api):
        raise SystemExit("vk_api.h: no HOS_OPT_CHEAT_MAGIC after the other cheats' options")
    replay = (ROOT / "gpu" / "vk" / "vk_replay.cpp").read_text(encoding="utf-8")
    if "if (id == HOS_OPT_CHEAT_MAGIC) return menu_infinite_magic();" not in replay:
        raise SystemExit("vk_replay.cpp: the option is not answered by the menu")
    menu = (ROOT / "gpu" / "vk" / "vk_menu.cpp").read_text(encoding="utf-8")
    for want, why in (('{TAB_DEBUG, "Infinite magic", nullptr, 0, 0, 0, nullptr,', "no Debug tab row"),
                      ("nullptr, false, true, 12},", "the row is not debug tool 12"),
                      ("int menu_infinite_magic() { return cheats_on() ? infinite_magic.load(std::memory_order_relaxed) : 0; }",
                       "menu_infinite_magic is not 0 with the debug tools off"),
                      ("inline bool cheat_is_toggle(int c) { return c == 0 || c == 1 || c == 7 || c == 12; }", "not an On / Off toggle"),
                      ("case 12: return tx_onoff(infinite_magic.load());", "its value is not On / Off"),
                      ("&& i == 12) {", "Left, Right and confirm do not change it")):
        if want not in menu:
            raise SystemExit("vk_menu.cpp: " + why)
    order = re.search(r"constexpr int debug_tools_order\[\] = \{([^}]*)\};", menu).group(1).replace(" ", "").split(",")
    player = re.search(r'\{"Player", 0, (\d+)\}', menu)
    if "12" not in order or not player or order.index("12") >= int(player.group(1)):
        raise SystemExit("vk_menu.cpp: Infinite magic is not shown in the Debug tab's Player group")
    with tempfile.TemporaryDirectory(prefix="infinite-magic-") as tmp:
        c = Path(tmp) / "fixture.c"
        exe = Path(tmp) / "fixture"
        c.write_text(FIXTURE.replace("@FN@", fn), encoding="utf-8")
        subprocess.run([a.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()

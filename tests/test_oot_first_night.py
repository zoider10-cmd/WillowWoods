"""The first adult night's time lock (host/hos_main.c oot_first_night_fix; Longshot d0b9c543, their #1064).

A save that still holds HrlField_isFirstNightTime_Adult (0x8592aa82) outside Hyrule Field can never leave 20:00. With
HOS_OOT_FIRST_NIGHT_FIX=1 the flag is cleared there through the game's own Bool, once; never in Hyrule Field, never with no
map, never while an event plays. Here the repair is OFF unless the switch is set (the same Bool picks a town's arrival time
and gates Hyrule Field's first-night event, beside the randomizer's own clock work: the owner decides), so the switch
unset must leave the flag alone. oot_inventory_refresh must call it with the map it read.

python -I -B tests/test_oot_first_night.py [--cc clang]
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

# (no RUN_ALL_ARGS: run_all.py has no C compiler placeholder; the check finds gcc or clang itself)
ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { int unused; } Ctx;
static int flag = 1;            /* HrlField_isFirstNightTime_Adult */
static int switch_on;           /* HOS_OOT_FIRST_NIGHT_FIX */
static int event_playing;       /* the game's event manager has an active event */
static int cleared;
static int env_on(const char *name) { return !strcmp(name, "HOS_OOT_FIRST_NIGHT_FIX") && switch_on; }
static void hos_log(const char *fmt, ...) { (void)fmt; }
static int oot_gamedata_bool(Ctx *c, uint32_t hash, int *value) {
    (void)c;
    if (hash == 0x8592aa82u) { *value = flag; return 1; }
    return 0;
}
static int oot_gamedata_set_bool(Ctx *c, uint32_t hash, int value) {
    (void)c;
    if (hash != 0x8592aa82u) return 0;
    if (flag != value) cleared++;
    flag = value;
    return 1;
}
static int oot_event_playing(Ctx *c) { (void)c; return event_playing; }

// FIX

static void check(const char *what, int want_flag, int want_cleared) {
    if (flag != want_flag || cleared != want_cleared) {
        fprintf(stderr, "FAIL: %s: flag %d (want %d), clears %d (want %d)\n", what, flag, want_flag, cleared, want_cleared);
        exit(1);
    }
}

int main(int argc, char **argv) {
    Ctx c = {0};
    switch_on = argc > 1 && !strcmp(argv[1], "on");
    if (!switch_on) {
        oot_first_night_fix(&c, "Market_Child");
        check("the switch unset leaves the flag (today's behaviour)", 1, 0);
        puts("PASS: HOS_OOT_FIRST_NIGHT_FIX unset leaves the flag alone");
        return 0;
    }
    oot_first_night_fix(&c, "Market_Child");
    check("the flag is cleared outside Hyrule Field", 0, 1);
    flag = 1, cleared = 0;
    oot_first_night_fix(&c, "HyruleField");
    check("the flag is left alone in Hyrule Field", 1, 0);
    flag = 0, cleared = 0;
    oot_first_night_fix(&c, "Market_Child");
    check("a clear flag is left clear", 0, 0);
    flag = 1, cleared = 0;
    oot_first_night_fix(&c, "");
    check("an empty map leaves the flag", 1, 0);
    event_playing = 1;
    oot_first_night_fix(&c, "Kakariko_Adult");
    check("an event running leaves the flag", 1, 0);
    event_playing = 0;
    oot_first_night_fix(&c, "Kakariko_Adult");
    check("after the event it clears", 0, 1);
    puts("PASS: with HOS_OOT_FIRST_NIGHT_FIX=1 the lock is cleared outside Hyrule Field, and only there");
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default=None)
    args = parser.parse_args()
    cc = ([args.cc] if os.path.isfile(args.cc) else shlex.split(args.cc)) if args.cc else [shutil.which("gcc") or shutil.which("clang") or "cc"]
    host = (ROOT / "host/hos_main.c").read_text(encoding="utf-8")
    fix = re.search(r"^static int oot_first_night_fix\(Ctx \*c, const char \*map\) \{.*?^\}", host, re.M | re.S)
    if not fix:
        raise SystemExit("FAIL: host/hos_main.c has no oot_first_night_fix")
    refresh = re.search(r"^static void oot_inventory_refresh\(Ctx \*c, int64_t now\) \{.*?^\}", host, re.M | re.S)
    if not refresh or "oot_first_night_fix(c, map);" not in refresh.group():
        raise SystemExit("FAIL: oot_inventory_refresh does not call oot_first_night_fix with the map it read")
    if "HOS_OOT_FIRST_NIGHT_FIX" not in (ROOT / "gpu/vk/switches.def").read_text(encoding="utf-8"):
        raise SystemExit("FAIL: no switches.def row for HOS_OOT_FIRST_NIGHT_FIX")
    with tempfile.TemporaryDirectory(prefix="oot-first-night-") as tmp:
        source = Path(tmp) / "test.c"
        source.write_text(FIXTURE.replace("// FIX", fix.group()), encoding="utf-8")
        binary = Path(tmp) / "test.exe"
        subprocess.run(cc + ["-std=c11", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)], check=True)
        for arg in ("off", "on"):
            subprocess.run([str(binary), arg], check=True)


if __name__ == "__main__":
    main()

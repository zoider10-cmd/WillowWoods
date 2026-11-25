"""Pots (POT_BAGGED): whether Link holds a Deku Nut or Stick bag, as a pot holding their bundle is read (host/hos_main.c
oot_pot_bag_held). Reported 2026-11-25: a save loaded in the Market had its stick pots read with the pouch not there yet (its
count -1), taken as a bag held: the game's own sticks, a green rupee with no bag, and no bag ever given. The pouch's count
when it is there; else the save's IsGet.<bag> flags; not known: not held (the pot drops the bundle that gives the bag).
Game-free: the function cut from the source, compiled with stand-ins.

python -I -B tests/test_rando_pot_bag.py [--cc gcc]
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = r'''#include <stdio.h>
#include <stdint.h>
#include <string.h>
typedef struct { uint64_t x[32]; } Ctx;
static int counts[3], flags_known, flags[3];
static const char *names[3] = {"Item_StickBag_Small", "Item_StickBag_Medium", "Item_StickBag_Large"};
static int oot_pouch_count(Ctx *c, const char *name) {
    (void)c;
    for (int i = 0; i < 3; i++) if (!strcmp(name, names[i])) return counts[i];
    return -1;
}
static uint32_t oot_flag_hash(const char *s) {
    for (int i = 0; i < 3; i++) { char f[64]; snprintf(f, sizeof f, "IsGet.%s", names[i]); if (!strcmp(s, f)) return (uint32_t)(i + 1); }
    return 0;
}
static int oot_gamedata_bool(Ctx *c, uint32_t hash, int *value) {
    (void)c;
    if (!flags_known || !hash) return 0;
    *value = flags[hash - 1];
    return 1;
}
@FN@
#define CHECK(x) do { if (!(x)) { printf("FAIL:%d %s\n", __LINE__, #x); return 1; } } while (0)
int main(void) {
    Ctx c;
    memset(&c, 0, sizeof c);
    counts[0] = counts[1] = counts[2] = 0;   /* the pouch there, no bag */
    CHECK(!oot_pot_bag_held(&c, names));
    counts[1] = 1;                            /* the pouch there, a bag */
    CHECK(oot_pot_bag_held(&c, names));
    counts[0] = counts[1] = counts[2] = -1;   /* the pouch not there yet (a save just loaded) */
    flags_known = 1, flags[0] = flags[1] = flags[2] = 0;
    CHECK(!oot_pot_bag_held(&c, names));      /* the save says none got: not held (the report's case) */
    flags[2] = 1;
    CHECK(oot_pot_bag_held(&c, names));       /* the save says one got */
    flags_known = 0;
    CHECK(!oot_pot_bag_held(&c, names));      /* nothing known: not held, the bundle that gives the bag */
    printf("PASS: a pot's Deku Nuts or Sticks: the bag by the pouch, else the save's IsGet flags, else not held\n");
    return 0;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    start = host.index("static int oot_pot_bag_held(Ctx *c, const char *const *sizes) {")
    fn = host[start:host.index("\n}\n", start) + 3]
    answer = host[host.index("static uint64_t oot_pot_look_answer(Ctx *c, uint64_t name_at) {"):]
    answer = answer[:answer.index("\n}\n")]
    if "oot_bundle_holder(item, &sizes) == 1 && !oot_pot_bag_held(c, sizes)" not in answer:
        raise SystemExit("FAIL: a pot's bundle is not chosen by oot_pot_bag_held")
    with tempfile.TemporaryDirectory(prefix="pot-bag-") as tmp:
        src, exe = Path(tmp) / "fixture.c", Path(tmp) / "fixture"
        src.write_text(FIXTURE.replace("@FN@", fn), encoding="utf-8")
        subprocess.run([a.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        print(r.stdout.strip())
        return r.returncode


if __name__ == "__main__":
    sys.exit(main())

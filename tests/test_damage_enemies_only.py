"""Damage numbers and health bars only for enemies and bosses (bug 134, the owner 2026-11-24: a pot hit and a rock blown up
with a bomb showed a number, as every actor with a life loses it at the same write, nx2/oot_patches.py patch_life_hits).

host/hos_main.c hos_oot_hit is cut out of the source with what it keeps (the hits' ring), compiled with stand-ins for the
game's memory, the clock, the log and the renderer's rx_option_set, and given hits on actors by name: an Enemy_ actor
(an enemy, a boss, a mini-boss, a Gold Skulltula) sends its number and reaches the Health bars; a pot, a rock, grass, an
animal or an actor with no name sends nothing; Link's own losses still send nothing. No game files.

python -I -B tests/test_damage_enemies_only.py [--cc clang]
"""
import argparse
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # (python -I leaves the check's own folder off the path)
from srccut import between

# (no RUN_ALL_ARGS: run_all.py has no C compiler placeholder; the check finds gcc or clang itself)
ROOT = Path(__file__).resolve().parents[1]

PRELUDE = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "oot_cheat_items.h"

typedef struct { int unused; } Ctx;
#define OOT_HITS 32
#define OOT_DAMAGE_ABOVE 1.2f
#define ACTOR 0x1000u
#define RESOURCE 0x2000u
static const char *actor_name;   /* the hit actor's resource record's name, at +88 */
static int is_link;
static int sent_hit, sent_at, health_hits;
static uint64_t recomp_load64(Ctx *c, uint64_t a) { (void)c; return a == ACTOR + 16 && actor_name ? RESOURCE : 0; }
static uint8_t recomp_load8(Ctx *c, uint64_t a) {
    (void)c;
    if (!actor_name || a < RESOURCE + 88) return 0;
    const uint64_t i = a - (RESOURCE + 88);
    return i <= strlen(actor_name) ? (uint8_t)actor_name[i] : 0;
}
static int hos_oot_is_player(Ctx *c, uint64_t a) { (void)c; (void)a; return is_link; }
static int64_t hos_now_ns(void) { return 1; }
static int env_on(const char *name) { (void)name; return 0; }
static void hos_log(const char *fmt, ...) { (void)fmt; }
static float oot_load_float(Ctx *c, uint64_t a) { (void)c; (void)a; return 0; }
static int oot_damage_screen(Ctx *c, const float p[3]) { (void)c; (void)p; return 5; }
void rx_option_set(int id, int value) {
    if (id == OOT_DAMAGE_HIT) sent_hit++;
    if (id == OOT_DAMAGE_AT) sent_at++;
    (void)value;
}
'''

MAIN = r'''
static void oot_health_hit(Ctx *c, uint64_t actor, uint64_t life, uint32_t old, uint32_t next, const char *name) {
    (void)c; (void)actor; (void)life; (void)old; (void)next; (void)name;
    health_hits++;
}

static int fails;
static void hit(const char *name, int link, int shown) {
    Ctx c = {0};
    actor_name = name, is_link = link, sent_hit = sent_at = health_hits = 0;
    hos_oot_hit(&c, ACTOR, 4, 2, 2, 0x3000);
    const int got = sent_hit == 1 && sent_at == 1 && health_hits == 1;
    const int none = sent_hit == 0 && sent_at == 0 && health_hits == 0;
    if (shown ? !got : !none) {
        printf("FAIL: a hit on %s%s %s (numbers sent %d, places %d, health bars %d)\n", name ? name : "(no name)",
               link ? " (Link)" : "", shown ? "shows nothing" : "shows a number or a health bar", sent_hit, sent_at, health_hits);
        fails++;
    }
}

int main(void) {
    hit("Enemy_Stalfos", 0, 1);
    hit("Enemy_Dekubaba", 0, 1);         /* (its name as the game keeps it, seen headless 2026-11-23) */
    hit("Enemy_DungeonBoss_Gohma", 0, 1);
    hit("Enemy_MiddleBoss_DarkLink", 0, 1);
    hit("Enemy_Skulltula_Gold", 0, 1);
    hit("Pot", 0, 0);                    /* (a pot: its name as the game keeps it, seen headless 2026-11-24) */
    hit("Obj_Pot_A_01", 0, 0);
    hit("Obj_BombRock", 0, 0);           /* (a rock blown up) */
    hit("Land_Grass_A_01", 0, 0);
    hit("Animal_Cucco", 0, 0);
    hit("FldObj_Sign", 0, 0);
    hit("Npc_Enemy_Like", 0, 0);         /* (Enemy_ in the middle is not an enemy's name) */
    hit(0, 0, 0);                        /* (no resource record: no name) */
    hit("Player", 1, 0);                 /* (Link's own losses) */
    if (!fails) printf("PASS\n");
    return fails != 0;
}
'''


def compiler(given):
    if given:
        return [given] if os.path.isfile(given) else shlex.split(given)
    found = shutil.which("gcc") or shutil.which("clang")
    if not found:
        for name in ("clang.exe", "clang", "gcc.exe", "gcc"):
            local = ROOT / "llvm-mingw" / "bin" / name
            if local.is_file():
                found = str(local)
                break
    return [found or "cc"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default=None)
    args = parser.parse_args()
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    cut = between(host, "static struct { uint64_t actor; int64_t at_ns; uint32_t hit, old, next; char name[48]; } oot_hits[OOT_HITS];",
                  "\n/* Movement speed")
    with tempfile.TemporaryDirectory(prefix="hookshot-damage-enemies-") as tmp:
        tmp = Path(tmp)
        (tmp / "t.c").write_text(PRELUDE + cut + MAIN, encoding="utf-8")
        binary = tmp / ("t.exe" if os.name == "nt" else "t")
        build = subprocess.run(compiler(args.cc) + ["-std=gnu11", "-Wall", "-Wno-unused-function", "-I", str(ROOT / "gpu" / "vk"),
                                                    str(tmp / "t.c"), "-o", str(binary)], text=True, capture_output=True)
        if build.returncode:
            print(build.stdout + build.stderr)
            print("FAIL: the cut of hos_oot_hit does not compile")
            return 1
        run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=30)
        print(run.stdout + run.stderr, end="")
        return run.returncode


if __name__ == "__main__":
    sys.exit(main())

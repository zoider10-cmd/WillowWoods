"""A switch that asks for a Hookshot hit gets it when the Hookshot's tip reaches it (bug 91, the Water Temple's gate
switch by Lake Hylia; nx2/oot_patches.py patch_hook_switch, host/hos_main.c hos_oot_hook_switch): no game data.

The ring above the Water Temple's door (Obj_LakeHrl_SwitchHit_A_01) turns on only for a hit of the Hookshot's damage type:
its AI asks QueryDamageCalculatorIsOnDamageTypeAny (f_82a01a30) and QueryDamageCalculatorIsOnDamageType with type 16
(f_808559c0) of its damage calculator's mask of this frame's damage types. In this build the tip arrives, its area
sensor touches the ring's hit sensor, and no hit is ever recorded (traced 2026-11-22 on a copy of the owner's save with
the gate shut): the mask stays 0, the tip bounces off and the gate's cutscene never plays. The two queries now ask the
host first, which sets the Hookshot's bit in the mask while the tip is at the switch, and for a fifth of a second after.
- the patch on a copy of the two functions' text: the host asked first in each, declared once, a second run changes
  nothing, and a file with neither function is left alone (None);
- the patch is applied by patch_file, counted, and a build where a function moved warns;
- the host's function, compiled alone against a made-up memory: the bit is set for a switch that asks for type 16 with
  the Hookshot's or the Longshot's tip at its sensor, held for the "any" query of the next frames and let go after;
  not for another type, another projectile, a tip far off, another layer's body, a handle gone stale, or with
  HOS_OOT_NO_HOOK_HIT=1 (the game's own behaviour, for a test).

    python -I -B tests/test_rando_hook_switch.py [--cc gcc]
"""
import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # (tests/srccut.py: python -I leaves this folder off the path)
from srccut import block   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def check(ok, why):
    if not ok:
        print("FAIL: %s" % why)
        sys.exit(1)


SOURCE = ('#include "a64.h"\n'
          "void f_808559c0(Ctx *__restrict A64_NOESC c) {\n"
          "    c->x[8]=recomp_load64(c,c->x[0] + 8);\n"
          "}\n"
          "void f_808559d0(Ctx *__restrict A64_NOESC c) {\n"
          "    c->x[8]=recomp_load64(c,c->x[0] + 8);\n"
          "}\n"
          "void f_82a01a30(Ctx *__restrict A64_NOESC c) {\n"
          "    c->x[8]=recomp_load64(c,c->x[0] + 8);\n"
          "}\n")

FIXTURE = r'''#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "@ENV_H@"   /* (env_on: the cut code reads its switch so) */
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
typedef struct { uint64_t x[32]; } Ctx;
#define BASE 0x1000000000ULL
static uint8_t mem[0x10000];
static uint8_t *at(uint64_t a, unsigned n) { CHECK(a >= BASE && a + n <= BASE + sizeof mem); return mem + (a - BASE); }
static uint64_t recomp_load64(Ctx *c, uint64_t a) { uint64_t v; (void)c; memcpy(&v, at(a, 8), 8); return v; }
static uint32_t recomp_load32(Ctx *c, uint64_t a) { uint32_t v; (void)c; memcpy(&v, at(a, 4), 4); return v; }
static uint8_t recomp_load8(Ctx *c, uint64_t a) { (void)c; return *at(a, 1); }
static void recomp_store32(Ctx *c, uint64_t a, uint32_t v) { (void)c; memcpy(at(a, 4), &v, 4); }
static float oot_load_float(Ctx *c, uint64_t a) { float v; (void)c; memcpy(&v, at(a, 4), 4); return v; }
static long long now_ns;
static long long hos_now_ns(void) { return now_ns; }
static int logged;
static void hos_log(const char *fmt, ...) { (void)fmt; logged++; }
@FN@
static void p64(uint64_t a, uint64_t v) { memcpy(at(a, 8), &v, 8); }
static void p32(uint64_t a, uint32_t v) { memcpy(at(a, 4), &v, 4); }
static void pf(uint64_t a, float v) { memcpy(at(a, 4), &v, 4); }
static void place(uint64_t body, float x, float y, float z) { pf(body + 0x8c, x), pf(body + 0x9c, y), pf(body + 0xac, z); }
enum { NODE = 0x000, A1 = 0x100, ACTOR = 0x200, B = 0x500, TABLE = 0x800, TYPE = 0xd00, DC = 0x1000, SENSOR = 0x2800, OWNER = 0x2a00,
       P50 = 0x2e00, PH = 0x2f00, ARR = 0x3200, E = 0x3300, CC = 0x3400, BARR = 0x3500, RB = 0x3600, H = 0x3900, BUF = 0x3a00,
       CON = 0x3b00, OTHER = 0x3c00, LAY = 0x3f00, USER = 0x4000, LINK = 0x4100, SHOOTER = 0x4200, NAME = 0x4600, NODE_ANY = 0x4700 };
#define A(o) (BASE + (o))
static void world(const char *name) {
    memset(mem, 0, sizeof mem);
    p64(A(NODE) + 8, A(A1)), p64(A(A1) + 8, A(ACTOR)), p64(A(ACTOR) + 0x1f0, A(B)), p64(A(B) + 0x270, A(TABLE));
    p64(A(NODE_ANY) + 8, A(A1));
    p64(A(NODE) + 0x20, A(TYPE) | 1), p32(A(TYPE), 16);
    p64(A(TABLE) + 0x2b8, A(DC)), p64(A(TABLE) + 0x3b8, A(SENSOR));
    p64(A(SENSOR) + 0x18, A(OWNER)), p64(A(OWNER) + 0x270, A(TABLE)), p64(A(TABLE) + 0x50, A(P50)), p64(A(P50) + 0x20, A(PH));
    p32(A(PH) + 0x38, 1), p64(A(PH) + 0x40, A(ARR)), p64(A(ARR), A(E)), p64(A(E) + 8, A(CC));
    p32(A(CC) + 0x10, 1), p64(A(CC) + 0x18, A(BARR)), p64(A(BARR) + 8, A(RB)), p64(A(RB) + 0x158, A(H));
    place(A(RB), -183.8f, 109.3f, 497.1f);
    p32(A(H) + 8, 1), p64(A(H) + 0x28, A(BUF)), p64(A(BUF), A(CON)), p64(A(CON) + 0x60, A(OTHER)), p64(A(CON) + 0x68, A(RB));
    p64(A(OTHER) + 0x150, A(LAY)), p32(A(LAY) + 8, 0x1019), p64(A(OTHER) + 0x108, A(USER));
    place(A(OTHER), -183.4f, 109.0f, 496.7f);   /* (where the tip stopped in the trace: 0.6 from the ring) */
    p64(A(USER) + 0x20, A(LINK)), p32(A(USER) + 0x28, 0x10b), p32(A(LINK) + 0x48, 0x10b), p64(A(LINK) + 0x40, A(SHOOTER));
    p64(A(SHOOTER) + 0x260, A(NAME));
    memcpy(at(A(NAME), 32), name, strlen(name) + 1);
}
static uint32_t ask(int any) {   /* (a query as the lifted code calls it; the mask after) */
    Ctx c;
    memset(&c, 0, sizeof c);
    c.x[0] = any ? A(NODE_ANY) : A(NODE);
    hos_oot_hook_switch(&c, any);
    return recomp_load32(&c, A(DC) + 0x2c0);
}
static uint32_t fresh(int any) {   /* (a later second, a new frame's empty mask, then the query) */
    now_ns += 1000000000LL;
    p32(A(DC) + 0x2c0, 0);
    return ask(any);
}
int main(int argc, char **argv) {
    const int off = argc > 1 && !strcmp(argv[1], "off");
    const uint32_t hook = 1u << 16;
    now_ns = 5000000000LL;
    world("Shootable_HookLong");
    if (off) {   /* (HOS_OOT_NO_HOOK_HIT=1: the game's own behaviour) */
        CHECK(fresh(0) == 0 && ask(1) == 0);
        printf("PASS: with HOS_OOT_NO_HOOK_HIT the switch is left to the game\n");
        return 0;
    }
    CHECK(fresh(1) == 0);                 /* (nothing held yet: the "any" query alone gives nothing) */
    CHECK(fresh(0) == hook && logged);    /* (the Longshot's tip at the ring: the hit) */
    p32(A(DC) + 0x2c0, 0x40);             /* (the next frame: another type's bit there, the tip gone from the sensor) */
    p32(A(H) + 8, 0);
    now_ns += 16000000LL;
    CHECK(ask(1) == (hook | 0x40));       /* (held for the "any" query, which the AI asks before the type's; other bits kept) */
    CHECK(ask(0) == (hook | 0x40));
    CHECK(fresh(1) == 0 && ask(0) == 0);  /* (a second on: let go) */
    world("Shootable_Hook");
    CHECK(fresh(0) == hook);              /* (the Hookshot's tip) */
    world("Shootable_HookLong"), p32(A(TYPE), 6);
    CHECK(fresh(0) == 0);                 /* (a switch asking for arrows is not given the Hookshot's hit) */
    world("Shootable_DekuSeed");
    CHECK(fresh(0) == 0);                 /* (another projectile) */
    world("Shootable_HookLong"), place(A(OTHER), -181.5f, 106.6f, 494.6f);
    CHECK(fresh(0) == 0);                 /* (the tip still on its way: its sensor touches from afar) */
    world("Shootable_HookLong"), p32(A(LAY) + 8, 0x100a);
    CHECK(fresh(0) == 0);                 /* (another layer's body: the aim's own sensors) */
    world("Shootable_HookLong"), p32(A(LINK) + 0x48, 0x10c);
    CHECK(fresh(0) == 0);                 /* (the body's actor is gone: its handle is another's now) */
    world("Shootable_HookLong"), p64(A(CON) + 0x68, A(OTHER));
    CHECK(fresh(0) == 0);                 /* (a contact that is not this sensor's: a stale entry) */
    world("Shootable_HookLong"), p64(A(TABLE) + 0x3b8, 0);
    CHECK(fresh(0) == 0);                 /* (no hit sensor) */
    world("Shootable_HookLong"), p64(A(TABLE) + 0x2b8, 0);
    now_ns += 1000000000LL;
    { Ctx c; memset(&c, 0, sizeof c); c.x[0] = A(NODE); hos_oot_hook_switch(&c, 0); }   /* (no damage calculator: nothing read past it) */
    printf("PASS: a switch that asks for the Hookshot gets its hit when the tip is there\n");
    return 0;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()
    sys.path.insert(0, str(ROOT / "nx2"))
    import oot_patches as P   # noqa: E402
    check(hasattr(P, "patch_hook_switch"), "nx2/oot_patches.py has no patch_hook_switch: the two queries do not ask the host")
    got = P.patch_hook_switch(SOURCE)
    check(got is not None and got[1] == 2, "the two queries were not both hooked")
    out = got[0]
    first = out[out.index("void f_808559c0"):out.index("void f_808559d0")]
    other = out[out.index("void f_808559d0"):out.index("void f_82a01a30")]
    second = out[out.index("void f_82a01a30"):]
    check(first.index("hos_oot_hook_switch(c, 0);") < first.index("recomp_load64"), "the type's query does not ask the host first")
    check(second.index("hos_oot_hook_switch(c, 1);") < second.index("recomp_load64"), "the any query does not ask the host first")
    check("hos_oot_hook_switch" not in other, "another function was hooked")
    check(out.count("extern void hos_oot_hook_switch(Ctx *c, int any);\n") == 1, "the host's function is not declared once")
    again = P.patch_hook_switch(out)
    check(again is not None and again[0] == out and again[1] == 2, "a second run changed the file or lost count")
    one = P.patch_hook_switch(SOURCE[:SOURCE.index("void f_82a01a30")])
    check(one is not None and one[1] == 1, "a file with one of the two was not hooked once")
    check(P.patch_hook_switch('#include "a64.h"\nvoid f_808559d0(Ctx *__restrict A64_NOESC c) {\n}\n') is None, "a file with neither was patched")
    src = (ROOT / "nx2" / "oot_patches.py").read_text(encoding="utf-8")
    check("patch_hook_switch(out)" in src and 'counts["hook switch queries"] += ' in src and 'total["hook switch queries"] != ' in src,
          "the patch is not applied, counted and warned of")
    host = (ROOT / "host" / "hos_main.c").read_text(encoding="utf-8")
    fn = block(host, "static int oot_hook_tip_at(Ctx *c, uint64_t sensor) {") + "\n" + block(host, "void hos_oot_hook_switch(Ctx *c, int any) {")
    with tempfile.TemporaryDirectory(prefix="hook-switch-") as tmp:
        c = Path(tmp) / "fixture.c"
        exe = Path(tmp) / "fixture"
        c.write_text(FIXTURE.replace("@FN@", fn).replace("@ENV_H@", (ROOT / "gpu/vk/compat/hookshot_env.h").as_posix()), encoding="utf-8")
        subprocess.run([a.cc, "-std=c11", "-Wall", "-Wextra", "-Werror", str(c), "-o", str(exe)], check=True)
        env = {k: v for k, v in os.environ.items() if k != "HOS_OOT_NO_HOOK_HIT"}
        subprocess.run([str(exe)], check=True, env=env)
        subprocess.run([str(exe), "off"], check=True, env=dict(env, HOS_OOT_NO_HOOK_HIT="1"))


if __name__ == "__main__":
    main()

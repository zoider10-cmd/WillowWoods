"""The OptimizeChangeBank thread's allocations are tried again when their heap is full (host/oot_heap_retry.c, nx2/oot_patches.py).

Issue 1697 (thread OptimizeChangeBanc writes guest 0x8 a few frames after loading a save), TomShafford/Hookshot's crash at
backflip + attack, issue 2437 (the same thread writes guest 0x20, lr 0x8044f684, crossing Gerudo Valley's bridge) and the
crash reports that end with a buffer made in the parent and a crash at the build's next allocation: a model's CPU
buffer, one of its 0x238-byte objects, that object's buffers or f_80443000's blocks (a heap's tryAlloc) or its GPU memory
(f_80522050) came back null from a full heap and the game wrote through it. Builds host/oot_heap_retry.c, as it is,
over a guest memory of its own with made-up sead heaps (name, size, parent, a vtable with tryAlloc and getFreeSize) and
a stand-in for the game's f_80522050, then checks:

- an allocation that succeeds is the game's alone: one call, nothing logged, nothing changed;
- a GPU allocation that fails is tried again in each parent with room, then in the game's default heap (no waits:
  it never sleeps); the request names its own heap again afterwards; nothing with room: it fails as before;
- a CPU allocation is tried in each parent with room, returned in x0, the other registers and the flags as they were,
  each of the seven places counted under its own name;
- one that came from a parent hands the rest of its build to that parent: the heaps' holder names the parent, the
  build's own heap is what f_804566e0's two reads of its heap get, and the second puts it back in the holder
  (HOS_GPU_ALLOC_REST=0 or a holder naming another heap: that allocation alone); a parent too small for the whole build
  is skipped; a GPU heap that is the same heap goes and comes back with it; a holder on a stack below the image
  (sead::MainThread's) counts;
- HOS_GPU_ALLOC_RETRY=0: the game's call alone, as shipped; HOS_GPU_ALLOC_TEST_FAIL=<n>: the first n refused by the named
  heap without calling it (nothing leaks), and the retry makes them; <gpu>,<cpu>,<objects>: each kind its own count;
  HOS_GPU_ALLOC_TEST_FILL=<n>[,<place>]: the first n heaps at the place (the object's when none is named) are emptied
  through their own tryAlloc, once each, and never the parent a build was handed;
- nx2/oot_patches.py makes the edits on lifted text shaped as the lift writes it, once, and a second run changes nothing;
  the places of other files (the hot list's) are edited there too, with their declarations.

python -I -B tests/test_oot_heap_retry.py [--cc gcc]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cc", "gcc"]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "nx2"))
import oot_patches  # noqa: E402

HOS_H = r'''#pragma once
#include <stdint.h>
#include <string.h>
typedef struct { uint64_t x[32]; uint8_t n, z, c, v; } Ctx;
typedef void (*A64Fn)(Ctx *);
#define GUEST 0x80000000ull
#define LOW 0x10ff000ull   /* (a page below the image: sead::MainThread's stack is there) */
extern unsigned char mem[0x100000], low[0x1000];
static inline unsigned char *guest(uint64_t a) { return a < GUEST ? low + (a - LOW) : mem + (a - GUEST); }
static inline uint64_t recomp_load8(Ctx *c, uint64_t a) { (void)c; return *guest(a); }
static inline uint64_t recomp_load64(Ctx *c, uint64_t a) { uint64_t v; (void)c; memcpy(&v, guest(a), 8); return v; }
static inline void recomp_store64(Ctx *c, uint64_t a, uint64_t v) { (void)c; memcpy(guest(a), &v, 8); }
A64Fn a64_lookup(uint64_t a);
void a64_icall(Ctx *c, uint64_t a);
void hos_log(const char *fmt, ...);
void hos_sleep_ns(int64_t ns);
'''

FIXTURE = r'''#include "hos.h"
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL:%d %s\n", __LINE__, #x); exit(1); } } while (0)
unsigned char mem[0x100000], low[0x1000];
static int logs, sleeps, game_calls;
static char said[8192];   /* (what was logged since it was last emptied) */
void hos_log(const char *fmt, ...) {
    char line[512];
    va_list a;
    va_start(a, fmt), vsnprintf(line, sizeof line, fmt, a), va_end(a);
    puts(line);
    logs++;
    if (strlen(said) + strlen(line) + 2 < sizeof said) strcat(said, line), strcat(said, "\n");
}
void hos_sleep_ns(int64_t ns) { (void)ns; sleeps++; }

/* heaps: at H(i), +0 the vtable, +0x20 its name, +0x30 its size, +0x38 its parent; the room left in room[i] */
#define VT 0x80001000ull
#define FN_TRY 0x80002000ull
#define FN_FREE 0x80002100ull
#define H(i) (0x80010000ull + 0x100ull * (i))
#define NAME(i) (0x80020000ull + 0x40ull * (i))
static uint64_t room[8], next_block = 0x80080000ull, free_after_calls[8];
static uint64_t heap_index(uint64_t h) { return (h - H(0)) / 0x100; }
static void try_alloc(Ctx *c) {   /* tryAlloc(heap, size, align): the block or 0 */
    const uint64_t i = heap_index(c->x[0]), size = c->x[1];
    c->x[1] = c->x[2] = c->x[3] = 0xdead;   /* (a callee's scratch registers) */
    c->n = c->z = c->c = c->v = 1;
    if (room[i] < size) { c->x[0] = 0; return; }
    room[i] -= size;
    c->x[0] = next_block, next_block += (size + 15) & ~15ull;
}
static void get_free(Ctx *c) { c->x[0] = room[heap_index(c->x[0])]; c->x[5] = 0xdead; }
A64Fn a64_lookup(uint64_t a) { return a == FN_TRY ? try_alloc : a == FN_FREE ? get_free : NULL; }
void a64_icall(Ctx *c, uint64_t a) { a64_lookup(a)(c); }
static void make_heap(int i, int parent, uint64_t free_room, const char *name) {
    recomp_store64(NULL, H(i), VT);
    strcpy((char *)mem + (NAME(i) - GUEST), name);
    recomp_store64(NULL, H(i) + 0x20, NAME(i));
    recomp_store64(NULL, H(i) + 0x30, 0x100000);
    recomp_store64(NULL, H(i) + 0x38, parent < 0 ? 0 : H(parent));
    room[i] = free_room;
}

/* the game's f_80522050: x1 the request (+0 count, +8 the heap, 0: the default, heap 3), x2 the size of one; x0 bit 0 */
static uint64_t default_heap = H(3);
static void game_gpu_alloc(Ctx *c) {
    game_calls++;
    uint64_t heap = recomp_load64(c, c->x[1] + 8);
    if (!heap) heap = default_heap;
    const uint64_t i = heap_index(heap), size = recomp_load64(c, c->x[1]) * c->x[2];
    if (free_after_calls[i] && game_calls >= (int)free_after_calls[i]) room[i] += size;   /* (a free landed) */
    c->x[0] = room[i] >= size ? (room[i] -= size, 1) : 0;
    c->x[9] = 0xdead;
}
void hos_oot_gpu_alloc(Ctx *c, void (*game)(Ctx *));
int hos_oot_heap_refuse(Ctx *c, uint64_t heap, uint64_t holder, uint64_t lr);
extern int hos_oot_heap_test_enabled;
void hos_oot_heap_test_init(void);
void hos_oot_heap_retry(Ctx *c, uint64_t heap, uint64_t size, uint64_t align, uint64_t lr, uint64_t holder);
void hos_oot_heap_rest_own(Ctx *c, uint64_t holder);
void hos_oot_heap_rest_end(Ctx *c, uint64_t holder);
#define BUFFER 0x80456910ull    /* (the places' return addresses: the +200 buffer, the 0x238-byte object, its second */
#define OBJECT 0x8044f670ull    /*  buffer, f_80443000's 0x310-byte object) */
#define OBJECT_BUFFER 0x8044f074ull
#define BLOCK 0x80443e30ull
/* the heaps' holder of a build: +8 the heap its allocations name (f_804558a0's four words on its stack) */
#define HOLDER 0x80050000ull
static void hold(uint64_t heap) { recomp_store64(NULL, HOLDER + 8, heap), recomp_store64(NULL, HOLDER + 16, H(3)); }
static uint64_t held(void) { return recomp_load64(NULL, HOLDER + 8); }
static uint64_t held_gpu(void) { return recomp_load64(NULL, HOLDER + 16); }   /* (the GPU heap: another one unless set) */

#define REQ 0x80030000ull
static void request(Ctx *c, uint64_t heap, uint64_t count) {
    memset(c, 0, sizeof *c);
    recomp_store64(c, REQ, count);
    recomp_store64(c, REQ + 8, heap);
    recomp_store64(c, REQ + 0x20, NAME(7));
    c->x[0] = 0x80040000ull, c->x[1] = REQ, c->x[2] = 0x100, c->x[30] = 0x80456f1cull;
    game_calls = logs = sleeps = 0;
}
static void reset(void) {
    memset(free_after_calls, 0, sizeof free_after_calls);
    make_heap(0, 1, 0, "OptimizeChangeBank");   /* (the named heap; its parent 1, whose parent is the root 2) */
    make_heap(1, 2, 0, "Model");
    make_heap(2, -1, 0, "Root");
    make_heap(3, -1, 0, "Default");
    make_heap(4, 1, 0, "Model/Other");
}
int main(int argc, char **argv) {
    Ctx c;
    recomp_store64(NULL, VT + 0x30, FN_TRY);
    recomp_store64(NULL, VT + 0x80, FN_FREE);
    strcpy((char *)mem + (NAME(7) - GUEST), "gsys::ModelResource(MatBlock)");
    const char *mode = argc > 1 ? argv[1] : "";
    hos_oot_heap_test_init();
    CHECK(hos_oot_heap_test_enabled == (!strcmp(mode, "refuse") || !strcmp(mode, "off-refuse") ||
          !strcmp(mode, "split") || !strcmp(mode, "object") || !strcmp(mode, "fill") ||
          !strcmp(mode, "fill-at") || !strcmp(mode, "blocks")));

    if (!strcmp(mode, "off")) {   /* HOS_GPU_ALLOC_RETRY=0: the game's call alone */
        reset(), room[1] = 1 << 20;
        request(&c, H(0), 4);
        hos_oot_gpu_alloc(&c, game_gpu_alloc);
        CHECK(!(c.x[0] & 1) && game_calls == 1 && !logs);
        c.x[0] = 0;
        hos_oot_heap_retry(&c, H(0), 0x4198, 8, 0x80456910ull, 0);
        CHECK(c.x[0] == 0 && room[1] == 1 << 20);
        hold(H(0));
        hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
        CHECK(c.x[0] == 0 && room[1] == 1 << 20 && held() == H(0));
        CHECK(!hos_oot_heap_refuse(&c, H(0), 0, BUFFER) && !hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT) && room[0] == 0);
        puts("PASS: HOS_GPU_ALLOC_RETRY=0: the game's own call alone");
        return 0;
    }
    if (!strcmp(mode, "off-refuse")) {   /* HOS_GPU_ALLOC_RETRY=0 HOS_GPU_ALLOC_TEST_FAIL=1: the full heap's failure, as shipped */
        reset(), room[0] = room[1] = 1 << 20;
        request(&c, H(0), 4);
        hos_oot_gpu_alloc(&c, game_gpu_alloc);
        CHECK(!(c.x[0] & 1) && game_calls == 0 && room[0] == 1 << 20 && room[1] == 1 << 20);
        CHECK(hos_oot_heap_refuse(&c, H(0), 0, BUFFER) && !hos_oot_heap_refuse(&c, H(0), 0, BUFFER));
        c.x[0] = 0;
        hos_oot_heap_retry(&c, H(0), 0x4198, 8, 0x80456910ull, 0);
        CHECK(c.x[0] == 0 && room[1] == 1 << 20);
        puts("PASS: HOS_GPU_ALLOC_RETRY=0 with HOS_GPU_ALLOC_TEST_FAIL=1: the failure the game crashes on, not tried again");
        return 0;
    }
    if (!strcmp(mode, "refuse")) {   /* HOS_GPU_ALLOC_TEST_FAIL=2 */
        reset(), room[0] = room[1] = 1 << 20;
        for (int k = 0; k < 3; k++) {
            request(&c, H(0), 4);
            const uint64_t named = room[0], parent = room[1];
            hos_oot_gpu_alloc(&c, game_gpu_alloc);
            CHECK(c.x[0] & 1);
            if (k < 2) CHECK(room[0] == named && room[1] == parent - 0x400 && !sleeps);   /* (refused: made in the parent) */
            else CHECK(room[0] == named - 0x400 && game_calls == 1);                 /* (then the game's own again) */
        }
        CHECK(hos_oot_heap_refuse(&c, H(0), 0, BUFFER) && hos_oot_heap_refuse(&c, H(0), 0, BUFFER) && !hos_oot_heap_refuse(&c, H(0), 0, BUFFER));
        hold(H(0));
        CHECK(hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT) && hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT) &&
              !hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT));
        CHECK(room[0] == (1 << 20) - 0x400);   /* (refused without a call: nothing taken from it) */
        puts("PASS: HOS_GPU_ALLOC_TEST_FAIL=2: two of each kind refused by their heap without a call, made by the retry, then as shipped");
        return 0;
    }
    if (!strcmp(mode, "split")) {   /* HOS_GPU_ALLOC_TEST_FAIL=0,1: the model buffer alone */
        reset(), room[0] = 1 << 20;
        request(&c, H(0), 4);
        hos_oot_gpu_alloc(&c, game_gpu_alloc);
        CHECK((c.x[0] & 1) && game_calls == 1 && !logs);
        CHECK(hos_oot_heap_refuse(&c, H(0), 0, BUFFER) && !hos_oot_heap_refuse(&c, H(0), 0, BUFFER));
        CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT));
        puts("PASS: HOS_GPU_ALLOC_TEST_FAIL=0,1: the GPU memory as shipped, one model buffer refused, no object");
        return 0;
    }
    if (!strcmp(mode, "object")) {   /* HOS_GPU_ALLOC_TEST_FAIL=0,0,1: the 0x238-byte object alone, made by the retry */
        reset(), room[0] = 1 << 20, room[1] = 4 << 20;
        request(&c, H(0), 4);
        hos_oot_gpu_alloc(&c, game_gpu_alloc);
        CHECK((c.x[0] & 1) && game_calls == 1 && !logs);
        CHECK(!hos_oot_heap_refuse(&c, H(0), 0, BUFFER));
        hold(H(0));
        CHECK(hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT) && !hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT));
        const uint64_t named = room[0];
        c.x[0] = 0;   /* (refused: the patched call made none, the heap it names untouched) */
        hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
        CHECK(c.x[0] >= 0x80080000ull && room[0] == named && room[1] == (4 << 20) - 0x238);
        CHECK(strstr(said, "oot: model object, 0x238 bytes from heap") && !strstr(said, "model buffer"));
        CHECK(held() == H(1) && strstr(said, "the rest of the build takes its memory"));
        puts("PASS: HOS_GPU_ALLOC_TEST_FAIL=0,0,1: the GPU memory and the buffers as shipped, one object refused and made in the parent");
        return 0;
    }
    if (!strcmp(mode, "rest-off")) {   /* HOS_GPU_ALLOC_REST=0: the object from the parent, the build left with its heap */
        reset(), room[1] = 4 << 20;
        memset(&c, 0, sizeof c), hold(H(0));
        hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
        CHECK(c.x[0] >= 0x80080000ull && room[1] == (4 << 20) - 0x238 && held() == H(0) && !strstr(said, "the rest of"));
        c.x[0] = 0x1234, c.x[8] = 0x5678;
        hos_oot_heap_rest_end(&c, HOLDER);
        CHECK(c.x[0] == 0x1234 && c.x[8] == 0x5678 && held() == H(0));
        puts("PASS: HOS_GPU_ALLOC_REST=0: the object made in the parent, the holder left naming the full heap");
        return 0;
    }
    if (!strcmp(mode, "fill-at")) {   /* HOS_GPU_ALLOC_TEST_FILL=1,0x80443e2c: at f_80443000's object, not at f_8044f420's */
        reset(), room[0] = 0x5123, room[1] = 4 << 20;
        memset(&c, 0, sizeof c), hold(H(0));
        CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT) && room[0] == 0x5123 && !said[0]);
        CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, BLOCK) && room[0] < 16 && strstr(said, "is full"));
        hos_oot_heap_retry(&c, H(0), 0x310, 8, BLOCK, HOLDER);
        CHECK(c.x[0] >= 0x80080000ull && held() == H(1));
        puts("PASS: HOS_GPU_ALLOC_TEST_FILL=1,0x80443e2c: the heap emptied at that place alone, and the build handed over there");
        return 0;
    }
    if (!strcmp(mode, "blocks")) {   /* HOS_GPU_ALLOC_TEST_FAIL=0,0,2: the third number is all the other CPU places' */
        reset(), room[0] = 1 << 20;
        memset(&c, 0, sizeof c), hold(H(0));
        CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, BUFFER));
        CHECK(hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT_BUFFER) && hos_oot_heap_refuse(&c, H(0), HOLDER, BLOCK) &&
              !hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT) && room[0] == 1 << 20);
        puts("PASS: HOS_GPU_ALLOC_TEST_FAIL=0,0,2: two of the other CPU allocations refused, whichever places they are");
        return 0;
    }
    if (!strcmp(mode, "fill")) {   /* HOS_GPU_ALLOC_TEST_FILL=2: the first two heaps at the object's place emptied, once each */
        reset(), room[0] = 0x5123, room[1] = 4 << 20, room[4] = 0x900;
        memset(&c, 0, sizeof c), hold(H(0));
        for (int r = 0; r < 31; r++) c.x[r] = 0x1000 + r;
        c.n = 1, c.z = 0, c.c = 1, c.v = 0;
        const Ctx before = c;
        CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT));   /* (not refused: the heap's own tryAlloc says no next) */
        CHECK(room[0] < 16 && room[1] == 4 << 20 && strstr(said, "HOS_GPU_ALLOC_TEST_FILL: ") && strstr(said, "is full"));
        for (int r = 0; r < 31; r++) CHECK(c.x[r] == before.x[r]);
        CHECK(c.n == 1 && c.z == 0 && c.c == 1 && c.v == 0);
        c.x[0] = H(0), c.x[1] = 0x238, c.x[2] = 8, try_alloc(&c);
        CHECK(c.x[0] == 0);
        hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);   /* (the object, and the build's rest) */
        CHECK(c.x[0] >= 0x80080000ull && held() == H(1) && room[1] == (4 << 20) - 0x238);
        CHECK(!hos_oot_heap_refuse(&c, H(1), HOLDER, OBJECT) && room[1] == (4 << 20) - 0x238);   /* (the parent is not filled) */
        hos_oot_heap_rest_end(&c, HOLDER);
        CHECK(held() == H(0));
        room[0] = 0x900, said[0] = 0;   /* (a second time at the same heap: filled once only) */
        CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT) && room[0] == 0x900 && !said[0]);
        hold(H(4));                     /* (the second heap) */
        CHECK(!hos_oot_heap_refuse(&c, H(4), HOLDER, OBJECT) && room[4] < 16 && strstr(said, "Model/Other"));
        room[3] = 0x900, said[0] = 0, hold(H(3));   /* (n = 2: no third) */
        CHECK(!hos_oot_heap_refuse(&c, H(3), HOLDER, OBJECT) && room[3] == 0x900 && !said[0]);
        puts("PASS: HOS_GPU_ALLOC_TEST_FILL=2: two heaps emptied through their own tryAlloc, once each, the registers as "
             "they were; the parent a build was handed is left alone");
        return 0;
    }

    /* made at once: the game's alone */
    reset(), room[0] = 1 << 20;
    request(&c, H(0), 4);
    hos_oot_gpu_alloc(&c, game_gpu_alloc);
    CHECK((c.x[0] & 1) && game_calls == 1 && !logs && !sleeps && recomp_load64(&c, REQ + 8) == H(0));

    /* full, its parent with room: made there at once, no sleep */
    reset(), room[1] = 1 << 20;
    request(&c, H(0), 4);
    hos_oot_gpu_alloc(&c, game_gpu_alloc);
    CHECK((c.x[0] & 1) && game_calls == 2 && !sleeps && room[1] == (1 << 20) - 0x400 && recomp_load64(&c, REQ + 8) == H(0));

    /* full, its parent too, the root has room: made there; the request names its heap again */
    reset(), room[2] = 1 << 20;
    request(&c, H(0), 4);
    hos_oot_gpu_alloc(&c, game_gpu_alloc);
    CHECK((c.x[0] & 1) && room[2] == (1 << 20) - 0x400 && recomp_load64(&c, REQ + 8) == H(0));
    CHECK(c.x[30] == 0x80456f1cull);

    /* no parent with room: the game's default heap */
    reset(), room[3] = 1 << 20;
    request(&c, H(0), 4);
    hos_oot_gpu_alloc(&c, game_gpu_alloc);
    CHECK((c.x[0] & 1) && room[3] == (1 << 20) - 0x400 && recomp_load64(&c, REQ + 8) == H(0));

    /* nothing has room: it fails, as before, and says so */
    reset();
    request(&c, H(0), 4);
    hos_oot_gpu_alloc(&c, game_gpu_alloc);
    CHECK(!(c.x[0] & 1) && logs >= 3 && recomp_load64(&c, REQ + 8) == H(0));
    CHECK(!sleeps);
    puts("PASS: GPU memory from a full heap: in a parent with room, in the default heap, or not at all; never a sleep");

    /* the CPU buffer: in the nearest parent with room; x0 the block, everything else as it was */
    reset(), room[2] = 1 << 20;
    memset(&c, 0, sizeof c);
    for (int r = 1; r < 31; r++) c.x[r] = 0x1000 + r;
    c.n = 1, c.z = 0, c.c = 1, c.v = 0;
    Ctx before = c;
    hos_oot_heap_retry(&c, H(0), 0x4198, 8, 0x80456910ull, 0);
    CHECK(c.x[0] >= 0x80080000ull && room[2] == (1 << 20) - 0x4198);
    for (int r = 1; r < 31; r++) CHECK(c.x[r] == before.x[r]);
    CHECK(c.n == 1 && c.z == 0 && c.c == 1 && c.v == 0);
    reset(), room[1] = 0x4198 + 0x1000;   /* (a parent without the margin is passed over) */
    c = before;
    hos_oot_heap_retry(&c, H(0), 0x4198, 8, 0x80456910ull, 0);
    CHECK(c.x[0] == 0 && room[1] == 0x4198 + 0x1000);
    reset(), room[1] = 1 << 20;
    c = before;
    hos_oot_heap_retry(&c, H(0), 0x4198, 8, 0x80456910ull, 0);
    CHECK(c.x[0] && room[1] == (1 << 20) - 0x4198);
    reset(), room[1] = 1 << 20;   /* (the second site, the +168 buffer, the same way) */
    c = before;
    hos_oot_heap_retry(&c, H(0), 0x800, 8, 0x80456da4ull, 0);
    CHECK(c.x[0] && room[1] == (1 << 20) - 0x800);
    CHECK(!hos_oot_heap_refuse(&c, H(0), 0, BUFFER));
    CHECK(strstr(said, "model buffer (0x8045690c)") && strstr(said, "model buffer (0x80456da0) 1 blocks"));
    CHECK(!strstr(said, "model object"));
    puts("PASS: the model buffer from a full heap: made in its nearest parent with room, x0 alone changed");

    /* f_8044f420's object: counted at its own site; a holder naming another heap is left alone. */
    reset(), room[2] = 1 << 20;
    c = before, said[0] = 0, hold(0);
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(c.x[0] >= 0x80080000ull && room[2] == (1 << 20) - 0x238);
    for (int r = 1; r < 31; r++) CHECK(c.x[r] == before.x[r]);
    CHECK(c.n == 1 && c.z == 0 && c.c == 1 && c.v == 0);
    CHECK(strstr(said, "oot: model object, 0x238 bytes from heap") && strstr(said, "model object (0x8044f66c) 1 blocks"));
    CHECK(!strstr(said, "model buffer") && held() == 0);
    reset(), room[1] = 0x238 + 0x1000;   /* (a parent without the margin is passed over; nothing else has room) */
    c = before, said[0] = 0;
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(c.x[0] == 0 && room[1] == 0x238 + 0x1000 && strstr(said, "oot: model object: no heap had room") && held() == 0);
    CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, OBJECT));
    puts("PASS: f_8044f420's object from a full heap: made in its nearest parent with room, counted as its own site");

    /* the rest of the build: a parent with room for the whole heap is named in the holder, so the build's next
       allocations, which read the heap there, are that parent's; x0 alone changed */
    reset(), room[1] = 0x4000, room[2] = 4 << 20;
    c = before, said[0] = 0, hold(H(0));
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(c.x[0] >= 0x80080000ull && room[1] == 0x4000 && room[2] == (4 << 20) - 0x238 && held() == H(2) && held_gpu() == H(3));
    for (int r = 1; r < 31; r++) CHECK(c.x[r] == before.x[r]);
    CHECK(!strstr(said, "the GPU's too"));
    CHECK(strstr(said, "the rest of the build takes its memory from heap") && strstr(said, "\"Root\"") &&
          strstr(said, "(1 builds so far)"));
    c.x[0] = held(), c.x[1] = 0x60, c.x[2] = 8, try_alloc(&c);   /* (the game's next allocation, unchanged code) */
    CHECK(c.x[0] && room[2] == (4 << 20) - 0x238 - 0x60 && room[0] == 0);
    /* f_804566e0's last read: x0 the heap and x8 its getFreeSize, loaded through the holder, are its own heap's again */
    c = before, c.x[0] = H(2), c.x[8] = 0xbad;
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == H(0) && held_gpu() == H(3) && c.x[0] == H(0) && c.x[8] == FN_FREE);
    for (int r = 1; r < 31; r++) CHECK(r == 8 || c.x[r] == before.x[r]);
    /* No parent can support the hand-over: do not consume a block in the smaller one. */
    reset(), room[1] = 0x4000;
    c = before, hold(H(0));
    hos_oot_heap_retry(&c, H(0), 0x238, 8, OBJECT, HOLDER);
    CHECK(!c.x[0] && room[1] == 0x4000 && held() == H(0));
    c.x[0] = 0x1234, c.x[8] = 0x5678;   /* (once: a build that was not handed over is not touched) */
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == H(0) && c.x[0] == 0x1234 && c.x[8] == 0x5678);
    /* the parent runs out too: handed on to its parent, and the build's own heap is still the one put back */
    reset(), room[1] = 4 << 20, room[2] = 8 << 20;
    c = before, hold(H(0));
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(held() == H(1));
    room[1] = 0;
    hos_oot_heap_retry(&c, H(1), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(c.x[0] && held() == H(2));
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == H(0) && c.x[0] == H(0));
    /* a model whose GPU heap is its CPU heap (f_80522050 takes a small object from it first, unchecked): both handed
       over, both put back; handed on to the next parent together too */
    reset(), room[1] = 4 << 20, room[2] = 8 << 20;
    c = before, said[0] = 0, hold(H(0)), recomp_store64(NULL, HOLDER + 16, H(0));
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(held() == H(1) && held_gpu() == H(1) && strstr(said, "takes its memory, the GPU's too, from heap"));
    room[1] = 0;
    hos_oot_heap_retry(&c, H(1), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(held() == H(2) && held_gpu() == H(2));
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == H(0) && held_gpu() == H(0) && c.x[0] == H(0));
    /* a holder that names another heap (the game took the thread's heap: its +8 is 0) is left alone */
    reset(), room[1] = 4 << 20;
    c = before, hold(0);
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(c.x[0] && held() == 0);
    c.x[0] = 0x1234, c.x[8] = 0x5678;
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == 0 && c.x[0] == 0x1234 && c.x[8] == 0x5678);
    /* a build that left its holder otherwise than it was handed (not seen in the game: one return): nothing put back */
    reset(), room[1] = 4 << 20;
    c = before, hold(H(0));
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, HOLDER);
    CHECK(held() == H(1));
    hold(H(3)), c.x[0] = 0x1234, c.x[8] = 0x5678;
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == H(3) && c.x[0] == 0x1234 && c.x[8] == 0x5678);
    /* the +200 buffer made in a parent hands the build over as well (the crash reports' case: the buffer made in the
       parent, the crash at the build's next allocation): f_804566e0's first read of its heap, just after, gets the
       build's own with the holder left naming the parent, its last read puts it back */
    reset(), room[1] = 4 << 20;
    c = before, said[0] = 0, hold(H(0));
    hos_oot_heap_retry(&c, H(0), 0x4198, 8, BUFFER, HOLDER);
    CHECK(c.x[0] && held() == H(1) && strstr(said, "oot: model buffer: the rest of the build takes its memory from heap"));
    c = before, c.x[0] = H(1), c.x[8] = 0xbad;
    hos_oot_heap_rest_own(&c, HOLDER);
    CHECK(c.x[0] == H(0) && c.x[8] == FN_FREE && held() == H(1));
    for (int r = 1; r < 31; r++) CHECK(r == 8 || c.x[r] == before.x[r]);
    c.x[0] = H(1), c.x[1] = 0x238, c.x[2] = 8, try_alloc(&c);   /* (the build's next allocation, the game's own code) */
    CHECK(c.x[0] && room[0] == 0);
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == H(0) && c.x[0] == H(0) && c.x[8] == FN_FREE);
    c.x[0] = 0x1234, c.x[8] = 0x5678;   /* (a build that was not handed over: both reads as the game made them) */
    hos_oot_heap_rest_own(&c, HOLDER), hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(c.x[0] == 0x1234 && c.x[8] == 0x5678 && held() == H(0));
    /* the object's buffers and f_80443000's blocks: the same retry and hand-over, each under its own name */
    reset(), room[1] = 4 << 20;
    c = before, said[0] = 0, hold(H(0));
    hos_oot_heap_retry(&c, H(0), 0x40, 8, OBJECT_BUFFER, HOLDER);
    CHECK(c.x[0] && held() == H(1) && strstr(said, "oot: object buffer, 0x40 bytes from heap") &&
          strstr(said, "object buffer (0x8044f070) 1 blocks"));
    hos_oot_heap_rest_end(&c, HOLDER);
    c = before, said[0] = 0;
    hos_oot_heap_retry(&c, H(0), 0x310, 8, BLOCK, HOLDER);
    CHECK(c.x[0] && held() == H(1) && strstr(said, "oot: model block, 0x310 bytes from heap") &&
          strstr(said, "model block (0x80443e2c) 1 blocks"));
    hos_oot_heap_rest_end(&c, HOLDER);
    CHECK(held() == H(0));
    /* a place that is none of them is not refused and not counted */
    CHECK(!hos_oot_heap_refuse(&c, H(0), HOLDER, 0x80456c20ull));
    /* sead::MainThread's holder: its stack is below the image (guest 0x10ff130 in a run), handed over all the same */
    reset(), room[1] = 4 << 20;
    c = before, recomp_store64(NULL, 0x10ff130ull + 8, H(0));
    hos_oot_heap_retry(&c, H(0), 0x238, 8, 0x8044f670ull, 0x10ff130ull);
    CHECK(c.x[0] && recomp_load64(NULL, 0x10ff130ull + 8) == H(1));
    hos_oot_heap_rest_end(&c, HOLDER);   /* (another build's end is not this one's) */
    CHECK(recomp_load64(NULL, 0x10ff130ull + 8) == H(1));
    hos_oot_heap_rest_end(&c, 0x10ff130ull);
    CHECK(recomp_load64(NULL, 0x10ff130ull + 8) == H(0) && c.x[0] == H(0) && c.x[8] == FN_FREE);
    puts("PASS: an object from a parent hands the rest of its build to that parent, and the build's own heap is back "
         "at f_804566e0's last read of it; a holder on a stack below the image too");
    return 0;
}
'''

# Synthetic functions contain only patch anchors and invented surrounding statements.
OBJECT_FUNCTION = """void synthetic_object(Ctx *c) {
    c->x[9] = 17;
{ uint64_t _t = c->x[8]; c->x[30] = 0x8044f670ULL; A64_ICALL(c, _t); }
    c->x[9] = 19;
}
"""
OTHER_FUNCTIONS = """void synthetic_other(Ctx *c) {
    c->x[10] = 23;
{ uint64_t _t = c->x[8]; c->x[30] = 0x8044efc8ULL; A64_ICALL(c, _t); }
{ uint64_t _t = c->x[8]; c->x[30] = 0x8044f074ULL; A64_ICALL(c, _t); }
{ uint64_t _t = c->x[8]; c->x[30] = 0x80443200ULL; A64_ICALL(c, _t); }
{ uint64_t _t = c->x[8]; c->x[30] = 0x80443e30ULL; A64_ICALL(c, _t); }
    c->x[10] = 29;
}
"""
LIFTED = """#include "a64.h"
void synthetic_build(Ctx *c) {
{ uint64_t _t = c->x[8]; c->x[30] = 0x80456910ULL; A64_ICALL(c, _t); }
    c->x[11] = 31;
{ uint64_t _t = c->x[8]; c->x[30] = 0x8045692cULL; A64_ICALL(c, _t); }
    c->x[11] = 37;
{ uint64_t _t = c->x[8]; c->x[30] = 0x80456da4ULL; A64_ICALL(c, _t); }
c->x[30] = 0x80456f1cULL; f_80522050(c);
c->x[30] = 0x80457098ULL; f_80522050(c);
    c->x[12] = 41;
{ uint64_t _t = c->x[8]; c->x[30] = 0x8045718cULL; A64_ICALL(c, _t); }
    c->x[12] = 43;
}
void synthetic_caller(Ctx *c) {
c->x[30] = 0x80dfe6a4ULL; f_80522050(c);
}
void f_80522050(Ctx *c) { c->x[0] = 47; }
""" + OBJECT_FUNCTION + OTHER_FUNCTIONS



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cc", default="gcc")
    a = p.parse_args()

    out, found = oot_patches.patch_heap_retry(LIFTED)
    assert "hos_oot_heap_retry(c, _hh, _hn, _ha, 0x8044f670ULL, _ho)" in out, \
        "f_8044f420's tryAlloc of its 0x238-byte object (0x8044f66c) is not tried again: issue 2437's crash"
    assert found == [2, 2, 5, 2], found
    assert out.count("hos_oot_gpu_alloc(c, f_80522050)") == 2
    assert "c->x[30] = 0x80dfe6a4ULL; f_80522050(c);" in out, "another caller of f_80522050 was changed"
    assert "void f_80522050(Ctx *c) { c->x[0] = 47; }" in out, "f_80522050 itself was changed"
    # (each place hands the retry the heaps' holder as it reads it itself)
    for lr, holder in (("0x80456910ULL", "recomp_load64(c, c->x[31] + 56)"), ("0x80456da4ULL", "recomp_load64(c, c->x[31] + 56)"),
                       ("0x8044f670ULL", "c->x[21]"), ("0x8044efc8ULL", "c->x[22]"), ("0x8044f074ULL", "c->x[22]"),
                       ("0x80443200ULL", "recomp_load64(c, c->x[31] + 0)"), ("0x80443e30ULL", "recomp_load64(c, c->x[31] + 0)")):
        assert out.count("_ha = c->x[2], _ho = %s;   /* (nx2/oot_patches.py: host/oot_heap_retry.c) */\n"
                         "  if (hos_oot_heap_test_enabled && hos_oot_heap_refuse(c, _hh, _ho, %s)) c->x[0] = 0;\n"
                         "  else { uint64_t _t = c->x[8]; c->x[30] = %s; A64_ICALL(c, _t); }\n"
                         "  if (!c->x[0]) hos_oot_heap_retry(c, _hh, _hn, _ha, %s, _ho); }\n" % (holder, lr, lr, lr)) == 1, lr
    assert "    c->x[9] = 17;" in out and "    c->x[10] = 29;" in out
    # The hooks precede the unchanged call anchors, with synthetic statements on either side.
    for which, lr, before, after in (("own", 0x8045692c, "    c->x[11] = 31;\n", "    c->x[11] = 37;\n"),
                                     ("end", 0x8045718c, "    c->x[12] = 41;\n", "    c->x[12] = 43;\n")):
        assert before + oot_patches.REST_NEW % (which, lr) + after in out
    assert out.count("hos_oot_heap_rest_own(c, ") == 1 and out.count("hos_oot_heap_rest_end(c, ") == 1
    assert out.count(oot_patches.GPU_ALLOC_DECL) == 1 and out.count(oot_patches.HEAP_ALLOC_DECL) == 1
    assert out.count(oot_patches.REST_DECL) == 1
    assert oot_patches.patch_heap_retry(out) == (out, [2, 2, 5, 2]), "a second run changed the text"
    other = LIFTED
    for lr in ("0x80456910", "0x80456da4", "0x80456f1c", "0x80457098", "0x8044f670", "0x8045692c", "0x8045718c", "0x8044efc8",
               "0x8044f074", "0x80443200", "0x80443e30"):
        other = other.replace(lr + "ULL", "%#xULL" % (int(lr, 16) + 4))
    assert oot_patches.patch_heap_retry(other) == (other, [0, 0, 0, 0]), "another version's text was edited"
    # (the hot list's files: the places f_804566e0 is not in, each with its declarations and no others)
    for text, n in ((OBJECT_FUNCTION, 1), (OTHER_FUNCTIONS, 4), (OBJECT_FUNCTION + OTHER_FUNCTIONS, 5)):
        alone, found = oot_patches.patch_heap_retry('#include "a64.h"\n' + text)
        assert found == [0, 0, n, 0] and alone.count("hos_oot_heap_retry(c, _hh, _hn, _ha, ") == n, found
        assert alone.count(oot_patches.HEAP_ALLOC_DECL) == 1, "a place alone in a file lacks its declarations"
        assert oot_patches.GPU_ALLOC_DECL not in alone and oot_patches.REST_DECL not in alone
        assert oot_patches.patch_heap_retry(alone) == (alone, [0, 0, n, 0])
    import inspect
    assert "patch_heap_retry(out) if protect_hearts else" in inspect.getsource(oot_patches.patch_file), \
        "the edits are made on builds other than the supported one"
    print("PASS: nx2/oot_patches.py: the eleven places edited once (f_80522050's other callers left), a second run changes "
          "nothing, other text is left alone, a place alone in a file has its declarations, the supported build only")

    # (Reborn 4050cb2's count: split_hot's code_hot.c may hold a second copy of an object site's function, each patched)
    import collections
    import contextlib
    import io

    def heap_warning(gpu, cpu, objects, rest):
        total = collections.Counter({"heap GPU sites": gpu, "heap CPU sites": cpu, "heap object sites": objects,
                                     "heap rest sites": rest})
        said = io.StringIO()
        with contextlib.redirect_stdout(said):
            try:
                oot_patches.report(["code.c"], [total], protect_hearts=True)
            except SystemExit:
                pass
        return "OptimizeChangeBank allocations were found" in said.getvalue()
    assert not heap_warning(2, 2, 5, 2) and not heap_warning(2, 2, 10, 2), "a hot copy of an object site is warned of"
    assert heap_warning(2, 2, 4, 2) and heap_warning(2, 3, 5, 2) and heap_warning(2, 2, 5, 1), "a missing place is not"
    print("PASS: report(): the object sites at least once each (hot copies too), the other places exactly once")

    cc =shutil.which(a.cc) or shutil.which("gcc") or shutil.which("clang")
    if not cc:
        print("SKIP: no C compiler")
        return
    with tempfile.TemporaryDirectory(prefix="heap-retry-") as tmp:
        tmp = Path(tmp)
        (tmp / "hos.h").write_text(HOS_H, encoding="utf-8")
        (tmp / "fixture.c").write_text(FIXTURE, encoding="utf-8")
        (tmp / "oot_heap_retry.c").write_text((ROOT / "host" / "oot_heap_retry.c").read_text(encoding="utf-8"),
                                              encoding="utf-8")
        exe = tmp / ("fixture.exe" if os.name == "nt" else "fixture")
        subprocess.run([cc, "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror", "-I", str(tmp), str(tmp / "fixture.c"),
                        str(tmp / "oot_heap_retry.c"), "-o", str(exe)], check=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("HOS_GPU_ALLOC")}
        for mode, extra in (("", {}), ("off", {"HOS_GPU_ALLOC_RETRY": "0"}), ("refuse", {"HOS_GPU_ALLOC_TEST_FAIL": "2"}),
                            ("off-refuse", {"HOS_GPU_ALLOC_RETRY": "0", "HOS_GPU_ALLOC_TEST_FAIL": "1"}),
                            ("split", {"HOS_GPU_ALLOC_TEST_FAIL": "0,1"}),
                            ("object", {"HOS_GPU_ALLOC_TEST_FAIL": "0,0,1"}),
                            ("rest-off", {"HOS_GPU_ALLOC_REST": "0"}),
                            ("fill", {"HOS_GPU_ALLOC_TEST_FILL": "2"}),
                            ("fill-at", {"HOS_GPU_ALLOC_TEST_FILL": "1,0x80443e2c"}),
                            ("blocks", {"HOS_GPU_ALLOC_TEST_FAIL": "0,0,2"})):
            r = subprocess.run([str(exe), mode], env=dict(env, **extra), capture_output=True, text=True)
            print("\n".join(line for line in r.stdout.splitlines() if line.startswith("PASS")))
            if r.returncode:
                raise SystemExit("FAIL (%s):\n%s%s" % (mode or "retry", r.stdout, r.stderr))


if __name__ == "__main__":
    main()

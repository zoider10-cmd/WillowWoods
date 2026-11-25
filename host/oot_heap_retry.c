/* (hookshot) Allocations of the game's "OptimizeChangeBank" thread tried again when their heap has no room, instead of the
   game going on with a null pointer and crashing a few frames later.

   The OptimizeChangeBank thread rebuilds a model's material block (f_804566e0, "gsys::ModelResource(MatBlock)") and takes
   memory for it from heaps its caller names (its second argument's +8 for the CPU's parts, +16 for the GPU's): small heaps
   of their own per model resource ("Model/....bfres", tens of KB), children of a large one. When such a heap is full none
   of these allocations is checked:
   - two CPU buffers from the heap's tryAlloc (vtable +0x30), at 0x8045690c (stored at the MatBlock's +200, its bump
     allocator's memory) and 0x80456da0 (stored at +168, the same base/used/size layout), each sized for the model. A
     null one makes its bump allocator hand out guest address 0: the next store, in f_8044cb30, writes guest 0x8 (issue
     1697: "CRASH: exception 0xc0000005 (write ..., guest 0x8)", thread OptimizeChangeBanc, lr 0x80456d48, every time a few
     frames after loading that player's save, since 2.0.12);
   - the GPU memory, f_80522050 called at 0x80456f18 and 0x80457094, leaves the material block with no memory pool
     (0x80457248), and the block is written to guest address 0 two calls later (TomShafford/Hookshot's crash at
     backflip + attack);
   - a 0x238-byte object from the same heap's tryAlloc, at 0x8044f66c in f_8044f420, one for each entry it adds to its
     list (the array at its first argument's +40, their number at +32). f_804566e0 reaches it from its call of f_8044cb30
     (0x80456d44) through f_8044db80, each handing the heaps down as its last argument. The object's 0x228 bytes after a
     16-byte head are cleared at once, so a null one is written from guest 0x10 (issue 2437: "CRASH: exception
     0xc0000005 (write ..., guest 0x20)", thread OptimizeChangeBanc, lr 0x8044f684 with x0 0x10 and x2 0x228, crossing
     Gerudo Valley's bridge as adult Link, in a log with none of the retries below);
   - what that build takes next from the same heap: two buffers for each of those objects (f_8044ed60, 0x8044efc4 and
     0x8044f070, handed on to f_8044eb10 and f_8044f300), then in f_80443000 a buffer (0x804431fc, written from its +384
     on) and a 0x310-byte object (0x80443e2c, written at once). The crash reports of v3.0.0 have each: write guest 0 with
     lr 0x814f2438 under 0x8044f3c0 and 0x8044f088 (the second buffer), write guest 0x190 with lr 0x80443240, write guest
     0 with lr 0x80443e30.
   Each is tried again in the heap's parents up to the root, the first with room (the GPU memory then in the game's
   default heap). Only these call sites are changed: f_80522050's other callers (some 30) are as shipped, and so is the
   other way f_8044f420 gets that object (f_8005eca0 at 0x8044f798, taken when the pointer it tests first is null).

   The rest of a build. A heap with no room for one of these has none for the next, and a build takes memory in places
   that are not in the list (f_8044e020's 0x268-byte object at 0x8044e1ec; the 0x90-byte object f_80522050 takes from its
   request's heap before the GPU memory itself, written through before the call can fail: write guest 0x10, lr 0x80056c28
   under 0x805220d0, from 0x80456f1c). Crash reports of v3.0.0 end with the +200 buffer made in the parent and, on the next
   line, the crash at another of the build's allocations. All of them read the heap at the +8 of the heaps' holder: four
   words of f_804558a0's on its stack (a vtable, the CPU heap, the GPU heap, one more), made for its one call of
   f_804566e0 and handed down as each function's last argument. So when one of the CPU allocations above had to come from
   a parent, that parent is written to the holder's +8 and the rest of the build takes its memory there, without asking
   the full heap again (only a parent with room for a heap of the model's size; HOS_GPU_ALLOC_REST=0: that allocation
   alone), and to its +16 as well where the GPU heap is that same heap. f_804566e0 reads the holder's heap twice for its
   count of the memory the build took (the heap's free size at 0x80456928, just after the +200 buffer, and at
   0x80457188, the difference added to the MatBlock's +680): both reads get the build's own heap
   (hos_oot_heap_rest_own, hos_oot_heap_rest_end), and the second puts it back in the holder (the function returns in
   one place, right after).
   The build is not the OptimizeChangeBank thread's alone: sead::MainThread, SceneLowPriority,
   BaseProcCreateAndDeleteThread and BootupBackgroundWorkThread make these objects too (a run with each one refused).

   Freeing: the MatBlock's destructor (f_8093f940) frees +168 and +200 through f_8021dea0, the game's free by address,
   which walks the heap tree for the heap whose range holds the block (read from the lifted code, not traced in a run), so
   a block from a parent goes back to that parent. The model's own heap does not count it (MatBlock +680's accounting
   neither). The 0x238-byte objects go back through f_8021dea0 as well: f_8044f420 frees the ones it replaces (0x80450264)
   and their list's destructor, f_8021d4b0, the rest (0x8021d500); the object's destructor (f_8021d560) frees its two
   buffers (its +136 and +184) through f_8021dea0 too, and f_8021d2e0 f_80443000's buffer and 0x310-byte object
   (0x8021d3b8, 0x8021d41c). The other blocks of a build handed to a parent were not followed to their frees. With bit 1
   of its flags f_8044f420 hands the objects it replaces to a release list instead (f_835b3190, 0x80450240), whose own
   release was not read. Every block moved to a parent is counted per call site, and the cumulative totals are logged
   every 16 moves after the first 60 log lines; these counts do not track frees. A build handed to a parent is logged
   with that parent's free size, every 16th after those lines; other users of that heap affect that free size too.

   The GPU part is ported from TomShafford/Hookshot 55d68e8cd6 and 65c1998222 (GPL-3.0, a Hookshot fork), by TomShafford;
   its waits before the parents are left out (its own log showed they did not help).

   A sead heap here (vtable 0x84c172c8, the heap class of these): +0x20 its name, +0x28 its memory, +0x30 its size, +0x38 its
   parent, vtable +0x30 tryAlloc(size, alignment), vtable +0x80 its free size (ExpHeap: the free list summed, main+0x834916d0).

   HOS_GPU_ALLOC_RETRY=0: none is tried again (as shipped).
   HOS_GPU_ALLOC_REST=0: the rest of a build stays with its full heap after one of its allocations came from a parent.
   HOS_GPU_ALLOC_TEST_FAIL=<n>, <gpu>,<cpu> or <gpu>,<cpu>,<objects> (a test): the first n allocations of each kind at these
   sites (or that many of the GPU memory, of the two CPU buffers and of the other CPU allocations, the objects' and
   f_80443000's; two numbers: none of those) are refused by the heap they name, as a full heap would, so the retry runs
   (with HOS_GPU_ALLOC_RETRY=0: the game's crash, as shipped).
   HOS_GPU_ALLOC_TEST_FILL=<n>[,<place>] (a test): the first n model heaps that reach a place (the call's address, hex;
   left out: the 0x238-byte object's, 0x8044f66c) are filled first, every free block of theirs taken and kept, so the
   heap itself refuses that allocation and whatever the build asks of it afterwards: the state issue 2437's heap was
   in. */
#include "hos.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { HEAP_NAME = 0x20, HEAP_START = 0x28, HEAP_SIZE = 0x30, HEAP_PARENT = 0x38, VT_TRY_ALLOC = 0x30, VT_FREE_SIZE = 0x80 };

static int on_unless_zero(const char *name) {   /* (unset: on; "0": off) */
    const char *e = getenv(name);
    return !e || atoi(e) != 0;
}
static int retry_on(void) {
    return on_unless_zero("HOS_GPU_ALLOC_RETRY");
}
static int rest_on(void) {
    return on_unless_zero("HOS_GPU_ALLOC_REST");
}
/* Set before game threads start, after the environment file has been read. */
int hos_oot_heap_test_enabled;
void hos_oot_heap_test_init(void) {
    const char *fail = getenv("HOS_GPU_ALLOC_TEST_FAIL"), *fill = getenv("HOS_GPU_ALLOC_TEST_FILL");
    const char *second = fail ? strchr(fail, ',') : NULL, *third = second ? strchr(second + 1, ',') : NULL;
    hos_oot_heap_test_enabled = (fill && atol(fill) > 0) || (fail && atol(fail) > 0) ||
                                (second && atol(second + 1) > 0) || (third && atol(third + 1) > 0);
}
/* HOS_GPU_ALLOC_TEST_FAIL: 1 while this kind's first n allocations are refused (kind 0 the GPU memory, 1 the two CPU
   buffers, 2 the other CPU allocations) */
static int test_fail(int kind) {
    static long left[3];
    static volatile int read;   /* (set once both counts are in: no thread decrements a count another is still setting) */
    if (!__atomic_load_n(&read, __ATOMIC_ACQUIRE)) {   /* ("<n>": every kind; "<gpu>,<cpu>[,<objects>]": each its own) */
        static volatile long lock;
        while (__sync_lock_test_and_set(&lock, 1)) {}
        if (!read) {
            const char *e = getenv("HOS_GPU_ALLOC_TEST_FAIL"), *comma = e ? strchr(e, ',') : NULL;
            const char *second = comma ? strchr(comma + 1, ',') : NULL;
            left[0] = e ? atol(e) : 0;
            left[1] = !e ? 0 : comma ? atol(comma + 1) : atol(e);
            left[2] = !e ? 0 : second ? atol(second + 1) : comma ? 0 : atol(e);
            __atomic_store_n(&read, 1, __ATOMIC_RELEASE);
        }
        __sync_lock_release(&lock);
    }
    return __atomic_sub_fetch(&left[kind], 1, __ATOMIC_RELAXED) >= 0;
}
static int readable(uint64_t a) { return a >= 0x80000000ULL && a < (1ULL << 39) - 0x100; }
static int guest_string(Ctx *c, uint64_t at, char *out, int n) {   /* (a guest C string: 1 if it reads as one) */
    int i = 0, ok = readable(at);
    for (; ok && i < n - 1; i++) {
        const char ch = (char)recomp_load8(c, at + i);
        if (!ch) break;
        if (ch < 32 || ch >= 127) ok = 0;
        out[i] = ch;
    }
    if (!ok || i < 2) i = 0, out[i++] = '?', ok = 0;
    out[i] = 0;
    return ok;
}
/* A guest function called as the game would, every register and flag as before but x0: its result */
static uint64_t guest_call(Ctx *c, uint64_t fn, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t lr) {
    uint64_t x[31];
    const uint8_t n = c->n, z = c->z, cf = c->c, v = c->v;
    memcpy(x, c->x, sizeof x);
    c->x[0] = a0, c->x[1] = a1, c->x[2] = a2, c->x[30] = lr;
    a64_icall(c, fn);
    const uint64_t r = c->x[0];
    memcpy(c->x, x, sizeof x);
    c->n = n, c->z = z, c->c = cf, c->v = v;
    return r;
}
static uint64_t heap_method(Ctx *c, uint64_t heap, unsigned slot) {   /* (0: none) */
    if (!readable(heap)) return 0;
    const uint64_t vt = recomp_load64(c, heap);
    return readable(vt) ? recomp_load64(c, vt + slot) : 0;
}
static uint64_t free_size(Ctx *c, uint64_t heap) {   /* (the heap's own getFreeSize; ~0: unknown) */
    const uint64_t fn = heap_method(c, heap, VT_FREE_SIZE);
    return fn && a64_lookup(fn) ? guest_call(c, fn, heap, 0, 0, c->x[30]) : ~0ULL;
}
static void describe(Ctx *c, uint64_t heap, char *out, int n) {
    char name[48], kb[32];
    if (!readable(heap)) { snprintf(out, n, "heap %#llx", (unsigned long long)heap); return; }
    if (!guest_string(c, recomp_load64(c, heap + HEAP_NAME), name, sizeof name))
        guest_string(c, recomp_load64(c, heap + HEAP_START), name, sizeof name);
    const uint64_t f = free_size(c, heap);
    if (f == ~0ULL) snprintf(kb, sizeof kb, "?");
    else snprintf(kb, sizeof kb, "%llu", (unsigned long long)(f >> 10));
    snprintf(out, n, "heap %#llx \"%s\" (%llu KB, %s KB free)", (unsigned long long)heap, name,
             (unsigned long long)(recomp_load64(c, heap + HEAP_SIZE) >> 10), kb);
}
static int tell(void) {   /* (the first 60 failures logged) */
    static volatile long told;
    return __atomic_fetch_add(&told, 1, __ATOMIC_RELAXED) < 60;
}
/* The CPU allocations tried again: the call's return address, what the log calls it, its name in the counts, and which of
   HOS_GPU_ALLOC_TEST_FAIL's numbers refuses it (1: the two buffers', 2: the others') */
static const struct { uint64_t lr; const char *what, *name; int kind; } SITES[] = {
    {0x80456910ULL, "model buffer", "model buffer (0x8045690c)", 1},     /* f_804566e0: its MatBlock's +200 */
    {0x80456da4ULL, "model buffer", "model buffer (0x80456da0)", 1},     /*             and +168 */
    {0x8044f670ULL, "model object", "model object (0x8044f66c)", 2},     /* f_8044f420: the 0x238-byte object */
    {0x8044efc8ULL, "object buffer", "object buffer (0x8044efc4)", 2},   /* f_8044ed60: its two buffers */
    {0x8044f074ULL, "object buffer", "object buffer (0x8044f070)", 2},
    {0x80443200ULL, "model block", "model block (0x804431fc)", 2},       /* f_80443000: its buffer */
    {0x80443e30ULL, "model block", "model block (0x80443e2c)", 2},       /*             and its 0x310-byte object */
};
enum { N_SITES = sizeof SITES / sizeof SITES[0] };
static int site_of(uint64_t lr) {   /* (-1: none of them) */
    for (int k = 0; k < N_SITES; k++)
        if (SITES[k].lr == lr) return k;
    return -1;
}
/* Blocks moved to a parent heap, per call site (slot 0: the GPU memory; then SITES in their order), and their bytes: the
   totals logged every 16th move after the log budget, and with each move while it lasts. What a build handed to a
   parent takes there afterwards is not in them */
static volatile long moved_n[1 + N_SITES], moved_bytes[1 + N_SITES];
static void count_moved(int slot, uint64_t bytes, int say) {
    const char *const name = slot ? SITES[slot - 1].name : "GPU memory";
    const long n = __atomic_add_fetch(&moved_n[slot], 1, __ATOMIC_RELAXED);
    const long b = __atomic_add_fetch(&moved_bytes[slot], (long)bytes, __ATOMIC_RELAXED);
    if (say || n % 16 == 0)
        hos_log("oot: heap-full retries so far: %s %ld blocks, %ld KB in parent heaps", name, n, b >> 10);
}

/* ---- the GPU memory: f_80522050(x0 the memory block, x1 the request: +0 the count, +8 the heap, +0x20 what it is for; x2
   the size of one). nx2/oot_patches.py makes f_804566e0's two calls of it call this, with the game's function ---- */
static int gpu_alloc_in(Ctx *c, A64Fn game, uint64_t a0, uint64_t a1, uint64_t a2, uint64_t lr, uint64_t heap,
                        uint64_t in) {
    recomp_store64(c, a1 + 8, in);
    c->x[0] = a0, c->x[1] = a1, c->x[2] = a2, c->x[30] = lr;
    game(c);
    recomp_store64(c, a1 + 8, heap);
    return (int)(c->x[0] & 1);
}
void hos_oot_gpu_alloc(Ctx *c, A64Fn game) {
    const uint64_t a0 = c->x[0], a1 = c->x[1], a2 = c->x[2], lr = c->x[30];
    const int on = retry_on() && readable(a1);
    const int refused = readable(a1) && recomp_load64(c, a1 + 8) && test_fail(0);
    if (refused && !on) {   /* (the failure alone, as a full heap gives it) */
        hos_log("oot: GPU memory refused by HOS_GPU_ALLOC_TEST_FAIL, not tried again (HOS_GPU_ALLOC_RETRY=0) (lr %#llx)",
                (unsigned long long)lr);
        c->x[0] = 0;
        return;
    }
    if (!refused) {
        game(c);
        if (!on || (c->x[0] & 1)) return;
    }
    const uint64_t count = recomp_load64(c, a1), heap = recomp_load64(c, a1 + 8), what = recomp_load64(c, a1 + 0x20);
    char name[64], where[160];
    guest_string(c, what, name, sizeof name);
    describe(c, heap, where, sizeof where);
    const int say = tell();
    if (say)
        hos_log("oot: GPU memory for %s, %#llx bytes from %s, %s (lr %#llx)", name, (unsigned long long)(count * a2), where,
                refused ? "refused by HOS_GPU_ALLOC_TEST_FAIL" : "failed", (unsigned long long)lr);
    int ok = 0;
    /* (the heaps it was made in: their parents up to the root, the free left in them after their children) */
    uint64_t h = heap;
    for (int up = 0; up < 8 && readable(h) && !ok; up++) {
        const uint64_t parent = recomp_load64(c, h + HEAP_PARENT);
        if (!readable(parent) || parent == h) break;
        h = parent;
        const uint64_t f = free_size(c, h);
        if (f != ~0ULL && f < count * a2 + 0x2000) continue;
        ok = gpu_alloc_in(c, game, a0, a1, a2, lr, heap, h);
        if (say) {
            describe(c, h, where, sizeof where);
            hos_log("oot: GPU memory: %s in its parent %s", ok ? "made" : "not made either", where);
        }
    }
    if (!ok && heap) {   /* (the game's own default when no heap is named: the thread's heap, or the root) */
        ok = gpu_alloc_in(c, game, a0, a1, a2, lr, heap, 0);
        if (say) hos_log("oot: GPU memory: %s in the game's default heap", ok ? "made" : "not made either");
    }
    if (ok) count_moved(0, count * a2, say);
    if (!ok && say) hos_log("oot: GPU memory: no heap had room: the game goes on without it (and crashes writing to it)");
}

/* ---- the CPU allocations (SITES): the heap's tryAlloc gave x0 = 0 (or a test switch refused it: nx2/oot_patches.py then
   made no call). Tried in each parent with room, x0 the block or 0 still, and the rest of the build handed to that
   parent. `holder` is the heaps' holder as the place reads it: its +8 is the heap the build's allocations name, its +16
   the GPU heap. It is on the building thread's stack, which for sead::MainThread is below the image (guest 0x10ff130 in
   a run), so readable() is not asked of it: the game has just read the heap through it ---- */
/* The block from the nearest parent with room (0: none had); *in the heap it came from */
static uint64_t in_parents(Ctx *c, uint64_t heap, uint64_t size, uint64_t align, uint64_t lr, const char *what, int say,
                           uint64_t whole, int handover, uint64_t *in) {
    char where[160];
    uint64_t h = heap, got = 0;
    for (int up = 0; up < 8 && readable(h) && !got; up++) {
        const uint64_t parent = recomp_load64(c, h + HEAP_PARENT);
        if (!readable(parent) || parent == h) break;
        h = parent;
        const uint64_t f = free_size(c, h), fn = heap_method(c, h, VT_TRY_ALLOC);
        if (!fn || !a64_lookup(fn)) continue;
        if (handover) {
            /* Reserve the model-sized remainder as well as this allocation and the margin. */
            if (f == ~0ULL || f < size || f - size < 0x2000 || f - size - 0x2000 < whole) continue;
        } else if (f != ~0ULL && (f < size || f - size < 0x2000)) continue;
        got = guest_call(c, fn, h, size, align, lr);
        if (say) {
            describe(c, h, where, sizeof where);
            hos_log("oot: %s: %s in its parent %s", what, got ? "made" : "not made either", where);
        }
    }
    if (!got && say) hos_log("oot: %s: no heap had room: the game goes on without it (and crashes writing to it)", what);
    *in = got ? h : 0;
    return got;
}
/* (this thread's build, while handed over: its holder, its own heap, the parent, whether the GPU heap went too) */
static _Thread_local struct { uint64_t holder, own, in; int gpu; } rest;
static volatile long rest_n;
/* HOS_GPU_ALLOC_TEST_FILL: at its place, a model's own heap (4 MB at most, not a parent a build was handed), once: all it
   has is taken */
static void test_fill(Ctx *c, uint64_t heap, uint64_t holder, uint64_t lr) {
    static volatile long left = -1, lock;
    static uint64_t at;   /* (the place's return address) */
    static uint64_t filled[64];
    static unsigned filled_n;
    if (__atomic_load_n(&left, __ATOMIC_ACQUIRE) < 0) {
        while (__sync_lock_test_and_set(&lock, 1)) {}
        if (__atomic_load_n(&left, __ATOMIC_RELAXED) < 0) {
            const char *e = getenv("HOS_GPU_ALLOC_TEST_FILL"), *comma = e ? strchr(e, ',') : NULL;
            const long n = e ? atol(e) : 0;
            at = (comma ? strtoull(comma + 1, NULL, 16) : 0x8044f66cULL) + 4;
            __atomic_store_n(&left, n > 0 ? n : 0, __ATOMIC_RELEASE);
        }
        __sync_lock_release(&lock);
    }
    if (__atomic_load_n(&left, __ATOMIC_ACQUIRE) <= 0 || lr != at || !holder || !readable(heap) || rest.holder == holder) return;
    if (recomp_load64(c, holder + 8) != heap || recomp_load64(c, heap + HEAP_SIZE) > (4ULL << 20)) return;
    const uint64_t fn = heap_method(c, heap, VT_TRY_ALLOC);
    if (!fn || !a64_lookup(fn)) return;
    int mine = 1;
    while (__sync_lock_test_and_set(&lock, 1)) {}
    for (unsigned k = 0; k < 64 && k < filled_n; k++)
        if (filled[k] == heap) mine = 0;
    if (mine && __atomic_load_n(&left, __ATOMIC_RELAXED) > 0) {
        __atomic_fetch_sub(&left, 1, __ATOMIC_RELAXED);
        filled[filled_n++ % 64] = heap;
    }
    else mine = 0;
    __sync_lock_release(&lock);
    if (!mine) return;
    long blocks = 0;
    uint64_t bytes = 0;
    for (uint64_t size = 1 << 16; size >= 16; size >>= 1)
        for (int k = 0; k < 4096 && guest_call(c, fn, heap, size, 8, lr); k++) blocks++, bytes += size;
    char where[160];
    describe(c, heap, where, sizeof where);
    hos_log("oot: HOS_GPU_ALLOC_TEST_FILL: %ld blocks, %llu KB, taken and kept: %s is full", blocks,
            (unsigned long long)(bytes >> 10), where);
}
int hos_oot_heap_refuse(Ctx *c, uint64_t heap, uint64_t holder, uint64_t lr) {
    const int site = site_of(lr);
    if (site < 0) return 0;
    test_fill(c, heap, holder, lr);
    return test_fail(SITES[site].kind);
}
void hos_oot_heap_retry(Ctx *c, uint64_t heap, uint64_t size, uint64_t align, uint64_t lr, uint64_t holder) {
    const int site = site_of(lr);
    const char *const what = site < 0 ? "allocation" : SITES[site].what;
    if (!retry_on()) {
        hos_log("oot: %s, %#llx bytes from heap %#llx, failed: not tried again (HOS_GPU_ALLOC_RETRY=0) (lr %#llx)", what,
                (unsigned long long)size, (unsigned long long)heap, (unsigned long long)lr);
        return;
    }
    char where[160];
    const int say = tell();
    if (say) {
        describe(c, heap, where, sizeof where);
        hos_log("oot: %s, %#llx bytes from %s, failed (lr %#llx)", what, (unsigned long long)size, where,
                (unsigned long long)lr);
    }
    const int handover = rest_on() && holder && readable(heap) && recomp_load64(c, holder + 8) == heap;
    const uint64_t own = handover && rest.holder == holder && rest.in == heap ? rest.own : heap;
    const uint64_t whole = handover ? recomp_load64(c, own + HEAP_SIZE) : 0;
    uint64_t in;
    const uint64_t got = in_parents(c, heap, size, align, lr, what, say, whole, handover, &in);
    if (got && site >= 0) count_moved(1 + site, size, say);
    if (got && handover) {
        /* (a parent that ran out in its turn hands the build on: the build's own heap stays the one to put back) */
        if (rest.holder != holder || rest.in != heap) rest.own = heap, rest.gpu = 0;
        recomp_store64(c, holder + 8, in);
        if (recomp_load64(c, holder + 16) == heap) recomp_store64(c, holder + 16, in), rest.gpu = 1;
        rest.holder = holder, rest.in = in;
        const long n = __atomic_add_fetch(&rest_n, 1, __ATOMIC_RELAXED);
        if (say || n % 16 == 0) {
            describe(c, in, where, sizeof where);
            hos_log("oot: %s: the rest of the build takes its memory%s from %s (%ld builds so far)", what,
                    rest.gpu ? ", the GPU's too," : "", where, n);
        }
    }
    c->x[0] = got;
}
/* f_804566e0 reads its heap's free size twice (x0 the heap, x8 its getFreeSize, both just loaded through the holder): a
   build handed to a parent has its own heap read, the first time (0x80456928; the hand-over can only be the +200
   buffer's) with the holder left as it is, the last time (0x80457188) with its own heap back in the holder too */
void hos_oot_heap_rest_own(Ctx *c, uint64_t holder) {
    if (!rest.holder || rest.holder != holder) return;   /* (no build of this thread was handed over, or not this one) */
    c->x[0] = rest.own;
    c->x[8] = recomp_load64(c, recomp_load64(c, rest.own) + VT_FREE_SIZE);
}
void hos_oot_heap_rest_end(Ctx *c, uint64_t holder) {
    if (!rest.holder || rest.holder != holder) return;
    const uint64_t own = rest.own, in = rest.in;
    rest.holder = 0;
    if (rest.gpu && recomp_load64(c, holder + 16) == in) recomp_store64(c, holder + 16, own);
    if (recomp_load64(c, holder + 8) != in) return;
    recomp_store64(c, holder + 8, own);
    c->x[0] = own;
    c->x[8] = recomp_load64(c, recomp_load64(c, own) + VT_FREE_SIZE);
}

/* tests/test_native_fp.py's driver: nx2/nativefp.py (ProjectReLink's native floating point, ported) against the exact
   bodies recomp_fpe_* (pure integer code: Arm's result and flags), built against the real a64.h with the a64_suyu.h /
   a64_suyu.c / a64_fpx.h the generators write (A64_NATIVE_FP=1, A64_FPX_EASY=1).

   nativefp_test easy <n> <seed>     A64_FPX_EASY: the binary32 FADD / FSUB / FMUL wrappers (a64_fpx_add32_add32,
                                     a64_fpx_sub32_sub32, a64_fpx_mul32_fma32 with the product's signed zero as the addend),
                                     random operands weighted to the special classes, random FPCR / FPSR (gate open and
                                     closed), and a sweep of special pairs: result AND FPSR equal to the body's.
   nativefp_test native <n> <seed>   A64_NATIVE_FP's scalar helpers (a64_fpx_nat_*, every shape with a native form),
                                     its 2/4-lane FADD / FSUB / FMUL (a64_vfpx_nat_*), its conversions (a64_nat_*) and, at
                                     x86-64-v3, the FP blocks' native ops (a64_bk_n*, a lane kept when the op says not bad),
                                     with MXCSR's FTZ and DAZ set from FPCR.FZ as host/hos_thread.c sets them: the value
                                     equal to the body's (FPSR not compared: a native op raises no flag), but under FZ a
                                     result the body flushes to a zero that the host rounded up to the smallest normal
                                     (counted: "edge"; it must stay rare).
   nativefp_test nomxcsr <n> <seed>  the same as native with MXCSR left at the host's default: must find mismatches (exit 1),
                                     or the test would not show that FTZ and DAZ are needed.
   Exit 0: pass. 1: a mismatch. */
#include "a64.h"
#include <stdio.h>
#include <stdlib.h>
#include <xmmintrin.h>
#ifndef A64_BK
#define A64_BK 0   /* (no FP blocks in this kit's lift) */
#endif
#if RECOMP_FPX_HOST != 2
#error "x86-64 with SSE2 only"
#endif

void hos_fpcr_follow(void) {}   /* (the native lift's constructor calls it: host/hos_thread.c) */

static uint64_t rs;
static uint64_t rnd(void) { rs ^= rs << 13; rs ^= rs >> 7; rs ^= rs << 17; return rs; }
static uint32_t r32(void) { return (uint32_t)(rnd() >> 16); }
static uint32_t rbelow(uint32_t n) { return (uint32_t)(((rnd() >> 32) * n) >> 32); }
static uint32_t mkf(uint32_t s, int e, uint32_t frac) { return (s << 31) | ((uint32_t)e << 23) | (frac & 0x7fffff); }
static uint64_t mkd(uint64_t s, int e, uint64_t frac) { return (s << 63) | ((uint64_t)e << 52) | (frac & UINT64_C(0xfffffffffffff)); }
static float F(uint32_t x) { float f; memcpy(&f, &x, 4); return f; }
static uint32_t B(float f) { uint32_t x; memcpy(&x, &f, 4); return x; }

static uint32_t op32(void) {
    const uint32_t s = r32() & 1;
    switch (rbelow(22)) {
    case 0: return s << 31;
    case 1: return mkf(s, 0, r32() | 1);                                  /* subnormal */
    case 2: return mkf(s, 0, rbelow(4) + 1);
    case 3: return mkf(s, 1 + rbelow(3), r32());                          /* near the smallest normal */
    case 4: return mkf(s, 254 - rbelow(3), r32());                        /* near the largest */
    case 5: case 6: return mkf(s, 255, 0);                                /* inf */
    case 7: return 0x7fc12345u;                                           /* quiet NaN with payload */
    case 8: return mkf(s, 255, 0x400000 | r32());                         /* quiet NaN */
    case 9: return mkf(s, 255, (r32() & 0x3fffff) | (1u << rbelow(22)));  /* signalling NaN */
    case 10: case 11: return mkf(s, 60 + rbelow(10), r32());              /* products near the normal range's bottom */
    case 12: return mkf(s, 0x7f, rbelow(3) ? 0 : r32());                  /* 1.0, -1.0 */
    default: return mkf(s, 1 + rbelow(254), r32());
    }
}
static uint64_t op64(void) {
    const uint64_t s = r32() & 1;
    switch (rbelow(22)) {
    case 0: return s << 63;
    case 1: return mkd(s, 0, rnd() | 1);
    case 2: return mkd(s, 0, rbelow(4) + 1);
    case 3: return mkd(s, 1 + rbelow(3), rnd());
    case 4: return mkd(s, 2046 - rbelow(3), rnd());
    case 5: case 6: return mkd(s, 2047, 0);
    case 7: return UINT64_C(0x7ff8000000000000);
    case 8: return mkd(s, 2047, UINT64_C(0x8000000000000) | rnd());
    case 9: return mkd(s, 2047, (rnd() & UINT64_C(0x7ffffffffffff)) | ((uint64_t)1 << rbelow(51)));
    case 10: case 11: return mkd(s, 500 + rbelow(30), rnd());
    case 12: return mkd(s, 1023, 0);
    default: return mkd(s, 1 + rbelow(2046), rnd());
    }
}
/* the third operand of a multiply-add: often near the negated product (cancellations, tiny results) */
static uint32_t addend32(uint32_t a, uint32_t b) {
    switch (rbelow(6)) {
    case 0: return B(-(float)((double)F(a) * (double)F(b)));
    case 1: return B(-(float)((double)F(a) * (double)F(b))) + (uint32_t)((int)rbelow(5) - 2);
    default: return op32();
    }
}
static void gen_state(uint64_t *fpcr, uint64_t *fpsr, int native) {
    uint64_t cr = 0, sr = 0;
    if (rbelow(2)) cr |= 1u << 24;                        /* FZ */
    if (rbelow(native ? 30 : 12) == 0) cr |= 1u << 25;    /* DN (gate closed) */
    if (rbelow(native ? 30 : 12) == 0) cr |= (uint64_t)rbelow(4) << 22;
    if (rbelow(200) == 0) cr |= RECOMP_FPX_INHIBIT;
    static const uint32_t bits[6] = {1, 2, 4, 8, 16, 128};
    if (rbelow(3) == 0) sr = 0x9f;
    else for (int k = 0; k < 6; k++) if (k == 4 ? rbelow(10) != 0 : rbelow(3) != 0) sr |= bits[k];
    *fpcr = cr;
    *fpsr = sr;
}

static unsigned long long checks, mismatches, edges, kept_bad;
static int report_left = 20;
static int mxcsr_follow = 1;
static unsigned default_csr;
static void csr_for(uint64_t fpcr) {
    _mm_setcsr(mxcsr_follow && (fpcr & (1u << 24)) ? (default_csr | 0x8040u) : (default_csr & ~0x8040u));
}
static void mism(const char *what, uint64_t cr, uint64_t sr, uint64_t a, uint64_t b, uint64_t z, uint64_t want, uint64_t wsr,
                 uint64_t got, uint64_t gsr) {
    mismatches++;
    if (report_left-- > 0)
        printf("MISMATCH %s fpcr %#llx fpsr %#llx a %#llx b %#llx z %#llx: body %#llx fpsr %#llx, got %#llx fpsr %#llx\n", what,
               (unsigned long long)cr, (unsigned long long)sr, (unsigned long long)a, (unsigned long long)b,
               (unsigned long long)z, (unsigned long long)want, (unsigned long long)wsr, (unsigned long long)got,
               (unsigned long long)gsr);
}
/* a native value against the body's: equal, or under FZ the body's flushed zero where the host rounded up to the smallest
   normal (same sign) */
static int native_ok(int w64, uint64_t cr, uint64_t want, uint64_t got) {
    if (want == got) return 1;
    if (!(cr & (1u << 24))) return 0;
    const uint64_t sign = w64 ? UINT64_C(1) << 63 : UINT64_C(1) << 31;
    const uint64_t minn = w64 ? UINT64_C(1) << 52 : UINT64_C(1) << 23;
    if ((want & ~sign) == 0 && (got & ~sign) == minn && (want & sign) == (got & sign)) { edges++; return 1; }
    return 0;
}

/* ---- A64_FPX_EASY ---- */
static void easy_one(int op, uint64_t cr, uint64_t sr, uint32_t a, uint32_t b) {
    Ctx ref, got;
    memset(&ref, 0, sizeof ref); ref.fpcr = cr; ref.fpsr = sr; got = ref;
    uint64_t w, v;
    const uint32_t z = (a ^ b) & 0x80000000u;
    const char *name;
    if (op == 0) { name = "fadd"; w = recomp_fpe_add32(&ref, a, b); v = a64_fpx_add32_add32(&got, a, b); }
    else if (op == 1) { name = "fsub"; w = recomp_fpe_sub32(&ref, a, b); v = a64_fpx_sub32_sub32(&got, a, b); }
    else { name = "fmul"; w = recomp_fpe_fma32(&ref, a, b, z); v = a64_fpx_mul32_fma32(&got, a, b, z); }
    checks++;
    if (w != v || ref.fpsr != got.fpsr) mism(name, cr, sr, a, b, z, w, ref.fpsr, v, got.fpsr);
}
static int run_easy(unsigned long long n) {
    for (unsigned long long i = 0; i < n; i++) {
        uint64_t cr, sr;
        gen_state(&cr, &sr, 0);
        easy_one((int)rbelow(3), cr, sr, op32(), op32());
    }
    static const uint32_t sp[] = {0, 0x80000000u, 1, 0x80000001u, 0x007fffffu, 0x00800000u, 0x80800000u, 0x00800001u,
                                  0x3f800000u, 0xbf800000u, 0x7f7fffffu, 0xff7fffffu, 0x7f800000u, 0xff800000u, 0x7fc00000u,
                                  0xffc00000u, 0x7fc12345u, 0x7f800001u, 0xff812345u, 0x1f800000u, 0x1f000000u, 0x20000000u,
                                  0x5f800000u, 0x60000000u, 0x00400000u, 0x80400000u, 0x34000000u, 0x0c000000u};
    const int ns = (int)(sizeof sp / sizeof sp[0]);
    static const uint64_t crs[2] = {0, 1u << 24}, srs[3] = {0x10, 0x9f, 0x18};
    for (int ci = 0; ci < 2; ci++)
        for (int si = 0; si < 3; si++)
            for (int i = 0; i < ns; i++)
                for (int j = 0; j < ns; j++)
                    for (int op = 0; op < 3; op++) easy_one(op, crs[ci], srs[si], sp[i], sp[j]);
    printf("easy: %llu checks, %llu mismatches\n", checks, mismatches);
    return mismatches ? 1 : 0;
}

/* ---- A64_NATIVE_FP ---- */
/* (and the exact wrapper the other functions call, under the same MXCSR: its value must stay the body's exactly) */
#define SCALAR(name, w64, body, native, exact) do { \
    Ctx ref, got, ex; \
    memset(&ref, 0, sizeof ref); ref.fpcr = cr; ref.fpsr = sr; got = ref; ex = ref; \
    _mm_setcsr(default_csr); \
    const uint64_t w_ = (body); \
    csr_for(cr); \
    const uint64_t v_ = (native); \
    const uint64_t x_ = (exact); \
    _mm_setcsr(default_csr); \
    checks += 2; \
    if (!native_ok(w64, cr, w_, v_)) mism(name, cr, sr, a, b, z, w_, ref.fpsr, v_, got.fpsr); \
    if (x_ != w_) mism(name " (exact wrapper)", cr, sr, a, b, z, w_, ref.fpsr, x_, ex.fpsr); \
} while (0)

/* products whose exact value sits just below the smallest normal, where rounding may reach it: the FZ edge */
static void edge32(uint64_t *a, uint64_t *b) {
    const double x = 1.0 + (double)(r32() & 0xffffff) / 16777216.0, t = 0x1p-126 * (1.0 - (double)(rbelow(64) + 1) * 0x1p-30);
    const float fa = (float)x, fb = (float)(t / (double)fa);
    *a = B(fa); *b = B(fb);
    if (r32() & 1) *a ^= 0x80000000u;
}
static void native_scalar(void) {
    uint64_t cr, sr, a, b, z;
    gen_state(&cr, &sr, 1);
    if (rbelow(8) == 0) {   /* (the edge, FZ set and the gate open) */
        cr = 1u << 24;
        edge32(&a, &b);
        z = (a ^ b) & 0x80000000u;
        SCALAR("mul32 (edge)", 0, recomp_fpe_fma32(&ref, a, b, z), a64_fpx_nat_mul32_fma32(&got, a, b, z), a64_fpx_mul32_fma32(&ex, a, b, z));
        return;
    }
    switch (rbelow(12)) {
    case 0: a = op32(); b = op32(); z = 0;
        SCALAR("add32", 0, recomp_fpe_add32(&ref, a, b), a64_fpx_nat_add32_add32(&got, a, b), a64_fpx_add32_add32(&ex, a, b)); break;
    case 1: a = op32(); b = op32(); z = 0;
        SCALAR("sub32", 0, recomp_fpe_sub32(&ref, a, b), a64_fpx_nat_sub32_sub32(&got, a, b), a64_fpx_sub32_sub32(&ex, a, b)); break;
    case 2: a = op32(); b = op32(); z = (a ^ b) & 0x80000000u;
        SCALAR("mul32", 0, recomp_fpe_fma32(&ref, a, b, z), a64_fpx_nat_mul32_fma32(&got, a, b, z), a64_fpx_mul32_fma32(&ex, a, b, z)); break;
    case 3: a = op32(); b = op32(); z = 0;
        SCALAR("div32", 0, recomp_fpe_div32(&ref, a, b), a64_fpx_nat_div32_div32(&got, a, b), a64_fpx_div32_div32(&ex, a, b)); break;
    case 4: a = op32(); b = 0; z = 0;
        SCALAR("sqrt32", 0, recomp_fpe_sqrt32(&ref, a), a64_fpx_nat_sqrt32_sqrt32(&got, a), a64_fpx_sqrt32_sqrt32(&ex, a)); break;
    case 5: a = op32(); b = op32(); z = addend32((uint32_t)a, (uint32_t)b);
        SCALAR("fma32", 0, recomp_fpe_fma32(&ref, a, b, z), a64_fpx_nat_fma32_fma32(&got, a, b, z), a64_fpx_fma32_fma32(&ex, a, b, z)); break;
    case 6: a = op64(); b = op64(); z = 0;
        SCALAR("add64", 1, recomp_fpe_add64(&ref, a, b), a64_fpx_nat_add64_add64(&got, a, b), a64_fpx_add64_add64(&ex, a, b)); break;
    case 7: a = op64(); b = op64(); z = 0;
        SCALAR("sub64", 1, recomp_fpe_sub64(&ref, a, b), a64_fpx_nat_sub64_sub64(&got, a, b), a64_fpx_sub64_sub64(&ex, a, b)); break;
    case 8: a = op64(); b = op64(); z = (a ^ b) & (UINT64_C(1) << 63);
        SCALAR("mul64", 1, recomp_fpe_fma64(&ref, a, b, z), a64_fpx_nat_mul64_fma64(&got, a, b, z), a64_fpx_mul64_fma64(&ex, a, b, z)); break;
    case 9: a = op64(); b = op64(); z = 0;
        SCALAR("div64", 1, recomp_fpe_div64(&ref, a, b), a64_fpx_nat_div64_div64(&got, a, b), a64_fpx_div64_div64(&ex, a, b)); break;
    case 10: a = op64(); b = 0; z = 0;
        SCALAR("sqrt64", 1, recomp_fpe_sqrt64(&ref, a), a64_fpx_nat_sqrt64_sqrt64(&got, a), a64_fpx_sqrt64_sqrt64(&ex, a)); break;
    default: a = op64(); b = op64(); z = op64();
        SCALAR("fma64", 1, recomp_fpe_fma64(&ref, a, b, z), a64_fpx_nat_fma64_fma64(&got, a, b, z), a64_fpx_fma64_fma64(&ex, a, b, z)); break;
    }
}
static void native_vector(void) {
    uint64_t cr, sr;
    gen_state(&cr, &sr, 1);
    const int op = (int)rbelow(3), k = op == 2 ? 4 : (rbelow(2) ? 4 : 2);
    uint32_t a[4], b[4], want[4] = {0, 0, 0, 0}, got4[4];
    for (int j = 0; j < 4; j++) { a[j] = op32(); b[j] = op32(); }
    Ctx ref, got;
    memset(&ref, 0, sizeof ref); ref.fpcr = cr; ref.fpsr = sr; got = ref;
    _mm_setcsr(default_csr);
    for (int j = 0; j < k; j++)
        want[j] = (uint32_t)(op == 0 ? recomp_fpe_add32(&ref, a[j], b[j]) : op == 1 ? recomp_fpe_sub32(&ref, a[j], b[j])
                                       : recomp_fpe_fma32(&ref, a[j], b[j], (a[j] ^ b[j]) & 0x80000000u));
    uint64_t d[2], n[2], m[2];
    memcpy(n, a, 16); memcpy(m, b, 16);
    csr_for(cr);
    if (op == 0) a64_vfpx_nat_add32(&got, d, n, m, k);
    else if (op == 1) a64_vfpx_nat_sub32(&got, d, n, m, k);
    else a64_vfpx_nat_mul32(&got, d, n, m, k);
    _mm_setcsr(default_csr);
    memcpy(got4, d, 16);
    for (int j = 0; j < 4; j++) {
        checks++;
        if (!native_ok(0, cr, want[j], got4[j])) mism(op == 0 ? "vadd" : op == 1 ? "vsub" : "vmul", cr, sr, a[j], b[j], (uint64_t)j, want[j], ref.fpsr, got4[j], got.fpsr);
    }
}
static void native_conv(void) {
    uint64_t cr, sr;
    gen_state(&cr, &sr, 1);
    const unsigned fpb = rbelow(2) ? 32 : 64, ib = rbelow(2) ? 32 : 64, sg = rbelow(2);
    uint64_t want, got, f1 = sr, f2 = sr, x;
    if (rbelow(2)) {   /* FCVTZ* (and the other rounding modes, which the native helper gives to the body) */
        const unsigned rm = rbelow(4) ? 3 : rbelow(3);
        x = fpb == 32 ? (uint64_t)op32() : op64();
        if (rbelow(2)) {   /* (values in or near an integer's range, so the host's conversion is taken) */
            const int64_t iv = (int64_t)rnd() >> rbelow(64);
            const double fr = (double)iv + (double)(int)rbelow(8) / 8.0;
            if (fpb == 32) x = B((float)fr); else memcpy(&x, &fr, 8);
        }
        _mm_setcsr(default_csr);
        want = recomp_fp_to_int(x, fpb, ib, sg, rm, cr, &f1);
        csr_for(cr);
        got = a64_nat_fp_to_int(x, fpb, ib, sg, rm, cr, &f2);
        _mm_setcsr(default_csr);
        checks++;
        if (want != got) mism("fcvtz", cr, sr, x, fpb * 1000 + ib, sg * 10 + rm, want, f1, got, f2);
    } else {           /* SCVTF / UCVTF */
        const unsigned fb = rbelow(4) ? 0 : rbelow(ib);
        x = rbelow(3) ? rnd() >> rbelow(64) : (uint64_t)(int64_t)(int32_t)r32();
        _mm_setcsr(default_csr);
        want = recomp_fixed_to_fp(x, fpb, ib, fb, sg, cr, &f1);
        csr_for(cr);
        got = a64_nat_fixed_to_fp(x, fpb, ib, fb, sg, cr, &f2);
        _mm_setcsr(default_csr);
        checks++;
        if (want != got) mism("cvtf", cr, sr, x, fpb * 1000 + ib, sg * 100 + fb, want, f1, got, f2);
    }
}
#if A64_BK
static void native_block(void) {
    uint64_t cr, sr;
    gen_state(&cr, &sr, 1);
    cr &= (1u << 24);   /* (a block runs under its gate: FPCR's FZ only) */
    const int op = (int)rbelow(10);
    uint32_t a[4], b[4], w[4], want[4] = {0, 0, 0, 0}, got4[4];
    for (int j = 0; j < 4; j++) { a[j] = op32(); b[j] = op32(); w[j] = rbelow(2) ? addend32(a[j], b[j]) : op32(); }
    Ctx ref;
    memset(&ref, 0, sizeof ref); ref.fpcr = cr; ref.fpsr = sr;
    const int lanes = op >= 4 ? 1 : 4;
    _mm_setcsr(default_csr);
    for (int j = 0; j < lanes; j++) {
        switch (op) {
        case 0: case 4: want[j] = (uint32_t)recomp_fpe_add32(&ref, a[j], b[j]); break;
        case 1: case 5: want[j] = (uint32_t)recomp_fpe_sub32(&ref, a[j], b[j]); break;
        case 2: case 6: want[j] = (uint32_t)recomp_fpe_fma32(&ref, a[j], b[j], (a[j] ^ b[j]) & 0x80000000u); break;
        case 3: case 8: want[j] = (uint32_t)recomp_fpe_fma32(&ref, a[j], b[j], w[j]); break;
        case 7: want[j] = (uint32_t)recomp_fpe_div32(&ref, a[j], b[j]); break;
        default: want[j] = (uint32_t)recomp_fpe_sqrt32(&ref, a[j]); break;
        }
    }
    __m128i va, vb, vw, bad = _mm_setzero_si128(), r;
    memcpy(&va, a, 16); memcpy(&vb, b, 16); memcpy(&vw, w, 16);
    const __m128i fzm = _mm_set1_epi32((cr & (1u << 24)) ? -1 : 0);
    csr_for(cr);
    switch (op) {
    case 0: r = a64_bk_nvadd(&bad, fzm, va, vb, A64_BK_L4); break;
    case 1: r = a64_bk_nvsub(&bad, fzm, va, vb, A64_BK_L4); break;
    case 2: r = a64_bk_nvmul(&bad, fzm, va, vb, A64_BK_L4); break;
    case 3: r = a64_bk_nvfma(&bad, fzm, va, vb, vw, A64_BK_L4); break;
    case 4: r = a64_bk_nsadd(&bad, fzm, va, vb); break;
    case 5: r = a64_bk_nssub(&bad, fzm, va, vb); break;
    case 6: r = a64_bk_nsmul(&bad, fzm, va, vb); break;
    case 7: r = a64_bk_nsdiv(&bad, fzm, va, vb); break;
    case 8: r = a64_bk_nsfma(&bad, fzm, va, vb, vw); break;
    default: r = a64_bk_nssqrt(&bad, fzm, va); break;
    }
    _mm_setcsr(default_csr);
    if (_mm_movemask_epi8(bad)) { kept_bad++; return; }   /* (the block's fallback runs: the per-op helpers, checked above) */
    memcpy(got4, &r, 16);
    for (int j = 0; j < 4; j++) {
        checks++;
        if (!native_ok(0, cr, want[j], got4[j])) mism("block", cr, sr, a[j], b[j], (uint64_t)(op * 10 + j), want[j], ref.fpsr, got4[j], 0);
    }
}
#endif
static int run_native(unsigned long long n) {
    for (unsigned long long i = 0; i < n; i++) {
        native_scalar();
        native_vector();
        native_conv();
#if A64_BK
        native_block();
#endif
    }
    printf("native%s: %llu checks, %llu mismatches, %llu at the smallest normal's edge under FZ, %llu blocks sent to their "
           "fallback%s\n", mxcsr_follow ? "" : " (MXCSR left at its default)", checks, mismatches, edges, kept_bad,
           A64_BK ? "" : " (no FP blocks at this -march)");
    return mismatches ? 1 : 0;
}

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    default_csr = _mm_getcsr() & ~0x8040u;
    const unsigned long long n = argc > 2 ? strtoull(argv[2], NULL, 10) : 100000;
    rs = argc > 3 ? strtoull(argv[3], NULL, 10) : 1;
    if (!rs) rs = 1;
    if (!strcmp(argv[1], "easy")) return run_easy(n);
    if (!strcmp(argv[1], "native")) return run_native(n);
    if (!strcmp(argv[1], "nomxcsr")) { mxcsr_follow = 0; return run_native(n); }
    return 2;
}

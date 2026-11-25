# Area 3: the game's CPU side (lift, FP, profile, native framework, game speed, threads, compile flags)

Survey of HeyListen (engine/ subtree from Hookshot a2e65052) against our tree (amd-fix-sharkiix-version). Read only.

## Facts that decide most of the ranking

1. **Our lifter is HeyListen's starting point, unchanged.** `third_party/a64-kit/lift/a64_lift.py` has had no commit in our
   tree since a2e65052 (1848 lines). HeyListen's lift work is a 536-line diff on that same file, plus a new `a64_block.py`
   (906 lines) and 46 lines in `a64_rtgen.py`. So the patches apply cleanly as text. But the folder is a vendored part with
   a `tree-sha256` in `PROVENANCE.md` (`scripts/check_third_party.py`, AGENTS.md: "a fix goes outside them"). A port either
   updates PROVENANCE and its hash (a local decision) or wraps the switches from `nx2/`.
2. **A changed lift needs its own PGO profile.** HeyListen measured this several times (TICK-040/041/045): if the lifted
   code changes and the profile does not, the game **loses 4-5 fps**. Their profile (`profile/hookshot_pieces.prof`) will
   **not** fit our lift. HeyListen kept **loop-header polls** (Sync 10 reverted upstream's back-edge polls, and their
   `nx2/rtgen.py` diff removes `a64_poll_cur`). Our tree has upstream's **back-edge polls**. Polls are branches, and clang's
   profile hash counts branches. Any lift switch therefore means recording our own profile: an `RX_PGO=gen` build (HeyListen:
   617-822 s, ~22 GB summed), `HOS_PGO` runs of 3 scenes (72-106 s each), then `llvm-profdata merge` 6:1 with upstream's.
   We already have all of that tooling (`host/pgo_rt.c`, `HOS_PGO`, `make_game.py` copies `work/hookshot_pieces.prof`).
3. **Our randomizer and fps patches match lifted text, and HeyListen's lift switches rewrite that text.**
   `nx2/oot_patches.py` finds its sites by literal lifted-C strings, FP ones included:
   - `STEP_OLD` = `_v=a64_fpx_div32_div32(...)`, the real-time step;
   - `WHOLE_SITES` / `SOLVER_OLD` = `recomp_fp_to_int(c->vreg[0][0]...)`;
   - `SOUND_OLD`, a vector load into `vreg[0]`;
   - `TEXT_ADD` and `CAMERA_SPEED_RETURN`, which multiply `vreg[0]`.

   Seven patched functions are in `work/hot_funcs.txt`, where `hot_text()` and the block lift act: f_8005ed00, f_802f1380,
   f_8030a320 / f_80312220 (the model swap), f_804e48c0 (the view loop), f_80644c80 (camera speed and mouse look),
   f_82c415e0 (the move/warp). `oot_wide.py` adds f_802a46e0.
   - If a switch changes an anchor, the patch **quietly does not apply**: the fps fix, camera speed or a rando patch is lost.
   - `A64_FPX_BLOCK` is worse. It keeps the original per-op code as the fallback and adds a speculative XMM copy. A patch
     that lands on the fallback text can be **skipped by the fast path** whenever the block's keep test passes.
   - HeyListen never had this problem: their `oot_patches.py` is a2e65052's plus job order. Their step, movie and whole
     hooks come from `nx2/hl_gates.py`, which is hash-gated and leaves a function alone, with a warning, when its text differs.
4. **How HeyListen checked correctness.**
   - Lift switches: differential tests on synthetic AArch64 that compare the whole Ctx and guest memory, old against new
     lowering, with FPCR modes, NaNs, subnormals and midpoints:
     - `test_vfpx_elem` 40 M cases, 0 differences;
     - `test_fpx_slowpath` 3 M a march, 40 M by hand, 0 mismatches;
     - `test_fpx_xmm` 1 M runs, 0 mismatches;
     - `test_fpx_block` 44 sequences x 3 switch sets, 2 M runs, 0 mismatches.
   - Seeded bugs ("teeth") make each test fail.
   - In the game: `HOS_SPEED_LOG` 59.98-60.04, screenshots alike, saves byte-identical after every run.
   - Native modules: live differential checks:
     - `HL_MATH_CHECK`: 0 mismatches over 1.8 M support and 0.18 M relxf calls, plus 1.01 M u3 calls;
     - `HL_GFX_*_CHECK`: 0 over 7 M and 19.4 M NVN calls;
     - `HOS_NR_*=diff`: 14.9 M checks, 0 differences.

---

## Candidates, best first

### 1. A freed region's discard gives up the virtual core (stutter on arriving in an area). Port first.
- **What:** `hos_region_free` gives the thread's virtual core up (`hos_vcore_away` / `hos_vcore_back`) around
  `discard_pages`. A big `DiscardVirtualMemory` on an area change held the core, and the module workers pinned to it
  stalled. HeyListen dc25c9c6 (upstream Hookshot #2924 by NotRexed); `host/hos_mem.c` (+15 lines),
  `tests/test_vcore_region_free.py`.
- **Measured:** Windows 11, RTX 3060 Ti, Ryzen 5 5600X, Death Mountain Trail arrival, 5 pairs:

  | | Core kept (as before) | Core given up (this change) |
  |---|---|---|
  | Frames over 50 ms | 13 / 1 / 1 / 0 / 2 | all 0 |
  | Longest frame | 34-140 ms | 32-42 ms |
  | fps | 54.8-59.1 | 59.2-60.0 |

  Water Temple: no change. Steam Deck: no change.
- **Ours:** not present (`host/hos_mem.c:186` discards while holding the core; no `HOS_DISCARD_HOLDS_CORE`).
- **Hardware:** none specific; helps most where cores are few. `HOS_DISCARD_HOLDS_CORE=1` restores the old behaviour.
- **Port:** about 15 lines in `host/hos_mem.c`, plus the test. It touches no lift, no rando, no guest state.
- **Risk:** low (the region is off the list and the lock is released first; the same pattern as `read_at`). **First.**

### 2. A starved thread gets its virtual core after 1 s (no "ran without a core after 2000 ms"). Port first.
- **What:** a game thread that waits more than `HOS_VCORE_STARVE_US` (1 s) for its core goes first at the next release
  and asks the holder to yield. Before, better threads kept winning the core until the 2 s escape ran it beside the
  holder. HeyListen 0ab1b72c (Longshot/magicbean, mooki); `host/hos_thread.c` (+46/-17), `test_vcore_escape.py`.
- **Measured:** Linux, i9-13900K / RTX 4090, Kokiri save loads, 10 vs 10 starts:
  - escapes in 0 of 10 starts against 4 of 10;
  - longest core wait at most 1.002 s against 2.0 s.

  Not measured on Windows. The same escape line is in an RX 9070 XT player's log and in 5700X3D rows.
- **Ours:** not present (no `vc_starved`). We do have the escape-related picks c8b9a9f0, 26c12b0d, d522ec0e, bce1476c.
- **Port:** small. Our `hos_thread.c` differs from a2e65052 by 735 lines, so expect a hand merge in `vc_acquire`, the
  waiter order and the stats line. No lift, no rando.
- **Risk:** medium-low. It changes scheduling order only after 1 s of starvation, and the switch `=0` restores the old
  rule. Run the save-load and teleport checks. **First (after 1).**

### 3. Record a play profile on OUR lift, and first check how stale the shipped one is. Do this before any lift change.
- **What:** not a HeyListen commit but their main lesson (TICK-040/041/045). They built a profile on their own lift: an
  `RX_PGO=gen` build, three scenes with `HOS_PGO`, merged 6:1 with upstream's.
- **Measured:**
  - The profile alone (B, base lift) was **inside the spread** against upstream's matching profile: 77.2 vs 75.3 standing,
    67.5 vs 68.1 walking.
  - A **mismatched** profile costs 4-5 fps.
- **Ours:**
  - `work/hookshot_pieces.prof`, `hot_funcs.txt` and `hot_order.txt` are upstream's (Nov 9, 6.5 MB).
  - The randomizer and our cosmetics, camera and mouse patches change 7 hot functions; how many profile records still
    match is unknown.
  - `build.py` compiles the hot pieces with `-Wno-everything`, which hides clang's "profile data may be out of date: of N
    functions, M have mismatched data" warning.
- **Cheap first step:** compile one or two `code_hot_*.c` once by hand with `-Wprofile-instr-out-of-date` to count the
  mismatches. If the count is large, record a profile on our lift with the existing tooling. This is also a prerequisite
  for candidates 4 and 7.
- **Risk:** none to behaviour (the profile changes code layout and inlining only). The cost is one long gen build and
  ~3 short play runs.

### 4. Three FP lift switches, `A64_VFPX_ELEM` + `A64_FPX_SLOWPATH` + `A64_FPX_FMA3`, with their own profile. Later.
- **What:**
  - `VFPX_ELEM` (TICK-041, c3a0294e): NEON FMUL/FMLA/FMLS by element and vector FMLA become SSE/AVX2 ops instead of
    per-lane loops through the host stack. HeyListen measured ~16-19% of the guest samples in those loops.
  - `SLOWPATH` (TICK-044, 385f755a): a per-lane fallback for quiet-NaN lanes, quiet-NaN and FDIV-infinity rescues, and a
    table fast path for FRSQRTE/FRECPE. Exact bodies drop from 3.6 M to 0.09 M calls a second.
  - `FMA3`: the scalar binary32 FMA by hardware fmaf.
  - On by default since TICK-045 (2a359a03).
- **Measured** (TICK-045, Ryzen 7 7800X3D + RTX 5070, 6 interleaved runs, each side with its own profile):
  - kokiri-idle 75.3 -> 78.0;
  - castle-move 68.1 -> 72.9;
  - hyrule-walk 70.9 -> 74.4 fps.

  That is +2.7 standing and +4.8 walking, beyond the spread. Each switch alone was inside the spread. `HOS_SPEED_LOG`
  was 60, shots alike, saves identical.
- **Ours:** none of them (no `lift_switch` in our a64_lift.py).
- **Hardware:** needs x86-64-v3 (AVX2/FMA); our default `-march` is x86-64-v3, falling back to v2 on older CPUs.
  HeyListen tested v3 and v2 bit-exact. Not AMD/NVIDIA dependent; the gain is CPU-side, and the owner's CPU is unknown.
- **Port:** about 300 lines of `a64_lift.py` and `a64_rtgen.py` from 2a359a03 / 385f755a / c3a0294e, plus the tests
  `test_vfpx_elem.py`, `test_fpx_slowpath.py` and their C fixtures. Then the PROVENANCE hash, or an nx2 wrapper.
- **Collision:**
  - `SLOWPATH` and `FMA3` change only the generated header and runtime (`a64_fpx.h`, `recomp_fp_estimate`). No lifted
    function text changes, so no oot_patches anchor moves.
  - `VFPX_ELEM` rewrites vector FMLA/FMUL-by-element loops in every function. None of our anchors contains those loops,
    but check it: compare the "applied" counts that `oot_patches.apply` prints before and after, every site (step, whole,
    solver, sound, camera, text, rando).
  - Needs candidate 3's profile recorded on the new lift, or it loses.
- **Risk:** low for correctness (bit-exact by test); medium for effort. **Later**, once candidate 3 has shown we can make
  a profile.

### 5. Hold movie pictures that run ahead of the clock above 60 fps. Port later (small).
- **What:** `nn_video.c dec_acquire`: a picture more than 8 ms ahead of the movie's clock is not handed out; the buffer
  gets the last picture again. Above 60 fps the game takes a picture each frame, so the movie ended early while its sound
  went on. HeyListen 8e5a1a77 (+34 lines). `HOS_VIDEO_NO_HOLD=1` turns it off.
- **Measured:** main PC at ~350 fps: pictures were 2.7 s ahead by the movie's end before, within 0.02 s after.
- **Ours:** we have the catch-up (skip behind) and `HOS_FPS_MOVIE` (cue timing), but no hold for early pictures.
- **Port:** small and host-only. Our nn_video.c differs, so merge by hand around `clock_pts`. Rando: none (movies are
  mostly skipped in the rando).
- **Risk:** low. **Later**, cheap.

### 6. `HOS_BG_THROTTLE`: OoT's OptimizeChangeBank thread runs 300 us, then sleeps 3 ms. Port later, and measure.
- **What:** in `hos_vcore_checkpoint`, the OptimizeChangeBank thread gives up its core and sleeps after 300 us of running.
  It burned 35-44% of a logical processor and slowed whatever ran on its SMT sibling up to 1.7x. HeyListen sprint 5
  (2895ec0a); `host/hos_thread.c` about 30 lines. On by default there.
- **Measured:** the thread's CPU went from 35-44% to 5%. Its fps effect was only measured inside the sprint-5 bundle
  (+4 fps for the whole bundle). Alone: unmeasured.
- **Ours:** we already run it at `THREAD_PRIORITY_LOWEST` (`hos_thread.c:1106`, `HOS_OCB_NORMAL`; RX 6600 + 5600G went
  from 17-20 to 21-28 fps). The throttle stacks on that.
- **Collision:** the same thread whose full-heap allocations we retry (`host/oot_heap_retry.c`). Slower bank rebuilds
  could delay model/material changes after an area change, and with them cosmetics and model swaps. Watch for pop-in.
- **Risk:** low-medium. **Later**, as an A/B on the owner's CPU.

### 7. The block lift `A64_FPX_BLOCK`: straight-line FP runs as speculative XMM blocks. Later, and only with anchor work.
- **What:** in hot functions, a run of FP/vector statements becomes one XMM block with a single combined keep test; the
  original per-op code is the exact fallback. `_ST` (vector stores) and `_CVT` (int conversions) are optional extras,
  off by default. TICK-063 (0272961d, ffc4515a, b7a9c8d9, 10148301), on by default since sprint 5 (2895ec0a).
  `a64_block.py` is 906 lines.
- **Measured:**
  - PC 3050 (i5-10400F): executors' guest CPU -8% (block) and -13% (with stores and conversions), but **fps unchanged**
    (29.16 / 29.22 / 28.60).
  - Main PC with PGO: 78.8 -> 79.3, inside the spread.
  - Sprint 5 stack: 80.4 / 78.7 / 79.3 against 76.9 / 78.4 / 77.7 (+1.8).
  - Exactness: 2 M runs, 0 mismatches.
- **Collision: high** (fact 3). It rewrites hot-function text and keeps the old text as the fallback, so an oot_patches
  site inside a run can be bypassed by the fast path. Camera speed and mouse look (f_80644c80), the model swap and the
  view loop are hot.
  - A port must make `a64_block` end a run at every patch marker, or apply the patches before the block pass (they now
  run after the lift).
  - Then verify per site.
- **Risk:** high for our tree; the gain is small and only where executors are on the critical path. **Later, or skip.**

### 8. Vulkan back end built with a play profile (`RX_VK_PGO`). Later (Windows needs work); in my area through the compile flags.
- **What:** a PGO build of `hookshot_vk`'s own files (gpu/vk/*.cpp, suyu decoders), with a stamp over the sources and the
  compiler so a stale profile is never used. HeyListen 992aaee0 (after Hookshot f12054fe5 / ProjectReLink): `nx2/vk_pgo.py`
  92 lines, `nx2/build.py` 12, `scripts/vk_profile.py`, tests.
- **Measured: on an RX 9070 XT** (Ryzen 5 5500X3D, RADV, Linux), 4 interleaved rounds:

  | Scene | fps without | fps with | Change | Replay time |
  |---|---|---|---|---|
  | Kokiri Forest | 106.9 | 110.8 | +3.7% | -13% |
  | Zora's Domain | 74.2 | 81.2 | +9.4% | -9.4% |

  The scenes are in-sample (the profile was recorded there).
- **Ours:** not present.
- **Hardware:** HeyListen enables it on Linux only, because llvm-mingw had no profile runtime. **Our local
  `llvm-mingw/lib/clang/23/lib/windows/libclang_rt.profile-x86_64.a` exists**, and `host/pgo_rt.c` already writes clang
  counters on Windows without compiler-rt. A Windows version looks doable but is unproven (continuous mode on Windows, the
  DLL's sections).
- **Rando:** no collision (renderer only).
- **Risk:** low for behaviour; medium for build effort. **Later.** Probably the biggest CPU-side gain for an AMD card.
  It may overlap the GPU/renderer area's report.

### 9. `HOS_NO_MUTEX_IX`: a mutex finds its host object through a number stored in the guest MutexType. Later, low priority.
- **What:** the SDK's nesting-count word (+8) holds an index into a host table. HeyListen measured the graphics
  recording job's shared-table probe at 0.69 ms a frame on the critical chain.
- **Ours:** not present. Our per-thread object cache is already 1024 entries (upstream's), so the gain is smaller.
- **Risk:** medium. It writes into guest memory (a field claimed unused). Unmeasured on its own. **Later / skip.**

### 10. TICK-062 host switches: `HOS_THREAD_OF_CACHE`, `HOS_SHORT_SLEEP_PAUSE`. Skip for now.
- **Measured:** each was inside the spread (B2 71.2 vs 70.4; B4 72.1); adopted only inside the sprint-5 bundle.
- **Ours:** CV signal fast is already in ours (`nn_os_sync.c:609`); thread-of is still a linear scan.
- `SHORT_SLEEP_PAUSE` spins with PAUSE to the deadline, which could hurt low-core CPUs.
- **Skip** unless the owner's CPU shows hos_thread_of in samples.

---

## Already in our tree (HeyListen picked them, or we have upstream's newer version)
- Game speed above 60 fps:
  - HOS_FPS_STEP (ours: `oot_patches` STEP hooks plus `nn_vi.c`);
  - HOS_FPS_MOVIE;
  - sound and solver hooks (8fcc8c22, 9df055f2);
  - whole-frame counters: pick-up fade, time of day, ripples, floor web, Scarecrow song.
  - **Our step floor is better** than HeyListen's f46b704e (1/480): ours is `1/max(cap,240)`.
- vcore fixes: c8b9a9f0, 26c12b0d, d522ec0e, 07b03596, bce1476c.
- Log written in batches (7f126435); timer short sleeps (4d488bc0, 376d0681, a1eb4604).
- OptimizeChangeBank heap retry (1b695334) and lowest priority.
- Commit given back near the commit limit (91a1ae8b). HeyListen's newer **host-allocation wait at the commit limit**
  (29243133 / 4fcd16d4, from Longshot 2547a8f3 #341: hos_xmalloc retries for 5 s, then an out-of-memory notice) is **not**
  in ours. That is memory robustness; another area may rank it.

## Skipped
- **The native engine (`engine/native` C++20, ~918 KB / 87 files, plus `host/hl_*.c` and `nx2/hl_gates.py`)**:
  HL_JOBS / DISPATCH / STAGES / JOBGROUP / MODSTAGES, HL_MAINLOOP, hl::math, hl::gfx, hl::stream.
  - Speed is "not being measured" by the owner's order. The candidate measured 2-4% *slower* than v0.3.2 on PC 3050.
  - The main loop has no speed A/B; HL_PROG_MEMO was 80.9 vs 79.4 fps, inside noise.
  - Huge, and it depends on HeyListen's gate and hash machinery and on their lift. hl::math replaces Havok kernels, so any
    divergence alters physics.
- **`A64_FPX_XMM`, `A64_LR_SCALAR` (TICK-055):** no in-game gain, off in HeyListen too.
- **TICK-026 native strcmp `HOS_NR_STRCMP_805AFC70`:** +3-5 fps on 3 kokiri pairs but off by default and unconfirmed. Its
  gate hash does not match a lift with back-edge polls (TICK-040), i.e. ours. The throttle (candidate 6) addresses the
  same thread.
- **TICK-047 job order (`OOT_JOB_ORDER`/`HOS_JOB_ORDER`):** inside the spread, not adopted.
- **`A64_GRAN` granule marks:** -1.7 fps, not adopted.
- **Twelve executors / twins:** not merged.
- **HL_STEP_SCAN:** a useful diagnostic (it found that **the chemistry objects count frames**, so burning and spreading
  run at the frame rate above 60, which is unfixed in both trees). It needs HL_TRACE's heap recorder (hl_trace*.c), which
  is large. Maybe later as a tool.
- **heapsplit / memsplit / hostsplit (HOS_HEAP_SPLIT, HOS_MEM_SPLIT, HOS_HOST_SPLIT):** measurement tools only; no gain
  by themselves (the memory area's levers HOS_LAZY_COMMIT and cold pages are another area's).
- **Linux-only items:** Linux short sleeps, dma-bufs, POSIX shims.
- **Telemetry, the Discord name, the HeyListen builder branding.**

## User-visible settings and features in this area that we lack
- **Code mods** (6bcce93f, 9a18c275, 23ceef10): IPS / IPS32 / pchtxt patches applied to the game's modules before the
  lift, with a "Code mods" option in the Windows and Linux builders. **Collides with the randomizer:** patched functions
  would break `oot_patches` anchors (HeyListen makes its gates and hooks step back for patched functions,
  `hookshot_code_patches.txt`). Not recommended for us.
- `HOS_VIDEO_NO_HOLD` (with candidate 5).
- `HOS_BG_THROTTLE=<run us>:<sleep us>` (candidate 6).
- `HOS_VCORE_STARVE_US` (candidate 2) and `HOS_DISCARD_HOLDS_CORE` (candidate 1): environment switches, not menu rows.
- Nothing missing in the frame cap or game-speed menus: ours (cap, steady pace, VSync) is at or ahead of HeyListen's.

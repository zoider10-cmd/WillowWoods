# HeyListen, 2026-11-22 (068033d9..8464b217, 75 commits; read only)

I read the clone's history without checking it out. Nothing was built, run or installed. Our tree was checked at
amd-fix-sharkiix-version 9907bb0c.

**Summary.** These two days were almost all HeyListen's "native engine" refactor plan (step 0 and step 1): a ledger of every
GPU result the game reads back, an exposure-meter ring, the R2/R3 readback classes, and then one **fixed-lag readback ring
(`HL_RB_LAG=2`), now on by default**. On an RTX 5070 in the Market it measured +10% fps, and on an RTX 3050 +5 to 8%. The rest
was experiments they measured and turned off again: frames in flight, deferred join, feed stream, completion thread,
segment tail, two of the five per-draw switches, and cold-page memory hold. There were also three small crash fixes in code
we don't have, a release CI and copyright headers. No launcher, settings or randomizer-area changes. The one real candidate
is the readback ring, and our own earlier no-code A/B (`RX_VK_READBACK_LATE=newest`: NOISE in the Market) suggests our PC
gains little from it. Measure the bound first.

## Candidates, best first

### 1. One fixed-lag readback ring for the meter, the 0x40 results and the 0x2000 pair (`HL_RB_LAG`, now default 2)
- **Commits:** 76f15e0f (the ring), 8dcd5b42 (ranges no program writes are answered with no wait), 044ad62f and 18ff8066
  (every 0x1040 read is R1, plus the 0xc0 companion), 945d69f3 and d16738c8 (diagnostics), 31a80e38 (on by default).
  85a9aec9's later changes to it serve only frames in flight (off).
- **Files:** gpu/vk/rb_ring.h (110 lines, pure rules plus test_rb_ring.py), vk_rbring.cpp (388), and hooks:
  `gpu_buffer_bind` (a written binding that is exactly a learned range is staged, not written back),
  `memory_end_submission` (`rbring_flush`: one barrier, copies into a 4 MB host ring, one barrier), and `invalidate`
  (learn the range, skip the ticket and write-back waits, `rbring_apply` at the end).
- **What it does:** a CPU read of the exposure meter (0x1040/0xc0), the per-object 0x40 result slots, or the alternating
  0x2000 pair gets the GPU's result from exactly 2 frames earlier, with no wait. Learned ranges that nothing writes are
  answered at once. Before, they waited for write-backs of other data on the same pages: 1.5 to 1.9 ms a frame of meter
  wait on the 5070.
- **Gain (docs/native-engine/readback-ring.md 4.7):** Market spin, RTX 5070 with a 7800X3D, 3 interleaved rounds: 77.4 to
  85.5 fps (+10%), p95 17.2 to 15.9 ms. RTX 3050: +5% at 1440p and +8% at 1080p (31a80e38). Their parallel replay was on
  (their default).
- **Correctness evidence:** at lag 1 it matches the old waited value in 0 of ~90,000 reads that differ (Market). Other scenes
  differ in 0.04% of reads, all of one known same-frame kind. At lag 2 every applied entry is exactly 2 frames old, with 0
  GPU waits. Shots of four scenes show no flash or tint. **Not checked by them:** a zone change inside the game (left to a
  test by hand) and run-to-run determinism.
- **Ours:** missing. We have the same base it hooks into: `invalidate` in vk_replay.cpp:4067, mirrors and `writebacks` in
  `gpu_buffer_bind`, `memory_end_submission`, `rb_pages` and the readback refresh. We lack their READB2/EXPO1 diagnostics and
  the readback ticket, which makes our hooks simpler. **But we already measured the idea's upper bound in part:**
  `RX_VK_READBACK_LATE=newest` (no wait for a range whose writer is the newest submission) was NOISE in our Market on
  2026-11-18 (fps 98.0 to 97.7, 1% low 58.2 to 58.9). A 9070 XT finishes the GPU work before the CPU asks, as their 5070
  does in the Market: 0.93 ms summed wait there, against 4.2 in Kakariko.
- **Hardware:** none. It helps most where the GPU is slow (the 3050). It does nothing to VRAM.
- **Game behaviour:** the exposure meter and the 0x40 sample-count fractions (likely sun or flare visibility) arrive one
  frame later than now. Our exposure-meter handling is our own (PR 430, the white-flash fixes): a stale or doubled meter sum
  is that bug family, so the pictures need checking at Lost Woods, Deku Tree and a zone change. No lift (nx2/) and no
  randomizer file is touched.
- **Port:** medium, ~500 lines in the renderer only (vk_rbring.cpp, rb_ring.h, ~15 lines of hooks), with the
  `HL_RB_LAG` row and the check mode. It conflicts with nothing in our randomizer files.
- **First, no code:** run a Kakariko A/B (our steady bench) with `RX_VK_NO_READBACK_WAIT=1` as the bound (a measuring run
  only, not for play: it is the white-flash risk), plus `RX_VK_LOG_READBACK_RANGES=1` to see our wait per range. If the
  bound is NOISE, as `newest` was, skip the port.
- **Score: later, and only if that bound shows a gain.** If it does, this is a better-made version of our late reads (no
  timing-dependent answer, and the quiet ranges are covered).

### 2. A texture handle's "storage pointer" answer kept per program (part of 76b1ef81, `RX_VK_DRAW_HPTR`, on by default)
- **What:** `build_descriptors` asks `handle_is_storage_pointer` for every fragment texture at every draw, a walk of the
  stage's storage-buffer descriptors. The answer belongs to the program, so it is kept in `ProgSlots` (one byte a texture
  slot).
- **Gain:** all five DRAW1 switches together cut the replay's summed draw CPU by 7.5% (12.95 to 11.98 ms) on the 5070 and
  by 5.5% on the 3050. fps was unchanged in both, since neither PC was replay-bound there. HPTR's own share was not measured.
- **Ours:** missing. We have the same per-draw call at vk_draw.cpp:4654 and our own `ProgSlots`. Our replay is serial and is
  the Market's critical path, so a per-draw saving reaches our frame, but this loop is short.
- **Port:** ~20 lines, renderer only. Risk low, and `RX_VK_DRAW_CHECK` shows how to check it. **Score: later, cheap. Bundle it
  with other per-draw work and A/B in Kakariko.**
- The other DRAW1 switches: `RX_VK_DRAW_LAZY` (work out may-skip only for a not-ready draw): **ours already is lazy**
  (`may_skip` is computed inside the not-ready branch, vk_draw.cpp:8321). `RX_VK_DRAW_EXCL` and Mooseca's 410d80ed (a
  thread-local copy of `cap_excl`) need `RX_VK_CAP_ONLY_GPU`, which we lack (still waiting from 11-17). **If CAP_ONLY_GPU is
  ported, take 410d80ed with it**, or its per-binding mutex becomes a new cost. PROGFRONT and PIPEFAST: turned off by
  them, no gain.

### 3. Small fixes, only for code we may take later
- **2e7dec93:** the plain ASTC decode binds its pipeline again after a chunk flush (otherwise there is a dispatch with no
  pipeline, a null read crash in the NVIDIA driver). We don't have ASTC chunking (`RX_VK_ASTC_CHUNK_MPX`, b556d431, skipped
  on 11-20). **Take it along if chunking is ever ported.**
- **6dbd9961:** `hos_gpu_write_live` indexed the CPU-write marks with the low 32 bits of the address, so a pool above 4 GB
  read the wrong page's mark (their issue 115). We have no `hos_gpu_write_live` (it is their lazy write-back's), and no
  `(uint32_t)addr >> 12` mark index anywhere in host/ or gpu/. Not affected.
- **d9a3da38, 3433427e:** the GPU profile's slots made before its query pool is published, and the profile's CPU sampler
  thread joined before exit. Both are in profile_run.cpp, which we don't have. Our one file-scope `std::thread`
  (vk_main.cpp:1230, the preparing window) is joined. Not affected.
- **1e793f27:** no Vulkan driver led to the WebGPU renderer's panic. Ours has no WebGPU renderer (host/rx_nowgpu.c says
  so). The only part worth copying is the `vkCreateInstance failed (VkResult %d: ...)` log line (vk_main.cpp:360, 2 lines),
  a nicety for a player's report.
- **7b021a96:** "too few programs sampled" still prepared lazily. Our `prepare_is_update` has no sampling (prepare before
  the game unless `RX_VK_PREPARE_BACKGROUND`). Not affected.

## Skipped (one line each)
- 85a9aec9, 416e6674, 885edefe, 4e8675e6 `RX_VK_FRAMES_IN_FLIGHT` on the ring: off by them, no gain on the 5070 (87.5 vs 87.7
  fps) or the 3050.
- 459c51e8, 31d700a4 `RX_VK_DEFER_JOIN`: a diagnosis, nothing to overlap. e5dfb832: the feed stream was not built.
- 4f435714, 9aa0fb9d, 9cf136f0 `RX_VK_FEED_LOG`, `RX_VK_POOL_SPIN` (off), 61333757 `RX_VK_COMPLETION_THREAD` (off), 2412b1bd
  `RX_VK_SEG_TAIL` (off), 25147b81, 4142f8b2: their parallel replay's tools. We run the serial replay (`RX_VK_PARALLEL=5` was
  slower here, 11-17).
- b73c8cfa, 908d727b `HL_EXPO_GPU` (the meter ring, off): replaced by item 1.
- aa22d849, 2bee5db1, 7696aedb, ac42941f, 31c3bbb7 READB2 (R2/R3 classes, `RX_VK_RB_WHO`, `HL_RB_R2`/`R3`): diagnostics,
  and the "cut" arm measured as noise. Only useful as tools if item 1 is ported.
- 31a80e38 `HL_GFX_VAR=1` (a native host loop for the key-0xa0 draw, engine/host/hl_gfx.c): HeyListen's native engine,
  "same speed, less translated work". It replaces guest code, a lift-side risk for the randomizer's patches.
- 177d1b93, 723fc56b, e1ba5733 `HL_MEM_ACCOUNT` / `HL_MEM_COLD_LOWMEM` (hl_mem.c, their own memory layer; off).
- 76b1ef81's profiler and sampler (`RX_VK_PROF_FINE` per thread, `RX_VK_DRAW_SAMPLE`): diagnostics.
- 208ffe5d / 986548fa market-spin bench scene, 6b7fde7c, ee2fc7f1, 7b3adc7f, docs (d9c5974d, 1109df5c, a2f1d723, b09e17d5,
  84f99311, 4dfd4e06, 7bd819f7, 627e374e, 2f777aa9, 29359159, 51fff380, 7de026bd, 8cc3b72a, 281ddd03, cd8b0a2a's note,
  e845dccd, d5318a86), 522f3b98 / decc67ad / d71bc1ac copyright lines, 962358a9..8464b217 and cea3a6ce release CI, 7d94a186:
  nothing for the frame.
- 5d002157 and 986548fa / d9c5974d are duplicates of 6dbd9961 / 208ffe5d / 1109df5c, from a merged branch. integ/v043 and
  the v0.4.3 tag are fully in main.

## Settings and bugs
- No new user-visible settings or launcher rows in this range. The ones listed on 11-20 (V-Sync mode, VRR, Unlimited limit,
  hidden rows, named backtraces) still stand.
- Nothing touches tunics, equipment or save logic: no fix that looks like bug 107 or another open bug of ours.

## Surveyed up to
origin/main **8464b217** (2026-11-22, "ci(release): recomplauncher.json keeps LF endings on a Windows checkout").

# Area 1: the frame's CPU/GPU work in the Vulkan back end (HeyListen survey)

Read only. HeyListen at 504f8362 (`engine/` = Hookshot a2e65052 + 670 commits); ours `amd-fix-sharkiix-version` at 41237d05.
Files read: HL `engine/gpu/vk/vk_replay.cpp`, `vk_memory.cpp`, `vk_draw.cpp`, `vk_texture.cpp` (barriers), `host/nvn_native.c`,
`host/hos_main.c`, `host/nvdrv.c`; HL `docs/tickets/TICK-006..063`, `SPRINT-5.md`, `docs/native-engine/{direct-emission,replay-cost,
frame-truth}.md`, `engine/docs/perf-audit.md`. Ours: `gpu/vk/vk_replay.cpp`, `vk_memory.cpp`, `vk_draw.cpp`, `vk_texture.cpp`,
`vk_recorder.h`, `host/nvn_native.c`, `share/recomp-perf-findings.md`.

## The context that decides most of this

- **HL measured on NVIDIA** (main PC 7800X3D + RTX 5070; PC 3050 i5-10400F + RTX 3050 on PCIe 3.0 x4). Its only AMD data is a
  contributor's RX 9070 XT on **Linux/RADV**. Nothing below was measured by HL on AMD Windows.
- **Our owner's frame is CPU-bound on the replay**: Market by day, replay ~10 ms on the Presentation Thread, GPU ~5.7 ms
  (`share/recomp-perf-findings.md`). So HL's GPU-time cuts (scatter copy, barrier trust/dedupe) buy little here; CPU-side cuts
  to the render chain (parallel replay, capture size, per-draw costs) are what can move fps.
- **HL's biggest structural differences from us**: parallel replay on by default (4-5 recorders, many refinements);
  `HOS_NVN_HOLD=2` (main thread's submits replayed on a host thread); a capture that leaves out heap memory (`RX_VK_CAP_ONLY_GPU`);
  the late-page wait moved to the queue (`RX_VK_LATE_DEFER`). Ours: parallel replay off by default (gated, ReLink idea, 37f1969c),
  `HOS_NVN_HOLD` 0/1 off, capture of whole mirrored imports, our own late fix (`RX_VK_LATE_FIX`, off).
- **HL turns many things on by host-side `setenv` before main** (`host/hos_main.c` `heylisten_env_defaults`): if any of those is
  ported, its default has to be set in our own code, not copied as that constructor.
- Nothing in this area touches the randomizer (`nx2/oot_patches.py`, `host/oot_*.c`, `host/hos_oot*`, `tools/rando`, the
  launcher's rando settings) or the lift, except where noted (HOLD=2 and pre-copy touch `host/` sync/NVN code, not rando code).

## Candidates, best first

### 1. Env-only A/Bs on our own tree first (no port): parallel replay with HL's thread count, and the streaming-store capture
- **What**: two switches our tree already has, which HL runs on by default:
  - `RX_VK_PARALLEL=5` (HL `par_threads()`: 5 recorders at 16+ hardware threads, 4 at 8+; the 9800X3D has 16). Our gate
    (`RX_VK_PARALLEL_MIN` 700, exposure buffers kept serial) stays on.
  - `RX_VK_CAPTURE_NT=1`: our `copy_nt` (vk_memory.cpp ~1598) is the same idea as HL's `RX_VK_CAPTURE_STREAM` (TICK-037, 3c111983,
    on by default in HL).
- **HL's gain**: parallel on by default since TICK-006 (6bf932fc): Kokiri 54 -> 65 fps, Hyrule Field 49 -> 62, p99 26 -> 20 ms
  (RTX 5070, 2026-11-09). Streaming stores: kokiri-idle 67.4 -> 70.3, castle-move 63.0 -> 66.3 fps, every on run above every off run
  (docs/benchmarks/2026-11-10-tick037-capture-stream.md).
- **Ours**: both present, both off. The owner's own A/B of gated `RX_VK_PARALLEL=3` (37f1969c): 74.8, 79.9 vs serial 75.0, 72.5
  (Market fountain): promising, inside the ±4 fps spread, never tried at 4-5. Upstream Hookshot made NT opt-in after an RTX desktop
  A/B showed no lower capture time and more stutters (f4e6fdde).
- **Hardware**: neither is vendor-specific. NT stores help most when the copy evicts the game's data from L3; the 9800X3D's 96 MB
  L3 is the case where it may not pay (HL's 7800X3D also has 96 MB and gained). Low-end CPUs: parallel takes cores from the game's
  job threads (HL defaults to 0 recorders below 8 hardware threads).
- **Port**: none. Runs only: Market A/B, interleaved, 3+ runs each, shots for black/washed frames (the parallel replay's known
  failure).
- **Risk**: parallel replay out-of-order bugs (see 4: the copy-destination mark we lack). NT: stutter tail (watch p99).
- **Score**: **first** (cheapest information in this area; decides whether 4 is worth doing).

### 2. A capture that no longer misses pages the replay's collection is re-marking (Longshot #1083 via HL 26e0f0a6)
- **What**: `memory_collect_written` takes every page's write mark, then marks the captured pages again for the next capture. A
  submit's capture scanning on the game's thread in between finds those pages unmarked and leaves them out; the GPU reads an older
  copy (Kokiri Forest's ground mist gone for a frame). Fix: a `collect_mu` held over that window and by the capture's scan.
- **Gain**: correctness (one-frame flicker), unmeasured for speed (one more uncontended lock a submit).
- **Ours**: lacks it. Our `memory_collect_written` (vk_memory.cpp ~739) has the same take-then-remark window with no lock
  (`host->collect_written`, then `host->mark_written` per captured page).
- **Hardware**: none.
- **Port**: ~40 lines in vk_memory.cpp (a mutex, the collection's window under it, `capture_make`'s scan taking it) + HL's
  `tests/test_vk_collect_window.py` (220 lines, cuts the source: adapt). Lock order to check against ours (HL's comment: collect_mu
  before cap_ranges_mu). Origin is Longshot 95475b67: if the Longshot survey ports it, skip here.
- **Risk**: low (a lock; deadlock only if the order is wrong).
- **Score**: **first** (small, a real race in our tree).

### 3. The replay's per-draw costs that upstream Hookshot cut and we lack: flat caches and the vertex-binding range
- **What**: HL 3aa51bf5 (Hookshot eda64e895, `flat_map.h`: open-addressing tables for `program_for`'s `picks`, `graphics_pipeline`'s
  `mine`, the recording's `c1_at`; `payload<T>` without a memcpy call) and 28623fcf (Hookshot 33ed7b81a, `RX_VK_VB_RANGE`: a draw
  whose vertex streams changed binds only the changed range, not all 16).
- **Gain**: built and run together with two more replay changes (desc counts 48f6e089, accessor-once 804e2074) on an **RX 9070 XT,
  RADV, Ryzen 5 5500X3D**: Kokiri 104.4 -> 110.7 fps, the replay 5.57 -> 5.09 ms; Zora's Domain 74.1 -> 76.9, replay 10.55 -> 10.02 ms
  (4 interleaved rounds). Not measured alone. Upstream: +3.4 fps on an RTX 5090 in one of two configs; no change on a 6-core
  RX 9070 XT desktop (Linux).
- **Ours**: we have the other two (`Program::desc_counts` in vk_shader.h; `Pass& ps = pass()` / `DescWriter& = dw()`) and our own
  flat handle table (7ac89d22, +4% here). Still `std::unordered_map`: `picks` (vk_shader.cpp ~2012), `mine` (vk_draw.cpp ~2419),
  `c1_at` (vk_draw.cpp ~423); `payload<T>` memcpy (vk_replay.cpp ~863); `vkCmdBindVertexBuffers2(cmd, 0, 16, ...)` (vk_draw.cpp ~8075).
- **Hardware**: none; the VB range came from a Steam Deck profile (1.1% of the replay on RADV).
- **Port**: flat_map.h 87 lines + ~45 lines of edits in vk_draw.cpp / vk_shader.cpp / vk_replay.cpp, VB range ~30 lines; tests
  test_flat_map.py, test_replay_copies.py, test_vertex_bind_range.py (cut source: adapt). **vk_shader.cpp changes the shader stamp:
  the first start re-prepares shaders once.** VB range is only right while every other bind clears `last_vb_valid` (HL lists the
  sites; ours must be checked, including our temporal/FSR passes). Check with the port-survey of upstream Hookshot / Longshot
  (Longshot 3d880bf is the same work): port once, from whichever source is cleaner.
- **Risk**: low-medium (VB range: a stale binding if one bind site is missed: wrong geometry). Each has an on/off.
- **Score**: **first** (the only HL-carried replay speedup in this area measured on an RX 9070 XT).

### 4. Parallel replay: HL's refinements and its last ordering fix (only if 1 says parallel pays here)
- **What**, all in vk_replay.cpp unless said:
  - 74e1f4e5 (+ vk_xfer.cpp): the dry pass marks a **texture copy's destination** as written (we mark clears already, 8803dc7c's
    equivalent is in our tree: `dry_clears_on`). Without it a later segment uploads stale guest memory over a copy's result.
  - TICK-050/052/054 (edde08b6, 23852736, 160785ef): one round of segments (`RX_VK_PARALLEL_ROUNDS`), the replay thread recording
    the first segment and helping (`RX_VK_PARALLEL_SELF=2`), boundaries by recording time (`BALANCE`), a point every 32 draws
    (`POINT=32`), lock spinning (`PARLOCK_SPIN=4000`), wider pool table, destroyed-texture ring.
  - bb99eb5b / cbe55b8b `RX_VK_FINE_SEGMENTS` / `SEG_MAX` (on below 16 hardware threads only: **not** on the 9800X3D).
  - 0c772989 + e7211a7a `RX_VK_EARLY_GPU=1` (each segment submitted in order as finished, the work before the dry pass submitted first).
  - 9af5661f `RX_VK_DRY_WANTED` (the dry pass copies state only at the points a boundary takes).
- **Gain**: TICK-054 confirm (6 rounds, RTX 5070, together with HOLD=2, item 6): kokiri-idle 72.3 -> 76.1, castle-move 68.3 -> 70.2,
  hyrule-walk 69.9 -> 72.1; SELF=2 alone +3.1, 5 recorders +2.7 vs the combo (screens). EARLY_GPU: PC 3050 36.45 -> 38.05 (GPU-bound
  card). FINE_SEGMENTS: PC 3050 36.0 -> 37.7. DRY_WANTED: inside the spread.
- **Ours**: the base parallel replay plus ReLink's gate and dry-pass render targets; none of the above.
- **Hardware**: CPU threads (the defaults scale by `hardware_concurrency`); nothing vendor-specific. Hurts 6-core CPUs if forced.
- **Port**: large: ~1,500+ lines across vk_replay.cpp (our parallel section differs: gate, dry RTs, `memory_rb_segments_begin`),
  vk_texture.cpp, vk_memory.cpp; many HL tests cut the source (test_segment_plan, test_parallel_init_order, test_seg_early, ...).
  74e1f4e5 alone is ~30 lines and goes in **with** any default change.
- **Risk**: medium-high (out-of-order segments: one-frame black/washed scenes have been this feature's failure mode in every fork).
- **Score**: 74e1f4e5 **first if parallel goes on**; the rest **later**, one switch at a time, only after 1.

### 5. `RX_VK_CAP_ONLY_GPU`: the capture clipped to the game's pools (HL d900badb, 9caff0dd, b9eb47c7, 511cf581, ef922c15, 850cfb0c)
- **What**: the back end imports guest memory in chunks around bindings, and the capture scanned every mirrored import whole: in
  OoT those chunks cover the actor heap (0x1050000000-0x1060000000), written every frame and never read by the GPU (NVN: a GPU
  address below 1 TB is valid only in a pool). Mode 1 clips the capture's ranges (and the replay's stamping) to the game's live
  pools; mode 2 only counts what 1 would leave out.
- **Gain**: pages a frame 10,010 -> 1,409 (39.1 -> 5.5 MB) in castle-move, 86-87% fewer in all three scenes, 0 reads into left-out
  ranges (main PC, docs/native-engine/direct-emission.md section 10). fps: PC 3050 castle-move 20.2 -> 22.8 (+13%), p50 -2.5 ms. Main-PC
  fps not given.
- **Ours**: lacks it. Our `cap_ranges` are the mirrored imports too, but our chunks are **4 MB** with mirrors (`import_chunk()`,
  vk_memory.cpp ~2982) against HL's 16 MB, so the share of heap memory in our capture is unknown and probably smaller.
- **Hardware**: none vendor-specific; gains most where the copy is slow (memory bandwidth, low-end CPU).
- **Port**: medium: ~250 lines in vk_memory.cpp against our different capture code (HL's `cap_excl`, `capture_union_locked`,
  pre-copy hooks don't exist here), plus host pieces it needed after play bugs: `hos_gpu_live_pools` export (nvdrv.c, ~10 lines),
  a pool-born hook at `nvnMemoryPoolInitialize` (HL feeds it through its `mkwvk_pool_flags` export, which we lack: an interface
  addition, maybe an `MKWVK_API_VERSION` bump), and the double-finalize fix in `nvnMemoryPoolFinalize` (nvn_native.c, ~10 lines).
  Test test_cap_only_gpu.py.
- **Risk**: medium. HL's first play session with it drew a new zone wrong for seconds (35,722 bindings into left-out ranges) until
  the two host fixes; a GPU read through a pointer outside any pool would show as missing data.
- **Score**: **later, measure first**: port mode 2 (count only, no behaviour change) to learn our share; port mode 1 only if the
  capture is a large part of our render chain.

### 6. `HOS_NVN_HOLD=2`: the main thread's submits replayed by a host thread (HL 4ae29eeb, 160785ef)
- **What**: submits from threads other than the presenting one are held; a host thread ("hos held submits") takes their capture
  and replays them ~10-20 us later, so the capture copy and recording leave the game's main thread. The presenting thread's own
  submits go first through `flush_cs` to keep queue order. HL also keeps `HOS_NVN_HOLD=1` (all held, Hookshot's).
- **Gain**: HOLD=2 alone +1.5 fps (castle-move, inside the spread); with item 4's switches +3.1, confirm numbers in item 4.
  `HOS_NVN_HOLD_CHECK`: 0.14% of captured pages had other bytes at the flush (upper bound).
- **Ours**: `HOS_NVN_HOLD` 0/1 only, off (host/nvn_native.c ~1056).
- **Hardware**: none; needs a spare core for the host thread.
- **Port**: medium: ~350 lines in host/nvn_native.c (+ rx_backend.c for the check), our nvn_native.c differs from HL's. Host
  code, not randomizer code, but it changes **when the game's memory is captured** relative to its submit.
- **Risk**: medium-high: picture (late writes), and readback order: HL's own follow-up (linger) burnt the exposure to white; the
  light meter's read-and-reset order is fragile. Vcore interplay (HL had to give the virtual core up around `flush_cs`).
- **Score**: **later** (after 1 and 4; its gain in HL came mostly with the parallel switches).

### 7. `RX_VK_LATE_DEFER`: the late-page wait moved from the capture's take to the queue (TICK-060, 559d7de6, d32058de, 1aa4ef7f, d2f6398d, 677c3937)
- **What**: a capture whose pages a submission still on the GPU writes back no longer waits for it on the CPU; the fix is copied
  in when the value is reached, and the queue holds the recordings that read it. `RX_VK_LATE_DEFER_TEX` extends it to live
  texture storage.
- **Gain**: PC 3050 +18-21% (castle-move 29.13 -> 34.40, 18/18 rounds). Main PC: screen 75.65 -> 77.54, confirm inside the spread,
  "does not lose", steadier.
- **Ours**: different mechanism for the same wait: `RX_VK_LATE_FIX` (GPU `late_fix.comp`, Hookshot 0815d984), off in Mako ("1-3 fps
  faster without"), and refused under `RX_VK_PARALLEL>1`.
- **Hardware**: gains where the GPU is the slow side (HL: GPU-bound 3050). On our fast GPU the wait should be short.
- **Port**: large (~500 lines in vk_memory/vk_replay, its own fix thread, review fixes for non-rising values); conflicts with our
  late-fix code paths.
- **Risk**: high (stale words in the capture = wrong picture; HL needed review fixes).
- **Score**: **later**: first read our frame trace's late-wait column (`RX_VK_FRAME_TRACE`, `memory_late_wait_ns`) in the Market;
  only if it is >~0.5 ms a frame, A/B `RX_VK_LATE_FIX=1` (in tree) before considering this port.

### 8. Mirror syncs and readback refresh as one compute scatter-copy (TICK-021, 4e6dc289)
- **What**: ~1,650 small copy regions a frame in ~53 `vkCmdCopyBuffer` calls become one dispatch (`shaders/msync_scatter.comp`) over
  a 4 MB ring of {src BDA, dst BDA, size} entries; unaligned or huge batches fall back to copies. On by default in HL
  (`RX_VK_MSYNC_SCATTER=0` off).
- **Gain**: engine copy GPU time 2.19 -> 0.81 ms a frame (msync 1.35 -> 0.29, rbrefresh 0.41 -> 0.09); fps +0.9 (72.4 -> 73.0),
  RTX 5070, hyrule-walk.
- **Ours**: lacks it.
- **Hardware**: buffer device address on host-visible memory (AMD Windows supports it; HL: "AMD/Intel BDA reads of host-cached
  memory not verified"). A GPU-time gain: small on our CPU-bound frame.
- **Port**: ~300 lines vk_memory.cpp + a shader and its generated SPIR-V header (regenerate with glslang, per AGENTS.md);
  capture buffers need STORAGE + SHADER_DEVICE_ADDRESS usage.
- **Risk**: low-medium (same bytes, same order; a ring wrap bug would corrupt mirrors).
- **Score**: **later** (only worth it if the GPU becomes the limit, e.g. with frame generation or a high resolution).

### 9. The fast fence poll and the readback ticket (TICK-058 a3c9d977, TICK-059 29573e8c)
- **What**: a timeout-0 fence poll on a submission already done answers without `sync_order_mu`; a ticket keeps the CPU's readbacks
  ordered after the replay in progress (without it the Market's exposure blew out to white).
- **Gain**: castle-move +1.4..+1.7 fps, above base in 5 of 9 confirm rounds (RTX 5070); on by default since sprint 5.
- **Ours**: lacks both.
- **Port**: ~390 lines vk_replay.cpp + tests (test_readback_ticket, test_late_defer cut the source).
- **Risk**: medium-high (readback ordering = exposure).
- **Score**: **later** (weak evidence, risky area).

### 10. `ee56ca1d` (Hookshot #2962): the capture's pool list hashed so libc++ does not put every pool in one bucket
- **What**: `refresh_pool_ranges_locked` keys 64 KB-aligned pool starts in `std::unordered_map` with identity hash; libc++ (our
  llvm-mingw) keeps a power-of-two bucket count from `reserve`, so all starts land in bucket 0 (~20 ms freezes every ~45 s in HL's
  Market, where its list was capped at exactly 8192).
- **Ours**: same code (vk_memory.cpp ~1155-1182), but our list grows past full (7edeee8d), so `reserve(n)` with n exactly a power of
  two is unlikely and libc++ rounds others to a prime. Exposure small.
- **Port**: ~14 lines + test. **Risk**: none. **Score**: **later** (cheap insurance; fold into any vk_memory port).

### 11. Barriers: `RX_VK_BARRIER_TRUST`, `RX_VK_BARRIER_DEDUPE_PAR` (TICK-057 4981d105, f0f11a00; on in sprint 5), and Hookshot's `RX_VK_GAME_ORDER` (#2559, 94a4df0c)
- **What**: the engine's pass-start and dispatch full barriers dropped where the game's own barrier orders the work; full-barrier
  dedupe inside parallel segments; back-to-back passes/dispatches ordered by the game's barriers.
- **Gain**: each inside the spread alone (+0.3 / +1.5); together with the pre-copy 85.0 vs 82.7 (5 rounds, RTX 5070). GAME_ORDER:
  "a tenth off the GPU frame on an RTX 5090", NVIDIA-only by default.
- **Ours**: our serial dedupe (`RX_VK_BARRIER_DEDUPE_OFF`) and `RX_VK_PASS_BARRIER=game` (opt-in) exist; the rest lacks.
- **Hardware**: GPU-time; AMD unmeasured, and a missed hazard on AMD is a corrupted frame or a device lost.
- **Score**: **skip for now** (GPU not the limit on the 9070 XT; risk without gain).

## Skipped (one line each)

- **Castle Town move/turn drop fix (TICK-027, d245801a)**: we have the equivalent and more (vk_texture.cpp `drawn_over_shifted`,
  `dead_targets.h`, `target_overlap.h`, the target pool from Longshot).
- **Write-backs only of what the CPU reads (TICK-015)** and **c7786343 `RX_VK_WB_MAX_KB`**: we have our own learned wb table and the cap.
- **90530d57 / 7a213552 (32 submitted pages), a86cfe8e (tex spans once a present), fc66ad44 (`RX_VK_BATCH_IDLE`)**: already in our tree.
- **Slow-link (PCIe) mode: `RX_VK_MSYNC_DIFF`, `RX_VK_CAPTURE_HASH`, `RX_VK_CLAIM_HASH`, `RX_VK_MSYNC_FAST` (3df13599, f3149242,
  4b170f0a, 297f2ea7, bd59eda5, ba5605e1)**: on only at <= 8 GB/s links (HL: -10% on x16 Gen4/5); link read via NVML on Windows
  (NVIDIA only) or sysfs on Linux; the owner's card is on a full x16 slot.
- **Capture pre-copy + kick (TICK-043 2a83cf5d, TICK-054 2fb14676, `HOS_PRECOPY_KICK` in host/nn_os_sync.c)**: alone it lost fps in
  HL's own A/B (75.4 -> 71.4); its later +1.3 was inside the spread; needs a hook in the game's end-of-frame wait.
- **Async submit / job graph / job order (TICK-042, 043, 047)**: measurements, nothing adopted; job order is a lift patch (`nx2/`).
- **`RX_VK_ASYNC`**: HL measured 56.4 fps vs 77.7 (a readback waits for the whole queue).
- **TICK-061 chain-B bundle (`CAPTURE_CLAIM`, `COLLECT_FAST`, `SHADOW_FAST`, `STAMP_SPLIT`, `DRY_LEAN`, `WORK_LOCAL`,
  `SEG_SETUP_PAR`, `OCC_PROXY_SKIP`; fad43fbd, 1,113 lines)**: each inside the spread; built on HL's capture and parallel structures.
- **`HOS_NVN_HOLD_LINGER_US`, `RX_VK_LATE_MERGE`, `RX_VK_ACQUIRE_FENCE`, `RX_VK_SYNC_HONEST`, `RX_VK_WAIT_REC_SENT`**: off in HL;
  the linger and WAIT_REC_SENT burnt the picture white.
- **Capture by written granules (`A64_GRAN`, `RX_VK_CAPTURE_GRAN`)**: a lift change; no gain (the marks cost what the copy saved).
- **`RX_VK_POOL_MIRROR`, `RX_VK_NO_HOST_IMPORT`, `HOS_GUEST_PAGES` (host/hos_guestpages.c), `HL_MEM_DROP`, `RX_VK_LEDGER`
  (vk_ledger.cpp)**: RAM-saving experiments and a diagnostic, all off by default in HL, high-risk host memory changes.
- **8286dbba (no idle flush while recordings wait for a late fix)**: an interaction of HL's late defer with batched submits, which
  are RADV-only in our tree.
- **`RX_VK_READBACK_STRICT` (25d542e8, 04067197)**: a RADV-only exposure fix (Linux 9070 XT).
- **36404a31 (Longshot #468/#469/#431 import table)**: memory correctness, belongs to the Longshot survey.
- **`RX_VK_TEST_BARRIER_DROP`**: a bound, not shippable.

## User-visible settings or features in this area that we lack

None: HL exposes nothing here in its menu or launcher; everything is environment switches with defaults chosen by thread count,
vendor or PCIe link. What we lack that the owner could see:
- **Defaults chosen by the hardware**: HL turns the parallel replay on by thread count (4 at 8+, 5 at 16+ hardware threads); ours is
  off unless `RX_VK_PARALLEL` is set by hand.
- **Measuring tools** (useful before any port above): `RX_VK_TL` (a timeline of the renderer's threads and the GPU over a few frames),
  `RX_VK_RB_PROF` (the CPU's readbacks timed by phase and caller), `RX_VK_LAG_LOG`, `RX_VK_PROF_FINE`'s replay-cost lines,
  `HOS_JOBTRACE` + `tools/bench/frameline.py` / `chainb.py` (the frame's critical path). Our `RX_VK_FRAME_TRACE` and
  `HOS_RECORD_STUTTERS` cover part of this.

# Area 2: stutter, textures and memory in the Vulkan back end (HeyListen survey)

Read only. HeyListen (HL) at 504f8362; our tree at 41237d05 (branch amd-fix-sharkiix-version). HL paths are `engine/gpu/vk/...`,
ours `gpu/vk/...`. Owner's PC: RX 9070 XT (16 GB), Windows 11.

Overall: most of this area's HL tickets (TICK-007/008/023/030/036/038, the drawn-terrain write-back, texel-view ownership, the
commit-limit texture rule, the render-target reuse, the 6-worker rule, ages once a present, zstd program cache) are already in
our tree in an equivalent or later Hookshot/Longshot/Mako form. What is left is a few small correctness ports from Longshot
and Hookshot that HL picked up and we did not, plus HL's own ASTC transcode work (TICK-031/051). That work is big, built for
an 8 GB RTX 3050, and conflicts with our AMD BC3 workarounds.

## Candidates, best first

### 1. A pipeline is drawn only with the program object it was built from (device lost / GPU hang): port first
- **What**: two program objects can share a pipeline key (code hash + variant hash), for example the one the precompile
  built a noted pipeline from and the one a later draw picks. The draw then ran one object's shaders under the other's layout,
  descriptors and constants. `PipeEntry` keeps the object it was built from, and a draw with a different object gets a
  pipeline of its own. `RX_VK_PIPE_BY_PROGRAM=0` turns it off. Default on.
- **HL**: 1ae91a2d (merged 0ffb6977), test `tests/test_pipe_by_program.py`, row in `docs/development.md`. It is a port of
  **Hookshot 65e2cb91** (NotRexed, on pixl27's 8b1e96ad).
- **Measured**: HL `engine/docs/tested/2026-11-17-pipe-by-program-nyakuoff-run01..03.md`, on a **Radeon RX 7800 XT** (RADV,
  Linux), Kokiri Forest standing after a save loads. Without it: device lost in 4 of 4 starts (`GPUVM fault` from the texture
  unit, a ~2 s submit, ring reset), always at a draw of the clustered-lit program 400655db8f12d0bc. With it: 0 of 4 and
  0 of 3 starts of 420 s. On NVIDIA the same bug was the "device lost near water". No fps numbers (not a performance change).
- **Ours**: missing. `PipeEntry` (`gpu/vk/vk_draw.cpp:1146`) has no program-object field, there is no `RX_VK_PIPE_BY_PROGRAM`,
  and `git cat-file` does not know 65e2cb91.
- **Hardware**: not vendor specific. It hit AMD and NVIDIA. No switch dependence. Might add a few extra pipeline builds
  (HL logged 3 programs a session).
- **Port**: ~40-60 lines in `vk_draw.cpp` plus a source-reading test. Port from **Hookshot 65e2cb91 itself**, not HL's
  version: HL dropped the kept-ready part (`kept_ready`, vk_programs.cpp's load-time pipelines), which our tree has.
  The randomizer and the lift are not touched.
- **Risk**: low. The worst case is one more pipeline built in play (a first-draw hitch). Score: **first**.

### 2. A copy into a BC3 texture only in whole 4x4 blocks or up to the level's edge (VUID 00207/00208, undefined on AMD)
- **What**: `texture_copy_into_bc` checks that dx/dy are block-aligned but not the extent. A region from an ASTC 6x6 or
  10x10 source that ends mid-block and does not reach the level's edge is invalid Vulkan (undefined on AMD and Intel). Now it
  is left to the copy's other paths.
- **HL**: f2bebddd (port of Longshot 21ad3104, #672), 3 lines in `vk_texture.cpp` and a test line.
- **Measured**: unmeasured (a validity fix).
- **Ours**: missing. `gpu/vk/vk_texture.cpp:3164-3167` has only `(dx & 3) || (dy & 3)`. The line to add, after `ow`/`oh`:
  `if (!dst->bc_resized && (((w & 3) && dx + w != ow) || ((h & 3) && dy + h != oh))) return false;`
- **Hardware**: AMD-relevant. No switch.
- **Port**: 3 lines plus a source-check test case. No conflicts: the function is ours as written, with the AMD `bc_resized`
  branch already there. Not randomizer code.
- **Risk**: very low. Score: **first** (trivial).

### 3. Texel buffer views only of formats the device supports (AMD: no RGB 3-component texel buffers)
- **What**: before `vkCreateBufferView`, check `bufferFeatures` for UNIFORM/STORAGE_TEXEL_BUFFER. If the format is not
  supported, return no view (or a 16-byte dummy R32 view where `nullDescriptor` is off) and log it. R8G8B8 and similar
  formats have no texel-buffer support on AMD and Intel, and an invalid view can fault the GPU.
- **HL**: 00e8805b (port of Longshot bcb364f9, #1244), ~54 lines in `vk_texture.cpp` and
  `tests/test_texel_buffer_format_support.py`.
- **Measured**: unmeasured.
- **Ours**: missing. `texel_buffer_view` (`gpu/vk/vk_texture.cpp:4093`) has the Longshot a23587f5 ownership registry (as HL's
  87878768) but no format check. It sits under the registry, so the port is the early-return block alone. The dummy view
  matters only without `nullDescriptor`, which AMD's Windows driver has.
- **Hardware**: AMD-specific benefit. Costs nothing elsewhere.
- **Port**: ~15 lines (the check and the log; the dummy is optional) plus a source-check test. No conflict.
- **Risk**: low. A format we now leave unbound would have been undefined anyway. Score: **first** (cheap). Whether the game
  ever asks for such a format shows in the new log line.

### 4. A compute program's pipeline read and published atomically (data race)
- **What**: `Program::compute_pipeline` is written by build workers and the precompile's threads while recording threads
  read it during dispatch. HL reads and writes it through `std::atomic_ref` with acquire/release, and publishes a pipeline
  only once it is fully made (`gated_compute` writes into a local first).
- **HL**: bfb16fc1 (port of Longshot 86abfce5, #621), ~28 lines in `vk_draw.cpp` and `tests/test_compute_pipeline_atomic.py`.
- **Measured**: unmeasured (prevention).
- **Ours**: missing. There are plain stores at `gpu/vk/vk_draw.cpp:9510, 10245, 10261` and plain reads at `10210-10211`
  and in the dispatch path.
- **Hardware**: none.
- **Port**: ~30 lines in our `dispatch()` and the precompile, adapted to our `compute_pipeline_cached` path (HL has none).
  No conflict with the randomizer.
- **Risk**: low. Score: **first/later** (cheap hygiene, no visible bug known).

### 5. Upload budget counted per looking-up thread, not summed over the parallel replay's workers
- **What**: the deferral of new ASTC uploads (`upload_defer`) compares the budget with `frame_upload_ns`, which is every
  thread's upload time summed. With the parallel replay's segment workers uploading side by side, the sum reaches the budget
  while the busiest thread has spent much less, so too many textures are held back and drawn with the placeholder for
  several presents at an area's arrival. HL makes the time thread-local; `RX_VK_UPLOAD_BUDGET_SUM=1` keeps the old rule.
  HL also adds `vk: deferral:` log lines (8ff4de67: how many were held back, what took the budget, how long they waited).
- **HL**: c6f44368 + 8ff4de67 (Mooseca, #58), merged 54b4316d.
- **Measured** (c6f44368's message), **RX 9070 XT**, Mesa RADV 26.2.6, Linux, Hyrule Field to the Market, 4 interleaved
  runs: textures held back 470 -> 116; their wait p95 672 -> 535 ms, max 1182 -> 565 ms. But the load's worst frame went
  391 -> 403 ms, frames over 33 ms in the 20 s after arrival went 21.5 -> 24.5, and Kokiri standing went 99.9 -> 98.1 fps.
  Textures come in sooner, at a slight cost in hitching. Not run on Windows.
- **Ours**: summed. `frame_upload_ns` is "every thread's" (`gpu/vk/vk_texture.cpp:1500, 1532, 2678`). Our budget is
  **10 ms** (Mako 4.1.1 lowered it from 40 to cut Hyrule Field's 60 -> 40 fps drops), and RX_VK_DEFER_FRAMES (3) caps the
  wait, so the summed rule holds back even more here than in HL.
- **Hardware**: measured on the owner's exact card (under Linux). No switch dependence.
- **Port**: ~20 lines (a thread_local counter reset per present, plus the env switch) in `vk_texture.cpp`. The deferral log
  is optional (~60 lines).
- **Risk**: low (correctness unchanged), but it trades hitches against texture pop-in. Needs a Market-arrival A/B on this PC
  at our 10 ms budget. Score: **later, with an A/B**.

### 6. Texture budget on 16 GB cards: our 6 GB cap (no HL code needed; a better option to flag)
- **What HL found** (TICK-051, `docs/tickets/TICK-051.md`, benchmark `docs/benchmarks/2026-11-11-tick051-stutter.md`):
  walking stutter came from ASTC re-transcodes of textures evicted over the budget. 82% of the transcodes were of storage
  transcoded before, and the next frame waited for them on the GPU.
- **Ours**: the texture budget is `min(70% of the allowance, 6144 MB)` (`gpu/vk/vk_texture.cpp:4563-4566`, the cap from
  Hookshot issues 105/106). On the RX 9070 XT (about 15 GB allowed) that is 6 GB, so textures past 6 GB are evicted while
  VRAM is free, and walking back transcodes them again. Our `astc_reuse` (Longshot) only reuses a finalized image that is
  still held. It does not help after an eviction.
- **Suggestion**: before porting HL's BC cache (item 8), A/B `RX_VK_VRAM_MB=9000` (or 10000) against the default on a
  Hyrule Field / Market walk on this PC. If the 1% low improves with no VRAM paging, consider a larger cap for cards whose
  driver allows over 12 GB. No code is needed to try it.
- **Risk**: VRAM over-commit if the rest grows. Our compaction and the 90%/97% rules already squeeze the budget near the
  limit. Score: **first to try (env only)**.

### 7. The first start's pipeline prediction: leave out huge programs, stop near the commit limit
- **What**: in `predict_run`, a program over `RX_VK_PREDICT_MAX_KWORDS` (300k SPIR-V words) is left to its first draw. The
  prediction stops when the system has less than `RX_VK_PREDICT_RESERVE_MB` (3072) of commit left. The progress lines gain
  private commit, C heaps and the programs in hand.
- **HL**: d2384687 (and 44ecd248), new `predict_limits.h`, ~135 lines in `vk_draw.cpp`, and tests
  `predict_limits_test.cpp` / `test_predict_limits.py`.
- **Measured** (commit message, PC 3050: RTX 3050, 32 GB, Windows): a cold prepare's prediction went 346.8 -> 93.5 s,
  start-up 531.9 -> 245.9 s, peak private commit 36-39 GB -> 4.3 GB, C heaps in play 29.5 -> 0.6 GB. Two programs,
  93e3e999f2fb9fd8 (1014k words) and cf987f56b971bdb3 (502k), each took the NVIDIA compiler over 3 minutes and over 11 GB.
- **Ours**: missing (`predict_run`, `gpu/vk/vk_draw.cpp:9762`, has no size or commit check). But our prediction is
  **off by default**. Mako 3.4.1 builds nothing ahead unless the launcher's "Quick first start" (`RX_VK_PREDICT_BG=1`,
  `launcher/Launcher.cs:2340`, off) or `=2` is set. With it on, the build runs behind the game at idle priority, where a
  multi-GB compile would be worse (commit-limit crash in play). Our `fallback_size_policy.h` caps the same 93e3e999 program
  only for the GCN mesh fallback.
- **Hardware**: NVIDIA's compiler measured. The AMD Windows compiler's cost for these programs is unknown.
- **Port**: ~60 lines without the diagnostics. Self-contained in `predict_run`. Not randomizer code.
- **Risk**: low. Score: **later** (matters only with Quick first start on; worth it if that option is ever recommended).

### 8. ASTC transcodes batched and a system-RAM BC cache (TICK-051), and ASTC kept as BC1/BC7 (TICK-031)
- **What**:
  - TICK-031 (1d87de77) is a new encoder, `shaders/astc_bc_encode.comp` (344 lines, written for HL): BC1 for alpha-free ASTC
    with blocks of 6x6 or larger (alpha read from the ASTC endpoint modes on the CPU), BC7 modes 6 and 5 otherwise. Every
    2D ASTC texture from 64 KB is kept compressed. It adds spare images and a log by ASTC kind.
  - TICK-051 (27d1d35e, 4b170f0a, fb458793): `RX_VK_ASTC_BATCH` transcodes up to 8 (level, layer) pieces per group, each in
    its own scratch layer with one set of barriers per group. `RX_VK_BC_CACHE_MB` (1024) copies each batched transcode's
    blocks into host-cached system RAM, keyed by shape and an ASTC-bytes hash. `RX_VK_BC_CACHE_LAZY` stores only past 3/4 of
    the budget on cards allowed more than 9.5 GB.
  - Follow-up fixes the BC7/BC1 path needed: 0a45549f (alpha 0/255 exact), 0fdae598 (HUD outlines and rectangles from the
    encoder, issue 16), 7b131e46, 2bff40b4.
- **Measured**: TICK-031, RTX 5070 castle-move: decoded ASTC 3.0 -> 1.1 GB, nvidia-smi peak 10.07 -> 8.63 GB. TICK-051,
  PC 3050, 5 runs, castle-move: 1% low 10.8 -> 14.0, p99 75.8 -> 58.1 ms, spikes 8.6 -> 2.4 a run, fps 24.2 -> 25.2.
  hyrule-walk and kokiri-idle were within the spread. A transcode costs 1.2-1.8 -> 1.06 ms of GPU on the 3050. Not measured
  on the main PC.
- **Ours**: not present. Our path is Hookshot's BC3 (Eden's encoder; BC7 mode 6 opt-in via `RX_VK_ASTC_BC7`) for ASTC from
  2 MB with blocks of 6x6 and up; finer ones stay RGBA8 below 64 MB (all as BC3 under 8.5 GB allowed). Our tree deliberately
  runs **one scratch layer per run**: multi-layer runs drew dark tile outlines on an RX 6600
  (`gpu/vk/vk_texture.cpp:1145-1150`). It also has the AMD uneven-level resize (`bc_resized`, off by default) and
  `astc_reuse`.
- **Hardware**: the gain was measured on an 8 GB NVIDIA card. HL itself made the cache lazy on cards allowed over 9.5 GB, so
  on a 16 GB card it rarely stores. HL's batch path requires the full 8-layer scratch and the BC1/BC7 modes (not BC3), which
  our AMD layer workaround avoids. AMD risk: unknown.
- **Port**: large, ~700 lines of C++, a new shader and its SPIR-V header (regenerated with glslang), and the follow-up fixes.
  It conflicts heavily with our `upload_astc_gpu`, `bc_ready`, `bc_scratch_make`, `texture_copy_into_bc` and the AMD
  `bc_resized` code. Not randomizer code.
- **Risk**: high (visual regressions HL already had to fix twice, plus the AMD multi-layer artefact). Score: **skip for
  now**. Try item 6's budget first. Revisit BC1-for-opaque-ASTC alone if VRAM ever gets tight: it halves BC3's size with
  the same colour block.

### 9. The renderer's own allocations wait at Windows' commit limit (new_handler), and the host's own allocations too
- **What**: (a) HL 2ecb782c / 5e1ffc65 (Longshot f88e6e3a, #1291): `new_refused`, a `std::set_new_handler` installed in
  `mkwvk_init`. With under 4 GB of commit left, it retries every 50 ms for up to 5 s per thread, then asks the host for the
  out-of-memory notice (`MkwVkHost::out_of_memory`, an API bump). Before, a `std::bad_alloc` crashed with 0x20474343.
  (b) HL 29243133 (Longshot 2547a8f3, #341): `hos_xmalloc`/`hos_xcalloc`/`hos_xrealloc` for the NVN layer's tables and the
  video service's pool, with the same wait and then a clear out-of-memory fatal.
- **Measured**: unmeasured (crash fixes; HL issues #55 and #62 on 16 and 32 GB PCs).
- **Ours**: partly. We already have the texture budget's commit rule (`RX_VK_COMMIT_RESERVE_MB` 2560, plus page-file growth
  in `commit_room.h`, which goes beyond HL) and the guest commit wait (`host/mkw_glue.c:23-113`). We lack the renderer's
  `new_handler` (no `set_new_handler` in `gpu/vk`) and the host's `hos_x*alloc` wrappers.
- **Hardware**: Windows only. Matters on 16 GB PCs and with a small page file.
- **Port**: (a) ~40 lines in `vk_main.cpp`, a host callback in `vk_api.h` (bump `MKWVK_API_VERSION` from 23) and the host
  side. (b) ~130 lines across `host/mkw_glue.c`, `nvn_native.c`, `nn_video.c` and `hos.h`. These are host files, but not the
  randomizer's `oot_*` / `hos_oot*` ones.
- **Risk**: low to medium (API bump; a wrong wait could hide a real leak as a 5 s freeze). Score: **later**. Only if the
  owner ever sees out-of-memory crashes.

### 10. Samplers past the driver's allocation limit are retired and reused
- **What**: samplers with the same create info share one. Past 3/4 of `maxSamplerAllocationCount` (less 64), the least
  recently used sampler is retired and destroyed once the GPU is past it, and every cache drops it. A full room fails the key
  for that present instead of caching a null sampler. The sampler count goes into the `vk: VRAM:` line.
- **HL**: a07f7531 (port of Longshot #442 by Yanis Manseur), with `tests/test_sampler_retirement.py`.
- **Measured**: unmeasured. A suspect for "fps falling over long sessions" (HL issue 30): new sampler sets at every
  anisotropy, resolution or upscaler change, about 4000 allowed on NVIDIA.
- **Ours**: missing. `sampler_for` (`gpu/vk/vk_draw.cpp:~3092`) only creates samplers and never retires one.
- **Hardware**: NVIDIA's limit is 4000. AMD reports a far larger limit, so the owner gains little; it would only matter
  after many menu changes in one session.
- **Port**: medium (~150 lines). It interacts with our descriptor reuse (`desc_slotgen`) and the sampler cache, both of which
  must drop retired samplers.
- **Risk**: medium (a stale sampler in a reused descriptor would be a GPU fault). Score: **later/skip** for this PC.

### 11. Pipeline cache saves in play only when RAM has room, in Windows' background mode
- **What**: a save in play goes ahead only when free physical RAM is at least twice the cache plus 4 GB, at most once every
  5 minutes, on a thread in `PROCESS_MODE_BACKGROUND_BEGIN`. Otherwise it is put off, with the pipelines still owed.
  `RX_VK_PCACHE_PLAY_SAVE` (0 never, 2 as before).
- **HL**: 17578b5a. Part of the merge f1fee868 that fixed the "steady-play spikes".
- **Measured**: f1fee868, main PC (RTX 5070), Temple of Time: 1% low 24-36 -> 53-54 fps, 0.1% low 5-9 -> 42-43, longest
  frame ~260 -> 30 ms. But most of that gain is the other half (71bffdc5), a fix to **HL's own HL_MEM_COLD heap trimmer**
  (VirtualQuery passes of 300-810 ms), which we do not have. This half addressed one 14 s freeze while trimmed pages came
  back from the page file after a 1.27 GB save.
- **Ours**: different design. Play-made pipelines go into small per-generation files (`hookshot_vk_pipelines_play_<n>.bin`),
  the main cache is written in play only after 64 MB of growth (`RX_VK_PLAY_SAVE_START_MB`), and the fetch goes into a
  mapped file. That covers most of the cause. There is no free-RAM gate and no background I/O priority.
- **Port**: ~40 lines. Score: **skip** unless a freeze after a "pipeline cache saved" line is seen.

## Already in our tree (no port needed)
- **The 100-350 ms frames / 1% low work** (HL f1fee868, 71bffdc5): a fix to HL's own `HL_MEM_COLD` heap pass
  (`engine/host/hl_mem.c`). We have no such pass (no `HL_MEM_COLD` in `host/`), so neither the bug nor the fix applies.
- **TICK-008 pipelines noted and precompiled; draws never wait** (dbad506e, 6bba9f16, da2a0046, bf912b7e): ours has
  `hookshot_pipelines.bin` notes, precompile, `vk_predict.cpp`, `warm_bounded.h`, `RX_VK_PIPE_SKIP` and `RX_VK_PIPE_WAIT_MS`.
- **TICK-038 compute pipelines built on first use, -2 GB RAM** (f140ddb6, `RX_VK_LAZY_COMPUTE`): ours keeps ready only the
  compute programs this install dispatched (`hookshot_computes.bin`, `RX_VK_PRECOMPILE_COMPUTES`,
  `gpu/vk/vk_draw.cpp:1636`), which targets the same "few GB of RAM". HL's `RX_VK_CS_MODULE_DROP` (dropping the compute module
  once its pipeline exists) is not in ours. That part is small and could follow item 4, but it is unmeasured on its own.
- **TICK-007 texture descriptor cache** (c79ad778): ours has Hookshot #1330's descriptor slotgen and the sampler cache (menu
  rows Descriptor reuse and Sampler cache). HL's extra per-slot 4-way table gave descriptors 2.77 -> 2.29 ms with fps
  unchanged. Skipped: no fps gain.
- **TICK-023 VRAM breakdown, budget from the driver, big images dedicated, idle mirrors freed** (75ae6549), and
  **TICK-030 teal ground** (bdc34602, which undid TICK-023's dedicated memory for BC images): ours has the periodic
  `vk: VRAM:` line, the budget from the allowance with the 90%/97% rules, VMA compaction (`vram_compact.h`, which goes beyond
  HL's "free in blocks" fix), `mirror_trim.h`, `retired_give_back.h` and `mirror_budget.h`. HL's `RX_VK_BIG_IMAGE_MB`
  dedicated images were superseded by compaction, and they caused TICK-030's regression.
- **TICK-036 Market ground white/mint** (82460cd1): ours has `mirror_inherit.h` (#1127, the CPU's newer pages kept). The
  "retired mirror filled by a later segment" case cannot happen here: our mirrors are never made inside a parallel segment
  (`gpu/vk/vk_memory.cpp:4236-4245`, #994).
- **Drawn terrain tiles written back** (c268d53d, ground garbling; Longshot 06a892fc): ours has `drawn_writeback.h`.
- **Texel buffer views tied to their buffer** (4871f026, 87878768, 1914073a; Longshot a23587f5): ours has the registry
  (`release_texel_buffer_views`, `tests/test_texel_buffer_ownership.py`). Only the format check (item 3) is missing.
- **ASTC decode and unswizzle stores bounds-checked (AMD)** (19edce9b, 03e0a4aa): ours has Hookshot 6e11217e (#2442).
- **The commit-limit texture rule** (part of 2ecb782c): ours has it, plus page-file growth (`commit_room.h`).
- **Render targets reused** (d734ed6d, #994), **dead targets every present** (3f22c6cc), **staging arenas kept**
  (1850c017, `RX_VK_STAGING_BURST_S`), **spans aged once a present** (a86cfe8e, #2420), **6 workers at 16+ threads**
  (76ce735d), **zstd program cache** (1d6f92d2; ours has #1630), **write the pipeline cache only when changed** (81e0a4f2),
  **one BC3 scratch layer** (2bff40b4; ours defaults to 1 everywhere), **handle tables as descriptor arrays** (97e584e3;
  ours has Lichii bd0171f7): all present.

## Skipped
- **HL_PROG_MEMO** (3c1feac7, c1254e8b, 504f8362; `vk_shader.cpp`): HL's own A/B was within noise (80.9 vs 79.4 fps).
- **The render target pool given back in two steps** (4134dea1, Longshot #637 part): for 6 GB cards; our compaction and
  `target_pool` rules differ. No gain at 16 GB.
- **`RX_VK_TEST_VRAM_MB`** (b62c39e5): a developer tool to fake a small card; nice to have, not needed.
- **iGPUs keep every large ASTC as BC3** (7b131e46), **dummy image view without nullDescriptor** (45c5fc7d), **AMD iGPU
  decodes ASTC on the CPU** (ed9145d6): not this hardware.
- **The frame trace columns and `tools/bench/spikes.py`** (27d1d35e): ours already has `RX_VK_FRAME_TRACE`. spikes.py
  could be copied as a tool if a stutter hunt starts.
- **BC cache lazy rules, capture spares by fit** (fb458793 and the WIP commits): depend on item 8.

## User-visible settings or features in this area that we lack
- None of note. HL's user guide offers no texture or VRAM settings. Everything above is env switches. Our launcher and menu
  already have more here (presets, ASTC as RGBA8, Descriptor reuse, Sampler cache, Quick first start).

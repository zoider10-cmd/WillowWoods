# HeyListen, 2026-11-20 (539d20ad..origin/HEAD, 194 commits; read only)

Read from the clone's history, without checking it out; nothing built, run or installed. Our tree checked at
amd-fix-sharkiix-version 55a6cc19. "Longshot xxx" means the change is a port of that Longshot commit. The Longshot survey
covers those, so for them this note says only what HeyListen added or measured and whether we have the change. Ranked for
the owner: RX 9070 XT, Windows 11, 120 fps, 1% lows, stutter at area changes, AMD discrete correctness, randomizer-safe.

**A correction to 2026-11-17 (area4_features.md:176):** it said "our rx_backend texel wrappers already give the core up". They
do not: `rx_nvn_read_texels` / `rx_nvn_write_texels` (host/rx_backend.c:561-587) call the back end with the virtual core
held. Only invalidate, guest_imported and vmap_changing give it up. That makes item 1 a real gap.

## Port first

### 1. Texel copies give up the virtual core (HeyListen 77bd2f86 Mooseca, v0.4.3; 01cc46c4 = Longshot 1780fbe0c's off switch)
- **What:** `rx_nvn_read_texels` / `rx_nvn_write_texels` wrap the back-end call in `hos_vcore_away()` / `hos_vcore_back()`,
  as `rx_nvn_invalidate` already does. Our `read_texels` runs `finish()` and then takes `replay_mu`, which the replay holds
  for a whole submission. `write_texels` waits too for a GPU-drawn texture. Meanwhile every game thread allowed on that
  core waits.
- **Gain:** Longshot measured about 1 s of stall at an area change. HeyListen's evidence is the escape logs (sead::MainThread
  at boot, ModuleSystemWorker4 in the GPU wait). Neither gave an fps number.
- **Ours:** missing (see the correction above).
- **Hardware:** none. Off switch: HOS_TEXELS_KEEP_CORE=1.
- **Port:** about 10 lines in host/rx_backend.c, plus the test (tests/test_vcore_texels.py). A write kept before the back
  end starts (`keep_early`) must not take the core away. Host only: no lift, no randomizer file.
- **Risk:** low. It is the same pattern as invalidate. **Score: first.**

### 2. Retired pools nothing needs are set aside (4971cd02 = hookshot-nr 20352f9c, pixl27)
- **What:** each area change retires ~30 import pools. In our tree `retired_pools`
  (gpu/vk/vk_memory.cpp:4230) is never shrunk, and it is walked at every submission (`retired_imports_give_back`), at the
  game threads' frees (`memory_guest_imported`), at every mirror made, at `trims_settle`, and in more places. HeyListen
  counted 798 retired pools in a 10-minute tour of six places. A retired pool that holds nothing (no import, mirror,
  shadow or pending state, and the GPU past it) moves to `retired_done`. The node stays alive at the same address, and its
  `shadow_known` vector is freed. Every 600 submissions it rechecks the newest 256 and returns any in use.
- **Gain:** not measured as fps. The new log line gives the walks' ms. The cost grows with session length, so a randomizer
  run (many warps) pays the most.
- **Ours:** missing. Our `Pool` has the same fields (memory, pieces, buffer, mstate, mirror_alloc, shadow, shadow_alloc,
  inherit_pending, shadow_known). Our sparse-mirror `blocks` must also be empty before a pool counts as idle. Leave out
  HeyListen's `lazy_held` / `held_told`.
- **Port:** about 70 lines in vk_memory.cpp, with the RX_VK_RETIRED_COMPACT=0 switch. Check `retired_pools_count` and the
  stats. Renderer only.
- **Risk:** medium-low. Nodes are never freed, only moved, so pointers to them stay valid. A/B after a long multi-area
  tour, not a Market stand. **Score: first.**

### 3. Emptied memory blocks go back to the driver off the render thread (2e1f5766 = hookshot-nr 8cb5a334, pixl27)
- **What:** VMA gets our own `vkFreeMemory`, which queues the call to one thread, in order (gpu/vk/vk_vma.cpp, about 70
  lines). The first four frees, every 64th and any over 20 ms are logged with their times.
- **Gain:** upstream measured 4-7 ms a block on an RTX 3060 Ti and ~250 ms a block on a player's RTX 4080 SUPER (83 in a
  row at the Market). The cost on AMD Windows is unknown, and the log line answers it on the first run.
- **Ours:** missing. `vma_init` (vk_vma.cpp:46) passes only the two loaders. We never call vkDestroyDevice, so a detached
  free thread is safe.
- **Hardware:** none. Off switch: RX_VK_FREE_LATER=0.
- **Risk:** low. The heap's budget lags a few ms behind the free, which does not matter on 16 GB. **Score: first.** Read the
  log's times first: if AMD frees in under 1 ms, the change buys little.

### 4. Extra descriptor pools are kept, not made and destroyed every recording (6ed31109, HeyListen's own)
- **What:** a recording that outgrows its pool (8192 sets / 32768 descriptors) makes another pool with
  vkCreateDescriptorPool, mid-draw on the render thread. In our tree the next recording destroys it again
  (gpu/vk/vk_draw.cpp:6175-6178), so the cycle repeats every recording in Hyrule Field and Kakariko. HeyListen resets and
  keeps the extra pools (`extra_used`, `extra_idle`) and destroys idle ones after 120 recordings.
- **Gain:** HeyListen's telemetry from a Radeon 780M in Kakariko showed 23 "descriptors" hitches (3.8 s). Part of that was
  texture work counted under the wrong cause. No fps A/B.
- **Ours:** missing. Our log already counts these pools: "... N descriptor pools made when a recording's own ran out" every
  3000 recordings. If the owner's log shows that number climbing in Hyrule Field, port this.
- **Port:** about 40 lines in vk_draw.cpp (`RecordingRes`, `bind_descriptors`, `draw_begin_recording`), with
  RX_VK_DESC_POOL_KEEP=0 to turn it off. The profiling split (DescPart) is optional.
- **Risk:** low. **Score: first if the counter moves, else skip.**

### 5. BC re-encode of ASTC levels of 1024 or less, eight layers a run (fb296071 = Longshot 65488813f; 5ea264f0 turned it off by default)
- **Measured on the owner's own card** (GrimVisage, RX 9070 XT): each terrain material array (1365 x 1365 x 90, 11 levels)
  took 51 ms to transcode one layer a run, and 15 ms at eight a run. That is about 70 ms saved at a Kokiri or Hyrule Field
  arrival (two arrays). HeyListen turned it off by default the same day because upstream saw grid lines on Hyrule Field's
  far ground with multi-layer runs on an RX 6600. Neither reported it on RDNA 4.
- **Ours:** one layer a run by default (vk_texture.cpp:1215-1221, the same RX 6600 note). **No code is needed to try it:**
  RX_VK_BC_LAYERS=8 already gives eight-layer runs at every level, through a 160 MB scratch instead of a small second one.
  A/B it at a Kokiri arrival and look at Hyrule Field's far ground for dark tile lines.
- **Related (33bf50cd = Longshot 7daafa7a, ASTC part):** our decoder (host_shaders/astc_decoder.comp:1436) stops only at the
  destination image's edge. With the 2048 scratch, threads past the mip's blocks read staged bytes beyond the mip's own,
  even past the buffer: a read the driver may fault on. They also write scratch texels outside the mip. A BC block at the
  mip's ragged edge (1365 >> k is never a multiple of 4) then encodes those texels. That *may* be the grid lines' cause.
  This is a hypothesis, not checked. The fix adds blocks_x/blocks_y to the push constants and an early return, about 30
  lines; the SPIR-V header is regenerated from our .comp. **Score: try the switch first; the bounds fix later, alongside it.**

## Later

### 6. Indirect mesh draws converted in batches at the game's barriers (c9603f66 = Longshot 9027e7374)
- **What:** today every vegetation indirect mesh draw (grass, ferns, leaves) ends its render pass, records three barriers, a
  fill and a copy, and begins the pass again (`mesh_indirect_convert`, vk_draw.cpp:7336). The change fills the argument
  ring with 1s once (slots 48 bytes apart) and converts the draws between two of the game's full barriers together.
  RX_VK_MESH_CONV=2 is the default; 1 is the ring fill only.
- **Gain:** unmeasured in HeyListen; the Longshot survey has upstream's numbers. The win is in foliage areas, on any GPU.
- **Why HeyListen's diff:** it is the better template for us. It was written onto the same EvilOOT conversion we have
  (it keeps RX_VK_MESH_IND_RAW and RX_VK_G3_MESHCOUNT, and our compute fallback reads the converted records).
- **Port:** large (vk_draw.cpp core, mesh_conv.h, two tests; 1634+/749-). It must respect our branch's RX_VK_MESH_ARGS
  (amd-fix) rewrite path. Renderer only. **Score: later, with an A/B in Kokiri / Hyrule Field.**

### 7. A draw is left out for want of its pipeline only where the next frame redraws that target (05378921 = hookshot-nr 41f37acf)
- **What:** our `may_skip` uses `targets_persistent` (vk_draw.cpp:5418): any target drawn in an earlier frame. That covers
  pieces drawn once into a kept target (a decal, a tile, a cached shadow). If such a draw is left out, it stays missing
  until the area reloads: upstream's "striped ground" (Fire Temple, Flix's route). The change skips a draw only when every
  target was drawn in the frame before and its viewport and scissor cover nine tenths of the target (`targets_redrawn`).
  Other draws wait. The first 40 decisions are logged.
- **Ours:** missing. Quick pipelines make the case rarer here but do not remove it.
- **Port:** about 25 lines. Needs a per-target last-drawn frame (we have `first_render_frame`). Off switch:
  RX_VK_SKIP_PARTS=1. **Score: later, cheap correctness fix.** It can add short waits on cold pipelines.

### 8. Each replay command buffer ends with MEMORY_WRITE -> HOST_READ (f0f7ae92 = Longshot 905e36a9)
- **What:** without this barrier, the host's reads of what the GPU wrote (copies, queries, readbacks) are not made visible
  as the spec requires. HeyListen also covered its early-replay paths.
- **Ours:** missing in `submit_recording` (vk_replay.cpp:857). We only have the capture copies' and the dumps' own barriers.
- **Port:** about 15 lines; no switch is needed. **Score: later, cheap.** AMD's driver flushes at the end of a submission in
  practice, so expect no visible change.

### 9. Capture buffers: allocation outside the lock, freeing on a thread (1a89977a and 258b2148 = Longshot #1553 and 8f462db52)
- **What:** our `cap_buf_get` (vk_memory.cpp:1254) holds `cap_free_mu` through `create_buffer_cached`. Our own comment says
  that is ~100 ms of vkAllocateMemory on AMD for a large buffer, and the replay's `cap_buf_free` waits on the same mutex.
  `cap_buf_free` also destroys buffers past the spares synchronously under that lock (Longshot measured 25-49 ms takes).
- **Ours:** missing, but our `cap_buf_free` already has Longshot's `from_worker` / `cap_shutting_down`, so Longshot's own
  version fits us better than HeyListen's (which was adapted to an older four-argument form). HeyListen measured nothing
  beyond Longshot. **Score: for the Longshot survey; AMD-relevant.**

### 10. Host-pointer imports: memory type per pointer, checked against the buffer (b82437b7 = Longshot a48592e3, 26dd54fc)
- **Ours:** the type is asked once for every later pointer and never checked against the buffer's memoryTypeBits
  (vk_memory.cpp, `static uint32_t type`). That is Vulkan-illegal, though AMD's Windows driver answers the same for every
  pointer. About 30 lines, AMD import path. **Score: later.**

### 11. Native HDR with frame generation: 10-bit frames (27d3d4e1) and the picture's kind travels with it (770fc3ce), HeyListen's own
- **Ours:** `fg.frames` and `set.frame` are RGBA8 (vk_framegen.cpp:368/375), so Native HDR loses two bits of PQ on every
  shown frame (banding in dark areas and the sky). `present_image` takes no pq flag, so at a switch between SDR and HDR
  pictures (a loading screen, then play) one frame can be encoded as the other kind (a flash).
- **Port:** 27d3d4e1 is ~400 lines plus regenerated fg_copy/fg_synth SPIR-V (FG_PQ); 770fc3ce is ~30 lines.
  **Score: only if the owner plays Native HDR with frame generation on.**

### 12. Smaller items, later
- **1696f804 RX_VK_READ_MAPPED (Longshot #1553):** our `submitted_read_locked` overlays captures page by page from the
  first page's guest address, as if guest memory were contiguous. That is wrong for a virtual (sparse) GPU address that
  crosses a page. A correctness fix of about 40 lines.
- **c782188b 5.1 centre spread (HeyListen's own):** the centre is also mixed into front left and right at -3 dB, so a
  virtual-surround headset that drops the centre still plays voices and the ocarina. Our `au_layout_channels` already sends
  devices without a full speaker mask to stereo. This covers only devices that report a proper 5.1 mask but play no
  centre. About 30 lines; off switch HOS_AUDIO_CENTRE=0. Only matters if the owner outputs 5.1.
- **f6063783 sparse BC usage (Longshot 8e62ff1f):** we query sparse support with TRANSFER and SAMPLED only, then create the
  image with x.usage (vk_texture.cpp:2339 vs 2516). Sparse images are only made for arrays over the budget, so this is rare
  on a 16 GB card.
- **b80a5999 sync-object table (hookshot-nr f0fab2a1):** a live byte per slot makes a rehash 9x faster upstream (62.9 ->
  6.85 ms at 524k slots). A rehash only happens when the table doubles, a few times a session. Our table has no
  HOS_OBJ_PACK, so the port is simpler than HeyListen's.
- **7534b45c pool calls give up the core:** boot-time only (an Intel Linux 165 s hold).
- **81271a62 doubled separator under \\?\ (Longshot b34daaee):** our `fs_wide` (host/nn_fs.c:25) does not collapse `//`. In a
  game folder deep enough for voice paths to pass 240 characters, cutscene voices go silent. One loop; only matters for a
  very deep game folder.

## Longshot #1553 parts HeyListen took, with nothing measured of its own (for the Longshot survey)
These came with no HeyListen measurements; status in our tree for each:
- cff2561a HOS_EVENT_FAST: we lack it; `event_signal` locks and calls WakeAll every time (host/nn_os_sync.c:715).
- 2cbcdb0c HOS_VC_YIELD_FAST: we lack it; `vc_yield` takes vc_lock every time (host/hos_thread.c:1946).
- a2c03f76 RX_VK_IMPORT_NEIGHBOUR and fd1b7e57 RX_VK_CAP_RANGES_REUSE: we lack both;
  `refresh_pool_ranges_locked` bumps `cap_ranges_ver` every rebuild.
- 2eef92fe HOS_REC_LOG_AWAY and bfb4b883 RX_VK_WRITE_HISTORY: we lack both.
- 34cf894c sampled-target mask: half done in our tree (we keep the mask, but still run `std::find` over `ps.sampled` at
  vk_draw.cpp:8521).
- c2828a19 HL_STREAM_AWAY: we already have Longshot's form (host/hos_zstd.c:348).
- b733f81d: Linux only.

Other Longshot ports in this range:
- bbc47d1a OptimizeChangeBank hold (Longshot c88f70440): we lack it. HeyListen rebuilt it as a hook in their lift step;
  Longshot's own nx2/oot_patches.py form fits our tree better. The randomizer is affected only through the preload choice.
- 2005df89 HOS_OS_YIELD: we lack it. Longshot measured no difference on 16 threads (longshot-2026-11-18).
- ece2d776 HOS_FRAME_CARRY: matters only below 60 fps at a 60 cap.
- be30109d / 24421c4a: VRAM given back (frame generation images, streams, pools); nothing to gain on 16 GB.
- b556d431 ASTC chunking: integrated GPUs' 2 s WDDM limit (we keep the CPU-decode rule).

## HeyListen data worth knowing
- **bcf53ef5:** HeyListen turned Longshot's page-mark bitmap off by default. On a 7800X3D with an RTX 5070 it measured 87.0
  fps without and 85.9 with, because HeyListen's own mark grouping (A64_MARK_STACK / group_marks) had already taken the
  gain. **We have no mark grouping, so keep ours on** (nx2/build.py:963). Longshot measured 40.4 -> 46.1 fps on a 5600X.
- **bd86dda1 storm hold:** for cold Market arrivals on an i5-10400F with an RTX 3050, demand ordering, the release on live
  jobs and the extra workers each shortened the time to the first clean picture. No ms numbers were given.

## Skipped (one line each)
- RX_VK_WAIT_OWN (1573e37c, 74ae61bd, bfac31a5): AMD **integrated** GPUs only (no VRAM mirror). It is not on for discrete
  cards.
- Storm hold, its workers and demand order (eb5482ff, 30b4c61e, f2970097, f8299bbe, c35ded20, a3102325, bd86dda1): they hide
  partial frames on cold-cache arrivals by withholding the present (a freeze instead). Prepared caches rarely hit this.
  Revisit only if arrivals after a shader-stamp change look broken.
- a7b8bf8e mesh-only fallback: Windows Navi 21-23 (RDNA 2) only; the owner has RDNA 4.
- 214df57a 32-lane pin within maxComputeWorkgroupSubgroups: expected to be a no-op on AMD's Windows driver (32 x 32 = 1024
  reaches any workgroup). We don't log that limit, so this is unverified.
- 74c83579 8-bit index quads: only for GPUs without index_type_uint8; RDNA 4 has it.
- ae33b4bb vertex divisor feature: RDNA 4 supports the feature (ours reads only the extension).
- 64673441 AMD unoptimized retry: ours has it (ReLink 3346f72, vk_draw.cpp:1515).
- 041133d8 module fault guard: ours has it (4f96efaa).
- f3e2b580 widen alpha: ours has it (691bc456).
- a8f74331 precompile stall: ours has it (Mako 4.2, vk_draw.cpp:10422).
- ee32a02b capture wait follows the GPU: ours has it (vk_memory.cpp:3130).
- f3b616b2 push-constant index fix and 73085e26 fog boxes: ours has both.
- 11dd1b66 BC upload over render-target storage: ours has it (WillowWoods ff479e988d).
- f64c0fab above-60 fixes (ledge, Zoras, ripples, song notes): ours has them (5f178a43, e64f73d1, 523349fd, 270bacf6).
- 9e486fe2 shader stamp leaves vk_api.h out: ours has it (nx2/translator_files.py).
- c802f023 voice option, efbe03ae and db26e6f9 HUD layout, 433c43a0 and f11cb284 keyboard prompts: ours has them.
- 29f37fcb, cd8961a3, def4caf0, 72781928, 356af26e, a0dc9180 PsychoV35 and its upscaler routes: ours has them from
  Hookshot/Longshot.
- 9efce641, d17f7c83 HeyListen's own HDR tone mapper, later removed again: nothing to take.
- 73cdd2cd, 8d6cecb4 DLAA before the bloom; f0ae985b, 53192ed9, ad2f8bf7, 69ad6eb3, c1d1c880, f20ebb8a DLSS / DLSS FG: NVIDIA
  only.
- 2b054bc4 strict readback bound: RADV, and we have no strict wait. bf72754f: the same mechanism.
- 33873659 meter zero/hold (Hookshot 53eb0441): our exposure-meter handling is our own (PR 430). Look at it only if white
  flashes are reported.
- bccc744c lazy write-back of small pools (issue 50): fixes HeyListen's own lazy write-back, which we don't have.
- 3cefe030 release hint (API 19): our releases are queued (async) or held (PR 430, vk_replay.cpp:6922). Not needed.
- 696a0022 prediction in play: ours already builds the prediction on 2 idle-priority threads (RX_VK_PREDICT_BG).
- e6e9ee55 uniform-buffer snapshot default: integrated and Intel only.
- 28684ef0, 48304afd compile gate and memory pressure; f3ec8776, ee9d6f58 RADV mesh rules; b733f81d; adbb43ca; e768f5db;
  8587a17f: Linux only.
- c058831e EQUAL depth margin: Intel only.
- 43adec0c, b248a854, 068033d9 (issue 99): the device-0-first rule was reverted on Windows; only a log line remains.
- 561e2b31 menu clip rects in a small window, 5385a5d5 / 208cc68e row moves, b3fd8afe hidden dependent rows: HeyListen's menu
  layout. Ours differs (help_box with y_min/y_max).
- f46cd50f software Vulkan device; 55658dbf romfs heap check; d688642b movie logs; 15d266ef fallback log: diagnostics.
- e9792ebc, 0dddae9a, a33a0f2f, 25860a45, 50ff816f, 2567bf38, 5d3973ee, 6bbbdb57, 0dd5aaa0, c2e402bf, e370a4bb, 9972ecfe,
  7afd14ab telemetry; c5d39431, 14c802c5, 03372e5b, 76d1279e, b8e153cb, 8b91125c crash reports; 77fbfbe6, a5ac5fe8, 9483a8ae
  launcher: none for the frame.
- 45e4af77 and bcf53ef5 mark bitmap: ours is on already (see the data above).
- Tests, docs, switch lists, fix-ups and build bookkeeping (6990c23b, 8506ca59, 509f58f1, 986a5cee, 76fcbd57, 1388a45b,
  da577c4d, 8282517d, 08f78a9d, ce300c39, 41ddf986, 34e7a9d5, 9c225cc2, 46924f01, d5a52b59, 2821236f, 7ad6f338, 233e4282,
  893ae408, db12cede, 554772f5, 80c913d4, 9de493ff, 9d4dfbf4, ad43caeb, b0a75da4, f2b5b78e, a2521874, c02a860f, d09751de,
  9b0e4010, 3640efca, f79b0d24, 2e55aaf6, cd1668d0, b9942cbe, 03ec8c7d, b6fbf49b, 91283fd0, 4f99171e, 3e1ad79e, 258c5622,
  006f2403, 137d9fe5, bf56da32, 3515f45a, 90a0bfc3, 39d64aa1, 00d81b03, 151a4b44, 03b5400f, 10efdee8, d052eb63, 63138156,
  8768f2cf, 17d2a8db, 466aa566, aa32736f, a967e38f, 7534b45c's test): none.

## User-visible settings HeyListen has and we lack
- **V-Sync mode row** (226181df): FIFO with 2 images (lowest latency), FIFO with 3 images, or Mailbox. AMD's Windows driver
  has no Mailbox, and our swapchain asks for at least 4 images (vk_main.cpp:1115). So under FIFO we can queue about 3
  frames, ~25 ms at 120 Hz. A 2-image FIFO choice would help latency on the owner's card.
- **VRR row** (439b8344): FIFO, a borderless popup window Windows can flip, and the frame limit held at refresh - 3 when
  above 60. Ours has no row for it.
- **Frame rate limit "Unlimited", with the limit as the presented rate** (b9f66b2f): our limit rows differ, so check before
  copying.
- **Rows hidden while their setting is off** (b3fd8afe): HDR rows without an HDR screen, frame-generation rows when off.
- **Crash backtraces named on the player's PC** (c5d39431): .sym tables beside the exe, so reports group by function
  across builds.

## Taken here (2026-11-20 evening)
- Item 1 (texel copies give up the virtual core) taken from Longshot 1780fbe0 as 078f364f, with its switch and check.
- Item 2 (retired pools set aside): our longest logged session of the owner's reached 256+ retired pools; a walk of that
  size costs microseconds a submission. Left for later.

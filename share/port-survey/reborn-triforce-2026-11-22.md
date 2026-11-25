# Reborn and Triforce, 2026-11-22 (read only)

Nothing was built, run or installed; no file of ours but this one was changed. Both ports are GPL-3.0-or-later.

**Summary.** Reborn (6babdc22 -> 5d00dad9, v1.1.5) is small: a stutter pass on its capture-buffer pool and the idle
mirrors' frees (measured on a 9800X3D + RX 7900 XTX, AMD Windows, our closest hardware yet), two gameplay options (pick
the ocarina actor; unlimited amiibo scans), and picks from Longshot and ProjectReLink we have already reviewed. Its
parallel-replay trial (on, then off again: 55 -> 42 fps on a 9800X3D + 7900 XTX) agrees with ours being off. Triforce
(043db52c -> e6f2f248, v0.7.0, 529 files, +56k lines) is a "performance audit" of about 170 numbered items, most off by
default or marked "not yet run in the game", many after "Source A" and "Source B" (other ports' work, much of which we
merged already: drawn page map, wrote regions, pend-held flush, surface-lost recovery, dead-target sweep at 1 present,
shadow-slot bucket, segment heap, movie acquire, short-sleep timer, FMA steps). Two things stand out as new for us. First,
the capture-buffer pool: Reborn and Triforce now fix it separately, as Longshot and HeyListen did before (Longshot #1553 and
#1848, "later" on 11-20). That makes four ports with the same fix, and Reborn's numbers are from an AMD card, so it moves up.
Second, smaller replay CPU cuts: the index-buffer rebase (about 2,900 vkCmdBindIndexBuffer calls a frame in the Market) and Reborn's
paced idle-mirror frees. No gain anywhere below is measured on an RX 9070 XT.

## Ranked candidates

### 1. Capture buffers: refill the spare a load took, keep small captures out of big spares, make and destroy off the lock — PORT FIRST (status raised)
- **What:** our `cap_buf_get` (gpu/vk/vk_memory.cpp ~1255) makes the 32/64/128/192 MB spares once, at the first capture,
  and never again; takes any spare that fits (a 2 MB capture can sit in the 192 MB spare for 24 submissions, so the next
  load makes its own on the game's submitting thread); and creates a new buffer with `cap_free_mu` held. `cap_buf_free`
  destroys past-limit buffers on the replay's thread inside that same lock. Triforce's `gpu/vk/cap_spare.h` (64 lines,
  pure rules; MEM-33, `RX_VK_CAP_SPARE_FIT`, on) describes our exact code as its "before" and fixes all three. `RX_VK_CAP_FREE_ASYNC`
  (on; `destroy_buffer_later`, vk_memory.cpp ~1999) destroys the given-up ones on a thread. Reborn did the same in its own way:
  adcb6f7 `ocr_capture_pool_policy.h` (demand by class, refill on a worker after each take, up to 3 per class), and 5d00dad
  `cap_destroy_later` plus `keep_hot` (keep a class taken in the last 10 s while RAM allows).
- **Gain:** Reborn, 9800X3D + **RX 7900 XTX**: 61 "capture pool miss" lines in three runs, 10-63 ms each, 964 ms in all,
  at scene loads. Destroying 64-128 MB buffers (VMA FreeDedicatedMemory) was 4.2% of the game thread in the Market's slow
  seconds. No "after" figure is given (VALIDATION-1.1.5.md: "not a controlled performance A/B"). Longshot #1848 (RTX 4070
  SUPER): takes of 10 ms or more 70 -> 2 an arrival. Triforce: unmeasured ("not yet run in the game").
- **Ours:** missing. HeyListen 11-20 item 9 and Longshot 11-20 item 10 point at the same code.
- **Hardware:** all. AMD's driver commits about 0.8 ms per MB when a buffer is made (our own comment), so AMD gains most.
  Holds no more than the 768 MB / 12 spares we already allow.
- **Port:** take Triforce's version. Its rules header drops onto our functions unchanged (same names: `cap_buf_get`,
  `cap_prewarm_class`, `cap_buf_free`, `cap_spare_max`). Then add `destroy_buffer_later`, ~150 lines with its test
  (tests/test_capture_spare_reuse.py, test_cap_free_async.py). Renderer only: no lift, no randomizer.
- **Risk:** low-medium (a buffer freed while the GPU reads it is a device loss; only spares go there, and the tests check
  that). Measure: area changes (teleport tour) with the frame log; count "capture" in slow-submit lines.

### 2. Long-idle mirrors given back a few at a time (Reborn adcb6f7, `OCR_MIRROR_IDLE_MB`) — PORT FIRST (small)
- **What:** the mirrors one load made were all synced at the same submit, so they all pass `kLongIdle` (6000 submissions) at
  once and `mirrors_give_back` frees all of them in one call on the submitting thread. Reborn frees at most 32 MB of
  long-idle mirrors per call (at least one) and calls again every 8 submissions until none are left. Frees made for room are
  not held back.
- **Gain:** Reborn, 9800X3D + RX 7900 XTX: 22 mirrors (475 MB), then 53 more (951 MB), went in two calls. The game's main
  thread then sat 90 ms and 477 ms in that submit, using no CPU time (the driver's frees). With the change: unmeasured
  (diagnostic line only).
- **Ours:** missing; our `mirrors_give_back` (vk_memory.cpp ~5119) and `memory_begin_submission` (~5460) are line for line
  the code Reborn patched.
- **Hardware:** all. AMD Windows measured. Off with `OCR_MIRROR_IDLE_MB=0` (rename to an `RX_VK_` switch + switches.def row).
- **Port:** ~25 lines in vk_memory.cpp. Renderer only.
- **Risk:** low (idle mirrors are held some seconds longer, within the budget). Check: a long session in one area after a
  teleport; look in the log for "mirror ... given back: idle" in bursts and for slow submits about 100 s after a load.

### 3. An indexed draw's index buffer bound at offset 0, its offset given as firstIndex (Triforce `RX_VK_INDEX_REBASE`, DESC-12) — PORT, gate
- **What:** our `bind_index` (gpu/vk/vk_draw.cpp ~7805) skips a bind only when buffer, offset and type are unchanged. The
  game's draws share one buffer at different offsets, so nearly every indexed draw calls vkCmdBindIndexBuffer (Triforce
  counted about 2,900 a frame in the Market). Bound at 0 with the offset added to firstIndex, the skip holds until the buffer
  changes. Only where the offset is a whole number of indices; indirect draws are untouched.
- **Files:** gpu/vk/index_rebase.h (30 lines), vk_draw.cpp `draw`/`bind_index`, tests/test_index_rebase.py.
- **Gain:** unmeasured in fps. HeyListen's audit measured vertex + index binds at 0.91 ms a frame of replay work. On AMD a
  driver call costs about twice NVIDIA's (Longshot's Test Farm on this card), and our Market is bound by the replay's CPU work.
- **Ours:** missing. **Hardware:** all; on by default there, `=0` off.
- **Port:** ~40 lines, renderer only. **Risk:** low (index range arithmetic; a wrong firstIndex shows at once as broken
  geometry). A/B at the Market.

### 4. Character shadow maps: fewer sizes, old sizes let go sooner (Triforce `HOS_OOT_SHADOW_STEP` GAME-05, `RX_VK_SLOT_RETIRE` TEX-76) — LATER
- **What:** the game sizes each character's depth shadow map from the screen every frame (384-1,920 a side), so moving
  characters keep asking for depth textures of new sides. STEP rounds the one read of the side (f_802640a0, `ldr w10,
  [x21,#0x4e8]`) up to a multiple of 64 through the host: 25 sizes, which the render-target pool then serves. SLOT_RETIRE
  lets an overdrawn old size go after 16 unused presents instead of 120.
- **Ours:** we have Mako's `HOS_SHADOW_BUCKET` (host/nvn_native.c ~627, shadow_slot.h): it keeps the storage addresses
  stable, but each new side is still a new image. STEP and SLOT_RETIRE are missing.
- **Gain:** unmeasured (no fps figure in the row).
- **Port:** STEP is a **lift patch in nx2/oot_patches.py** (`patch_shadow_step`, ~40 lines + host/oot_shadow_step.c/.h ~65),
  so it touches the randomizer's file and needs a re-lift; SLOT_RETIRE is ~50 lines in vk_texture.cpp `texture_sweep`.
- **Risk:** medium for STEP (game code; a map at most 63 texels a side bigger, projection unchanged). Try SLOT_RETIRE
  alone first; gate both at Kakariko (people moving).

### 5. Slow-submit line split by thread: own memory work, CPU time vs wall time (Reborn adcb6f7) — LATER (diagnostic, small)
- `vk_replay.cpp` SlowWatch: each slow submit's line names its submission and this thread's maps/capture/collect, the rest,
  and "on CPU x of y ms" (GetThreadTimes): a stall where the thread was not running (driver frees, paging) shows plainly.
  Also counts every slow submit (not just the first 80) and logs those over 50 ms later in the session. ~60 lines, no
  behaviour change. Useful for chasing the 1% low; it is how Reborn found items 1 and 2.

### 6. Shader-cache checks: predicted and light-precompile pipelines verified at start (Triforce `RX_VK_PREDICT_CHECK` PIPE-68, `RX_VK_BUILT_CHECK` PIPE-21, `RX_VK_PREPARE_RECHECK`) — LATER (adds to 11-20 item 7)
- At a start whose record says "all built", up to 12-24 recorded pipelines are built again and timed; if most are cold
  (the driver lost them: "AMD's Windows driver keeping a third"), they are all rebuilt behind the game or before the title.
  PREPARE_RECHECK re-prepares when the program cache was made for another GPU or settings. Ours has the `.built` marker
  (vk_draw.cpp ~1661) and `predict_background`, but neither check. Unmeasured; prevents first-visit hitches after a driver
  update. ~400 lines with tests; take with 11-20's lib_check.

### 7. A lone Alt no longer freezes the start-up screen (Triforce `HOS_ALT_MENU`, host/display.c `keymenu_dropped`) — small fix
- DefWindowProc's SC_KEYMENU enters the menu loop on the window's thread, which during the shader start-up screen is the
  thread waiting for shaders: the screen froze until a key. 10 lines in our `WM_SYSCOMMAND` case (host/display.c ~477),
  which lacks it. Alt+Enter, Alt+F4, Alt+Space unchanged. Low risk.

## Already on our list; status changed or confirmed by these ports
- **Game audio effects (reverb, delay, biquad on mixes):** Triforce now has them on by default (`HOS_AUDIO_EFFECTS`, a
  "Volcano eruption audio bugged" ticket: the sound played unfiltered and at full volume). Ours still says "Other effects remain
  incomplete" (host/nn_audio.c:12). Still area4_features item 5 (HeyListen 924e08a9); one more reason to do it. Needs a listen.
- **Four-way sync-object cache** (`HOS_OBJ_CACHE`, 16,384 entries): = Longshot 11-20 item 11 (+2.0/+2.5%). Ours is still
  1024 direct-mapped (host/nn_os_sync.c ~221).
- **Write-back forget without the sort** (`RX_VK_WB_FORGET_SORT`): = Longshot 11-17 (ours still sorts, vk_memory.cpp ~6127).
- **TICK-062 host switches** (thread_of cache, short-sleep PAUSE spin; "lab +5.8%" as a bundle): skipped in area3 item 10;
  CV signal fast is ours already. No new numbers.
- **Sync table liveness bytes** (Reborn 5d00dad, ReLink v0.7.9.2): = heylisten-2026-11-20 (b80a5999), rare rehash only.
- **XInput on its own thread** (Reborn 5d00dad, Longshot c5e1421d #2124): skipped 11-21; XInput is polled only when SDL has no
  pad, and the owner plays with a controller.
- **QueryMemoryInfo slack** (11-20 Triforce item 1, not taken): Reborn imported it but **off by default**
  (`HOS_MEM_QUERY_SLACK_MB`, default 0, "it can also make the game retain more actual memory"), on the new used-memory
  figure, which Reborn has on. No numbers from Reborn.
- **Parallel replay:** Reborn turned it on by default (dced210, after the dry pass made every render target, which ours
  already does) and off again 30 minutes later (721c49f: 55 -> 42 fps on a 9800X3D + 7900 XTX). Ours stays off.
- **Capture's late-page wait capped at 20 ms** (Reborn 37f8317): ours has it, adaptive (Mako 4.2 from ReLink, vk_memory.cpp ~3130).

## Bug 107 (young Link's tunics with Either age's tunics): a technique to look at
Reborn's ocarina picker (host/ocr_ocarina.c, nx2/ocr_ocarina.py, same build e0f3ccfa) makes child and adult Link
use either ocarina without touching the inventory. It hooks `EquipmentUser::update` for one slot (0x82e16c80; slots 13 and
16 are the ocarina actor and its `_Holder`). That function reads the equipped item's actor name into a 64-byte stack
SafeString before the game creates the actor natively, and Reborn swaps the name in that buffer. It then asks for those two
slots again on the player's update, outside events, to apply a change. If our child tunic equips but does nothing or
shows nothing, the tunic slot's native actor creation is the place to look, and this hook is a worked example of changing
which actor a slot makes. Not tried; only a pointer.

## Settings and features they have that we lack
- Reborn: **Ocarina choice** (Original / Fairy Ocarina / Ocarina of Time, both ages, F1 and launcher; lift hooks in
  nx2/ocr_ocarina.py and host). Note: our randomizer has "Shuffle the ocarinas"; a picker must not count as owning one.
  **Unlimited amiibo** (off by default; lift hooks on AmiiboMgr's two cooldown answers, nx2/ocr_amiibo_rules.py).
- Triforce: **Achievements** (25 built in, read from the save once a second, nothing written to the save; a list page in
  Options; your own in achievements.txt; host/achievements.c/.h ~480 lines). A randomizer-flavoured set could be fun later.
- Triforce: first start sized to a weak card (`RX_VK_FIRST_START_AUTO`, off), FG images let go when FG is off
  (`RX_VK_FG_KEEP`, VRAM), DLSS rows (NVIDIA only).

## Skipped (one line each)
- Triforce `RX_VK_WB_EXCL_CLIP` (the 0.6 crashes after warps): fixes a crash that came with their `RX_VK_CAP_ONLY_GPU`
  (new in 0.6.0), which we don't have.
- Triforce occlusion gate (`RX_VK_OCC_GATE`, invisible objects in the Forest Temple): their own count scheme. Ours
  (`RX_VK_OCC_QUERIES`) gives a draw skipped by a render condition no query, and a run with no queries stays "visible"
  (vk_replay.cpp `occ_take`, `occ_reported`), so the same lock-in looks impossible here. Watch for missing objects all the same.
- Triforce `RX_VK_CAPTURE_TABLES` / `RX_VK_REDRAW_STATE`: their "every plain draw drawn again into the motion vectors";
  ours redraws only the skinned draws (vk_temporal.cpp), different code.
- Triforce `RX_VK_IMPORT_LEAVING`: ours already counts evicted and dead imports in `memory_guest_imported`.
- Triforce `RX_VK_RANGE_WALK`, `RX_VK_TABLE_STREAM`, `RX_VK_UB_BATCH`, `RX_VK_ORDER_WAKE`, `RX_VK_RELEASE_QUEUE`,
  `RX_VK_LATE_INLINE`, `RX_VK_SETTLE_GATE`, `RX_VK_WB_WAIT_REC`: "not yet run in the game" there; revisit when they report.
- Triforce lift/build items (`A64_VECFP` = Longshot's, on our list; `A64_DMB_LIGHT` off; `A64_HOT_STICKY`,
  `RX_COLD_OPT`, `HOOKSHOT_*` build switches, nup/prompt tool speed-ups): build time or a re-lift for unmeasured gains.
- Triforce helper-thread tuner (`RX_VK_TUNER_SETTLED`), recorder auto, replay pin soft, `HOS_X3D` (two-die X3D only;
  the owner's 9800X3D is one die), `HOS_SIM_CPU`, `RX_VK_SIM_GPU_SLOW`, lock census, GPU-wait timing, lab A/B knobs.
- Triforce Linux, Steam Deck, Intel, GCN, NVIDIA/DLSS/Reflex/DLSS-FG and RADV items; launcher, builder, setup.
- Triforce memory-pressure items for 16 GB PCs (commit reserve, swap reserve, `HOS_MEM_ZERO_MARK`, memory priority): not
  needed on 32 GB.
- Reborn ASTC staging read-back fix (BC1 scan from write-combined memory, 16-17 ms uploads): only with astc_opaque's BC1,
  which we skipped.
- Reborn `chunks.py` corrupt-cache recovery (Longshot 5ca51209) and profile-recording guard: build robustness only; small,
  take with the next Longshot build pick if wanted.
- Reborn diagnostics (frame-time histogram, audio events capped, debug package), launcher, build screen, patch notes.

## Surveyed up to
- Reborn: **5d00dad956e95eceb8c8146ef585ea35190b6551** (v1.1.5, 2026-11-22), from 6babdc22: adcb6f7, dced210, 37f8317,
  721c49f, 5d00dad.
- Triforce: **e6f2f248f2387ab4296b6df397b1735feaa10489** (v0.7.0 "Sage Of Courage", 2026-11-22), tree diff from 043db52c
  (includes 70c210c, Linux FSR 4 AppImage).

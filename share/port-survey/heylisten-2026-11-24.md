# HeyListen survey, 2026-11-24 (8464b217..origin/HEAD 752e305b, 157 commits; read only)

**Goal (the owner's, 2026-11-24): compatibility and performance across all PCs and platforms** (NVIDIA, Intel, AMD, low
VRAM, narrow PCIe, Steam Deck/Linux, older CPUs, 16 GB RAM), never breaking the owner's PC (RX 9070 XT, Windows 11).

Read with `git show` in a no-checkout clone. Nothing of theirs was built, run or installed. Their engine/ is Hookshot at
a2e65052, which we have, so engine/<path> was compared with our <path> on amd-fix-sharkiix-version c62505c1. Three
read-only agents split the range: renderer correctness and memory, renderer performance, and host/input/tools. Their
numbers come from docs/research/perf-plan-2026-11.md and the lever notes. Their PCs: an RTX 5070 with a 7800X3D, an
RTX 3050 with an i5-10400F (PCIe 6.5 GB/s, often under memory pressure), and an AMD laptop with a Ryzen 7 5700U (Vega 8).

**Summary.** These two days were the fork's "+30% and no stutters" push. The gains they measured depend on things we
don't have:
- The lift (LIFT2 native FP, 5070 Market +10-12%). Not ours to port.
- Parallel replay on by default (MID_SEG, 5070 castle +13%). Ours is off by default.
- Their readback ring and HL_MEM_COLD memory machinery. We have neither.

What does fit our tree:
- Four small fixes for real bugs: a shader-fold bug, ASTC on AMD APUs, a refused import retried, and the
  own-frame present wait on AMD APUs.
- Two memory changes for long sessions and 16 GB PCs.
- A thread cap for CPUs with 6 cores or fewer.
- One crash fix whose buggy code we carry too. It is heavy.

## Ranked list

| # | Change | What it does | Helps | Risk | Size / port |
|---|---|---|---|---|---|
| 1 | 46e5a0a7 bit-field extract fold | constant fold of BitFieldUExtract(b,0,32) gave 0 (1U<<32), SExtract count 0 and offset+count>32 threw (program untranslated) | every GPU (correctness) | very low | ~25 lines, small adaptation (we use FoldWhenAllImmediates, not their WithFlags) |
| 2 | d834350d + 8f5ca506 (#127) ASTC on the CPU on AMD APUs | default widened from our 0x164E/0x13C0 to every AMD integrated GPU on Windows, Vega APUs excluded | Ally / Ally X (890M lost the device: 491 ms of GPU ASTC in one frame), 680M/780M laptops | low | ~35 lines, mechanical |
| 3 | bc74bce9, part: refused import given back and retried (RX_VK_IMPORT_EMERGENCY) | an import refused with INVALID_EXTERNAL_HANDLE/OOM frees idle retired imports and retries | AMD/Intel Windows, long sessions (issue 131: RX 9060 XT after 4 h, every import refused, draws left out) | low-medium | ~50 lines, small adaptation; the 1 GB bound itself is covered by our GRACE rule |
| 4 | 2b141867 + e65826e3 RX_VK_ACCUM_RETIRE | every 1200 submissions, chunks with no live game pool left and idle 1200 recordings are retired | every vendor, long sessions, low VRAM (owner's 55 min: 843 MB given back, #121) | low-medium | ~130 lines, small adaptation (our guest_pools for their hos_gpu_live_pools) |
| 5 | 19cb5cee + 38f72926 + 26ab8203 RX_VK_WB_GUESS_CHECKED | a bare storage entry's guessed 64-byte head is written back only where the GPU changed it and the CPU did not | every GPU (crash: 20 of 49 v0.4.3 reports, module jobs, Dodongo's Cavern/Crater; mostly NVIDIA) | medium (26ab8203 fixed a lock deadlock in the first form) | ~230 lines, **heavy**: we have the bug (vk_draw.cpp:4473) but not their CPU-applied staged write-back |
| 6 | 51e533a8 (form of their 1573e37c) RX_VK_WAIT_OWN=1 on AMD APUs | each present waits for its own frame's GPU work on AMD integrated GPUs | AMD APUs: HUD whole in 18 of 18 pictures vs 15-17 of 20 wrong (5700U) | low; costs fps on APUs (Ally X, BC-250 reports) | ~14 lines in do_present, small adaptation; behind a switch |
| 7 | d722126f + 0ffd4a77 HL_REGION_KEEP=20 | a freed address region stays resident 20 s; a region allocated over it is zeroed in place, not faulted back | 16 GB PCs, zone changes under memory pressure (3050: +1.5 fps, frames >25 ms -20%, longest stall 0.8 vs 1.1-1.3 s; 5070 under pressure: stutters -19%) | medium (wrong zeroing = stale data; up to 2 GB more resident) | ~277 lines, small adaptation (hook before hos_commit in hos_mem.c) |
| 8 | e44c839d + 72f0e617 HOS_BG_CAP=auto (ReLink 34efe84) | background threads take a virtual core only while fewer than physical cores - 1 are held; 8 ms wait at most | CPUs with 6 cores or fewer (3050's i5: frames >25 ms -8 to -30%; ReLink 6 cores 52.3 -> 56.7 fps); nothing at 8+ cores | low-medium | ~94 lines in hos_thread.c, small adaptation to our vc_* names |
| 9 | 5e713eba RX_VK_LINK_PROBE | 32 MB each way 3 times at start, the PCIe link logged in GB/s | diagnosis of narrow PCIe / eGPU reports; base for #10 | very low | ~133 lines, near-clean |
| 10 | 568184e2 + 334da7f4 + 08d0b337 RX_VK_WB_LAZY / _SETTLE | on a link under 9 GB/s, big written page runs not read back are written back 1/30 a frame, guarded by PAGE_NOACCESS | narrow PCIe (3050 1440p: Hyrule +5.7%, castle +5.0%, write-back 59 -> 17 MB a frame) | high (fault handler, deferred visibility, Windows only) | ~960 lines, **heavy**: our vk_memory.cpp has diverged |
| 11 | ac119ff2 + 783169c4 RX_VK_OCC_GATE | one-draw occlusion proxies predicate their draws on the GPU with VK_EXT_conditional_rendering | GPU-bound PCs (Market +4.2% on 5070 and 3050) | medium | ~245 lines, **heavy**: built on their RX_VK_OCC_REAL ring; re-implement on our kOccPool / OccReport (n==1). Complements our RX_VK_OCC_QUERIES |
| 12 | 22f0dfae RX_VK_BARRIER_HAZARD (off) | game barriers folded and pass-start barriers dropped when nothing written overlaps | GPU-bound (5070 Kokiri barrier time 0.37 -> 0.25 ms, fps flat; 3050 untested, bound +8.7%) | medium-high (missed hazard = wrong picture) | ~263 lines, small adaptation |
| 13 | c189dafe..68366a52 texcache (RX_VK_BC_DISK) | ASTC->BC blocks cached on disk, per-map read-ahead; default on for iGPUs and cards < 10 GB | low VRAM / iGPUs (3050 +3.4% hyrule-walk; Vega 8 laptop +30% turning) | medium (file IO) | ~1.4k lines, **heavy**: sits on their in-memory BC cache and batched ASTC, which we lack |
| 14 | 708e4060, 0c98db33, 1de6f07a, 7b7ee79f, 282fb51f HUD-less frame generation | the pre-HUD picture fed to FSR 3.1 / the built-in interpolator, HUD laid over each made frame | anyone using frame generation (HUD error 29.7 -> 2.6) | medium (picture only, off) | ~600 lines + 3 shaders, medium-heavy; must be reconciled with our RX_VK_FSR_FG_HUD patched passes; our redstone_hudless capture can be reused |
| 15 | b0534f8f part: RX_VK_DESTROY_PER_FRAME + create-failure retry | dead textures capped a frame; a refused creation waits for the queue and retries | stutters at zone change (5070: noise; fork turned it off) | low | ~50 lines; our reaper (vk_vma.cpp) has neither |
| 16 | 60dd49f5 HOS_SHADOW_LADDER (off) | square depth maps under 384 use finer size rungs | low VRAM, maybe | low | 23 lines, clean (shadow_slot.h); not measured |

**Later** (in order): 9 then 10 (measure our link first; the owner's 9070 XT at PCIe 5.0 never turns it on), 11, 12, 13,
14, 15, 16. 624e2d0b (the builder rebuilds when the DLSS or FSR 4 box is ticked, issue 130) is ~218 lines in
builder/HookshotBuilder. It is worth a look only if our builder has the same issue.

## Notes

- **1, the fold.** Our gpu/vk/eden/shader_recompiler/ir_opt/constant_propagation_pass.cpp:1131-1151 has the same code
  (and gpu/third_party/suyu has its own copy, which must stay as it is under PROVENANCE). In ours only plain-immediate
  extracts fold, so it is rarer than in theirs. When it is hit, though, a word is wrongly 0 or a program fails to
  translate. Their 3.0 M-case test needs adapting. It did not cure their black leaves (#97). Shaders are prepared again
  once.
- **2, ASTC.** Their astc_cpu_policy.h rule: Windows, vendor 0x1002, not one of 0x15DD/0x15D8/0x1636/0x164C/0x1638/0x15E7
  (Vega APUs), and either INTEGRATED_GPU or 0x164E/0x13C0. On the 5700U, CPU decode ran 1.3 fps against 14.2 for the
  GPU, which is why the Vega APUs are left out. Our vk_texture.cpp:629-640 needs one more argument. Not testable here,
  and the owner's discrete 9070 XT is unaffected.
- **3/4, memory.** Our retired_imports_give_back (GRACE: 30 s, 2 s over 85 % heap) already bounds retired imports
  (bc74bce9's main part). We lack the refused-import retry and the sweep of pools the game has dropped. Issue 131 was
  an RDNA 4 card like the owner's, so the owner's long sessions may gain from both. The emergency path was never hit
  on real hardware in the fork; their RX_VK_IMPORT_REFUSE_MB test switch (b2b74712) forces it and is worth taking with
  it.
- **5, the guessed head.** gpu/vk/vk_draw.cpp:4473-4476 is the same as theirs, and RX_VK_WB_DIFF does not protect it.
  We lack their v0.4.3 aggravator (RX_VK_WB_POOL_EAGER), so our exposure is likely lower, but that has not been
  measured. The port needs a small staging readback, a CPU apply that respects the host lock at the next
  memory_end_submission, and a snapshot at bind. The pure helper wb_guess.h applies cleanly. Test it in the Crater and
  Dodongo's Cavern (randomizer saves can reach both).
- **6, the own-frame wait.** We have no wait_own at all, only RX_VK_WAIT_GPU (default 0). Their commit names a Hookshot
  original, 737a0975 (bubblesnout), which is not in our history. If it is on Forgejo's main, take it from there. It is
  an fps-for-picture trade on APUs, so make it a switch whose default is decided by the owner.
- **7, keep freed regions.** host/hos_mem.c:209 discards freed regions, and the next zone faults them back (5-6 GB a
  warp tour in theirs). Our HOS_KEEP_FREED_PAGES never zeroes, which is unsafe. REGION_KEEP is the bounded form: 2 GB
  cap, emptied under 1 GB free, skips imported pages. Drop their hos_gp_ready and lazy-commit hooks. Our PC has 32 GB+,
  so for the Market A/B add a memory hog.
- **8, BG cap.** It does nothing at 8+ cores, so the owner's PC is unaffected (the A/B should show NOISE).
- **Randomizer / lift:** none of 1-16 touches nx2/, host/oot_*, oot_patches.py, tools/rando or the launcher's rando
  settings. 7 and 8 change host memory and threads under the randomizer's code, so rando_guard runs after them.

## Skipped

- **Lift (not ours to port):** 7ce98e0c, 737e2c25, 6d759b71, 7d765a23, f9aaaa83, bd8cf681, f99f6c9e (also
  hos_fpcr_follow in host/, lift-only), fbe6b0c9, c11be124, 1434a3ed. LIFT2 gave the 5070 Market +10-12%; LIFT1 pieces
  1-4 gave nothing. The gen-lock set ec6367b0, 9deade78, 861f1bdb and 5a5662a5 is in nx2/ and edits oot_patches.py.
- **Need parallel replay on by default and their TICK-050 segment plan:** 4d57b051 + 133566ac MID_SEG (5070 castle
  +13%, kokiri +8.6%), 424341a8 SMALL_LOG, 56b54df4 + bb113c46 SMALL_PREFIX (no gain), 8c7e9a40 + 881746b9 + e8627c14
  TOUCH_FAST (no fps gain, fewer locks). Revisit only if we turn RX_VK_PARALLEL on.
- **Need their readback ring:** 9b2d7bfb, 3039e831.
- **Measured no gain, or worse:** 0d092aa1 + 56727129 working-set floor (neutral to harmful; the STALL1 gain was
  HL_MEM_COLD, which we lack) and b6cd4b32 (HL_MEM_COLD default, HL_PREFAULT unmeasured). 8afd19a1 COMPUTE_ONLY_IMAGES
  (noise). e31a649a / c7491df3 / ae9a1474 NVIDIA cache dir (start-up 2.1 -> 36.5 s, reverted). 877ea63b sleep cadence
  and kernel wakes (off, unmeasured, no base for the =2 part). b653e1eb (reaper off: noise).
- **Have it:** 5ff89060 ZERO_UPLOAD (ours is a superset, with holes), b0534f8f reaper core (ours, from ReLink, on).
- **Randomizer / gameplay:** 00891f5a + f04633c7 Sprint (edits nx2/oot_patches.py, new host/oot_sprint.c). Its
  touchpad-opens-menu part we already do (vk_menu.cpp:7440).
- **Diagnostics built on their telemetry, which we lack:** c899eee1, b848e4e4, 2ca95a82 stutter_report.py (an idea
  worth rewriting for our logs), 73b775aa HL_FAULT_WATCH, 180c853d HL_TRACE_WB, 7ca17c8c IMPORT_VQ.
- **Launcher / builder / bench not ours:** 04b12e88 (RecompLauncher; our updater already honours
  HOOKSHOT_NO_UPDATE_CHECK), 87754e99, d929c475 (their run_bench.py).
- **Tests, CI, docs and switch lists:** 752e305b, b2b74712 (worth taking with #3), 4d967c41, ad0da156, 0e5db210,
  0e895c49, 2ed3bab9, 716e3903, 89fbd5e9, 3251d76f, 8e639f48, 9008f4f5, 60b781e0, the docs(research) / docs(switches)
  / docs commits (19159fde ... 779b5fe9), 2b318895, 3404db09, 42721c5f, 4de1b19f, fb331af8, b48fc265, 3b87700f,
  5ef80084, 14e72b62, b6a8dff8.

## Status (2026-11-24)

Surveyed only. Nothing is ported yet. Suggested first batch, all small and each behind a switch or a fix:
1, 2, 3 (+ b2b74712), 4, 6. Then 7 and 8 with their own A/B (the hog for 7). Then 5 as its own task.

## Status (2026-11-24, ports on amd-fix-sharkiix-version)

| # | Change | Commit here | Switch, default | Gate |
|---|---|---|---|---|
| 1 | 46e5a0a7 bit-field extract fold | 42f47865 | (a fix, always on; shader stamp changes: prepared again once) | tests/test_bitfield_extract_fold.py (old code: 1341 wrong, 1.5 M threw) |
| 2 | d834350d + 8f5ca506 ASTC on the CPU on AMD iGPUs (Windows, Vega excluded) | 0309a577 | RX_VK_ASTC_CPU: on for AMD integrated GPUs on Windows; discrete AMD, other vendors, Linux unchanged | tests/test_astc_cpu_policy.py; not testable here |
| 3 | bc74bce9 (refused import retried) + b2b74712 | fa398738, link fix 1c2d76e4 | RX_VK_IMPORT_EMERGENCY on; RX_VK_IMPORT_REFUSE_MB (test) | tests/test_import_emergency.py; the bound part not taken (our GRACE rule covers it) |
| 4 | 2b141867 + e65826e3 sweep of ended pools' chunks | b887b74d | RX_VK_ACCUM_RETIRE on (=0 off), RX_VK_ACCUM_DIAG | tests/test_accum_retire.py; in the batch A/B |
| 6 | 51e533a8 own-frame present wait on AMD iGPUs | 5f93404d | RX_VK_WAIT_OWN=1 on AMD integrated GPUs **on Windows only** (Steam Deck keeps no wait: unmeasured there); 0 elsewhere | tests/test_wait_own.py; not testable here |
| 8 | e44c839d + 72f0e617 HOS_BG_CAP=auto | 8126562f | auto; no cap on the owner's 8-core (7 physical for the game >= 6 virtual) | test_vcore_escape.py cap case |

**The batch A/B:** **PASS for the ports' side.** Market fountain, headless, 2560x1440 FSR 4, the full build at 8126562f (plus the owner's uncommitted randomizer files) in the test copy, shaders prepared first. "On" = every switch at its default; "off" = RX_VK_QUERY_RING=0, RX_VK_INDIRECT_AHEAD=0, RX_VK_SPLIT_AT_PASS=0, RX_VK_REAP_TURNS=0, RX_VK_CAP_FREE_HERE=1, RX_VK_ACCUM_RETIRE=0. Runs pr1124_pr_on_1..5 / pr1124_pr_off_1..5 (warm-ups pr1124w_*), 5 pairs: **fps 88.4 vs 84.1 (+5.1 %), 1 % low 68.5 vs 65.5 (+4.6 %)**; the "on" side won 25 of 25 pairs on both; worst frame 18.6-22.4 vs 19.0-22.8 ms (gate.py, A=on, B=off, printed FAIL for B). Pictures alike (vk_057600 of on_3 / off_3). The log: 12,288 indirect mesh draws converted in 2,048 stretches; the sweep retired 1 ended chunk (20 MB) in a run. The batch was not split per switch: all six stay on.

**Skipped as asked:** #5 write-back guess fix (heavy), #7 region keep, the "later" list.

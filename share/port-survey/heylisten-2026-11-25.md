# HeyListen survey, 2026-11-25 (752e305b..origin/HEAD e5e14b2a, 140 commits; read only)

**Goal (the owner's, 2026-11-24): compatibility and performance across all PCs and platforms** (NVIDIA, Intel, AMD, low
VRAM, narrow PCIe, Steam Deck/Linux, older CPUs), never breaking the owner's PC (RX 9070 XT, Windows 11).

I read the range with `git show` in a fresh no-checkout clone (the old clone in scratchpad/src had lost its HEAD and
config, so I cloned again to scratchpad/src2/heylisten). Nothing of theirs was built, run or installed. I searched our
tree at amd-fix-sharkiix-version 97892c69. Their numbers come from docs/research/perf-plan-2026-11.md,
lowend-laptop.md and the commit messages. Their PCs are an RTX 5070 with a 7800X3D, an RTX 3050 with an i5-10400F
(6 cores, 12 threads) and a Ryzen 7 5700U laptop (Vega 8, no mesh shaders).

**Summary.** The night had three lines of work:
- **The order thread (DECOUPLE).** The replay's submits and presents run on one ordered thread, on by default with 8 or
  more logical processors. On the 3050 it gave +9.8% Kokiri, +7.9% Hyrule and +4.2% Market. It is about 2,000 lines,
  built on their per-submission state, their readback ring and their present rule. A load hang in it was fixed only
  last night, and brightness flashes are still open (FLASH1). We should not take it yet.
- **The low-end laptop (LAPTOP1).** A Volumetric fog row, Render resolution 33% for the game's upscaler, and a
  first-start rule for iGPUs without mesh shaders. On the 5700U, 6-8 fps turning went to about 16.
- **Background compile threads off the replay's core (PRIO1).** +5.7% on a cold shader cache on the 3050.

Also in the range: a shader fix (dead code elimination dropped a vote: black leaves on NVIDIA), and a Base frame rate
limit with AMD FSR 4 frame generation, untested on real hardware. The small, separable ones fit our tree.

## Ranked list

| # | Change | What it does | Measured (hardware) | Have it? | Hardware | Size | Rando-sensitive | Risk | Rank |
|---|---|---|---|---|---|---|---|---|---|
| 1 | c81f500c (on 016f1507) PRIO1, RX_VK_THREAD_PRIO | Pins the background compile threads (in-play prepare, state list, prediction, precompile once the game runs) off the replay thread's reserved core (hos_reserved_cpus). Priorities and jobs workers are unchanged. | 3050 / i5-10400F: cold shader cache (first start after an update) +5.7% (3/3); warm equal (58.64 vs 58.74). Pinning the jobs workers too cost 1% warm, so c81f500c dropped that. | No (we have hos_reserved_cpus, the hook it needs) | CPUs where a core is reserved (8+ logical, so the owner's too). The gain is at first start and after shader-stamp changes. Windows only (no-op on Linux). | ~70-line header (thread_prio.h) + 3 call sites in vk_draw.cpp + init in vk_main.cpp; small adaptation | No | low | **take** |
| 2 | bdd56f2a dead code elimination keeps warp-wide operations (#97) | VoteAll/Any/Equal, SubgroupBallot and the four Shuffles count as having side effects, so dead code elimination never drops them | Fix: black leaves and bushes on NVIDIA (vegetation compute program 7650519f88e59b19) | No (our microinstruction.cpp:78 list lacks them) | NVIDIA mostly (convergence); correctness on every GPU | 12 lines + test (109+34) | No | very low; the shader stamp changes, so every shader is prepared again once | **take** (hardening, low priority: their trigger is their pseudo-op fold, which ours skips at constant_propagation_pass.cpp:88) |
| 3 | 5716afbf part + 45fd440e help: Volumetric fog row (RX_VK_FOG) | A Graphics row (on by default). Off leaves out the dispatches of the fog's three compute programs (27ee9883..., ee7764a6..., 1e2fcee3...). | Vega 8: the fog costs ~9 ms of a 60 ms frame, off is +1.5/+1.9 fps alone; 3050: +2.7 to +5.2% (one run a cell); 5070 a few %. Off: no haze or mist, nothing black (GPU11 pictures) | No (we have RX_VK_FOG_BOXES and RX_VK_SKIP_PROG, not this) | iGPUs, low-end dGPUs; a choice for everyone | ~30 lines (lowend_rule.h fog part, vk_draw.cpp dispatch, vk_menu.cpp row + options key) | vk_menu.cpp (a settings row only) | low (picture changes only when the player turns it off) | **take** |
| 4 | 45fd440e Render resolution 33% for the game's upscaler | kGameSteps gains 6 (33%) | Vega 8: still +1.3 fps, turning ~0; 33% "acceptable", 25% blocky; RTX 5070 with the game's network at 25%: picture right | Partly: our kOffSteps has 33%, kGameSteps does not (upscaler_rows.h:64) | iGPUs, handhelds | 1 line + test fixture | No | very low | **take** |
| 5 | 5716afbf + 9b87191e + 44e37b78 + 4e6af9d0 low-end first-start rule (HL_LOWEND) | Once, on an iGPU without mesh shaders (Vega APUs, Intel Xe-LP), writes only three rows: Render resolution 33%, handheld profile (from the next start), fog off. Marks `lowend_rule=1` and is never applied again. It keeps CRLF/LF and is logged. HL_LOWEND=0 never, =1 for one run. | 5700U: 6-8 fps turning -> 14.2 on the first start -> ~16 after (goal 25-30 not reached) | No | AMD Vega APUs, Intel Xe-LP iGPUs (not the 680M/780M/890M/Deck, which have mesh shaders) | ~120 lines (lowend_rule.h, vk_menu.cpp options writing, vk_main.cpp call) | vk_menu.cpp, options file | medium: changes players' settings unasked (on those PCs only); our options writer differs from theirs | **maybe: owner's decision** |
| 6 | 9b87191e part: VRAM mirror in place of the present wait on AMD no-mesh APUs | mirror_on() is on for AMD iGPUs without mesh shaders, and RX_VK_WAIT_OWN (our 5f93404d port of 51e533a8) is then off there | 5700U: HUD and grass right (0 faulty HUD in 18 shots); GPU gaps 13-16 -> 8.5-11 ms; +1 fps turning at 33%, nothing at 50% | No; it changes our own WAIT_OWN default | AMD Vega APUs only (not Intel: unmeasured) | ~10 lines (vk_memory.cpp mirror_on, vk_replay.cpp do_present) | No | low-medium (not testable here; our mirror_on rule, vk_memory.cpp:3965, has its own discrete-only reasoning) | **maybe** (with #5) |
| 7 | 90a91794 (+269843d7) Base frame rate limit | A row that caps the game's own rate (30-120, off). With frame generation the rate shown is the base times the multiplier. | 5070: base 48 at 3x = 48.0 / 144.4 fps shown | No (we have "Game frame rate cap", a different meaning) | frame-generation users, any GPU | ~20 lines nn_vi.c + menu row; our frame-gen rows differ (no framegen_rows.h) | vk_menu.cpp | low-medium | **maybe** |
| 8 | 90a91794 AMD FSR 4 frame generation | A fourth "Frame generation by" choice through AMD's runtime, offered only where AMD's version query lists it, falling back on any refusal | **Untested on real hardware** in HeyListen | No | Radeon RX 9000 only (**the owner's card is exactly that**) | ~534 lines vk_fsr4fg.cpp + AMD headers (third_party/fidelityfx: PROVENANCE rules) | vk_menu.cpp | medium-high (new runtime path, untested) | **maybe: owner's decision** (only this PC can test it; heavy) |
| 9 | db51759b RX_VK_SHADOW_SHIFT / RX_VK_VRS / RX_VK_LOAD_CLEAR | Sun shadow map (12288^2 D16, 288 MB) 2^n smaller; 2x2 shading rate for named programs; a pass-opening clear becomes loadOp CLEAR. All off. | **Not measured** ("nothing below was compiled or run") | No | SHADOW_SHIFT: low VRAM | ~320 lines | No | medium (picture) | later (SHADOW_SHIFT is worth a look for low VRAM once they measure it) |
| 10 | DECOUPLE order thread: 9581e0ca, bc9f4f35, cdd86fa1, 1758bb3b, 7ed2ea56, e42aa06b, 714f7dad, 0c927359, cc753074, de82506b, 650f686d, with the SUB1/REC1 refactors (58450ff9, fa7fa6ef, 30675282, b8739f70, 68902015, 46fc9336, 5054c633) and fixes (e67d919c, 64f941b8) | The replay's submits and presents on one ordered thread pinned to the reserved core; the game's threads go on after the capture. On by default with 8+ logical processors. | 3050: +9.8% Kokiri, +7.9% Hyrule, +4.2% Market (3/3 each), 20 of 20 starts clean after cc753074 (5 of 20 froze before). PIPE2 notes: Market adds stutters in the game-bound scene. **Open: brightness spikes of 1-2 frames on the 5070 (FLASH1).** | No (no order thread, no per-submission MemSub/MemView, no readback ring) | CPU-bound PCs with 8+ logical processors (the owner's too) | ~2,000+ lines vk_replay.cpp/vk_memory.cpp/vk_texture.cpp + host (rx_backend.c, nvn_native.c, nn_os_sync.c, hos_main.c) | hos_main.c (default setter) | **high** (freezes, flashes, timeline order) | **skip for now; watch**. Revisit once FLASH1 is closed and it has shipped in a release |

## Notes

- **1, PRIO1.** Their `hos_reserved_cpus` is the same host function as ours (host/hos_thread.c:1016). Port the final
  form (c81f500c), not 016f1507's priority roles. It applies to the owner's PC, so it needs the Market A/B. The gain is
  on a cold shader cache, so also time one run after a shader-stamp change (#2 makes one). Expect NOISE warm.
- **2, the DCE fix.** We have the 46e5a0a7 fold fix (42f47865) but not their FoldWhenAllImmediatesWithFlags pseudo-op
  fold, which is what made the vote dead in their case. Other folds (FoldSelect on an immediate) can still orphan a
  vote in ours, so the rule is cheap insurance. gpu/third_party/suyu's copy stays as it is (PROVENANCE).
- **3/4/5, low-end.** #3 and #4 are independent of #5 and safe alone. #5 is a policy decision: it rewrites three
  options on first start for Vega/Xe-LP iGPUs. It needs the options writer in our vk_menu.cpp (options_version 7,
  binds_load) adapted. Their CRLF fix (44e37b78) is part of it.
- **6, mirror vs wait.** It flips part of what we took last night (5f93404d: RX_VK_WAIT_OWN=1 on AMD iGPUs on
  Windows). Their final rule keeps the wait on AMD iGPUs *with* mesh shaders (680M/780M/890M) and uses the mirror on
  Vega APUs.
- **7/8, frame generation.** HeyListen's frame-gen rows (framegen_rows.h) are not ours, so the Base limit is a hand
  merge into nn_vi.c and our menu. FSR 4 FG is the one item here only the owner's PC can test.
- **10, the order thread.** Their +26% / +20% / +35% (Market / Hyrule / Kokiri) on v0.4.3 -> night1b on the 3050 is
  the whole night together. The order thread alone is +5.5% / +6.2% / +10.5% over night1b with it off.

## Skipped

- **Measured no gain:** 7d11e165 RX_VK_FALLBACK_INDEXED (Vega 8: noise, 11.14 -> 11.10 ms; their list 6).
- **Diagnostics or switches for things we lack:** 1da506c9 HL_SLACK (+ host/hos_slack.c), 563bd7db stall watch,
  4f3fe142 RX_VK_REC_OVERLAP_CHECK, 09484e74 RX_VK_CAP_DEPTH, b49b5524 / ac7d78a3 lanes (inert in this game, their
  notes), 7f12b5ae SUB_OVERLAP (loses 2-6%), 02cf81c1, 8aee42ad, e5cb7eca, 0550f3d2 / 1bd22639 (reverted), f109058c /
  cbec7601 (present thread, reverted), 0bb22896 (their readback ring), fbd417c9.
- **Their stall watch's Linux link fix:** 71a058d4 + e5e14b2a (QueryThreadCycleTime in host/posix for
  host/hos_jobtrace.c, which we don't have). Take only if we ever take their stall watch.
- **Bisect aids:** c4ea8ffb, c8b410e8 (fold bisect switches, dropped by bdd56f2a) and 4d59741b HL_SKIP_GIVEUP_S
  (title-skip give-up time; host/oot_autoload.c, a test aid).
- **Pass-timing labels:** f5f2bd64, 588e0e8d (RX_VK_PASS_TIMING names for the no-mesh fallback). Small and
  diagnostic: take only when profiling a no-mesh GPU.
- **Merges, test fixtures, switch lists, docs:** a01c3441, b48d8446, c0cf8baf, f7cdb58d, d0d8c90a, 05ed0224, e1d84424,
  79a3b568, 179d7e41, aebf053f, 7c05aaf3, 9d5a497e, e333b869, c0729d80, a6386d97, 2a2472e4, be83ae2a (merge fixes of
  the order thread), 5b2269da, a0c6f8b4, 897ea237, 52aaa76d, a1ce2732, 59e05cc3, 269843d7, and every docs(research) /
  docs(switches) / docs(native) commit (dce058bf, 3ded8c8b, fa5a6e14, 59faff9c, b8479aa7, 1d86b207, 07ef3532,
  f7901e09, ee1f6125, 1acb21ee, 6cb70467, e0d44cc7, 1bf55240, 1dd36835, 9ce80d38, 4bb67412, ba39848b, b426ad6f,
  1c58bfea, 4ef7f224, a28e5c07, 03baa36c, b041bc18, b4f558d2, 058909e7, b8aea6b2, a9a1149f, b699b5a2, 6a0f0d4f,
  f24afbe9, 7bded83a, 662ac956, 37165e2b, 14db49c2, 3eeb6bab, 0ccbaaa4, ca3de930, d0130575, 64c89449, b4c09ebc,
  1a928605, 6d69fb65, f8e5de6a, d61dcf91, 06050ff2, d77bcdf4, ecb9675e, efb3b7af, b7d2a974, 566f7d9b, b9c53fbc,
  febf012b, 673c5e2d, 4be99489, 6e4a8af1, 7d280c0f, 254f65fb, 226339ec).

## Plan

- **Taken:** nothing yet.
- **To try:** 1 (PRIO1, Market A/B plus a cold-cache run), 2 (DCE fix, with its game-free test), 3 + 4 (fog row and
  33%, one commit each).
- **Owner's decision:** 5 + 6 (change settings and the present wait on Vega/Xe-LP iGPUs, untestable here), 7, and
  8 (FSR 4 frame generation: heavy, but this PC is the one that can test it).
- **Skipped / watching:** 9 until measured; 10 until FLASH1 is closed and it has shipped in a release.

## Surveyed up to
origin/HEAD **e5e14b2a** (2026-11-25).

## Ported 2026-11-25 (code only, not built)

Nothing was built, installed or run. Game-free checks: the same 161 failing before and after; the new
tests/test_thread_prio.py, test_dce_convergent_ops.py and test_fog_row.py pass.

- **91e477c1** #1 c81f500c PRIO1, RX_VK_THREAD_PRIO (gpu/vk/thread_prio.h). Our in-play compile threads only: the update's
  prepare_background / prepare_run(background) and predict_background / predict_run(background); a pinned thread marks
  itself so the state list's and the libraries' workers it starts are pinned too. The start's prepare/precompile are not
  (the game waits for them). vk_draw.cpp and vk_main.cpp could not be syntax-checked here (no Vulkan headers).
- **07a36bda** #2 bdd56f2a: warp-wide ops kept by dead code elimination. **Changes the shader stamp** (gpu/vk/eden):
  every shader is prepared again once.
- **29a538a4** #3 5716afbf, the Volumetric fog row only (RX_VK_FOG; gpu/vk/fog_row.h). Not the HL_LOWEND first-start
  rule nor the VRAM-mirror change (#5, #6: the owner's). The row name has no translations yet.
- **54ce75ab** #4 45fd440e: Render resolution 33% for the game's own upscaler (+ its fog help wording).

**Once built:**
- The renderer build: a compile of vk_draw.cpp / vk_main.cpp (unchecked here). The B side of any A/B needs
  `HOOKSHOT_SHADER_STAMP=<A's stamp>` (07a36bda alters translation, so only for the timing build; install with the honest stamp).
- #1: the log line `vk: thread priorities: RX_VK_THREAD_PRIO=1: ... kept off logical processors 0x...`; the Market A/B
  (5+ reps; expect NOISE warm) and one timed cold-cache start right after the stamp change, against RX_VK_THREAD_PRIO=0.
- #2: a look at foliage (Kokiri, the Lost Woods) for nothing black; the one-time re-prepare.
- #3: Volumetric fog Off: the haze gone, nothing black or flashing (Hyrule Field, the Lost Woods); `vk: volumetric fog
  off` logged; the fog's three program keys are HeyListen's (unverified here). A Market A/B fog on/off for the findings.
- #4: Render resolution 33% with the game's own upscaler: the picture right; the menu steps 50 -> 33 -> Auto.
- rando_guard.sh (vk_menu.cpp rows) and a shop run.

## Measured 2026-11-25 (Market A/B, 5 runs a side after a warm-up, own shader caches, FSR 4 2560x1440)
- Build of 11-22 (old) vs today's (all of 2026-11-24's and 2026-11-25's ports): 82.3 -> 87.2 fps (+6.0%), 1% low 57.0 -> 66.1
  (+15.9%), 75 of 75 pairs. Runs ports1125_old_*, ports1125_new_*.
- RX_VK_THREAD_PRIO=0 (new_tpoff): 87.2 fps, 1% low 66.4 against new's 87.1 / 65.6: NOISE with a warm cache, as HeyListen found
  (their gain is on a cold one). Kept on.
- RX_VK_FOG=0 (new_fogoff): 88.3 fps, 1% low 66.7: about +1%, within the noise on this PC. The row stays On by default.

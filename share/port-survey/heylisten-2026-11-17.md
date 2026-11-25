# HeyListen survey, 2026-11-17 (HeyListen 504f8362)

HeyListen (https://github.com/Sacrappy/HeyListen, GPL-3.0-or-later) is a Hookshot fork: its engine/ is Hookshot at
a2e65052, which our tree also holds, plus 670 commits of its own. Four read-only passes (area1-4 files here) sorted
them. Most of its frame-rate work is NVIDIA-measured; much of the rest we already had (from Longshot, ReLink or later
Hookshot). Our Market frame is limited by the CPU's replay (~10 ms), not the GPU (~5.7 ms).

## Taken (10 fixes, on amd-fix-sharkiix-version, installed 2026-11-17 18:31)

| Commit | What | Source |
|---|---|---|
| f1059332 | a pipeline is drawn only with the program object it was built from (device lost on AMD: RX 7800 XT 4/4 -> 0/7 starts); RX_VK_PIPE_BY_PROGRAM=0 off | HeyListen 1ae91a2d / Hookshot 65e2cb91 |
| 5f976fc8 | a copy into a BC3 texture only in whole blocks (undefined on AMD) | HeyListen f2bebddd / Longshot #672 |
| cdd63675 | texel buffer views only of formats the device supports (AMD lacks RGB 3-channel) | HeyListen 00e8805b / Longshot #1244 |
| 59232803 | a compute program's pipeline read and published atomically (a race) | HeyListen bfb16fc1 / Longshot #621 |
| 8a6d41ac | a capture no longer misses pages the replay is marking again (Kokiri mist gone for a frame) | HeyListen 26e0f0a6 / Longshot #1083 |
| 52a92f5e | a freed region's discard gives the core up (frames over 50 ms at Death Mountain Trail 13 -> 0 on their PC); HOS_DISCARD_HOLDS_CORE=1 off | HeyListen dc25c9c6 / Hookshot #2924 |
| c38cfb52 | a thread starved of its core gets it after 1 s (HOS_VCORE_STARVE_US) | HeyListen 0ab1b72c |
| 5c8a9de6 | hookshot_options.ini written atomically (a crash while saving no longer empties every setting) | HeyListen 7cec25ab / Longshot 524d5520 |
| 1065e040 | audio Auto picks 5.1 by the speaker layout, not the channel count | HeyListen d21a5f7c |
| b95741fb | nn::fs WriteFile/FlushFile give the core up | HeyListen f6a4b2e6 |

Measured (Market, RX 9070 XT, 5 interleaved runs a side, a quiet PC): old 70.2 fps / 1% low 51.1; all fixes 69.6 /
50.4; renderer half 72.9 / 51.0; host half 73.0 / 51.2. No change beyond noise either way (rank test 10-13 of 25):
they are fixes, kept for stability. An earlier run with Firefox and Discord in use was too noisy to read.
Randomizer guard: no new check failures (111 -> 110 failing, all old); only gpu/vk/vk_menu.cpp of the randomizer's
files touched (the atomic save). Headless: the Kokiri Shop save bought an item, the Tracker marked it, the shelves drew right.

## Taken: the per-draw replay cuts (installed 2026-11-17 20:58)

| Commit | What | Source |
|---|---|---|
| fa53aad5 | flat per-draw caches (program picks, the thread's pipeline map, c1_at; one FlatMap in gpu/vk/flat_map.h, our handle table moved into it) and an inline op payload copy | HeyListen 3aa51bf5 / Hookshot eda64e895 |
| 2658273d | a draw whose vertex streams changed binds only the bindings that changed (every bind site audited); RX_VK_VB_RANGE=0 off | HeyListen 28623fcf / Hookshot 33ed7b81a |

**The first A/B was WRONG** (72.6 -> 82.3 fps, +13.4%): its B renderer was built renderer-only (perf-ab/buildmain.sh), which
leaves FSR 4 out (HOOKSHOT_FSR), so B ran the game's own upscaler while A ran FSR 4 Native AA: the 13% is FSR 4's cost
(the log's "memory sync" 1.3-1.7 ms against 0.3-0.7), not the speedup. Re-measured with both sides built the same way (renderer-only, no FSR 4, stamp pinned; 5 runs a side): **84.3 -> 83.8 fps
(-0.6%), 1% low 59.1 -> 60.1, rank test 11 and 13 of 25: no change on this PC.** Kept for other hardware (upstream:
+3.4 fps on an RTX 5090 in one config; HeyListen's RADV run with two more changes; the binding range came from a Steam
Deck profile) since it costs this PC nothing. Pictures match. Randomizer guard: no new failures, no randomizer file touched; the Kokiri Shop run bought, tracked and drew right.
The install used the honest stamp: the shaders were prepared again by the build (347 s), not at the owner's start.

## Tried, not taken (switches, no code)

| Switch | Market result | Kept off because |
|---|---|---|
| RX_VK_PARALLEL=5 (HeyListen's default) | -5.5% fps, worst frames 35-40 ms (FAIL) | slower here |
| RX_VK_CAPTURE_NT=1 (streaming-store capture) | noisy PC +4.3% (16 of 25); quiet PC -2.7% fps / +4.5% 1% low (11 and 15 of 25): no change | nothing measurable here |
| RX_VK_VRAM_MB=9000 | no change | nothing to gain in the Market |

## Waiting (ranked; details in area1-4)

- RX_VK_CAP_ONLY_GPU (capture only the game's pools): +13% on an RTX 3050; count-only mode first.
- Our play profile is stale (Nov 9, upstream's; seven hot functions changed by our patches): record our own (RX_PGO=gen), then the three FP lift switches (+2.7/+4.8 fps on their RTX 5070). Lift work: the randomizer's patches must all still apply.
- Host allocations and the renderer's operator new wait at the commit limit (crash fixes; the renderer half needs an MKWVK_API_VERSION bump: bundle with another).
- Audio reverb/delay/biquad effects (~420 lines; needs listening).
- Upload budget per thread (RX 9070 XT Linux: held textures 470 -> 116, worst load frame slightly worse): A/B first.
- The launcher also writes hookshot_options.ini non-atomically (Launcher.cs 213, 3248): same fix there.

## Skipped

HeyListen's native engine (huge, unmeasured, slower on one PC); code mods (break the randomizer's lift patches); the
ASTC->BC1/BC7 system (~700 lines, conflicts with our AMD BC3 workarounds); telemetry rows; slow-link mode (PCIe <= 8 GB/s
only, NVIDIA-only detection on Windows); NVIDIA GPU-time cuts (our Market frame is CPU-bound).

## Play profile (2026-11-17): recorded, not adopted

Our shipped profile (work/hookshot_pieces.prof, upstream's of Nov 9) no longer fits much of our hot code: llvm-profdata
overlap with a new recording: 702 functions match, 801 mismatch. A new profile was recorded (RX_PGO=gen build; one
headless tour of 11 areas as child and adult, F:/Games/perf-ab/ours.prof; the recorder is port-survey's
record_profile.sh) and built in (make_game.py now lets RX_PGO set by hand win). Market A/B, both with FSR 4: 69.7 ->
71.3 fps (+2.3%, 16 of 25), 1% low 50.5 -> 49.4: NOISE. The Market frame waits on the renderer's replay, not the game's
code, so a better game-code profile can't show there. Kakariko (child, by day, villagers and cuccos; the replay is about half the frame there) A/B, 5 runs a side: 126.8 ->
125.8 fps (-0.8%, 7 of 25), 1% low 103.7 -> 104.4: NOISE again. Not adopted: a fresher profile buys nothing
measurable on this PC. Kakariko is a far steadier bench than the Market (same-build runs within ~1.5% against ~7%).

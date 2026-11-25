# Area 4: HeyListen's changes outside raw frame rate

Scope: crash and stability fixes, audio, the overlay and menu rows, DLSS/FSR 4/temporal, Linux, the builder, and the
measurement tools. Everything here was read only. HeyListen hashes are from its clone; our tree is
`C:\Users\beerc\Hookshot` (branch amd-fix-sharkiix-version).

Many of HeyListen's November commits are picks from Longshot or upstream Hookshot, and **we already hold most of them**:
- the guest commit wait at the commit limit (4fcd16d4 equals our `commit_wait` in `host/mkw_glue.c`);
- the texture commit-room budget (2ecb782c's texture half equals our 91a1ae8b, `gpu/vk/commit_room.h`);
- the heap retry (2a9ccd56/271fc075 equals our `host/oot_heap_retry.c`);
- the frame generation multiplier fix (7eae50ab equals `gpu/vk/vk_framegen.cpp:831`, `m = fg.mult`);
- FSR 4 and its native HDR (8be18e98 equals `vk_fsr4.cpp` `RX_VK_FSR4_HDR`);
- the Render resolution kept when the Upscaler changes (48482e9e equals our f647a072);
- the above-60 fps fixes (Deku web, ripples, time of day, pick-up counter, sound and platforms, cutscene cues: our
  9f64464b, 6df80a8d, f0c40fc9, f915af93, 8fcc8c22/9df055f2, a7cc747d);
- the vcore escape at 2 s and the OpenFile, movie and escape fixes (07b03596, 26c12b0d, d522ec0e, c8b9a9f0, bce1476c);
- Skip title screen, the frame rate cap, the F10 FPS counter, the per-frame trace (`RX_VK_FRAME_TRACE`, same columns),
  `RX_VK_FRAME_LOG`, `RX_VK_PASS_TIMING`, `HOS_PRESENT_TRACE` and `HOS_FPS_LOG`.

The candidates below are what is left.

## Candidates, best first

### 1. Settings written atomically (7cec25ab, from Longshot 524d5520). Port first.
- **What it does:** `host/hos_atomic_file.h` writes `<path>.hosnew`, flushes it, and moves it over the file in one step,
  and the next start removes a leftover. It covers `hookshot_options.ini`, `language.txt`, `mouse_sens.txt` and the
  saves' move.
- **Our tree:** lacks it. `gpu/vk/vk_menu.cpp:2565` and `:5637` write the options with `fopen(..., "w")`, so a crash or
  a kill in the middle empties `hookshot_options.ini` and every setting, the randomizer's included, goes back to default.
  We already use the same pattern for `share_write` (vk_menu.cpp:2859).
- **Gain:** unmeasured. It is a correctness fix; HeyListen's kill sweep test passes.
- **Hardware:** none, no switch.
- **Port:** about 195 lines of header plus about 80 lines across vk_menu.cpp, hos_main.c, nn_applet.c and nn_hid.c, and
  a test. Our menu is heavily changed, so the site edits are by hand. It doesn't touch the lift or the seed tool. The
  launcher writes the options too (`launcher/Launcher.cs`), and it should get the same temp-and-move.
- **Risk:** low.

### 2. The host's own allocations wait at the commit limit (29243133, from Longshot 2547a8f3 #341). Port first.
- **What it does:** `hos_xmalloc`, `hos_xcalloc` and `hos_xrealloc` retry for up to 5 s while the renderer gives commit
  back. They cover the NVN layer's recording buffers and tables, and the video service's image pool and decoder table.
  After that come a log line, the out-of-memory notice and a fatal that says out of memory. The guest side already does
  this.
- **Our tree:** lacks it. There is no `hos_xmalloc`. Our guest commits wait (`commit_wait`) but a host `malloc` that
  fails still dies at once with an unclear fatal.
- **Gain:** unmeasured. It is a crash fix; HeyListen's issue 55 was on a 32 GB PC.
- **Hardware:** Windows commit limit, so it matters most on 16 GB PCs with a small page file. It is harmless on the
  owner's PC.
- **Port:** about 130 lines in mkw_glue.c, about 30 in nvn_native.c and nn_video.c, and tests. It reuses our
  `hos_out_of_memory_box`. `HOS_TEST_ALLOC_REFUSE` lets it be tested.
- **Risk:** low.

### 3. The renderer's `operator new` waits at the commit limit (2ecb782c, its new-handler half; Longshot f88e6e3a #1291). Port first, together with #2.
- **What it does:** `new_refused`, a `std::set_new_handler` that mkwvk_init installs. With under 4 GB of commit left it
  retries every 50 ms for 5 s, then asks the host for the out-of-memory notice (a new `MkwVkHost::out_of_memory`). With
  more commit left it still throws `bad_alloc`.
- **Our tree:** lacks it. There is no `set_new_handler` in `gpu/vk`. Our texture commit-room budget (the other half of
  this commit) we have.
- **Gain:** fixes a crash with exception 0x20474343 (an uncaught `bad_alloc`) in hookshot_vk.dll in Hyrule Field on a
  32 GB PC. Unmeasured beyond that.
- **Hardware:** none.
- **Port:** about 40 lines in vk_main.cpp, 14 in rx_backend.c, and a vk_api.h field, which **bumps `MKWVK_API_VERSION`**
  (ours is 23). That bump means every player prepares shaders again, so it is better bundled with another API change.
  Tests are about 190 lines.
- **Risk:** low.

### 4. Audio: Auto counts 5.1 speakers, not channels (d21a5f7c, from Longshot 4ff4f3df #1167). Port first.
- **What it does:** Auto picks 5.1 only when the device's mix-format channel mask has a centre and a rear or side pair.
- **Our tree:** lacks it. `host/nn_audio.c:779` uses `mix->nChannels`. An audio interface with 8 outputs (mask 0), a
  quad output, or a format with no mask gets 5.1, and the centre (voices, the ocarina, Link) goes to an output nothing
  listens to, so it is silent.
- **Gain:** unmeasured. It fixes missing voices on such devices.
- **Hardware:** Windows only.
- **Port:** about 20 lines plus a test, in one function.
- **Risk:** very low.

### 5. Audio: the standard reverb, delay and biquad filter effects (924e08a9). Port later, after a listen.
- **What it does:** implements `AddReverb` (the standard reverb, which Ocarina uses, through the I3DL2 network),
  `AddDelay`, `AddBiquadFilter`, effect order per mix, and aux enable. `HOS_AUDIO_NO_EFFECTS=1` leaves them out.
- **Our tree:** has the I3DL2 reverb, aux and splitter biquads. It lacks `_ZN2nn5audio9AddReverb...`, `AddDelay` and
  `AddBiquadFilter` (only `GetRequiredBufferSizeForDelay` exists), so those sub mixes play dry.
- **Gain:** unmeasured, by ear: the sound is closer to the console's.
- **Hardware:** none, but it is CPU work on the audio thread. That cost is small; check it at the Market.
- **Port:** about 420 lines in nn_audio.c and a 300-line test. Our nn_audio.c differs (aux, mono, the deadline), so it
  is a hand merge. It doesn't touch the randomizer.
- **Risk:** medium. The audio could sound wrong, so the owner should listen (indoors, caves, the Temple of Time).
  The switch makes it easy to compare.

### 6. Write and flush calls give up the virtual core (f6a4b2e6). Port first; it is tiny.
- **What it does:** nn::fs `WriteFile` and `FlushFile` call `hos_vcore_away/back` around the host call, as OpenFile and
  ReadFile already do.
- **Our tree:** lacks it (`host/nn_fs.c:495`, `:519`). A save's `FlushFileBuffers` can block for tens of ms on a core,
  with the threads that share that core waiting behind it. Saves are frequent in the randomizer.
- **Gain:** unmeasured (found by an audit).
- **Port:** about 12 lines and a test.
- **Risk:** low.

### 7. A thread starved of its core gets it after 1 s (0ab1b72c, upstream Hookshot by mooki). Port later.
- **What it does:** `HOS_VCORE_STARVE_US` (1 s by default; 0 turns it off). A waiter pinned to one core that better
  threads keep taking is marked starved, goes first at the next release, and asks the holder to yield. This replaces
  the 2 s escapes where two threads share one core's state, the #1929 crash risk.
- **Gain:** on Linux, an RTX 4090 and an i9: escapes went from 4 of 10 starts to 0 of 10 while loading a save. The
  same escape line appears in a 16 GB RX 9070 XT log.
- **Our tree:** lacks it. Our hos_thread.c has the 2 s escape and no starve rule.
- **Port:** a medium change in `vc_acquire`, `vc_better` and `vc_yield`.
- **Risk:** medium (the scheduler). First count `ran without a core` lines in our own logs. If there are none, skip it.

### 8. The pipeline prediction skips giant programs and stops near the commit limit (d2384687). Port later, after a check.
- **What it does:** a program over `RX_VK_PREDICT_MAX_KWORDS` (300k SPIR-V words) is left to its draw, and the
  prediction stops when commit left is under `RX_VK_PREDICT_RESERVE_MB` (3072).
- **Gain:** two programs (1014k and 502k words) each took the NVIDIA compiler over 3 minutes and 11 to 29 GB. On an
  RTX 3050 with a cold prepare: prediction 346.8 s to 93.5 s, start-up 531.9 s to 245.9 s, peak commit 36-39 GB to
  4.3 GB (docs/native-engine/shader-efficiency.md).
- **Our tree:** our prediction differs. It has `RX_VK_PREDICT_STALL_S` (abandon a stuck worker) but no size or commit
  limit. Whether the AMD Windows driver blows up the same way is unknown.
- **Check first:** on the next cold prepare, look in `hookshot_log.txt` for the prediction's time and Task Manager's
  commit. If it is long or huge, port the limits (about 135 lines in vk_draw.cpp, plus predict_limits.h).
- **Risk:** low. A skipped program is only compiled at its first draw, which can hitch once.

### 9. A movie picture ahead of its clock is held above 60 fps (8e5a1a77). Port later.
- **What it does:** nn_video gives the previous picture again while the next one is ahead of the movie's clock.
  `HOS_VIDEO_NO_HOLD=1` restores the old behaviour.
- **Our tree:** lacks it. We have the cue sync (a7cc747d) but not the picture hold, so movies can run fast above a
  60 cap.
- **Port:** 34 lines in host/nn_video.c.
- **Risk:** low. It matters only with a cap above 60; check one movie.

### 10. Measurement tools to reuse. Port later; tools only, no game change.
- **`tools/bench/spikes.py`** (117 lines): splits each spike frame in the per-frame trace by cause (late pages, memory
  sync, pipelines and translation, uploads, replay CPU, GPU behind). Our `RX_VK_FRAME_TRACE` already writes the same
  columns. Two adaptations: our CSV has no `t_s` column (add one to the trace, or cut by frame number), and HeyListen
  adds `qsubmit_ms` and `dispatch_ms`, which are optional. It is the cheapest way to say why the Market stutters and
  would sit well beside gate.py.
- **`perf_report.cpp`'s idea:** frame-time and GPU-time histograms per map, and "what a slow frame waited on" (pipeline,
  translate, upload, memsync, GPU-bound, readback, game CPU, pace). We could keep it as a local file only, with nothing
  sent. Each A/B would then get a per-area histogram for free. It is about 370 lines and needs an API bump
  (`perf_info`), so it waits for another bump.
- **`RX_VK_TEST_VRAM_MB`** (b62c39e5): treats the card as having n MB, to try the 8 GB and 6 GB tiers on the 16 GB
  9070 XT without other hardware. It is small and our tree lacks it. This matters because `docs/workflow.md` asks us
  not to break those tiers.
- **`HOS_LOG_QPC`** (e93c9523, stamps log lines with PresentMon's clock) and **`RX_VK_FRAME_LOG` with QPC time**
  (97294482): useful only alongside PresentMon. Port later.
- **`RX_VK_TL` and `RX_VK_TL_PROBE`** (GPU timeline with calibrated timestamps), **the PASS_TIMING timeline layout**
  (6460c85e, 5a9634a0), **segment GPU timestamps** (17308b8c, 6d8add8e, e4e0eda5), and **`HOS_JOBTRACE`** with
  frameline, critpath, chainb, wakelat and jobtrace.py: tied to HeyListen's parallel segments and held submits
  (`HOS_NVN_HOLD`), which our replay doesn't have. Skip unless those land; `jobtrace` alone (the guest threads' waits)
  could be ported on its own later.
- **`run_bench.py` and `summarize.py`:** our bench.sh and gate.py already do the A/B. Worth borrowing:
  summarize.py's budget columns (the share of frames over 8.33 ms and 6.94 ms, and the 0.1% low), as about 20 lines
  in gate.py.
- **`ressample.py`:** private bytes, threads and GPU memory once a second. The `smi.csv` part is nvidia-smi only, so
  it is of limited use on AMD.

### 11. Save export to an emulator (the builder's Saves.cs, a54ee435). Port later; it is a feature.
- **What it does:** HeyListen's builder finds Lichii, Eden and its forks and NX2navi, runs
  `scripts/oot_saves.py --dry-run`, asks, then copies after a backup.
- **Our tree:** we have `scripts/oot_saves.py` (it does import and export). Import works through the game's
  `SAVE FOLDER` (host/hos_main.c:423) and the launcher's "Import saves" row. There is **no export** and no
  emulator detection.
- **Port:** our launcher is WinForms and ships no Python, so export would be a C# copy and backup in Launcher.cs, about
  100-150 lines.
- **Randomizer:** randomizer saves (`user/save_rando`) must not be offered for export to an emulator; they are
  meaningless there. Only the normal game's saves qualify, and the owner says the normal game no longer matters.
  **Low value.**

### 12. Crash window after a crash (e1cfcb59, 15799b68, 580af70d; Longshot a0dac82e, 17394b71). Skip for now.
- **What it does:** a helper process shows "what happened", then "Report manually" (clipboard plus a GitHub issue) or
  sends automatically to HeyListen's server.
- **Our tree:** has the crash records (`hos_crash_record.c`, privacy redaction) and the launcher's "Send logs" and log
  summary, but no window right after a crash. The port is over 3500 lines and needs an API bump; the telemetry half is
  HeyListen's own server. Only the window part would be worth it, and only if the owner wants it.

## Skipped (one line each)
- 4fcd16d4 guest commit wait, 2ecb782c texture commit rule, 2a9ccd56/271fc075 heap retry, 7eae50ab frame generation
  multiplier, 8be18e98 FSR 4 HDR, 48482e9e Render resolution kept, the above-60 fps fixes, and the vcore escape,
  OpenFile and movie fixes: **already in our tree** (see the top).
- 67c82be6 (no core held across flush_cs) and 77bd2f86 (texel copies): our tree has no flush_cs (HeyListen's
  `HOS_NVN_HOLD`), and our rx_backend texel wrappers already give the core up.
- 2edb42dd DLSS feature at the recommended size, 6b5975c3 DLSS CNN preset E under 7 GB: NVIDIA only, and the owner
  has AMD (worth it only for NVIDIA players of a shared build).
- facc79f2 overlay "Scaling" names the upscaler, 51c1782e shader and pipeline waits, 8bb3b52e/8c78da47 GPU numbers and
  CPU temperature: these belong to HeyListen's own full overlay. Its GPU numbers come from NVML or amdgpu sysfs, so on
  AMD Windows they would show "-". We have our own Performance monitor.
- 19b7fcef Linux sound reopen, 3c36ed41 dma-bufs under Steam and Flatpak, 2cc2f22f/5b05f84a RADV mesh defaults,
  5d8d37fb Steam Deck Game Mode, 73e022d4/56c612c2 AppImage: Linux only; the owner is on Windows. 19b7fcef is the one
  to take if a Linux build ever matters (upstream f6e60978e).
- Telemetry (perf statistics sending, crash auto-send, c51f4900, 8f144033, eea9638c, 62f104fc crash_groups.py):
  HeyListen's own server.
- RecompLauncher packaging (dbaca991, be3e92d0, 955d46d9), the builder's progress bar and rename (b3b9911f,
  fcfcbd22): HeyListen's distribution.
- Code mods (exeFS `.ips` and `.pchtxt` applied before the lift: 6bcce93f, 9a18c275, 23ceef10, 8f24c988): they rewrite
  the game's code before the lift, which can break the randomizer's lift patches (nx2/oot_patches.py anchors). Skip
  unless the owner asks.
- 7795a921 update offer only when newer: our launcher has its own update flow.
- 2661907b/4dd319ff `HOS_MEMINFO_OLD` by RAM: we already have `HOS_MEMINFO_OLD` (host/hos_mem.c).
- `HL_TRACE` (the crash recorder's ring of allocations and frees, hltrace.py): about 1500 lines tied to HeyListen's
  native heaps (`hl::mem`). Skip.
- Native-engine `HL_*` items (math, UBO memo, program memo, main loop): another area's (CPU).

## User-visible settings and features: HeyListen's against ours

**HeyListen's menu** (`engine/gpu/vk/vk_menu.cpp`) against ours (`gpu/vk/vk_menu.cpp`). Ours is a superset except for
the items marked LACK.

| HeyListen | Ours |
|---|---|
| Graphics: Quality preset, Fullscreen, GPU device, Frame generation (Off, Auto, 2x to 8x), Frame pacing | have |
| HDR (Off, Expanded, Native), HDR paper white, HDR peak brightness | have, plus contrast and tone mapper |
| NVIDIA Reflex | have, plus AMD Anti-Lag 2 |
| Frame rate limit (60, 90, 120, 144, 165, 240) | have, as "Game frame rate cap" |
| Output resolution, Upscaler (game's own, DLSS, DLAA, FSR 3.1, FSR 4, FSR 4 Native AA), DLSS model, Render resolution, Window scaling filter, Sharpness | have, plus "Off (no upscaling)", a custom output size and "Frame generation by" |
| Handheld profile, Ultrawide | have, as "Profile", "Aspect ratio" and "Ultrawide menus" |
| Robust buffers | have (Debug tab) |
| Gameplay: FPS counter (Off, FPS, Full panel; F10 cycles) | have (levels, position, Performance monitor) |
| Menu size, Game speed, Text speed, Skip title screen, Microphone, Discord status | have |
| Audio output (Auto, Stereo, 5.1) | have, plus Mono, Volume and Mute in background. **LACK:** Auto's speaker-mask detection (candidate 4) |
| **Send performance statistics**, **Send crash reports automatically** | **LACK.** HeyListen's telemetry; skip (we have Send logs and Bug report) |
| Controls: background pad, mouse camera and sensitivity, inverts, stick dead zone, rumble, Motion page, layout preset, button prompts, menu shortcut | have, plus camera centering, camera speed, walk mode and compact menu key |
| Debug: tools, heart protection, no-clip, mark and return, set time, inventory, free camera, teleport, switch age; Descriptor reuse, Sampler cache, Intel shader compiles | have, plus Damage taken, Movement speed and Save my pipeline list |

**HeyListen's user guide (docs/USER_GUIDE.md):**

| Feature | Ours |
|---|---|
| Builder from a `.nup` or romfs/exefs, game-folder updates that download changed parts only | have (our builder and launcher) |
| Insert/F1 menu | have |
| RecompLauncher install | LACK. HeyListen distribution; skip |
| Import saves from emulators | have (SAVE FOLDER, the launcher's "Import saves") |
| **Export saves to an emulator**, **emulator detection with a dry-run listing** | **LACK** (candidate 11; low value with randomizer saves) |
| File mods (`mods/<name>/romfs`) | have (host/mods.c) |
| **Code mods (exeFS `.ips`/`.pchtxt`) in the builder** | **LACK.** Skip: risk to the randomizer's lift patches |
| Linux AppImage, `--cli` builds, udmabuf guidance | partly. Our tree has Linux builder files; not the owner's concern |
| **Crash window with Report manually/automatically** | **LACK** (candidate 12) |
| **Opt-in performance statistics** | **LACK.** Skip |
| In-game update offer (`HOOKSHOT_UPDATE_CHECK=1`, off by default) | n/a (our launcher's own update flow) |
| Problems page with "Copy for a bug report" | have equivalents (the launcher's Send logs, Report on GitHub, the Bug report row) |

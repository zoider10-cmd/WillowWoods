# HeyListen and Triforce: new work, 2026-11-17 (evening)

This pass was read only: nothing was built, run or downloaded. Both ports are GPL-3.0-or-later (each has a LICENSE file
in its tree). Triforce's virtual-core spin includes code from totk-pc-recomp, which is MIT (compatible; keep the notice
if it is ported).

The gains below are judged against what we measured on this PC. The Market by day waits on the renderer's CPU replay
(about 9 ms of a 14 ms frame). Kakariko is the steadier bench (same-build runs vary about 1.5%, against about 7% in the
Market). Changes that cut GPU time or game-code time have not shown a gain here so far.

---

## HeyListen: 504f8362 to 9a9962d2

I read the 11 new engine commits (`git log --no-merges 504f8362..origin/HEAD -- engine`). `docs/benchmarks` has no new
files; only `docs/USER_GUIDE.md`, `docs/recomplauncher.md` and `docs/release/RELEASE_NOTES.md` changed. The release
notes now describe v0.4.2. Their fixes up to 504f8362 were covered in this morning's survey
(`heylisten-2026-11-17.md`, area1-4).

The three renderer fixes come from Mooseca (HeyListen PR #64). Mooseca found them with the Vulkan validation layer on an
**RX 9070 XT** (RADV 26.2.6, Linux), the same GPU as ours. None of the three is in our tree.

### Ranked

1. **Uniform updates of the same bytes land in stream order** (2a12d65c; `vk_replay.cpp` `flush_ub_updates`, plus a new
   `ub_disjoint_writes` of about 30 lines; tests `test_ub_update_order.py` and `test_split_ub_flush.py`).
   - **The problem:** the game updates one uniform block many times per recording (4, 16 and 64 bytes at a time). Each
     update is a `vkCmdUpdateBuffer` with no barrier between them. When two updates hit the same bytes, either one can
     land last, so older bytes may stay for the next frames.
   - **What VVL saw:** about 2000 SYNC-HAZARD-WRITE-AFTER-WRITE reports a second in Kokiri, Hyrule Field and Zora's
     Domain, about 70 a frame.
   - **The fix:** sort the updates by address and merge the overlapping ones on the CPU, in stream order, into one
     write. They tried a barrier first; it cost about 2% fps in Kokiri.
   - **Our code:** `gpu/vk/vk_replay.cpp:1168` is identical to their old version.
   - **Cost:** a small sort per flush, on the replay thread (about 70 items a frame); it also means fewer
     `vkCmdUpdateBuffer` calls. Unmeasured for fps.
   - **Hardware:** none in particular. It is a spec hazard; whether AMD's Windows driver actually reorders these is
     unknown.
   - **Risk:** low. The test checks the merge against in-order application on 2000 random lists. It doesn't touch the
     randomizer.
   - **Verdict: port first.** It is a correctness fix seen on our GPU, it is small, and the barrier version was slower.
     Run a Kakariko A/B as the "no worse" check.
2. **The overlays load their Vulkan functions from the instance** (309585d1; `vk_imgui.cpp` `load`, one line removed;
   test `test_ui_function_loader.py`).
   - **The problem:** ImGui's backend also loads instance-level functions. Asking `vkGetDeviceProcAddr` for those is
     undefined before Vulkan 1.2.193, and VVL warned for 8 names.
   - **Our code:** we have the old version at `gpu/vk/vk_imgui.cpp:43-46`.
   - **Cost:** a few device-level calls a frame now go through the loader's dispatch.
   - **Verdict: port first.** Trivial and no risk; it makes an old-driver crash less likely.
3. **8- and 16-bit integers in shaders only where the device has them** (6f82d229; `vk_shader.cpp` `make_profile` and
   `disk_stamp`).
   - **The problem:** the profile claimed every GPU had shaderInt8 and shaderInt16.
   - **The fix:** take both from the device's features. The cache stamp changes only on a device that lacks them.
   - **Effect here:** none. The RX 9070 XT has both, so our program cache stays valid.
   - **Who it helps:** older or integrated GPUs that lack shaderInt16.
   - **Verdict: later.** Bundle it with another shader change; it costs nothing on this PC.
4. **Open-menu binding** (e43797b7; `vk_menu.cpp`, `nn_hid.c`, `vk_api.h`, `pad_sdl.c`, `hos_sdl.c`; about 320 lines
   with tests).
   - **What it adds:** a Controls row, *Open menu*, that takes one gamepad button or two together (L3+R3,
     Share+Options), saved as `pad_menu=a,b`. Pads also log their SDL mapping.
   - **What we already have:** the touchpad click opening the menu (8790b8f6).
   - **Touches:** `vk_menu.cpp` (a randomizer file) and `vk_api.h` (enums only).
   - **Verdict: later.** It is a user-visible feature we lack, and useful on a pad without Home.

### Skipped

- **Update offer on by default** (36ef4284, 2336d5cf): it points at HeyListen's releases, and the owner has asked for no
  update button.
- **`--play` for the builder and launcher** (37822e38, 14cb9398): RecompLauncher plumbing.
- **The test-stub fix** (42ee0c18): it goes with the update row.
- **Button prompts in releases** (9f863832): only release packaging plus one log line in `prompts.c`. We build locally
  and already have `nx2/prompt_assets.py`.
- **FSR 4 tick downloads the runtime** (50fd7e5e): our builder already passes `--fetch-fsr-runtime`
  (`builder/HookshotBuilder/MainWindow.xaml.cs:1036`).

---

## Triforce: 93eeb714 (v0.4.0) to 72793f2 (v0.5.0 plus the Linux AppImage fix)

The diff is 601 files, about 116,000 lines added. 72793f2 itself only touches the AppImage scripts (`appimage.sh`,
`check_player_build.sh`, `renodx_shaders.py`). Triforce keeps no changelog: the release commit's message and
`readme.md` stand in for one. I read those, `docs/development.md` (the switch table), the new docs
(`lazy-writeback.md`, `framegen-resource-failure.md`, `design.md`), and the header comment of every new `gpu/vk/*.h`
and `host/*` file. Most of the new renderer work is NX2navi's ideas rewritten for Hookshot's design. Triforce's "lab"
(their test PC and scripted tours) measures it at the Market, mostly on NVIDIA. Almost none of it is in our tree: I
checked each switch and file name with grep.

### Ranked

1. **Per-binding descriptor reuse and whole-draw signature skip** (`RX_VK_DESC_KEEP` and `RX_VK_DESC_SIG`, both on by
   default; `gpu/vk/desc_keep.h` 113 lines, `desc_sig.h` 95 lines, about 90 references in `vk_draw.cpp`
   `build_descriptors`, `same_desc`, `desc_sig_walk`).
   - **What it does:** a draw that has to rebuild its descriptors takes each one (texture, UBO, c1, read-only SSBO) from
     the program's last result on that thread, as long as its inputs and stamps match. When the whole signature matches,
     the build and the push are skipped entirely.
   - **The time it targets:** in the owner's test7 session, "descriptors" took 1.5-2.2 ms of a 7.4-9.8 ms replay. Only
     381 of 2,830 draws a frame kept their descriptors before; the build plus compare was 2.0-3.3 ms a frame.
   - **Measured:** time per part only, no fps A/B. Both modes have a `=check` setting that rebuilds and compares, which
     makes a safe self-test.
   - **Our code:** we have `same_desc`, push templates and the sampler cache, but not this.
   - **Hardware:** none in particular; it is CPU work on the replay thread.
   - **Risk:** medium-high. The stamps are subtle (issue 1126: a kept view could name freed memory). Our `vk_draw.cpp`
     differs from theirs, so the port is hand work.
   - **Verdict: port first.** It is the largest replay-CPU cut either port offers, and our Market frame is replay-bound.
     Measure in Kakariko and the Market, run the `=check` mode once, and run the randomizer guard.
2. **Capture copies behind the replay** (`RX_VK_CAPTURE_BEHIND`, on; `gpu/vk/capture_behind.h` 129 lines, about 80
   lines in `vk_memory.cpp` `capture_make`).
   - **What it does:** the submitting thread copies only the pages it needs at once. The rest go to the capture's copy
     helpers in parts of 32 pages while that thread replays.
   - **Their numbers:** at the Market the copy was about 0.25 ms of each submit's 0.35 ms capture, six submits a frame,
     so about 1.5 ms a frame moves off the critical thread.
   - **Our code:** we have the copy helpers (`RX_VK_CAPTURE_THREADS`).
   - **Who it helps:** CPUs with spare cores. It is off with `RX_VK_LOW_SPEC`.
   - **Risk:** medium (memory ordering).
   - **Verdict: port first,** after item 1, with an A/B.
3. **Replay thread at highest priority while it replays** (`RX_VK_REPLAY_PRIO`, on; `gpu/vk/replay_prio.h` 39 lines,
   inside our existing `ReplayPin`, `vk_replay.cpp:2591`).
   - **The idea (NX2navi):** in Kokiri, 274 of 2,737 frames submitted late because the replaying thread was preempted.
     The helper threads (above normal) outrank a replay that runs at the game's normal priority.
   - **Hardware:** Windows only. It could starve other threads on a PC with few cores.
   - **Port size:** tiny.
   - **Verdict: port first.** It is cheap; judge it on the 1% lows.
4. **Start next frame early** (`RX_VK_TAIL_EARLY`, on since options_version 6; a Debug row; `gpu/vk/tail_early.h` 104
   lines, about 60 references in `vk_replay.cpp`).
   - **What it does:** the frame's recording is cut at the upscale dispatch. Where the tail (upscaler plus interface)
     reads and writes no guest memory, the frame's event words are written before the tail. The game's present poll
     then lets the next frame start while the GPU still runs the tail.
   - **Why it may matter here:** on this PC the tail includes FSR 4 Native AA, which we saw is costly.
   - **Measured:** their docs say "not yet run in the game", yet it is on by default in v0.5.0.
   - **Risk:** medium; the event timing is tuned by play.
   - **Verdict: later.** A/B it with FSR 4 on; it may hide FSR 4's GPU time.
5. **Indirect mesh draws stay in their pass** (`RX_VK_MESH_AHEAD`, on; `gpu/vk/mesh_ahead.h` 135 lines).
   - **What it does:** the first indirect mesh draw of a run copies the records for the ones after it, so foliage
     (about 16 a frame at the Market) no longer ends and restarts its pass, which cost three barriers, a fill and a
     copy each.
   - **Who it helps:** mostly the GPU, a little the CPU. Native mesh only; the RDNA 4 driver draws mesh natively.
   - **Verdict: later.** A/B it in Kokiri or Hyrule Field, where there is grass.
6. **Texture lookups kept through other textures' ends** (`RX_VK_VIEW_KEEP`, on; `gpu/vk/view_keep.h` 69 lines plus
   `views_gone` in `vk_texture.cpp`).
   - **What it does:** any eviction or dead render target used to make every thread resolve every texture handle again.
     Now only the looks of textures that actually went are redone.
   - **NX2navi's number:** about 7% more frames where CPU-bound in Kokiri.
   - **Verdict: later.** This is a replay-CPU cut; take it after item 1, since they share the descriptor path.
7. **64-bit page write generations** (`gpu/vk/write_gen.h` and `write_gen_table.h`).
   - **The problem:** our `memory_generation()` and `Texture::upload_gen` are 32-bit (`vk_internal.h:345`,
     `vk_texture.h:57`). After 2^32 generations, textures and mirrors keep stale contents until the next start. NX2navi
     hit that after 15-66 hours of play.
   - **Cost:** about 1-2 MB more of tables.
   - **Verdict: later.** It is a correctness fix for long sessions (a randomizer run can be long). Mechanical, but it
     touches many places.
8. **Failed uploads stay owed** (`gpu/vk/upload_owed.h`).
   - **The problem:** when there is no staging memory, a texture was marked uploaded anyway and stayed wrong until it
     was evicted.
   - **Who it helps:** low-VRAM and low-RAM PCs.
   - **Verdict: later.**
9. **Scissor and clear rectangles without int overflow** (`gpu/vk/rect_clamp.h` 42 lines).
   - **The problem:** a width of INT_MAX wrapped, giving an empty clear or a scissor two billion pixels wide.
   - **Verdict: later.** A tiny correctness fix; take it with any `vk_draw.cpp` port.
10. **Late-page waits end at the writer's recording** (`RX_VK_WB_WAIT_REC`, off by default; `gpu/vk/wb_rec_wait.h`).
    - **Their numbers:** the lab Market had a 20-46 ms stall of the game thread about once a minute (186 waits of 8 ms
      or more in 15 runs).
    - **Measured:** still being measured; it is off in v0.5.0.
    - **Verdict: later.** Watch our stall lines first; it is worth trying only if we see the same.
11. **Game threads spin for a virtual core before sleeping** (`HOS_VCORE_SPIN_US` 250, on; plus a lock-free yield fast
    path; `host/hos_thread.c` `vc_spin`; code from totk-pc-recomp, MIT).
    - **What it does:** cuts an OS wake from each core hand-off. Triforce counted about 66,000 core waits per 5 s at
      the Market, 67 us on average.
    - **Who it helps:** spins only on CPUs with more than 8 logical cores (2 spinners on 16 threads).
    - **Effect here:** the gain is on game threads, which haven't shown up in our Market so far.
    - **Verdict: later.** Run the A/B in Kakariko.
12. **AMD FSR 4 frame generation** (a Frame generation row choice; `vk_fsr4.cpp` +482, `framegen_rows.h`).
    - **What it does:** AMD's library makes one frame between each two, on an RX 9000.
    - **Measured:** their own doc says nobody has run it on a card with FSR 4 frame generation.
    - **Verdict: later.** This is the one new feature aimed at the owner's card. It is untested and large.
13. **RAM savers:** SPIR-V packed at rest (`RX_VK_SPV_PACK`; NX2navi went from 777 to 229 MiB) and kept pipelines
    given back while RAM is short (`RX_VK_PIPE_RELEASE`).
    - **Verdict: later,** only if RAM is short on this PC.

### User-visible settings and features we lack

- **Picture:** Steady frame rate (paced to a rate the PC holds); frame pacing smoothing on the plain present
  (`RX_VK_PACE_SMOOTH`, on after their A/B); a VSync row; caps of 30, 40 and 45; RivaTuner limiter integration;
  Reflex limit; an Anti-aliasing row (FXAA, SMAA Ultra; `third_party/smaa` added); Texture detail; Opaque textures as
  BC1 (VRAM; it conflicts with our AMD BC3 workarounds, as HeyListen's did); ultrawide 16:10, 21:9 and 32:9; HDR and
  RenoDX rows.
- **Controls:** dead zones per stick, Rumble strength, Vibration curve, Trigger vibration, Walk scale.
- **Menu and overlay:** menu sounds read from the game files; a full performance overlay (GPU and CPU load and
  temperature through NVML or ADL, 1% and 0.1% lows, replay time).
- **Saves and reports:** Export and Import save (zip); a bug capture on F8 (frame.png, log tail, save, position).
- **Debug and mods:** Debug pages for game flags by name and cutscenes by name (useful for randomizer testing; host
  code in `hos_main.c`); amiibo scan; one game per folder (`hos_instance.h`); a 32 KiB stack guarantee, so a stack
  overflow still writes its crash report (`hos_stack_guarantee`); mods with code patches and cheats, and a GameBanana
  browser.
- **Tooling:** `RX_VK_FRAME_TRACE=1` writes a frames.csv with each frame's replay parts, and `scripts/frame_rank.py`
  ranks the slow frames. Both could sharpen our A/Bs.

### Skipped

- **Parallel replay fixes and tuning** (`RX_VK_PARALLEL*`, `upload_earliest`, `reupload_early`, `touch_quick`,
  `stream_order`, `helper_spin`, `replay_threads`): RX_VK_PARALLEL was slower here (-5.5%) and is off.
- **Barrier relaxations** (`RX_VK_PASS_BARRIER=game`, `SPLIT_BARRIER=pass`, `EVENT_BARRIER=late`): they default to
  NVIDIA only and keep full barriers on AMD; they are GPU-side.
- **Lazy write-back:** stays off on AMD's driver by their own rule (NX2navi's AMD players crashed in play).
- **Import ahead:** off after GPU hangs at the title (6 of 12 runs).
- **Gate wait:** off, and a lab switch.
- **Occlusion answers** (`occ_answer.h`): we already have real occlusion counts (`RX_VK_OCC_QUERIES`, upstream).
- **Task/mesh fallback for every AMD RDNA 1/2 on Windows:** not our RDNA 4 card.
- **Texture re-upload work for the after-tour Market** (`upload_same`, `shadow_prev`, `upload_torn`): we tried
  `RX_VK_TEX_SAME` (pass 2), which gave no gain and cost the replay. Worth a look only if a long session shows white
  frames.
- **Present thread:** off in Triforce itself (the lab found no gain).
- **Step steady:** cost nothing at the Market in their A/B, and its gain is pacing smoothness; low priority.
- **Code-patch mods** (`nx2/code_mods.py`, `emit_pool.py`, `chunks.py`, `build.py`): they touch the lift and would
  collide with the randomizer's patches.
- **X3D die pinning** (`HOS_X3D`): only for two-die X3D CPUs.
- **The rest:** RTSS, DLSS-G, RenoDX and HDR, SMAA (picture options, not fixes); the Mask Salesman and GameBanana
  browser, Setup's Mods, Steam and sound pages; NVML and ADL telemetry.

---

## Read up to

- HeyListen: `9a9962d2` (origin/HEAD, 2026-11-18), engine commits from 504f8362.
- Triforce: `72793f2` (v0.5.0 plus the Linux AppImage fix), tree diff from 93eeb714.

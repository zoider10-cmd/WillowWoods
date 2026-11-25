# Longshot survey, 2026-11-24 (b) (8aa5ab87..origin/HEAD 863aaf8d, 5 commits; read only)

**Goal (the owner's, 2026-11-24): compatibility and performance across all PCs and platforms** (NVIDIA, Intel, AMD, low
VRAM, narrow PCIe, Steam Deck/Linux, older CPUs, 16 GB RAM), never breaking the owner's PC (RX 9070 XT, Windows 11).

Follows longshot-2026-11-24.md (surveyed to 8aa5ab87). Read with `git show` in the no-checkout clone; nothing built, run
or installed. All five commits are new here (none is an ancestor of 544229a2, the sources.json base note). Our tree
searched at C:\Users\beerc\Hookshot.

**Summary.** A small batch with no renderer or performance change. Two player-visible fixes: the d-pad prompt icons
follow the bindings (keyboard players saw a pad's d-pad), and the area title card's frame fits ultrawide and 16:10
pictures; the second is lift work through nx2/oot_patches.py, so it is excluded. One input fix restores Longshot's
RenHDrum rumble integration, which we never took; only its "honour the game's PermitVibration" part applies to our
code. The other two are CI and test upkeep. Nothing here is worth doing before the ReLink replay items
(relink-2026-11-24.md #1-#2).

## Ranked list

| # | Change | What it does | Helps | Risk | Status |
|---|---|---|---|---|---|
| 1 | 863aaf8d (#1921) | d-pad prompt icons show what the d-pad is bound to: the keys on the Keyboard face, the bound button on a pad face | keyboard players (every PC), rebinders | low-medium; hand merge, prompts rebuilt | later (UX) |
| 2 | 9046a8d7 (#2478), the permission part only | PermitVibration(false) silences the pads and IsVibrationPermitted reports it; IsOunceVibrationDeviceMounted HLE'd | anyone, if the game revokes vibration (not shown for OoT) | low | later, small |
| 3 | 6123c76a (#2463), test_wb_spans.py only | `#include <memory>` in the check's harness | dev: a stricter libstdc++ | none | only if our check fails |

Excluded (lift / randomizer file): **3395639a** (#1841, title card frame: nx2/oot_patches.py + nx2/oot_wide.py).
Not applicable: the rest of **9046a8d7** (RenHDrum, which we lack), **6123c76a** (their own checks, website, mise),
**ef280956** (CI secrets, website workflow).

## Candidates

### 1. The d-pad icons show what the d-pad is bound to, on every face (863aaf8d, #1921) - LATER (UX, medium hand merge)
- **What it does.** In texts and on the HUD (the icon between the ocarina and Navi), the d-pad icons showed the face's
  own d-pad whatever the controls. On the Keyboard prompts a pad's d-pad stood where the keys are 1 2 3 4; on a pad
  face, a d-pad bound elsewhere still showed the d-pad. Now `nx2/prompt_assets.py` (`dpad_glyphs`, `dpad_table`,
  `prompts/dpad.bin`) builds each d-pad icon from four pieces (CFF global subrs: each face's icon of each input, each
  key's icon, hollow pieces), and `host/prompts.c` writes the calls for the current bindings when it serves the font
  (`dpad_bind`), plus a glyph per set of pieces for texts rewritten while the game runs (`dpad_slot`, `slots_point`).
- **Measured.** A fix (player report "There are still sections that don't have the PC buttons"). ~395 lines of test.
- **Our tree.** Same bug: nx2/prompt_assets.py:81 `STATIC = {0xE049: "dpad", ...}` keeps the d-pad icons static, and
  host/prompts.c:73 says so. Both files have diverged from their parent: 470 diff lines in prompts.c (our own face
  choice and size-table handling), 168 in prompt_assets.py.
- **Hardware.** None; every keyboard player.
- **Port.** Medium: ~186 lines in prompts.c and ~224 in prompt_assets.py by hand, plus their test adapted. The prompt
  assets are made from the game's font at the build (make_game.py:3228, `--incremental`), so a game build is needed to
  see it (assets built from the game: never sent). Not a randomizer file, not the lift.
- **Risk.** Low-medium: a wrong glyph table shows a blank or wrong icon; the font is served to the game, so a bad
  CFF edit could cost every prompt. Test on the Keyboard face and one pad face.

### 2. The game's vibration permission honoured (9046a8d7, #2478; the nn_hid part only) - LATER (small)
- **What it does.** `PermitVibration(false)` zeroes the motor amplitudes, sends silence (motors and HD), and makes
  `vibration_send` drop values until permitted again; `IsVibrationPermitted` reports the flag. Also HLEs
  `IsOunceVibrationDeviceMounted` (both forms) as mounted.
- **Our tree.** host/nn_hid.c:1526-1527: `PermitVibration` returns 0 and does nothing; `IsVibrationPermitted` always
  says 1. No Ounce HLE. Whether OoT ever calls PermitVibration(false) (say, in the HOME/pause path) is not shown: check
  with a call log before porting, or the change does nothing.
- **Port.** ~40 lines in nn_hid.c (an SRW lock around `vibration_send`, the flag, the two HLEs); our HD path is
  `hd_rumble.h` / pad_sdl.c, not RenHDrum, so the silence call becomes ours (`hos_sdl_rumble(0, 0)` and an HD idle
  value per side). Their `tests/test_vibration_permission.py` adapts.
- **Risk.** Low.

### 3. test_wb_spans.py's harness includes `<memory>` (6123c76a) - ONLY IF NEEDED
- One line. Our tests/test_wb_spans.py (taken 11-24) has the same include list; it uses no `std::unique_ptr` itself,
  so this matters only if the source it cuts needs `<memory>` under some compiler. Take it if the check ever fails to
  build.

## Excluded (touches the lift / a randomizer file)
- **3395639a (#1841) The area title card's frame fits the picture on every screen shape.** Above 16:9 (21:9, 32:9,
  48:9) the big area card's frame stayed at 16:9 width; below 16:9 (16:10: the Steam Deck) the joining lines are
  shortened. host/hos_wide_ui.c (+416), and hooks in nx2/oot_wide.py and **nx2/oot_patches.py**: a re-lift and a
  randomizer file, so not ported. Measured on an RTX 5090 at 21:9 / 32:9 / 48:9 / 16:10: frames whole, no
  end-of-reveal jump. Note it for the owner only if ultrawide or Deck players report the card.

## Not applicable
- **9046a8d7 (#2478), the rest.** It restores Longshot's RenHDrum integration (#2418): host/rumble_renhdrum.c, the
  Compatible Bluetooth profile for the original Switch Pro Controller, a 40 ms USB refresh, DualSense crisp notes and a
  high-resolution Bluetooth timer, Xbox trigger effects (200 ms with a 100 ms refresh), vibration shutdown on the close
  path. We have none of RenHDrum, vibration.h or the trigger/DualSense haptics; our Switch HD rumble is our own
  host/hd_rumble.h through SDL's effect call, and our motors are SDL_GameControllerRumble with a duration (they stop on
  their own at exit). Untested on hardware in their PR too.
- **6123c76a (#2463).** Their checks brought in line with #2383 / #2258 / #2338 (code we took in part or not at all),
  the website, a guide image, mise pins. Only the test_wb_spans line above touches a check we have.
- **ef280956 (#2429).** CI: seal.key only for main and v* tags; the website's PR code off the deploy runner. CI only.

## Surveyed up to
origin/HEAD **863aaf8d** (2026-11-25 UTC, "fix(prompts): the d-pad icons show what the d-pad is bound to").

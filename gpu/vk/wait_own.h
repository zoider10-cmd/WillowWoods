// Copyright (C) 2026 Sacrappy

// (HeyListen 51e533a8, from v0.4.4 and Hookshot 737a0975 by bubblesnout) RX_VK_WAIT_OWN: how far behind the GPU the replay lets the game run at each present, for the hazard of a GPU
// that reads guest memory where it is (an integrated GPU: no VRAM mirror, vk_memory.cpp mirror_on) and a game that rewrites its HUD's
// records before a pass has read them (a Radeon 890M, ROG Xbox Ally X: icons flashing, the minimap drawn with another texture).
// Plain functions: tests/test_wait_own.py compiles this header and checks them.
//   0  no wait (any GPU's default but an AMD integrated one's on Windows: vk_replay.cpp do_present)
//   1  each present waits for its own frame's GPU work: the GPU idle while the game builds the next frame, so the frame time is
//      the game's plus the GPU's (v0.4.3's rule on an AMD integrated GPU; the ROG Ally X and the BC-250 lost fps, #81, #67). The default on an
//      AMD integrated GPU: on a Ryzen 7 5700U (24 Nov, pictures every 60 presents, the camera turning) it is the only value with a
//      whole HUD, 0 wrong pictures of 18; 0, 2 and 3 gave 16, 17 and 15 wrong of 20 (hearts missing, the minimap another texture)
//   2  each present waits for the frame before's GPU work: the game is at most one frame ahead of the GPU, the console's own two
//      frames in flight (its records are a ring of two: a frame's are rewritten once the one before it is done), and the GPU works
//      while the game builds the next frame
//   3  as 2, and a present whose frame uploaded textures (the game wrote texels the GPU then reads: the HUD's icons and minimap, the
//      glitches' moment: the ROG Ally X's stutters of 5-10 fps and flashes came with texture uploads, #81) waits for its own frame's
//      work as 1. Steady frames pay the frame before's wait only. (The default from 20 to 24 Nov, never released: it flickers)
#pragma once
#include <cstdint>
#include <cstdlib>

namespace wait_own {

/// The mode: RX_VK_WAIT_OWN's number when set (0, 1, 2 or 3; any other nonzero number is 1: the switch's old rule), else 0 when
/// RX_VK_WAIT_GPU (a ring of frames) is set, else 1 on an AMD integrated GPU, else 0
inline int mode(const char* own_env, bool wait_gpu_set, bool amd_igpu) {
    if (own_env) {
        const int v = atoi(own_env);
        return v == 0 ? 0 : v == 2 ? 2 : v == 3 ? 3 : 1;
    }
    if (wait_gpu_set) return 0;
    return amd_igpu ? 1 : 0;
}

/// The value this present waits for, given the mode, its own value, the value of the present before it (0: none yet) and whether the
/// frame uploaded textures; `prev` is updated to this present's. 0: nothing to wait for
inline uint64_t target(int mode, uint64_t value, uint64_t& prev, bool uploaded = false) {
    const uint64_t before = prev;
    prev = value;
    return mode == 1 ? value : mode == 2 ? before : mode == 3 ? (uploaded ? value : before) : 0;
}

}   // namespace wait_own

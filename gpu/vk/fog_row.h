// (HeyListen 5716afbf, the Volumetric fog row only: not its first-start low-end rule) The volumetric fog's compute programs, left
// out with the Graphics tab's Volumetric fog row Off (vk_draw.cpp dispatch, vk_menu.cpp fog_runs). RX_VK_FOG=0/1 decides over
// the row. tests/test_fog_row.py
#pragma once
#include <cstdint>

namespace fog_row {

// The volumetric fog: 27ee9883e2a20323 (a 96x72x88 froxel volume with shadow lookups), ee7764a6b1ef459c (48x36x48) and
// 1e2fcee33a0c7209 (the 96x72 pass after the first). The first and the third ping-pong two sets of images by frame parity, so a
// lower rate is wrong (HeyListen's GPU11: the haze goes, or a white-out); left out from the start they write nothing and the
// scene reads no haze: no black, flashing or undefined parts (their pictures in Hyrule Field and the Lost Woods). On a Ryzen 7
// 5700U's Vega 8 they cost about 9 ms of a 60 ms frame; on an RTX 3050 0.6-1.1 ms (HeyListen's measures)
inline bool fog_program(uint64_t key) {
    return key == 0x27ee9883e2a20323ull || key == 0xee7764a6b1ef459cull || key == 0x1e2fcee33a0c7209ull;
}
/// Whether the fog runs: RX_VK_FOG (env: -1 unset, else 0 off / 1 on) over the row (row: opts.fog, 1 on)
inline bool fog_on(int env, int row) { return env >= 0 ? env != 0 : row != 0; }

}  // namespace fog_row

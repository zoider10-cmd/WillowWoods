// (Triforce v0.7.0 e6f2f248, taken 2026-11-22; Triforce, 11-21, the performance audit's DESC-12, after Source A's) An indexed draw's index buffer bound at offset 0,
// with the draw's offset given as its first index.
//
// The game's draws share one buffer at different offsets, so bind_index's skip (the same buffer, offset and type as the
// one on the command buffer) rarely held: nearly every indexed draw called vkCmdBindIndexBuffer, about 2,900 calls a frame
// in the Market. Bound at 0 with the offset as the draw's firstIndex, the skip holds until the buffer or the index type
// changes. Only where the offset is a whole number of indices that fits a first index; otherwise the draw binds at its
// offset as before. Indirect indexed draws are not touched: their first index is in the GPU's records.
// RX_VK_INDEX_REBASE=0: every draw binds at its own offset, as before.
//
// The rule alone, no Vulkan: tests/test_index_rebase.py compiles it.
#pragma once
#include <cstdint>
#include <cstdlib>

namespace index_rebase {

/// The switch's value: on unless it is set to 0
inline bool on(const char* asked) { return !(asked && *asked && atoi(asked) == 0); }

/// Whether a draw whose indices start offset bytes into its buffer, unit bytes an index, can be drawn from the buffer bound
/// at 0: *first is then its first index. Not when the offset falls inside an index, nor past what a first index the draw's
/// own range is added to can hold
inline bool rebase(uint64_t offset, uint32_t unit, uint32_t* first) {
    if (!unit || offset % unit || offset / unit > 0x7fffffffull) return false;
    *first = (uint32_t)(offset / unit);
    return true;
}

}   // namespace index_rebase

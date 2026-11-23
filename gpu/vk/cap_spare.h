// (Triforce v0.7.0 e6f2f248, taken 2026-11-22; Triforce, 11-22, the performance audit's MEM-33, after Source A's) Which spare capture buffer a capture takes, how
// much the spares and the ones being made ahead may hold together, and a capture's size in steps.
//
// A capture's buffer comes from the spares (retired buffers, and the 32 to 192 MB ones made ahead on a worker), or is
// made new on the game's submitting thread. Three things were so before:
//  - the new buffer was made with cap_free_mu held (AMD's driver: about 0.8 ms a MB), and the replay's take, holding
//    pools_mu, waits on that mutex to retire a buffer;
//  - any spare that fit was taken, so a 2 MB capture could sit in a load's 192 MB spare for the 24 submissions a capture
//    is kept, and the load then made its own on the game's thread;
//  - a spare made ahead was made once: the one a load took was not made again.
// The rules here are the decisions alone (no Vulkan, no lock): tests/test_capture_spare_reuse.py compiles them, and
// vk_memory.cpp's cap_buf_get, cap_prewarm_class and cap_buf_free ask them. RX_VK_CAP_SPARE_FIT=0: as before.
#pragma once
#include <cstddef>
#include <cstdint>

namespace cap_spare {

constexpr uint64_t kMB = 1ull << 20;
constexpr uint64_t kBig = 32 * kMB;    // (a load's spare: the classes made ahead start here)
constexpr uint64_t kHeld = 768 * kMB;  // (the most the spares hold, whatever the card)
constexpr size_t kMost = 12;           // (and the most there are)

/// A capture of size class `cls` leaves the spare of `size` bytes alone: a big one (32 MB or more) over twice its class.
/// any_size: no spare is left alone (spares capped at 32 MB, the switch off, or the fallback after a failed allocation)
constexpr bool skips(uint64_t size, uint64_t cls, bool any_size) { return !any_size && size >= kBig && size > 2 * cls; }

/// The spare a capture of `need` bytes (class `cls`) takes of n spares, size_of(i) the i-th one's bytes: the smallest that
/// fits and is not left alone, the first of equals. n: none
template <class SizeOf>
constexpr size_t pick(size_t n, const SizeOf& size_of, uint64_t need, uint64_t cls, bool any_size) {
    size_t best = n;
    for (size_t i = 0; i < n; i++) {
        const uint64_t s = size_of(i);
        if (s >= need && !skips(s, cls, any_size) && (best == n || s < size_of(best))) best = i;
    }
    return best;
}

/// Room for one more spare of `size` bytes to be made ahead: with what the spares hold and what is being made (reserved)
/// it stays within what spares may hold (spare_max: the card's, cap_spare_max) and 768 MB
constexpr bool room(uint64_t held, uint64_t reserved, uint64_t size, uint64_t spare_max) {
    const uint64_t limit = spare_max < kHeld ? spare_max : kHeld;
    return held + reserved <= limit && size <= limit - (held + reserved);
}

/// A buffer of `size` bytes given back is kept as a spare: fewer than 12 with the ones being made (workers), none over 256
/// MB (keep_old, RX_VK_CAPTURE_KEEP_OLD: 64), and with the bytes being made (reserved) within the limit. With no workers
/// and nothing reserved this is the rule as it was
constexpr bool keeps(size_t spares, size_t workers, uint64_t held, uint64_t reserved, uint64_t size, uint64_t spare_max, bool keep_old) {
    const uint64_t limit = keep_old ? spare_max : (spare_max < kHeld ? spare_max : kHeld);
    return spares + workers < kMost && size <= (keep_old ? 64 * kMB : 256 * kMB) && held + reserved <= limit &&
           size <= limit - (held + reserved);
}

/// (RX_VK_CAP_STEP_MB=<n>, 0: off) a capture over 16 and up to 32 MB in steps of step_mb MB, not the whole 32 MB class,
/// where spares are capped at 32 MB (a card of 6.5 GB or less). cls: its class as it is (cap_buf_size)
constexpr uint64_t stepped(uint64_t need, uint64_t cls, uint64_t step_mb, bool capped) {
    if (!step_mb || !capped || cls != kBig || need <= 16 * kMB || need > kBig) return cls;
    const uint64_t step = step_mb * kMB, v = (need + step - 1) / step * step;
    return v < cls ? v : cls;
}

}   // namespace cap_spare

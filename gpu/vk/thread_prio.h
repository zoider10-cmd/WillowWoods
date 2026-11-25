// (HeyListen c81f500c, on 016f1507: PRIO1) Keeps the threads that only compile in the background (RX_VK_THREAD_PRIO) off the
// replay thread's core. Header only.
//
// The host keeps one physical core (both its hardware threads, hos_reserved_cpus) for the replay thread. A compile thread on the
// sibling hardware thread of that core slows the replay (up to 1.7x, the host's own measure), and a lower priority does not help
// there: priority only matters when no processor is free, and the sibling is free. HeyListen's PC 3050 (i5-10400F, Kokiri, cold
// shader cache, 3 rounds): off 52.3-52.7 fps, pinned 55.0-55.7 (+4.7%); warm the same. Priorities are left as they were.
//
// Which threads here: the in-play ones only, the shaders translated behind the game after an update (prepare_background:
// prepare_run's workers, and the state list and library warming it may run) and the predicted pipelines built behind the game
// (predict_background: predict_run's workers). A thread pinned here marks itself, so the workers it starts are pinned too
// (pinned_here). Not the start's preparation, prediction and precompile (the game waits for them, nothing to share the core
// with), and NOT the jobs workers (vk_jobs.cpp): they also run work a frame waits for, and keeping them off two logical
// processors cost HeyListen's warm case about 1%; they, the replay's workers, the capture helpers and the game's threads are
// untouched. RX_VK_THREAD_PRIO=0: off. Windows only (on Linux a thread inherits its creator's affinity and the shim has none):
// no effect there.
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <string>

namespace mkwvk::prio {

inline int mode() {
    static const int m = [] {
        const char* e = getenv("RX_VK_THREAD_PRIO");
        return e && *e ? (atoi(e) != 0 ? 1 : 0) : 1;
    }();
    return m;
}

/// The processors a background compile thread may use: the process's, without the replay's core; all of them when that leaves none
inline uint64_t compile_mask(uint64_t process, uint64_t reserved) {
    const uint64_t m = process & ~reserved;
    return m ? m : process;
}

// (installed by the renderer's init, Windows: pins the calling thread with compile_mask)
struct Hooks {
    void (*pin_compile)() = nullptr;
    uint64_t pinned_off = 0;   // (the mask kept free, for the start line)
};
inline Hooks& hooks() {
    static Hooks h;
    return h;
}

/// Whether this thread was pinned here (a background compile thread): the workers it starts are pinned as well
inline bool& pinned_here() {
    static thread_local bool p = false;
    return p;
}

inline void pin_background() {
    if (mode() > 0 && hooks().pin_compile) {
        hooks().pin_compile();
        pinned_here() = true;
    }
}

inline std::string describe() {
    char b[400];
    if (mode() == 0) {
        std::snprintf(b, sizeof b, "off (RX_VK_THREAD_PRIO=0): every thread keeps the processors it had");
        return b;
    }
    if (!hooks().pinned_off) {
        std::snprintf(b, sizeof b, "RX_VK_THREAD_PRIO=1: no core is kept for the replay here, nothing pinned");
        return b;
    }
    std::snprintf(b, sizeof b,
                  "RX_VK_THREAD_PRIO=1: the background compile threads (in play: the shaders after an update, the predicted pipelines) "
                  "are kept off logical processors %#llx (the replay's core); priorities, the jobs workers and the game's threads as "
                  "they were",
                  (unsigned long long)hooks().pinned_off);
    return b;
}

} // namespace mkwvk::prio

#define MKWVK_PIN_BACKGROUND() ::mkwvk::prio::pin_background()

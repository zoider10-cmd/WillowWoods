"""Acquire ahead: the presenter thread asks for the window's next image right after its present, and #1376's hang stays impossible.

Since #1458 the swapchain's image is waited for on the CPU at its present (present_image: the acquire's fence, image_free).
AMD's driver on Windows hands the image back from vkAcquireNextImageKHR at once and leaves the wait to the fence; in a window
the system gives it back a few ms later, and the render thread waited for it every frame. With acquire ahead the presenter
thread (on every PC since #1763) asks for the next image right after its own present of a game frame (a timeout of 0), while
the swapchain is still its own, so the fence is signaled while the next frame is made.

Cut out of gpu/vk/vk_replay.cpp and compiled against a model of a presentation engine: present_image's acquire (from its drain
of the presenter to the frame's command pool reset), its copy's submit info and its end (the hand-over); the helpers before it
(the image's fence, the fences let go, the held image, the image-wait counter) and the ahead acquire after it; the presenter's
state, presenter_wait_idle, present_hand_off and present_thread_drain; and presenter_loop's take of a hand-over and its end
(from present_finish to the presenter saying it is done). The model's engine hands an image back at once and signals its fence
a while later (AMD's driver on Windows), or never while the window is hidden; or, NVIDIA-like, the wait is in the acquire and a
timeout of 0 gives none. The presenter runs right after each hand-over, or late (when the render thread waits for it), or not
at all (stuck). Each platform's side of the source's _WIN32 lines is compiled on its own.

Ported from Longshot 12bd87e0 (#1574). Hookshot has no device_policy.h: acquire ahead is on by default wherever the presenter
thread runs (RX_VK_PRESENT_THREAD; acquire_ahead_wanted), and RX_VK_ACQUIRE_AHEAD=0 turns it off. Each platform side runs three
ways: the switch unset, =0 (the off path) and =1. Checked:

- off: one acquire in each present, on the render thread, before its copy, waited for there (#1458's order); none on the
  presenter;
- on: the acquire for present k+1 made on the presenter after its present of k came back VK_SUCCESS, with presenter.mu and the
  swapchain's lock (presenter_queue_mu) held, the queue's lock not, a timeout of 0; never two images out; present k+1 does not
  wait when the fence was signaled meanwhile; the render thread never acquires or reads the image while the presenter owns
  the swapchain;
- the first present's line says which way it went, once; the image-wait counter only with the switch set to on;
- the image still not free at its present: waited for up to kImageFreeNs, shown, no frame dropped;
- #1458's own case (the window hidden): no copy waits on the GPU for the image, none into an image not given back, no other
  acquire while it is held, frames shown again once it is given back;
- the swapchain made again with an ahead image out (off: a held one, the window hidden): let go, a fence that is not in use
  and unsignaled for every acquire; a
  fence let go unsignaled is used again only once signaled, and then before a new one is made;
- a present that came back suboptimal: no image asked for ahead of the swapchain it asks to make again;
- the presenter late (it runs when the render thread waits for it): every present made, one image out;
- a drain that gave up on a stuck presenter: no image asked for ahead after it;
- frame generation, FIFO and the start-up screen's presents: no ahead acquire;
- an NVIDIA-like engine: the ahead acquire never waits; a lost device at the ahead acquire is reported; an out-of-date answer
  to it takes no image, and the next present makes the swapchain again.

Broken variants that must fail are listed in BROKEN below, each with what it breaks.

No GPU.

python -I -B tests/test_present_acquire_ahead.py [--cxx clang++]
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # (tests/srccut.py: python -I leaves this folder off the path)
from srccut import between, block   # noqa: E402
from test_present_image_free import platform_side   # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]

FIXTURE_HEAD = r'''
#include <algorithm>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <vector>
using VkResult = int;
using VkFence = uint64_t; using VkSemaphore = uint64_t; using VkSwapchainKHR = uint64_t; using VkCommandBuffer = uint64_t;
using VkCommandPool = uint64_t;
constexpr uint64_t VK_NULL_HANDLE = 0;
constexpr VkResult VK_SUCCESS = 0, VK_NOT_READY = 1, VK_TIMEOUT = 2, VK_ERROR_DEVICE_LOST = -4,
    VK_ERROR_SURFACE_LOST_KHR = -1000000000, VK_SUBOPTIMAL_KHR = 1000001003, VK_ERROR_OUT_OF_DATE_KHR = -1000001004;
constexpr int VK_TRUE = 1, VK_STRUCTURE_TYPE_FENCE_CREATE_INFO = 8, VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO = 1000314005,
    VK_STRUCTURE_TYPE_COMMAND_BUFFER_SUBMIT_INFO = 1000314006, VK_STRUCTURE_TYPE_SUBMIT_INFO_2 = 1000314004;
using VkPresentModeKHR = int;
constexpr VkPresentModeKHR VK_PRESENT_MODE_IMMEDIATE_KHR = 0, VK_PRESENT_MODE_MAILBOX_KHR = 1, VK_PRESENT_MODE_FIFO_KHR = 2;
constexpr uint64_t VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT = 0x10000;
struct VkFenceCreateInfo { int sType; const void* pNext = nullptr; int flags = 0; };
struct VkSemaphoreSubmitInfo { int sType; const void* pNext = nullptr; VkSemaphore semaphore = 0; uint64_t value = 0;
    uint64_t stageMask = 0; uint32_t deviceIndex = 0; };
struct VkCommandBufferSubmitInfo { int sType; const void* pNext = nullptr; VkCommandBuffer commandBuffer = 0; uint32_t deviceMask = 0; };
struct VkSubmitInfo2 { int sType; const void* pNext = nullptr; int flags = 0; uint32_t waitSemaphoreInfoCount = 0;
    const VkSemaphoreSubmitInfo* pWaitSemaphoreInfos = nullptr; uint32_t commandBufferInfoCount = 0;
    const VkCommandBufferSubmitInfo* pCommandBufferInfos = nullptr; uint32_t signalSemaphoreInfoCount = 0;
    const VkSemaphoreSubmitInfo* pSignalSemaphoreInfos = nullptr; };
struct Extent { uint32_t width = 1920, height = 1080; };
struct QueueLock {   // (dev.present_mu, the queue's: the replay's submits take it; dev.presenter_queue_mu, the swapchain's)
    bool held = false;
    void lock() { held = true; }
    void unlock() { held = false; }
    bool try_lock() { return held ? false : (held = true); }
};
enum class Sw { acquire_ahead };
struct Policy {   // (device_policy.h's acquire_ahead: the PC's default, RX_VK_ACQUIRE_AHEAD over it; main sets it)
    bool acquire_ahead = false, by_switch = false;
    bool set(Sw) const { return by_switch; }
};
struct Device { int device = 1; VkSwapchainKHR swapchain = 1; uint64_t swapchain_generation = 0; Extent swap_extent;
    std::vector<VkSemaphore> swap_rendered{901, 902, 903, 904}; QueueLock present_mu, presenter_queue_mu;
    VkPresentModeKHR swap_mode = VK_PRESENT_MODE_IMMEDIATE_KHR; Policy policy; } dev;
struct Frame { VkCommandPool pool = 11; VkCommandBuffer cmd = 12; VkFence done = 13; };
namespace fps_stats { enum { kGpuWait, kPace }; }
namespace gpu_wait_stats { struct Exclude { Exclude() {} }; }
void fps_wait(int, int64_t) {}
bool fps_breakdown_on() { return false; }
void framelog_collect(int) {}
int64_t now_ns = 0;   // (the model's clock: only the waits move it, and the frames' work)
int64_t fps_clock() { return now_ns; }
std::vector<std::string> logs;
template<class... T> void logf(const char* f, T... a) {
    char b[1024];
    if constexpr (sizeof...(T) == 0) std::snprintf(b, sizeof b, "%s", f);
    else std::snprintf(b, sizeof b, f, a...);
    logs.push_back(b);
}
bool invalidate_lost_surface(VkResult) { return true; }
bool fg_on = false;
bool framegen_on() { return fg_on; }
bool present_thread_on() { return true; }   // (on every PC since #1763)
struct Lost {};
int lost_reports = 0;
[[noreturn]] void device_lost() { ++lost_reports; throw Lost{}; }
int problems = 0;
void problem(const char* what) {   // (the first 12 said)
    if (++problems <= 12) std::printf("FAIL (%s, %s): %s\n", PLATFORM, MODE, what);
}

// ---- the presentation engine ----
constexpr int kImages = 4;
constexpr int64_t kNever = INT64_MAX, kMs = 1000000;
int64_t delay_ns = 3 * kMs;   // (an image's fence is signaled this long after its acquire, AMD-like)
bool shown = true;            // (the window seen; hidden: no image acquired is given back until engine_lets_go)
bool give_at_once = true;     // (false, NVIDIA-like: the wait is in the acquire, and a timeout of 0 gives no image)
bool lose_at_ahead = false;   // (the device lost at the next ahead acquire)
bool out_of_date = false;     // (every acquire answers VK_ERROR_OUT_OF_DATE_KHR until the swapchain is made again)
bool remake_kills = true;     // (a swapchain made again: its images out never given back (true), or their fences still signaled)
struct FenceState { VkFence fence; int64_t at; };   // (handed to an acquire and not reset: signaled once now >= at)
std::vector<FenceState> fences;
struct Out { VkSwapchainKHR sc; int image; VkFence fence; bool given_back; };   // (acquired, not presented)
std::vector<Out> out;
int next_image = 0, acquires = 0, ahead_acquires = 0, presents = 0, submits = 0, copied_into = -1, ahead_out_of_date = 0;
int fences_made = 0;
bool ahead_waited = false, resize_asked = false, presenter_presented = false;
VkResult next_present_result = VK_SUCCESS;
FenceState* fence_of(VkFence f) { for (auto& s : fences) if (s.fence == f) return &s; return nullptr; }
void remake() {   // (the swapchain made again)
    if (remake_kills) for (const Out& o : out) if (FenceState* s = fence_of(o.fence)) s->at = kNever;
    out.clear();
    dev.swapchain_generation++, dev.swapchain++, next_image = 0, out_of_date = false;
}
bool create_swapchain(uint32_t, uint32_t) { remake(); return true; }
void engine_lets_go() { for (auto& s : fences) if (s.at == kNever) s.at = now_ns; }
void hide() {   // (the window hidden: what is out and not given back yet stays so, an image asked for ahead too)
    shown = false;
    for (auto& s : fences) if (s.at > now_ns) s.at = kNever;
}
std::unique_lock<std::mutex>* presenter_lk = nullptr;   // (set while the model's presenter thread runs: presenter_run)
bool presenter_busy();
VkResult vkAcquireNextImageKHR(int, VkSwapchainKHR sc, uint64_t timeout, VkSemaphore, VkFence fence, uint32_t* index) {
    const bool ahead = presenter_lk != nullptr;   // (on the presenter thread: the ahead acquire)
    if (ahead) {
        if (!presenter_lk->owns_lock()) problem("the ahead acquire without presenter.mu held: a drain that gave up may go on beside it");
        if (!dev.presenter_queue_mu.held) problem("the ahead acquire without the swapchain's lock (presenter_queue_mu)");
        if (!presenter_presented) problem("the ahead acquire before the presenter's present of the frame it follows");
        if (timeout) problem("the ahead acquire may wait: a timeout that is not 0");
    } else if (presenter_busy()) {
        problem("an acquire on the render thread while the presenter still owns the swapchain (no drain first)");
    }
    if (ahead && lose_at_ahead) return VK_ERROR_DEVICE_LOST;
    if (sc != dev.swapchain) problem("an acquire on a swapchain made again since");
    if (!fence) problem("an acquire without the image's fence");
    if (fence_of(fence)) problem("the acquire's fence is signaled or still in use (VUID-vkAcquireNextImageKHR-fence-01287)");
    if (dev.present_mu.held) problem("an acquire with the queue's lock held: the replay's submits wait for it");
    if (!out.empty()) problem("a second image acquired while one is out (one at most)");
    if (out_of_date) { if (ahead) ++ahead_out_of_date; return VK_ERROR_OUT_OF_DATE_KHR; }   // (no image, the fence untouched)
    if (!give_at_once) {
        if (!timeout) return VK_NOT_READY;
        now_ns += delay_ns;   // (the wait in the acquire)
        if (ahead) ahead_waited = true;
    }
    ++acquires;
    if (ahead) ++ahead_acquires;
    *index = (uint32_t)next_image;
    fences.push_back({fence, give_at_once ? (shown ? now_ns + delay_ns : kNever) : now_ns});
    out.push_back({sc, next_image, fence, false});
    next_image = (next_image + 1) % kImages;
    return VK_SUCCESS;
}
VkResult vkWaitForFences(int, uint32_t, const VkFence* f, int, uint64_t timeout) {
    if (*f == 13) return VK_SUCCESS;   // (the frame slot's own: done)
    if (!presenter_lk && presenter_busy() && *f != 13) problem("the image's fence looked at on the render thread while the presenter owns it");
    FenceState* s = fence_of(*f);
    if (!s) {
        if (timeout == UINT64_MAX) problem("a wait without end on a fence no acquire was given");
        else now_ns += (int64_t)timeout;
        return VK_TIMEOUT;
    }
    if (s->at <= now_ns) return VK_SUCCESS;
    if (s->at != kNever && (uint64_t)(s->at - now_ns) <= timeout) { now_ns = s->at; return VK_SUCCESS; }
    if (timeout == UINT64_MAX) { problem("a wait without end on an image never given back"); return VK_TIMEOUT; }
    now_ns += (int64_t)timeout;
    return VK_TIMEOUT;
}
VkResult vkResetFences(int, uint32_t, const VkFence* f) {
    if (*f == 13) return VK_SUCCESS;
    for (size_t i = 0; i < fences.size(); i++) {
        if (fences[i].fence != *f) continue;
        if (fences[i].at > now_ns) problem("a fence reset while the presentation engine may still signal it");
        for (Out& o : out) if (o.fence == *f) o.given_back = true;
        fences.erase(fences.begin() + (long)i);
        break;
    }
    return VK_SUCCESS;
}
uint64_t next_fence = 500;
VkResult vkCreateFence(int, const VkFenceCreateInfo*, void*, VkFence* made) { *made = ++next_fence, ++fences_made; return VK_SUCCESS; }
VkResult vkEndCommandBuffer(VkCommandBuffer) { return VK_SUCCESS; }
VkFence present_copy_done = VK_NULL_HANDLE;
bool present_acquire_ahead = false;
void present_finish(VkResult r, bool on_presenter) {   // (the presenter's: out of date or suboptimal asks for a new swapchain)
    if (on_presenter && (r == VK_ERROR_OUT_OF_DATE_KHR || r == VK_SUBOPTIMAL_KHR)) resize_asked = true;
}
VkResult model_present(uint32_t index, VkSwapchainKHR sc) {   // (vkQueuePresentKHR, as the presenter makes it)
    bool found = false;
    for (size_t i = 0; i < out.size(); i++) {
        if (out[i].image != (int)index || out[i].sc != sc) continue;
        found = true;
        out.erase(out.begin() + (long)i);
        break;
    }
    if (!found) problem("a present of an image not acquired from the swapchain as it is");
    if (sc != dev.swapchain) problem("a present on a swapchain made again since its hand-over");
    ++presents, presenter_presented = true;
    const VkResult r = next_present_result;
    next_present_result = VK_SUCCESS;
    return r;
}
// (the presenter: 0 runs right after each hand-over; 1 late, when the render thread waits for it; 2 stuck, never)
int presenter_mode = 0;
void presenter_run();
template<class Idle> bool model_wait(std::unique_lock<std::mutex>& lk, Idle idle) {
    if (!idle() && presenter_mode == 1) {
        lk.unlock();
        presenter_run();
        lk.lock();
    }
    return idle();
}
'''

FIXTURE_TAIL = r'''
bool presenter_busy() { return presenter.busy; }
void presenter_run() {   // (the presenter thread's turn: the present handed over, as presenter_loop takes it, makes it and ends)
    std::unique_lock<std::mutex> lk(presenter.mu);
    if (!presenter.busy) return;
@@LOOP_HEAD@@
    (void)done;
    presenter_presented = false;
    const bool copied = true;
    VkResult res = model_present(index, sc);
    presenter_lk = &lk;
    struct Off { ~Off() { presenter_lk = nullptr; } } off;
@@LOOP_TAIL@@
}
bool present_out(uint32_t index, std::unique_lock<QueueLock>& qk) {   // (present_out's hand-over, present_image's present)
    if (!qk.owns_lock()) problem("the present made without the queue's lock");
    if (!present_copy_done) problem("present_image's present without its copy's fence: not handed to the presenter");
    qk.unlock();
    present_hand_off(index, present_copy_done);
    return true;
}

void present(Frame& f, bool game = true) {
    if (resize_asked) {   // (present_image's swap_resize: the presenter idle first, then the swapchain made again)
        resize_asked = false;
        present_thread_drain();
        remake();
    }
    const uint64_t src = game ? 77 : 0;
    const int log_slot = 0;
    (void)log_slot;
@@ACQUIRE@@
@@SUBMIT@@
    ++submits, copied_into = (int)index;
    if (si.waitSemaphoreInfoCount)
        problem("the copy waits on the GPU, on the replay's queue, for the window's image: whatever holds the image holds the "
                "game's work too, and the GPU hang watch ends the game (#1376)");
    for (const Out& o : out)
        if (o.image == (int)index && o.sc == dev.swapchain && !o.given_back)
            problem("a copy submitted into an image the system has not given back");
    std::unique_lock qk(dev.present_mu);
@@TAIL@@
}

Frame fr;
int64_t step(int64_t work_ns, bool game = true) {   // (a frame's work, then its present: what the present waited)
    now_ns += work_ns;
    const int64_t t0 = now_ns;
    present(fr, game);
    const int64_t w = now_ns - t0;
    if (presenter_mode == 0) presenter_run();
    return w;
}
const std::string* last_log(const char* start) {
    for (size_t i = logs.size(); i-- > 0;) if (logs[i].rfind(start, 0) == 0) return &logs[i];
    return nullptr;
}

int main() {
    {   // (the mode: the driver's default, then the switch over it by device_policy_env's rule, for the values the check sets)
        const char* d = std::getenv("MODEL_DEFAULT_ON");
        dev.policy.acquire_ahead = d && std::strcmp(d, "1") == 0;
        if (const char* e = std::getenv("RX_VK_ACQUIRE_AHEAD"); e && *e)
            dev.policy.acquire_ahead = std::strcmp(e, "0") != 0, dev.policy.by_switch = true;
    }
    const bool on = dev.policy.acquire_ahead, counted = on && dev.policy.by_switch;
    presenter.started = true;   // (the model runs the presenter itself: presenter_run)
    { VkFenceCreateInfo fi{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO}; vkCreateFence(dev.device, &fi, nullptr, &acquire_fence); }
    // 1. the window seen, the image back 3 ms after its acquire, frames of 10 ms: 600 presents
    int64_t waited = 0, waited_later = 0;
    for (int i = 0; i < 600; i++) {
        const int a = acquires, ah = ahead_acquires, p = presents, s = submits;
        const int64_t w = step(10 * kMs);
        waited += w;
        if (i) waited_later += w;
        if (presents != p + 1 || submits != s + 1) { problem("a present with the window seen was not made"); break; }
        if (out.size() > 1) { problem("more than one image out"); break; }
        if (!on && (acquires != a + 1 || ahead_acquires != ah))
            { problem("off: not one acquire in the present, before its copy (#1458's order)"); break; }
        if (on && ahead_acquires != ah + 1)
            { problem("on: the next image was not asked for on the presenter right after its present"); break; }
        if (on && i && acquires != a + 1) { problem("on: an acquire in the present though one was made ahead"); break; }
    }
    if (!on && waited != 600 * delay_ns) problem("off: the presents did not wait for the image as before (#1458)");
    if (on && waited_later) problem("on: a present waited for an image asked for a present ahead and given back meanwhile");
    {
        const std::string* l = last_log("vk: the window's image (600 presents): waited for ");
        double ms = -1;
        if (!counted && l)
            problem("a counter line for the window's image without RX_VK_ACQUIRE_AHEAD set to on (a player's log gets none)");
        else if (counted && (!l || std::sscanf(l->c_str(), "vk: the window's image (600 presents): waited for %lf", &ms) != 1))
            problem("RX_VK_ACQUIRE_AHEAD=1: no counter line for the window's image after 600 presents");
        else if (counted && (ms > 0.01 || l->find("asked for a present ahead") == std::string::npos ||
                             l->find(" 0 waited for there") == std::string::npos))
            problem("RX_VK_ACQUIRE_AHEAD=1: the counter line does not say the images were asked for ahead and found free");
    }
    {   // (the first present's line: which way it went, and why; once)
        int said = 0;
        const std::string* first = nullptr;
        for (const std::string& l : logs)
            if ((l.rfind("vk: acquire ahead: on", 0) == 0 || l.rfind("vk: acquire ahead: off", 0) == 0) && !said++) first = &l;
        const char* want = dev.policy.by_switch ? (on ? "vk: acquire ahead: on: " : "vk: acquire ahead: off: ")
                           : on ? "vk: acquire ahead: on by default:"
                                : "vk: acquire ahead: off by default with this driver";
        if (said != 1) problem("the first present's line on which way acquire ahead went is not said once");
        else if (first->rfind(want, 0) != 0) problem("the first present's line does not say which way it went, and why");
        else if (dev.policy.by_switch && first->find("set by RX_VK_ACQUIRE_AHEAD") == std::string::npos)
            problem("the first present's line does not say RX_VK_ACQUIRE_AHEAD set it");
    }
    // 2. the image back 20 ms after its acquire, frames of 10 ms: none dropped
    delay_ns = 20 * kMs;
    for (int i = 0; i < 6; i++) {
        const int p = presents;
        const int64_t w = step(10 * kMs);
        if (presents != p + 1) { problem("an image given back late (in kImageFreeNs) was not waited for: its frame dropped"); break; }
        if (!on && w != 20 * kMs) { problem("off: the late image's wait is not as before"); break; }
        if (on && i && w > 10 * kMs) { problem("on: the late image was waited for longer than it needed"); break; }
    }
    delay_ns = 3 * kMs;
    step(10 * kMs);
    // 3. #1458's own case: the window hidden, nothing given back
    hide();
    {
        const int s = submits;
        // (on: the image asked for after the last present, never given back; waited for 250 ms, no more, then held)
        if (step(10 * kMs) != 250 * kMs)
            problem("the first present with the window hidden did not wait the image's 250 ms (kImageFreeNs) and then go on");
        if (submits != s) problem("a copy submitted into an image the system has not given back");
        const int a = acquires;
        for (int i = 0; i < 5; i++)
            if (step(10 * kMs)) { problem("a held image waited for again at a later present"); break; }
        if (acquires != a) problem("another image acquired while one is held");
        if (submits != s) problem("a held image copied into before it was given back");
        shown = true;
        engine_lets_go();
        const int ah0 = ahead_acquires;
        step(10 * kMs);
        if (submits != s + 1 || acquires - ahead_acquires != a - ah0)   // (an ahead acquire after its present: allowed)
            problem("the held image was not the next one copied into once given back");
        step(10 * kMs);
        if (submits != s + 2) problem("the present after the held image did not go on");
    }
    // 4. the swapchain made again with an image asked for ahead (a resize at the next present), and a present that came back
    //    suboptimal: no image asked for ahead of the swapchain it asks to make again
    step(10 * kMs);
    {
        remake();
        const int s = submits;
        step(10 * kMs);
        if (submits != s + 1) problem("no copy after the swapchain was made again with an image out");
        step(10 * kMs);
        if (submits != s + 2) problem("the second present on the new swapchain did not copy");
        const int ah = ahead_acquires;
        next_present_result = VK_SUBOPTIMAL_KHR;
        step(10 * kMs);
        if (ahead_acquires != ah) problem("an image asked for ahead after a present that came back suboptimal");
        const int s2 = submits;
        step(10 * kMs);
        step(10 * kMs);
        if (submits != s2 + 2) problem("no copies after a suboptimal present asked for the swapchain to be made again");
    }
    // 5. fences let go: a swapchain made again while the ahead image's fence is pending lets the fence go; one let go is used
    //    again only once it is signaled, and then before a new one is made
    if (on) {
        step(10 * kMs);
        remake();   // (A: its images never given back, the ahead image's fence never signaled)
        const int made = fences_made;
        step(10 * kMs);
        if (fences_made != made + 1) problem("a swapchain made again with the image's fence pending: no new fence for the next acquire");
        remake_kills = false, delay_ns = 20 * kMs;
        step(10 * kMs);   // (its ahead image's fence signaled 20 ms after its acquire)
        resize_asked = true;
        const int made_b = fences_made;
        step(1 * kMs);    // (B: made again with that fence pending, the one let go at A never signaled: neither used, one made)
        if (fences_made != made_b + 1) problem("fences let go and not signaled since: no new fence made");
        delay_ns = 3 * kMs;
        step(25 * kMs);   // (B's fence signaled meanwhile)
        resize_asked = true;
        const int made_c = fences_made;
        step(1 * kMs);    // (C: made again with the next fence pending: B's, signaled, used again)
        if (fences_made != made_c) problem("a fence let go and signaled since was not used again: a new one made (it leaks)");
        remake_kills = true;
        for (int i = 0; i < 3; i++) step(10 * kMs);
    } else {   // (off, #1376's case: an image held while the window is hidden, its swapchain made again; the same fences)
        remake_kills = false;
        hide();
        step(10 * kMs);   // (the image held: its fence never signaled while hidden)
        resize_asked = true;
        const int made = fences_made;
        step(10 * kMs);   // (D: made again, the held image's fence let go pending, a new one made; that one held in turn)
        if (fences_made != made + 1) problem("a swapchain made again with a held image's fence pending: no new fence");
        shown = true;
        engine_lets_go();
        step(10 * kMs);
        step(10 * kMs);
        hide();
        step(10 * kMs);
        resize_asked = true;
        const int made_e = fences_made;
        step(10 * kMs);   // (E: made again with a held image again: D's fence, signaled since, used again)
        if (fences_made != made_e) problem("a fence let go and signaled since was not used again: a new one made (it leaks)");
        shown = true;
        engine_lets_go();
        remake_kills = true;
        for (int i = 0; i < 3; i++) step(10 * kMs);
    }
    // 6. the presenter late: it runs when the render thread waits for it (its drain before the acquire)
    {
        presenter_mode = 1;
        const int p = presents, s = submits;
        for (int i = 0; i < 20; i++) step(10 * kMs);
        presenter_mode = 0;
        presenter_run();
        if (presents != p + 20 || submits != s + 20) problem("the presenter late: a present not made");
        step(10 * kMs);
    }
    // 7. the presenter stuck past a drain's limit: the drain gives up, and no image is asked for ahead after it
    {
        presenter_mode = 2;
        now_ns += 10 * kMs;
        present(fr);
        const int ah = ahead_acquires;
        present_thread_drain();   // (gives up: the presenter still holds its present)
        presenter_mode = 0;
        presenter_run();          // (its present made at last)
        if (ahead_acquires != ah) problem("an image asked for ahead after the drain gave up on the presenter's present");
        const int s = submits;
        step(10 * kMs);
        step(10 * kMs);
        if (submits != s + 2) problem("no copies after a drain gave up on the presenter");
    }
    // 8. no ahead acquire with frame generation, FIFO, or at the start-up screen's presents
    for (int gate = 0; gate < 3; gate++) {
        step(10 * kMs);
        fg_on = gate == 0;
        if (gate == 1) dev.swap_mode = VK_PRESENT_MODE_FIFO_KHR;
        const int ah = ahead_acquires, s = submits;
        for (int i = 0; i < 4; i++) step(10 * kMs, gate != 2);
        if (ahead_acquires != ah) {
            const char* what[] = {"frame generation", "FIFO", "the start-up screen's presents"};
            char b[160];
            std::snprintf(b, sizeof b, "an image asked for ahead with %s", what[gate]);
            problem(b);
        }
        if (submits != s + 4) problem("a present not made while the ahead acquire is off");
        fg_on = false, dev.swap_mode = VK_PRESENT_MODE_MAILBOX_KHR;
    }
    // 9. NVIDIA-like: the wait in the acquire; none given at a timeout of 0
    step(10 * kMs);
    give_at_once = false;
    {
        const int s = submits;
        for (int i = 0; i < 6; i++) step(10 * kMs);
        if (ahead_waited) problem("the ahead acquire waited for an image");
        if (submits != s + 6) problem("with none given at once, a present was not made");
    }
    give_at_once = true;
    // 10. a lost device at the ahead acquire: reported
    step(10 * kMs);
    if (on) {
        lose_at_ahead = true;
        bool thrown = false;
        try { step(10 * kMs); } catch (const Lost&) { thrown = true; }
        if (!thrown || lost_reports != 1) problem("a lost device at the ahead acquire was not reported");
        lose_at_ahead = false;
        presenter.busy = false;   // (the process ends there; the model goes on)
        if (dev.presenter_queue_mu.held) problem("the swapchain's lock left held past the ahead acquire");
        dev.presenter_queue_mu.held = false;
    }
    // 11. the swapchain out of date at the ahead acquire (off: at the present's own acquire): no image taken from that answer,
    //     the fence left as it was, the next present makes the swapchain again, and the presents after it copy
    step(10 * kMs);
    step(10 * kMs);
    {
        out_of_date = true;
        const int s = submits, ah = ahead_acquires;
        const uint64_t gen = dev.swapchain_generation;
        step(10 * kMs);   // (on: the image asked for after the present before is copied; its own ahead acquire is answered out of date)
        if (on && (submits != s + 1 || ahead_out_of_date != 1 || ahead_acquires != ah || !out.empty()))
            problem("an out-of-date answer to the ahead acquire: an image taken from it, or the present before it not made");
        if (!on && (submits != s || dev.swapchain_generation == gen))
            problem("off: an out-of-date answer at the present did not make the swapchain again");
        if (on) {
            step(10 * kMs);   // (the present's own acquire meets it: the swapchain made again, nothing copied)
            if (submits != s + 1 || dev.swapchain_generation == gen)
                problem("after an out-of-date answer to the ahead acquire, the next present did not make the swapchain again");
        }
        const int s2 = submits;
        step(10 * kMs);
        step(10 * kMs);
        if (submits != s2 + 2) problem("no copies after the out-of-date swapchain was made again");
    }
    if (problems) return 1;
    std::printf("PASS (%s, %s): %s%s; late, hidden and given back, swapchain made again, fences let go, presenter late and stuck, "
                "gates, NVIDIA-like, device lost, out of date\n", PLATFORM, MODE,
                on ? "the next image asked for on the presenter after each present and found free" : "#1458's order kept",
                counted ? ", the counter line" : "");
    return 0;
}
'''

BROKEN = [
    ("the ahead acquire made on the render thread at the hand-over, before the present",
     "    present_out(index, qk);\n    present_copy_done = VK_NULL_HANDLE;\n    present_acquire_ahead = false;",
     "    acquire_ahead(dev.swapchain, dev.swapchain_generation);\n    present_out(index, qk);\n    present_copy_done = VK_NULL_HANDLE;\n"
     "    present_acquire_ahead = false;"),
    ("the hand-over not passing acquire ahead to the presenter",
     "presenter.ahead = present_acquire_ahead;",
     "presenter.ahead = false;"),
    ("the presenter's ahead acquire without presenter.mu held",
     "        if (copied) present_finish(res, true);\n        lk.lock();",
     "        if (copied) present_finish(res, true);\n        if (presenter.ahead && res == VK_SUCCESS) acquire_ahead(sc, generation);\n"
     "        lk.lock();"),
    ("the ahead acquire without the swapchain's lock",
     "        std::lock_guard pq(dev.presenter_queue_mu);\n        res = vkAcquireNextImageKHR(dev.device, sc, 0,",
     "        res = vkAcquireNextImageKHR(dev.device, sc, 0,"),
    ("the ahead acquire after a present that came back suboptimal",
     "if (presenter.ahead && res == VK_SUCCESS) acquire_ahead(sc, generation);",
     "if (presenter.ahead) acquire_ahead(sc, generation);"),
    ("a drain that gave up leaves the ahead acquire on",
     "        presenter.ahead = false;   // (acquire ahead: none after a present the caller goes on without)",
     "        // (the ahead acquire left on)"),
    ("present_image's drain of the presenter before its acquire removed",
     "    present_thread_drain();\n    const int64_t fence_t0 = fps_breakdown_on()",
     "    const int64_t fence_t0 = fps_breakdown_on()"),
    ("the wait at the present removed",
     "else image_waits.ahead_waited++, ready = image_free(kImageFreeNs);",
     "else image_waits.ahead_waited++;"),
    ("the drop at a new swapchain removed",
     "    if (held_image.held && held_image.generation != dev.swapchain_generation) held_image_drop();",
     "    if (false) held_image_drop();"),
    ("a fence let go reused without its being signaled",
     "        if (r != VK_SUCCESS) continue;   // (not signaled yet; a lost device: the next wait that meets it says so)",
     "        (void)r;"),
    ("fences let go never used again",
     "    if (fences_let_go.size() < 8) fences_let_go.push_back(acquire_fence);",
     "    (void)fences_let_go;"),
    ("the FIFO gate removed",
     "dev.swap_mode != VK_PRESENT_MODE_IMMEDIATE_KHR && dev.swap_mode != VK_PRESENT_MODE_MAILBOX_KHR ? 2 : 0",
     "false ? 2 : 0"),
    ("the frame generation gate removed",
     "const int why = framegen_on() ? 1",
     "const int why = false ? 1"),
    ("the ahead acquire with a timeout",
     "res = vkAcquireNextImageKHR(dev.device, sc, 0, VK_NULL_HANDLE, acquire_fence, &index);",
     "res = vkAcquireNextImageKHR(dev.device, sc, 1000000000ull, VK_NULL_HANDLE, acquire_fence, &index);"),
    ("an out-of-date answer to the ahead acquire taken as an image",
     "    if (res != VK_SUCCESS && res != VK_SUBOPTIMAL_KHR) {   // (no image: the fence untouched, the next present acquires)",
     "    if (res == VK_NOT_READY || res == VK_TIMEOUT) {   // (no image: the fence untouched, the next present acquires)"),
    ("the present's wait for a hidden window's image not bounded at 250 ms (30 s)",
     "constexpr uint64_t kImageFreeNs = 250000000ull;",
     "constexpr uint64_t kImageFreeNs = 30000000000ull;"),
    # (Hookshot: no device_policy.h; the default is on wherever the presenter thread runs, RX_VK_ACQUIRE_AHEAD over it)
    ("the default ignored: off with nothing set (unset)",
     "    const bool v = acquire_ahead_set() ? strcmp(getenv(\"RX_VK_ACQUIRE_AHEAD\"), \"0\") != 0 : true;",
     "    const bool v = acquire_ahead_set() ? strcmp(getenv(\"RX_VK_ACQUIRE_AHEAD\"), \"0\") != 0 : false;",
     ((True, None),)),
    ("the switch ignored: on with =0",
     "    const bool v = acquire_ahead_set() ? strcmp(getenv(\"RX_VK_ACQUIRE_AHEAD\"), \"0\") != 0 : true;",
     "    const bool v = true;",
     ((True, "0"),)),
    ("the image-wait counter with the switch off (=0)",
     "const bool image_count = acquire_ahead_counted();",
     "const bool image_count = true;",
     ((True, "0"),)),
    ("the image-wait counter by the default too, not only with =1 (unset)",
     "acquire_ahead_on() && acquire_ahead_set();",
     "acquire_ahead_on();",
     ((True, None),)),
    ("the first present's line not saying the default went on (unset)",
     '"vk: acquire ahead: on by default: the next image asked for right after each present "',
     '"vk: acquire ahead: on: the next image asked for right after each present "',
     ((True, None),)),
]


def no_tracy(text):
    """The text without its `#ifdef TRACY_ENABLE` ... `#endif` blocks (the profiler's scopes)"""
    return re.sub(r"\n[ \t]*#ifdef TRACY_ENABLE\n.*?\n[ \t]*#endif[^\n]*", "", "\n" + text, flags=re.S)[1:]


def cut(text, start, end, what):
    if text.count(start) != 1:
        raise SystemExit("FAIL: %s: its start %r found %d times, not once (the source changed?)" % (what, start, text.count(start)))
    return between(text, start, end)


def fixture(replay, windows, mode):
    present = block(replay, "void present_image(VkImage src,")
    acquire = cut(present, "    // (the presenter thread, RX_VK_PRESENT_THREAD: the present handed over",
                  "    if (vkResetCommandPool(dev.device, f.pool, 0)",
                  "present_image's drain and acquire")
    submit = cut(present, "    if (vkEndCommandBuffer(f.cmd) == VK_ERROR_DEVICE_LOST) device_lost();",
                 "    std::unique_lock qk(dev.present_mu);", "present_image's copy's submit")
    start = "    present_acquire_ahead = src" if "    present_acquire_ahead = src" in present else "    present_copy_done = f.done;"
    tail = cut(present, start, "\n}", "present_image's hand-over (from %r)" % start)   # (main's: no acquire ahead)
    helpers = cut(replay, "static VkFence acquire_fence = VK_NULL_HANDLE;", "void present_image(VkImage src,", "the image's helpers")
    marker = "static bool acquire_ahead_wanted() {"   # (main has none: its presents then fail the checks)
    ahead = between(replay, marker, "bool present_commit(const PendingPresent& p) {") if marker in replay else ""
    state = cut(replay, "struct Presenter {", "/// The copy's fence, in 100 ms steps", "the presenter's state")
    idle = block(replay, "bool presenter_wait_idle(std::unique_lock<std::mutex>& lk, int limit_ms = 0) {")
    idle = (idle.replace("presenter.cv.wait_for(lk, std::chrono::milliseconds(limit_ms), idle)", "model_wait(lk, idle)")
                .replace("presenter.cv.wait(lk, idle);", "if (!model_wait(lk, idle)) problem(\"a hand-over waits without end\");"))
    hand = block(replay, "void present_hand_off(uint32_t index, VkFence done) {")
    hand = hand.replace("std::thread(presenter_loop).detach();", "")
    drain = block(replay, "void present_thread_drain() {")
    loop = block(replay, "void presenter_loop() {")
    head = cut(loop, "        const uint32_t index = presenter.index;", "        lk.unlock();", "presenter_loop's take of a hand-over")
    end = cut(loop, "        if (copied) present_finish(res, true);", "    }\n}", "presenter_loop's end of a present")
    body = (FIXTURE_TAIL.replace("@@LOOP_HEAD@@", head + "        lk.unlock();\n").replace("@@LOOP_TAIL@@", end)
            .replace("@@ACQUIRE@@", platform_side(acquire, windows)).replace("@@SUBMIT@@", platform_side(submit, windows))
            .replace("@@TAIL@@", platform_side(tail, windows)))
    presenter = "\n".join(no_tracy(t) for t in (state, idle, hand, drain))
    return ('#define PLATFORM "%s"\n#define MODE "%s"\n' % ("Windows" if windows else "Linux", mode)
            + FIXTURE_HEAD + platform_side(helpers, windows)
            + "static void acquire_ahead(VkSwapchainKHR sc, uint64_t generation);\n"
            + platform_side(ahead, windows) + presenter + "\n" + body)


# (the policy's default: off, which no driver has now; on, every driver's), and RX_VK_ACQUIRE_AHEAD over it (None: unset)
MODES = [(True, None), (True, "0"), (True, "1")]   # (Hookshot: on by default, no PC where the default is off)


def build_and_run(cxx, replay, windows, temp, name, modes, quiet=False):
    """Compiles the fixture and runs it in each of modes (the driver's default, RX_VK_ACQUIRE_AHEAD): whether every run passed
    (None: the fixture did not compile, said)"""
    cpp, exe = Path(temp) / (name + ".cpp"), Path(temp) / (name + ".exe")
    ok = True
    for default_on, value in modes:
        src = fixture(replay, windows, "default %s, RX_VK_ACQUIRE_AHEAD=%s" % ("on" if default_on else "off",
                                                                            value if value is not None else "unset"))
        cpp.write_text(src, encoding="utf-8")
        c = subprocess.run([cxx, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-variable",
                            "-Wno-unused-parameter", "-Wno-unused-function", "-Wno-missing-field-initializers", str(cpp), "-o",
                            str(exe)], capture_output=quiet, text=True)
        if c.returncode:
            print("FAIL (%s): the fixture does not compile" % name)
            return None
        env = dict(os.environ)
        env.pop("RX_VK_ACQUIRE_AHEAD", None)
        env["MODEL_DEFAULT_ON"] = "1" if default_on else "0"
        if value is not None:
            env["RX_VK_ACQUIRE_AHEAD"] = value
        r = subprocess.run([str(exe)], env=env, timeout=60, capture_output=quiet, text=True)
        ok &= r.returncode == 0
    return ok


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=ROOT)
    p.add_argument("--cxx", default="clang++")
    a = p.parse_args()
    replay = (a.source / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    failed = False
    with tempfile.TemporaryDirectory(prefix="present-acquire-ahead-") as temp:
        for windows in (True, False):
            failed |= not build_and_run(a.cxx, replay, windows, temp, "Windows" if windows else "Linux", MODES)
        for what, old, new, *modes in BROKEN:
            if replay.count(old) != 1:
                print("FAIL: the broken variant '%s' finds its place %d times, not once (the source changed?)" % (what, replay.count(old)))
                failed = True
                continue
            ran = build_and_run(a.cxx, replay.replace(old, new), True, temp, "broken", modes[0] if modes else ((False, "1"),),
                                quiet=True)
            if ran is None or ran:   # (a variant that does not compile proves nothing either)
                print("FAIL: the broken variant '%s' %s" % (what, "does not compile" if ran is None else
                                                            "passes: the check does not see it"))
                failed = True
            else:
                print("ok: the broken variant '%s' fails" % what)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()

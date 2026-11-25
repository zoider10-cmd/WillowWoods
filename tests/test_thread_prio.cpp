// thread_prio.h (RX_VK_THREAD_PRIO, HeyListen c81f500c): the processors a background compile thread may use, the pin hook, the
// mark it leaves for the workers it starts, the start line. tests/test_thread_prio.py runs it at RX_VK_THREAD_PRIO=0 and 1
// (argv[1] is the mode expected).
#include "thread_prio.h"

#include <cstdio>
#include <thread>

using namespace mkwvk;

static int failures = 0;
static int pins = 0;
static void expect(bool ok, const char* what) {
    if (!ok) std::printf("FAIL: %s\n", what), failures++;
}

int main(int argc, char** argv) {
    const int m = argc > 1 ? std::atoi(argv[1]) : 1;
    expect(prio::mode() == m, "mode() reads RX_VK_THREAD_PRIO");
    expect(prio::compile_mask(0xFFF, 0xC00) == 0x3FF, "compile threads leave the replay's core out");
    expect(prio::compile_mask(0xC00, 0xC00) == 0xC00, "all of them when that leaves none");
    expect(prio::compile_mask(0xFF, 0) == 0xFF, "no core kept: all of them");
    prio::pin_background();
    expect(pins == 0 && !prio::pinned_here(), "no hook (no core kept): nothing happens, nothing marked");
    prio::hooks().pin_compile = [] { pins++; };
    prio::hooks().pinned_off = 0xC00;
    bool other = true;
    std::thread([&] { other = prio::pinned_here(); }).join();
    expect(!other, "another thread is not marked before it pins itself");
    prio::pin_background();
    expect(pins == (m ? 1 : 0), m ? "on: a background compile thread is pinned" : "off: no pin");
    expect(prio::pinned_here() == (m != 0), m ? "and marked, for the workers it starts" : "and not marked");
    std::thread([&] { other = prio::pinned_here(); }).join();
    expect(!other, "the mark is the thread's own");
    const std::string d = prio::describe();
    expect(d.find("RX_VK_THREAD_PRIO") != std::string::npos, "the start line names the switch");
    expect(m == 0 || d.find("0xc00") != std::string::npos, "the start line says which processors are kept free");
    if (!failures) std::printf("ok\n");
    return failures != 0;
}

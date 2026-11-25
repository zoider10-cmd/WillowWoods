# Copyright (C) 2026 Sacrappy

"""(HeyListen 51e533a8) RX_VK_WAIT_OWN (gpu/vk/wait_own.h, v0.4.4): how far behind the GPU the replay lets the game run at each present on an AMD
integrated GPU. Compiled with a small program: the mode by the switch, RX_VK_WAIT_GPU and the GPU's kind (1, the frame's own work, by default on an AMD integrated GPU; 3 the frame before's and the frame's own after a texture upload; 2 the frame before's; 0 none), and the value each present waits for. And, by the
text, that the present waits for that value only (and not for its own on mode 2).

python -I -B tests/test_wait_own.py --cxx <compiler>
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]

CPP = r'''
#include "wait_own.h"
#include <cstdio>
static int fails;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL line %d: %s\n", __LINE__, #c); fails++; } } while (0)
int main() {
    using namespace wait_own;
    CHECK(mode(nullptr, false, true) == 1);    // (an AMD integrated GPU: its own frame's, the only value with a whole HUD on a 5700U)
    CHECK(mode(nullptr, false, false) == 0);   // (any other GPU: none)
    CHECK(mode(nullptr, true, true) == 0);     // (RX_VK_WAIT_GPU set: the ring is the user's choice)
    CHECK(mode("1", false, false) == 1 && mode("1", true, true) == 1 && mode("0", false, true) == 0);
    CHECK(mode("2", false, false) == 2 && mode("3", false, false) == 3 && mode("7", false, false) == 1 && mode("", false, true) == 0);
    uint64_t prev = 0;
    CHECK(target(2, 10, prev) == 0 && prev == 10);   // (the first present: nothing before it)
    CHECK(target(2, 11, prev) == 10 && prev == 11);
    CHECK(target(2, 12, prev) == 11);
    prev = 0;
    CHECK(target(2, 10, prev, true) == 0 && target(2, 11, prev, true) == 10);   // (2 does not look at uploads)
    prev = 0;
    CHECK(target(3, 10, prev, false) == 0 && target(3, 11, prev, false) == 10 && target(3, 12, prev, false) == 11);
    CHECK(target(3, 13, prev, true) == 13 && prev == 13);   // (a frame that uploaded: its own)
    CHECK(target(3, 14, prev, false) == 13);
    prev = 0;
    CHECK(target(1, 20, prev) == 20 && target(1, 21, prev) == 21);
    prev = 0;
    CHECK(target(0, 30, prev) == 0 && prev == 30);
    if (!fails) std::printf("PASS the modes\n");
    return fails;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="g++")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        cpp, exe = Path(tmp) / "t.cpp", Path(tmp) / "t.exe"
        cpp.write_text(CPP)
        subprocess.run([args.cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT / "gpu/vk"), str(cpp), "-o", str(exe)],
                       check=True)
        subprocess.run([str(exe)], check=True)
    rp = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    at = rp.index('wait_own::mode(getenv("RX_VK_WAIT_OWN")')
    block = rp[at:at + 1800]
    assert "VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU" in block and "0x1002" in block, "the default is no longer an AMD integrated GPU's"
    # (here: on Windows only, the hardware it was measured on; the Steam Deck keeps today's no wait)
    head = rp[rp.rindex("static const int own = [] {", 0, at):at + 400]
    assert "windows && dev.props.vendorID == 0x1002" in head, "the default is not kept to Windows"
    assert "wait_own::target(own, value, own_prev, uploaded)" in block and "texture_stats(&uploads, &astc, &bytes)" in block and "if (t) wait_value(t);" in block, "the present does not wait for the target"
    assert "if (own) wait_value(value);" not in rp, "the present still waits for its own frame in every mode"
    print("PASS the wiring")


if __name__ == "__main__":
    main()

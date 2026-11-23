"""Capture spares (Triforce cap_spare.h, taken 2026-11-22): a capture takes the smallest spare that fits, leaves a load's
big spare to a load, a big spare taken is made again, and buffers are made and destroyed with cap_free_mu let go.

The rules header is compiled and asked; vk_memory.cpp's use of it is checked by source. RX_VK_CAP_SPARE_FIT=0: as before.

python -I -B tests/test_cap_spare.py [--cxx clang++]
"""
import argparse
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = r'''
#include "cap_spare.h"
#include <cstdio>
#include <vector>
#define CHECK(w, c) do { if (!(c)) { std::printf("FAIL: %s\n", w); return 1; } } while (0)
int main() {
    using namespace cap_spare;
    std::vector<uint64_t> sp = {192 * kMB, 32 * kMB, 8 * kMB};
    auto at = [&](size_t i) { return sp[i]; };
    CHECK("a 2 MB capture takes the 8 MB spare, not a big one", pick(sp.size(), at, 2 * kMB, 2 * kMB, false) == 2);
    sp = {192 * kMB, 64 * kMB};
    CHECK("a 2 MB capture leaves the load's big spares alone", pick(sp.size(), at, 2 * kMB, 2 * kMB, false) == sp.size());
    CHECK("a 40 MB capture (64 MB class) takes the 64 MB spare", pick(sp.size(), at, 40 * kMB, 64 * kMB, false) == 1);
    CHECK("a 130 MB capture (192 MB class) takes the 192 MB spare", pick(sp.size(), at, 130 * kMB, 192 * kMB, false) == 0);
    CHECK("any size: the smallest that fits, as before", pick(sp.size(), at, 2 * kMB, 2 * kMB, true) == 1);
    CHECK("none fits", pick(sp.size(), at, 300 * kMB, 256 * kMB, false) == sp.size());
    std::puts("ok");
    return 0;
}
'''


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cxx", default="clang++")
    a = p.parse_args()
    failed = False
    with tempfile.TemporaryDirectory() as t:
        src, exe = pathlib.Path(t) / "f.cpp", pathlib.Path(t) / "f.exe"
        src.write_text(FIXTURE, encoding="utf-8")
        c = subprocess.run([a.cxx, "-std=c++20", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "gpu" / "vk"), str(src), "-o", str(exe)])
        if c.returncode or subprocess.run([str(exe)]).returncode:
            failed = True
    mem = (ROOT / "gpu" / "vk" / "vk_memory.cpp").read_text(encoding="utf-8")
    get = mem[mem.index("bool cap_buf_get("):]
    get = get[:get.index("\n}\n")]
    free = mem[mem.index("void cap_buf_free("):]
    free = free[:free.index("\n}\n")]
    for ok, what in (("cap_spare::pick(" in get, "cap_buf_get does not ask cap_spare::pick"),
                     ("cap_prewarm_class(size);" in get, "a big spare taken is not made again"),
                     ("lk.unlock();" in get and "std::unique_lock lk(cap_free_mu);" in get, "a new buffer is made with the lock held"),
                     ("if (!keep && cap_spare_fit()) destroy_buffer(buffer, alloc);" in free, "a buffer past the limits is destroyed with the lock held"),
                     ('getenv("RX_VK_CAP_SPARE_FIT")' in mem and "SW(RX_VK_CAP_SPARE_FIT," in
                      (ROOT / "gpu" / "vk" / "switches.def").read_text(encoding="utf-8"), "no RX_VK_CAP_SPARE_FIT, or no row for it")):
        if not ok:
            print("FAIL: " + what)
            failed = True
    print("FAIL" if failed else "PASS: capture spares taken by fit, made again, made and destroyed off the lock")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

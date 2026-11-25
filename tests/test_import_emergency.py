"""(HeyListen bc74bce9 part, b2b74712) A refused import gives idle retired imports back and is tried again
(RX_VK_IMPORT_EMERGENCY, RX_VK_IMPORT_REFUSE_MB; gpu/vk/vk_memory.cpp; no game, no GPU).

HeyListen's issue 131 (an RX 9060 XT after 4 h): the driver refused every import (VK_ERROR_INVALID_EXTERNAL_HANDLE) and draws
were left out. Our GRACE rule already bounds retired imports over time; this adds the moment of refusal. Read from the source:
- pool_lookup retries a refused import only for the driver's limit codes, after retired_emergency_free freed something, and
  forgets the range's failure hold first (else import_pool would refuse it again at once);
- retired_emergency_free takes only idle retired pools (no mirror, no inherit pending, the GPU past them), oldest first, stops
  once need + 256 MB is free, and does nothing with RX_VK_IMPORT_EMERGENCY=0 or retired imports kept (Mode::KEEP);
- the test hook refuses before any driver call and counts what is imported: every free of a host-pointer import subtracts it;
- import_hold.h's forget removes only the exact range (its rule compiled and run).

    python -I -B tests/test_import_emergency.py [--cxx g++]
"""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block  # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r"""
#include <cstdio>
#include "import_hold.h"
int main() {
    mkwvk::ImportHolds h;
    h.deny_for(0x1000, 0x2000, 0);
    h.deny_for(0x3000, 0x4000, 0);
    if (h.allow(0x1000, 0x2000, 1) || h.allow(0x3000, 0x4000, 1)) return 1;
    h.forget(0x1000, 0x2000);
    if (!h.allow(0x1000, 0x2000, 1)) return 2;   // (forgotten: tried again at once)
    if (h.allow(0x3000, 0x4000, 1)) return 3;    // (another range keeps its hold)
    h.forget(0x3000, 0x3800);                    // (not the exact range: nothing)
    if (h.allow(0x3000, 0x4000, 1)) return 4;
    std::printf("import holds: forget ok\n");
    return 0;
}
"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    mem = (ROOT / "gpu/vk/vk_memory.cpp").read_text(encoding="utf-8")
    fails = []

    def check(ok, why):
        if not ok:
            fails.append(why)

    look = block(mem, "Pool* pool_lookup(uint64_t guest, uint64_t size) {")
    retry = look[look.find("ok = import_pool(lo, hi, p);"):]
    retry = retry[:retry.find("const double ms")]
    for code in ("VK_ERROR_INVALID_EXTERNAL_HANDLE", "VK_ERROR_OUT_OF_HOST_MEMORY", "VK_ERROR_OUT_OF_DEVICE_MEMORY"):
        check(code in retry, "a refused import is not retried for " + code)
    check(retry.find("retired_emergency_free(hi - lo)") < retry.find("import_forget_failure(lo, hi);") <
          retry.rfind("ok = import_pool(lo, hi, p);"), "the retry does not free, forget the hold, then import again, in that order")

    em = block(mem, "uint64_t retired_emergency_free(uint64_t need) {")
    check('getenv("RX_VK_IMPORT_EMERGENCY")' in em and "retired_give_back::Mode::KEEP" in em,
          "the give-back runs with RX_VK_IMPORT_EMERGENCY=0 or retired imports kept")
    for idle in ("p.inherit_pending", "p.retired_value > mem_completed", "p.last_value > mem_completed", "Pool::MIRROR_NONE"):
        check(idle in em, "a retired pool is given back without checking " + idle)
    check("if (freed >= need + (256ull << 20)) break;" in em, "the give-back does not stop once enough is free")
    check("pools_gen++;" in em, "the pools' generation is not bumped for a pool given back (cached lookups would keep it)")

    imp = block(mem, "bool import_pool(uint64_t lo, uint64_t hi, Pool& p) {")
    check(imp.find('getenv("RX_VK_IMPORT_REFUSE_MB")') < imp.find("vkCreateBuffer("), "the test hook refuses after a driver call")
    check("st_pinned.fetch_add((int64_t)bytes" in imp, "a made import is not counted")
    # (every host-pointer import freed: vkFreeMemory of a pool's or a dead import's memory beside pinned_sub)
    frees = [m.start() for m in re.finditer(r"vkFreeMemory\(dev\.device, (p|m|dead_imports\.front\(\))\.memory, nullptr\);", mem)]
    for at in frees:
        near = mem[at:at + 200]
        line = mem.count("\n", 0, at) + 1
        check("pinned_sub(" in near or "allocated == VK_SUCCESS" in mem[at - 80:at],
              f"vk_memory.cpp:{line}: an import's memory freed without pinned_sub")
    check(len(frees) >= 6, "fewer import frees found than there are (%d)" % len(frees))

    cxx = shutil.which(a.cxx) or a.cxx
    with tempfile.TemporaryDirectory(prefix="import-holds-") as tmp:
        c, exe = Path(tmp) / "holds.cpp", Path(tmp) / "holds.exe"
        c.write_text(FIXTURE, encoding="utf-8")
        subprocess.run([cxx, "-std=c++20", "-O1", "-I", str(ROOT / "gpu/vk"), str(c), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        print(r.stdout, end="")
        check(r.returncode == 0, "ImportHolds::forget is wrong (%d)" % r.returncode)
    if fails:
        for f in fails:
            print("FAIL: " + f)
        raise SystemExit(1)
    print("PASS: a refused import gives idle retired imports back and is tried again")


if __name__ == "__main__":
    main()

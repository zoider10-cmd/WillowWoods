"""(HeyListen 2b141867 + e65826e3) Chunks of the game's ended pools are retired by a sweep (RX_VK_ACCUM_RETIRE;
gpu/vk/vk_memory.cpp; no game, no GPU).

A chunk (an import around a binding, with its VRAM mirror) left the pool table only when a larger import took it in, so every
zone visited left its chunks imported for good. Every 1200 submissions the chunks with no live game pool in them and unbound
for RX_VK_ACCUM_IDLE recordings are retired. Checked:
- LivePoolIndex.reaches, cut out of the source and run over overlapping and nested pools against a plain walk;
- the sweep does nothing without a list of the game's pools (every chunk would look ended), never takes a chunk a live pool
  reaches, one the GPU may still use or one imported ahead and not bound, retires through retire_pool, and drops the
  inheritance; it runs at a submission's start under pools_mu, before the retired imports' give-back.

    python -I -B tests/test_accum_retire.py [--cxx g++]
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block  # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]

FIXTURE = r"""
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>
struct GuestPool { uint64_t lo, hi; };
static std::vector<GuestPool> guest_pools;
@INDEX@;
int main() {
    std::mt19937_64 rng(121);
    for (int round = 0; round < 2000; round++) {
        guest_pools.clear();
        const int n = (int)(rng() % 12);
        for (int i = 0; i < n; i++) {
            const uint64_t lo = (rng() % 64) * 0x1000, len = (1 + rng() % 16) * 0x1000;
            guest_pools.push_back({lo, lo + len});
        }
        std::sort(guest_pools.begin(), guest_pools.end(), [](const GuestPool& a, const GuestPool& b) { return a.lo < b.lo; });
        LivePoolIndex live;
        live.make();
        for (int q = 0; q < 50; q++) {
            const uint64_t lo = (rng() % 80) * 0x1000, hi = lo + (1 + rng() % 8) * 0x1000;
            bool want = false;
            for (const GuestPool& g : guest_pools) want |= g.lo < hi && g.hi > lo;
            if (live.reaches(lo, hi) != want) {
                std::printf("FAIL: reaches(%#llx, %#llx) = %d, a walk says %d\n", (unsigned long long)lo, (unsigned long long)hi,
                            (int)live.reaches(lo, hi), (int)want);
                return 1;
            }
        }
    }
    std::printf("LivePoolIndex: ok\n");
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

    sweep = block(mem, "void accum_sweep() {")
    check("guest_pools.empty()) return;" in sweep, "the sweep runs without a list of the game's pools")
    rule = "if (retire && !has_live && idle && p.last_value <= mem_completed && !p.prefetched) dead.push_back(it);"
    check(rule in sweep, "the sweep's rule lost a condition (a live pool, idle, the GPU past it, not imported ahead)")
    check(sweep.find("retire_pool(it);") < sweep.find("p.inherit_pending = false;"), "a swept chunk is not retired, or still inherits")
    check('getenv("RX_VK_ACCUM_RETIRE")' in block(mem, "bool accum_retire_on() {"), "RX_VK_ACCUM_RETIRE is not read")
    begin = block(mem, "void memory_begin_submission() {")
    check(begin.find("std::lock_guard lk(pools_mu);") < begin.find("accum_sweep();") < begin.find("retired_imports_give_back();"),
          "the sweep is not made under pools_mu at a submission's start, before the retired imports' give-back")

    cxx = shutil.which(a.cxx) or a.cxx
    with tempfile.TemporaryDirectory(prefix="accum-") as tmp:
        c, exe = Path(tmp) / "accum.cpp", Path(tmp) / "accum.exe"
        c.write_text(FIXTURE.replace("@INDEX@", block(mem, "struct LivePoolIndex {")), encoding="utf-8")
        subprocess.run([cxx, "-std=c++20", "-O1", str(c), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60)
        print(r.stdout, end="")
        check(r.returncode == 0, "LivePoolIndex.reaches differs from a walk over the pools")
    if fails:
        for f in fails:
            print("FAIL: " + f)
        raise SystemExit(1)
    print("PASS: chunks of ended pools are swept, and only those")


if __name__ == "__main__":
    main()

"""The core kept for the replay is one the process may run on (host/hos_thread.c reserved_candidate, last_fastest_core).

hos_reserved_cpus keeps a core for the replay. Its fallback kept to the cores whose logical processors are all in the
process's affinity mask (a launcher's, `start /affinity`, Process Lasso's), but Windows' choice of the last core of the
fastest kind (last_fastest_core) returned before that look: under 0x0FFF of 16 the last core of all, 0xC000, was kept. The
replay thread's pin to it is then refused (Windows refuses a processor outside the process's mask) and the thread runs
beside the game's.

reserved_candidate and pick_reserved_core are cut out of the source and run over authored cores and process masks: a core
with a logical processor outside the mask is no candidate and is not counted; with every processor allowed the core kept
is the one kept before. And last_fastest_core is read: it lists every core through reserved_candidate with the process's
own mask, and still counts them all (the cache die's rule reads that count, host/hos_x3d.h).

    python -I -B tests/test_reserved_core_mask.py [--cxx clang++]
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

RUN_ALL_ARGS = ["--cxx", "g++"]

ROOT = Path(__file__).resolve().parents[1]


def fail(message):
    raise SystemExit("FAIL: " + message)


def block(text, marker):
    start = text.index(marker)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


FIXTURE = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>
static void hos_log(const char *, ...) {}   // (ours: pick_reserved_core logs its choice once)
#define CHECK(ok) do { if (!(ok)) { std::fprintf(stderr, "failed line %d: %s\n", __LINE__, #ok); std::exit(1); } } while (0)
@PICK@
@CANDIDATE@
struct Core { uint64_t mask; unsigned char cls; };
// (as last_fastest_core lists them: every core, through reserved_candidate)
uint64_t pick(const std::vector<Core>& cores, uint64_t allowed) {
    std::vector<uint64_t> masks;
    std::vector<unsigned char> classes;
    for (const Core& c : cores) masks.push_back(reserved_candidate(c.mask, allowed)), classes.push_back(c.cls);
    return pick_reserved_core(masks.data(), classes.data(), (int)cores.size());
}
void add(std::vector<Core>& v, int n, int per, int first, unsigned char cls) {
    for (int i = 0; i < n; i++) v.push_back({((1ull << per) - 1) << (first + i * per), cls});
}
int main() {
    CHECK(reserved_candidate(0xC000, ~0ull) == 0xC000);
    CHECK(reserved_candidate(0xC000, 0x0FFF) == 0);
    CHECK(reserved_candidate(0xC000, 0x7FFF) == 0);      // (one of its two logical processors allowed: not wholly)
    CHECK(reserved_candidate(0x0C00, 0x0FFF) == 0x0C00);
    std::vector<Core> v;
    add(v, 8, 2, 0, 0);    // 8 cores with SMT, one kind (16 logical processors)
    CHECK(pick(v, ~0ull) == 0xC000);     // no mask (or one that could not be read): the last core, as before
    CHECK(pick(v, 0xFFFF) == 0xC000);
    CHECK(pick(v, 0x0FFF) == 0x0C00);    // the first 6 cores: the last of those, not the PC's last
    CHECK(pick(v, 0x7FFF) == 0x3000);    // half of the last core: the last whole one
    CHECK(pick(v, 0xFF00) == 0xC000);    // the last 4 cores (8 logical processors): the last
    CHECK(pick(v, 0x00FF) == 0x00C0);    // the first 4
    CHECK(pick(v, 0x003F) == 0);         // 3 cores, 6 logical processors: none kept, as on a PC that small
    CHECK(pick(v, 0x5555) == 0);         // one logical processor of every core: no core wholly allowed
    v.clear();
    add(v, 8, 2, 0, 1);    // 8 performance cores with HT (0-15), then 4 efficiency cores (16-19)
    add(v, 4, 1, 16, 0);
    CHECK(pick(v, ~0ull) == 0xC000);
    CHECK(pick(v, 0xF0FFF) == 0x0C00);   // 6 of the performance cores and the efficiency cores: the last fast one allowed
    CHECK(pick(v, 0xF003F) == 0);        // 3 performance cores: fewer than 4 of the fastest kind, none kept
    CHECK(pick(v, 0xF0000) == 0);        // the efficiency cores alone: 4 logical processors
    std::puts("PASS: the kept core is wholly inside the process's mask, or none; with every processor allowed, the core kept before");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--source', type=Path, default=ROOT / 'host/hos_thread.c')
    args = parser.parse_args()
    thread = args.source.read_text(encoding='utf-8')
    try:
        pick = block(thread, 'static uint64_t pick_reserved_core(')
        candidate = block(thread, 'static uint64_t reserved_candidate(')
        last = block(thread, 'static uint64_t last_fastest_core(')
        cpus = block(thread, 'static uint64_t process_cpus(')
    except ValueError as e:
        fail("a text this test reads is not there (%s)" % e)
    for text, needle, why in (
            (cpus, "if (!GetProcessAffinityMask(GetCurrentProcess(), &proc, &sys) || !proc) return ~0ull;",
             "a mask that cannot be read no longer allows every processor"),
            (last, "const uint64_t allowed = process_cpus();", "last_fastest_core does not read the process's mask"),
            (last, "masks[n] = reserved_candidate((uint64_t)e->Processor.GroupMask[0].Mask, allowed);",
             "last_fastest_core lists a core without the look at the process's mask"),
            (last, "*cores = n;", "last_fastest_core no longer counts every core it lists")):
        if needle not in text:
            fail(why)
    if last.index("reserved_candidate(") > last.index("*cores = n;") or last.index("*cores = n;") > last.index("return pick_reserved_core(masks, classes, n);"):
        fail("last_fastest_core: the cores are not listed, counted and then chosen from, in that order")
    with tempfile.TemporaryDirectory(prefix='reserved-core-mask-') as tmp:
        cpp = Path(tmp) / 'fixture.cpp'
        exe = Path(tmp) / 'fixture.exe'
        cpp.write_text(FIXTURE.replace("@PICK@", pick).replace("@CANDIDATE@", candidate), encoding='utf-8')
        built = subprocess.run([args.cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', str(cpp), '-o', str(exe)],
                               capture_output=True, text=True)
        if built.returncode:
            print(built.stdout + built.stderr)
            fail("the fixture did not build")
        subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    main()

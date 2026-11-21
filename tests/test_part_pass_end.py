"""A submission's part ends where the game has already ended its render pass (vk_replay.cpp maybe_split; Longshot a3565ac).

Compiles the actual maybe_split with stand-ins (split_part records where each part ended) and runs draws through it with the
game's pass open or ended: a part ends at the first pass end once it is RX_VK_PART_MIN (120) draws long, the submission's first
at the first past RX_VK_PART_FIRST (32), and wherever it is at RX_VK_PART_MAX (512) when the pass never ends; RX_VK_CHUNK=<n>
ends one every n draws wherever it falls, as before. Before the change parts ended every 120 draws, open pass or not.

    python -I -B tests/test_part_pass_end.py [--cxx clang++]
"""
import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
typedef int VkCommandBuffer;
static int64_t env_int(const char* n, int64_t d) { const char* e = getenv(n); return e ? atoll(e) : d; }
static bool dump_on() { return false; }
static void logf(const char*, ...) {}
struct Recording { int part = 0; };
static Recording rec;
Recording* rec_cur = &rec;
int rec_parts = 0;
int64_t part_work = 0;
constexpr int kMaxParts = 32;
thread_local bool split_off = false;
bool part_end_wanted = false;
static bool part_ends_before_draw() { return false; }
static bool pass_open = true;
static bool draw_pass_open() { return pass_open; }
static std::vector<int> ends;   // (the draw count of each part when it ended)
static void split_part(VkCommandBuffer&) { ends.push_back((int)part_work); part_work = 0, rec_parts++; }
#define namespace_close
struct { int64_t at_pass_end = 0, ceiling = 0; } part_st;
#include "maybe_split.inc"
int main(int argc, char** argv) {
    const char* mode = argc > 1 ? argv[1] : "";
    VkCommandBuffer cmd = 0;
    int bad = 0;
    auto run = [&](int draws, auto open_at) {
        ends.clear(), rec_parts = 0, part_work = 0;
        for (int i = 0; i < draws; i++) { pass_open = open_at(i); maybe_split(cmd); }
    };
    auto want = [&](std::vector<int> w, const char* what) {
        if (ends != w) {
            std::printf("FAIL %s: parts ended at", what);
            for (int e : ends) std::printf(" %d", e);
            std::printf("\n");
            bad = 1;
        }
    };
    if (!strcmp(mode, "rule")) {
        // (the game ends its pass every 50 draws: at draws 50, 100, 150...)
        run(400, [](int i) { return (i + 1) % 50 != 0; });
        want({50, 150, 150}, "the pass ends: the first past 32, then past 120");
        run(1200, [](int) { return true; });
        want({512, 512}, "a pass that never ends: the ceiling");
    } else if (!strcmp(mode, "chunk")) {
        run(400, [](int i) { return (i + 1) % 50 != 0; });
        want({120, 120, 120}, "RX_VK_CHUNK=120: every 120 draws, as before");
    }
    if (!bad) std::printf("ok %s\n", mode);
    return bad;
}
"""


def block(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    src = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    body = block(src, "void maybe_split(VkCommandBuffer& cmd) {")
    compiler = shutil.which(args.cxx)
    if not compiler:
        raise SystemExit("C++ compiler not found: " + args.cxx)
    with tempfile.TemporaryDirectory(prefix="part-pass-end-") as tmp:
        folder = Path(tmp)
        (folder / "maybe_split.inc").write_text(body + "\n", encoding="utf-8")
        (folder / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        exe = folder / "harness.exe"
        r = subprocess.run([compiler, "-std=c++17", "-Wall", "-Wno-unused-function", "-Wno-unused-variable", "-I" + str(folder),
                            str(folder / "harness.cpp"), "-o", str(exe)], capture_output=True, text=True)
        if r.returncode:
            print(r.stdout + r.stderr)
            raise SystemExit("FAIL: the harness did not compile")
        base = {k: v for k, v in os.environ.items() if not k.startswith("RX_VK_")}
        failed = False
        for mode, env in (("rule", base), ("chunk", dict(base, RX_VK_CHUNK="120"))):
            r = subprocess.run([str(exe), mode], capture_output=True, text=True, env=env, timeout=20)
            print(r.stdout, end="")
            failed |= r.returncode != 0
        if failed:
            raise SystemExit("FAIL")
    print("ok: a part ends where the game ended its render pass (RX_VK_PART_MIN/MAX/FIRST; RX_VK_CHUNK as before)")


if __name__ == "__main__":
    main()

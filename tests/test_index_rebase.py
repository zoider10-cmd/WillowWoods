"""An indexed draw's index buffer is bound at offset 0, with the draw's offset as its first index (gpu/vk/
index_rebase.h, vk_draw.cpp draw, bind_index and index_bind_same; no game, no GPU).

(Triforce, 11-21, the performance audit's DESC-12, after Source A's.) The game's draws share one buffer at different
offsets, so the skip of an index buffer already on the command buffer rarely held: nearly every indexed draw called
vkCmdBindIndexBuffer.

This compiles index_rebase.h with index_bind_same cut from the source and replays a frame's binds through them: 16-bit
draws at 0x100 and 0x2c0 of one buffer bind once, with first indices 0x80 and 0x160; an offset inside an index (3,
16-bit) and one past what a first index holds (0x200000000, 32-bit) fall back to their own offset; another buffer, or
another index type, binds again; with the switch off every offset binds, as before.

And reads the source: the direct indexed draw asks the rule, binds at 0 when it holds and passes the first index to
vkCmdDrawIndexed; the indirect indexed draw still binds at its own offset; the switch is read by the rule and is in the
switches table; the binds made are counted.

    python -I -B tests/test_index_rebase.py [--cxx clang++]
"""
import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu" / "vk"
RUN_ALL_ARGS = ["--cxx", "{cxx}"]


def check(ok, why):
    if not ok:
        raise SystemExit("FAIL: " + why)


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


PROGRAM = r"""
#include <cstdint>
#include <cstdio>
#include "index_rebase.h"
static int fails = 0;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL:%d %s\n", __LINE__, #x); fails++; } } while (0)
INDEX_BIND_SAME
// the draw's own lines, as vk_draw.cpp has them: what is bound, and the first index the draw is given
struct Bound { uint64_t buffer = 0, offset = 0; uint32_t type = 0; int on = 0; } last;
static int binds;
static uint32_t draw(bool rebase_on, uint64_t buffer, uint64_t offset, uint32_t unit) {
    const uint32_t type = unit == 1 ? 2 : unit == 2 ? 0 : 1;
    uint32_t first = 0;
    const bool rebased = rebase_on && index_rebase::rebase(offset, unit, &first);
    const uint64_t at = rebased ? 0 : offset;
    if (!index_bind_same(buffer, at, type, last.buffer, last.offset, last.type, last.on)) binds++, last = {buffer, at, type, 1};
    return first;
}
int main() {
    CHECK(index_rebase::on(nullptr) && index_rebase::on("") && index_rebase::on("1") && !index_rebase::on("0"));
    uint32_t f = 99;
    CHECK(index_rebase::rebase(0x100, 2, &f) && f == 0x80);
    CHECK(index_rebase::rebase(0x2c0, 2, &f) && f == 0x160);
    CHECK(index_rebase::rebase(0, 4, &f) && f == 0);
    CHECK(index_rebase::rebase(7, 1, &f) && f == 7);
    f = 99;
    CHECK(!index_rebase::rebase(3, 2, &f) && f == 99);                 // (inside an index)
    CHECK(!index_rebase::rebase(0x200000000ull, 4, &f) && f == 99);    // (past what a first index holds)
    CHECK(index_rebase::rebase(0x7fffffffull * 4, 4, &f) && f == 0x7fffffffu);
    CHECK(!index_rebase::rebase(0x80000000ull * 4, 4, &f));
    CHECK(!index_rebase::rebase(16, 0, &f));
    // a frame's draws from one buffer
    CHECK(draw(true, 0xB0, 0x100, 2) == 0x80 && binds == 1);
    CHECK(draw(true, 0xB0, 0x2c0, 2) == 0x160 && binds == 1);           // (the same buffer at another offset: no bind)
    CHECK(draw(true, 0xB0, 0x100, 2) == 0x80 && binds == 1);
    CHECK(draw(true, 0xB0, 3, 2) == 0 && binds == 2 && last.offset == 3);   // (falls back: at its own offset)
    CHECK(draw(true, 0xB0, 0x40, 2) == 0x20 && binds == 3 && last.offset == 0);
    CHECK(draw(true, 0xB0, 0x40, 4) == 0x10 && binds == 4);             // (another index type: bound again)
    CHECK(draw(true, 0xC0, 0x40, 4) == 0x10 && binds == 5);             // (another buffer)
    CHECK(draw(true, 0xC0, 0x200000000ull, 4) == 0 && binds == 6 && last.offset == 0x200000000ull);
    // the switch off: every offset binds, first index 0
    last = {}, binds = 0;
    CHECK(draw(false, 0xB0, 0x100, 2) == 0 && binds == 1);
    CHECK(draw(false, 0xB0, 0x2c0, 2) == 0 && binds == 2);
    CHECK(draw(false, 0xB0, 0x2c0, 2) == 0 && binds == 2);
    return fails ? 1 : 0;
}
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    src = (VK / "vk_draw.cpp").read_text(encoding="utf-8")
    check('#include "index_rebase.h"' in src, "vk_draw.cpp does not use the rule")
    draw = block(src, "void draw(")
    direct = draw[draw.index("} else if (d.indexed) {"):]
    direct = direct[:direct.index("} else {")]
    check('static const bool rebase_on = index_rebase::on(getenv("RX_VK_INDEX_REBASE"));' in direct, "the switch is not the rule's")
    check("const bool rebased = rebase_on && index_rebase::rebase((uint64_t)ib.offset, unit, &first_index);" in direct and
          "bind_index(cmd, ib.buffer, rebased ? 0 : ib.offset, itype);" in direct,
          "the direct indexed draw does not bind at 0 where the rule holds, and at its own offset where it does not")
    check("vkCmdDrawIndexed(cmd, (uint32_t)d.count, (uint32_t)std::max(1, d.instances), first_index, d.base_vertex," in direct,
          "the draw is not given its first index")
    check(direct.index("uint32_t first_index = 0;") < direct.index("index_rebase::rebase("), "the first index is not 0 unless the rule sets it")
    indirect = draw[draw.index("if (d.indirect) {"):draw.index("} else if (d.indexed) {")]
    check("bind_index(cmd, ib.buffer, ib.offset, itype);" in indirect and "index_rebase" not in indirect,
          "an indirect indexed draw, whose first index is in the GPU's records, no longer binds at its own offset")
    bind = block(src, "void bind_index(")
    check(bind.index("index_bind_same(") < bind.index("vkCmdBindIndexBuffer("),   # (ours counts no binds made: no FC_IBIND_MADE)
          "the bind is not skipped when the same buffer, offset and type are bound")
    sw = (VK / "switches.def").read_text(encoding="utf-8")   # (ours: the switches' rows are in gpu/vk/switches.def)
    check("SW(RX_VK_INDEX_REBASE," in sw, "gpu/vk/switches.def has no row for RX_VK_INDEX_REBASE")

    with tempfile.TemporaryDirectory(prefix="index-rebase-") as tmp:
        c, exe = Path(tmp) / "rebase.cpp", Path(tmp) / "rebase.exe"
        c.write_text(PROGRAM.replace("INDEX_BIND_SAME", block(src, "bool index_bind_same(")), encoding="utf-8")
        subprocess.run([args.cxx, "-std=c++20", "-O1", "-Wall", "-Wextra", "-Werror", "-I" + str(VK), str(c), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        check(r.returncode == 0, "the rule as made:\n" + r.stdout)
    print("PASS: draws at different offsets of one index buffer bind it once, at 0, each with its first index")


if __name__ == "__main__":
    main()

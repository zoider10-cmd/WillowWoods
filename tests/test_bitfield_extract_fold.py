"""(HeyListen 46e5a0a7) The constant fold of bit-field extracts gives SPIR-V's values (no game, no GPU).

gpu/vk/eden/shader_recompiler/ir_opt/constant_propagation_pass.cpp folded BitFieldUExtract(base, 0, 32) to 0 (1U << 32 is
undefined in C++, 0 on x86), and threw on BitFieldSExtract with a count of 0 and on any extract whose offset + count passes
32, which failed the program's translation. Now a count of 0 or an offset of 32 gives 0, a count of 32 the base, and an
undefined range (offset + count > 32) is not folded but left to the back end.

The two cases are cut out of the pass into a harness whose FoldWhenAllImmediates calls the lambda on the immediates, and
compared with SPIR-V's semantics over the edge cases and 3 million random immediates (HeyListen's test runs the whole pass;
this one needs no Eden build).

    python -I -B tests/test_bitfield_extract_fold.py [--cxx g++]
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block, between  # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "gpu/vk/eden/shader_recompiler/ir_opt/constant_propagation_pass.cpp"

HARNESS = r"""
#include <cstdint>
#include <cstdio>
#include <random>
using u32 = uint32_t; using s32 = int32_t; using u64 = uint64_t;
namespace IR { enum class Opcode { BitFieldUExtract, BitFieldSExtract, BitFieldInsert, Other }; }
struct Val { u32 v; u32 U32() const { return v; } };
struct Inst {
    u32 args[3];
    Val Arg(int i) const { return {args[i]}; }
    bool AreAllArgsImmediates() const { return true; }
};
namespace IR { using Inst = ::Inst; }
struct LogicError { template <class... A> LogicError(A&&...) {} };
static bool folded;
static u32 result;
template <class F> bool FoldWhenAllImmediates(Inst& inst, F&& f) {
    result = f(inst.args[0], inst.args[1], inst.args[2]);
    folded = true;
    return true;
}
@HELPER@
static void Fold(IR::Opcode op, Inst& inst) {
    folded = false;
    switch (op) {
@CASES@
    default: return;
    }
}
// SPIR-V: defined for offset + count <= 32; count 0 gives 0, count 32 the base (U) or the base (S)
static bool Reference(bool sign, u32 a, u32 off, u32 count, u32& out) {
    if ((u64)off + count > 32) return false;
    if (count == 0) { out = 0; return true; }
    const u64 field = ((u64)a >> off) & ((1ull << count) - 1);
    if (!sign) { out = (u32)field; return true; }
    const bool neg = ((field >> (count - 1)) & 1) != 0;
    out = (u32)(neg ? (field | (~0ull << count)) : field);
    return true;
}
static long long wrong, threw, folded_undefined, checked;
static void One(bool sign, u32 a, u32 off, u32 count) {
    Inst inst{{a, off, count}};
    try {
        Fold(sign ? IR::Opcode::BitFieldSExtract : IR::Opcode::BitFieldUExtract, inst);
    } catch (const LogicError&) {
        if (threw++ < 5) std::printf("threw: %s(%#x, %u, %u)\n", sign ? "SExtract" : "UExtract", a, off, count);
        return;
    }
    u32 want;
    if (!Reference(sign, a, off, count, want)) {
        if (folded && folded_undefined++ < 5) std::printf("folded an undefined %s(%#x, %u, %u)\n", sign ? "SExtract" : "UExtract", a, off, count);
        return;
    }
    checked++;
    if (!folded || result != want) {
        if (wrong++ < 10) std::printf("wrong: %s(%#x, %u, %u) = %#x%s, SPIR-V %#x\n", sign ? "SExtract" : "UExtract", a, off, count,
                                      result, folded ? "" : " (not folded)", want);
    }
}
int main() {
    const u32 bases[] = {0, 1, 0x80000000u, 0xFFFFFFFFu, 0x7FFFFFFFu, 0x12345678u, 0xDEADBEEFu};
    for (int sign = 0; sign < 2; sign++)
        for (u32 a : bases)
            for (u32 off = 0; off <= 33; off++)
                for (u32 count = 0; count <= 33; count++) One(sign, a, off, count);
    std::mt19937 rng(46);
    for (int i = 0; i < 3000000; i++) {
        const u32 a = rng(), off = rng() % 33, count = rng() % 33;
        One(i & 1, a, off, count);
    }
    std::printf("%lld checked, %lld wrong, %lld threw, %lld undefined ones folded\n", checked, wrong, threw, folded_undefined);
    return wrong || threw || folded_undefined ? 1 : 0;
}
"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cxx", default="g++")
    a = p.parse_args()
    cxx = shutil.which(a.cxx) or a.cxx
    src = SRC.read_text(encoding="utf-8")
    helper = block(src, "inline bool BitFieldRangeDefined(const IR::Inst& inst) {")
    cases = between(src, "    case IR::Opcode::BitFieldUExtract:", "    case IR::Opcode::BitFieldInsert:")
    code = HARNESS.replace("@HELPER@", helper).replace("@CASES@", cases)
    with tempfile.TemporaryDirectory(prefix="bfe-fold-") as tmp:
        c, exe = Path(tmp) / "fold.cpp", Path(tmp) / "fold.exe"
        c.write_text(code, encoding="utf-8")
        subprocess.run([cxx, "-std=c++20", "-O2", "-w", str(c), "-o", str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        print(r.stdout, end="")
        if r.returncode:
            raise SystemExit("FAIL: the bit-field extract fold differs from SPIR-V")
    print("PASS: bit-field extracts fold as SPIR-V defines them, and undefined ranges are left to the back end")


if __name__ == "__main__":
    main()

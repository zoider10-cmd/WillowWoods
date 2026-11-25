"""(HeyListen bdd56f2a, their issue 97: black leaves on NVIDIA) Dead code elimination keeps the warp-wide operations (VOTE,
ballot, shuffles) in gpu/vk/eden's Inst::MayHaveSideEffects, in particular a VoteAny the constant fold leaves without a
reader. Builds the real ConstantPropagationPass and DeadCodeEliminationPass with tests/test_dce_convergent_ops.cpp. No game,
no GPU.

python -I -B tests/test_dce_convergent_ops.py [--cxx clang++] [--microinstruction <microinstruction.cpp>]
"""
import argparse
import os
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
EDEN = ROOT / "gpu/vk/eden"
SR = EDEN / "shader_recompiler"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    parser.add_argument("--microinstruction", type=Path, default=SR / "frontend/ir/microinstruction.cpp",
                        help="another copy of microinstruction.cpp (to show the check fails on the code before the fix)")
    args = parser.parse_args()
    sources = [SR / "frontend/ir" / n for n in ("basic_block.cpp", "condition.cpp", "ir_emitter.cpp", "opcodes.cpp", "patch.cpp",
                                                 "type.cpp", "value.cpp")]
    sources += [args.microinstruction, SR / "ir_opt/constant_propagation_pass.cpp", SR / "ir_opt/dead_code_elimination_pass.cpp"]
    with tempfile.TemporaryDirectory(prefix="dce-conv-") as tmp:
        exe = Path(tmp) / ("t.exe" if os.name == "nt" else "t")
        subprocess.run([args.cxx, "-std=c++20", "-O1", "-w", "-I", str(SR / "frontend/ir"), "-I", str(EDEN),
                        "-I", str(ROOT / "gpu/vk/compat"), "-I", str(ROOT / "gpu/compat"),
                        str(ROOT / "tests/test_dce_convergent_ops.cpp"), *map(str, sources), "-o", str(exe)],
                       check=True, timeout=600)
        subprocess.run([str(exe)], check=True, timeout=60)


if __name__ == "__main__":
    main()

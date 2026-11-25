"""(HeyListen 5716afbf, its Volumetric fog row only) The Graphics tab's Volumetric fog row leaves the fog's three compute
programs out (gpu/vk/fog_row.h). No game, no GPU.

fog_row.h is built on its own and asked: the three program keys and no other; RX_VK_FOG over the row (unset: the row). The
source is checked (tests/srccut.py): the row, on by default, read once at the start and exempt from the Quality preset (which
does not set it); fog_runs reads RX_VK_FOG over opts.fog once; dispatch returns before any work for a fog program while the fog
is off, after RX_VK_SKIP_PROG's own return.

python -I -B tests/test_fog_row.py [--cxx clang++]
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))   # (python -I leaves the check's own folder off the path)
from srccut import block, between  # noqa: E402

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]
VK = ROOT / "gpu" / "vk"

HARNESS = r"""
#include "fog_row.h"
#include <cstdio>
int main() {
    int bad = 0;
    auto expect = [&](bool ok, const char* what) { if (!ok) std::printf("FAIL: %s\n", what), bad = 1; };
    expect(fog_row::fog_program(0x27ee9883e2a20323ull) && fog_row::fog_program(0xee7764a6b1ef459cull) &&
           fog_row::fog_program(0x1e2fcee33a0c7209ull), "the fog's three programs");
    expect(!fog_row::fog_program(0) && !fog_row::fog_program(0x27ee9883e2a20322ull), "no other program");
    expect(fog_row::fog_on(-1, 1) && !fog_row::fog_on(-1, 0), "unset: the row decides");
    expect(!fog_row::fog_on(0, 1) && fog_row::fog_on(1, 0) && fog_row::fog_on(2, 0), "RX_VK_FOG over the row");
    if (!bad) std::printf("ok\n");
    return bad;
}
"""


def check_source():
    menu = (VK / "vk_menu.cpp").read_text(encoding="utf-8")
    header = (VK / "vk_menu.h").read_text(encoding="utf-8")
    draw = (VK / "vk_draw.cpp").read_text(encoding="utf-8")
    row = between(menu, '{TAB_GRAPHICS, "Volumetric fog", &opts.fog, 0, 1, 1, tx_onoff,', "},", where="gpu/vk/vk_menu.cpp")
    if not row.rstrip().endswith("nullptr, true, true"):
        raise SystemExit("the Volumetric fog row: read once at the start (restart) and exempt from the Quality preset")
    if "int fog = 1;" not in header:
        raise SystemExit("the fog is on by default (opts.fog = 1)")
    if "opts.fog" in block(menu, "void apply_preset(int p) {", where="gpu/vk/vk_menu.cpp"):
        raise SystemExit("apply_preset sets the fog now: take the row's preset_exempt away (tests/test_preset_exempt.py)")
    runs = block(menu, "bool fog_runs() {", where="gpu/vk/vk_menu.cpp")
    if "static const bool on" not in runs or 'getenv("RX_VK_FOG")' not in runs or "fog_row::fog_on(env, opts.fog)" not in runs:
        raise SystemExit("fog_runs: RX_VK_FOG over the row, decided once")
    dispatch = block(draw, "void dispatch(VkCommandBuffer cmd, NvnState& s, uint32_t x, uint32_t y, uint32_t z, uint64_t indirect) {",
                     where="gpu/vk/vk_draw.cpp")
    skip = dispatch.find("if (fog_row::fog_program(cp->key) && !fog_runs()) {")
    if skip < 0 or dispatch.find("return;", skip) > dispatch.find("dclock.key = cp->key;"):
        raise SystemExit("dispatch: a fog program returns before any work while the fog is off")
    if not 0 <= dispatch.find('getenv("RX_VK_SKIP_PROG")') < skip:
        raise SystemExit("dispatch: the fog's return is where RX_VK_SKIP_PROG's is, after the program is known")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    check_source()
    print("PASS: the Volumetric fog row (on, at the start, preset-exempt), fog_runs, dispatch's return")
    with tempfile.TemporaryDirectory(prefix="fog-row-") as tmp:
        src = Path(tmp) / "fog.cpp"
        src.write_text(HARNESS, encoding="utf-8")
        exe = Path(tmp) / ("fog.exe" if os.name == "nt" else "fog")
        subprocess.run([args.cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(VK), str(src), "-o", str(exe)],
                       check=True, timeout=120)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        print(r.stdout, end="")
        if r.returncode or "ok" not in r.stdout:
            raise SystemExit("fog_row.h")


if __name__ == "__main__":
    main()

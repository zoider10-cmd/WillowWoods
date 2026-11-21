"""The foliage in the sun's far shadow cascades drawn with one face culled (gpu/vk/foliage_shadow.h; vk_draw.cpp draw_cull;
Triforce v0.6.0 after NX2navi 754ded9; no game, no GPU).

Compiles the header's rules and checks them: the switch's values and default (off here; "1" from layer 1, the back faces), which
draws are taken (mesh programs only, no colour target, a depth target square and wider than 768, the layer), and that a draw
the game already culls keeps its own face. Reads vk_draw.cpp for what needs the game: the face goes through the packed dynamic
state (so a draw into another cascade layer is not taken for the same state), and the cull mode is set from it as dynamic
state (no other pipeline).

    python -I -B tests/test_foliage_shadow.py [--cxx clang++]
"""
import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

RUN_ALL_ARGS = ["--cxx", "{cxx}"]

ROOT = Path(__file__).resolve().parents[1]

HARNESS = r"""
#include "foliage_shadow.h"
#include <cstdio>
using namespace mkwvk::foliage_shadow;
static int bad = 0;
#define EXPECT(x) do { if (!(x)) { std::printf("FAIL: %s\n", #x); bad = 1; } } while (0)
int main() {
    Rule d = parse(nullptr), e = parse(""), off = parse("off"), neg = parse("-1"), two = parse("2"), f = parse("0f");
    EXPECT(d.from == -1);   // (off unless asked for here)
    EXPECT(e.from == -1);
    Rule one = parse("1");
    EXPECT(one.from == 1 && !one.front);
    EXPECT(off.from == -1 && neg.from == -1);
    EXPECT(two.from == 2 && !two.front);
    EXPECT(f.from == 0 && f.front);
    // (a far cascade's foliage: a mesh program, no colour, a depth target 1600 square, layer 1 or 2)
    EXPECT(cull(one, kNone, true, 0, true, 1600, 1600, 1) == kBack);
    EXPECT(cull(one, kNone, true, 0, true, 1600, 1600, 2) == kBack);
    EXPECT(cull(f, kNone, true, 0, true, 1600, 1600, 0) == kFront);
    // (left as the game draws it)
    EXPECT(cull(one, kNone, true, 0, true, 1600, 1600, 0) == kNone);    // the near cascade
    EXPECT(cull(one, kNone, false, 0, true, 1600, 1600, 2) == kNone);   // not a mesh program
    EXPECT(cull(one, kNone, true, 1, true, 1600, 1600, 2) == kNone);    // a colour target
    EXPECT(cull(one, kNone, true, 0, false, 1600, 1600, 2) == kNone);   // no depth target
    EXPECT(cull(one, kNone, true, 0, true, 768, 768, 2) == kNone);      // a character's shadow map
    EXPECT(cull(one, kNone, true, 0, true, 1600, 900, 2) == kNone);     // not square
    EXPECT(cull(one, kFront, true, 0, true, 1600, 1600, 2) == kFront);  // the game culls already
    EXPECT(cull(off, kNone, true, 0, true, 1600, 1600, 2) == kNone);  // off
    if (!bad) std::printf("ok: the rules\n");
    return bad;
}
"""


def block(text, marker):
    start = text.index(marker)
    end = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


def check_source(draw):
    if '#include "foliage_shadow.h"' not in draw or "constexpr int kDynCull = 23;" not in draw:
        raise SystemExit("FAIL: vk_draw.cpp does not include foliage_shadow.h, or has no kDynCull (the packed word of the face)")
    pack = block(draw, "int dyn_pack(")
    if "up[kDynCull] = draw_cull(s, at)" not in pack or re.search(r"up\[23\]", pack) or "s.poly.cull" in pack:
        raise SystemExit("FAIL: vk_draw.cpp dyn_pack: the face packed is not draw_cull's alone")
    state = block(draw, "void dynamic_state(VkCommandBuffer cmd")
    if "const uint32_t cull = du[kDynCull];" not in state or "s.poly.cull" in state:
        raise SystemExit("FAIL: vk_draw.cpp dynamic_state: the cull mode is not set from draw_cull's face")
    if not state.index("dyn_pack(s, at, topo, mesh, df, du, db)") < state.index("const uint32_t cull = du[kDynCull];"):
        raise SystemExit("FAIL: vk_draw.cpp dynamic_state: the face is read before it is packed")
    for needle in ("cull == NVN_FACE_FRONT ? VK_CULL_MODE_FRONT_BIT", "cull == NVN_FACE_BACK ? VK_CULL_MODE_BACK_BIT",
                   "if (DYN_CHANGED(cull)) vkCmdSetCullMode(cmd, d.cull);"):
        if needle not in state:
            raise SystemExit("FAIL: vk_draw.cpp dynamic_state: the cull mode is not dynamic state (%s)" % needle)
    cull = block(draw, "uint32_t draw_cull(")
    if 'getenv("RX_VK_FOLIAGE_SHADOW_CULL")' not in cull or "cur_program->mesh || cur_program->fallback" not in cull:
        raise SystemExit("FAIL: vk_draw.cpp draw_cull: not RX_VK_FOLIAGE_SHADOW_CULL's rule for mesh programs")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cxx", default="clang++")
    args = parser.parse_args()
    check_source((ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8"))
    compiler = shutil.which(args.cxx)
    if not compiler:
        raise SystemExit("C++ compiler not found: " + args.cxx)
    with tempfile.TemporaryDirectory(prefix="foliage-shadow-") as tmp:
        folder = Path(tmp)
        (folder / "harness.cpp").write_text(HARNESS, encoding="utf-8")
        exe = folder / "harness.exe"
        r = subprocess.run([compiler, "-std=c++17", "-Wall", "-I" + str(ROOT / "gpu/vk"), str(folder / "harness.cpp"), "-o", str(exe)],
                           capture_output=True, text=True)
        if r.returncode:
            print(r.stdout + r.stderr)
            raise SystemExit("FAIL: the harness did not compile")
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        print(r.stdout, end="")
        if r.returncode:
            raise SystemExit("FAIL")
    print("ok: the far cascades' foliage is drawn with one face culled (RX_VK_FOLIAGE_SHADOW_CULL)")


if __name__ == "__main__":
    main()

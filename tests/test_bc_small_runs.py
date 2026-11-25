"""(ProjectReLink 88e38c0) ASTC->BC3: 4 layers of 1024 x 1024 a run through an aliased view of the scratch
(RX_VK_BC_SMALL_RUNS, gpu/vk/vk_texture.cpp; no game, no GPU).

The BC3 scratch is 2048 x 2048 x 1 (16 MB); the same memory as 1024 x 1024 x 4 (vmaCreateAliasingImage) lets the levels of
1024 and less of a texture array decode and encode 4 layers a run. Runs of layers gave AMD's Windows driver dark lines on
Hyrule Field, and there is no NVIDIA card here, so it is on by default on NVIDIA only. Read from the source:
- the default: NVIDIA's vendor id only, the switch over it, never with RX_VK_BC_LAYERS or a scratch given back (RX_VK_BC_IDLE_S);
- the small image fits the scratch's memory (same bytes) and the encoder's buffer (4 layers' blocks);
- a run uses the small view only for a level that fits it and not for a resized texture, and the image used starts from
  UNDEFINED each run (Vulkan's rule for aliases); the encoder reads the view that was decoded into.

    python -I -B tests/test_bc_small_runs.py
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block, between  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    tex = (ROOT / "gpu/vk/vk_texture.cpp").read_text(encoding="utf-8")
    fails = []

    def check(ok, why):
        if not ok:
            fails.append(why)

    want = block(tex, "bool bc_small_wanted() {")
    check('getenv("RX_VK_BC_SMALL_RUNS")' in want and "dev.props.vendorID == 0x10DE" in want,
          "RX_VK_BC_SMALL_RUNS is not NVIDIA-only by default")
    check("0x1002" not in want and "0x8086" not in want, "the small runs are on by default on AMD or Intel")
    check('!getenv("RX_VK_BC_LAYERS")' in want and "!bc_idle_s()" in want,
          "the small runs are not off with RX_VK_BC_LAYERS or a scratch that is given back")
    dims = re.search(r"constexpr uint32_t kBcDim = (\d+)", tex)
    small = re.search(r"constexpr uint32_t kBcSmallDim = (\d+), kBcSmallLayers = (\d+);", tex)
    check(bool(dims and small), "the scratch's sizes are not found")
    if dims and small:
        big, sd, sl = int(dims.group(1)), int(small.group(1)), int(small.group(2))
        check(sd * sd * sl == big * big, "the small scratch is not the same bytes as the 1-layer scratch (%d^2 x %d vs %d^2)" % (sd, sl, big))
    make = block(tex, "bool bc_scratch_make() {")
    check(make.find("create_aliasing_image(bc_scratch_alloc, si, bc_small)") > make.find("bc_have = true;"),
          "the small image is not made over the scratch's memory once it is there")
    layout = block(tex, "bool bc_scratch_layout(VkCommandBuffer cmd, bool resized = false) {")
    check("b.image = bc_small;" in layout, "the small scratch's first layout is not set")
    run = between(tex, "const bool small = bc_small_view && !tex.bc_resized && g.w <= kBcSmallDim && g.h <= kBcSmallDim;",
                  "k0 = k1;")
    check("const uint32_t run = small ? kBcSmallLayers : bc_layers();" in run, "a small level's run is not 4 layers")
    check(run.find("ab.oldLayout = VK_IMAGE_LAYOUT_UNDEFINED") < run.find("vkCmdDispatch(") and "ab.image = small ? bc_small : bc_scratch;" in run,
          "the image a run uses does not start from UNDEFINED before the decode")
    check("small ? bc_small_view : bc_scratch_view" in run and "small ? bc_small_view : VK_NULL_HANDLE" in run,
          "the decode and the encode do not use the same view")
    if fails:
        for f in fails:
            print("FAIL: " + f)
        raise SystemExit(1)
    print("BC3 small runs: ok (NVIDIA only by default)")


if __name__ == "__main__":
    main()

"""(ProjectReLink 88e38c0) Indirect mesh draws converted at the game's barriers (RX_VK_INDIRECT_AHEAD; no game, no GPU).

Each indirect mesh draw's records ({count, first} in NVN, {x, y, z} in Vulkan) were copied into a ring right before the draw:
a pass ended and three barriers a draw. Now at each NOP_BARRIER the replay scans forward to the next op that may write
memory, collects the indirect NOP_DRAW_MESH ops, and converts them all at once right after the game's barrier; each draw finds
its records by its op pointer and the stretch's generation. Read from the source:
- the scan stops at every op that may write memory (barriers, dispatches, copies, updates, events, counters, conditional
  render, jumps, calls, the end) and only those: the set of ops that it walks over is exactly the state binds, clears and
  draws, and every op of rx_nvn.h is either walked over or stops it;
- each replayed command buffer begins a new stretch (mesh_convert_ahead with none), and the draw names its op first;
- the feature is off on the compute fallback and with the records' other readings (RAW, ARGS, COUNT_WORD), and not in the
  parallel replay's workers;
- the ahead path's conversion matches the old one's (fill of 1s, copy of the count word, the three barriers).

    python -I -B tests/test_indirect_ahead.py
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block, between  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

# (the ops the scan walks over: they write no memory the next draws' counts could come from)
WALK = {"NOP_DRAW_MESH", "NOP_SET_RT", "NOP_CLEAR_COLOR", "NOP_CLEAR_DS", "NOP_VIEWPORTS", "NOP_SCISSOR", "NOP_DEPTH_RANGE",
        "NOP_BIND_PROGRAM", "NOP_BIND_STATE", "NOP_BIND_VATTR", "NOP_BIND_VSTREAM", "NOP_BIND_VBUF", "NOP_BIND_UBO",
        "NOP_BIND_SSBO", "NOP_BIND_TEX", "NOP_BIND_SAMP", "NOP_STENCIL", "NOP_POLY_OFFSET", "NOP_DRAW", "NOP_DRAW_IDX",
        "NOP_SET_TEX_POOL", "NOP_SET_SAMP_POOL", "NOP_BLEND_COLOR", "NOP_BIND_IMG", "NOP_DEPTH_CLAMP", "NOP_RENDER_ENABLE",
        "NOP_RASTER_DISCARD", "NOP_PRIMITIVE_RESTART", "NOP_BIND_BUFS", "NOP_DRAW_INDIRECT", "NOP_PUSH_CONST"}
# (the ops that must stop it)
STOP = {"NOP_BARRIER", "NOP_DISPATCH", "NOP_DISPATCH_INDIRECT", "NOP_COPY_B2B", "NOP_COPY_B2T", "NOP_COPY_T2B", "NOP_COPY_T2T",
        "NOP_COPY_STRIDE", "NOP_CLEAR_BUF", "NOP_CLEAR_TEX", "NOP_UPDATE_UB", "NOP_SIGNAL_EVENT", "NOP_WAIT_EVENT",
        "NOP_REPORT_COUNTER", "NOP_RESET_COUNTER", "NOP_RENDER_COND", "NOP_END", "NOP_BEGIN", "NOP_JUMP", "NOP_CALL"}


def main():
    replay = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    draw = (ROOT / "gpu/vk/vk_draw.cpp").read_text(encoding="utf-8")
    nvn = (ROOT / "gpu/render/rx_nvn.h").read_text(encoding="utf-8")
    fails = []

    def check(ok, why):
        if not ok:
            fails.append(why)

    ops = set(re.findall(r"\b(NOP_[A-Z0-9_]+)\b", nvn)) - {"NOP_COUNT_"}
    check(not (ops - WALK - STOP), "ops this check does not know (add each to WALK or STOP): " + ", ".join(sorted(ops - WALK - STOP)))

    rep = block(replay, "void replay(VkCommandBuffer& cmd, NvnState& s, const uint8_t* p, const uint8_t* end = nullptr) {")
    check(rep.find("if (!dry) mesh_convert_ahead(cmd, nullptr, 0);") < rep.find("for (;;) {"),
          "a replayed command buffer does not begin a new stretch")
    bar = between(rep, "case NOP_BARRIER:", "// ---- work ----")
    check("if (!worker && mesh_ahead_on()) {" in bar, "the scan is not gated on mesh_ahead_on() and kept out of the workers")
    check(bar.find('full_barrier(cmd, "barrier (the game\'s nvnCommandBufferBarrier)");') < bar.find("mesh_convert_ahead(cmd, ahead.data()"),
          "the conversion is not after the game's barrier")
    scan = between(bar, "switch (hq.op) {", "if (stop) break;")
    walked = set(re.findall(r"case (NOP_[A-Z0-9_]+):", scan))
    check(walked == WALK, "the scan walks over other ops than the state binds, clears and draws: "
          f"extra {sorted(walked - WALK)}, missing {sorted(WALK - walked)}")
    check("default: stop = true;" in scan, "an op the scan does not know does not stop it")
    check("q + hq.size > end" in bar and "hq.size < sizeof hq" in bar, "the scan can run past its stream's end")

    mesh = between(rep, "const auto d = payload<nvn_p_draw_mesh>(a, avail);", "case NOP_DISPATCH: {")
    check(mesh.find("mesh_op_set(p);") < mesh.find("draw(cmd, s, da);") and mesh.find("mesh_op_set(p);") >= 0,
          "the mesh draw does not name its op before draw()")

    on = block(draw, "bool mesh_ahead_on() {")
    for name in ("RX_VK_INDIRECT_AHEAD", "RX_VK_MESH_IND_RAW", "RX_VK_MESH_ARGS", "RX_VK_MESH_IND_COUNT_WORD", "dev.mesh_fallback"):
        check(name in on, "mesh_ahead_on() does not look at " + name)
    conv = block(draw, "bool mesh_indirect_convert(VkCommandBuffer cmd, const DrawArgs& d) {")
    check(conv.find("m.op == mesh_op_now && m.gen == mesh_ahead_gen") >= 0 and
          conv.find("m.op == mesh_op_now") < conv.find("end_pass(cmd);"),
          "a draw converted ahead still ends the pass, or is found without its generation")
    ahead = block(draw, "void mesh_convert_ahead(VkCommandBuffer cmd, const MeshDraw* draws, size_t count) {")
    check(0 <= ahead.find("mesh_ahead().clear();") < ahead.find("mesh_ahead_gen++;") < ahead.find("if (!count) return;"),
          "a stretch does not start empty under a new generation")
    for step in ("vkCmdFillBuffer(cmd, mesh_ring, j.off, (uint64_t)j.n * 12, 1u);", "vkCmdCopyBuffer(cmd, j.args.buffer, mesh_ring,",
                 "VK_PIPELINE_STAGE_2_DRAW_INDIRECT_BIT"):
        check(step in ahead, "the ahead conversion lacks: " + step)
    check(ahead.count("vkCmdPipelineBarrier2(cmd, &di);") == 3, "the ahead conversion has not the old one's three barriers")
    if fails:
        for f in fails:
            print("FAIL: " + f)
        raise SystemExit(1)
    print("indirect mesh draws ahead: ok")


if __name__ == "__main__":
    main()

"""(Triforce 86170247) The recordings' timestamps through a ring the GPU copies them into (RX_VK_QUERY_RING,
gpu/vk/vk_replay.cpp; no game, no GPU).

vkGetQueryPoolResults cost about 0.6 ms a frame on AMD's Windows driver on the thread that replays the frame, and with the recorder
thread each call is a boundary that waits for it. A slot's next use copies its last use's timestamps into a mapped, host-coherent
ring before it resets them; the slot's turn after that reads them from memory. Read from the source:
- the ring: made with the pool, host-coherent or not used (an invalidate would be a recorder boundary), the switch;
- the copy: in the command buffer just begun, before the reset (query commands run in submission order), each value with its
  availability word, never waiting on the GPU (a use that was never submitted would hang it), behind a copy-to-host barrier,
  through vk_work.h (the recorder's list, so the recorder thread keeps it in order);
- the read: only what was copied, only when the copying use was submitted (taken before recording_wait clears it), each
  value's availability checked; the old path kept when there is no ring.

    python -I -B tests/test_query_ring.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def before(text, *parts):
    at = -1
    for p in parts:
        i = text.find(p, at + 1)
        if i < 0:
            return False
        at = i
    return True


def main():
    vk = ROOT / "gpu/vk"
    replay = (vk / "vk_replay.cpp").read_text(encoding="utf-8")
    rec = (vk / "vk_recorder.h").read_text(encoding="utf-8")
    work = (vk / "vk_work.h").read_text(encoding="utf-8")
    fails = []

    def check(ok, why):
        if not ok:
            fails.append(why)

    check("V(vkCmdCopyQueryPoolResults)" in rec, "the copy is not in the recorder's list of calls")
    check("#define vkCmdCopyQueryPoolResults(...)" in work and "rx_vkCmdCopyQueryPoolResults" in work,
          "vk_work.h does not send the copy through the recorder")
    make = block(replay, "void query_ring_make() {")
    check('getenv("RX_VK_QUERY_RING")' in block(replay, "bool query_ring_on() {"), "RX_VK_QUERY_RING is not read")
    check(before(make, "create_buffer_cached(", "host_coherent(ts_ring_alloc)", "destroy_buffer(ts_ring, ts_ring_alloc);",
                 "ts_ring_map = "), "the ring is used without host-coherent memory")
    begin = block(replay, "void gpu_time_begin(Recording& r) {")
    check(before(begin, "query_ring_make();", "if (ts_ring_map && ts_pending[r.slot]) {", "vkCmdCopyQueryPoolResults(r.cmd, ts_pool,",
                 "VK_QUERY_RESULT_64_BIT | VK_QUERY_RESULT_WITH_AVAILABILITY_BIT", "VK_PIPELINE_STAGE_2_HOST_BIT",
                 "vkCmdPipelineBarrier2(r.cmd, &di);", "ts_ring_copied[r.slot] = true;",
                 "vkCmdResetQueryPool(r.cmd, ts_pool, 2 * r.slot, 2);"),
          "the copy is not made before the reset, with availability, behind a host barrier")
    copy = begin[begin.index("vkCmdCopyQueryPoolResults("):begin.index("VkMemoryBarrier2")]
    check("WAIT_BIT" not in copy, "the copy waits on the GPU for queries a use that was never submitted would never write")
    collect = block(replay, "void gpu_time_collect(Recording& r, bool sent = true) {")
    check(before(collect, "if (ts_ring_map) {", "if (!ts_ring_copied[r.slot]) return;", "ts_ring_copied[r.slot] = false;",
                 "if (!sent) return;", "if (!w[1] || !w[3]) return;", "} else {", "vkGetQueryPoolResults(dev.device, ts_pool,"),
          "the ring is read without its copy, its submit or the availability words, or the old read is gone")
    for marker in ("Recording& begin_recording(uint64_t value) {", "Recording& begin_segment_recording(uint64_t value) {"):
        body = block(replay, marker)
        check(before(body, "const bool sent = r.submitted;", "recording_wait(r);", "gpu_time_collect(r, sent);"),
              marker + ": whether the slot's last use was submitted is not taken before recording_wait clears it")
    for f in sorted(vk.glob("*.cpp")):
        text = f.read_text(encoding="utf-8", errors="replace")
        if "vkCmdCopyQueryPoolResults(" in text and f.name != "vk_replay.cpp" and '#include "vk_work.h"' not in text:
            check(False, f.name + " copies query results outside the recorder")
    if fails:
        for f in fails:
            print("FAIL: " + f)
        raise SystemExit(1)
    print("query ring: ok")


if __name__ == "__main__":
    main()

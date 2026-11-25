"""(ProjectReLink 88e38c0) The reaper lets the driver's submits and presents go first, and capture buffers are freed on it
(RX_VK_REAP_TURNS, RX_VK_CAP_FREE_HERE; no game, no GPU).

The driver keeps one lock for object destruction, memory frees and queue submits/presents: a destruction on the reaper while
the replay submits held that submit up. The reaper now waits, 3 ms at most, before each of its calls while a DriverTurn is
alive around a vkQueueSubmit2 / vkQueuePresentKHR. A capture buffer not kept for reuse is destroyed on the reaper. Read from
the source:
- every vkQueueSubmit2 and vkQueuePresentKHR in vk_replay.cpp (the frame's path) is made under a DriverTurn;
- the reaper calls reap_wait_turn before each function it runs, and the wait has its 3 ms limit and its switch;
- cap_buf_free sends a buffer it does not keep to the reaper unless RX_VK_CAP_FREE_HERE=1, and destroys it only once.

    python -I -B tests/test_reap_turns.py
"""
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from srccut import block  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    vk = ROOT / "gpu/vk"
    replay = (vk / "vk_replay.cpp").read_text(encoding="utf-8")
    vma = (vk / "vk_vma.cpp").read_text(encoding="utf-8")
    mem = (vk / "vk_memory.cpp").read_text(encoding="utf-8")
    internal = (vk / "vk_internal.h").read_text(encoding="utf-8")
    fails = []

    def check(ok, why):
        if not ok:
            fails.append(why)

    check("struct DriverTurn {" in internal and "extern std::atomic<int> driver_turns;" in internal, "DriverTurn is not declared")
    lines = replay.split("\n")
    calls = 0
    for i, line in enumerate(lines):
        code = line.split("//")[0]
        if re.search(r"\bvkQueue(Submit2|PresentKHR)\(", code):
            calls += 1
            near = "\n".join(lines[max(0, i - 1):i + 1])
            check("DriverTurn turn;" in near, f"vk_replay.cpp:{i + 1}: a submit or present without a DriverTurn: {line.strip()}")
    check(calls >= 6, "fewer submits and presents found than the frame's path has (%d)" % calls)

    wait = block(vma, "void reap_wait_turn() {")
    check('getenv("RX_VK_REAP_TURNS")' in wait, "RX_VK_REAP_TURNS is not read")
    check("std::chrono::milliseconds(3)" in wait and "break;" in wait, "the reaper's wait has no 3 ms limit")
    on = block(vma, "bool reap_on() {")
    check("reap_wait_turn(), fn();" in on, "the reaper does not wait for the driver's turn before each call")

    free = block(mem, "void cap_buf_free(VkBuffer buffer, VmaAllocation alloc, void* map, uint64_t size, bool from_worker = false) {")
    check("reap([buffer, alloc] { destroy_buffer(buffer, alloc); });" in free, "a capture buffer let go is not destroyed on the reaper")
    check('getenv("RX_VK_CAP_FREE_HERE")' in block(mem, "bool cap_free_reaped() {"), "RX_VK_CAP_FREE_HERE is not read")
    # (each path destroys once: inside the lock only when not reaped and not spare-fit; after it, reaped or spare-fit)
    check("if (!keep && !cap_spare_fit() && !cap_free_reaped()) destroy_buffer(buffer, alloc);" in free and
          "else if (!keep && cap_spare_fit()) destroy_buffer(buffer, alloc);" in free,
          "a capture buffer could be destroyed twice, or not at all")
    if fails:
        for f in fails:
            print("FAIL: " + f)
        raise SystemExit(1)
    print("reaper turns and capture frees: ok (%d submits and presents)" % calls)


if __name__ == "__main__":
    main()

"""Long-idle mirrors given back a few at a time (Ocarina Reborn adcb6f7, taken 2026-11-22).

A load's mirrors pass the long-idle mark together; mirrors_give_back now frees at most RX_VK_MIRROR_IDLE_MB (32) of them a
call (at least one), and memory_begin_submission calls it every 8 submissions while some are left. Frees for room are not
held back. Checked by source.

python -I -B tests/test_mirror_idle_pace.py
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    mem = (ROOT / "gpu" / "vk" / "vk_memory.cpp").read_text(encoding="utf-8")
    give = mem[mem.index("void mirrors_give_back(uint64_t want_bytes) {"):]
    give = give[:give.index("\n}\n")]
    begin = mem[mem.index("void memory_begin_submission() {"):]
    begin = begin[:begin.index("\n}\n")]
    sw = (ROOT / "gpu" / "vk" / "switches.def").read_text(encoding="utf-8")
    checks = (
        ('getenv("RX_VK_MIRROR_IDLE_MB")' in give and ": 32) << 20;" in give, "no RX_VK_MIRROR_IDLE_MB step of 32 MB"),
        ("if (!for_room && long_idle && idle_step && idle_freed > 0 && idle_freed + (p->hi - p->lo) > idle_step) {" in give and
         "mirror_idle_backlog = true;" in give, "long-idle mirrors are not held for a later call past the step"),
        ("if (for_room || long_idle) {" in give and 'for_room ? "idle, for room" : "idle"' in give, "a free for room is held back"),
        ("(mirror_idle_backlog && mirror_epoch % 8 == 0)" in begin, "the backlog is not given back every 8 submissions"),
        ("SW(RX_VK_MIRROR_IDLE_MB," in sw, "no switch row for RX_VK_MIRROR_IDLE_MB"),
    )
    failed = [w for ok, w in checks if not ok]
    for w in failed:
        print("FAIL: " + w)
    print("FAIL" if failed else "PASS: long-idle mirrors given back a few at a time")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""The Forest Temple's Bow room opens its barred door once its Stalfos are dead (OOTRR 7146d21, taken 2026-11-22).

tools/rando/rando_seed.py bow_room_fix points the lock's multi-input entry that read the eye switch's focus at the
focus's other condition (the Stalfos cleared). Checked on an AI file of that shape made here: no game files.

python -I -B tests/test_rando_bow_room.py
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def make(eye_twice=False):
    """nodes: 0 the cleared OR, 1 the focus, 2 the eye, 3 a flag; multi entries: the AND (eye, cleared out 1), the lock
    (flag, focus)"""
    names = [b"OperateOR", seed.BOW_ROOM_NAMES[0].encode(), seed.BOW_ROOM_NAMES[1].encode(), b"HoldGameDataGetBoolSimple"]
    pool = b""
    offs = []
    for n in names:
        offs.append(len(pool))
        pool += n + b"\0"
    data = bytearray(0x74 + 0x3C * len(names))
    data[:4] = b"AIB "
    struct.pack_into("<I", data, 4, 0x408)
    struct.pack_into("<I", data, 0x10, len(names))
    for i, o in enumerate(offs):
        struct.pack_into("<I", data, 0x74 + 0x3C * i + 8, o)
    multi = len(data)
    entries = [(2, 4), (0, 1), (3, 0), (1, 0)] + ([(2, 4), (3, 0)] if eye_twice else [])
    for node, out in entries:
        data += struct.pack("<II", node | out << 16, 0)
    struct.pack_into("<III", data, 0x30, len(data), 0, multi)
    struct.pack_into("<I", data, 0x24, len(data))
    return bytes(data + pool), multi


def main():
    data, multi = make()
    out = seed.bow_room_fix(data)
    lock = struct.unpack_from("<I", out, multi + 8 * 3)[0]
    check(len(out) == len(data) and lock == (0 | 1 << 16), "the lock does not read the Stalfos cleared (node 0, output 1): %#x" % lock)
    check([i for i in range(len(data)) if data[i] != out[i]] == [multi + 24, multi + 26],
          "more of the file changed than the lock's entry")
    for bad, why in ((out, "a file changed already"), (make(eye_twice=True)[0], "a file whose eye is read twice"),
                     (b"XXXX" + data[4:], "not an AI file")):
        try:
            seed.bow_room_fix(bad)
            check(False, "bow_room_fix took " + why)
        except ValueError:
            pass
    script = open(seed.__file__, encoding="utf-8").read()
    check("changed[rel] = bow_room_fix(data)" in script and seed.BOW_ROOM_LOGIC.endswith("Room_06_Prefab_6b8c.logic.module.ainb")
          and seed.FIXES_VERSION >= 70, "every seed does not write the Bow room's fix, or seeds made before are not written again")
    print("FAIL" if failed else "PASS: the Forest Temple's Bow room opens once its Stalfos are dead")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""With Skip cutscenes the Fire Temple's jailed Gorons are gone and their chests unlocked (tools/rando/rando_seed.py:
FIRE_GORONS, FIRE_CHESTS, ainb_fix_inputs), on an AI file made here. No game files."""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = []


def check(ok, what):
    if not ok:
        failed.append(what)
        print("FAIL: " + what)


def ai_file(inputs, classes=("OperateOR", "ActorLogicNpc", "ActorLogicSimpleActor")):
    """An AIB 0x408 file: nodes of `classes` (0x3C bytes from 0x74, the class name's place at +8), the inputs' part at
    the header's +0x34 with 16-byte `inputs` (name, node | output << 16, flags, value), then the strings."""
    names = sorted({c for c in classes} | {n for n, *_ in inputs})
    pool_text = b"".join(n.encode() + b"\0" for n in names)
    place = {}
    at = 1
    for n in names:
        place[n] = at
        at += len(n) + 1
    pool_text = b"\0" + pool_text
    nodes = b"".join(struct.pack("<8sI48s", b"", place[c], b"") for c in classes)
    ins_at = 0x74 + len(nodes)
    ins = b"".join(struct.pack("<IIII", place[n], src, flags, value) for n, src, flags, value in inputs)
    pool = ins_at + len(ins)
    head = bytearray(0x74)
    head[:4] = b"AIB "
    struct.pack_into("<I", head, 4, 0x408)
    struct.pack_into("<I", head, 0x10, len(classes))
    struct.pack_into("<I", head, 0x24, pool)
    struct.pack_into("<I", head, 0x34, ins_at)
    return bytes(head) + nodes + ins + pool_text


def main():
    linked = 2 | 1 << 16
    data = ai_file([("Logic_Delete", linked, 0, 0), ("Logic_Delete", linked, 0, 0), ("Logic_Delete", 0xFFFF, 0x01800000, 0),
                    ("Logic_Create", 0xFFFF, 0x01800000, 1)])
    out = seed.ainb_fix_inputs(data, "Logic_Delete", "ActorLogicNpc", 2)
    u32 = lambda d, a: struct.unpack_from("<I", d, a)[0]
    at = u32(out, 0x34)
    check(len(out) == len(data) and [(u32(out, at + 16 * k + 4), u32(out, at + 16 * k + 8), u32(out, at + 16 * k + 12)) for k in range(4)] ==
          [(0xFFFF, 0x01800000, 1), (0xFFFF, 0x01800000, 1), (0xFFFF, 0x01800000, 0), (0xFFFF, 0x01800000, 1)],
          "the Goron's and its wall's Logic_Delete are not made a fixed true, or another input moved")
    for bad, why in ((lambda: seed.ainb_fix_inputs(out, "Logic_Delete", "ActorLogicNpc", 2), "a file already done"),
                     (lambda: seed.ainb_fix_inputs(data, "Logic_Delete", "ActorLogicTreasureBox", 2), "a file without the node"),
                     (lambda: seed.ainb_fix_inputs(data, "Logic_Delete", "ActorLogicNpc", 1), "a file of more inputs than known")):
        try:
            bad()
            check(False, "ainb_fix_inputs took " + why)
        except ValueError:
            pass
    script = open(os.path.join(HERE, "..", "tools", "rando", "rando_seed.py"), encoding="utf-8").read()
    check(len(seed.FIRE_GORONS) == 9 and len(seed.FIRE_CHESTS) == 8 and not set(seed.FIRE_GORONS) & set(seed.FIRE_CHESTS) and
          all(r.startswith("Logic/FireTemple_Level_Room_") and r.endswith(".logic.module.ainb") for r in seed.FIRE_GORONS + seed.FIRE_CHESTS),
          "the nine Gorons' rooms and eight chests' logic files are not listed")
    check("    if a.skip_cutscenes:   # (the Fire Temple's jailed Gorons gone and their chests unlocked, FIRE_GORONS)" in script and
          seed.FIXES_VERSION >= 64, "the Gorons are not taken away with Skip cutscenes, or seeds made before are not written again")
    print("FAIL" if failed else "PASS: the Fire Temple's jailed Gorons gone with Skip cutscenes")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""Bug 133 (the owner's run 2026-11-23): with every mask on the Happy Mask Shop's shelves (masks_open), borrowing the
Bunny Hood started the mask salesman's trade, and no other mask could be had until it was sold. Every seed (fixes 78)
makes the trade's step (an enum of the game's list, hash MASK_TRADE, seen in the owner's save) start a new game at
Complete, as the game has it once the trade is done: masks swapped freely. enum_default is tried here on a made-up list
of the same shape (big-endian BYML: Data.Enum, each {DefaultValue, Hash, Values}); it was tried on the game's list by
hand (2026-11-23: same size, and a second run refused). No game files.

python -I -B tests/test_rando_mask_trade.py
"""
import os
import struct
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools", "rando"))
import rando_seed as seed  # noqa: E402

failed = False


def check(ok, what):
    global failed
    if not ok:
        failed = True
        print("FAIL: " + what)


def byml(enums):
    """a big-endian BYML {Data: {Enum: [{DefaultValue: u32, Hash: u32, Values: [u64, ...]}, ...]}}"""
    keys = sorted(["Data", "Enum", "DefaultValue", "Hash", "Values"])
    ki = {k: i for i, k in enumerate(keys)}
    out = bytearray(16)
    # (the key table)
    key_at = len(out)
    strings = b""
    offs = []
    for k in keys:
        offs.append(4 + 4 * (len(keys) + 1) + len(strings))
        strings += k.encode() + b"\0"
    out += bytes((0xC2,)) + len(keys).to_bytes(3, "big") + b"".join(struct.pack(">I", o) for o in offs) + struct.pack(">I", offs[-1] + 0) + strings
    out += bytes(-len(out) & 3)

    def put(node):
        nonlocal out
        out += bytes(-len(out) & 3)
        at = len(out)
        out += node
        return at

    def u64(v):
        return put(struct.pack(">Q", v))

    def dict_node(entries):   # entries: [(key, type, value)] sorted by key
        return bytes((0xC1,)) + len(entries).to_bytes(3, "big") + b"".join(ki[k].to_bytes(3, "big") + bytes((t,)) + struct.pack(">I", v) for k, t, v in entries)

    def array_node(entries):   # [(type, value)]
        n = len(entries)
        return bytes((0xC0,)) + n.to_bytes(3, "big") + bytes(t for t, _ in entries) + bytes(-n & 3) + b"".join(struct.pack(">I", v) for _, v in entries)
    nodes = []
    for default, h, values in enums:
        vals = put(array_node([(0xD5, u64(v)) for v in values]))
        nodes.append(put(dict_node([("DefaultValue", 0xD3, default), ("Hash", 0xD3, h), ("Values", 0xC0, vals)])))
    enum_at = put(array_node([(0xC1, n) for n in nodes]))
    data_at = put(dict_node([("Enum", 0xC0, enum_at)]))
    root = put(dict_node([("Data", 0xC1, data_at)]))
    struct.pack_into(">2sHIII", out, 0, b"BY", 7, key_at, 0, root)
    return bytes(out)


def main():
    m = seed.murmur3
    steps = [m(n.encode()) for n in ("NotReady", "Ready", "UntilRentMaskOfKeaton", "Step08", "Complete")]
    other = (m(b"NotReady"), 0x1234, steps)
    data = byml([other, (m(b"NotReady"), seed.MASK_TRADE, steps)])
    new = seed.enum_default(data)
    check(len(new) == len(data), "the list's size changed")
    changed = [i for i in range(len(data)) if data[i] != new[i]]
    check(len(changed) >= 1 and new[:changed[0]] == data[:changed[0]] and max(changed) - min(changed) < 4,
          "more than the trade's default was changed")
    at = min(changed) - min(changed) % 4 if changed else 0
    check(changed and struct.unpack_from(">I", new, at)[0] == m(b"Complete"), "the trade does not start at Complete")
    try:
        seed.enum_default(new)
        check(False, "a list made already was made again")
    except ValueError:
        pass
    try:
        seed.enum_default(byml([other]))
        check(False, "a list without the trade's enum was not refused")
    except ValueError:
        pass
    try:
        seed.enum_default(byml([(m(b"NotReady"), seed.MASK_TRADE, steps[:-1])]))
        check(False, "an enum without Complete was not refused")
    except ValueError:
        pass
    src = open(seed.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("new = enum_default(new)" in main_src and main_src.index("new = masks_open(new)") < main_src.index("new = enum_default(new)"),
          "the list of flags is not given the trade done")
    check(seed.FIXES_VERSION >= 78 and seed.MASK_TRADE == 3925934864, "FIXES_VERSION not past 77, or not the save's trade enum")
    print("FAIL" if failed else "PASS: a new game starts with the mask salesman's trade done")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

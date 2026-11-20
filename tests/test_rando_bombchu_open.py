"""Bombchu Bowling and the Bombchu Shop open from the start, the shop day and night, and the Water Temple's gate free of
the Ice Cavern (tools/rando/rando_seed.py: ALWAYS_EXP, always_exp, ainb_exp_swap, flow_switch_yes, WATER_WALL), on
files made here: a list of flags with the formulas, and an AI file. No game files."""
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


def flag_list(target_steps):
    """A big-endian BYML like the game's GameDataList: Data.Bool (ALWAYS_FLAG) and Data.BoolExp (the quest done,
    ALWAYS_EXP with `target_steps`, and a formula holding the steps OR and NOT), each step's numbers 64-bit."""
    keys = sorted(["Bool", "BoolExp", "Data", "Hash", "Values"])
    k = {name: i for i, name in enumerate(keys)}
    out = bytearray(b"BY\x00\x07" + bytes(12))
    body = []

    def put(b):
        while len(out) % 4:
            out.append(0)
        at = len(out)
        out.extend(b)
        return at

    key_at = put(bytes((0xC2, 0, 0, len(keys))) + bytes(4 * (len(keys) + 1)))
    offs = []
    for name in keys:
        offs.append(len(out) - key_at)
        out.extend(name.encode() + b"\0")
    offs.append(len(out) - key_at)
    for i, o in enumerate(offs):
        struct.pack_into(">I", out, key_at + 4 + 4 * i, o)
    u64 = lambda v: put(struct.pack(">Q", v))

    def arr(items):   # [(type, value)]
        n = len(items)
        return put(bytes((0xC0, 0, 0, n)) + bytes(t for t, _ in items) + bytes(-n & 3) + b"".join(struct.pack(">I", v) for _, v in items))

    def dic(items):   # [(key, type, value)]
        return put(bytes((0xC1, 0, 0, len(items))) + b"".join(k[n].to_bytes(3, "big") + bytes((t,)) + struct.pack(">I", v) for n, t, v in items))

    def step(*nums):
        return arr([(0xD5, u64(n)) for n in nums])

    quest = 0x1002B466
    formula = lambda h, steps: dic([("Hash", 0xD3, h), ("Values", 0xC0, arr([(0xC0, s) for s in steps]))])
    exps = [formula(seed.murmur3(seed.BOMBCHU_QUEST.encode()), [step(1, quest), step(2, seed.murmur3(b"Complete"))]),
            formula(seed.murmur3(seed.ALWAYS_EXP.encode()), [step(*s) for s in target_steps(quest)]),
            formula(0x1234, [step(0, seed.murmur3(seed.ALWAYS_FLAG.encode())), step(0, 0x55), step(5), step(4)])]
    bools = [dic([("Hash", 0xD3, seed.murmur3(seed.ALWAYS_FLAG.encode()))])]
    data = dic([("Bool", 0xC0, arr([(0xC1, b) for b in bools])), ("BoolExp", 0xC0, arr([(0xC1, e) for e in exps]))])
    root = dic([("Data", 0xC1, data)])
    struct.pack_into(">III", out, 4, key_at, 0, root)
    return bytes(out)


def evaluate(data, name, values):
    """ALWAYS_EXP's formula in `data` worked out with the flags `values` ({hash: truth})"""
    key_at, _, root = struct.unpack_from(">III", data, 4)
    count = lambda at: int.from_bytes(data[at + 1:at + 4], "big")
    u32 = lambda at: struct.unpack_from(">I", data, at)[0]
    keys = [data[key_at + u32(key_at + 4 + 4 * i):data.index(b"\0", key_at + u32(key_at + 4 + 4 * i))].decode() for i in range(count(key_at))]
    fields = lambda at: {keys[int.from_bytes(data[at + 4 + 8 * i:at + 7 + 8 * i], "big")]: u32(at + 8 + 8 * i) for i in range(count(at))}
    items = lambda at: [u32(at + 4 + (count(at) + 3 & ~3) + 4 * i) for i in range(count(at))]
    exps = items(fields(fields(root)["Data"])["BoolExp"])
    f = next(fields(e) for e in exps if fields(e)["Hash"] == seed.murmur3(name.encode()))
    stack = []
    for s in items(f["Values"]):
        nums = [struct.unpack_from(">Q", data, v)[0] for v in items(s)]
        if nums[0] == 0:
            stack.append(values[nums[1]])
        elif nums[0] == 4:
            b, a = stack.pop(), stack.pop()
            stack.append(a or b)
        elif nums[0] == 5:
            stack.append(not stack.pop())
        else:
            return None
    return stack[0] if len(stack) == 1 else None


def main():
    # ---- the formula made always true, on steps the list already has ----
    was = flag_list(lambda quest: [(12, quest), (2, seed.murmur3(b"Ready"))])
    new = seed.always_exp(was)
    check(len(new) == len(was) + (-len(was) & 3) + 24 and new[:len(was)] != was, "the formula is not given a new array of its own at the file's end")
    flag = seed.murmur3(seed.ALWAYS_FLAG.encode())
    check(evaluate(new, seed.ALWAYS_EXP, {flag: False}) is True and evaluate(new, seed.ALWAYS_EXP, {flag: True}) is True,
          "the formula is not true whatever its flag is")
    check(evaluate(new, seed.BOMBCHU_QUEST, {}) is None, "the quest's own formula changed")
    for bad, what in ((new, "a list made already"), (flag_list(lambda quest: [(12, quest), (2, seed.murmur3(b"Complete"))]), "another formula")):
        try:
            seed.always_exp(bad)
            check(False, "always_exp took %s" % what)
        except ValueError:
            pass
    check(seed.ALWAYS_EXP == "Get_StoneOfFire_IsAfter_Ready_Exp", "ALWAYS_EXP is not the formula nothing reads")

    # ---- an AI file's one reading of the quest moved to it ----
    pool_strings = b"\0OperateOR\0" + seed.BOMBCHU_QUEST.encode() + b"\0Other\0"
    head = bytearray(0x74 + 0x40)
    head[:4] = b"AIB "
    struct.pack_into("<I", head, 4, 0x408)
    struct.pack_into("<I", head, 0x24, len(head))
    struct.pack_into("<I", head, 0x80, 11)   # (the reading: the quest's place in the strings)
    ai = bytes(head) + pool_strings
    out = seed.ainb_exp_swap(ai)
    pool = struct.unpack_from("<I", out, 0x24)[0]
    at = struct.unpack_from("<I", out, 0x80)[0]
    check(out[pool + at:].split(b"\0")[0] == seed.ALWAYS_EXP.encode() and out[:len(ai)].replace(out[0x80:0x84], ai[0x80:0x84]) == ai,
          "the AI file's reading does not read ALWAYS_EXP, or more of the file changed")
    two = bytearray(ai)
    struct.pack_into("<I", two, 0x90, 11)
    for bad, what in ((out, "a file made already"), (bytes(two), "a file reading the quest twice")):
        try:
            seed.ainb_exp_swap(bad)
            check(False, "ainb_exp_swap took %s" % what)
        except ValueError:
            pass

    # ---- the files and the seed's steps ----
    script = open(seed.__file__, encoding="utf-8").read()
    check(len(seed.CHU_LOGIC) == 3 and seed.BOMBCHU_DOOR_LOGIC in seed.CHU_LOGIC and "new = always_exp(new if new is not None else was)" in script,
          "the shop's door, the bowling's attendant and its game are not all moved to ALWAYS_EXP, or the list of flags not made")
    check([e for _, e in seed.CHU_FLOWS] == ["Event137", "Event14"] and "files[rel] = flow_switch_yes(" in script and
          "out[cases + 12:cases + 14] = data[cases + 4:cases + 6]" in script,
          "the bowling's question does not go on to its answer 0 (true: the quest done) either way")
    check(seed.WATER_WALL == ("FldObj_AirWall_All", "SageOfWater_IsAfter_Step03_Exp") and "changed[rel] = water_wall_out(data)" in script,
          "the Water Temple's gate wall is not taken out of the adult's Hyrule Field")
    check(seed.WATER_GATE == {"HavePlayedEvent.Dm_WaterTemple_0000": True, "WaterTemple_EmitGatePillar": True} and "**WATER_GATE," in script,
          "a new game does not start with the Water Temple's gate open (its cutscene played, its pillars risen)")
    host = open(os.path.join(HERE, "..", "host", "hos_main.c"), encoding="utf-8").read()
    check("static const uint32_t gate[2] = {0x392b86fbu, 0xab74fd3cu};" in host and
          [seed.murmur3(n.encode()) for n in seed.WATER_GATE] == [0x392b86fb, 0xab74fd3c],
          "the game's side does not open the Water Temple's gate on a save made before, or by other flags")
    check(seed.FIXES_VERSION >= 60, "FIXES_VERSION not raised: seeds made before would keep the shut doors")
    print("FAIL" if failed else "PASS: Bombchu Bowling, the Bombchu Shop and the Water Temple's gate open")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

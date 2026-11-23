"""Bug 127 (the owner's run 2026-11-23): Goron City's sign-order grotto gave no chest for the right order after one wrong
try. The right chest's gate reads node 31 = OR(node 28, the saved _clear), node 28 being OR(clear_InLocalScene,
faild_InLocalScene): a wrong try's faild_InLocalScene held it back while Link stayed in Goron City. sign_grotto_fix makes
node 31's first input node 26's (clear_InLocalScene) in place of node 28's. Tried here on a made-up logic file of the
same layout (it was tried on the game's by hand, 2026-11-23: 2 bytes changed, a second run refused). No game files.

python -I -B tests/test_rando_sign_grotto.py
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


def ainb(kinds, entries):
    """a made-up AIB 0x408: nodes of these classes (0x3C bytes each from 0x74, the class name's place at +8), a
    multi-input table of these (node | output << 16) entries, then the strings"""
    nodes_end = 0x74 + 0x3C * len(kinds)
    table = nodes_end
    table_end = table + 8 * len(entries)
    pool = table_end
    where, strings = {}, b"\0"
    for k in sorted(set(kinds)):
        where[k] = len(strings)
        strings += k.encode() + b"\0"
    out = bytearray(pool + len(strings))
    out[:4] = b"AIB "
    struct.pack_into("<I", out, 4, 0x408)
    struct.pack_into("<I", out, 0x10, len(kinds))
    struct.pack_into("<I", out, 0x24, pool)
    struct.pack_into("<I", out, 0x30, table_end)
    struct.pack_into("<I", out, 0x38, table)
    for i, k in enumerate(kinds):
        struct.pack_into("<I", out, 0x74 + 0x3C * i + 8, where[k])
    for j, e in enumerate(entries):
        struct.pack_into("<II", out, table + 8 * j, e, 0)
    out[pool:] = strings
    return bytes(out)


def main():
    kinds = ["Other"] * 40
    for i in (10, 26, 27):
        kinds[i] = "HoldGameDataGetBoolSimple"
    for i in (28, 31):
        kinds[i] = "OperateOR"
    entries = list(range(40))
    entries[28], entries[29] = 28 | 1 << 16, 10
    data = ainb(kinds, entries)
    try:
        new = seed.sign_grotto_fix(data)
        table = struct.unpack_from("<I", data, 0x38)[0]
        check(len(new) == len(data) and struct.unpack_from("<I", new, table + 8 * 28)[0] == 26, "node 31 does not read node 26's output 0")
        check(new[:table + 8 * 28] == data[:table + 8 * 28] and new[table + 8 * 28 + 4:] == data[table + 8 * 28 + 4:], "more than the one input was changed")
    except ValueError as e:
        check(False, "the made-up file was refused: %s" % e)
        new = data
    for what, bad in (("made already", new), ("not node 28's input", ainb(kinds, entries[:28] + [27 | 1 << 16] + entries[29:])),
                      ("another node class", ainb(kinds[:31] + ["OperateAND"] + kinds[32:], entries))):
        try:
            seed.sign_grotto_fix(bad)
            check(False, "a file %s was not refused" % what)
        except ValueError:
            pass
    src = open(seed.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("changed[rel] = sign_grotto_fix(data)" in main_src and main_src.index("sign_grotto_fix(data)") < main_src.index("    # ---- the size table ----"),
          "every seed does not write the grotto's logic")
    check(seed.SIGN_GROTTO_LOGIC == "Logic/HidingHole_Level_Hole_17_Prefab_e58a.logic.module.ainb" and seed.FIXES_VERSION >= 80, "not the grotto's file, or FIXES_VERSION not past 79")
    print("FAIL" if failed else "PASS: Goron City's sign-order grotto gives its right chest after a wrong try")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

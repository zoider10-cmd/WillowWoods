"""Bug 119 (the owner's run 2026-11-23): the Longshot did not catch the vines of Lake Hylia's dead tree. A thin
FldObj_AirWall_Hookshot lies along the vines in both Links' Hyrule Field maps while the Water Temple's room 7 is not
walked into (WaterTemple_Room07_00). Fixes 73 took it out (read as a wall that stops the Hookshot) and the vines still
did not catch; from fixes 79 it is what the Hookshot catches, kept there always (water_wall_out with TREE_WALL, keep:
its Presence taken away); that hid the marker, so fixes 82 takes it out again. The Longshot then reached the tree but
did not pull. The tree's collision is baked into Hyrule Field's static compound (HyruleField_<age>_X7_Z10), and this build
seems to read only a shape's first material there (the owner: the vines' hit makes no sound after a load, then the
wood's). Tried and changed nothing: its own mesh's Wood (83), its climbing boxes (84), unbaked (85: drawn dark). From
fixes 86 the baked Wood, the tree's first material, is tagged StickHookshot (baked_tree_hook). Checked on made-up files
and by source. No game files.

python -I -B tests/test_rando_tree_wall.py
"""
import collections
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


def actor(gyaml, flag=None):
    d = collections.OrderedDict(Gyaml=("string", gyaml))
    if flag:
        d["Presence"] = ("dict", collections.OrderedDict(FlagName=("string", flag)))
    return ("dict", d)


def main():
    check(seed.TREE_WALL == ("FldObj_AirWall_Hookshot", "WaterTemple_Room07_00"), "TREE_WALL changed")
    check(len(seed.TREE_WALL_FILES) == 2 and all("HyruleField_" in f for f in seed.TREE_WALL_FILES), "not both Links' Hyrule Field maps")
    tree = ("dict", collections.OrderedDict(Actors=("array", [actor("FldObj_AirWall_Hookshot"), actor("FldObj_AirWall_Hookshot", "WaterTemple_Room07_00"),
                                                                actor("FldObj_AirWall_All", "SageOfWater_IsAfter_Step03_Exp")])))
    try:
        data = seed.byml_build(tree, 7)
        out, _ = seed.byml_parse(seed.water_wall_out(data, seed.TREE_WALL))
        left = [(a[1]["Gyaml"][1], a[1].get("Presence", ("", {}))[1].get("FlagName", ("", ""))[1] if "Presence" in a[1] else "")
                for a in out[1]["Actors"][1]]
        check(left == [("FldObj_AirWall_Hookshot", ""), ("FldObj_AirWall_All", "SageOfWater_IsAfter_Step03_Exp")],
              "the tree's hookshot-stopping wall alone is not taken out: %s" % left)
        out2, _ = seed.byml_parse(seed.water_wall_out(data))
        check(len(out2[1]["Actors"][1]) == 2, "the Water Temple gate's wall is no longer taken out by default")
    except (ValueError, struct.error, KeyError) as e:
        check(False, "a made-up map: %s" % e)
    # (a made-up static compound: the header's table bounds, another Wood, the tree's four, another entry after)
    vines = [(2, 0x2B, 1 << 44), (2, 0x2B, 1 << 40), (2, 0x2B, 1 << 44)]
    rows = [(14, 0, 0), (7, 0, 0), (14, 0, 1 << 3)] + vines + [(14, 0, 0)]
    table = b"".join(struct.pack("<IIQ", *e) for e in rows)
    head = bytearray(b"Phive" + bytes(0x40 - 5))
    struct.pack_into("<II", head, 0x20, 0x40, 0x40 + len(table))
    baked = bytes(head) + table + b"rest"
    try:
        got = seed.baked_tree_hook(baked)
        want = rows[:2] + [(14, 0, (1 << 3) | (1 << 44))] + rows[3:]
        check(len(got) == len(baked) and [struct.unpack_from("<IIQ", got, 0x40 + 16 * k) for k in range(len(rows))] == want and got[-4:] == b"rest",
              "the tree's baked Wood alone (the one before its vines) is not tagged StickHookshot")
    except (ValueError, struct.error) as e:
        check(False, "a made-up static compound: %s" % e)
    for bad in (baked.replace(b"Phive", b"Nope!", 1), baked[:0x40] + table[:16 * 3] + table[16 * 4:]):
        try:
            seed.baked_tree_hook(bad)
            check(False, "a file that is no Phive file, or without the tree's four materials, was changed")
        except ValueError:
            pass
    check(len(seed.BAKED_TREE_FILES) == 2 and all("HyruleField" in f and "_X7_Z10." in f and f.endswith(".bphsc.zs") for f in seed.BAKED_TREE_FILES)
          and not any(hasattr(seed, n) for n in ("tree_hook_wood", "tree_climb_hook", "tree_unbake")),
          "not both ages' baked squares of the tree, or an earlier try is still made")
    src = open(seed.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("for rel in TREE_WALL_FILES:" in main_src and "changed[rel] = water_wall_out(data, TREE_WALL)" in main_src and
          main_src.index("water_wall_out(data, TREE_WALL)") < main_src.index("    # ---- the size table ----"),
          "the tree's wall is not taken out of both maps before the size table")
    check("for rel in BAKED_TREE_FILES:" in main_src and "changed[rel] = baked_tree_hook(" in main_src and
          main_src.index("baked_tree_hook(") < main_src.index("    # ---- the size table ----")
          and "sizes[rel[:-3]] = len(changed[rel])" in main_src[main_src.index("baked_tree_hook("):][:200],
          "the tree's baked wood is not tagged in both files before the size table, or their sizes not counted")
    check(seed.FIXES_VERSION >= 86, "FIXES_VERSION not past 85")
    print("FAIL" if failed else "PASS: Lake Hylia's dead tree without its hookshot-stopping wall, its baked wood a Hookshot catch")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

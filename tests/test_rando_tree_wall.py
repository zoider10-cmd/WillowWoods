"""Bug 119 (the owner's run 2026-11-23): the Longshot did not catch the vines of Lake Hylia's dead tree. A thin
FldObj_AirWall_Hookshot lies along the vines in both Links' Hyrule Field maps while the Water Temple's room 7 is not
walked into (WaterTemple_Room07_00). Fixes 73 took it out (read as a wall that stops the Hookshot) and the vines still
did not catch; from fixes 79 it is what the Hookshot catches, kept there always (water_wall_out with TREE_WALL, keep:
its Presence taken away); that hid the marker, so fixes 82 takes it out again. The Longshot then reached the tree but
did not pull: its collision's Wood had no StickHookshot tag (Kokiri's catching ivy has it). From fixes 83 the tree's
Wood is tagged (tree_hook_wood on TREE_HOOK_FILE). Checked on a made-up map file and mesh and by source. No game files.

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
    # (a made-up mesh: the header's table place and size, Wood with a tag of its own, a Grass/Vine left as it was)
    table = struct.pack("<IIQ", 14, 0, 1 << 3) + struct.pack("<IIQ", 2, 0x2B, seed.TAG_CLIMB)
    mesh = bytearray(b"Phive\x00" + bytes(0x40 - 6)) + table + bytes(16)
    struct.pack_into("<I", mesh, 0x10, 0x40), struct.pack_into("<I", mesh, 0x20, len(table))
    try:
        got = seed.tree_hook_wood(bytes(mesh))
        check(len(got) == len(mesh) and struct.unpack_from("<IIQ", got, 0x40) == (14, 0, (1 << 3) | (1 << 44)) and
              got[0x50:] == bytes(mesh[0x50:]) and got[:0x40] == bytes(mesh[:0x40]),
              "the tree's Wood is not tagged StickHookshot alone, or more than it changed")
    except (ValueError, struct.error) as e:
        check(False, "a made-up mesh: %s" % e)
    for bad in (b"NotPhive" + bytes(0x60), bytes(mesh[:0x40]) + struct.pack("<IIQ", 2, 0x2B, 0) + bytes(32)):
        try:
            seed.tree_hook_wood(bad)
            check(False, "a file that is no Phive mesh, or has no Wood, was changed")
        except ValueError:
            pass
    check(seed.TAG_STICK_HOOKSHOT == 1 << 44 and seed.MATERIAL_WOOD == 14 and "Land_LakeHrl_Tree_A_01__Physical" in seed.TREE_HOOK_FILE,
          "the tag, the material or the tree's mesh changed")
    src = open(seed.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("for rel in TREE_WALL_FILES:" in main_src and "changed[rel] = water_wall_out(data, TREE_WALL)" in main_src and
          main_src.index("water_wall_out(data, TREE_WALL)") < main_src.index("    # ---- the size table ----"),
          "the tree's wall is not taken out of both maps before the size table")
    check("changed[rel] = tree_hook_wood(" in main_src and main_src.index("tree_hook_wood(") < main_src.index("    # ---- the size table ----")
          and "sizes[rel[:-3]] = len(changed[rel])" in main_src[main_src.index("tree_hook_wood("):][:300],
          "the tree's wood is not tagged before the size table, or its size not counted")
    check(seed.FIXES_VERSION >= 83, "FIXES_VERSION not past 82")
    print("FAIL" if failed else "PASS: Lake Hylia's dead tree without its hookshot-stopping wall, its wood a Hookshot catch")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

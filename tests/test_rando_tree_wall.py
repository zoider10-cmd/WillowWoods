"""Bug 119 (the owner's run 2026-11-23): the Longshot did not catch the vines of Lake Hylia's dead tree. A hookshot-
stopping wall stands round the tree in both Links' Hyrule Field maps until the Water Temple's room 7 is walked into
(WaterTemple_Room07_00); every seed takes it out (water_wall_out with TREE_WALL). Checked on a made-up map file and by
source. No game files.

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
              "the tree's wall alone is not taken out: %s" % left)
        out2, _ = seed.byml_parse(seed.water_wall_out(data))
        check(len(out2[1]["Actors"][1]) == 2, "the Water Temple gate's wall is no longer taken out by default")
    except (ValueError, struct.error, KeyError) as e:
        check(False, "a made-up map: %s" % e)
    src = open(seed.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("for rel in TREE_WALL_FILES:" in main_src and "changed[rel] = water_wall_out(data, TREE_WALL)" in main_src and
          main_src.index("water_wall_out(data, TREE_WALL)") < main_src.index("    # ---- the size table ----"),
          "the tree's wall is not taken out of both maps before the size table")
    check(seed.FIXES_VERSION >= 73, "FIXES_VERSION not past 72")
    print("FAIL" if failed else "PASS: Lake Hylia's dead tree takes the Longshot from the start")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

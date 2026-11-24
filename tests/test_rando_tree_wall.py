"""Bug 119 (the owner's run 2026-11-23): the Longshot did not catch the vines of Lake Hylia's dead tree. A thin
FldObj_AirWall_Hookshot lies along the vines in both Links' Hyrule Field maps while the Water Temple's room 7 is not
walked into (WaterTemple_Room07_00). Fixes 73 took it out (read as a wall that stops the Hookshot) and the vines still
did not catch; from fixes 79 it is what the Hookshot catches, kept there always (water_wall_out with TREE_WALL, keep:
its Presence taken away); that hid the marker, so fixes 82 takes it out again. The Longshot then reached the tree but
did not pull: the two climbing boxes over its vines (AirwallForClimb) stand in front of them with no StickHookshot tag
(Kokiri's catching ivy, one mesh, has it). From fixes 84 the boxes carry Wall_StickHookshot too (tree_climb_hook; 83
had tagged the mesh's Wood, which changed nothing in play); 84 changed nothing either: the tree is placed Bakeable, its
body the copy in Hyrule Field's static compound, so from fixes 85 it is placed without (tree_unbake). Checked on a made-up map file and pack and by source.

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
    # (the tree placed without Bakeable, its other keys and the other actors as they were)
    def placed(gyaml, **more):
        d = collections.OrderedDict(Gyaml=("string", gyaml))
        d.update((k, ("string", v)) for k, v in more.items())
        return ("dict", d)
    field = ("dict", collections.OrderedDict(Actors=("array", [placed(seed.TREE_NAME, Bakeable="yes", Name="tree"), placed("Rock", Bakeable="yes")])))
    try:
        got, _ = seed.byml_parse(seed.tree_unbake(seed.byml_build(field, 7)))
        check([sorted(a[1]) for a in got[1]["Actors"][1]] == [["Gyaml", "Name"], ["Bakeable", "Gyaml"]],
              "the tree alone is not placed without Bakeable: %s" % [list(a[1]) for a in got[1]["Actors"][1]])
    except (ValueError, KeyError, struct.error) as e:
        check(False, "a made-up map for the tree: %s" % e)
    check(seed.TREE_NAME == "Land_LakeHrl_Tree_A_01" and "changed[rel] = tree_unbake(water_wall_out(data, TREE_WALL))" in open(seed.__file__, encoding="utf-8").read(),
          "the tree is not placed without Bakeable in both Hyrule Field maps")
    # (a made-up pack: the climbing shape's two boxes, and another part left as it was)
    def box(*presets):
        return ("dict", collections.OrderedDict(MaterialPresets=("array", [("string", x) for x in presets])))
    shape = ("dict", collections.OrderedDict(Box=("array", [box("AirWallForClimb"), box("AirWallForClimb", "Wall_StickHookshot")])))
    try:
        pack = seed.sarc_write({seed.TREE_CLIMB_SHAPE: seed.byml_build(shape, 7), "Actor/Other.bgyml": b"other"})
        parts = seed.sarc_read(seed.tree_climb_hook(pack))
        got, _ = seed.byml_parse(parts[seed.TREE_CLIMB_SHAPE])
        check([[x[1] for x in b[1]["MaterialPresets"][1]] for b in got[1]["Box"][1]] ==
              [["AirWallForClimb", "Wall_StickHookshot"], ["AirWallForClimb", "Wall_StickHookshot"]] and parts["Actor/Other.bgyml"] == b"other",
              "the tree's climbing boxes are not each a Hookshot catch once, or another part changed")
    except (ValueError, KeyError, struct.error) as e:
        check(False, "a made-up pack: %s" % e)
    try:
        seed.tree_climb_hook(seed.sarc_write({"Actor/Other.bgyml": b"other"}))
        check(False, "a pack without the climbing shape was changed")
    except ValueError:
        pass
    check(seed.HOOK_PRESET == "Wall_StickHookshot" and "Land_LakeHrl_Tree_A_01" in seed.TREE_PACK and "AirwallForClimb" in seed.TREE_CLIMB_SHAPE
          and not hasattr(seed, "tree_hook_wood"), "the preset, the tree's pack or shape changed, or its mesh is still changed")
    src = open(seed.__file__, encoding="utf-8").read()
    main_src = src[src.index("\ndef main():"):]
    check("for rel in TREE_WALL_FILES:" in main_src and "changed[rel] = tree_unbake(water_wall_out(data, TREE_WALL))" in main_src and
          main_src.index("water_wall_out(data, TREE_WALL)") < main_src.index("    # ---- the size table ----"),
          "the tree's wall is not taken out of both maps before the size table")
    check("pack_files[rel] = tree_climb_hook(was)" in main_src and main_src.index("tree_climb_hook(") < main_src.index("    # ---- the size table ----")
          and "pack_parts.add(TREE_CLIMB_SHAPE)" in main_src, "the tree's climbing boxes are not changed before the size table, or their part's size not raised")
    check(seed.FIXES_VERSION >= 85, "FIXES_VERSION not past 84")
    print("FAIL" if failed else "PASS: Lake Hylia's dead tree without its hookshot-stopping wall, the vines' climbing boxes a Hookshot catch")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
